"""Regression fixtures for the 2026-11-12 adjudicated disagreements.

These tests preserve two distinct dimensions: the user's final paper-fact
verdict and what the writer-facing source view actually contained. They do not
turn the adjudications into a production gate or claim an overall rate.
"""

import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures/adjudicated_claims_20261112.json"


def load_cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_adjudicated_fixture_preserves_all_21_claims_and_verdicts():
    cases = load_cases()
    assert len(cases["cases"]) == 21
    assert sum(c["scientific_verdict"] == "supported" for c in cases["cases"]) == 17
    assert sum(c["scientific_verdict"] == "partially supported" for c in cases["cases"]) == 3
    assert sum(c["scientific_verdict"] == "contradicted" for c in cases["cases"]) == 1
    keys = {(c["blind_id"], c["claim_id"]) for c in cases["cases"]}
    assert len(keys) == 21


def test_scientific_truth_and_writer_scope_are_kept_separate():
    cases = {(c["blind_id"], c["claim_id"]): c for c in load_cases()["cases"]}
    # Paper facts were adjudicated as supported, but the sampled writer view
    # did not expose the Methods/quantitative detail needed to assert them.
    for key in [
        ("immune_fixed_source_roles-arm-1", 78),
        ("immune_fixed_source_roles-arm-1", 9),
        ("immune_fixed_source_roles-arm-2", 11),
        ("if_fixed_source_roles-arm-2", 85),
    ]:
        assert cases[key]["scientific_verdict"] == "supported"
        assert "unseen" in cases[key]["writer_evidence_scope"] or "abstract" in cases[key]["writer_evidence_scope"]

    # A missing source record remains a provenance limitation even when the
    # referenced paper supports the claim externally.
    assert cases[("immune_fixed_source_roles-arm-2", 8)]["scientific_verdict"] == "supported"
    assert cases[("immune_fixed_source_roles-arm-2", 8)]["writer_evidence_scope"] == "missing_source_record"


def test_contradiction_fixture_is_not_collapsed_into_missing_evidence():
    cases = {(c["blind_id"], c["claim_id"]): c for c in load_cases()["cases"]}
    case = cases[("if_fixed_source_roles-arm-1", 68)]
    assert case["scientific_verdict"] == "contradicted"
    assert case["writer_evidence_scope"] == "abstract_only_title_scope_conflict"
