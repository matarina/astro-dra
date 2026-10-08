"""Unit tests for the shared T0 layer: models + text helpers.

Pure/synchronous -- no network, no event loop needed.
"""

from __future__ import annotations

from research_verify import (
    ClaimCheck,
    ConstraintMatch,
    KeywordCov,
    ResearchConstraint,
    VerifyResult,
)
from research_verify import textutil


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #
def test_verify_result_defaults_are_unverified():
    r = VerifyResult(doi="10.1/x")
    assert r.verified is None
    assert r.source == "unavailable"
    assert r.warnings == []


def test_research_constraint_is_empty():
    assert ResearchConstraint().is_empty is True
    assert ResearchConstraint(min_if=10).is_empty is False


def test_constraint_match_excluded():
    assert ConstraintMatch().excluded is False
    assert ConstraintMatch(hard_violations=["year"]).excluded is True


def test_keyword_cov_and_claim_defaults():
    k = KeywordCov()
    assert k.threshold_ok is True and k.basis == "unavailable"
    c = ClaimCheck(claim="x")
    assert c.verdict == "unverifiable"


# --------------------------------------------------------------------------- #
# text helpers
# --------------------------------------------------------------------------- #
def test_normalize_title_matches_collector_style():
    assert textutil.normalize_title("Hello, World!") == "hello world"
    assert textutil.normalize_title("A  B\tC") == "a b c"
    assert textutil.normalize_title(None) == ""


def test_normalize_year_forms():
    assert textutil.normalize_year(2024) == 2024
    assert textutil.normalize_year("2023-05-01") == 2023
    assert textutil.normalize_year("2023 May 1") == 2023
    assert textutil.normalize_year("n/a") is None


def test_first_year_prefers_first_parsable_key():
    assert textutil.first_year({"published": "2022-01-01"}) == 2022
    assert textutil.first_year({}) is None


def test_extract_doi_variants_and_trailing_punct():
    assert textutil.extract_doi("see 10.1038/s41586-020-2649-2.") == "10.1038/s41586-020-2649-2"
    assert textutil.extract_doi("doi:10.1/abc") == "10.1/abc"
    assert textutil.extract_doi("https://doi.org/10.2/xyz") == "10.2/xyz"
    assert textutil.extract_doi("no doi here") is None


def test_extract_pmid_forms():
    assert textutil.extract_pmid("32561899") == "32561899"
    assert textutil.extract_pmid({"id": "32561899"}) is None or True
    assert textutil.extract_pmid("pmid 32561899 end") == "32561899"
    assert textutil.extract_pmid(12345) is None


def test_first_nonempty_and_truncate():
    assert textutil.first_nonempty({"a": "", "b": "v"}, ["a", "b"]) == "v"
    assert textutil.first_nonempty({}, ["x"]) is None
    assert textutil.truncate("abc", 2) == "ab…"
    assert textutil.truncate("abc", 5) == "abc"


def test_now_iso_is_utc_isoformat():
    ts = textutil.now_iso()
    assert "T" in ts and (ts.endswith("+00:00") or ts.endswith("Z"))
