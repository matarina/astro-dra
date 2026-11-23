"""Regression fixtures for errors that previously changed report content silently."""
import json
from types import SimpleNamespace

from langchain_core.documents import Document

from local_deep_research.report_generator import IntegratedReportGenerator
from local_deep_research.web.services.research_service import _format_checked_answer
from local_deep_research.web.services import report_assembly_service
from local_deep_research.web_search_engines.engines import search_engine_pubmed
from local_deep_research.web_search_engines.relevance_filter import filter_previews_for_relevance
from research_verify.evidence_flow import parse_review, review_units
from research_verify.generation import SourceMaterial, format_source_documents, page_excerpts
from research_verify.source_reading import build_reading_notes
from research_verify.synthesis_trace import source_ids


def test_pubmed_sends_balanced_queries_and_keeps_the_optimizer_date_clause(monkeypatch):
    captured = []
    from research_verify import retrieval
    monkeypatch.setattr(retrieval, "pace", lambda *a: None)
    def request(url, **kwargs):
        captured.append(kwargs["params"]["term"])
        return SimpleNamespace(status_code=429 if len(captured) == 1 else 200,
                               headers={"Retry-After": "0"}, close=lambda: None,
                               raise_for_status=lambda: None,
                               json=lambda: {"esearchresult": {"idlist": [], "count": "0"}})

    monkeypatch.setattr(search_engine_pubmed, "safe_get", request)
    query = '"BCR-ABL+"[Title/Abstract] AND "T cell"[Title/Abstract]'
    optimized = 'single-cell[Title/Abstract]\nAND 2026[dp]'
    model = SimpleNamespace(invoke=lambda _: SimpleNamespace(content=optimized))
    engine = search_engine_pubmed.PubMedSearchEngine(llm=model, optimize_queries=True)
    assert engine._optimize_query_for_pubmed("Find papers published in 2026") == optimized
    assert engine._optimize_query_for_pubmed(query) == query
    engine._search_pubmed(query)
    assert captured == [query, query]


def test_failed_relevance_batch_retains_unscreened_candidates():
    def select(prompt):
        if "Eligible paper" in prompt:
            raise TimeoutError()
        return SimpleNamespace(content="[]")

    previews = [{"title": "Forests"}, {"title": "Eligible paper"}]
    retained = filter_previews_for_relevance(
        SimpleNamespace(invoke=select), previews, "Tumor samples", batch_size=1,
    )
    assert retained == [{"title": "Eligible paper", "relevance_filter_status": "unavailable"}]


def test_unavailable_source_selector_uses_the_end_of_the_candidate_pool():
    documents = [
        Document(page_content="Abstract. " * 70,
                 metadata={"index": i, "title": f"Paper {i}", "source": f"https://example.org/{i}"})
        for i in range(1, 21)
    ]
    material = format_source_documents(documents, "Question", selector=lambda _: "{}", max_chars=3700)
    assert {1, 20} <= set(source_ids(material))
    assert source_ids(SourceMaterial("[99]\nTitle: Embedded numeric text", {})) == []



def test_selection_transport_failure_skips_subsequent_model_calls(monkeypatch):
    from research_verify import generation

    monkeypatch.setattr(generation, "SOURCE_SELECTION_BATCH_CHARS", 1000)
    documents = [Document(page_content="Abstract. " * 70, metadata={"index": i, "title": str(i)})
                 for i in range(1, 7)]
    calls, receipts = [], []

    def offline(prompt):
        calls.append(prompt)
        raise TimeoutError()

    generation.format_source_documents(documents, "Question", selector=offline,
                                       max_chars=3000, selection_receipts=receipts)
    assert len(calls) == 1
    assert receipts[0]["fallback_batches"] == 6
    assert receipts[0]["batch_errors"][0]["error_type"] == "TimeoutError"
    assert receipts[0]["batch_errors"][-1]["error_type"] == "selector_unavailable"


def test_excerpting_keeps_acquired_appendix_and_reader_locates_a_short_count():
    body = "General introduction. " * 400 + "\n\nReferences\n\nAppendix\n\nMethods: Xenium, n=6 per arm."
    assert "n=6 per arm" in page_excerpts(body, "Xenium sample counts", budget=1800)
    notes = build_reading_notes(json.dumps({"readings": [{"source_id": 1, "observations": [
        {"quote": "n=6 per arm", "subject_quote": "n=6"},
    ]}]}), {1: body})
    assert notes["observations"][0]["start"] == body.index("n=6 per arm")


def test_active_review_distinguishes_supplied_quotes_from_unbacked_verdicts():
    claims = {1: {"text": "Six samples per group [7].", "source_ids": [7]}}
    issue = {"claim_id": 1, "status": "supported", "source_id": 7}
    material = {7: "Six samples per group."}
    def check(payload):
        return parse_review(json.dumps({"issues": [payload]}), claims,
                            include_checked=True, material=material)
    pending, checked = check(issue)
    assert not checked and pending[0]["status"] == "review_support_unverified"
    assert check({**issue, "evidence_quote": material[7]})[0] == []
    assert check({**issue, "source_id": 8, "evidence_quote": material[7]})[0]
    assert any("Six samples per group" in unit.text for unit in review_units(
        "## Sources\n\nSix samples per group [7]."
    ))


def test_detailed_report_keeps_study_headings_and_counts():
    generator = object.__new__(IntegratedReportGenerator)
    generator.model = SimpleNamespace(invoke=lambda _: SimpleNamespace(
        content="STRUCTURE\n1. Design\n2) Cell sources and sample counts\n - Controls | Sample count\nEND_STRUCTURE",
    ))
    outline = generator._determine_report_structure({"current_knowledge": "Acquired data"}, "Study design")
    assert outline[-1]["name"] == "Cell sources and sample counts"
    content = "## Sources for the Analysis\n- Tumor: 6 samples\n- Controls: 4 samples\n\n## Sources\n\n[1] Study"
    cleaned = generator._strip_subsection_boilerplate(content, "Design")
    assert cleaned.endswith("Controls: 4 samples")


def test_citation_save_preserves_code_and_distinct_same_title_sources():
    body = "Example `data[7]`:\n\n```text\n[7]\n```\n\nStudy A [8]. Study B [9]."
    sources = [{"index": i, "title": "Single-cell and spatial profiling of human cancer",
                "link": f"https://example.org/{i}"} for i in (7, 8, 9)]
    rendered, selected = _format_checked_answer(body, sources)
    assert "`data[7]`" in rendered and "```text\n[7]\n```" in rendered
    assert [source["original_indices"] for source in selected] == [["8"], ["9"]]


def test_report_assembler_does_not_hide_bibliography_behind_a_subject_heading(monkeypatch):
    monkeypatch.setattr(report_assembly_service, "_build_sources_markdown", lambda *a: "[7] Study")
    monkeypatch.setattr(report_assembly_service, "_build_metrics_markdown", lambda *a: "")
    row = SimpleNamespace(report_content="## Sources of tumor samples\n\nSix donors.", research_meta={})
    report = report_assembly_service.assemble_full_report(row, None)
    assert report.startswith(row.report_content)
    assert report.endswith("## Sources\n\n[7] Study")


def test_json_recovery_preserves_punctuation_inside_strings():
    from local_deep_research.utilities.json_utils import extract_json

    data = extract_json('{"title":"Study ,} includes ... and ```json",}', dict)
    assert data == {"title": "Study ,} includes ... and ```json"}
