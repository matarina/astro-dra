"""Regression checks for the installed report and collector entry points."""

import json
import sqlite3
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

strategy = pytest.importorskip(
    "local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy"
)
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
from research_verify.generation import INCOMPLETE_SYNTHESIS_MESSAGE


class ScriptedModel(FakeMessagesListChatModel):
    prompts: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.prompts.append(messages[0].content)
        return super()._generate(messages, *args, **kwargs)


def test_plain_writer_retries_an_empty_length_stopped_response():
    model = ScriptedModel(responses=[
        AIMessage(content="", response_metadata={"finish_reason": "length"}),
        AIMessage(content="Recovered report."),
    ])
    writer = StandardCitationHandler(model)
    assert writer._invoke_text("Write about [7].", stage="writer") == "Recovered report."
    assert len(model.prompts) == 2


def test_failed_synthesis_preserves_draft_and_reports_incomplete():
    source = {"index": "1", "link": "https://example.org/paper", "title": "Test record"}
    progress = Mock()
    state = SimpleNamespace(
        collector=SimpleNamespace(results=[source], sources=[source["link"]]),
        all_links_of_system=[source],
        get_setting=lambda key, default=None: default,
        _attach_doi_verification=Mock(),
        _attach_constraint_match=Mock(),
        _attach_citation_qc=lambda answer, sources: (answer, []),
        _format_citations=lambda answer, sources: answer,
        _update_progress=progress,
        citation_handler=SimpleNamespace(analyze_followup=Mock(side_effect=TimeoutError)),
    )
    result = strategy.LangGraphAgentStrategy._finalize(state, "Question", "Draft [1].", 1, 0, [])
    assert result["error"] == result["synthesis_error"] == INCOMPLETE_SYNTHESIS_MESSAGE
    assert result["findings"][0]["synthesis_error"] == INCOMPLETE_SYNTHESIS_MESSAGE
    assert result["current_knowledge"].endswith("Draft [1].")
    assert progress.call_args.args[2]["phase"] == "synthesis_incomplete"


def test_timed_out_subagent_cannot_update_the_next_subsections_sources(monkeypatch):
    collector = strategy.SearchResultsCollector([])
    release, finished = Event(), Event()
    late_record = {"link": "https://example.org/late", "title": "Previous subsection"}
    failures = []

    def invoke(*args):
        try:
            assert release.wait(3)
            for register in (lambda: collector.add_results([late_record]),
                             lambda: collector.find_or_add_result(late_record)):
                with pytest.raises(RuntimeError, match="scope expired") as exc:
                    register()
                failures.append(exc.value)
            return {"messages": []}
        finally:
            finished.set()

    monkeypatch.setattr(strategy, "SUBAGENT_TIMEOUT_SECONDS", 0.15)
    monkeypatch.setattr(strategy, "build_fetch_tool", lambda *a, **kw: None)
    monkeypatch.setattr(strategy, "_load_specialized_engine_tools", lambda *a, **kw: [SimpleNamespace(name="search_mock")])
    def stream(*args, **kwargs):
        yield invoke(*args)

    monkeypatch.setattr("langchain.agents.create_agent", lambda **kw: SimpleNamespace(stream=stream))
    subagent = strategy._make_research_subtopic_tool("mock", None, {}, collector, 2, search_enabled=False)
    try:
        assert "timed out" in subagent.invoke({"subtopics": ["Previous subsection"]})
        collector.reset()
        collector.add_results([{"link": "https://example.org/current", "title": "Current subsection"}])
    finally:
        release.set()
    assert finished.wait(3)
    assert len(failures) == 2
    assert [source["title"] for source in collector.results] == ["Current subsection"]


