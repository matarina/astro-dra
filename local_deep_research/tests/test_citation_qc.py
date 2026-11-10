"""Evidence and publishing regression tests; judges are controlled test doubles."""
from __future__ import annotations

import json

import pytest

from research_verify.citation_qc import (
    Claim,
    CitationQc,
    content_hash,
    NO_VERIFIED_CLAIMS,
)
from research_verify.config import VerifyConfig
from research_verify.evidence import (
    Artifact,
    SourceLookup,
    locate_quote,
    retrieve,
    source_artifacts,
)
from research_verify.models import ClaimCheck


class FakeCollector:
    def __init__(self, mapping):
        self._m = mapping

    def find_by_index(self, idx):
        return self._m.get(idx)


class FakeJudge:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        data = self.payload(prompt) if callable(self.payload) else self.payload
        return type(
            "Response",
            (),
            {"content": json.dumps(data) if isinstance(data, dict) else data},
        )()


def verdict(value="supported", quote="The method improves accuracy.", **extra):
    return {
        "verdict": value,
        "evidence_quotes": [quote] if quote is not None else [],
        "reason": "test judgment",
        **extra,
    }


def qc(judge=None, **settings):
    return CitationQc(
        judge_model=judge,
        cfg=VerifyConfig(qc_review_rounds=0, qc_repair_rounds=0, **settings),
    )


def collector(**source):
    return FakeCollector(
        {1: {"doi": "10.test/paper", "body": "The method improves accuracy.", **source}}
    )


def test_extract_includes_uncited_and_skips_bibliography():
    report = "# Findings\nA result [1].\nAn uncited result.\n## Sources\n1. Reference\n"
    claims = qc().extract_claims(report)
    assert [c.text for c in claims] == ["A result [1].", "An uncited result."]
    assert claims[1].citations == []
    assert all(report[c.start : c.end] == c.text for c in claims)


def test_chinese_punctuation_trailing_citations_and_decimal():
    text = "结果提高5.5%。[1]另一结果没有变化[2]。 The score is 0.5 [1, 2]."
    claims = qc().extract_claims(text)
    assert len(claims) == 3
    assert claims[0].citations == [1]
    assert claims[1].citations == [2]
    assert claims[2].citations == [1, 2]
    assert "0.5" in claims[2].text


def test_numbered_lists_and_table_rows_preserve_positions():
    text = "1. A result [1].\n\n| Method | Result |\n|---|---|\n| A | 5% [1] |\n"
    claims = qc().extract_claims(text)
    assert [c.text for c in claims] == ["A result [1].", "| A | 5% [1] |"]
    assert all(text[c.start : c.end] == c.text for c in claims)


def test_detailed_sections_after_embedded_audit_are_checked():
    text = "## First\nA [1].\n### 结论可溯源性核查\n| old audit |\n## Second\nNew fact [2]."
    assert [c.text for c in qc().extract_claims(text)] == ["A [1].", "New fact [2]."]


def test_skipped_appendix_cannot_preserve_unchecked_facts_in_published_body():
    report = "The method improves accuracy [1].\n## Sources\nHidden invented conclusion.\n## Next section\nThe method improves accuracy [1]."
    result = qc(FakeJudge(verdict())).verify_report(report, collector())
    assert "Hidden invented" not in result.content
    assert len(result.checks) == 2
    assert result.input_content_sha256 == content_hash(report)


def test_no_judge_and_missing_source_never_pass():
    check = qc().check([Claim("Result [1]", [1])], collector())[0]
    assert check.verdict == "unverifiable"
    assert check.reason_code == "no_judge"
    check = qc(FakeJudge(verdict())).check([Claim("Result [99]", [99])], collector())[0]
    assert check.reason_code == "missing_source"


def test_uncited_claim_is_not_auto_attributed():
    judge = FakeJudge(verdict())
    check = qc(judge).check([Claim("An invented conclusion")], collector())[0]
    assert check.reason_code == "missing_citation"
    assert not judge.prompts


def test_supported_requires_located_body_quote():
    check = qc(FakeJudge(verdict())).check(
        [Claim("The method improves accuracy [1].", [1])], collector()
    )[0]
    assert check.verdict == "supported"
    evidence = check.source_checks[0].evidence[0]
    assert evidence.field == "body" and evidence.basis == "body"
    assert evidence.quote == "The method improves accuracy."
    assert evidence.start == 0 and evidence.end == len(evidence.quote)
    assert evidence.content_sha256 == content_hash(evidence.quote)


