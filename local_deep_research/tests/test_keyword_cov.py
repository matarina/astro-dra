"""Unit tests for requirement 3 -- keyword coverage."""

from __future__ import annotations

from research_verify.config import VerifyConfig
from research_verify.keyword_cov import KeywordCoverage

KWS = ["m6A", "hepatocellular carcinoma", "METTL3", "prognosis"]


def _kc(**kw) -> KeywordCoverage:
    return KeywordCoverage(VerifyConfig(), **kw)


def test_threshold_is_max_of_min_and_ratio():
    kc = _kc(min_hits=3, ratio=0.75)
    assert kc._threshold(4) == 3
    assert kc._threshold(8) == 6
    # min_hits floor still applies for tiny keyword sets
    assert kc._threshold(2) == 3


def test_fulltext_basis_and_pass():
    text = "This study of m6A and METTL3 in hepatocellular carcinoma improves prognosis."
    cov = _kc().compute({"full_content": text * 5, "content_type":"full_text"}, KWS)
    assert cov.basis == "fulltext"
    assert cov.threshold_ok is True
    assert len(cov.hits) == 4


def test_abstract_fallback_when_no_fulltext():
    cov = _kc().compute({"abstract": "m6A and METTL3 only", "title": "x"}, KWS)
    assert cov.basis == "abstract"
    assert cov.threshold_ok is False
    assert set(cov.missed) == {"hepatocellular carcinoma", "prognosis"}


def test_unavailable_when_no_text():
    cov = _kc().compute({"title": ""}, KWS)
    assert cov.basis == "unavailable"
    assert cov.threshold_ok is False
    assert cov.coverage == 0.0


def test_matching_is_casefold():
    cov = _kc().compute({"full_content": "m6a mettl3 " * 40}, KWS)
    assert "m6A" in cov.hits and "METTL3" in cov.hits


def test_extract_keywords_from_settings_string():
    kws = _kc().extract_keywords("ignored", {"keywords": "a, b，c"})
    assert kws == ["a", "b", "c"]


def test_extract_keywords_regex_from_query():
    kws = _kc().extract_keywords("m6A hepatocellular carcinoma METTL3 prognosis")
    assert kws == []


def test_empty_keywords_is_unknown():
    cov = _kc().compute({"full_content": "x" * 300}, [])
    assert cov.total == 0 and cov.threshold_ok is None
    assert cov.semantic_assessment == "not_performed"
