"""Private, request-scoped capture of text returned in provider reasoning channels."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from loguru import logger

from .synthesis_trace import _current_id, _SENSITIVE, text_digest
from .model_call_context import current_model_call, current_model_trace


_REASONING_KEYS = ("reasoning_content", "reasoning", "thinking", "analysis", "thoughts", "reasoning_details")
_TEXT_KEYS = (*_REASONING_KEYS, "text", "content", "summary", "delta")
_REASONING_TYPES = {"thinking", "analysis", "reasoning", "reasoning_text", "reasoning.text",
                    "reasoning.summary", "thinking_delta", "summary_text"}
_TAG = re.compile(r"<(think|thinking|analysis|reasoning)>", re.I)
_OPEN_TAGS = ("<think>", "<thinking>", "<analysis>", "<reasoning>")


def _on(value):
    if isinstance(value, dict):
        value = value.get("value")
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def reasoning_capture_enabled(settings=None):
    for name in ("LDR_REASONING_CAPTURE", "LDR_APP_DEBUG"):
        if name in os.environ:
            return _on(os.environ[name])
    return _on((settings or {}).get("app.debug"))


def _now():
    return datetime.now(timezone.utc).isoformat()


class _InlineReasoning:
    """Keep tag state, including a tag cut across two deltas."""
    def __init__(self, fields, prefix):
        self.fields = fields
        self.prefix = prefix
        self.tag = None
        self.pending = ""

    def feed(self, text):
        text = self.pending + text
        self.pending = ""
        while text:
            closing = f"</{self.tag}>" if self.tag else None
            if closing:
                closed = re.search(closing, text, re.I)
                if closed:
                    self.fields[self.prefix + self.tag].append(text[:closed.start()])
                    text = text[closed.end():]
                    self.tag = None
                    continue
            else:
                opened = _TAG.search(text)
                if opened:
                    self.tag = opened.group(1).lower()
                    self.fields.setdefault(self.prefix + self.tag, [])
                    text = text[opened.end():]
                    continue
            start = text.rfind("<")
            markers = (closing,) if closing else _OPEN_TAGS
            if start >= 0 and any(marker.startswith(text[start:].lower()) for marker in markers):
                self.pending, text = text[start:], text[:start]
            if self.tag:
                self.fields[self.prefix + self.tag].append(text)
            return

    def finish(self):
        if self.tag and self.pending:
            self.fields[self.prefix + self.tag].append(self.pending)
        return self.tag is not None


def _extract_text(value, path, fields):
    # Walk only text within an explicit reasoning field. Tool arguments,
    # signatures, ciphertext and arbitrary fields are never traversed.
    if isinstance(value, str):
        fields.setdefault(path, []).append(value)
    elif isinstance(value, list):
        for position, block in enumerate(value):
            index = block.get("index", position) if isinstance(block, dict) else position
            if type(index) is not int:
                index = position
            _extract_text(block, f"{path}[{index}]", fields)
    elif isinstance(value, dict):
        for key in _TEXT_KEYS:
            if key in value:
                _extract_text(value[key], f"{path}.{key}", fields)


class _Choice:
    def __init__(self):
        self.fields = {}
        self.inline = {}
        self.finish_reason = None

    def observe(self, part):
        for key in _REASONING_KEYS:
            if key in part:
                _extract_text(part[key], key, self.fields)
        content = part.get("content")
        if isinstance(content, str):
            self.feed_inline("content", content)
        if isinstance(content, list):
            for position, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                index = block.get("index", position)
                path = f"content[{index if type(index) is int else position}]"
                kind = block.get("type")
                if isinstance(kind, str) and kind in _REASONING_TYPES:
                    _extract_text(block, path, self.fields)
                elif kind in ("text", "output_text") and isinstance(block.get("text"), str):
                    self.feed_inline(path + ".text", block["text"])

    def feed_inline(self, path, text):
        if path not in self.inline:
            self.inline[path] = _InlineReasoning(self.fields, path + ".")
        self.inline[path].feed(text)


class ReasoningCapture:
    def __init__(self, root, research_id):
        self.call_id = uuid4().hex
        self.research_id = research_id
        self.stage, self.synthesis_trace_id = current_model_call()
        self.started_at = _now()
        self.provider_id = self.model = None
        self.choices = {}
        self.observation_errors = 0
        self.finished = False
        self.path = root / research_id / "model-reasoning" / (self.call_id + ".json.gz")
        for directory in (root, self.path.parent.parent, self.path.parent):
            directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Expected a private trace directory")
            if directory != root:
                directory.chmod(0o700)
        trace = current_model_trace()
        if trace:
            try:
                trace.record("provider_reasoning_call", {
                    "call_id": self.call_id, "stage": self.stage,
                    "receipt": "model-reasoning/" + self.path.name,
                })
            except Exception as error:
                logger.warning("[MODEL_REASONING] trace link unavailable ({})", type(error).__name__)

    def observe(self, payload):
        """Consume one provider message or delta. The adapter still owns the original object."""
        if self.finished:
            return
        try:
            if not isinstance(payload, dict):
                payload = payload.model_dump()
            if not isinstance(payload, dict):
                return
            if isinstance(payload.get("id"), str):
                self.provider_id = payload["id"]
            if isinstance(payload.get("model"), str):
                self.model = payload["model"]
            for position, item in enumerate(payload.get("choices") or ()):
                if not isinstance(item, dict):
                    continue
                index = item.get("index", position)
                if type(index) is not int:
                    continue
                if index not in self.choices:
                    self.choices[index] = _Choice()
                choice = self.choices[index]
                if isinstance(item.get("finish_reason"), str):
                    choice.finish_reason = item["finish_reason"]
                part = item.get("delta") if "delta" in item else item.get("message")
                if isinstance(part, dict):
                    choice.observe(part)
        except Exception as error:
            self.observation_errors += 1
            logger.warning("[MODEL_REASONING] capture {} observation failed ({})", self.call_id, type(error).__name__)

    def finish(self, status="completed"):
        """Publish one complete private file, including receipts for empty and interrupted calls."""
        if self.finished:
            return
        self.finished = True
        tmp_path = None
        try:
            secrets = [v for k, v in os.environ.items() if _SENSITIVE.search(k) and len(v) >= 8]
            rows = []
            present = False
            for index, choice in sorted(self.choices.items()):
                unterminated = [path for path, parser in choice.inline.items() if parser.finish()]
                fields = {}
                for path, pieces in choice.fields.items():
                    text = "".join(pieces)
                    for secret in secrets:
                        text = text.replace(secret, "<REDACTED>")
                    text = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "<REDACTED>", text)
                    text = re.sub(r"(?i)(bearer\s+|api[_-]?key=|access_token=)[^\s&\"']+", r"\1<REDACTED>", text)
                    fields[path] = text
                present |= any(fields.values())
                rows.append({"index": index, "finish_reason": choice.finish_reason,
                             "reasoning_fields": fields, "unterminated_inline": unterminated})
            receipt = {"schema_version": 1, "call_id": self.call_id, "research_id": self.research_id,
                       "stage": self.stage, "synthesis_trace_id": self.synthesis_trace_id,
                       "provider_response_id": self.provider_id, "model": self.model,
                       "started_at": self.started_at, "finished_at": _now(), "status": status,
                       "reasoning_present": present, "observation_errors": self.observation_errors, "choices": rows}
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as handle:
                tmp_path = Path(handle.name)
                with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as archive:
                    archive.write(json.dumps(receipt, ensure_ascii=False).encode("utf-8"))
            os.replace(tmp_path, self.path)
        except Exception as error:
            logger.warning("[MODEL_REASONING] capture {} save failed ({})", self.call_id, type(error).__name__)
        finally:
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("[MODEL_REASONING] temporary capture cleanup failed")
            self.choices.clear()


def begin_reasoning_capture(settings_snapshot=None):
    """Called at invocation time, after the caller has entered its research context."""
    try:
        if not reasoning_capture_enabled(settings_snapshot):
            return None
        research_id = _current_id()
        if not research_id:
            return None
        value = str(research_id)
        safe_id = value if re.fullmatch(r"[A-Za-z0-9-]{1,80}", value) else text_digest(value)[:32]
        root = Path(os.environ.get("LDR_RESEARCH_TRACE_DIR") or
                    Path(os.environ.get("LDR_DATA_DIR", "/data")) / "research_traces")
        return ReasoningCapture(root, safe_id)
    except Exception as error:
        logger.warning("[MODEL_REASONING] initialization failed ({})", type(error).__name__)
        return None