@pytest.mark.parametrize("quote", ["Invented result.", None])
def test_fabricated_or_missing_quote_never_supported(quote):
    check = qc(FakeJudge(verdict(quote=quote))).check(
        [Claim("Result [1]", [1])], collector()
    )[0]
    assert check.verdict == "unverifiable"
    assert check.reason_code == "invalid_quote"


def test_quote_outside_shown_chunks_is_not_accepted():
    artifact = Artifact(
        "body", "body", "First passage. " + "x" * 500 + " Hidden quote."
    )
    chunks = retrieve(
        artifact, "First passage", chunk_chars=200, top_k=1, context_chars=1000
    )
    assert locate_quote("Hidden quote.", artifact, chunks, 1, "p") is None


def test_whitespace_only_normalization_preserves_original_offsets():
    artifact = Artifact(
        "body", "body", "Prefix. The method\n  improves accuracy. Suffix."
    )
    chunks = retrieve(artifact, "method", chunk_chars=200, top_k=1, context_chars=1000)
    span = locate_quote("The method improves accuracy.", artifact, chunks, 1, "p")
    assert span is not None
    assert (
        artifact.text[span.start : span.end]
        == span.quote
        == "The method\n  improves accuracy."
    )
    assert (
        locate_quote("The method improves precision.", artifact, chunks, 1, "p") is None
    )


def test_abstract_high_support_is_not_body_pass():
    check = qc(FakeJudge(verdict())).check(
        [Claim("Result [1]", [1])],
        FakeCollector({1: {"abstract": "The method improves accuracy."}}),
    )[0]
    assert check.verdict == "unverifiable"
    assert check.source_checks[0].abstract_verdict == "supported"
    assert check.reason_code == "missing_body"


def test_abstract_only_requires_explicit_opt_in_and_is_labeled():
    check = qc(FakeJudge(verdict()), qc_require_body=False).check(
        [Claim("Result [1]", [1])],
        FakeCollector({1: {"abstract": "The method improves accuracy."}}),
    )[0]
    assert check.verdict == "supported"
    assert check.reason_code == "abstract_only"
    assert "仅摘要" in check.reason


def test_body_detail_absent_from_abstract_is_preserved():
    def respond(prompt):
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        return (
            verdict("insufficient_evidence", None)
            if data["basis"] == "abstract"
            else verdict()
        )

    check = qc(FakeJudge(respond)).check(
        [Claim("The method improves accuracy [1].", [1])],
        collector(abstract="We describe a method."),
    )[0]
    assert check.verdict == "supported"
    assert check.source_checks[0].abstract_verdict == "unverifiable"
    assert check.source_checks[0].body_verdict == "supported"


def test_abstract_body_conflict_remains_pending():
    def respond(prompt):
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        return (
            verdict("contradicted", "The method fails.")
            if data["basis"] == "abstract"
            else verdict()
        )

    check = qc(FakeJudge(respond)).check(
        [Claim("Result [1]", [1])], collector(abstract="The method fails.")
    )[0]
    assert check.verdict == "unverifiable"
    assert check.reason_code == "abstract_body_conflict"


def test_contradiction_is_recorded_separately_from_missing_evidence():
    quote = "The method did not improve accuracy."
    check = qc(FakeJudge(verdict("contradicted", quote))).check(
        [Claim("The method improves accuracy [1].", [1])], collector(body=quote)
    )[0]
    assert check.verdict == "contradicted"
    assert check.source_checks[0].evidence[0].quote == quote


@pytest.mark.parametrize(
    "setting",
    [
        {"qc_max_claims": 0},
        {"qc_max_model_calls": 0},
        {"qc_review_rounds": 3},
        {"qc_repair_rounds": -1},
    ],
)
def test_invalid_budgets_are_rejected(setting):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VerifyConfig(**setting)


def test_late_evidence_is_retrieved_and_body_not_hidden_by_abstract():
    target = "TARGET experiment improves accuracy by 5%."
    body = ("Unrelated background. " * 300) + target
    judge = FakeJudge(
        lambda prompt: verdict("insufficient_evidence", None)
        if '"basis": "abstract"' in prompt
        else verdict(quote=target)
    )
    check = qc(judge).check(
        [Claim("TARGET experiment improves accuracy by 5% [1].", [1])],
        collector(body=body, abstract="A short overview."),
    )[0]
    assert check.verdict == "supported"
    assert any(target in p for p in judge.prompts)
    assert check.source_checks[0].evidence[-1].start > 1500


