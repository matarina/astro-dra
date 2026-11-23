"""Unit tests for requirement 2 -- constraint matching (IF DB mocked)."""

from __future__ import annotations

from research_verify.constraint_matcher import ConstraintMatcher
from research_verify.models import ResearchConstraint


def test_free_query_does_not_establish_scope():
    c = ConstraintMatcher().parse("找 2026年 关于 m6A 的文献，IF>10，只要英文")
    assert c.year_from is None and c.min_if is None and c.language is None
    assert c.unresolved == ["query_intent_not_structured"]


def test_parse_cjk_if_variant():
    c = ConstraintMatcher().parse("影响因子≥15 的论文", {"min_if":15})
    assert c.min_if == 15


def test_parse_explicit_settings_win():
    c = ConstraintMatcher().parse("2020年", {"year_from": 2019, "min_if": 5})
    assert c.year_from == 2019
    assert c.min_if == 5


def test_match_year_violation_marks_hard_violation():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "year": 2019}, ResearchConstraint(year_from=2026))
    assert r.year_ok is False
    assert "year" in r.hard_violations
    assert r.excluded is True


def test_match_year_pass_and_missing():
    m = ConstraintMatcher()
    ok = m.match({"index": "1", "year": 2026}, ResearchConstraint(year_from=2026))
    assert ok.year_ok is True
    missing = m.match({"index": "2"}, ResearchConstraint(year_from=2026))
    assert missing.year_ok is None and not missing.hard_violations


def test_match_if_below_threshold_is_violation():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "journal": "Nature",
                 "_jcr_check": {"impact_factor": 17.18, "passes_threshold": False}}, ResearchConstraint(min_if=30))
    assert r.if_ok is False
    assert "if" in r.hard_violations


def test_match_if_pass():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "journal": "Nature",
                 "_jcr_check": {"impact_factor": 17.18, "passes_threshold": True}}, ResearchConstraint(min_if=10))
    assert r.if_ok is True and not r.hard_violations


def test_match_without_jcr_receipt_is_unknown():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "journal": "Science"}, ResearchConstraint(min_if=10))
    assert r.if_unknown is True
    assert r.if_ok is None
    assert r.hard_violations == []  # unknown never counts as a violation


def test_match_language_mismatch():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "language": "zh"}, ResearchConstraint(language="en"))
    assert r.lang_ok is False and "language" in r.hard_violations


def test_match_index_does_not_establish_language():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "source_engine": "pubmed"}, ResearchConstraint(language="en"))
    assert r.lang_ok is None and r.detail["pending"]


def test_match_empty_constraint_returns_neutral():
    m = ConstraintMatcher()
    r = m.match({"index": "1", "year": 1990}, ResearchConstraint())
    assert r.hard_violations == [] and r.year_ok is None


def test_match_many_skips_when_empty():
    assert ConstraintMatcher().match_many([{"index": "1"}], ResearchConstraint()) == {}


def test_match_evaluates_the_current_threshold_instead_of_the_cached_answer():
    source = {"_jcr_check": {"status": "found", "impact_factor": 20,
                            "minimum_if": 10, "threshold_operator": ">=", "passes_threshold": True}}
    matcher = ConstraintMatcher()
    assert matcher.match(source, ResearchConstraint(min_if=20, if_operator=">")).if_ok is False
    assert matcher.match(source, ResearchConstraint(min_if=20, if_operator=">=")).if_ok is True
