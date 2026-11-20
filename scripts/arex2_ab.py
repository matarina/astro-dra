#!/usr/bin/env python3
"""Run a controlled AREX-2 writer/extractor A/B without changing LDR defaults.

The production LDR path expects an OpenAI-compatible endpoint and tool-call
semantics.  AREX-2 is a local Transformers model, so this runner evaluates it
against a frozen prompt/source packet first.  It never performs web search and
never edits Compose settings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time


DEFAULT_MODEL = Path("/data1/maxw/models/AREX-2")
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=([^>]+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)
_TOOL_PARAMETER_RE = re.compile(
    r"<parameter=([^>]+)>(.*?)</parameter>", re.DOTALL
)


def inspect_model(model_dir: Path) -> dict:
    config_path = model_dir / "config.json"
    index_path = model_dir / "model.safetensors.index.json"
    result = {
        "model_dir": str(model_dir),
        "exists": model_dir.is_dir(),
        "config_exists": config_path.is_file(),
        "index_exists": index_path.is_file(),
        "safetensor_shards": len(list(model_dir.glob("*.safetensors"))),
        "transformers_available": False,
        "torch_available": False,
        "compatible_runtime": False,
    }
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text())
            result.update({
                "architecture": config.get("architectures"),
                "model_type": config.get("model_type"),
                "context_length": (config.get("text_config") or {}).get("max_position_embeddings"),
                "transformers_version_declared": config.get("transformers_version"),
                "dtype": config.get("dtype"),
            })
        except (OSError, ValueError) as exc:
            result["config_error"] = type(exc).__name__
    try:
        import torch  # noqa: F401
        result["torch_available"] = True
    except Exception:
        pass
    try:
        import transformers  # noqa: F401
        result["transformers_available"] = True
    except Exception:
        pass
    result["compatible_runtime"] = bool(
        result["exists"] and result["config_exists"] and result["index_exists"]
        and result["torch_available"] and result["transformers_available"]
    )
    return result


def run_local(model_dir: Path, prompt: str, max_new_tokens: int, tools=None) -> str:
    try:
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor
    except ImportError as exc:
        raise RuntimeError("AREX-2 requires torch and a recent Transformers release") from exc
    processor = AutoProcessor.from_pretrained(str(model_dir))
    model = AutoModelForMultimodalLM.from_pretrained(
        str(model_dir), dtype=torch.bfloat16, device_map="auto"
    )
    messages = [{"role": "user", "content": prompt}]
    template_kwargs = {"enable_thinking": False}
    if tools:
        template_kwargs["tools"] = tools
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt", **template_kwargs,
    ).to(model.device)
    with torch.inference_mode():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
    generated = outputs[0][inputs["input_ids"].shape[-1]:]
    return processor.decode(generated, skip_special_tokens=True)


def extract_raw_tool_calls(text: str) -> list[dict]:
    """Parse AREX's XML-like smoke format without executing a tool."""
    calls = []
    for function, body in _TOOL_CALL_RE.findall(text or ""):
        parameters = {
            name.strip(): value.strip()
            for name, value in _TOOL_PARAMETER_RE.findall(body)
        }
        calls.append({"name": function.strip(), "arguments": parameters})
    return calls


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--prompt")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tools-file", type=Path,
                        help="JSON array of OpenAI-style tool definitions for a raw tool-call smoke test")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--run", action="store_true", help="load the 27B model and generate")
    args = parser.parse_args(argv)
    info = inspect_model(args.model_dir)
    if not args.run:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0 if info["exists"] else 2
    prompt = args.prompt
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt:
        parser.error("--run requires --prompt or --prompt-file")
    if not info["compatible_runtime"]:
        print(json.dumps({"status": "not_run", "reason": "missing_torch_or_transformers", **info}, ensure_ascii=False))
        return 3
    started = time.time()
    tools = None
    if args.tools_file:
        tools = json.loads(args.tools_file.read_text(encoding="utf-8"))
        if not isinstance(tools, list):
            raise ValueError("--tools-file must contain a JSON array")
    text = run_local(args.model_dir, prompt, args.max_new_tokens, tools=tools)
    tool_calls = extract_raw_tool_calls(text)
    canonical_calls = {
        json.dumps(call, ensure_ascii=False, sort_keys=True)
        for call in tool_calls
    }
    payload = {
        "model": str(args.model_dir),
        "elapsed_seconds": round(time.time() - started, 3),
        "output": text,
        "tools_supplied": len(tools or []),
        "tool_calls_detected": tool_calls,
        "duplicate_tool_calls": max(0, len(tool_calls) - len(canonical_calls)),
        "think_markers_present": "<think>" in text or "</think>" in text,
    }
    if args.output:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

