"""Requirement 1 -- online DOI/PMID authenticity validation.

Given a search-result ``source`` dict, resolve its DOI against **Crossref** and
its PMID against **PubMed E-utilities**, then classify the outcome as one of::

    verified is True   -> the queried provider returned the same identifier
    verified is False  -> legacy externally supplied result; not emitted here
    verified is None   -> could not be checked (offline / transport error)

Contract (see the detailed plan, §0.2):

* never block the main flow -- a transport error degrades to ``unverified``;
* never silently pass -- a metadata mismatch is recorded as a ``warning``;
* concurrency-limited HTTP via the shared :class:`HttpClient`.

The module is deliberately usable both from the ``_finalize`` hot-patch and as
a standalone CLI (``python -m research_verify.doi_validator --doi ...``).
"""

from __future__ import annotations

import argparse
import asyncio
import json

import httpx
from loguru import logger

from .config import VerifyConfig, get_config
from .http_client import HttpClient
from .models import VerifyResult
from .record_identity import make_record_provenance
from .textutil import (
    extract_doi,
    extract_pmid,
    first_nonempty,
    normalize_title,
    normalize_year,
    now_iso,
    truncate,
)

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
PUBMED_ESUMMARY_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
)
# Link hosts that indicate a resolvable identifier even without DOI/PMID.
_RESOLVABLE_HOSTS = (
    "pubmed.ncbi.nlm.nih.gov",
    "doi.org",
    "dx.doi.org",
    "ncbi.nlm.nih.gov",
)

BADGE_VERIFIED = "✅标识记录已查得"
BADGE_INVALID = "❌无效DOI"
BADGE_MISMATCH = "⚠️信息不一致"
BADGE_UNVERIFIED = "❓未能核验"


def badge_for(result: VerifyResult) -> str:
    """Human-facing badge derived from a :class:`VerifyResult`."""
    if result.verified is True:
        if not result.record_provenance:
            return BADGE_UNVERIFIED
        return BADGE_MISMATCH if result.warnings else BADGE_VERIFIED
    if result.verified is False:
        return BADGE_UNVERIFIED
    return BADGE_UNVERIFIED


