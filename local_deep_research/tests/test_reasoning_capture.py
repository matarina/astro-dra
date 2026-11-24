import gzip
import json
from pathlib import Path
from stat import S_IMODE

import pytest

from research_verify.reasoning_capture import begin_reasoning_capture
from research_verify.synthesis_trace import trace_context


def load(recorder):
    return json.loads(gzip.decompress(recorder.path.read_bytes()))


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("LDR_RESEARCH_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("LDR_APP_DEBUG", "true")
    monkeypatch.delenv("LDR_REASONING_CAPTURE", raising=False)
    return tmp_path / "traces"


def test_capture_controls_and_task_isolation(root, monkeypatch):
    assert begin_reasoning_capture() is None
    with trace_context("task-4"):
        monkeypatch.setenv("LDR_REASONING_CAPTURE", "false")
        assert begin_reasoning_capture({"app.debug": {"value": True}}) is None
        monkeypatch.delenv("LDR_REASONING_CAPTURE")
        monkeypatch.delenv("LDR_APP_DEBUG")
        assert begin_reasoning_capture() is None
        capture = begin_reasoning_capture({"app.debug": {"value": True}})
        assert capture.path.parent == root / "task-4" / "model-reasoning"
        capture.finish()
        assert not load(capture)["reasoning_present"]
    with trace_context("../../other"):
        monkeypatch.setenv("LDR_REASONING_CAPTURE", "true")
        capture = begin_reasoning_capture()
        capture.finish()
        assert capture.path.is_relative_to(root)
        assert capture.path.parent != root / "task-4" / "model-reasoning"
    assert len(list(root.rglob("*.json.gz"))) == 2


def test_all_provider_fields_kept_separate_from_plain_response_and_tools(root, monkeypatch):
    monkeypatch.setenv("EXAMPLE_SECRET", "secret-1234567890")
    hidden = {"signature":"private-signature","type":"thinking","thinking":"abcdef中文"}
    with trace_context("task"):
        capture = begin_reasoning_capture()
        capture.observe({"model":"example", "id":"id-42","choices":[
            {"index":0, "message":{"reasoning_content":"returned field\n", "content":[hidden,
                {"type":"text","text":"do not record the answer"},
                {"type":"tool_use","input":{"reasoning":"do not record tool data"}}],
                "reasoning_details":[{"type":"reasoning.text","index":3,"text":"supplement"},
                                     {"type":"reasoning.encrypted","data":"private-ciphertext"}],
                "analysis":"prefix secret-1234567890", "tool_calls":[{"arguments":"do not record me"}]},
             "finish_reason":"stop"},
            {"index":1, "message":{"content":"just an answer"}, "finish_reason":"length"}
        ]})
        capture.finish()
    receipt = load(capture)
    assert receipt["model"] == "example" and receipt["provider_response_id"] == "id-42"
    assert receipt["reasoning_present"] and receipt["observation_errors"] == 0
    first, second = receipt["choices"]
    assert first["reasoning_fields"] == {
        "reasoning_content":"returned field\n", "content[0].thinking":"abcdef中文",
        "reasoning_details[3].text":"supplement", "analysis":"prefix <REDACTED>"}
    assert second["reasoning_fields"] == {} and second["finish_reason"] == "length"
    serialized = json.dumps(receipt)
    assert all(secret not in serialized for secret in
               ("do not record", "private-signature", "private-ciphertext", "secret-1234567890", "just an answer"))
    assert S_IMODE(capture.path.stat().st_mode) == 0o600
    assert S_IMODE(capture.path.parent.stat().st_mode) == 0o700


def test_interleaved_choice_deltas_inline_tags_and_empty_finish_frames(root):
    with trace_context("task"):
        capture = begin_reasoning_capture()
        chunks = [
            (0, {"content":"visible<th"}), (1, {"reasoning_content":"α"}),
            (0, {"content":"ink>İ真</thi"}), (1, {"reasoning_content":"β"}),
            (0, {"content":"nk>also visible<analysis>open<"}),
        ]
        for index, delta in chunks:
            capture.observe({"choices":[{"index":index, "delta":delta}]})
        capture.observe({"choices":[]})
        capture.observe({"choices":[{"index":1,"delta":{},"finish_reason":"stop"}]})
        capture.finish("cancelled")
        capture.finish("completed")
    receipt = load(capture)
    first, second = receipt["choices"]
    assert first["reasoning_fields"] == {"content.think":"İ真", "content.analysis":"open<"}
    assert first["unterminated_inline"] == ["content"] and first["finish_reason"] is None
    assert second["reasoning_fields"] == {"reasoning_content":"αβ"}
    assert receipt["status"] == "cancelled" and "visible" not in json.dumps(receipt)


def test_reject_redirected_task_dir(root, tmp_path):
    root.mkdir()
    (root / "task").symlink_to(tmp_path, target_is_directory=True)
    with trace_context("task"):
        assert begin_reasoning_capture() is None
    assert not (tmp_path / "model-reasoning").exists()


def test_specific_stage_trace_links_parallel_or_retried_calls(root):
    from research_verify.model_call_context import model_call_stage

    class Trace:
        trace_id = "synthesis123"
        events = []

        def record(self, stage, data):
            self.events.append((stage, data))

    trace = Trace()
    with trace_context("task"), model_call_stage("writer", trace):
        first = begin_reasoning_capture()
        second = begin_reasoning_capture()
        second.finish()
        first.finish()
    assert first.call_id != second.call_id
    for (event, link), recorder in zip(trace.events, (first, second), strict=True):
        assert event == "provider_reasoning_call"
        assert link == {"call_id": recorder.call_id, "stage":"writer",
                        "receipt":"model-reasoning/" + recorder.path.name}
        data = load(recorder)
        assert data["synthesis_trace_id"] == trace.trace_id and data["stage"] == "writer"
