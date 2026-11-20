"""Independent boundary regressions; located text is not an entailment verdict."""
import json

from research_verify.independent_verification import (
    SourcePassage, VerificationQuestion, parse_verification_response,
)


def answer(source_id, quote, passages):
    raw = json.dumps({"answers": [{"question_id": "q", "status": "supported",
                                  "answer": "An answer needing evidence.",
                                  "evidence": [{"source_id": source_id, "quote": quote}]}]})
    return parse_verification_response(raw, [VerificationQuestion("q", "What was measured?")], passages)[0]


def test_whitespace_only_quote_is_not_located_evidence():
    parsed = answer(1, " ", [SourcePassage(1, text="This source has spaces.")])
    assert parsed.evidence_status != "located"
    assert parsed.effective_status == "unknown"


def test_boolean_source_id_cannot_alias_article_one():
    parsed = answer(True, "A measured association.", [SourcePassage(1, text="A measured association.")])
    assert parsed.evidence_status != "located"
    assert parsed.effective_status == "unknown"


def test_multiple_passages_from_one_article_preserve_earlier_evidence():
    parsed = answer(1, "Measured association.", [
        SourcePassage(1, text="Measured association.", field="results"),
        SourcePassage(1, text="Causality is unresolved.", field="discussion"),
    ])
    assert parsed.evidence_status == "located"


def test_quote_from_another_article_is_not_evidence_for_named_article():
    parsed = answer(1, "Measured association.", [
        SourcePassage(1, text="Causality is unresolved."),
        SourcePassage(2, text="Measured association."),
    ])
    assert parsed.evidence_status != "located"


def test_valid_contiguous_quote_stays_available_with_multiple_articles():
    parsed = answer(2, "Measured association.", [
        SourcePassage(1, text="A different source."),
        SourcePassage(2, text="Measured association. Causality is unresolved."),
    ])
    assert parsed.evidence_status == "located"
