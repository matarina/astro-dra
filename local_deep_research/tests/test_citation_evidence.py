"""Deterministic quote/mapping regressions; no real-paper accuracy claims."""
from hashlib import sha256
import json
from types import SimpleNamespace
import pytest
from semantic_test_helpers import complete_payload

from research_verify.evidence import paper_identity, source_artifacts
from research_verify.citation_qc import CitationQc, Claim
from research_verify.record_identity import make_record_provenance


class Collector:
    def __init__(self, mapping):
        self.mapping = mapping

    def find_by_index(self, index):
        return self.mapping.get(index)


class Judge:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=json.dumps(complete_payload(next(self.responses))))


def paper(text="The trial observed a 12% reduction.", **extras):
    return {"index": "1", "doi": "10.1234/fixture", "abstract": text, **extras}


def mismatched_record():
    receipt = make_record_provenance("crossref", {"DOI": "10.1234/fixture", "title": ["Other registered title"]})
    return paper(title="Local title", _verify={"verified": True, "record_provenance": receipt})


def payload(quote="The trial observed a 12% reduction.", verdict="supported"):
    return {"verdict": verdict, "supporting_fragment": quote, "reason": "fixture"}


def check(source, response):
    return CitationQc(Judge([response])).check([Claim("The trial observed a 12% reduction [1].", [1])],
                                               Collector({1: source}))[0]


def test_verbatim_quote_records_replayable_raw_coordinates_and_hash():
    source = paper("Background.\nThe trial observed a 12% reduction.\nEnd.")
    checked = check(source, payload())
    item = checked.citation_checks[0]
    loc = item.evidence.locator
    assert checked.verdict == "supported" and item.evidence.quote_verified
    assert loc.paper_id == "doi:10.1234/fixture"
    assert loc.basis == "abstract"
    assert loc.quote == source["abstract"][loc.start:loc.end]
    assert loc.content_sha256 == sha256(source["abstract"].encode()).hexdigest()
    assert checked.model_dump()["citation_checks"][0]["evidence"]["locator"]["quote"] == loc.quote


def test_whitespace_normalization_preserves_raw_offsets():
    source = paper("背景。 The trial\n observed a\t12% reduction.")
    loc = check(source, payload()).citation_checks[0].evidence.locator
    assert loc.quote == "The trial\n observed a\t12% reduction."
    assert source["abstract"][loc.start:loc.end] == loc.quote


@pytest.mark.parametrize("quote", [
    "The trial observed a 42% reduction.",
    "The trial observed a 12% increase.",
    "The trial observed ... reduction.",
    "the trial observed a 12% reduction.",
    "", None,
])
def test_fabricated_altered_or_missing_quote_cannot_pass(quote):
    result = check(paper(), payload(quote))
    assert result.verdict == "unverifiable"
    assert result.citation_checks[0].reason_code in {"quote_missing", "quote_not_found"}


def test_negation_is_not_removed_during_matching():
    result = check(paper("The intervention did not improve survival."),
                   payload("The intervention did improve survival."))
    assert result.verdict == "unverifiable"


def test_missing_second_source_cannot_be_hidden_by_first_supported_source():
    judge = Judge([payload()])
    result = CitationQc(judge).check([Claim("Conclusion [1, 2].", [1, 2])], Collector({1: paper()}))[0]
    assert result.verdict == "unverifiable"
    assert [c.verdict for c in result.citation_checks] == ["supported", "unverifiable"]
    assert result.citation_checks[1].reason_code == "unresolved_citation"
    assert len(judge.prompts) == 1


def test_each_cited_work_gets_its_own_prompt_and_quote():
    judge = Judge([payload(), payload(verdict="unsupported", quote=None)])
    sources = {1: paper(), 2: paper("Study B investigated unrelated outcomes.", index="2", doi="10.1234/b")}
    result = CitationQc(judge).check([Claim("Conclusion [1, 2].", [1, 2])], Collector(sources))[0]
    assert result.verdict == "partial"
    assert len(result.citation_checks) == 2
    assert "unrelated outcomes" not in judge.prompts[0]
    assert "12% reduction" not in judge.prompts[1]
    assert result.citation_checks[1].paper_id == "doi:10.1234/b"


