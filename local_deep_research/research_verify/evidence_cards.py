"""Compact, field-level evidence cards for biomedical source synthesis.

Metadata cards describe supplied record fields. Passage cards describe exact
candidate text and its source offsets; neither card is a support verdict.
"""
from __future__ import annotations

import hashlib

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


def additional_source_metadata(source):
    """Retain supplied values under original schema keys, without field binding."""
    return {key: source[key] for key in ADDITIONAL_METADATA_FIELDS if _present(source.get(key))}


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


def build_passage_card(source_id, source_text: str, start: int, end: int, text: str,
                       *, field: str | None = None, method: str = "candidate",
                       score: float | None = None,
                       lexical_match: bool | None = None) -> dict:
    """Bind a candidate passage to the exact supplied source text.

    This records candidate availability only. It does not decide support,
    entailment, correction, or publication status.
    """
    if not isinstance(source_text, str) or not isinstance(text, str):
        raise TypeError("source_text and text must be strings")
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise ValueError("invalid passage offsets")
    if end > len(source_text) or source_text[start:end] != text:
        raise ValueError("passage text does not match source offsets")
    card = {
        "schema_version": "evidence_passage_card.v1",
        "source_id": source_id,
        "offsets": {"start": start, "end": end},
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "source_text_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "status": "candidate_passage",
        "method": str(method or "candidate"),
    }
    if field is not None:
        card["field"] = str(field)
    if score is not None:
        card["relevance_hint"] = float(score)
    if lexical_match is not None:
        card["lexical_match"] = bool(lexical_match)
    return card


def build_complete_source_card(source_id, source_text: str, *, basis: str,
                               source_identity: dict | None = None) -> dict:
    """Represent all supplied acquired text without claiming paper completeness."""
    card = build_passage_card(
        source_id, source_text, 0, len(source_text), source_text,
        field="complete_source_text", method="complete_acquired_text",
        lexical_match=False,
    )
    card.update({
        "status": "complete_acquired_text",
        "scope": str(basis or "retrieved text; completeness unconfirmed"),
        "completeness": "unconfirmed",
    })
    if isinstance(source_identity, dict):
        card["source_identity"] = {
            str(key): value for key, value in source_identity.items()
            if value not in (None, "", [], {})
        }
    return card

