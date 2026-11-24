"""Unit tests for requirement 1 -- DOI/PMID validation (respx-mocked HTTP)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from research_verify.config import VerifyConfig
from research_verify.doi_validator import (
    BADGE_INVALID,
    BADGE_MISMATCH,
    BADGE_UNVERIFIED,
    BADGE_VERIFIED,
    DoiValidator,
    badge_for,
)
from research_verify.http_client import HttpClient

REAL_DOI = "10.1038/s41586-020-2649-2"
CROSSREF_REAL = f"https://api.crossref.org/works/{REAL_DOI}"
PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _cosmetic_config() -> VerifyConfig:
    return VerifyConfig(http_max_retries=0)


@pytest.mark.asyncio
@respx.mock
async def test_real_doi_verified_with_matching_metadata():
    respx.get(CROSSREF_REAL).mock(
        return_value=httpx.Response(
            200,
            json={"message": {"DOI": REAL_DOI, "title": ["Array programming with NumPy"], "issued": {"date-parts": [[2020]]}}},
        )
    )
    src = {"index": "1", "doi": REAL_DOI, "title": "Array programming with NumPy", "year": 2020}
    async with HttpClient(_cosmetic_config()) as http:
        res = await DoiValidator(http).verify(src)
    assert res.verified is True
    assert res.source == "crossref"
    assert res.warnings == []
    assert badge_for(res) == BADGE_VERIFIED


@pytest.mark.asyncio
@respx.mock
async def test_crossref_registry_miss_is_not_global_identifier_absence():
    respx.get("https://api.crossref.org/works/10.9999/nope").mock(
        return_value=httpx.Response(404)
    )
    async with HttpClient(_cosmetic_config()) as http:
        res = await DoiValidator(http).verify({"index": "2", "doi": "10.9999/nope"})
    assert res.verified is None and res.lookup_status == "not_found_in_registry"
    assert badge_for(res) == BADGE_UNVERIFIED


@pytest.mark.asyncio
@respx.mock
async def test_title_mismatch_warns_but_still_verified():
    respx.get(CROSSREF_REAL).mock(
        return_value=httpx.Response(200, json={"message": {"DOI": REAL_DOI, "title": ["Something Else Entirely"]}})
    )
    src = {"index": "3", "doi": REAL_DOI, "title": "A totally different local title"}
    async with HttpClient(_cosmetic_config()) as http:
        res = await DoiValidator(http).verify(src)
    assert res.verified is True
    assert res.title_ok is False
    assert res.warnings
    assert badge_for(res) == BADGE_MISMATCH


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_degrades_to_unverified():
    respx.get(CROSSREF_REAL).mock(side_effect=httpx.ConnectError("down"))
    async with HttpClient(_cosmetic_config()) as http:
        res = await DoiValidator(http).verify({"index": "4", "doi": REAL_DOI})
    assert res.verified is None
    assert res.source == "unavailable"
    assert badge_for(res) == BADGE_UNVERIFIED


@pytest.mark.asyncio
@respx.mock
async def test_pmid_esummary_positive_and_negative():
    respx.get(PUBMED).mock(
        side_effect=[
            httpx.Response(200, json={"result": {"32561899": {"uid": "32561899", "title": "X"}}}),
            httpx.Response(200, json={"result": {"1234567": {"error": "cannot get document summary"}}}),
        ]
    )
    async with HttpClient(_cosmetic_config()) as http:
        v = DoiValidator(http)
        ok = await v.verify({"index": "5", "pmid": "32561899"})
        bad = await v.verify({"index": "6", "_pmid": "1234567"})
    assert ok.verified is True and ok.source == "pubmed"
    assert bad.verified is None and bad.lookup_status == "remote_error"


@pytest.mark.asyncio
@respx.mock
async def test_verify_many_indexes_results_and_survives_one_failure():
    respx.get(CROSSREF_REAL).mock(return_value=httpx.Response(200, json={"message": {"DOI": REAL_DOI, "title": ["T"]}}))
    respx.get("https://api.crossref.org/works/10.9999/bad").mock(return_value=httpx.Response(404))
    sources = [
        {"index": "1", "doi": REAL_DOI, "title": "T"},
        {"index": "2", "doi": "10.9999/bad"},
        {"no_index": True, "doi": REAL_DOI},  # skipped
    ]
    async with HttpClient(_cosmetic_config()) as http:
        out = await DoiValidator(http).verify_many(sources)
    assert set(out) == {1, 2}
    assert out[1].verified is True and out[2].verified is None


@pytest.mark.asyncio
async def test_verify_many_retains_completed_checks_on_timeout(monkeypatch):
    validator = DoiValidator(HttpClient(_cosmetic_config()))
    cancelled = asyncio.Event()
    result = object()

    async def verify(source):
        if source["index"] == 1:
            return result
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(validator, "verify", verify)
    assert await validator.verify_many([{"index": 1}, {"index": 2}], timeout=0.02) == {1: result}
    assert cancelled.is_set()


@pytest.mark.asyncio
@respx.mock
async def test_link_only_source_is_unverified_not_claimed():
    async with HttpClient(_cosmetic_config()) as http:
        res = await DoiValidator(http).verify(
            {"index": "7", "link": "https://pubmed.ncbi.nlm.nih.gov/123/"}
        )
    assert res.verified is None
    assert res.source == "link"