def test_abstract_disguised_as_full_content_cannot_pass_body():
    source = {
        "content_type": "abstract",
        "full_content": "The method improves accuracy.",
    }
    check = qc(FakeJudge(verdict())).check(
        [Claim("Result [1]", [1])], FakeCollector({1: source})
    )[0]
    assert check.reason_code == "missing_body"
    assert source_artifacts({"full_content": "x" * 20000}) == (None, None)


def test_reference_only_match_and_embedded_abstract_are_excluded():
    body = "Abstract\nABSTRACT_ONLY\nIntroduction\nActual experiment.\nReferences\nREFERENCE_ONLY"
    artifact = source_artifacts({"content_type": "full_text", "full_content": body})[1]
    chunks = retrieve(
        artifact,
        "REFERENCE_ONLY ABSTRACT_ONLY",
        chunk_chars=1000,
        top_k=4,
        context_chars=2000,
    )
    assert all(
        "REFERENCE_ONLY" not in c.text and "ABSTRACT_ONLY" not in c.text for c in chunks
    )


def test_custom_body_heading_does_not_promote_structured_abstract_subheading():
    text = "## Abstract\nOverview.\n### Results\nABSTRACT_RESULT\n## Experimental setup\nBODY_RESULT"
    body = source_artifacts({"content_type": "full_text", "full_content": text})[1]
    assert body is not None
    assert text[body.start :].startswith("## Experimental setup")


def test_each_citation_gets_independent_verdict():
    def respond(prompt):
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        return (
            verdict()
            if data["citation"] == 1
            else verdict("insufficient_evidence", None)
        )

    check = qc(FakeJudge(respond)).check(
        [Claim("Result [1, 2].", [1, 2])],
        FakeCollector(
            {
                1: {"body": "The method improves accuracy."},
                2: {"body": "Unrelated experiment."},
            }
        ),
    )[0]
    assert len(check.source_checks) == 2
    assert check.verdict == "unverifiable"
    assert check.source_checks[0].verdict == "supported"
    assert check.source_checks[1].verdict == "unverifiable"


@pytest.mark.parametrize(
    "state",
    [
        {"_verify": {"verified": False}},
        {"_constraint": {"hard_violations": ["year"]}},
        {"admission": "pending"},
    ],
)
def test_excluded_sources_cannot_support_claims(state):
    check = qc(FakeJudge(verdict())).check(
        [Claim("Result [1]", [1])], collector(**state)
    )[0]
    assert check.reason_code == "source_not_admitted"


def test_low_support_uses_separate_review_without_prior_explanation():
    first = FakeJudge(
        verdict("insufficient_evidence", None, reason="DO_NOT_LEAK_INITIAL_REASON")
    )
    review = FakeJudge(verdict())
    checker = CitationQc(first, VerifyConfig(qc_review_rounds=1), review_model=review)
    check = checker.check([Claim("Result [1]", [1])], collector())[0]
    assert check.verdict == "supported"
    assert check.source_checks[0].review_count == 1
    assert len(review.prompts) == 1
    assert "DO_NOT_LEAK_INITIAL_REASON" not in review.prompts[0]
    assert review.prompts[0].startswith("TASK: evidence_review")


def test_review_budget_does_not_silently_pass():
    judge = FakeJudge(verdict("insufficient_evidence", None))
    checker = CitationQc(judge, VerifyConfig(qc_max_model_calls=1, qc_review_rounds=2))
    check = checker.check([Claim("Result [1]", [1])], collector())[0]
    assert check.verdict == "unverifiable"
    assert check.reason_code == "model_budget_exhausted"
    assert len(judge.prompts) == 1


def test_claim_budget_covers_omitted_work_with_explicit_status():
    checks = qc(FakeJudge(verdict()), qc_max_claims=1).check(
        [Claim("A [1]", [1]), Claim("B [1]", [1])], collector()
    )
    assert checks[0].verdict == "supported"
    assert checks[1].reason_code == "claim_budget_exhausted"


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        {"verdict": "maybe"},
        {"verdict": None},
        {"verdict": "supported", "evidence_quotes": "not a list"},
    ],
)
def test_bad_judge_results_never_pass(payload):
    assert (
        qc(FakeJudge(payload)).check([Claim("Result [1]", [1])], collector())[0].verdict
        == "unverifiable"
    )


