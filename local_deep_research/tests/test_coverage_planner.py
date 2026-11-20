from research_verify.coverage_planner import CoverageCandidate, plan_coverage
from research_verify.evidence_cards import build_complete_source_card, build_passage_card


def test_planner_covers_distinct_fields_before_repeating_one_field():
    plan = plan_coverage(
        [
            CoverageCandidate(1, 0, 20, "population", ("population",), 1.0),
            CoverageCandidate(1, 20, 40, "population duplicate", ("population",), 0.99),
            CoverageCandidate(2, 0, 20, "method", ("method",), 0.4),
        ],
        ["population", "method"], context_chars=40,
    )
    assert plan.complete
    assert plan.covered_fields == ("population", "method")
    assert {item.source_id for item in plan.selected} == {1, 2}


def test_planner_preserves_uncovered_field_and_exact_context_hash():
    plan = plan_coverage(
        [CoverageCandidate("s1", 5, 10, "one", ("a",), 1.0)],
        ["a", "b"], context_chars=20,
    )
    assert not plan.complete
    assert plan.uncovered_fields == ("b",)
    assert plan.context_chars == 3
    assert len(plan.context_sha256) == 64


def test_planner_deduplicates_offsets_and_respects_item_limit():
    plan = plan_coverage(
        [
            CoverageCandidate(1, 0, 4, "same", ("a",), 0.2),
            CoverageCandidate(1, 0, 4, "same", ("a",), 0.9),
            CoverageCandidate(2, 0, 4, "other", ("b",), 0.8),
        ],
        ["a", "b"], context_chars=20, max_items=2,
    )
    assert len(plan.selected) == 2
    assert plan.selected[0].text == "same"


def test_planner_preserves_selection_provenance_fields():
    plan = plan_coverage(
        [CoverageCandidate(1, 0, 4, "span", ("method",), 0.8,
                           method="semantic_ranker", lexical_match=False,
                           ranker_score=0.8)],
        ["method"], context_chars=10,
    )
    selected = plan.selected[0]
    assert selected.method == "semantic_ranker"
    assert selected.lexical_match is False
    assert selected.ranker_score == 0.8


def test_passage_card_binds_exact_source_offsets_and_hashes():
    source = "prefix decisive method suffix"
    card = build_passage_card(7, source, 7, 23, source[7:23], field="method")
    assert card["status"] == "candidate_passage"
    assert card["offsets"] == {"start": 7, "end": 23}
    assert card["source_text_sha256"]
    assert card["text_sha256"]


def test_passage_card_rejects_mismatched_text():
    try:
        build_passage_card(7, "abcdef", 1, 4, "wrong")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched passage must be rejected")


def test_complete_source_card_keeps_scope_unknown_and_identity_visible():
    card = build_complete_source_card(
        4, "acquired source text", basis="retrieved page excerpt",
        source_identity={"doi": "10.1000/example", "pmid": "123"},
    )
    assert card["status"] == "complete_acquired_text"
    assert card["completeness"] == "unconfirmed"
    assert card["source_identity"]["doi"] == "10.1000/example"
