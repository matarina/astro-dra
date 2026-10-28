"""Report coverage and bounded passage selection regressions."""
import json
from types import SimpleNamespace
import pytest
from semantic_test_helpers import complete_payload

from research_verify.citation_qc import CitationQc, Claim
from research_verify.config import VerifyConfig
from research_verify.evidence import source_artifacts
from research_verify.passages import retrieve_passages
from research_verify.models import ClaimCheck


class Judge:
    def __init__(self, quote):
        self.quote = quote
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=json.dumps(complete_payload({"verdict":"supported", "supporting_fragment":self.quote})))


class Collector:
    def __init__(self, text):
        self.source = {"index":"1", "doi":"10.1234/fixture", "full_content":text, "content_type":"full_text"}

    def find_by_index(self, index):
        return self.source if index == 1 else None


def test_uncited_statement_is_audited_without_calling_judge():
    judge = Judge("not needed")
    claims = CitationQc().extract_claims("METTL3 increases proliferation.")
    result = CitationQc(judge).check(claims, None)[0]
    assert result.verdict == "unverifiable" and result.reason == "missing_citation"
    assert result.report_start == 0 and not judge.prompts


@pytest.mark.parametrize("report,expected", [
    ("甲增加增殖。乙降低死亡率。[2]", [[], [2]]),
    ("Mortality fell. [1] Survival increased.", [[1], []]),
    ("Mortality fell [1][2].", [[1,2]]),
    ("Mortality fell [1](https://example.org/p).", [[1]]),
    ("The reduction was 12.5% [1]. Another fact.", [[1], []]),
    ("Smith et al. observed reduced mortality [1].", [[1]]),
    ("- METTL3 increases proliferation.\n- ALKBH5 lowers growth [2].", [[], [2]]),
    ("METTL3 increases\nproliferation [1].", [[1]]),
])
def test_sentence_boundaries_and_citation_attachment(report, expected):
    claims = CitationQc().extract_claims(report)
    assert [c.citations for c in claims] == expected
    assert all(report[c.report_start:c.report_end] == c.text for c in claims)


def test_tables_have_header_context_and_preserve_uncited_rows():
    report = "| Marker | Result |\n|---|---|\n| METTL3 | 12% increase |\n| ALKBH5 | 4% reduction [1] |\n"
    claims = CitationQc().extract_claims(report)
    assert len(claims) == 2
    assert claims[0].kind == "table_candidate" and claims[0].citations == []
    assert "Marker" in claims[0].context and "Result" in claims[1].context


def test_scientific_heading_is_a_candidate_but_structural_heading_is_not():
    claims = CitationQc().extract_claims("# Results\n## METTL3 increases proliferation\n")
    assert len(claims) == 1 and claims[0].kind == "heading_candidate"


def test_code_sources_and_verification_tables_are_not_claims():
    report = """# Findings
Mortality declined [1].

```python
fake_claim = "A causes B [9]."
```

## Sources
1. Article [8]

### Nested source notes
Wrong fact [7].

## 结论可溯源性核查
| 结论 | 判定 |
|---|---|
| Fake fact [6] | unknown |
"""
    claims = CitationQc().extract_claims(report)
    assert len(claims) == 1 and claims[0].citations == [1]


def test_pure_question_or_recommendation_is_excluded_but_factual_advice_is_retained():
    report = "What should we investigate?\n\nWe recommend further research.\n\nWe recommend treatment because mortality decreases by 12%.\n"
    claims = CitationQc().extract_claims(report)
    assert len(claims) == 1 and "12%" in claims[0].text


def test_plain_reference_heading_and_fence_tildes_are_excluded():
    report = "Observation [1].\n\n~~~\nFake [4].\n~~~\n\nReferences:\nFake [3]."
    assert [c.citations for c in CitationQc().extract_claims(report)] == [[1]]


