"""Budget exhaustion and tool failures must still deliver task-local originals."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json
from types import SimpleNamespace

import pytest

from research_verify.subtask_research import SubtaskCollector, track_sources, run_subtask, _fallback_material
from research_verify.subtask_handoff import build_handoff
from test_generation_grounding import collector


TEXT = "Loss of factor Q caused damage. Factor Q itself maintained balance."


def paper(number=1):
    return {"title": f"Study {number}", "link": f"https://example.org/{number}", "abstract": TEXT}


class Trace:
    def __init__(self):
        self.events = []

    def record(self, stage, data):
        self.events.append((stage, data))

    def values(self, stage):
        return [data for name, data in self.events if name == stage]


class Model:
    def __init__(self, error=None, text=None):
        self.prompts = []
        self.error = error
        self.text = text

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.text or json.dumps({
            "summary": {"directions": ["Mechanisms"], "priority_papers": [{"source_id": 1, "use_for": "Mechanism section"}],
                        "outline": ["Mechanisms", "Limitations"], "gaps": []},
            "evidence": [{"source_id": 1, "quote": TEXT}]}))


class Searching:
    def __init__(self, proxy, *, failure=None, empty=False):
        self.proxy, self.failure, self.empty = proxy, failure, empty
        self.tool_calls = 0
        self.closed = False

    def stream(self, request, config, stream_mode):
        assert stream_mode == "values"
        self.graph_limit = config["recursion_limit"]
        messages = [SimpleNamespace(type="human", content="Question")]
        yield {"messages": list(messages)}
        try:
            for n in range(100):
                messages.append(SimpleNamespace(type="ai", content="Search more",
                    tool_calls=[{"id": f"call-{n}"}], response_metadata={"token_usage": {"input_tokens": 10}}))
                yield {"messages": list(messages)}
                if not self.empty:
                    self.proxy.add_results([paper(n + 1)], engine_name="mock")
                self.tool_calls += 1
                messages.append(SimpleNamespace(type="tool", content="Original result", tool_call_id=f"call-{n}"))
                yield {"messages": list(messages)}
                if self.failure:
                    raise self.failure
        finally:
            self.closed = True


def run(agent_factory, model=None, max_rounds=3):
    base = collector()
    proxy, trace, model = SubtaskCollector(base), Trace(), model or Model()
    with track_sources(trace) as acquired:
        agent = agent_factory(proxy)
        text = run_subtask(agent, model, "Question", max_rounds, acquired, trace)
    return text, trace, agent, model


def test_search_stops_after_budget_and_finishes_all_last_round_tools():
    text, trace, agent, model = run(Searching)
    assert agent.tool_calls == 2 and agent.closed
    assert len(model.prompts) == 1
    state = trace.values("subtask_handoff")[0]["execution"]
    assert state == {"search_end": "search_budget", "delivery_status": "finalized", "model_rounds": 2,
                     "search_round_budget": 2, "available_source_ids": [1, 2]}
    assert TEXT in text
    assert trace.values("subtask_delivery_request")[0]["tools_enabled"] is False


@pytest.mark.parametrize("error", [type("GraphRecursionError", (Exception,), {})("limit"), RuntimeError("provider failure")])
def test_search_error_still_delivers_acquired_material_and_partial_messages(error):
    text, trace, agent, model = run(lambda p: Searching(p, failure=error))
    assert TEXT in text and len(model.prompts) == 1
    end = trace.values("subtask_search_end")[0]
    assert end["reason"] == ("iteration_limit" if type(error).__name__ == "GraphRecursionError" else "search_error")
    assert end["source_ids"] == [1]
    assert trace.values("subtask_messages")[0]["messages"][-1]["role"] == "tool"
    assert trace.values("subtask_sources")[0]["sources"][0]["abstract"] == TEXT


@pytest.mark.parametrize("error", [TimeoutError("timed out"), ValueError("bad provider response")])
def test_final_model_failure_still_returns_originals_without_a_fabricated_map(error):
    text, trace, agent, model = run(Searching, Model(error=error))
    assert TEXT in text and "No completed research map" in text
    assert trace.values("subtask_handoff")[0]["execution"]["delivery_status"] == "partial"
    assert len(model.prompts) == 1 and trace.values("subtask_delivery_error")


def test_malformed_delivery_does_not_lose_originals():
    text, trace, _, _ = run(Searching, Model(text="Unstructured navigation."))
    assert "Unstructured navigation." in text and TEXT in text
    assert trace.values("subtask_handoff")[0]["execution"]["delivery_status"] == "partial"


def test_no_hits_do_not_trigger_an_ungrounded_delivery_model_call():
    text, trace, _, model = run(lambda p: Searching(p, empty=True))
    assert not model.prompts and "No original source selections" in text
    assert trace.values("subtask_handoff")[0]["execution"]["delivery_status"] == "partial"


def test_natural_structured_delivery_is_reused_without_extra_model_call():
    class Finished:
        def __init__(self, proxy):
            self.proxy = proxy

        def stream(self, *args, **kwargs):
            self.proxy.add_results([paper()], "mock")
            yield {"messages": [SimpleNamespace(type="ai", tool_calls=[], content=json.dumps({
                "summary": "Read paper [1].", "evidence": [{"source_id": 1, "quote": TEXT}]}))]}
    text, trace, _, model = run(Finished)
    assert not model.prompts and TEXT in text
    assert trace.values("subtask_handoff")[0]["execution"]["delivery_status"] == "natural"


def test_tool_calls_from_last_allowed_round_are_all_resolved_before_delivery():
    class ParallelTools:
        def __init__(self, proxy):
            self.proxy = proxy

        def stream(self, *args, **kwargs):
            messages = [SimpleNamespace(type="ai", content="Search", tool_calls=[{"id": "a"}, {"id": "b"}])]
            yield {"messages": list(messages)}
            for i, call in enumerate(["a", "b"], 1):
                self.proxy.add_results([paper(i)], "mock")
                messages.append(SimpleNamespace(type="tool", content="Result", tool_call_id=call))
                yield {"messages": list(messages)}
            raise AssertionError("Controller should stop after receiving both tool results")
    _, trace, _, _ = run(ParallelTools, max_rounds=2)
    assert trace.values("subtask_search_end")[0]["source_ids"] == [1, 2]
    assert trace.values("subtask_search_end")[0]["reason"] == "search_budget"


def test_reused_tool_call_id_does_not_skip_the_next_rounds_real_results():
    class ReusedIds:
        def __init__(self, proxy):
            self.proxy = proxy

        def stream(self, *args, **kwargs):
            messages = []
            for n in range(2):
                messages.append(SimpleNamespace(type="ai", content="Search", tool_calls=[{"id": "same-id"}]))
                yield {"messages": list(messages)}
                self.proxy.add_results([paper(n + 1)], "mock")
                messages.append(SimpleNamespace(type="tool", content="Result", tool_call_id="same-id"))
                yield {"messages": list(messages)}
    _, trace, _, _ = run(ReusedIds)
    assert trace.values("subtask_search_end")[0]["source_ids"] == [1, 2]


def test_cancellation_does_not_start_delivery_or_hide_termination():
    class Cancelled(BaseException):
        pass
    model = Model()
    with pytest.raises(Cancelled):
        run(lambda p: Searching(p, failure=Cancelled()), model)
    assert not model.prompts


def test_source_tracking_isolated_between_workers_and_propagated_tool_threads():
    base = collector()
    base.add_results([paper(1), paper(2)], "mock")
    proxy = SubtaskCollector(base)
    def worker(index):
        with track_sources(Trace()) as acquired:
            with ThreadPoolExecutor(max_workers=1) as tools:
                tools.submit(copy_context().run, proxy.find_by_index, index).result()
            return acquired.snapshot()
    with ThreadPoolExecutor(max_workers=2) as workers:
        one, two = list(workers.map(worker, [1, 2]))
    assert set(one) == {1} and set(two) == {2}


def test_same_source_with_new_raw_content_is_recorded_as_progress():
    proxy, trace = SubtaskCollector(collector()), Trace()
    with track_sources(trace) as acquired:
        proxy.add_results([paper()], "mock")
        proxy.find_or_add_result({"link": paper()["link"], "fetched_content": "New primary methods text."}, "fetch")
        assert len(acquired.snapshot()) == 1
        assert acquired.snapshot()[1]["fetched_content"] == "New primary methods text."
        assert acquired.updates == 2


def test_source_capture_keeps_existing_whitelist_and_detaches_mutable_records():
    trace = Trace()
    proxy = SubtaskCollector(collector())
    record = {**paper(), "password": "private", "settings_snapshot": {"api_key": "private"}}
    with track_sources(trace) as acquired:
        proxy.add_results([record], "mock")
        saved = acquired.snapshot()[1]
        assert "password" not in saved and "settings_snapshot" not in saved
    assert "private" not in json.dumps(trace.values("subtask_source"))


def test_unrelated_shared_pool_sources_are_not_sent_to_delivery():
    base = collector()
    base.add_results([paper(1), {**paper(2), "abstract": "Unrelated private topic material."}], "mock")
    proxy, trace, model = SubtaskCollector(base), Trace(), Model()
    class Failed:
        def stream(self, *args, **kwargs):
            proxy.find_by_index(1)
            yield {"messages": [SimpleNamespace(type="ai", content="Bad draft says the opposite", tool_calls=[])]}
    with track_sources(trace) as sources:
        run_subtask(Failed(), model, "Question", 3, sources, trace)
    assert "Unrelated private topic" not in model.prompts[0]
    assert "Bad draft says the opposite" not in model.prompts[0]
    assert trace.values("subtask_delivery_request")[0]["available_source_ids"] == [1]


def test_navigation_object_is_rendered_with_source_ids_without_retelling_facts():
    obj = {"summary": {"directions": ["Dynamics"], "priority_papers": [{"source_id": 7, "use_for": "Mechanism section"}],
                       "outline": ["Mechanisms", "Gaps"], "gaps": ["Clinical evidence missing"]},
           "evidence": [{"source_id": 7, "quote": TEXT}]}
    handoff = build_handoff(json.dumps(obj), {7: {**paper(), "index": 7}}.get)
    assert handoff["status"] == "structured"
    assert "[7] Mechanism section" in handoff["summary"] and TEXT not in handoff["summary"]
    assert handoff["materials"][0]["text"] == TEXT


def test_late_relevant_source_is_not_lost_behind_earlier_irrelevant_hits():
    records = {i: {**paper(i), "index": i, "abstract": "Unrelated background. " * 280} for i in range(1, 8)}
    records[8] = {**paper(8), "index": 8, "abstract": "Temperature drift calibration was measured precisely."}
    handoff = _fallback_material("Temperature drift calibration", records)
    assert handoff["materials"][0]["source_id"] == 8
    assert handoff["materials"][0]["text"] == records[8]["abstract"]
    assert any(c["status"] == "omitted_material_budget" for c in handoff["materials"])


def test_fallback_can_select_a_late_passage_from_long_original_text():
    text = "Background. " * 1500 + "\n\nTemperature drift calibration changed after heating.\n\n" + "Methods. " * 1500
    handoff = _fallback_material("Temperature drift calibration", {7: {"index": 7, "content_type": "full_text", "content": text}})
    card = handoff["materials"][0]
    assert "Temperature drift calibration changed" in card["text"]
    assert card["text"] == text[card["start"]:card["end"]]


def test_step_telemetry_does_not_count_model_token_usage_again_on_tool_updates():
    _, trace, _, _ = run(Searching)
    steps = trace.values("subtask_messages_step")
    assert sum(len(step["new_model_usage"]) for step in steps) == 2
    assert [s["model_rounds"] for s in steps] == [0, 1, 1, 2, 2]
    assert all(s["messages_text_chars"] >= 0 for s in steps)
