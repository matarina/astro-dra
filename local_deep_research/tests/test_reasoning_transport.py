import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage

from research_verify import reasoning_transport as transport


class Receipt:
    def __init__(self):
        self.observed = []
        self.status = None

    def observe(self, payload):
        self.observed.append(payload)

    def finish(self, status):
        assert self.status is None
        self.status = status


@pytest.fixture
def receipts(monkeypatch):
    monkeypatch.setenv("LDR_REASONING_CAPTURE", "1")
    calls = []

    def begin(settings):
        assert settings == {"app.debug": True}
        receipt = Receipt()
        calls.append(receipt)
        return receipt

    monkeypatch.setattr(transport, "begin_reasoning_capture", begin)
    return calls


def build(respond):
    mock = httpx.MockTransport(respond)
    return transport.create_capture_model(
        {"model": "fixture", "api_key": "unused", "base_url": "https://fixture.invalid/v1",
         "max_retries": 0, "http_client": httpx.Client(transport=mock),
         "http_async_client": httpx.AsyncClient(transport=mock)},
        {"app.debug": True, "secret.setting": "must not be retained"},
    )


def serve(request):
    body = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert body["messages"][-1]["content"] == "question"
    base = {"id": "provider-id", "model": "fixture", "created": 1}
    if not body.get("stream"):
        response = {**base, "object": "chat.completion", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "answer", "reasoning_content": "opaque"}}]}
        return httpx.Response(200, json=response)
    frames = []
    for delta, finish_reason in (({"role": "assistant", "reasoning_content": "first"}, None),
                                 ({"reasoning_content": "second", "content": "OK"}, None),
                                 ({}, "stop")):
        chunk = {**base, "object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": delta, "finish_reason": finish_reason}]}
        frames.append("data: " + json.dumps(chunk) + "\n\n")
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                          content="".join(frames) + "data: [DONE]\n\n")


def test_bound_sync_invocation_preserves_provider_extra_before_normalization(receipts):
    model = build(serve)
    tool = {"type": "function", "function": {"name": "lookup", "parameters": {"type":"object","properties":{}}}}
    answer = model.bind_tools([tool]).invoke("question")
    assert answer.content == "answer"
    assert receipts[0].observed[0]["choices"][0]["message"]["reasoning_content"] == "opaque"
    assert receipts[0].status == "completed"


def test_sync_streams_are_isolated_when_interleaved_and_cancelled(receipts):
    model = build(serve)
    messages = [HumanMessage(content="question")]
    one = model._stream(messages)
    two = model._stream(messages)
    next(one)
    assert [c.text for c in two] == ["", "OK", ""]
    one.close()
    assert [r.status for r in receipts] == ["cancelled", "completed"]
    assert [len(r.observed) for r in receipts] == [1, 3]
    assert [r["choices"][0]["delta"].get("reasoning_content")
            for r in receipts[1].observed] == ["first", "second", None]


def test_async_invoke_stream_and_error(receipts):
    async def run():
        model = build(serve)
        assert (await model.ainvoke("question")).content == "answer"
        text = "".join([chunk.content async for chunk in model.astream("question")])
        assert text == "OK"
        broken = build(lambda request: httpx.Response(502, json={"error":{"message":"test"}}))
        with pytest.raises(Exception):
            await broken.ainvoke("question")
    asyncio.run(run())
    assert [(r.status, len(r.observed)) for r in receipts] == [
        ("completed", 1), ("completed", 3), ("error", 0)]


def test_diagnostic_error_does_not_hide_normal_response(monkeypatch):
    monkeypatch.setenv("LDR_REASONING_CAPTURE", "1")
    attempts = []

    def broken(_):
        attempts.append(True)
        raise PermissionError()
    monkeypatch.setattr(transport, "begin_reasoning_capture", broken)
    assert build(serve).invoke("question").content == "answer"
    assert attempts == [True]


def test_explicit_off_returns_the_original_endpoint_model(monkeypatch):
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("LDR_REASONING_CAPTURE", "0")
    model = build(serve)
    assert type(model) is ChatOpenAI
    assert model.invoke("question").content == "answer"
