"""Unit tests for requirement 4 -- claim extraction + support judging."""

from __future__ import annotations

from research_verify.citation_qc import Claim, CitationQc
from research_verify.config import VerifyConfig


class FakeCollector:
    def __init__(self, mapping):
        self._m = mapping

    def find_by_index(self, idx):
        return self._m.get(idx)


class FakeJudge:
    def __init__(self, payload):
        self._payload = payload

    def invoke(self, prompt):
        class R:
            content = self._payload

        return R()


REPORT = """# Findings

m6A regulates hepatocellular carcinoma progression [1]. METTL3 is upregulated in tumors [1, 2].

This line has no citation.

Another supported claim here [3].

## Sources

1. source
"""


def test_extract_claims_only_cited_sentences():
    claims = CitationQc().extract_claims(REPORT)
    texts = [c.text for c in claims]
    assert any("[1]" in t for t in texts)
    assert all("no citation" not in t for t in texts)
    # multi-citation parsing
    multi = [c for c in claims if c.citations == [1, 2]]
    assert multi
    # Sources section excluded
    assert all("source" != c.text for c in claims)


def test_check_unverifiable_when_no_fragment():
    qc = CitationQc(judge_model=FakeJudge("{}"))
    collector = FakeCollector({1: {"index": "1", "link": "u"}})  # no text
    checks = qc.check([Claim("x [1]", [1])], collector)
    assert checks[0].verdict == "unverifiable"


def test_check_supported_via_judge():
    qc = CitationQc(judge_model=FakeJudge('{"verdict":"supported","reason":"ok"}'))
    collector = FakeCollector({1: {"index": "1", "abstract": "m6A drives HCC"}})
    checks = qc.check([Claim("x [1]", [1])], collector)
    assert checks[0].verdict == "supported"


def test_check_unsupported_and_partial():
    qc = CitationQc(judge_model=FakeJudge('{"verdict":"unsupported","reason":"no"}'))
    collector = FakeCollector({1: {"index": "1", "abstract": "text"}})
    assert qc.check([Claim("x [1]", [1])], collector)[0].verdict == "unsupported"


def test_check_judge_error_degrades_to_unverifiable():
    class BadJudge:
        def invoke(self, prompt):
            raise RuntimeError("boom")

    qc = CitationQc(judge_model=BadJudge())
    collector = FakeCollector({1: {"index": "1", "abstract": "text"}})
    assert qc.check([Claim("x [1]", [1])], collector)[0].verdict == "unverifiable"


def test_verdict_whitelist_rejects_garbage():
    qc = CitationQc(judge_model=FakeJudge('{"verdict":"maybe","reason":"?"}'))
    collector = FakeCollector({1: {"index": "1", "abstract": "t"}})
    assert qc.check([Claim("x [1]", [1])], collector)[0].verdict == "unverifiable"


def test_render_section_and_inline_markers():
    from research_verify.models import ClaimCheck

    checks = [
        ClaimCheck(claim="A [1]", citations=[1], verdict="supported"),
        ClaimCheck(claim="B [2]", citations=[2], verdict="unsupported", reason="no support"),
    ]
    section = CitationQc.render_section(checks)
    assert "结论可溯源性核查" in section and "❌缺少支撑" in section
    out = CitationQc.apply_inline_markers("B [2] is here.", checks)
    assert out == "B [2] ⚠️缺少支撑 is here."


def test_missing_judge_is_unverifiable():
    qc = CitationQc(judge_model=None)
    collector = FakeCollector({1: {"index": "1", "abstract": "t"}})
    assert qc.check([Claim("x [1]", [1])], collector)[0].verdict == "unverifiable"
