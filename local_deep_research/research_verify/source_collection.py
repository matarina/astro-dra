"""Small, topic-independent corrections to LDR source identity and feedback."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from .retrieval import academic_snippet
from .source_identity import with_identity


_SOURCE_SCOPE: ContextVar[tuple[object, int | None, float] | None] = ContextVar(
    "subagent_source_scope", default=None,
)


@contextmanager
def subagent_source_scope(collector, generation, deadline):
    token = _SOURCE_SCOPE.set((collector, generation, deadline))
    try:
        yield
    finally:
        _SOURCE_SCOPE.reset(token)


def require_open_source_scope(collector: object, generation: int | None) -> None:
    """Check under the collection lock before mutating shared evidence."""
    scope = _SOURCE_SCOPE.get()
    if scope is not None and scope[0] is collector:
        _, opened_generation, deadline = scope
        if opened_generation != generation or monotonic() >= deadline:
            raise RuntimeError("Subagent source collection scope expired")


def sources_for_draft(current, accumulated, draft):
    """Keep current hits and recover only uniquely indexed sources cited in prose.

    This resolves explicit syntax, not scientific relevance or entailment. Do
    not widen to the whole archive or mutate the collector/previous records.
    """
    from copy import deepcopy
    from .citation_display import cited_indices
    from .evidence import SourceLookup

    selected = list(current or [])
    lookup = SourceLookup([*selected, *(accumulated or [])])
    current_ids = {int(source["index"]) for source in SourceLookup(selected).records()}
    requested = cited_indices(draft or "")
    recovered, missing, ambiguous = [], [], []
    for index in requested:
        if index in lookup.ambiguous_indices:
            ambiguous.append(index)
        elif (source := lookup.find_by_index(index)) is None:
            missing.append(index)
        elif index not in current_ids:
            selected.append(deepcopy(source))
            recovered.append(index)
    return selected, {
        "scope": "citation_index_lookup_only",
        "requested_ids": requested, "recovered_ids": recovered,
        "missing_ids": missing, "ambiguous_ids": ambiguous,
        "current_source_count": len(current or []), "selected_source_count": len(selected),
        "status": "incomplete" if missing or ambiguous else "resolved" if requested else "no_citations",
    }


class CollectionOffset(int):
    """Keep the original integer API and attach feedback for this call only."""


class SourceCollectionMixin:
    def find_or_add_result(self, result, engine_name="web"):
        return super().find_or_add_result(with_identity(result), engine_name)

    def _find_duplicate(self, result):
        keys = self._identity_keys(result)
        identifiers = {k.split(":", 1)[0]: k for k in keys
                       if k.startswith(("doi:", "pmid:", "pmcid:"))}
        for key in keys:
            if key.startswith("title:"):
                continue
            existing = self._identity_map.get(key)
            if existing is None:
                continue
            old = {k.split(":", 1)[0]: k for k in self._identity_keys(existing)
                   if k.startswith(("doi:", "pmid:", "pmcid:"))}
            if any(old[name] != identifiers[name] for name in old.keys() & identifiers.keys()):
                continue
            return existing
        return None

    def _merge_duplicate(self, existing, incoming):
        relations = list(existing.get("related_articles") or [])
        for relation in incoming.get("related_articles") or []:
            if relation not in relations:
                relations.append(relation)
        super()._merge_duplicate(existing, incoming)
        # Fetch tools use find_or_add_result, which also calls this hook while
        # holding the collector lock. A duplicate after reset is evidence for
        # the current call too; reuse its ID and return the retained record.
        if not any(item is existing for item in self._results):
            self._results.append(existing)
        link = existing.get("link") or existing.get("url")
        if link and link not in self._sources:
            self._sources.append(link)
        if relations:
            existing["related_articles"] = relations
        if existing.get("abstract") and any(existing.get(k) for k in ("doi", "pmid", "journal")):
            # Render identity from the retained record, not a second header
            # embedded in an independently selected longer snippet.
            existing["snippet"] = academic_snippet(existing, existing["abstract"])

    def add_results(self, results, engine_name="web"):
        with self._lock:
            require_open_source_scope(self, getattr(self, "_collection_generation", None))
            offset = CollectionOffset(len(self._all_links))
            offset.added = offset.reused = offset.excluded = 0
            offset.flagged = 0
            offset.flagged_sources = []
            offset.unregistered = []
            returned = []
            returned_ids = set()
            for raw in results:
                if not isinstance(raw, dict):
                    continue
                record = with_identity(raw)
                if record.get("publication_status") not in {None, "formal"}:
                    offset.flagged += 1
                    offset.flagged_sources.append({
                        "index": record.get("index"),
                        "status": record.get("publication_status"),
                        "reason": record.get("publication_status_reason"),
                        "url": record.get("link") or record.get("url"),
                    })
                existing = self._find_duplicate(record)
                if existing is not None:
                    self._merge_duplicate(existing, record)
                    if not any(item is existing for item in self._results):
                        self._results.append(existing)
                    offset.reused += 1
                    record = existing
                elif len(self._results) >= self._max_results:
                    offset.unregistered.append(record)
                    # A later item in this same batch can still be a known hit.
                    continue
                else:
                    record["index"] = str(len(self._all_links) + 1)
                    record["source_engine"] = engine_name
                    if "link" not in record and "url" in record:
                        record["link"] = record["url"]
                    self._results.append(record)
                    self._all_links.append(record)
                    if record.get("link"):
                        self._sources.append(record["link"])
                    for key in self._identity_keys(record):
                        self._identity_map[key] = record
                    offset.added += 1
                if record.get("index") not in returned_ids:
                    returned.append(record)
                    returned_ids.add(record.get("index"))
            results[:] = returned
            offset.limit = self._max_results
            return offset


def format_collection_results(results, offset, original_formatter):
    if not isinstance(offset, CollectionOffset):
        return original_formatter(results, offset)
    pending = offset.unregistered
    status = f"{len(pending)} not registered"
    if pending:
        status += " because the source budget is full"
    lines = [f"Search hits: {offset.added} newly registered, {offset.reused} already registered, {status}."]
    if any(r.get("relevance_filter_status") == "unavailable" for r in results):
        lines.append("Some candidates were returned while relevance screening was unavailable; "
                     "they have not passed that screening.")
    if results:
        lines.append(original_formatter(results, offset))
    if pending:
        lines.append(f"Source budget: {offset.limit}. The following hits have no citation IDs. "
                     "They are search hits, not a zero-result search; their URLs can be fetched if needed.")
        for record in pending:
            lines.append(f"Unregistered: {record.get('title', '')} "
                         f"({record.get('link') or record.get('url') or ''})\n"
                         f"{str(record.get('snippet') or '')[:1200]}")
    if getattr(offset, "flagged", 0):
        lines.append(
            f"{offset.flagged} hits were retained with provenance warnings; "
            "they are not formal citation records until identity is confirmed."
        )
    return "\n\n".join(lines)
