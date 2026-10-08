"""Unit tests for requirement 2 -- constraint matching (IF DB mocked)."""

from __future__ import annotations

from research_verify.config import VerifyConfig
from research_verify.constraint_matcher import ConstraintMatcher, _valid_if
from research_verify.models import ResearchConstraint


def test_valid_if_treats_zero_and_none_as_unknown():
    assert _valid_if(None) is None
    assert _valid_if(0) is None
    assert _valid_if(0.0) is None
    assert _valid_if(17.18) == 17.18


def test_parse_year_min_if_language_from_query():
    c = ConstraintMatcher().parse("找 2026年 关于 m6A 的文献，IF>10，只要英文")
    assert c.year_from == 2026
    assert c.min_if == 10
    assert c.language == "en"


def test_parse_cjk_if_variant():
    c = ConstraintMatcher().parse("影响因子≥15 的论文")
    assert c.min_if == 15


def test_parse_explicit_settings_win():
    c = ConstraintMatcher().parse("2020年", {"year_from": 2019, "min_if": 5})
    assert c.year_from == 2019
    assert c.min_if == 5


def _matcher_with_if(mapping: dict[str, float | None]) -> ConstraintMatcher:
    m = ConstraintMatcher(VerifyConfig())
    m._if_cache = mapping
    return m


def test_match_year_violation_marks_hard_violation():
    m = _matcher_with_if({})
    r = m.match({"index": "1", "year": 2019}, ResearchConstraint(year_from=2026))
    assert r.year_ok is False
    assert "year" in r.hard_violations
    assert r.excluded is True


def test_match_year_pass_and_missing():
    m = _matcher_with_if({})
    ok = m.match({"index": "1", "year": 2026}, ResearchConstraint(year_from=2026))
    assert ok.year_ok is True
    missing = m.match({"index": "2"}, ResearchConstraint(year_from=2026))
    assert missing.year_ok is None and not missing.hard_violations


def test_match_if_below_threshold_is_violation():
    m = _matcher_with_if({"nature": 17.18})
    r = m.match({"index": "1", "journal": "Nature"}, ResearchConstraint(min_if=30))
    assert r.if_ok is False
    assert "if" in r.hard_violations


def test_match_if_pass():
    m = _matcher_with_if({"nature": 17.18})
    r = m.match({"index": "1", "journal": "Nature"}, ResearchConstraint(min_if=10))
    assert r.if_ok is True and not r.hard_violations


def test_match_if_zero_means_unknown_not_violation():
    # A journal present with impact_factor 0.0 pre-normalised to None in cache.
    m = _matcher_with_if({"science": None})
    r = m.match({"index": "1", "journal": "Science"}, ResearchConstraint(min_if=10))
    assert r.if_unknown is True
    assert r.if_ok is None
    assert r.hard_violations == []  # unknown never counts as a violation


def test_match_language_mismatch():
    m = _matcher_with_if({})
    r = m.match({"index": "1", "language": "zh"}, ResearchConstraint(language="en"))
    assert r.lang_ok is False and "language" in r.hard_violations


def test_match_english_engine_infers_en():
    m = _matcher_with_if({})
    r = m.match({"index": "1", "source_engine": "pubmed"}, ResearchConstraint(language="en"))
    assert r.lang_ok is True


def test_match_empty_constraint_returns_neutral():
    m = _matcher_with_if({})
    r = m.match({"index": "1", "year": 1990}, ResearchConstraint())
    assert r.hard_violations == [] and r.year_ok is None


def test_match_many_skips_when_empty():
    assert ConstraintMatcher().match_many([{"index": "1"}], ResearchConstraint()) == {}
