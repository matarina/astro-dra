"""Operator engine flags applied even to stale or partial research snapshots."""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping

_LOG = logging.getLogger(__name__)
_FLAGS = ("agent_enabled", "use_in_auto_search")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _operator_flag(engine: str, flag: str) -> bool | None:
    if flag not in _FLAGS:
        raise ValueError("Unsupported engine policy flag")
    key = f"LDR_SEARCH_ENGINE_WEB_{engine.upper()}_{flag.upper()}"
    value = os.environ.get(key)
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    # Invalid configuration must not silently restore an unavailable source.
    _LOG.warning("Invalid Boolean engine policy for %s; engine disabled", key)
    return False


def engine_flag_enabled(engine: str, flag: str, fallback=True) -> bool:
    override = _operator_flag(engine, flag)
    if override is not None:
        return override
    if isinstance(fallback, str):
        return fallback.strip().casefold() in _TRUE
    return bool(fallback)


def apply_operator_engine_flags(configs: Mapping) -> dict:
    """Return fresh configs so policy cannot contaminate a cached snapshot."""
    result = {}
    for engine, config in configs.items():
        updated = dict(config)
        for flag in _FLAGS:
            override = _operator_flag(engine, flag)
            if override is not None:
                updated[flag] = override
        result[engine] = updated
    return result