def test_all_sources_must_have_located_quotes_for_supported():
    judge = Judge([payload(), payload()])
    result = CitationQc(judge).check([Claim("Conclusion [1, 2].", [1, 2])],
        Collector({1: paper(), 2: paper(index="2", doi="10.1234/b")}))[0]
    assert result.verdict == "supported"
    assert all(c.evidence.quote_verified for c in result.citation_checks)


@pytest.mark.parametrize("source,reason", [
    (paper(index="2"), "citation_index_mismatch"),
    (paper(index="bad"), "citation_index_mismatch"),
    (mismatched_record(), "identity_mismatch"),
    (paper(link="https://doi.org/10.9999/other"), "identity_mismatch"),
    ({"index":"1","abstract":"Text"}, "identity_unavailable"),
    ({"index":"1","doi":"10.1234/fixture"}, "source_text_unavailable"),
])
def test_bad_mapping_or_missing_identity_does_not_invoke_judge(source, reason):
    judge = Judge([])
    result = CitationQc(judge).check([Claim("Conclusion [1].", [1])], Collector({1:source}))[0]
    assert result.citation_checks[0].reason_code == reason
    assert not judge.prompts


def test_unscoped_negative_or_generic_warning_does_not_block_textual_assessment():
    for check in ({"verified": False}, {"verified": None, "warnings": ["request_incomplete"]}):
        judge = Judge([payload()])
        result = CitationQc(judge).check([Claim("Conclusion [1].", [1])], Collector({1: paper(_verify=check)}))[0]
        assert judge.prompts and result.source_checks[0].abstract_verdict == "supported"
        assert result.verdict == "unverifiable"  # a missing body is still missing


def test_full_content_abstract_marker_is_not_labeled_fulltext():
    source = paper(full_content="Enriched abstract text.", content_type="abstract")
    artifact = source_artifacts(source)[0]
    assert artifact.basis == "abstract"


def test_untyped_full_content_is_not_proof_of_original_text():
    source = {"index":"1","doi":"10.1234/fixture","full_content":"The trial observed a 12% reduction."}
    result = check(source, payload())
    assert result.verdict == "unverifiable"
    item = result.citation_checks[0]
    assert item.basis == "snippet"
    assert item.evidence.quote_verified
    assert item.reason_code == "original_text_unconfirmed"


def test_marked_fulltext_keeps_fulltext_provenance():
    source = paper(full_content="The trial observed a 12% reduction.", content_type="full_text")
    result = check(source, payload())
    assert result.citation_checks[0].evidence.locator.basis == "fulltext"


def test_relevant_quote_beyond_opening_window_is_retrieved():
    source = paper("A"*1600 + " The trial observed a 12% reduction.")
    result = check(source, payload())
    assert result.verdict == "supported"
    assert result.citation_checks[0].evidence.locator.start > 1500


def test_stable_identity_and_artifact_survive_citation_renumbering():
    a = paper(index="1")
    b = paper(index="9", doi="https://doi.org/10.1234/FIXTURE")
    assert paper_identity(a) == paper_identity(b)
    assert source_artifacts(a)[0].artifact_id == source_artifacts(b)[0].artifact_id


def test_changed_text_has_a_different_artifact_and_hash():
    a = source_artifacts(paper())[0]
    b = source_artifacts(paper("Changed text."))[0]
    assert a.paper_id == b.paper_id
    assert a.artifact_id != b.artifact_id and a.content_sha256 != b.content_sha256


