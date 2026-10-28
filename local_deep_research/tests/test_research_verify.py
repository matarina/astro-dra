"""Skeleton unit tests for the ``research_verify`` baseline.

Dependencies (not shipped in the runtime image; install on demand)::

    pip install pytest pytest-asyncio respx

Run from the hot-patch directory (``nh/local_deep_research``)::

    pytest -q tests/test_research_verify.py

The tests cover the §0.1 baseline only: configuration switches and the shared
HTTP client's ok / not-found / transport-error semantics (the three states the
whole verification chain depends on).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from research_verify import HttpClient, HttpResult, VerifyConfig
from research_verify.config import get_config


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
def test_default_audit_is_enabled_without_automatic_selection_constraints():
    cfg = VerifyConfig()
    assert cfg.enable_verify is True
    assert cfg.module_enabled("doi_validation") is True
    assert cfg.module_enabled("constraint_match") is False
    assert cfg.module_enabled("keyword_coverage") is False
    assert cfg.module_enabled("citation_qc") is True


def test_master_switch_disables_all(monkeypatch):
    monkeypatch.setenv("LDR_VERIFY_ENABLE_VERIFY", "false")
    cfg = VerifyConfig()
    assert cfg.module_enabled("doi_validation") is False
    assert cfg.module_enabled("citation_qc") is False


def test_module_switch_is_independent(monkeypatch):
    monkeypatch.setenv("LDR_VERIFY_ENABLE_KEYWORD_COVERAGE", "false")
    cfg = VerifyConfig()
    assert cfg.module_enabled("keyword_coverage") is False
    assert cfg.module_enabled("doi_validation") is True


def test_env_overrides_thresholds(monkeypatch):
    monkeypatch.setenv("LDR_VERIFY_MIN_KEYWORD_HITS", "4")
    monkeypatch.setenv("LDR_VERIFY_HTTP_CONCURRENCY", "3")
    cfg = VerifyConfig()
    assert cfg.min_keyword_hits == 4
    assert cfg.http_concurrency == 3


def test_get_config_is_cached():
    assert get_config() is get_config()


# --------------------------------------------------------------------------- #
# shared HTTP client: the three states the chain relies on
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@respx.mock
async def test_get_ok_returns_json():
    respx.get("https://example.test/ok").mock(
        return_value=httpx.Response(200, json={"a": 1}, headers={"content-type": "application/json"})
    )
    async with HttpClient(VerifyConfig()) as http:
        res = await http.get("https://example.test/ok")
    assert isinstance(res, HttpResult)
    assert res.ok and not res.not_found and not res.transport_error
    assert res.json == {"a": 1}


@pytest.mark.asyncio
@respx.mock
async def test_get_404_is_not_found():
    respx.get("https://example.test/missing").mock(return_value=httpx.Response(404))
    async with HttpClient(VerifyConfig()) as http:
        res = await http.get("https://example.test/missing")
    assert res.not_found
    assert not res.ok
    assert not res.transport_error


@pytest.mark.asyncio
@respx.mock
async def test_get_transport_error_is_unverified_not_crash():
    respx.get("https://example.test/down").mock(side_effect=httpx.ConnectError("boom"))
    cfg = VerifyConfig(http_max_retries=0)
    async with HttpClient(cfg) as http:
        res = await http.get("https://example.test/down")
    assert res.transport_error
    assert not res.ok
    assert res.status is None