def test_related_passage_beyond_opening_keeps_absolute_source_position():
    text = ("Unrelated background about weather.\n\n"*100) + "METTL3 increases tumor proliferation."
    judge = Judge("METTL3 increases tumor proliferation.")
    result = CitationQc(judge).check([Claim("METTL3 increases tumor proliferation [1].", [1])], Collector(text))[0]
    item = result.citation_checks[0]
    assert result.verdict == "supported"
    assert item.evidence.locator.start > 1500
    assert text[item.evidence.locator.start:item.evidence.locator.end] == judge.quote
    assert judge.quote in judge.prompts[0]
    assert "lexical" in item.retrieval_method


def test_selected_budget_and_near_identical_window_dedup():
    text = "\n\n".join(f"METTL3 controls tumor progression in study {i}. " * 60 for i in range(8))
    selected = retrieve_passages(text, "METTL3 tumor progression", window_chars=300, max_passages=2, overlap_chars=40)
    assert len(selected) == 2 and sum(len(p.text) for p in selected) <= 600
    assert all(text[p.start:p.end] == p.text for p in selected)


def test_multiple_relevant_paragraphs_and_chinese_terms_are_retrieved():
    text = "无关背景。" + "\n\n" + "甲促进肿瘤增殖。" + "\n\n" + "乙抑制肿瘤增殖。"
    selected = retrieve_passages(text, "肿瘤增殖", max_passages=2)
    assert len(selected) == 2
    assert all("肿瘤增殖" in p.text for p in selected)


def test_reference_titles_cannot_be_used_as_supporting_passages():
    text = "Unrelated introduction.\n\nReferences\nMETTL3 increases tumor proliferation."
    selected = retrieve_passages(text, "METTL3 increases tumor proliferation")
    assert all("METTL3" not in p.text for p in selected)


def test_quote_across_omitted_passages_cannot_be_manufactured():
    text = "METTL3 increases\n\nUnrelated material.\n\nproliferation in tumors."
    result = CitationQc(Judge("METTL3 increases proliferation in tumors.")).check(
        [Claim("METTL3 increases proliferation in tumors [1].", [1])], Collector(text))[0]
    assert result.verdict == "unverifiable"


def test_repeated_quote_is_located_inside_selected_later_passage():
    text = "Observed a reduction.\n\n" + "Unrelated background.\n\n"*80 + "METTL3: Observed a reduction."
    artifact = source_artifacts(Collector(text).source)[0]
    start = text.index("METTL3:")
    loc = artifact.locate("Observed a reduction.", within=((start,len(text)),))
    assert loc.start >= start
    assert text[loc.start:loc.end] == loc.quote


def test_unselected_existing_quote_is_rejected():
    text = "A control measurement showed no change.\n\n"*30 + "METTL3 increases tumor proliferation."
    result = CitationQc(Judge("A control measurement showed no change.")).check(
        [Claim("METTL3 increases tumor proliferation [1].", [1])], Collector(text))[0]
    assert result.verdict == "unverifiable"
    assert result.citation_checks[0].reason_code == "quote_outside_presented_text"


def test_no_term_overlap_uses_explicit_bounded_fallback():
    selected = retrieve_passages("A"*2000, "unrelated", window_chars=400)
    assert len(selected) == 1 and selected[0].start == 0
    assert selected[0].score == 0 and len(selected[0].text) == 400


@pytest.mark.parametrize("extra", [
    {"qc_passage_chars":10},
    {"qc_max_passages":0},
    {"qc_passage_chars":200,"qc_passage_overlap_chars":200},
])
def test_invalid_retrieval_settings_are_rejected(extra):
    with pytest.raises(ValueError):
        VerifyConfig(**extra)


def test_audit_can_replay_report_offsets_and_retrieved_ranges():
    report = "METTL3 increases proliferation [1].\n\nMortality falls."
    qc = CitationQc(Judge("METTL3 increases proliferation."))
    checked = qc.check(qc.extract_claims(report), Collector("METTL3 increases proliferation."))
    parsed = ClaimCheck.model_validate_json(checked[0].model_dump_json())
    assert report[parsed.report_start:parsed.report_end] == parsed.claim
    assert parsed.citation_checks[0].retrieved_passages[0].end > 0
    assert checked[1].reason == "missing_citation"

