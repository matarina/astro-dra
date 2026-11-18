from hashlib import sha256
import json

import pytest

from research_verify.evidence_grounding import (
    GroundingLocator,
    SourceEnrichment,
    SourceRegistry,
    build_evidence_grounding,
    apply_source_enrichments,
    identity_hash,
    validate_evidence_locator,
)
from research_verify.heldout import (
    CaseReview,
    ClaimReview,
    HeldoutCase,
    HeldoutManifest,
    HeldoutModelSettings,
    ManualReviewPacket,
    seal_manual_packet,
    validate_manifest,
    evaluate_acceptance,
)
from research_verify.research_spec import parse_research_spec


def source(index=1, abstract="A measured result"):
    return {"index": index, "title": "Study", "doi": "10.1234/example",
            "link": "https://doi.org/10.1234/example", "abstract": abstract,
            "content_type": "abstract"}


def test_count_without_relation_is_unresolved():
    spec = parse_research_spec("", {"requested_count": 10})
    assert spec.requested_count == 10
    assert spec.count_relation == "unknown"
    assert "count_relation" in spec.unresolved


def test_grounding_contains_uncited_claim_and_exact_locator():
    text = source()["abstract"]
    report = "A measured result [1].\n\nAn uncited claim."
    grounding = build_evidence_grounding(report, [source()], research_spec=parse_research_spec(""))
    assert grounding.schema_version == "evidence_grounding.v1"
    assert len(grounding.claims) == 2
    assert grounding.claims[0].verdict == "unverifiable"
    assert grounding.claims[0].reason_code == "missing_review"
    assert grounding.claims[1].reason_code == "missing_citation"
    locator = GroundingLocator(source_index=1, source_identity_hash=identity_hash(source()),
                               field="abstract", basis="abstract",
                               content_sha256=sha256(text.encode()).hexdigest(),
                               start=0, end=len(text), quote=text)
    assert validate_evidence_locator(locator, text).quote == text


def test_source_enrichment_propagates_and_preserves_conflict():
    record = source()
    registry = SourceRegistry([record])
    identity = identity_hash(record)
    applied = registry.enrich(SourceEnrichment(source_index=1, identity_hash=identity,
                                               updated_fields={"language": "en"},
                                               provenance={"provider": "pubmed"}))
    assert applied.status == "applied" and record["language"] == "en"
    conflict = registry.enrich(SourceEnrichment(source_index=1, identity_hash=identity,
                                                updated_fields={"language": "zh"}))
    assert conflict.status == "conflict"
    assert record["language"] == "en"
    assert record["enrichment_conflicts"]["language"] == ["en", "zh"]
    document = {"metadata": {"index": 1}}
    outcome = apply_source_enrichments(
        [record], [{"source_index": 1, "identity_hash": identity,
                    "updated_fields": {"journal": "Fixture Journal"}}], [document])
    assert outcome[0].status == "applied"
    assert document["metadata"]["journal"] == "Fixture Journal"


