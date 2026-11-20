"""Private, opt-in evidence snapshots. Recording never decides report content."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

from loguru import logger

_research_id = ContextVar("synthesis_trace_research_id", default=None)
_SENSITIVE = re.compile(r"api[_-]?key|password|secret|authorization|credential|access[_-]?token", re.I)
_SOURCE_FIELDS = ("index", "title", "link", "url", "doi", "pmid", "pmcid", "journal",
                  "journal_ref", "pubdate", "publication_date", "year", "authors",
                  "language", "languages", "lang", "platform", "technology",
                  "population", "sample_size", "groups", "outcome",
                  "impact_factor", "impact_factor_value", "journal_impact_factor", "jif",
                  "impact_factor_provenance", "jif_provenance",
                  "_jcr_check", "jcr_provenance", "jcr_check_status",
                  "metric_year", "passes_threshold",
                  "abstract", "snippet", "content", "body", "full_content",
                  "fetched_content", "content_type", "evidence_type", "engine", "source_engine",
                  "related_articles", "publication_types", "publication_versions",
                  "version_resolution", "authority_status")


def text_digest(text):
    return sha256(str(text).encode("utf-8")).hexdigest()


def source_snapshot(sources):
    """Explicit allowlist: no settings, HTTP headers, or connection objects."""
    if not isinstance(sources, (list, tuple)):
        return []
    return [{key: source[key] for key in _SOURCE_FIELDS if key in source}
            for source in sources if isinstance(source, dict)]


def source_ids(text):
    registry = getattr(text, 'views', None)
    if isinstance(registry, dict) and registry:
        return sorted(int(index) for index in registry)
    return [int(n) for n in re.findall(r"^\[(\d+)\]\nTitle:", text, re.M)]


def message_snapshot(messages):
    result = []
    for message in messages:
        if isinstance(message, dict):
            result.append({key: message[key] for key in ("role", "content", "tool_calls", "tool_call_id") if key in message})
        else:
            result.append({"role": getattr(message, "type", "unknown"),
                           "content": getattr(message, "content", None),
                           "tool_calls": getattr(message, "tool_calls", []),
                           "tool_call_id": getattr(message, "tool_call_id", None)})
    return result


def record_tool_results(messages):
    with start_trace("tool_results") as trace:
        if trace:
            trace.record("tool_messages", {"messages": message_snapshot(messages)})


@contextmanager
def trace_context(research_id):
    """For programmatic callers; web workers already carry a research context."""
    token = _research_id.set(str(research_id))
    try:
        yield
    finally:
        _research_id.reset(token)


def _current_id():
    value = _research_id.get()
    if value:
        return value
    try:
        from local_deep_research.utilities.thread_context import get_search_context
        context = get_search_context() or {}
        return context.get("research_id")  # Never serialize the context/password.
    except (ImportError, RuntimeError):
        return None


class DisabledTrace:
    def __bool__(self):
        return False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def record(self, *_, **__):
        return None


DISABLED = DisabledTrace()


class SynthesisTrace:
    def __init__(self, research_id, kind):
        # UUIDs remain readable; all other identifiers are hashed, never paths.
        value = str(research_id)
        self.research_id = value if re.fullmatch(r"[A-Za-z0-9-]{1,80}", value) else text_digest(value)[:32]
        self.trace_id = uuid4().hex
        root = Path(os.environ.get("LDR_RESEARCH_TRACE_DIR") or
                    str(Path(os.environ.get("LDR_DATA_DIR", "/data")) / "research_traces"))
        kind = re.sub(r"[^a-zA-Z0-9_-]", "_", kind)[:40]
        self.path = root / self.research_id / (kind + "-" + self.trace_id)
        for directory in (root, root / self.research_id, self.path):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Trace directory must be a real directory")
            directory.chmod(0o700)
        self.secrets = [v for k, v in os.environ.items() if _SENSITIVE.search(k) and len(v) >= 8]
        self.lock = threading.Lock()
        self.sequence = self.used = 0
        self.limit = max(1024, int(os.environ.get("LDR_RESEARCH_TRACE_MAX_BYTES", 64 * 1024 * 1024)))
        self.started = time.monotonic()
        self.record("start", {"kind": kind, "research_id": self.research_id,
                              "trace_id": self.trace_id, "schema_version": 1})

    def __bool__(self):
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.record("finish", {"status": "failed" if exc_type else "completed",
                               "error_type": exc_type.__name__ if exc_type else None})
        return False

    def _clean(self, value):
        if isinstance(value, dict):
            return {str(k): "<REDACTED>" if _SENSITIVE.search(str(k)) else self._clean(v)
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "<REDACTED>")
            value = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "<REDACTED>", value)
            value = re.sub(r"(?i)(bearer\s+|api[_-]?key=|access_token=)[^\s&\"']+", r"\1<REDACTED>", value)
            value = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1<REDACTED>@", value)
            return value
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return "<unsupported value>"  # Avoid repr() of credential-bearing objects.

    def record(self, stage, data):
        """Write compressed JSON; index only closed artifacts, never block research."""
        try:
            safe = self._clean(data)
            raw = json.dumps(safe, ensure_ascii=False, allow_nan=False).encode("utf-8")
            stage = re.sub(r"[^a-zA-Z0-9_-]", "_", stage)[:80]
            with self.lock:
                self.sequence += 1
                elapsed = round(time.monotonic() - self.started, 3)
                row = {"sequence": self.sequence, "stage": stage,
                       "at": datetime.now(timezone.utc).isoformat(), "elapsed_s": elapsed,
                       "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                # Never truncate evidence and mislabel it as a complete prompt.
                if len(raw) > min(self.limit // 2, 16 * 1024 * 1024) or self.used + len(raw) > self.limit:
                    row["status"] = "omitted_size_limit"
                else:
                    name = f"{self.sequence:04d}-{stage}.json.gz"
                    fd = os.open(self.path / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(gzip.compress(raw, mtime=0))
                    self.used += len(raw)
                    row.update(status="recorded", file=name)
                event_fd = os.open(self.path / "events.jsonl", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                with os.fdopen(event_fd, "a") as handle:
                    handle.write(json.dumps(row) + "\n")
            logger.info("[SYNTHESIS_TRACE] research={} trace={} stage={} status={} elapsed={}s",
                        self.research_id, self.trace_id, stage, row["status"], elapsed)
            return row
        except Exception as exc:
            logger.warning("[SYNTHESIS_TRACE] recording unavailable ({})", type(exc).__name__)
            return None


def start_trace(kind, research_id=None):
    if os.environ.get("LDR_RESEARCH_TRACE_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return DISABLED
    try:
        identifier = research_id or _current_id()
        if not identifier:
            return DISABLED
        return SynthesisTrace(identifier, kind)
    except Exception as exc:
        logger.warning("[SYNTHESIS_TRACE] initialization unavailable ({})", type(exc).__name__)
        return DISABLED


def record_model_response(trace, stage, response, text, **flags):
    if trace:
        try:
            meta = getattr(response, "response_metadata", {}) or {}
            trace.record(stage + "_response", {
                "raw_content": response if isinstance(response, str) else getattr(response, "content", None),
                "text_used": text, "text_sha256": text_digest(text),
                "model_metadata": {k: meta[k] for k in ("model_name", "model", "finish_reason", "token_usage") if k in meta},
                **flags,
            })
        except Exception as exc:
            logger.warning("[SYNTHESIS_TRACE] response recording unavailable ({})", type(exc).__name__)


def consistency_prompt(question, draft, sources):
    return f"""Analyze these sources for factual consistency.
Check the working draft against its cited source text to help answer the question.
Question:
{question}

Check cited statements together with their headings and table categories. Keep
each study's technique, input data and analysis task associated with the correct
source. A paper using several assays does not make every result a result of each
assay. Check what numbers count, their units, and independent versus repeated
measurements; preserve uncertainty and scope. Distinguish actual contradictions
from different populations, experiments or data modalities.
Use only the supplied evidence. Missing details in an abstract or excerpt mean
not established by this material, not that the full paper lacks them. Do not
infer sample sizes or methods that the supplied text does not establish.
Return concise, actionable issues: the draft statement or heading, its [N]
source, the supporting source phrase if available, and what needs correction or
clarification. Identify major source conflicts and basic factual errors too.
Do not rewrite the report or declare it verified. This review concerns the
working draft; a later writer may still introduce new errors.

Working draft:
{draft}

Supplied sources:
{sources}
"""
