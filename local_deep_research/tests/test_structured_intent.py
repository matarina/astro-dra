"""State-boundary checks; these are not report effectiveness evidence."""
import json
from research_verify.research_spec import parse_research_spec, format_research_spec
from research_verify.constraint_matcher import ConstraintMatcher
from research_verify.keyword_cov import KeywordCoverage


def test_unknown_intent_adds_no_scope_instructions():
    spec = parse_research_spec("Review stable gene expression in Chinese hamster cells from the 2020 cohort.")
    assert spec.language is None and spec.year_from is None
    assert spec.requested_fields == () and spec.output_mode is None
    assert format_research_spec(spec) == ""


def test_settings_are_not_overwritten_by_question_words():
    spec = parse_research_spec("Chinese cohort 2020 at least 20 patients", {
        "language":"en", "year_from":2010, "year_to":2015, "requested_count":3})
    assert (spec.language, spec.year_from, spec.year_to, spec.requested_count) == ("en",2010,2015,3)
    assert all(v.startswith("explicit") for v in spec.provenance.values())


def test_explicit_language_scope_is_structured_without_filtering_sources():
    spec = parse_research_spec("Chinese literature", {"language": "zh"})
    rendered = format_research_spec(spec)
    payload = json.loads(rendered.split("\n", 1)[1])
    policy = payload["evidence_scope_policy"]["language"]
    assert policy["requested"] == "zh"
    assert "authoritative_source_language" in policy["match_field"]
    assert "supplemental" in policy["mismatch_records"]
    assert "no supplied record" in policy["no_matches"]


def test_bad_settings_remain_unknown_and_unresolved():
    spec = parse_research_spec("", {"requested_count":False, "year_from":2026,
                                    "year_to":2020, "requested_fields":"guess fields"})
    assert spec.requested_count is None and spec.year_from is None and spec.year_to is None
    assert set(spec.unresolved) == {"requested_count", "year_range", "requested_fields"}


def test_constraint_parser_never_calls_model_to_guess_intent():
    class Forbidden:
        def invoke(self, *args): raise AssertionError("unrequested semantic inference")
    scope = ConstraintMatcher(model=Forbidden()).parse("No publication-date restriction; 2020 is the cohort year.")
    assert scope.year_from is None and scope.unresolved
    match = ConstraintMatcher().match({"year":2019, "language":"eng"}, scope)
    assert match.detail["pending"] and not match.hard_violations


def test_strict_and_inclusive_if_are_distinct_for_explicit_settings():
    matcher = ConstraintMatcher()
    matcher._if_cache = {"journal":10.0}
    for operator, expected in ((">",False),(">=",True),("=",True)):
        scope = matcher.parse("", {"min_if":10, "if_operator":operator})
        assert matcher.match({"journal":"journal"}, scope).if_ok is expected
    scope = matcher.parse("", {"min_if":9, "if_operator":"="})
    assert matcher.match({"journal":"journal"}, scope).if_ok is False


def test_missing_source_metadata_is_not_condition_pass():
    scope = ConstraintMatcher().parse("", {"language":"en", "year_from":2020})
    match = ConstraintMatcher().match({"source_engine":"pubmed"}, scope)
    assert match.year_ok is None and match.lang_ok is None and match.detail["pending"]


def test_lexical_hits_never_certify_relevance_or_fulltext():
    coverage = KeywordCoverage().compute({"full_content":"term " * 100}, ["term"])
    assert coverage.basis == "retrieved_text"
    assert coverage.semantic_assessment == "not_performed"
    assert KeywordCoverage().extract_keywords("term") == []


