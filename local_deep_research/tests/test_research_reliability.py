"""Regression checks for the installed report and collector entry points."""

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

strategy = pytest.importorskip(
    "local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy"
)
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
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


def journal_writer(responses, lookups):
    @tool("search_journal")
    def journal(source_index: int) -> str:
        """Look up a metric in the test catalog."""
        lookups.append(source_index)
        return f"Journal metric for source {source_index}."

    model = ScriptedModel(responses=responses)
    writer = StandardCitationHandler(model)
    writer.set_writer_jcr_tool_factory(lambda: journal)
    return writer, model


def lookup_message(index):
    return AIMessage(content="", tool_calls=[{
        "name": "search_journal", "args": {"source_index": index}, "id": f"lookup-{index}",
    }])


@pytest.mark.parametrize("look_up", [False, True])
def test_empty_assistant_message_retries_without_using_input_or_tool_as_output(look_up):
    responses = [lookup_message(7)] if look_up else []
    responses.extend([
        AIMessage(content="", response_metadata={"finish_reason": "length"}),
        AIMessage(content="Recovered report."),
    ])
    writer, model = journal_writer(responses, [])
    assert writer._invoke_text("Write about [7].", stage="writer") == "Recovered report."
    assert ("Journal metric for source 7." in model.prompts[-1]) is look_up


def test_writer_can_complete_one_sequential_lookup_per_supplied_source():
    indices = list(range(1, 26))
    lookups = []
    writer, _ = journal_writer(
        [*(lookup_message(index) for index in indices), AIMessage(content="Finished report.")],
        lookups,
    )
    assert writer._invoke_text("Rank the sources.", stage="writer", source_count=len(indices)) == "Finished report."
    assert lookups == indices


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
    monkeypatch.setattr("langchain.agents.create_agent", lambda **kw: SimpleNamespace(invoke=invoke))
    subagent = strategy._make_research_subtopic_tool("mock", None, {}, collector, 1, search_enabled=False)
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