def test_optional_pipe_table_rows_keep_column_context():
    report = "Marker | Result\n--- | ---\nMETTL3 | 12% increase\n"
    claims = CitationQc().extract_claims(report)
    assert len(claims) == 1 and claims[0].kind == "table_candidate"
    assert claims[0].context == "Marker | Result"


def test_reference_markers_alone_are_not_factual_claims():
    assert CitationQc().extract_claims("[1] [2](https://example.org)\n") == []


def test_range_bound_whitespace_quote_keeps_absolute_coordinates():
    text = "Earlier unrelated material.\n\nMETTL3\n increases\tproliferation."
    artifact = source_artifacts(Collector(text).source)[0]
    start = text.index("METTL3")
    loc = artifact.locate("METTL3 increases proliferation.", within=((start,len(text)),))
    assert loc.start == start and loc.quote == text[loc.start:loc.end]


def test_strategy_entry_audits_uncited_claim_and_late_evidence():
    import ast
    import re
    import threading
    from pathlib import Path
    from loguru import logger
    tree = ast.parse((Path(__file__).parents[1] / "langgraph_agent_strategy.py").read_text())
    collector_node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                          and n.name == "SearchResultsCollector")
    strategy_node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                         and n.name == "LangGraphAgentStrategy")
    entry = next(n for n in strategy_node.body if isinstance(n, ast.FunctionDef)
                 and n.name == "_attach_citation_qc")
    ns = dict(threading=threading, re=re, logger=logger, DEFAULT_MAX_UNIQUE_SOURCES=80)
    exec(compile(ast.Module(body=[collector_node,entry],type_ignores=[]),"<strategy-entry>","exec"),ns)
    quote = "METTL3 increases proliferation."
    source = Collector(("Unrelated background.\n\n"*100)+quote).source
    judge = Judge(quote)
    runner = SimpleNamespace(model=judge, collector=ns["SearchResultsCollector"]([source]))
    audit = []
    runner._write_citation_qc_json = lambda checks: audit.extend(c.model_dump() for c in checks)
    report = "METTL3 increases proliferation [1].\n\nMortality declined."
    output, checks = ns["_attach_citation_qc"](runner, report, [source])
    assert len(checks) == 1 and len(judge.prompts) == 1
    assert checks[0].citation_checks[0].evidence.locator.start > 1500
    assert output == report
    replay = ClaimCheck.model_validate_json(json.dumps(audit[0]))
    assert report[replay.report_start:replay.report_end] == "METTL3 increases proliferation [1]."

def test_nested_ignored_heading_does_not_reopen_reference_body():
    report = "Fact [1].\n\n## Sources\n### References\n### Additional notes\nWrong claim [9]."
    assert [c.citations for c in CitationQc().extract_claims(report)] == [[1]]


def test_mixed_advice_and_question_with_fact_cues_stays_a_candidate():
    claims = CitationQc().extract_claims("We recommend therapy because it supports immunity.\n\nMortality decreases by 12%, does it not?")
    assert len(claims) == 2 and all(not c.citations for c in claims)


def test_t04_acceptance_fixture_missing_citation_is_executable():
    from pathlib import Path
    data = json.loads((Path(__file__).parent / "fixtures/strict_verification_cases.json").read_text())
    case = next(c for c in data["cases"] if c["id"] == "T04")
    qc = CitationQc()
    result = qc.check(qc.extract_claims(case["claim"]), None)[0]
    assert result.verdict == case["expected_status"]
    assert result.reason == case["expected_reason"]

def test_table_column_context_changes_claim_identity():
    qc = CitationQc()
    a = qc.check([Claim("| METTL3 | 12% |", context="| Marker | Proliferation |")], None)[0]
    b = qc.check([Claim("| METTL3 | 12% |", context="| Marker | Mortality |")], None)[0]
    assert a.claim_id != b.claim_id
