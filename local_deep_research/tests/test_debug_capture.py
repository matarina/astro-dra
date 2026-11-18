import json
from pathlib import Path

from research_verify.debug_capture import capture_chat_completion


class FakeResponse:
    status_code = 200

    def __init__(self):
        self.content = json.dumps({
            "model": "fixture",
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": "Visible answer",
                    "reasoning_content": "Provider-returned reasoning",
                },
            }],
        }).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def post(self, endpoint, *, json, timeout):
        assert endpoint.endswith("/chat/completions")
        assert json["max_tokens"] == 12000
        assert timeout == (15, 900)
        return FakeResponse()


def test_capture_preserves_raw_response_and_returned_reasoning(tmp_path):
    data, receipt = capture_chat_completion(
        FakeSession(), "http://fixture/v1/chat/completions",
        {"model": "fixture", "max_tokens": 12000},
        capture_dir=tmp_path, arm="candidate", case_id="D01",
    )
    assert data["choices"][0]["message"]["content"] == "Visible answer"
    assert receipt["thinking_fields"]["choices[0].message.reasoning_content"] == "Provider-returned reasoning"
    capture_path = Path(receipt["capture_dir"])
    assert json.loads((capture_path / "request.json").read_text())["max_tokens"] == 12000
    assert json.loads((capture_path / "response.json").read_text())["model"] == "fixture"
    assert (capture_path / "response.raw").read_bytes()


def test_capture_failure_writes_receipt(tmp_path):
    class FailedSession:
        def post(self, *args, **kwargs):
            raise TimeoutError("fixture timeout")

    try:
        capture_chat_completion(FailedSession(), "http://fixture", {}, capture_dir=tmp_path)
    except RuntimeError as exc:
        assert "fixture timeout" in str(exc)
    else:
        raise AssertionError("expected capture failure")
    receipts = list(tmp_path.rglob("receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["status"] == "failed"
