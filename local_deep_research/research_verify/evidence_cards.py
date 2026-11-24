"""Compact, field-level evidence cards for biomedical source synthesis.

Metadata cards describe supplied record fields. Passage cards describe exact
candidate text and its source offsets; neither card is a support verdict.
"""
from __future__ import annotations

import json
import re


from .source_identity import classify_source


DEFAULT_FIELDS = (
    "title", "authors", "journal", "year", "language", "study_type",
    "platform", "technology", "population", "sample_size", "groups", "outcome",
)

# These are useful supplied fields, not synonyms for the requested columns.
# Retain them under their original keys rather than interpreting a cohort as a
# group, a species as a study population, or a generic n as a sample count.
ADDITIONAL_METADATA_FIELDS = (
    "pubyear", "publication_year", "pubdate", "publication_date",
    "journal_title", "publication_name", "container_title",
    "instrument", "platform_name", "assay", "workflow", "method",
    "species", "organism", "sample_population", "n", "sample_n",
    "number_of_samples", "grouping", "cohort", "arms", "publication_types",
    "study_design", "outcomes", "endpoint", "endpoints",
)


def _present(value):
    return value not in (None, "", [], {})


# Flat provider records also carry article text, identity, and application state.
# These have their own evidence channels; never render them as study fields.
_RECORD_FIELDS = set("""
    index link url source engine source_engine title authors authorString author_string
    journal journal_ref year language languages lang doi pmid pmcid issn eissn essn
    abstract snippet body content full_content fetched_content raw_content raw_content_sha256
    content_type evidence_type source_kind document_type publication_status identity_status
    canonical_url formal_citation_allowed publication_status_reason publication_state
    peer_review_status relevance_status evidence_scope temporal_validity contradiction_status
    authority_status version_resolution publication_versions related_articles related_notices
    identity_provenance peer_review_status_provenance relevance_filter_status
    impact_factor impact_factor_value journal_impact_factor jif metric_year passes_threshold
    jcr_provenance jcr_check_status impact_factor_provenance jif_provenance
    platform technology population sample_size groups outcome
    headers settings settings_snapshot request response raw metadata additional_source_metadata
    connection session cookies full_text html text score rank payload raw_payload raw_response
    records request_params config debug trace fulltext raw_html pdf pdf_text
""".split())
_PRIVATE_KEY = re.compile(
    r"password|secret|credential|authorization|api.?key|token|cookie|session|header|connection|"
    r"(?:^|_)(?:user_?id|username|private|internal|settings|auth)(?:_|$)", re.I
)


def _plain_metadata(value, depth=0):
    if depth > 8:
        return False
    if type(value) in (str, int, float, bool) or value is None:
        return True
    if isinstance(value, (list, tuple)):
        return all(_plain_metadata(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and not key.startswith("_") and not _PRIVATE_KEY.search(key)
                   and _plain_metadata(item, depth + 1)
                   for key, item in value.items())
    return False


def additional_source_metadata(source):
    """Carry supplied public study fields with their original names and units."""
    fields = {key: source[key] for key in ADDITIONAL_METADATA_FIELDS if _present(source.get(key))}
    supplied = source.get("additional_source_metadata")
    if isinstance(supplied, dict):
        candidates = {**supplied, **source}
    else:
        candidates = source
    for key, value in candidates.items():
        if not isinstance(key, str) or key.startswith("_") or key in fields or key in _RECORD_FIELDS:
            continue
        if _PRIVATE_KEY.search(key) or not _present(value):
            continue
        if not _plain_metadata(value):
            continue
        if len(json.dumps(value, ensure_ascii=False)) <= 4096:
            fields[key] = value
    return fields


def _value(source, field):
    # Explicit bibliographic year keys share a schema meaning. Full dates stay
    # available under their own keys; no scientific field binding is inferred.
    keys = ("year", "pubyear", "publication_year") if field == "year" else (field,)
    for key in keys:
        value = source.get(key)
        if _present(value):
            return value, key
    return None, None


def build_source_card(source: dict, requested_fields=DEFAULT_FIELDS) -> dict:
    """Describe supplied metadata; missing keys do not establish paper omissions."""
    normalized = classify_source(source or {})
    fields = {}
    missing_metadata = []
    requested = list(requested_fields or DEFAULT_FIELDS)
    retained = [key for key in ADDITIONAL_METADATA_FIELDS if _present(normalized.get(key))]
    for field in dict.fromkeys(requested + retained):
        value, key = _value(normalized, field)
        if value is None:
            fields[field] = {"value": None, "status": "unknown", "source_key": None,
                             "reason": "missing_metadata"}
            missing_metadata.append(field)
        else:
            fields[field] = {"value": value, "status": "provided_metadata", "source_key": key}
    abstract = normalized.get("abstract")
    body = normalized.get("body") or (
        normalized.get("full_content")
        if str(normalized.get("content_type") or "").casefold() in {"full_text", "fulltext", "body"}
        else None
    )
    abstract_available = isinstance(abstract, str) and bool(abstract.strip())
    body_available = isinstance(body, str) and bool(body.strip())
    return {
        "index": normalized.get("index"),
        "identity": {
            "doi": normalized.get("doi"),
            "pmid": normalized.get("pmid"),
            "pmcid": normalized.get("pmcid"),
            "canonical_url": normalized.get("canonical_url", ""),
            "identity_status": normalized.get("identity_status", "missing"),
            "identity_provenance": normalized.get("identity_provenance", {}),
        },
        "provenance": {
            "source_kind": normalized.get("source_kind", "unknown"),
            "document_type": normalized.get("document_type", "unknown"),
            "publication_status": normalized.get("publication_status", "unverified"),
            "publication_state": normalized.get("publication_state", "unknown"),
            "peer_review_status": normalized.get("peer_review_status", "unknown"),
            "peer_review_status_provenance": normalized["peer_review_status_provenance"],
            "relevance_status": normalized.get("relevance_status", "unknown"),
            "evidence_scope": normalized.get("evidence_scope", "unknown"),
            "temporal_validity": normalized.get("temporal_validity", "unknown"),
            "contradiction_status": normalized.get("contradiction_status", "unknown"),
            "status_reason": normalized.get("publication_status_reason", ""),
            "formal_citation_allowed": bool(normalized.get("formal_citation_allowed")),
        },
        "evidence": {
            "abstract": {"available": abstract_available,
                         "status": "available" if abstract_available else "not_available"},
            "body": {"available": body_available,
                     "status": "available" if body_available else "not_available"},
        },
        "fields": fields,
        "missing_metadata": missing_metadata,
    }


def build_source_cards(sources, requested_fields=DEFAULT_FIELDS) -> list[dict]:
    return [build_source_card(source, requested_fields) for source in sources or [] if isinstance(source, dict)]
