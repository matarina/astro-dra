"""Additive evidence-grounding metadata and generic source enrichment.

The production report is the user-facing artifact.  This module stores the
observable evidence boundary beside it so that missing citations, unavailable
source text, identity conflicts, and detector failures remain inspectable.
Nothing in this module edits report text or decides whether a report may be
published.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .claims import Claim, extract_report_claims
from .source_identity import canonical_url, classify_source, identity_fields, identity_provenance


VERDICTS = Literal[
    "supported", "partial", "contradicted", "unsupported", "unverifiable"
]


def _digest(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


def identity_hash(source: dict[str, Any]) -> str:
    """Return a stable hash for one source's bibliographic identity.

    The display index is intentionally excluded.  Two records with the same
    index but different identity hashes remain ambiguous and cannot be merged.
    A source with no stable identifier still receives a deterministic hash of
    its explicit identity fields and URL/title metadata.
    """
    if not isinstance(source, dict):
        return _digest({"identity": {}})
    values = {
        "identifiers": identity_fields(source),
        "url": canonical_url(source.get("link") or source.get("url")) or
               str(source.get("link") or source.get("url") or ""),
        "title": " ".join(str(source.get("title") or source.get("name") or "").split()),
        "journal": " ".join(str(source.get("journal") or source.get("journal_title") or "").split()),
    }
    return _digest(values)


class GroundingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroundingResearchSpec(GroundingModel):
    """Validated, serializable scope information, including unresolved fields."""

    language: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    requested_count: int | None = None
    count_relation: str | None = None
    requested_fields: list[str] = Field(default_factory=list)
    output_mode: str | None = None
    protocol_requested: bool | None = None
    min_if_mentioned: float | None = None
    if_operator: str | None = None
    if_deferred: bool = True
    intent_status: str = "unknown"
    provenance: dict[str, str] = Field(default_factory=dict)
    unresolved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def count_relation_is_explicit_or_unresolved(self):
        if self.requested_count is not None and not self.count_relation:
            if "count_relation" not in self.unresolved:
                self.unresolved.append("count_relation")
        return self


class GroundingSource(GroundingModel):
    source_index: int = Field(ge=1)
    identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, str] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class GroundingLocator(GroundingModel):
    source_index: int = Field(ge=1)
    source_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    field: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("evidence locator end must exceed start")
        return self


class GroundingClaim(GroundingModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    report_start: int = Field(ge=0)
    report_end: int = Field(gt=0)
    citations: list[int] = Field(default_factory=list)
    verdict: VERDICTS = "unverifiable"
    reason_code: str = Field(min_length=1)
    reason: str = ""
    locators: list[GroundingLocator] = Field(default_factory=list)
    review_status: str = "unreviewed"
    failure_reasons: list[str] = Field(default_factory=list)

    @field_validator("citations")
    @classmethod
    def citation_ids_are_positive(cls, values):
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("citation IDs must be positive integers")
        if len(values) != len(set(values)):
            raise ValueError("citation IDs must be unique per claim")
        return values

    @model_validator(mode="after")
    def valid_report_range(self):
        if self.report_end <= self.report_start:
            raise ValueError("claim report_end must exceed report_start")
        return self


class DetectorFinding(GroundingModel):
    detector: str = Field(min_length=1)
    claim_id: str | None = None
    verdict: VERDICTS = "unverifiable"
    status: str = "recorded"
    reason_code: str = Field(min_length=1)
    reason: str = ""
    evidence_locator_ids: list[str] = Field(default_factory=list)


class ReviewReceipt(GroundingModel):
    status: str = "not_run"
    failure_reasons: list[str] = Field(default_factory=list)
    reviewed_claim_ids: list[str] = Field(default_factory=list)
    skipped_claim_ids: list[str] = Field(default_factory=list)


class WriterContextReceipt(GroundingModel):
    model_config = ConfigDict(extra="allow")

    batch: int | None = None
    input_mode: str = "draft_and_sources"
    draft_sha256: str | None = None
    context_sha256: str | None = None
    source_ids: list[int] = Field(default_factory=list)
    prior_draft_available: bool = True


class SourceSetReceipt(GroundingModel):
    status: str = "recorded"
    count: int = Field(ge=0)
    source_ids: list[int] = Field(default_factory=list)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GroundingSourceSets(GroundingModel):
    collected_candidates: SourceSetReceipt
    selected_writer_context: SourceSetReceipt
    cited_sources: SourceSetReceipt
    confirmed_source_records: SourceSetReceipt


class PendingFinding(GroundingModel):
    claim_id: str | None = None
    status: str = "unresolved"
    reason_code: str = Field(min_length=1)
    reason: str = ""


class ProposedChange(GroundingModel):
    claim_id: str | None = None
    status: str = "pending"
    proposal: str = ""
    reason_code: str = "detector_proposal"


class EvidenceGroundingV1(GroundingModel):
    schema_version: Literal["evidence_grounding.v1"] = "evidence_grounding.v1"
    research_spec: GroundingResearchSpec
    sources: list[GroundingSource] = Field(default_factory=list)
    claims: list[GroundingClaim] = Field(default_factory=list)
    detectors: list[DetectorFinding] = Field(default_factory=list)
    review: ReviewReceipt = Field(default_factory=ReviewReceipt)
    writer_context: list[WriterContextReceipt] = Field(default_factory=list)
    source_sets: GroundingSourceSets
    pending_findings: list[PendingFinding] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)


class SourceEnrichment(GroundingModel):
    """A source-indexed update that cannot silently overwrite conflicts."""

    source_index: int = Field(ge=1)
    identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    updated_fields: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: Literal["applied", "conflict", "ambiguous", "unresolved"] = "unresolved"
    conflict_information: dict[str, list[Any]] = Field(default_factory=dict)


def _spec_payload(spec: Any) -> dict[str, Any]:
    if spec is None:
        return {}
    if hasattr(spec, "as_dict"):
        value = spec.as_dict()
    elif hasattr(spec, "model_dump"):
        value = spec.model_dump(mode="json")
    elif is_dataclass(spec):
        value = asdict(spec)
    elif isinstance(spec, dict):
        value = deepcopy(spec)
    else:
        value = {}
    value["requested_fields"] = list(value.get("requested_fields") or [])
    value["unresolved"] = list(value.get("unresolved") or [])
    if value.get("requested_count") is not None and not value.get("count_relation"):
        value["count_relation"] = "unknown"
        if "count_relation" not in value["unresolved"]:
            value["unresolved"].append("count_relation")
    return GroundingResearchSpec.model_validate(value).model_dump(mode="json")


def _source_set(name: str, ids: set[int], sources_by_id: dict[int, dict[str, Any]], *, status: str = "recorded") -> SourceSetReceipt:
    ordered = sorted(ids)
    identities = [identity_hash(sources_by_id[index]) for index in ordered if index in sources_by_id]
    return SourceSetReceipt(status=status, count=len(ordered), source_ids=ordered,
                            sha256=_digest({"name": name, "ids": ordered, "identities": identities}))


def _locator_from_span(span: Any, source: dict[str, Any]) -> GroundingLocator | None:
    try:
        citation_value = _get(span, "citation")
        if not (type(citation_value) is int or
                isinstance(citation_value, str) and citation_value.isdigit()):
            return None
        citation = int(citation_value)
        quote = _get(span, "quote")
        start, end = _get(span, "start"), _get(span, "end")
        content_sha = _get(span, "content_sha256")
        field, basis = _get(span, "field"), _get(span, "basis")
    except (AttributeError, TypeError, ValueError):
        return None
    if (citation != int(source["index"]) or not isinstance(quote, str) or not quote
            or type(start) is not int or type(end) is not int
            or not isinstance(field, str) or not isinstance(basis, str) or not basis):
        return None
    source_text = source.get(field)
    if not isinstance(source_text, str) or not (0 <= start < end <= len(source_text)):
        return None
    if source_text[start:end] != quote or _digest(source_text) != content_sha:
        return None
    return GroundingLocator(source_index=citation, source_identity_hash=identity_hash(source),
                            field=field, basis=basis, content_sha256=content_sha,
                            start=start, end=end, quote=quote)


def _claim_check(checks: list[Any], claim: Claim):
    for check in checks:
        text = check.get("claim") if isinstance(check, dict) else getattr(check, "claim", None)
        start = check.get("start") if isinstance(check, dict) else getattr(check, "start", None)
        if text == claim.text and (start is None or start == claim.report_start):
            return check
    return None


def _get(value: Any, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def build_evidence_grounding(
    report: str,
    sources: list[dict[str, Any]] | None,
    *,
    research_spec: Any = None,
    checks: list[Any] | None = None,
    writer_context: list[dict[str, Any]] | None = None,
    pending_findings: list[dict[str, Any]] | None = None,
    proposed_changes: list[dict[str, Any]] | None = None,
    detector_findings: list[dict[str, Any]] | None = None,
    review: ReviewReceipt | dict[str, Any] | None = None,
) -> EvidenceGroundingV1:
    """Build the additive ledger for a report without changing ``report``."""
    from .evidence import SourceLookup
    # Reuse the review lookup's ambiguity policy. Never choose one of two
    # different records carrying the same citation label, even with equal IDs.
    lookup = SourceLookup(sources or [])
    source_rows = lookup.records()
    ambiguous_ids = lookup.ambiguous_indices
    by_id: dict[int, dict[str, Any]] = {}
    grounding_sources = []
    for source in source_rows:
        try:
            index = int(source.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 1 or index in by_id:
            continue
        by_id[index] = source
        normalized = classify_source(source)
        grounding_sources.append(GroundingSource(
            source_index=index, identity_hash=identity_hash(source),
            identity={key: value for key, value in identity_fields(source).items()},
            state={key: str(normalized.get(key) or "unknown") for key in (
                "source_kind", "document_type", "publication_state", "peer_review_status",
                "relevance_status", "evidence_scope", "temporal_validity", "contradiction_status",
                "identity_status")},
            provenance=normalized.get("identity_provenance") or {},
            snapshot={key: value for key, value in normalized.items()
                      if key not in {"identity_provenance"} and key in {
                          "index", "title", "link", "url", "doi", "pmid", "pmcid", "journal",
                          "publication_date", "pubdate", "language", "publication_types",
                          "impact_factor", "metric_year", "passes_threshold", "jcr_check_status",
                          "jcr_provenance", "_jcr_checks", "enrichment_conflicts", "enrichment_provenance"}},
        ))

    checks = list(checks or [])
    claims = []
    detectors = []
    pending = list(pending_findings or [])
    for index in sorted(ambiguous_ids):
        pending.append({"status": "unresolved", "reason_code": "ambiguous_source",
                        "reason": f"Citation ID {index} has differing source records"})
    cited_ids: set[int] = set()
    for number, claim in enumerate(extract_report_claims(report), 1):
        citation_ids = list(claim.citations)
        cited_ids.update(citation_ids)
        check = _claim_check(checks, claim)
        verdict = _get(check, "verdict", "unverifiable") if check else "unverifiable"
        reason_code = _get(check, "reason_code", "missing_review") if check else "missing_review"
        reason = _get(check, "reason", "") if check else ""
        review_status = "reviewed" if check else "unreviewed"
        failures = [] if check else ["missing_review"]
        locators = []
        if check:
            for source_check in _get(check, "source_checks", []) or []:
                citation = _get(source_check, "citation")
                source = by_id.get(int(citation)) if str(citation).isdigit() else None
                if source is None or int(citation) not in citation_ids:
                    continue
                for span in _get(source_check, "evidence", []) or []:
                    locator = _locator_from_span(span, source)
                    if locator is not None:
                        locators.append(locator)
        binding_failure = None
        if not citation_ids:
            binding_failure = ("missing_citation", "No explicit citation IDs")
        elif any(index in ambiguous_ids for index in citation_ids):
            binding_failure = ("ambiguous_source", "One or more citation IDs have differing source records")
        elif any(index not in by_id for index in citation_ids):
            binding_failure = ("missing_source", "One or more citation IDs have no source record")
        elif any(not any(isinstance(source.get(key), str) and source.get(key).strip()
                         for key in ("abstract", "body", "content", "full_content", "fetched_content"))
                 for index in citation_ids for source in [by_id[index]]):
            binding_failure = ("source_text_unavailable", "Cited source text is unavailable")
        elif check and verdict in {"supported", "partial"} and not locators:
            binding_failure = ("evidence_binding_unavailable", "No exact source-bound evidence locator")
        elif not check:
            pending.append({"claim_id": f"claim-{number}", "status": "unresolved",
                            "reason_code": "review_not_run", "reason": "No detector result"})
        if binding_failure:
            reason_code, reason = binding_failure
            failures.append(reason_code)
            pending.append({"claim_id": f"claim-{number}", "status": "unresolved",
                            "reason_code": reason_code, "reason": reason})
            # Keep the raw detector finding below, separately from whether
            # this ledger can substantiate its positive verdict.
            if verdict in {"supported", "partial"} or not citation_ids:
                verdict = "unverifiable"
        row = GroundingClaim(claim_id=f"claim-{number}", text=claim.text,
                             report_start=int(claim.report_start or 0), report_end=int(claim.report_end or 0),
                             citations=citation_ids, verdict=verdict,
                             reason_code=str(reason_code or "unverifiable"), reason=str(reason or ""),
                             locators=locators, review_status=review_status,
                             failure_reasons=failures)
        claims.append(row)
        if check:
            detectors.append(DetectorFinding(detector="citation_qc", claim_id=row.claim_id,
                                              verdict=_get(check, "verdict", "unverifiable"),
                                              status="evidence_binding_unresolved" if binding_failure else "recorded",
                                              reason_code=str(_get(check, "reason_code") or "unverifiable"),
                                              reason=str(_get(check, "reason") or ""),
                                              evidence_locator_ids=[_digest(locator.model_dump()) for locator in locators]))
    detectors.extend(DetectorFinding.model_validate(item) for item in (detector_findings or []))

    selected_ids = {int(index) for row in writer_context or [] for index in (row.get("source_ids") or [])
                    if str(index).isdigit()}
    confirmed_ids = {index for index, source in by_id.items()
                     if (classify_source(source).get("identity_status") == "confirmed"
                         or classify_source(source).get("publication_status") == "formal")}
    if isinstance(review, ReviewReceipt):
        receipt = review
    else:
        review_payload = dict(review or {})
        review_payload.setdefault("status", "completed" if checks else "not_run")
        if not review_payload.get("reviewed_claim_ids"):
            review_payload["reviewed_claim_ids"] = [row.claim_id for row in claims if row.review_status == "reviewed"]
        if not review_payload.get("skipped_claim_ids"):
            review_payload["skipped_claim_ids"] = [row.claim_id for row in claims if row.review_status != "reviewed"]
        review_payload.setdefault("failure_reasons", [] if checks else ["detector_not_run"])
        receipt = ReviewReceipt.model_validate(review_payload)
    writer_rows = [WriterContextReceipt.model_validate(row) for row in (writer_context or [])]
    return EvidenceGroundingV1(
        research_spec=GroundingResearchSpec.model_validate(_spec_payload(research_spec)),
        sources=grounding_sources, claims=claims, detectors=detectors,
        review=receipt, writer_context=writer_rows,
        source_sets=GroundingSourceSets(
            collected_candidates=_source_set("collected_candidates", set(by_id) | set(ambiguous_ids), by_id),
            selected_writer_context=_source_set(
                "selected_writer_context", selected_ids, by_id,
                status="recorded" if writer_context is not None else "unavailable"),
            cited_sources=_source_set("cited_sources", cited_ids, by_id),
            confirmed_source_records=_source_set("confirmed_source_records", confirmed_ids, by_id),
        ),
        pending_findings=[PendingFinding.model_validate(item) for item in pending],
        proposed_changes=[ProposedChange.model_validate(item) for item in (proposed_changes or [])],
    )


def validate_evidence_locator(locator: GroundingLocator | dict[str, Any], source_text: str) -> GroundingLocator:
    """Validate an exact locator against the supplied source bytes."""
    item = locator if isinstance(locator, GroundingLocator) else GroundingLocator.model_validate(locator)
    if not isinstance(source_text, str) or source_text[item.start:item.end] != item.quote:
        raise ValueError("evidence_locator_quote_mismatch")
    if _digest(source_text) != item.content_sha256:
        raise ValueError("evidence_locator_content_mismatch")
    return item


def pending_native_findings(claims: list[Any], reviewed_claim_ids: set[str] | list[str], reason_code: str) -> list[PendingFinding]:
    """Create explicit unresolved rows for native-review skips or failures."""
    reviewed = {str(value) for value in reviewed_claim_ids}
    rows = []
    for number, claim in enumerate(claims or [], 1):
        claim_id = str(_get(claim, "claim_id", f"claim-{number}"))
        if claim_id not in reviewed:
            rows.append(PendingFinding(claim_id=claim_id, status="unresolved",
                                       reason_code=reason_code,
                                       reason="Native detector did not produce a finding"))
    return rows


class SourceRegistry:
    """Shared source registry for generic enrichment propagation."""

    def __init__(self, sources: list[dict[str, Any]] | None = None):
        self.sources: dict[int, dict[str, Any]] = {}
        self.ambiguous: set[int] = set()
        for source in sources or []:
            if not isinstance(source, dict):
                continue
            if isinstance(source.get("index"), bool) or not str(source.get("index", "")).isdigit():
                continue
            try:
                index = int(source.get("index"))
            except (TypeError, ValueError):
                continue
            if index < 1:
                continue
            if index in self.sources and self.sources[index] != source:
                self.ambiguous.add(index)
            else:
                self.sources[index] = source

    def enrich(self, enrichment: SourceEnrichment | dict[str, Any]) -> SourceEnrichment:
        item = enrichment if isinstance(enrichment, SourceEnrichment) else SourceEnrichment.model_validate(enrichment)
        source = self.sources.get(item.source_index)
        if source is None or item.source_index in self.ambiguous:
            return item.model_copy(update={"status": "ambiguous", "conflict_information": {"source_index": [item.source_index]}})
        if identity_hash(source) != item.identity_hash:
            return item.model_copy(update={"status": "conflict", "conflict_information": {
                "identity_hash": [identity_hash(source), item.identity_hash]}})
        conflicts: dict[str, list[Any]] = {}
        for key, value in item.updated_fields.items():
            if key in source and source[key] not in (None, "", [], {}) and source[key] != value:
                conflicts[key] = [deepcopy(source[key]), deepcopy(value)]
                continue
            source[key] = deepcopy(value)
        if conflicts:
            source.setdefault("enrichment_conflicts", {}).update(conflicts)
        if item.provenance:
            source.setdefault("enrichment_provenance", []).append(deepcopy(item.provenance))
        return item.model_copy(update={"status": "conflict" if conflicts else "applied",
                                       "conflict_information": conflicts})

    def propagate(self, review_documents: list[Any] | None = None) -> None:
        """Copy current source metadata into already-created review documents."""
        for document in review_documents or []:
            metadata = (document.get("metadata") if isinstance(document, dict)
                        else getattr(document, "metadata", None))
            if not isinstance(metadata, dict):
                continue
            try:
                index = int(metadata.get("index"))
                source = None if index in self.ambiguous else self.sources.get(index)
            except (TypeError, ValueError):
                source = None
            if source:
                metadata.update(deepcopy(source))


def apply_source_enrichments(sources: list[dict[str, Any]], enrichments: list[dict[str, Any]], review_documents: list[Any] | None = None) -> list[SourceEnrichment]:
    registry = SourceRegistry(sources)
    outcomes = [registry.enrich(item) for item in enrichments or []]
    registry.propagate(review_documents)
    return outcomes


# Short aliases make the additive contract convenient for callers that do not
# need to spell out its versioned wire name.
EvidenceGrounding = EvidenceGroundingV1
SourceIdentityEnrichment = SourceEnrichment


__all__ = [
    "EvidenceGrounding", "EvidenceGroundingV1", "GroundingClaim", "GroundingLocator", "GroundingSource",
    "GroundingResearchSpec", "SourceEnrichment", "SourceIdentityEnrichment", "SourceRegistry", "apply_source_enrichments",
    "build_evidence_grounding", "identity_hash", "pending_native_findings",
    "validate_evidence_locator",
]
