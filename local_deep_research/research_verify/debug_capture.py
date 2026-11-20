"""Opt-in capture of observable chat-completion request and response data.

This module is for controlled diagnostics.  It records the complete request
payload and raw JSON response when a caller supplies a capture directory.  If a
provider returns fields such as ``reasoning_content`` or ``thinking``, those
fields are preserved in the raw response and indexed in the receipt.  Hidden
chain-of-thought that the provider does not return cannot be recovered by this
client.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any
import uuid


_THINKING_KEYS = frozenset({
    "analysis", "reasoning", "reasoning_content", "thinking", "thoughts",
})


def _sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def _thinking_fields(value: Any, path: str = "") -> dict[str, Any]:
    found: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else key
            if key.casefold() in _THINKING_KEYS:
                found[child_path] = item
            found.update(_thinking_fields(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_thinking_fields(item, f"{path}[{index}]"))
    return found


def _capture_directory(root: str | Path, *, arm: str | None, case_id: str | None) -> Path:
    path = Path(root)
    if arm:
        path /= arm
    if case_id:
        path /= case_id
    path /= uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o700)
    return path


def capture_chat_completion(
    session: Any,
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout: tuple[float, float] | float = (15, 900),
    capture_dir: str | Path | None = None,
    arm: str | None = None,
    case_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """POST one chat completion and optionally write a complete diagnostic receipt.

    The returned receipt is safe to serialize and includes request/response
    hashes, timing, status, usage, finish reason, visible content, and any
    provider-returned thinking fields.  The raw response bytes and parsed JSON
    are written only when ``capture_dir`` is explicitly provided.
    """
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    request_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
    receipt: dict[str, Any] = {
        "schema_version": "astro_dra_debug_capture.v1",
        "started_utc": started_utc,
        "endpoint": endpoint,
        "request_sha256": _sha256(request_bytes),
        "request_bytes": len(request_bytes),
    }
    capture_path = _capture_directory(capture_dir, arm=arm, case_id=case_id) if capture_dir else None
    if capture_path:
        _write_json(capture_path / "request.json", payload)
    try:
        response = session.post(endpoint, json=payload, timeout=timeout)
        raw_bytes = bytes(getattr(response, "content", b""))
        receipt.update({
            "status": "received",
            "status_code": getattr(response, "status_code", None),
            "response_sha256": _sha256(raw_bytes),
            "response_bytes": len(raw_bytes),
        })
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("chat completion response is not a JSON object")
        choices = data.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        visible_content = message.get("content") or ""
        receipt.update({
            "status": "completed",
            "provider_model": data.get("model"),
            "usage": data.get("usage"),
            "finish_reason": choice.get("finish_reason"),
            "visible_output": visible_content,
            "visible_output_chars": len(visible_content) if isinstance(visible_content, str) else None,
            "thinking_fields": _thinking_fields(data),
        })
        if capture_path:
            (capture_path / "response.raw").write_bytes(raw_bytes)
            (capture_path / "response.raw").chmod(0o600)
            _write_json(capture_path / "response.json", data)
    except Exception as exc:
        receipt.update({"status": "failed", "error_type": type(exc).__name__,
                       "error": str(exc)[:2000]})
        if capture_path:
            raw_bytes = locals().get("raw_bytes", b"")
            (capture_path / "response.raw").write_bytes(raw_bytes)
            (capture_path / "response.raw").chmod(0o600)
    receipt["elapsed_s"] = round(time.monotonic() - started, 3)
    if capture_path:
        receipt["capture_dir"] = str(capture_path)
        _write_json(capture_path / "receipt.json", receipt)
    if receipt["status"] != "completed":
        raise RuntimeError(receipt.get("error", "chat completion failed"))
    return data, receipt


__all__ = ["capture_chat_completion"]
