"""Requirement 1 -- online DOI/PMID authenticity validation.

Given a search-result ``source`` dict, resolve its DOI against **Crossref** and
its PMID against **PubMed E-utilities**, then classify the outcome as one of::

    verified is True   -> the identifier exists (and metadata is consistent)
    verified is False  -> the identifier definitively does not exist
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

BADGE_VERIFIED = "✅已核验"
BADGE_INVALID = "❌无效DOI"
BADGE_MISMATCH = "⚠️信息不一致"
BADGE_UNVERIFIED = "❓未能核验"


def badge_for(result: VerifyResult) -> str:
    """Human-facing badge derived from a :class:`VerifyResult`."""
    if result.verified is True:
        return BADGE_MISMATCH if result.warnings else BADGE_VERIFIED
    if result.verified is False:
        return BADGE_INVALID
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
            source.get("pmcid"),
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
            return
        if res.not_found:
            result.verified = False
            result.source = "crossref"
            return
        if not res.ok:
            result.verified = None
            result.source = "unavailable"
            return

        result.source = "crossref"
        message = (res.json or {}).get("message", {}) if isinstance(res.json, dict) else {}
        remote_titles = message.get("title") or []
        if not remote_titles:
            result.verified = None
            result.warnings.append("crossref_no_title")
            return

        result.verified = True
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
            return
        result.source = "pubmed"
        payload = res.json or {}
        entry = (payload.get("result") or {}).get(pmid) if isinstance(payload, dict) else None
        if not entry or entry.get("error"):
            result.verified = False
            return
        result.verified = True

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

    @staticmethod
    def _link_resolvable(source: dict) -> bool:
        link = str(first_nonempty(source, ("link", "url")) or "")
        return any(host in link for host in _RESOLVABLE_HOSTS)

    # -- batch --------------------------------------------------------------
    async def verify_many(
        self, sources: list[dict], concurrency: int | None = None
    ) -> dict[int, VerifyResult]:
        """Verify all sources that carry a 1-based ``index``.

        Returns ``{index: VerifyResult}``. The concurrency is bounded by the
        shared :class:`HttpClient` semaphore, so no extra pool is created here.
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

        results = await asyncio.gather(*(_one(i, s) for i, s in targets))
        return {idx: res for idx, res in results}


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