def test_judge_errors_do_not_leak_exception_details():
    def broken(prompt):
        raise RuntimeError("SECRET_API_KEY")

    check = qc(FakeJudge(broken)).check([Claim("Result [1]", [1])], collector())[0]
    assert check.verdict == "unverifiable"
    assert "SECRET_API_KEY" not in check.model_dump_json()


def test_revision_rechecks_changed_numbers_and_preserves_safe_text():
    def respond(prompt):
        if prompt.startswith("TASK: repair_claim"):
            return {"replacement": "Accuracy improved by 5% [1]."}
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        return verdict(
            "partial" if "50%" in data["claim"] else "supported",
            "Accuracy improved by 5%.",
        )

    checker = CitationQc(
        FakeJudge(respond), VerifyConfig(qc_review_rounds=0, qc_repair_rounds=1)
    )
    result = checker.verify_report(
        "# Findings\nAccuracy improved by 50% [1].\nAn invented uncited fact.",
        collector(body="Accuracy improved by 5%."),
    )
    assert "50%" not in result.content and "invented" not in result.content
    assert "Accuracy improved by 5% [1]." in result.content
    assert result.revised_claims == 1 and result.removed_claims == 1
    assert result.status == "partial" and result.content_sha256 == content_hash(
        result.content
    )
    assert result.checks[0].verdict == "supported"
    assert (
        result.content[result.checks[0].start : result.checks[0].end]
        == result.checks[0].claim
    )


def test_failed_repair_never_publishes_the_original_or_replacement():
    def respond(prompt):
        return (
            {"replacement": "Accuracy improved by 99% [1]."}
            if prompt.startswith("TASK: repair_claim")
            else verdict("partial", "Accuracy improved by 5%.")
        )

    checker = CitationQc(
        FakeJudge(respond), VerifyConfig(qc_review_rounds=0, qc_repair_rounds=1)
    )
    result = checker.verify_report(
        "Accuracy improved by 50% [1].", collector(body="Accuracy improved by 5%.")
    )
    assert result.content == NO_VERIFIED_CLAIMS
    assert not result.checks


@pytest.mark.parametrize(
    "replacement",
    [
        "Accuracy is 5% [99].",
        "# Sources\nAccuracy is 5% [1].",
        "Accuracy is 5% without a citation.",
    ],
)
def test_repair_cannot_introduce_sources_or_hide_unchecked_prose(replacement):
    judge = FakeJudge(
        lambda p: {"replacement": replacement}
        if p.startswith("TASK: repair_claim")
        else verdict("partial")
    )
    result = CitationQc(judge, VerifyConfig(qc_review_rounds=0)).verify_report(
        "Wrong result [1].", collector()
    )
    assert result.content == NO_VERIFIED_CLAIMS


def test_safe_statement_and_offsets_survive_deletion():
    result = qc(FakeJudge(verdict())).verify_report(
        "Uncited invention. The method improves accuracy [1].", collector()
    )
    assert result.content.strip() == "The method improves accuracy [1]."
    assert (
        result.content[result.checks[0].start : result.checks[0].end]
        == result.checks[0].claim
    )
    assert result.paper_checks[0]["body_supported"] == 1
    assert result.paper_checks[0]["abstract_support_ratio"] is None
    assert "核验未完成" in CitationQc.render_paper_section(result.paper_checks)


def test_source_lookup_uses_explicit_indices_and_rejects_ambiguity():
    lookup = SourceLookup(
        [
            {"index": "4", "body": "one"},
            {"index": 4, "body": "two"},
            {"body": "no index"},
            {"index": "9", "body": "nine"},
        ]
    )
    assert lookup.find_by_index(4) is None and lookup.find_by_index(1) is None
    assert lookup.find_by_index(9)["body"] == "nine"


def test_rendering_labels_abstract_ratio_and_keeps_legacy_marker_helper():
    check = ClaimCheck(
        claim="A [1]", citations=[1], verdict="unsupported", reason="no support"
    )
    assert "❌缺少支撑" in CitationQc.render_section([check])
    assert CitationQc.apply_inline_markers("A [1]", [check]) == "A [1] ⚠️缺少支撑"
    assert "不是幻觉概率" in CitationQc.render_paper_section(
        [
            {
                "citation": 1,
                "claims": 2,
                "abstract_supported": 1,
                "body_supported": 2,
                "review_count": 0,
            }
        ]
    )
