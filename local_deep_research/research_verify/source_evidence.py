"""Evidence preparation and provenance helpers used by the report boundary.

The collector may contain search hits, publisher pages, repository copies and
formal PubMed/Europe PMC records at the same time.  This module keeps those
origins visible and optionally retrieves a bounded original article body for a
cited record.  Retrieval is advisory: an unavailable body is recorded as an
unavailable evidence state and never deletes a source or a report sentence.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import os
from typing import Any

from .source_identity import classify_source, publication_status, source_kind


_MISSING = object()
_ACTIVE_EGRESS: ContextVar[Any] = ContextVar("ldr_active_egress_context", default=None)


def active_egress_context(value=_MISSING):
    """Get the current egress snapshot or install one for a ``with`` block.

    Existing call sites use both ``active_egress_context()`` as a getter and
    ``with active_egress_context(snapshot):`` as a scoped setter, so the small
    dual interface is intentional.
    """
    if value is _MISSING:
        return _ACTIVE_EGRESS.get()

    @contextmanager
    def _scope():
        token = _ACTIVE_EGRESS.set(value)
        try:
            yield value
        finally:
            _ACTIVE_EGRESS.reset(token)

    return _scope()


def normalize_source(source: dict) -> dict:
    """Add deterministic identity/provenance fields to a source in place."""
    if not isinstance(source, dict):
        return source
    source.update(classify_source(source))
    return source


def is_search_page(source: dict) -> bool:
    """Return whether a record is a search-results page rather than an article."""
    return source_kind(source) == "search_result"


def source_rejection(source: dict) -> str | None:
    """Return an advisory reason when a source is unsuitable as formal evidence.

    The caller may use this to annotate a citation check.  It is deliberately
    not a publication gate: ``publication_status`` remains on the source and
    the report renderer can show an unverified lead separately.
    """
    if not isinstance(source, dict):
        return "source_not_mapping"
    normalized = classify_source(source)
    status = normalized.get("publication_status")
    reason = normalized.get("publication_status_reason")
    if status == "formal":
        return None
    if status == "conflict":
        return "identity_mismatch"
    if status == "nonformal" and reason == "search_results_page":
        return "search_results_page"
    if status == "preprint":
        return "preprint_unverified"
    if status == "nonformal":
        return reason or "nonformal_source"
    if status == "unverified":
        if any(normalized.get(key) for key in ("doi", "pmid", "pmcid")):
            # A stable identifier can still be assessed for textual support;
            # the publication renderer keeps its unverified status visible.
            return None
        return reason or "identity_unavailable"
    if not normalized.get("doi") and not normalized.get("pmid") and not normalized.get("pmcid"):
        return "identity_unavailable"
    return reason or "identity_unconfirmed"


def _body_available(source: dict) -> bool:
    content_type = str(source.get("content_type") or "").casefold().replace("-", "_")
    if content_type not in {"full_text", "fulltext", "body"}:
        return bool(source.get("body"))
    return bool(source.get("body") or source.get("full_content") or source.get("content"))


class ArticleEvidenceClient:
    """Bounded adapter around :class:`research_verify.evidence_fetch.EvidenceFetcher`.

    The adapter is synchronous because citation preparation runs at the
    synchronous report boundary.  Tests and deployments can inject a custom
    fetcher through ``settings['_evidence_fetcher']`` without network access.
    """

    def __init__(self, settings=None, *, egress_context=None, fetcher=None):
        self.settings = dict(settings or {}) if isinstance(settings, dict) else {}
        self.egress_context = egress_context if egress_context is not None else active_egress_context()
        self.fetcher = fetcher
        self.events: list[dict] = []

    def __enter__(self):
        if self.fetcher is None:
            injected = self.settings.get("_evidence_fetcher")
            if injected is not None:
                self.fetcher = injected
            else:
                try:
                    from .evidence_fetch import EvidenceFetcher

                    settings = dict(self.settings)
                    if self.egress_context is not None:
                        settings.setdefault("_egress_context", self.egress_context)
                    try:
                        requests = max(6, min(20, int(settings.get("_evidence_requests", 12))))
                    except (TypeError, ValueError):
                        requests = 12
                    self.fetcher = EvidenceFetcher(
                        settings=settings,
                        seconds=30,
                        # Field extraction often asks for 20 papers. Keep
                        # retrieval bounded, but do not stop at the first six
                        # when the request explicitly asks for a larger set.
                        requests=requests,
                    )
                except Exception as exc:  # optional retrieval dependency
                    self.events.append({"status": "unavailable", "error_type": type(exc).__name__})
                    self.fetcher = None
        return self

    def __exit__(self, *_exc):
        close = getattr(self.fetcher, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        return False

    def fetch(self, source: dict) -> dict | None:
        """Fetch a cited body's original text, preserving provenance fields."""
        if not isinstance(source, dict) or _body_available(source):
            return None
        if self.fetcher is None:
            return None
        try:
            text = None
            if hasattr(self.fetcher, "article"):
                text = self.fetcher.article(source)
            if text:
                return {
                    "body": text,
                    "full_content": text,
                    "content": text,
                    "content_type": "full_text",
                    "evidence_type": "retrieved_full_text",
                    "evidence_status": "retrieved",
                    "evidence_source": "Europe PMC/PubMed linked article",
                }
            # A direct publisher URL is a fallback lead only.  Evidence remains
            # marked as retrieved text with completeness unconfirmed.
            link = source.get("link") or source.get("url")
            if link and hasattr(self.fetcher, "web"):
                title = str(source.get("title") or source.get("name") or "article")
                candidates = self.fetcher.web(title, url=str(link)) or []
                candidate = next((item for item in candidates if item.get("fetched_content")), None)
                if candidate:
                    return {
                        "fetched_content": candidate["fetched_content"],
                        "content_type": "retrieved_web_document",
                        "evidence_type": "publisher_page_excerpt",
                        "evidence_status": "retrieved_unconfirmed",
                    }
        except Exception as exc:
            self.events.append({
                "source_index": source.get("index"),
                "status": "unavailable",
                "error_type": type(exc).__name__,
            })
        return None


