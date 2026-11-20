"""Regression tests for the opt-in document-consistency review context."""
import json

from research_verify.evidence_flow import (
    document_structure_spans,
    parse_review,
    review_claim_groups,
    review_prompt,
)


class _Doc:
    page_content = "A source passage."
    metadata = {"index": 1, "title": "Study", "source": "https://example.org/1"}


def test_structure_spans_keep_uncited_heading_and_table_labels():
    answer = "## Breast cohort\n\n| Study | Platform [1] |\n| --- | --- |\n| Breast | ST |\n"
    spans = document_structure_spans(answer)
    assert any(span["kind"] == "heading_candidate" and "Breast cohort" in span["text"] for span in spans)
    assert any(span["kind"] == "table_candidate" for span in spans)


def test_review_prompt_exposes_structure_as_diagnostic_only():
    answer = "## Breast cohort\n\nResult [1].\n"
    groups = review_claim_groups(answer, [_Doc()], [{"index": 1}], "Question", 60000)
    claims = groups[0]
    prompt = review_prompt(
        "Question", answer, "source", claims=claims,
        structure_spans=document_structure_spans(answer),
    )
    assert "STRUCTURAL REPORT SPANS" in prompt
    assert "internal_inconsistency" in prompt
    assert "do not propose" in prompt


def test_internal_inconsistency_is_retained_unresolved():
    raw = json.dumps({"issues": [{"claim_id": 0, "status": "internal_inconsistency",
        "atom_checks": [{"attribute": "population", "result": "contradiction",
                          "evidence_quote": "The study used breast tissue."}]}]})
    issues = parse_review(raw, {0: {"text": "Result [1].", "source_ids": [1]}})
    assert issues and issues[0]["status"] == "internal_inconsistency"
