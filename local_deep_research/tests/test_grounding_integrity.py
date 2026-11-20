"""A detector's positive label must not hide broken evidence bindings."""
from hashlib import sha256

import pytest

from research_verify.evidence_grounding import build_evidence_grounding


def record(index=1):
    return {"index": index, "title": "Study", "abstract": "A measured result"}


def check(span=None):
    return {"claim": "A measured result [1].", "verdict": "supported",
            "reason_code": "model_supported", "reason": "Reported result",
            "source_checks": [{"citation": 1, "evidence": [span] if span else []}]}


def locator(**changes):
    text = record()["abstract"]
    return {"citation": 1, "quote": text, "start": 0, "end": len(text),
            "content_sha256": sha256(text.encode()).hexdigest(),
            "field": "abstract", "basis": "abstract", **changes}


@pytest.mark.parametrize("sources,span,reason", [
    ([], locator(), "missing_source"),
    ([{"index": 1, "title": "Metadata only"}], locator(), "source_text_unavailable"),
    ([record()], None, "evidence_binding_unavailable"),
    ([record()], locator(citation=2), "evidence_binding_unavailable"),
    ([record()], locator(citation=True), "evidence_binding_unavailable"),
    ([record()], locator(field="body"), "evidence_binding_unavailable"),
    ([record()], locator(content_sha256="0" * 64), "evidence_binding_unavailable"),
    ([record()], locator(start=True), "evidence_binding_unavailable"),
    ([record(), {**record(), "abstract": "A conflicting result"}], locator(), "ambiguous_source"),
])
def test_positive_detector_is_preserved_but_unbound_claim_stays_unresolved(sources, span, reason):
    report = "A measured result [1]."
    result = build_evidence_grounding(report, sources, checks=[check(span)])
    assert result.claims[0].verdict == "unverifiable"
    assert result.claims[0].reason_code == reason
    assert reason in result.claims[0].failure_reasons
    assert result.detectors[0].verdict == "supported"
    assert result.detectors[0].status == "evidence_binding_unresolved"
    assert result.pending_findings


def test_serialized_and_model_evidence_have_identical_exact_binding():
    from types import SimpleNamespace
    for span in (locator(), SimpleNamespace(**locator())):
        result = build_evidence_grounding("A measured result [1].", [record()], checks=[check(span)])
        assert result.claims[0].verdict == "supported"
        assert result.claims[0].locators[0].field == "abstract"
        assert result.claims[0].failure_reasons == []
        assert result.pending_findings == []


def test_duplicate_citation_is_counted_as_candidate_but_not_resolved():
    result = build_evidence_grounding("A measured result [1].", [record(), {**record(), "title": "Other"}])
    assert result.source_sets.collected_candidates.source_ids == [1]
    assert result.sources == []
    assert result.claims[0].reason_code == "ambiguous_source"


def test_identical_duplicate_and_boolean_index_do_not_create_ambiguity():
    result = build_evidence_grounding("A measured result [1].", [record(), record(), record(True)],
                                     checks=[check(locator())])
    assert result.claims[0].verdict == "supported"
    assert len(result.sources) == 1


def test_ambiguous_registry_never_overwrites_existing_review_material():
    from research_verify.evidence_grounding import SourceRegistry
    registry = SourceRegistry([record(), {**record(), "abstract": "Other acquired text"}])
    document = {"metadata": {"index": 1, "abstract": "Preserve original review text"}}
    registry.propagate([document])
    assert document["metadata"]["abstract"] == "Preserve original review text"
