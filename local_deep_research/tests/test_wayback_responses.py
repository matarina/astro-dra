"""Behavioral contracts for untrusted Wayback API responses.

Load the deployed overlay with network/base-class stubs; all response handling
and public entrypoint code is real. No upstream network calls or model judge.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
import re
import pytest
from research_verify.search_policy import engine_flag_enabled

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def api():
    class RateLimitError(Exception):
        pass

    class Base:
        @staticmethod
        def _scrub_error(exc):
            return type(exc).__name__

    noop = lambda *a, **k: None
    ns = dict(
        re=re, Any=Any, Dict=Dict, List=List, Optional=Optional, Tuple=Tuple,
        engine_flag_enabled=engine_flag_enabled,
        RateLimitError=RateLimitError, BaseSearchEngine=Base, BaseLLM=object,
        Sensitivity=SimpleNamespace(NON_SENSITIVE=1),
        Exposure=SimpleNamespace(EXPOSING=1),
        logger=SimpleNamespace(info=noop, warning=noop, exception=noop, debug=noop),
        redact_url_for_log=lambda _: "https://example.invalid",
        get_setting_from_snapshot=lambda *a, **k: True,
    )
    tree = ast.parse((ROOT / "local_deep_research/overlay/search_engine_wayback.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<wayback-overlay>", "exec"), ns)
    return ns


class Response:
    def __init__(self, data=None, status=200, mime="application/json", invalid=False):
        self.status_code = status
        self.headers = {"Content-Type": mime}
        self.data, self.invalid = data, invalid
        self.json_calls = 0

    def json(self):
        self.json_calls += 1
        if self.invalid:
            raise ValueError("synthetic-private-body")
        return self.data


HEADERS = ["timestamp", "original", "statuscode", "mimetype"]
CDX = [HEADERS, ["20240101000000", "https://example.invalid", "200", "text/html"]]


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_non_success_status_is_not_parsed_or_treated_as_empty(api, status):
    response = Response([], status=status, mime="text/html")
    with pytest.raises(api["WaybackResponseError"]) as caught:
        api["_validated_snapshot_response"](response, "cdx")
    assert caught.value.reason_code == "http_status"
    assert caught.value.status_code == status
    assert response.json_calls == 0


@pytest.mark.parametrize("mime", ["text/html; charset=utf-8", "application/xhtml+xml"])
def test_explicit_html_response_is_rejected_before_parsing(api, mime):
    response = Response(CDX, mime=mime)
    with pytest.raises(api["WaybackResponseError"], match="unexpected_content_type"):
        api["_validated_snapshot_response"](response, "cdx")
    assert response.json_calls == 0


@pytest.mark.parametrize("mime", ["application/json", "text/plain", ""])
def test_valid_cdx_json_preserves_legacy_plain_or_missing_content_type(api, mime):
    assert api["_validated_snapshot_response"](Response(CDX, mime=mime), "cdx") == CDX


def test_json_parse_error_does_not_expose_response_body(api):
    with pytest.raises(api["WaybackResponseError"]) as caught:
        api["_validated_snapshot_response"](Response(invalid=True), "cdx")
    assert caught.value.reason_code == "invalid_json"
    assert "synthetic-private-body" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("data", [
    None, {}, ["wrong header"], [["timestamp", "original"]],
    [HEADERS + ["original"]],
    [HEADERS, ["20240101000000"]],
    [HEADERS, [123, "https://example.invalid", "200", "text/html"]],
    [HEADERS, ["bad timestamp", "https://example.invalid", "200", "text/html"]],
    [HEADERS, ["20240101000000", None, "200", "text/html"]],
])
def test_malformed_cdx_structure_is_a_source_failure(api, data):
    with pytest.raises(api["WaybackResponseError"]):
        api["_validated_snapshot_response"](Response(data), "cdx")


@pytest.mark.parametrize("data", [
    None, [], {}, {"archived_snapshots": []},
    {"archived_snapshots": {"closest": 5}},
    {"archived_snapshots": {"closest": {"url": "https://example.invalid"}}},
])
def test_malformed_available_structure_is_a_source_failure(api, data):
    with pytest.raises(api["WaybackResponseError"]):
        api["_validated_snapshot_response"](Response(data), "closest")


@pytest.mark.parametrize("data,kind", [
    ([], "cdx"), ([HEADERS], "cdx"), ({"archived_snapshots": {}}, "closest"),
])
def test_valid_empty_responses_remain_successful_empty(api, data, kind):
    assert api["_validated_snapshot_response"](Response(data), kind) == data


def engine(api, response, closest=False):
    api["safe_get"] = lambda *a, **k: response
    obj = api["WaybackSearchEngine"].__new__(api["WaybackSearchEngine"])
    obj.closest_only = closest
    obj.max_snapshots_per_url = 3
    obj.available_api = "https://example.invalid/available"
    obj.cdx_api = "https://example.invalid/cdx"
    obj._get_full_content = lambda items: items
    return obj


def invoke(obj, route):
    if route == "closest":
        obj.closest_only = True
        return obj._get_wayback_snapshots("https://example.invalid")
    if route == "latest":
        return obj.get_latest_snapshot("https://example.invalid")
    if route == "date_range":
        return obj.search_by_date_range("https://example.invalid", "20200101", "20250101")
    return obj._get_wayback_snapshots("https://example.invalid")


@pytest.mark.parametrize("route", ["cdx", "closest", "latest", "date_range"])
@pytest.mark.parametrize("status", [429, 502])
def test_all_snapshot_entrypoints_propagate_failure_instead_of_empty(api, route, status):
    response = Response(status=status)
    expected = api["RateLimitError"] if status == 429 else api["WaybackResponseError"]
    with pytest.raises(expected):
        invoke(engine(api, response), route)
    assert response.json_calls == 0


def test_real_snapshot_formatting_still_works(api):
    rows = engine(api, Response(CDX))._get_wayback_snapshots("https://example.invalid")
    assert len(rows) == 1
    assert rows[0]["formatted_date"] == "2024-01-01 00:00:00"
    assert rows[0]["url"].endswith("/20240101000000/https://example.invalid")


def test_unavailable_closest_snapshot_does_not_become_a_preview(api):
    data = {"archived_snapshots": {"closest": {"available": False}}}
    assert engine(api, Response(data), closest=True)._get_wayback_snapshots("https://example.invalid") == []

def test_paused_duckduckgo_cannot_be_reached_indirectly_from_wayback(api):
    keys = []
    def paused(key, *a, **k):
        keys.append(key)
        return False
    api["get_setting_from_snapshot"] = paused
    obj = engine(api, Response())
    assert obj._extract_urls_from_query("synthetic natural language search") == []
    assert keys == ["search.engine.web.ddg.agent_enabled"]


def test_explicit_url_search_remains_available_when_duckduckgo_is_paused(api):
    api["get_setting_from_snapshot"] = lambda *a, **k: False
    obj = engine(api, Response())
    assert obj._extract_urls_from_query("https://example.invalid") == ["https://example.invalid"]