def test_heldout_manifest_validates_frozen_hashes(tmp_path):
    prompt = tmp_path / "prompt.txt"
    packet = tmp_path / "sources.json"
    prompt.write_text("Question", encoding="utf-8")
    packet.write_text("[]", encoding="utf-8")
    digest = lambda path: sha256(path.read_bytes()).hexdigest()
    case = HeldoutCase(
        case_id="case-1", prompt_file=prompt.name, prompt_sha256=digest(prompt),
        source_packet_file=packet.name, source_packet_sha256=digest(packet),
        model=HeldoutModelSettings(model="fixture", endpoint="https://example.test"),
        baseline_output="baseline.md", candidate_output="candidate.md",
        fixed_reference=True,
    )
    manifest = HeldoutManifest(status="sealed",
                               manual_packet=seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z"),
                               cases=[case])
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    assert validate_manifest(path, require_sealed=True).cases[0].excluded_from_tuning
    prompt.write_text("Changed", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt hash mismatch"):
        validate_manifest(path)


def test_acceptance_keeps_paired_regressions_visible():
    common = dict(source_support="supported", scope_adherence="adherent",
                  identity_metadata_correctness="correct", abstention_correctness="correct",
                  useful_content_retention="retained")
    baseline = [ClaimReview(claim_id="c1", citation_alignment="misaligned", **common)]
    candidate = [ClaimReview(claim_id="c1", citation_alignment="aligned", **common)]
    result = evaluate_acceptance(
        baseline, candidate,
        manual_packet=seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z"),
    )
    assert result.accepted
    assert result.paired_effects["citation_mismatch_rate"]["rate_delta"] < 0


def test_acceptance_fails_closed_on_empty_or_duplicate_reviews():
    sealed = seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z")
    empty = evaluate_acceptance([], [], manual_packet=sealed)
    assert not empty.accepted
    assert "review_row_integrity" in empty.reasons
    row = ClaimReview(claim_id="c1", source_support="supported", citation_alignment="aligned",
                      scope_adherence="adherent", identity_metadata_correctness="correct",
                      abstention_correctness="correct", useful_content_retention="retained")
    duplicate = evaluate_acceptance([row, row], [row], manual_packet=sealed)
    assert not duplicate.accepted
    assert "review_row_integrity" in duplicate.reasons


def test_zero_assertion_case_requires_explicit_case_reason():
    with pytest.raises(ValueError):
        CaseReview(case_id="C0", assertion_count=0)
    sealed = seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z")
    result = evaluate_acceptance(
        [], [], manual_packet=sealed, expected_case_ids=["C0"],
        expected_claim_ids=[],
        baseline_cases=[CaseReview(case_id="C0", assertion_count=0, no_assertions_reason="No substantive assertions")],
        candidate_cases=[CaseReview(case_id="C0", assertion_count=0, no_assertions_reason="No substantive assertions")],
    )
    assert result.accepted
    assert result.criteria["manual_labels_complete"]


def test_zero_assertion_receipt_does_not_hide_unreviewed_case():
    sealed = seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z")
    result = evaluate_acceptance(
        [], [], manual_packet=sealed, expected_claim_ids=[], expected_case_ids=["C0", "C1"],
        baseline_cases=[CaseReview(case_id="C0", assertion_count=0, no_assertions_reason="No assertions")],
        candidate_cases=[CaseReview(case_id="C0", assertion_count=0, no_assertions_reason="No assertions")],
    )
    assert not result.accepted
    assert not result.criteria["review_row_integrity"]


def test_case_aware_reviews_allow_multiple_assertions_per_case_and_reject_unbound_rows():
    sealed = seal_manual_packet(ManualReviewPacket(), "2026-11-18T00:00:00Z")
    common = dict(source_support="supported", citation_alignment="aligned",
                  scope_adherence="adherent", identity_metadata_correctness="correct",
                  abstention_correctness="correct", useful_content_retention="retained",
                  case_id="CASE-1")
    rows = [ClaimReview(claim_id="c1", **common), ClaimReview(claim_id="c2", **common)]
    result = evaluate_acceptance(
        rows, rows, manual_packet=sealed, expected_claim_ids=["c1", "c2"],
        expected_case_ids=["CASE-1"],
        baseline_cases=[CaseReview(case_id="CASE-1", assertion_count=2)],
        candidate_cases=[CaseReview(case_id="CASE-1", assertion_count=2)],
    )
    assert result.criteria["review_row_integrity"]
    unbound = [ClaimReview(claim_id="c1", **{**common, "case_id": None})]
    bad = evaluate_acceptance(
        unbound, unbound, manual_packet=sealed, expected_claim_ids=["c1"],
        expected_case_ids=["CASE-1"],
        baseline_cases=[CaseReview(case_id="CASE-1", assertion_count=0, no_assertions_reason="No claims bound")],
        candidate_cases=[CaseReview(case_id="CASE-1", assertion_count=0, no_assertions_reason="No claims bound")],
    )
    assert not bad.criteria["review_row_integrity"]