def _source_list(collector):
    if collector is None:
        return []
    records = getattr(collector, "results", None)
    if isinstance(records, list):
        return records
    records = getattr(collector, "_results", None)
    return records if isinstance(records, list) else []


def prepare_cited_evidence(claims, collector, cfg=None, *, egress_context=None) -> dict:
    """Prepare bodies for cited sources and return a traceable status summary."""
    citations = []
    for claim in claims or []:
        for citation in getattr(claim, "citations", []) or []:
            try:
                value = int(citation)
            except (TypeError, ValueError):
                continue
            if value not in citations:
                citations.append(value)
    source_by_index = {}
    for source in _source_list(collector):
        if not isinstance(source, dict):
            continue
        try:
            source_by_index[int(source.get("index"))] = source
        except (TypeError, ValueError):
            continue
    # SourceLookup exposes find_by_index but not necessarily a results list.
    for index in citations:
        if index not in source_by_index and hasattr(collector, "find_by_index"):
            try:
                candidate = collector.find_by_index(index)
            except Exception:
                candidate = None
            if isinstance(candidate, dict):
                source_by_index[index] = candidate

    body_sources = fetched_sources = 0
    unavailable_sources = []
    statuses = {}
    with active_egress_context(egress_context) if egress_context is not None else _null_scope():
        with ArticleEvidenceClient(egress_context=egress_context) as client:
            for index in citations:
                source = source_by_index.get(index)
                if source is None:
                    unavailable_sources.append(index)
                    statuses[str(index)] = "missing_source"
                    continue
                normalize_source(source)
                if _body_available(source):
                    body_sources += 1
                    statuses[str(index)] = "available"
                    continue
                update = client.fetch(source)
                if update:
                    source.update(update)
                    normalize_source(source)
                    fetched_sources += 1
                    body_sources += 1
                    statuses[str(index)] = str(update.get("evidence_status") or "fetched")
                else:
                    unavailable_sources.append(index)
                    statuses[str(index)] = "unavailable"
            if client.events:
                statuses["_events"] = client.events
    if unavailable_sources:
        status = "partial" if body_sources else "unavailable"
    else:
        status = "complete" if citations else "no_citations"
    return {
        "status": status,
        "requested_sources": len(citations),
        "body_sources": body_sources,
        "fetched_sources": fetched_sources,
        "unavailable_sources": unavailable_sources,
        "source_status": statuses,
    }