def test_pmid_and_url_fallback_are_stable_without_number():
    assert paper_identity({"pmid":"12345678","index":"1"}) == "pmid:12345678"
    assert paper_identity({"url":"https://example.org/paper#part"}) == paper_identity({"url":"https://example.org/paper"})


def test_empty_citations_and_collector_failure_remain_unverifiable():
    assert CitationQc().check([Claim("Uncited", [])], Collector({}))[0].verdict == "unverifiable"
    class Broken:
        def find_by_index(self, index):
            raise ValueError("broken")
    result = CitationQc().check([Claim("x [1]", [1])], Broken())[0]
    assert result.citation_checks[0].reason_code == "source_lookup_error"


def test_audit_renders_each_reference_and_its_original_quote():
    result = check(paper(), payload())
    section = CitationQc.render_section([result])
    assert "12% reduction" in section
    assert "abstract" in section
    assert "doi:10.1234/fixture" in section

def test_strategy_entry_retains_per_citation_evidence_in_audit():
    # Execute the existing collector and entry method without importing the full
    # application, whose dependencies are absent from the standalone test venv.
    import ast
    import re
    import threading
    from pathlib import Path
    from loguru import logger
    from research_verify.config import VerifyConfig
    from research_verify.models import ClaimCheck
    tree = ast.parse((Path(__file__).parents[1] / "langgraph_agent_strategy.py").read_text())
    collector_node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                          and n.name == "SearchResultsCollector")
    strategy_node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                         and n.name == "LangGraphAgentStrategy")
    entry = next(n for n in strategy_node.body if isinstance(n, ast.FunctionDef)
                 and n.name == "_attach_citation_qc")
    ns = dict(threading=threading, re=re, logger=logger,
              DEFAULT_MAX_UNIQUE_SOURCES=80)
    exec(compile(ast.Module(body=[collector_node, entry], type_ignores=[]), "<strategy-entry>", "exec"), ns)
    source = paper()
    source["paper_id"] = "doi:10.1234/fixture"
    runner = SimpleNamespace(model=Judge([payload()]), collector=ns["SearchResultsCollector"]([source]))
    audit = []
    runner._write_citation_qc_json = lambda checks: audit.extend(c.model_dump() for c in checks)
    report, checks = ns["_attach_citation_qc"](runner, "The trial observed a 12% reduction [1].", [source])
    assert report == "The trial observed a 12% reduction [1]."
    assert checks[0].verdict == "supported"
    assert audit[0]["citation_checks"][0]["source_field"] == "abstract"
    replay = ClaimCheck.model_validate_json(json.dumps(audit[0]))
    assert replay.citation_checks[0].evidence.locator.quote == payload()["supporting_fragment"]
    assert runner._citation_checks[0].claim_id == checks[0].claim_id


def test_invalid_model_quote_type_or_json_shape_cannot_pass():
    class Bad:
        def invoke(self, prompt):
            return SimpleNamespace(content='{"verdict":"supported","supporting_fragment":["text"]}')
    result = CitationQc(Bad()).check([Claim("Conclusion [1]", [1])], Collector({1: paper()}))[0]
    assert result.verdict == "unverifiable"


def test_repeated_citation_is_checked_once():
    judge = Judge([payload()])
    result = CitationQc(judge).check([Claim("Conclusion [1, 1].", [1, 1])], Collector({1: paper()}))[0]
    assert len(result.citation_checks) == 1 and len(judge.prompts) == 1

def test_known_registered_doi_mismatch_cannot_pass():
    result = check(paper(_verify={"verified":True, "doi":"10.1234/other"}), payload())
    assert result.verdict == "unverifiable"
    assert result.citation_checks[0].reason_code == "identity_mismatch"


def test_locator_has_doi_or_pmid_resolver_when_source_url_is_absent():
    assert source_artifacts(paper())[0].source_url == "https://doi.org/10.1234/fixture"
    assert source_artifacts({"pmid":"12345678","abstract":"Study text"})[0].source_url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
