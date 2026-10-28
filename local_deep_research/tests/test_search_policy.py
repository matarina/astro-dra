"""Disabled engine policy must win over stale snapshots and remain reversible."""
import pytest
from research_verify.search_policy import apply_operator_engine_flags, engine_flag_enabled


@pytest.fixture(autouse=True)
def clear_operator_flags(monkeypatch):
    for name in ("arxiv", "semantic_scholar", "brave", "ddg", "pubmed"):
        for flag in ("agent_enabled", "use_in_auto_search"):
            monkeypatch.delenv(f"LDR_SEARCH_ENGINE_WEB_{name.upper()}_{flag.upper()}", raising=False)


@pytest.mark.parametrize("name", ["arxiv", "semantic_scholar", "brave", "ddg"])
@pytest.mark.parametrize("flag", ["agent_enabled", "use_in_auto_search"])
@pytest.mark.parametrize("value,expected", [("false", False), ("true", True)])
def test_operator_policy_wins_over_stale_config_and_can_be_restored(monkeypatch, name, flag, value, expected):
    original = {name: {flag: not expected, "default_params": {"max_results": 10}}}
    monkeypatch.setenv(f"LDR_SEARCH_ENGINE_WEB_{name.upper()}_{flag.upper()}", value)
    current = apply_operator_engine_flags(original)
    assert current[name][flag] is expected
    assert original[name][flag] is not expected
    assert current[name]["default_params"] == {"max_results": 10}


def test_absent_operator_override_preserves_source_policy():
    original = {"pubmed": {"agent_enabled": True, "use_in_auto_search": False}}
    assert apply_operator_engine_flags(original) == original


def test_unregistered_indirect_ddg_call_still_obeys_operator_pause(monkeypatch):
    monkeypatch.setenv("LDR_SEARCH_ENGINE_WEB_DDG_AGENT_ENABLED", "false")
    assert not engine_flag_enabled("ddg", "agent_enabled", fallback=True)


def test_invalid_operator_value_does_not_enable_source_or_log_raw_value(monkeypatch, caplog):
    monkeypatch.setenv("LDR_SEARCH_ENGINE_WEB_ARXIV_AGENT_ENABLED", "synthetic-private-marker")
    assert not engine_flag_enabled("arxiv", "agent_enabled", fallback=True)
    assert "synthetic-private-marker" not in caplog.text
    assert "engine disabled" in caplog.text


def test_string_false_from_legacy_snapshot_is_not_truthy():
    assert not engine_flag_enabled("pubmed", "agent_enabled", fallback="false")