def prepare_cited_source_bodies(sources, citations, *, settings=None, fetcher=None,
                                egress_context=None, limit=24) -> dict:
    """Optionally expose bounded original bodies before writer context assembly.

    This is an evaluation-only evidence-access seam.  It does not judge a
    claim, add citations, delete sources, or gate publication.  The default
    runtime leaves it disabled; when enabled, only cited source indices are
    considered and every unavailable fetch remains explicit.
    """
    try:
        max_sources = max(0, int(limit))
    except (TypeError, ValueError):
        max_sources = 24
    wanted = []
    for value in citations or []:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if index not in wanted:
            wanted.append(index)
    wanted = wanted[:max_sources]
    by_index = {}
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        try:
            by_index[int(source.get('index'))] = source
        except (TypeError, ValueError):
            continue
    statuses = {}
    fetched = available = 0
    unavailable = []
    with active_egress_context(egress_context) if egress_context is not None else _null_scope():
        with ArticleEvidenceClient(settings=settings, egress_context=egress_context, fetcher=fetcher) as client:
            for index in wanted:
                source = by_index.get(index)
                if source is None:
                    statuses[str(index)] = 'missing_source'
                    unavailable.append(index)
                    continue
                normalize_source(source)
                if _body_available(source):
                    statuses[str(index)] = 'available'
                    available += 1
                    continue
                update = client.fetch(source)
                if update:
                    source.update(update)
                    normalize_source(source)
                    statuses[str(index)] = str(update.get('evidence_status') or 'fetched')
                    fetched += 1
                    available += 1
                else:
                    statuses[str(index)] = 'unavailable'
                    unavailable.append(index)
            if client.events:
                statuses['_events'] = client.events
    return {
        'status': 'complete' if not unavailable else ('partial' if available else 'unavailable'),
        'requested_sources': len(wanted),
        'available_sources': available,
        'fetched_sources': fetched,
        'unavailable_sources': unavailable,
        'source_status': statuses,
    }


def prepare_selected_evidence(sources, *, limit=6, egress_context=None) -> dict:
    """Fetch a bounded set of source bodies for field-extraction reports.

    This is a source-reading step, not a citation audit.  It lets a request
    for groups/sample sizes/platforms see a body when the search result only
    carried an abstract, while keeping network work bounded and advisory.
    """
    selected = [source for source in (sources or []) if isinstance(source, dict)][:max(0, int(limit))]
    body_sources = fetched_sources = 0
    unavailable = []
    with active_egress_context(egress_context) if egress_context is not None else _null_scope():
        with ArticleEvidenceClient(egress_context=egress_context) as client:
            for source in selected:
                normalize_source(source)
                if _body_available(source):
                    body_sources += 1
                    continue
                update = client.fetch(source)
                if update:
                    source.update(update)
                    normalize_source(source)
                    fetched_sources += 1
                    body_sources += 1
                else:
                    unavailable.append(source.get("index"))
    return {
        "status": "complete" if not unavailable else ("partial" if body_sources else "unavailable"),
        "requested_sources": len(selected),
        "body_sources": body_sources,
        "fetched_sources": fetched_sources,
        "unavailable_sources": unavailable,
    }


@contextmanager
def _null_scope():
    yield None

