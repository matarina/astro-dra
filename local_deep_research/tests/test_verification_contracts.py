"""Foundation gate behavior; does not claim the legacy pipeline is strict."""
import pytest
from pydantic import ValidationError
from research_verify.contracts import (
    CheckResult, ClaimEvidence, EvidenceLocator, GateDecision, TaskPolicy, evaluate_gate,
)


def result(check_id, status):
    return CheckResult(check_id=check_id, status=status, reason_code="fixture", verifier_version="1")


@pytest.mark.parametrize("statuses,expected", [
    (("pass", "pass"), "admitted"),
    (("pass", "fail"), "rejected"),
    (("pass", "unknown"), "pending"),
    (("pass", "not_applicable"), "pending"),
    (("fail", "unknown"), "rejected"),
])
def test_gate_required_outcomes(statuses, expected):
    checks = tuple(result(key, status) for key, status in zip(("identity", "claim"), statuses))
    assert evaluate_gate(("identity", "claim"), checks) == expected


def test_absent_disabled_or_empty_checks_cannot_pass():
    assert evaluate_gate(("claim",), ()) == GateDecision.PENDING
    assert evaluate_gate((), ()) == GateDecision.PENDING
    assert evaluate_gate(("identity", "claim"), (result("claim", "pass"),)) == GateDecision.PENDING


def test_duplicate_outcomes_cannot_pass():
    checks = (result("claim", "pass"), result("claim", "pass"))
    assert evaluate_gate(("claim",), checks) == GateDecision.PENDING
    assert evaluate_gate(("claim", "claim"), checks) == GateDecision.PENDING


def test_traceability_pass_does_not_imply_full_literature_pass():
    checks = (result("claim", "pass"),)
    assert evaluate_gate(("claim",), checks) == GateDecision.ADMITTED
    assert evaluate_gate(("identity", "jif", "fulltext_keywords", "claim"), checks) == GateDecision.PENDING
    assert evaluate_gate(("claim",), checks + (result("jif", "fail"),)) == GateDecision.ADMITTED


def test_confirmed_defaults_are_serializable_and_year_is_exact():
    policy = TaskPolicy(task_id="test", year_from=2026, year_to=2026,
                        keywords=("A", "B", "C", "D"), keyword_min_hits=3)
    assert policy.jif_selection == "latest_published"
    assert policy.jif_snapshot is None  # no invented current-year metric
    assert policy.keyword_scope == "body_excluding_references"
    assert TaskPolicy.model_validate_json(policy.model_dump_json()) == policy


@pytest.mark.parametrize("extra", [
    {"year_from":2027, "year_to":2026},
    {"keywords":("A", "a"), "keyword_min_hits":1},
    {"keywords":("A", "B"), "keyword_min_hits":3},
    {"keywords":("A",)},
    {"keyword_min_hits":1},
    {"min_jif":float("nan")},
    {"required_checks":("claim", "claim")},
    {"required_checks":("",)},
])
def test_invalid_policy_is_rejected(extra):
    with pytest.raises(ValidationError):
        TaskPolicy(task_id="test", **extra)


def locator(**extra):
    fields = dict(paper_id="synthetic:1", artifact_id="fixture:1", content_sha256="0"*64,
                  basis="abstract", start=0, end=10, quote="Study text")
    fields.update(extra)
    return EvidenceLocator(**fields)


@pytest.mark.parametrize("extra", [
    {"end":0}, {"start":10, "end":10}, {"content_sha256":"bad"}, {"quote":""},
])
def test_invalid_evidence_coordinates_are_rejected(extra):
    with pytest.raises(ValidationError):
        locator(**extra)


def test_supported_requires_verified_quote_and_matching_paper():
    base = dict(claim_id="c1", claim="Study text", paper_id="synthetic:1",
                verdict="supported", reason_code="matched")
    with pytest.raises(ValidationError):
        ClaimEvidence(**base)
    with pytest.raises(ValidationError):
        ClaimEvidence(**base, locator=locator(), quote_verified=False)
    with pytest.raises(ValidationError):
        ClaimEvidence(**base, locator=locator(paper_id="synthetic:2"), quote_verified=True)
    evidence = ClaimEvidence(**base, locator=locator(), quote_verified=True)
    assert evidence.locator.basis == "abstract"  # support is scoped, not fulltext proof