def test_failed_report_cleanup_uses_the_failure_notification(monkeypatch):
    from local_deep_research.constants import ResearchStatus
    from local_deep_research.settings import env_registry
    from local_deep_research.web.queue.processor_v2 import queue_processor
    from local_deep_research.web.routes import globals as research_globals
    from local_deep_research.web.services import research_service

    socket = Mock()
    failed, completed = Mock(), Mock()
    monkeypatch.setattr(queue_processor, "notify_research_completed", completed)
    monkeypatch.setattr(queue_processor, "notify_research_failed", failed)
    monkeypatch.setattr(research_service, "SocketIOService", lambda: socket)
    monkeypatch.setattr(research_globals, "cleanup_research", Mock())
    monkeypatch.setattr(env_registry, "is_test_mode", lambda: False)
    research_service.cleanup_research_resources(
        "research-id", "test-user", final_status=ResearchStatus.FAILED,
        error_message=INCOMPLETE_SYNTHESIS_MESSAGE,
    )
    failed.assert_called_once_with(
        "test-user", "research-id", error_message=INCOMPLETE_SYNTHESIS_MESSAGE, user_password=None,
    )
    completed.assert_not_called()
    assert socket.emit_to_subscribers.call_args.args[-1]["status"] == ResearchStatus.FAILED


def test_finalizer_hands_task_plan_and_journal_scope_to_actual_citation_writer():
    from local_deep_research.citation_handler import CitationHandler

    source = {"index": "1", "link": "https://example.org/paper", "title": "Test record"}
    plan = {"requirements": [{"requirement": "Return five papers"}]}
    journal_selection = {"minimum": 10, "operator": ">", "year": "latest"}
    actual = SimpleNamespace()

    def analyze_followup(question, search_results, previous_knowledge, nr_of_links):
        assert actual.task_plan is plan and actual.journal_selection is journal_selection
        assert question == "Question" and search_results == [source]
        return {"content": "Verified report [1]."}

    actual.analyze_followup = analyze_followup
    facade = CitationHandler.__new__(CitationHandler)
    facade._handler = actual
    state = SimpleNamespace(
        collector=SimpleNamespace(results=[source], sources=[source["link"]],
                                  task_plan=plan, journal_selection=journal_selection),
        all_links_of_system=[source],
        get_setting=lambda key, default=None: default,
        _attach_doi_verification=Mock(),
        _attach_constraint_match=Mock(),
        _attach_citation_qc=lambda answer, sources: (answer, []),
        _format_citations=lambda answer, sources: answer,
        _update_progress=Mock(),
        citation_handler=facade,
    )
    result = strategy.LangGraphAgentStrategy._finalize(state, "Question", "Draft [1].", 1, 0, [])
    assert result["current_knowledge"] == "Verified report [1]."


def test_lead_initializes_retrieval_without_a_planning_model_call():
    collector = strategy.SearchResultsCollector()
    collector.task_plan = {"requirements": [{"requirement": "Return 20 papers"}]}
    model = Mock()
    build_tools = Mock(return_value=[])
    state = SimpleNamespace(
        collector=collector, all_links_of_system=[], model=model, _build_tools=build_tools,
        _update_progress=Mock(), check_termination=Mock(), _error_result=lambda message: message,
    )
    request = "Summarize research on school phone bans."
    assert strategy.LangGraphAgentStrategy.analyze_topic(state, request) == "No tools available"
    build_tools.assert_called_once_with(overall_query=request)
    model.invoke.assert_not_called()
    assert collector.task_plan == {}


@pytest.fixture
def journal_catalog(monkeypatch, tmp_path):
    from research_verify import jcr_adapter
    from research_verify.jcr_mcp.jcr_database import JCRDatabase

    catalog = {"Journal A": 18.1, "Journal B": 10.0, "Journal C": 7.9, "Journal D": 12.0}
    path = tmp_path / "jcr.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE JCR2025 (Journal, IF)")
        connection.executemany("INSERT INTO JCR2025 VALUES (?, ?)", catalog.items())
    database = JCRDatabase(str(path), read_only=True)
    monkeypatch.setattr(database, "search_journal", Mock(wraps=database.search_journal))
    monkeypatch.setattr(jcr_adapter, "get_database", lambda: database)
    collector = strategy.SearchResultsCollector()
    collector.add_results([
        {"title": f"Study {i}", "link": f"https://example.org/{i}", "journal": journal,
         "abstract": "Study abstract."}
        for i, journal in enumerate(catalog, 1)
    ])
    return collector, strategy._make_jcr_tool(collector), database


