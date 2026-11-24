"""Observe provider-returned reasoning at the OpenAI chat completion boundary."""

import asyncio
from contextlib import aclosing, contextmanager

from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import PrivateAttr

from .reasoning_capture import begin_reasoning_capture, reasoning_capture_enabled


class ReasoningChatOpenAI(ChatOpenAI):
    """Identical model invocation, with one private recorder per active call."""

    _debug_settings: dict = PrivateAttr(default_factory=dict)
    _reasoning_recorder = PrivateAttr(default=None)
    _capturing_stream: bool = PrivateAttr(default=False)

    @contextmanager
    def _capture_call(self, *, streaming=False):
        try:
            recorder = begin_reasoning_capture(self._debug_settings)
        except Exception as exc:
            logger.warning("Reasoning capture could not start ({})", type(exc).__name__)
            recorder = None
        if recorder is None:
            yield self
            return

        # LangChain can use this same model for concurrent calls and tool
        # bindings. A shallow copy shares the SDK connection pools but owns
        # its request state even when async conversion runs in a worker thread.
        call = self.model_copy()
        call._reasoning_recorder = recorder
        call._capturing_stream = streaming
        status = "completed"
        try:
            yield call
        except (GeneratorExit, asyncio.CancelledError):
            status = "cancelled"
            raise
        except BaseException:
            status = "error"
            raise
        finally:
            try:
                recorder.finish(status=status)
            except Exception as exc:
                logger.warning("Reasoning capture could not finish ({})", type(exc).__name__)

    def _observe(self, payload):
        if self._reasoning_recorder is not None:
            try:
                data = payload if isinstance(payload, dict) else payload.model_dump()
                self._reasoning_recorder.observe(data)
            except Exception as exc:
                logger.warning("Reasoning capture could not observe response ({})", type(exc).__name__)

    def _create_chat_result(self, response, generation_info=None):
        # A structured stream can send its aggregate completion after its
        # deltas. The deltas were already recorded at conversion time.
        if not self._capturing_stream:
            self._observe(response)
        return super()._create_chat_result(response, generation_info)

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        if "choices" in chunk:
            self._observe(chunk)
        elif chunk.get("type") == "chunk" and "chunk" in chunk:
            self._observe(chunk["chunk"])
        return super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        with self._capture_call() as call:
            return super(ReasoningChatOpenAI, call)._generate(messages, stop, run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        with self._capture_call() as call:
            return await super(ReasoningChatOpenAI, call)._agenerate(messages, stop, run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        with self._capture_call(streaming=True) as call:
            yield from super(ReasoningChatOpenAI, call)._stream(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        with self._capture_call(streaming=True) as call:
            stream = super(ReasoningChatOpenAI, call)._astream(messages, stop, run_manager, **kwargs)
            async with aclosing(stream):
                async for chunk in stream:
                    yield chunk


def create_capture_model(params, settings_snapshot):
    """Instantiate the endpoint model without retaining credentials in capture state."""
    if not reasoning_capture_enabled(settings_snapshot):
        return ChatOpenAI(**params)
    model = ReasoningChatOpenAI(**params)
    if settings_snapshot and "app.debug" in settings_snapshot:
        model._debug_settings = {"app.debug": settings_snapshot["app.debug"]}
    return model
