"""Small, topic-independent corrections to LDR source identity and feedback."""
from .retrieval import academic_snippet
from .source_identity import with_identity


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
        if relations:
            existing["related_articles"] = relations
        if existing.get("abstract") and any(existing.get(k) for k in ("doi", "pmid", "journal")):
            # Render identity from the retained record, not a second header
            # embedded in an independently selected longer snippet.
            existing["snippet"] = academic_snippet(existing, existing["abstract"])

    def add_results(self, results, engine_name="web"):
        with self._lock:
            offset = CollectionOffset(len(self._all_links))
            offset.added = offset.reused = offset.excluded = 0
            offset.unregistered = []
            returned = []
            returned_ids = set()
            for raw in results:
                if not isinstance(raw, dict):
                    continue
                if self._is_preprint_url(raw):
                    offset.excluded += 1
                    continue
                record = with_identity(raw)
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
    if offset.excluded:
        lines.append(f"{offset.excluded} hits excluded by the existing source policy.")
    return "\n\n".join(lines)
