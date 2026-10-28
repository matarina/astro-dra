"""Run inside the LDR image: verify the optional Qwen base-model backend."""

import json
import os
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage
from local_deep_research.config.llm_config import get_llm
from local_deep_research.config.thread_settings import settings_context
from local_deep_research.llm.providers.implementations.llamacpp import LlamaCppProvider


def main():
    endpoint = os.environ.get(
        "LDR_LLM_LLAMACPP_URL", "http://27.30.76.162:6183/ai/v1"
    )
    models = LlamaCppProvider.list_models_for_api(base_url=endpoint)
    assert models, "Qwen endpoint returned no models"
    model = next(m["value"] for m in models if "Qwen3.8-Flash-Next" in m["value"])
    snapshot = {
        "llm.provider": "llamacpp",
        "llm.model": model,
        "llm.llamacpp.url": endpoint,
        "llm.llamacpp.api_key": "",
        "llm.temperature": 0,
        "llm.max_tokens": 512,
        "policy.egress_scope": "public_only",
        "llm.require_local_endpoint": False,
        "embeddings.require_local": False,
        "search.tool": "pubmed",
    }
    context = SimpleNamespace(
        username=None, get_setting=lambda key, default=None: snapshot.get(key, default)
    )
    with settings_context(context):
        assert LlamaCppProvider.is_available(snapshot)
        llm = get_llm(
            provider="llamacpp", model_name=model, temperature=0,
            settings_snapshot=snapshot,
        )
        reply = llm.invoke("请只回复：连接成功。")
        assert reply.content and "连接成功" in reply.content, repr(reply.content)
        streamed = "".join(
            chunk.content for chunk in llm.stream("Reply with just: STREAM_OK")
            if isinstance(chunk.content, str)
        )
        assert "STREAM_OK" in streamed, repr(streamed)
        tool = {
            "type": "function",
            "function": {
                "name": "add_numbers",
                "description": "Add two integers. Use this for addition.",
                "parameters": {
                    "type": "object",
                    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
            },
        }
        bound = llm.bind_tools([tool])
        messages = [HumanMessage(content="Use add_numbers to calculate 2 plus 3.")]
        call = bound.invoke(messages)
        assert call.tool_calls, "Model did not return a structured tool call"
        chosen = call.tool_calls[0]
        assert chosen["name"] == "add_numbers" and chosen["args"] == {"a": 2, "b": 3}
        final = bound.invoke(messages + [
            call, ToolMessage(content="5", tool_call_id=chosen["id"])
        ])
        assert "5" in final.content, repr(final.content)
    print(json.dumps({
        "checks_passed": True,
        "endpoint": endpoint,
        "provider": "llamacpp",
        "model": model,
        "checks": ["model_discovery", "native_provider_available", "ldr_get_llm",
                   "chinese_completion", "streaming", "structured_tool_call", "tool_result_roundtrip"],
        "default_provider": os.environ.get("LDR_LLM_PROVIDER"),
        "default_model": os.environ.get("LDR_LLM_MODEL"),
        "scope": "Base-model integration smoke test; no full biomedical research run.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
