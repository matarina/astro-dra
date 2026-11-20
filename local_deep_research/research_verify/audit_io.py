"""Small, private audit-file helpers for provenance and evidence snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit

from .source_identity import canonical_url, classify_source


def _safe_url(value):
    try:
        parts = urlsplit(str(value or ""))
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        if parts.username or parts.password:
            return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return ""


def _source_for_audit(source):
    if not isinstance(source, dict):
        return {"source_type": type(source).__name__}
    normalized = classify_source(source)
    result = {}
    # Keep metadata and provenance, while excluding transient private fields.
    for key, value in normalized.items():
        if key.startswith("_") and key not in {"_verify", "_constraint", "_keyword_cov"}:
            continue
        if key in {"content", "full_content", "body", "fetched_content"}:
            if isinstance(value, str):
                result[key + "_chars"] = len(value)
                result[key + "_sha256"] = hashlib.sha256(value.encode()).hexdigest()
            continue
        if key in {"link", "url"}:
            safe = _safe_url(value)
            if safe:
                result[key] = safe
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            result[key] = str(value)
        else:
            result[key] = value
    result["canonical_url"] = canonical_url(result.get("link") or result.get("url"))
    try:
        from .evidence_cards import build_source_card
        result["evidence_card"] = build_source_card(source)
    except Exception:
        result["evidence_card_status"] = "unavailable"
    return result


def publication_sources(sources) -> list[dict]:
    """Return JSON-safe publication metadata with formal/unverified status."""
    output = []
    for source in sources or []:
        if isinstance(source, dict):
            output.append(_source_for_audit(source))
    return output


def write_audit(audit: dict | None, sources=None, *, prefix="citation_qc") -> str:
    """Atomically write a private JSON audit under ``LDR_DATA_DIR/logs``."""
    root = Path(os.environ.get("LDR_DATA_DIR", "/data"))
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    payload = dict(audit or {})
    if sources is not None:
        payload["sources"] = publication_sources(sources)
    payload.setdefault("written_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("schema_version", "provenance-audit-1")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{prefix}_{stamp}_{os.getpid()}.json"
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return str(target)