def finalize_with_writer(collector, writer, request_text):
    state = SimpleNamespace(
        collector=collector, all_links_of_system=collector.results,
        get_setting=lambda key, default=None: default,
        _attach_doi_verification=Mock(), _attach_constraint_match=Mock(),
        _attach_citation_qc=lambda content, sources: (content, []),
        _format_citations=lambda content, sources: content, _update_progress=Mock(),
        citation_handler=writer,
    )
    return strategy.LangGraphAgentStrategy._finalize(state, request_text, "", 1, 0, [])


@pytest.mark.parametrize(("request_text", "calls", "parameters", "eligible"), [
    ("总结学校手机禁令对学生表现的研究", [], {}, None),
    ("展示相关论文的影响因子", [2], {"use": "display"}, None),
    ("按影响因子降序排列", [3, 1, 2], {"use": "rank", "order": "descending"}, [1, 2, 3]),
    ("找影响因子严格大于 10 的论文", [1, 2, 3], {"use": "filter", "minimum_if": 10, "operator": ">"}, [1]),
    ("展示相关论文 2024 年的 JCR IF", [2], {"use": "display", "year": "2024"}, None),
])
def test_journal_tool_is_opt_in_and_writer_reuses_receipts(
    monkeypatch, journal_catalog, request_text, calls, parameters, eligible,
):
    from research_verify import evidence_flow

    collector, tool, database = journal_catalog
    collector.task_question = request_text
    for index in (1, 4):
        collector.find_by_index(index).update(
            impact_factor=2.0, passes_threshold=False,
            _jcr_check={"status": "found", "requested_metric_year": "latest", "impact_factor": 2.0},
        )
    receipts = [json.loads(tool.invoke({"journal_name": collector.find_by_index(i)["journal"],
                                        "source_index": i, **parameters})) for i in calls]
    if "minimum_if" in parameters:
        assert [row["passes_threshold"] for row in receipts] == [True, False, False]
    else:
        assert all(row["passes_threshold"] is None for row in receipts)
    if "year" in parameters:
        assert receipts[0]["missing_reason"] == "metric_year_unavailable"
    assert database.search_journal.call_count == len(calls)

    monkeypatch.setattr(evidence_flow, "resolve_source_identities", lambda *a, **kw: None)
    monkeypatch.setattr(evidence_flow, "resolve_versions", lambda *a, **kw: None)
    model = ScriptedModel(responses=[AIMessage(content="Report from supplied evidence.")])
    writer = StandardCitationHandler(model, settings_snapshot={"citation.enable_source_reading": False})
    result = finalize_with_writer(collector, writer, request_text)
    assert result["current_knowledge"] == "Report from supplied evidence."
    assert database.search_journal.call_count == len(calls)
    assert len(model.prompts) == 1
    assert model.prompts[0].count("jcr_mcp status:") == len(calls)
    assert "Impact-factor metadata (impact_factor): 2.0" not in model.prompts[0]
    if eligible is None:
        assert "Confirmed eligible paper IDs" not in model.prompts[0]
    else:
        assert f"requested order, if specified: {eligible}. Pending IDs: [4]" in model.prompts[0]
    if "year" in parameters:
        assert "jcr_mcp metric year: 2024" in model.prompts[0]
        assert "metric_year_unavailable" in model.prompts[0]


def test_journal_cache_reuses_value_by_year_and_recalculates_task_threshold(journal_catalog):
    collector, tool, database = journal_catalog
    collector.add_results([{"link": "https://example.org/another", "journal": "Journal A"}])
    first = json.loads(tool.invoke({"journal_name": "Journal A", "source_index": 1, "use": "filter",
                                    "minimum_if": 10, "operator": ">="}))
    collector.reset()
    assert not collector.journal_checks and not collector.journal_selection
    second = json.loads(tool.invoke({"journal_name": "Journal A", "source_index": 5, "year": "2025",
                                     "use": "filter", "minimum_if": 18.1, "operator": ">"}))
    assert database.search_journal.call_count == 1
    assert first["impact_factor"] == second["impact_factor"] == 18.1
    assert first["passes_threshold"] is True and second["passes_threshold"] is False