class DoiValidator:
    """Validate DOI/PMID existence with bounded concurrency."""

    def __init__(self, http: HttpClient, cfg: VerifyConfig | None = None) -> None:
        self._http = http
        self._cfg = cfg or get_config()

    # -- per-source ---------------------------------------------------------
    async def verify(self, source: dict) -> VerifyResult:
        """Verify a single source. Never raises for expected I/O failures."""
        doi = extract_doi(
            source.get("doi"),
            source.get("DOI"),
            source.get("link"),
            source.get("url"),
        )
        pmid = extract_pmid(
            source.get("pmid"),
            source.get("_pmid"),
        )
        result = VerifyResult(doi=doi, pmid=pmid, verified_at=now_iso())

        if doi:
            await self._verify_crossref(doi, source, result)
        elif pmid:
            await self._verify_pubmed(pmid, source, result)
        else:
            # No identifier -- fall back to whether the link points somewhere
            # that could resolve, but do not claim existence.
            if self._link_resolvable(source):
                result.source = "link"
            else:
                result.source = "unavailable"
            result.verified = None
        return result

    async def _verify_crossref(
        self, doi: str, source: dict, result: VerifyResult
    ) -> None:
        res = await self._http.get(
            CROSSREF_URL.format(doi=doi),
            params={"mailto": self._cfg.crossref_mailto},
        )
        if res.transport_error:
            result.verified = None
            result.source = "unavailable"
            result.lookup_status = "unavailable"
            return
        if res.not_found:
            # /works covers Crossref's registry. Other agencies' valid DOIs
            # also return 404 here; do not declare the identifier nonexistent.
            result.verified = None
            result.source = "crossref"
            result.lookup_status = "not_found_in_registry"
            result.warnings.append("crossref_record_not_found")
            return
        if not res.ok:
            result.verified = None
            result.source = "unavailable"
            result.lookup_status = "unavailable"
            return

        result.source = "crossref"
        message = res.json.get("message") if isinstance(res.json, dict) else None
        receipt = make_record_provenance("crossref", message)
        if not receipt:
            result.verified = None
            result.lookup_status = "malformed_response"
            return
        if receipt["identifiers"].get("doi") != doi.casefold():
            result.verified = None
            result.lookup_status = "response_identifier_mismatch"
            return

        result.verified = True
        result.lookup_status = "record_found"
        result.record_provenance = receipt
        self._compare_metadata(source, message, result)

    async def _verify_pubmed(
        self, pmid: str, source: dict, result: VerifyResult
    ) -> None:
        res = await self._http.get(
            PUBMED_ESUMMARY_URL,
            params={"db": "pubmed", "id": pmid, "retmode": "json"},
        )
        if res.transport_error or not res.ok:
            result.verified = None
            result.source = "unavailable"
            result.lookup_status = "unavailable"
            return
        result.source = "pubmed"
        payload = res.json
        entries = payload.get("result") if isinstance(payload, dict) else None
        entry = entries.get(pmid) if isinstance(entries, dict) else None
        if not isinstance(entry, dict) or entry.get("error"):
            result.verified = None
            result.lookup_status = "remote_error" if isinstance(entry, dict) and entry.get("error") else "malformed_response"
            return
        receipt = make_record_provenance("pubmed", entry)
        if not receipt:
            result.verified = None
            result.lookup_status = "malformed_response"
            return
        if receipt["identifiers"].get("pmid") != pmid:
            result.verified = None
            result.lookup_status = "response_identifier_mismatch"
            return
        result.verified = True
        result.lookup_status = "record_found"
        result.record_provenance = receipt
        self._compare_pubmed_metadata(source, entry, result)

    def _compare_metadata(
        self, source: dict, message: dict, result: VerifyResult
    ) -> None:
        """Record a warning when Crossref title/year disagree with the source."""
        remote_title = " ".join(message.get("title") or [])
        local_title = first_nonempty(source, ("title", "name"))
        if local_title and remote_title:
            if normalize_title(remote_title) != normalize_title(local_title):
                result.title_ok = False
                result.warnings.append(
                    f"title_mismatch: local={truncate(str(local_title), 80)!r} "
                    f"crossref={truncate(remote_title, 80)!r}"
                )
            else:
                result.title_ok = True

        remote_year = normalize_year(
            first_nonempty(message, ("issued", "published", "published-print"))
        )
        local_year = normalize_year(first_nonempty(source, ("year", "published", "publication_date", "pubdate")))
        if remote_year and local_year and remote_year != local_year:
            result.year_ok = False
            result.warnings.append(
                f"year_mismatch: local={local_year} crossref={remote_year}"
            )
        elif remote_year and local_year:
            result.year_ok = True

        remote_journal = first_nonempty(message, ("container-title", "short-container-title"))
        if isinstance(remote_journal, list):
            remote_journal = remote_journal[0] if remote_journal else None
        local_journal = first_nonempty(source, ("journal", "journal_ref", "container-title"))
        if local_journal and remote_journal:
            result.journal_ok = normalize_title(str(local_journal)) == normalize_title(str(remote_journal))
            if result.journal_ok is False:
                result.warnings.append(
                    f"journal_mismatch: local={truncate(str(local_journal), 80)!r} "
                    f"crossref={truncate(str(remote_journal), 80)!r}"
                )
        local_authors = source.get("authors") or source.get("author") or []
        remote_authors = message.get("author") or []
        local_first = self._author_key(local_authors[0] if isinstance(local_authors, list) and local_authors else local_authors)
        remote_first = self._author_key(remote_authors[0] if remote_authors else None)
        if local_first and remote_first:
            result.authors_ok = local_first == remote_first
            if result.authors_ok is False:
                result.warnings.append(f"author_mismatch: local={local_first!r} crossref={remote_first!r}")

    def _compare_pubmed_metadata(self, source: dict, entry: dict, result: VerifyResult) -> None:
        """Compare the local record with PubMed's summary metadata."""
        remote_title = entry.get("title") or ""
        local_title = first_nonempty(source, ("title", "name"))
        if local_title and remote_title:
            result.title_ok = normalize_title(str(local_title)) == normalize_title(str(remote_title))
            if result.title_ok is False:
                result.warnings.append(
                    f"title_mismatch: local={truncate(str(local_title), 80)!r} "
                    f"pubmed={truncate(str(remote_title), 80)!r}"
                )
        remote_year = normalize_year(entry.get("pubdate") or entry.get("sortpubdate"))
        local_year = normalize_year(first_nonempty(source, ("year", "published", "publication_date", "pubdate")))
        if remote_year and local_year:
            result.year_ok = remote_year == local_year
            if result.year_ok is False:
                result.warnings.append(f"year_mismatch: local={local_year} pubmed={remote_year}")
        remote_journal = entry.get("fulljournalname") or entry.get("source") or ""
        local_journal = first_nonempty(source, ("journal", "journal_ref", "container-title"))
        if local_journal and remote_journal:
            result.journal_ok = normalize_title(str(local_journal)) == normalize_title(str(remote_journal))
            if result.journal_ok is False:
                result.warnings.append(
                    f"journal_mismatch: local={truncate(str(local_journal), 80)!r} "
                    f"pubmed={truncate(str(remote_journal), 80)!r}"
                )
        local_authors = source.get("authors") or source.get("author") or []
        remote_authors = entry.get("sortfirstauthor") or entry.get("authors") or []
        local_first = self._author_key(local_authors[0] if isinstance(local_authors, list) and local_authors else local_authors)
        remote_first = self._author_key(remote_authors[0] if isinstance(remote_authors, list) and remote_authors else remote_authors)
        if local_first and remote_first:
            result.authors_ok = local_first == remote_first
            if result.authors_ok is False:
                result.warnings.append(f"author_mismatch: local={local_first!r} pubmed={remote_first!r}")

    @staticmethod
    def _author_key(value) -> str:
        if isinstance(value, dict):
            value = value.get("family") or value.get("name") or value.get("fullName") or value.get("lastname")
        text = normalize_title(str(value or ""))
        return text.split()[0] if text else ""

    @staticmethod
    def _link_resolvable(source: dict) -> bool:
        from urllib.parse import urlsplit
        link = str(first_nonempty(source, ("link", "url")) or "")
        try:
            parsed = urlsplit(link)
            return parsed.scheme in {"http", "https"} and parsed.hostname in _RESOLVABLE_HOSTS
        except ValueError:
            return False

    # -- batch --------------------------------------------------------------
    async def verify_many(
        self, sources: list[dict], concurrency: int | None = None,
        *, timeout: float | None = None,
    ) -> dict[int, VerifyResult]:
        """Verify all sources that carry a 1-based ``index``.

        Returns ``{index: VerifyResult}``. The concurrency is bounded by the
        shared :class:`HttpClient` semaphore. A time budget returns completed
        checks and cancels the remaining ones before the client closes.
        """
        targets: list[tuple[int, dict]] = []
        for src in sources:
            if not isinstance(src, dict):
                continue
            idx = src.get("index")
            if idx is None:
                continue
            try:
                targets.append((int(idx), src))
            except (TypeError, ValueError):
                continue

        async def _one(idx: int, src: dict) -> tuple[int, VerifyResult]:
            try:
                return idx, await self.verify(src)
            except Exception as exc:  # defensive: never fail the batch
                logger.warning("doi_validation failed for index {}: {}", idx, exc)
                return idx, VerifyResult(verified=None, source="unavailable", verified_at=now_iso())

        if timeout is None:
            return dict(await asyncio.gather(*(_one(i, s) for i, s in targets)))
        if not targets:
            return {}
        tasks = [asyncio.create_task(_one(i, s)) for i, s in targets]
        try:
            done, _ = await asyncio.wait(tasks, timeout=timeout)
            return dict(task.result() for task in tasks if task in done)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


# --------------------------------------------------------------------------- #
# standalone CLI self-test
# --------------------------------------------------------------------------- #
async def _cli(args: argparse.Namespace) -> int:
    source: dict = {"doi": args.doi, "title": args.wrong_title} if args.doi else {"pmid": args.pmid}
    if args.wrong_title and not args.doi:
        source["title"] = args.wrong_title
    cfg = get_config()
    async with HttpClient(cfg) as http:
        result = await DoiValidator(http, cfg).verify(source)
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    print("badge:", badge_for(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="research_verify DOI/PMID validator")
    parser.add_argument("--doi")
    parser.add_argument("--pmid")
    parser.add_argument("--wrong-title", default=None, help="local title to force a mismatch")
    args = parser.parse_args(argv)
    if not args.doi and not args.pmid:
        parser.error("provide --doi or --pmid")
    return asyncio.run(_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