def test_journal_filter_requires_an_explicit_comparison_before_lookup(journal_catalog):
    _, tool, database = journal_catalog
    result = json.loads(tool.invoke({"journal_name": "Journal A", "source_index": 1,
                                     "use": "filter", "minimum_if": 10}))
    assert result["status"] == "invalid_input"
    database.search_journal.assert_not_called()


def test_same_79_if_randomized_trial_across_three_independent_tasks(monkeypatch, journal_catalog):
    from local_deep_research.citation_handlers import standard_citation_handler
    from research_verify import evidence_flow, task_evidence

    _, _, database = journal_catalog
    design_quote = "参与者被随机分到干预组和对照组。"
    paper = {"title": "School programme study", "journal": "Journal C",
             "link": "https://example.org/rct", "doi": "10.1234/rct", "abstract": design_quote}
    events = {}
    trace = SimpleNamespace(record=lambda stage, data: events.update({stage: data}))
    monkeypatch.setattr(standard_citation_handler, "start_trace", lambda *args: nullcontext(trace))
    monkeypatch.setattr(evidence_flow, "resolve_source_identities", lambda *a, **kw: None)
    monkeypatch.setattr(evidence_flow, "resolve_versions", lambda *a, **kw: None)
    rereads = []
    monkeypatch.setattr(task_evidence, "gather_evidence",
                        lambda handler, sources, targets, *args: rereads.extend(targets) or True)

    for request_text, threshold, operator, expected in (
        ("要求 IF > 10", 10, ">", "excluded"),
        ("只要随机对照试验，补查随机分组方法", None, None, "confirmed"),
        ("要求 IF ≥ 7", 7, ">=", "confirmed"),
    ):
        collector = strategy.SearchResultsCollector()
        collector.task_question = request_text
        collector.add_results([paper])
        raw_source = collector.results[0]
        planned_replies = []
        if threshold is not None:
            tool = strategy._make_jcr_tool(collector)
            receipt = json.loads(tool.invoke({"journal_name": "Journal C", "source_index": 1,
                "use": "filter", "minimum_if": threshold, "operator": operator}))
            assert receipt["impact_factor"] == 7.9 and receipt["metric_year"] == 2025
            assert receipt["passes_threshold"] is (expected == "confirmed")
            assert "passes_threshold" not in raw_source
        else:
            # An older persisted source can have only the flattened flag.
            raw_source.update(_screened_task=True, impact_factor=7.9, metric_year=2025,
                              passes_threshold=False)
            collector.record_task_requirements({
                "eligibility": [{"criterion": "随机对照试验", "user_quote": "随机对照试验"}],
                "questions": [{"question": "随机分组方法", "user_quote": "随机分组方法"}],
            })
            planned_replies.extend([
                AIMessage(content='{"gaps":[{"source_id":1,"question":"随机分组方法"}]}'),
                AIMessage(content=json.dumps({"checks": [
                    {"source_id": 1, "criterion_id": 1, "status": "supported", "quote": design_quote},
                ]})),
            ])
        model = ScriptedModel(responses=[*planned_replies, AIMessage(content="Report.")])
        writer = StandardCitationHandler(model, settings_snapshot={"citation.enable_source_reading": False})
        finalize_with_writer(collector, writer, request_text)
        assert events["final_eligibility"]["sources"][1]["status"] == expected
        if threshold is None:
            assert rereads == [(1, "随机分组方法")]
            assert "Impact-factor metadata" not in model.prompts[-1]
            assert design_quote in model.prompts[-1]
    database.search_journal.assert_called_once()


@pytest.mark.parametrize(("metric_order", "expected"), [(None, [3, 1, 2]), ("descending", [1, 2, 3])])
def test_if_selection_keeps_candidate_order_across_writer_batches(
    monkeypatch, journal_catalog, metric_order, expected,
):
    from research_verify import evidence_flow, generation
    from research_verify.jcr_adapter import sources_with_journal_receipts

    collector, tool, _ = journal_catalog
    sources = [collector.find_by_index(i) for i in (3, 1, 2)]
    for source in sources:
        options = {"use": "filter_and_rank", "order": metric_order} if metric_order else {"use": "filter"}
        tool.invoke({"source_index": int(source["index"]), "journal_name": source["journal"],
                     "minimum_if": 7, "operator": ">=", **options})
    monkeypatch.setattr(evidence_flow, "resolve_source_identities", lambda *a, **kw: None)
    monkeypatch.setattr(evidence_flow, "resolve_versions", lambda *a, **kw: None)
    monkeypatch.setattr(evidence_flow, "writing_batches", lambda *a: ["First [1].", "Second [3] [2]."])
    format_material = generation.format_source_documents

    def format_batch(documents, query, **kwargs):
        current = [doc for doc in documents if int(doc.metadata["index"]) in kwargs["required_ids"]]
        return format_material(current, query, **kwargs)

    monkeypatch.setattr(generation, "format_source_documents", format_batch)
    model = ScriptedModel(responses=[AIMessage(content="Report [1]."), AIMessage(content="Report [3] [2].")])
    writer = StandardCitationHandler(model, settings_snapshot={"citation.enable_source_reading": False})
    writer.journal_selection = collector.journal_selection
    scoped = list(sources_with_journal_receipts(sources, collector.journal_checks, collector.journal_selection))
    writer.analyze_followup("List qualifying papers", scoped, "Draft [1] [3] [2].", 0)
    assert "if specified: [1]." in model.prompts[0]
    assert f"if specified: {expected}. Pending IDs: []" in model.prompts[1]
    assert "Preserve the supplied order unless the user requested another order." in model.prompts[1]


@pytest.mark.parametrize(("request_text", "check_design", "limit_requested"), [
    ("只要随机对照试验", True, False),
    ("给我 5 篇代表性论文", False, True),
    ("给我 5 篇随机对照试验", True, True),
])
def test_delivery_count_does_not_control_eligibility(
    monkeypatch, request_text, check_design, limit_requested,
):
    from research_verify import evidence_flow

    monkeypatch.setattr(evidence_flow, "resolve_source_identities", lambda *args, **kwargs: None)
    monkeypatch.setattr(evidence_flow, "resolve_versions", lambda *args, **kwargs: None)
    collector = strategy.SearchResultsCollector()
    collector.task_question = request_text
    requirements = {}
    if limit_requested:
        requirements["requirements"] = [
            {"requirement": "交付 5 篇论文", "user_quote": "5 篇", "status": "explicit"},
        ]
    if check_design:
        requirements["eligibility"] = [{"criterion": "随机对照试验", "user_quote": "随机对照试验"}]
    collector.record_task_requirements(requirements)
    abstracts = ["参与者被随机分到干预组和对照组。"] * 6 + ["这是一项非随机观察性研究。"]
    records = [{"title": f"Study {i}", "link": f"https://example.org/{i}", "abstract": abstract}
               for i, abstract in enumerate(abstracts, 1)]
    collector.add_results(records)
    responses = []
    if check_design:
        responses.append(AIMessage(content=json.dumps({"checks": [
            {"source_id": i, "criterion_id": 1, "quote": abstract,
             "status": "supported" if i <= 6 else "contradicted"}
            for i, abstract in enumerate(abstracts, 1)
        ]})))
    responses.append(AIMessage(content="Report using the supplied studies."))
    model = ScriptedModel(responses=responses)
    writer = StandardCitationHandler(model, settings_snapshot={"citation.enable_source_reading": False})
    writer.task_plan = collector.task_plan
    writer.analyze_followup(request_text, collector.results, "", 0)

    assert len(model.prompts) == (2 if check_design else 1)
    assert request_text in model.prompts[-1]
    if limit_requested:
        assert "交付 5 篇论文" in model.prompts[-1]
    if check_design:
        assert "Check explicit inclusion criteria" in model.prompts[0]
        assert "eligible paper IDs in requested order, if specified: [1, 2, 3, 4, 5, 6]" in model.prompts[-1]
    else:
        assert "Confirmed eligible paper IDs" not in model.prompts[-1]
