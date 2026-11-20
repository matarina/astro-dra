"""Tests for the isolated source-only verification stage."""
import json

import pytest

from research_verify.independent_verification import (
    ClaimPlanningInput,
    SourcePassage,
    VerificationAnswer,
    VerificationEvidence,
    VerificationQuestion,
    build_claim_reconciliation_prompt,
    build_verification_prompt,
    parse_claim_reconciliation_response,
    plan_verification_questions,
    parse_verification_response,
    reconcile_claim_answers,
    run_independent_verification,
    summarize_claim_answer_coverage,
)


def _questions():
    return [
        VerificationQuestion("population", "Which population was measured?", (1,)),
        VerificationQuestion("direction", "What happened to the measured outcome?", (1, 2)),
    ]


def _passages():
    return [
        SourcePassage(
            1, "Paper A", {"pmid": "1"},
            "In 20 adults, the intervention reduced marker X. The result was observational.",
            field="results", basis="full text", scope_note="Methods and results excerpt",
        ),
        SourcePassage(
            2, "Paper B", {"pmid": "2"},
            "In mice, marker X increased after exposure; causality was not established.",
            field="abstract", basis="abstract only", scope_note="Complete supplied abstract",
        ),
    ]


def test_prompt_has_only_neutral_questions_and_original_sources():
    prompt = build_verification_prompt(_questions(), _passages())
    assert "NEUTRAL QUESTIONS" in prompt
    assert "ORIGINAL SOURCE PASSAGES" in prompt
    assert "Draft claims" not in prompt
    assert "verdict" not in prompt.lower()
    assert "In 20 adults" in prompt and "In mice" in prompt
    assert "abstract only" in prompt


def test_verification_schema_is_id_neutral_and_lists_per_question_allowed_ids():
    prompt = build_verification_prompt(
        [VerificationQuestion("q-a", "What does source A report?", (11,)),
         VerificationQuestion("q-b", "What does source B report?", (22,))],
        [SourcePassage(11, "A", text="A text"), SourcePassage(22, "B", text="B text")],
    )
    assert '"source_id": 1' not in prompt
    assert '"source_id": "an integer from that question\'s source scope"' in prompt
    assert "allowed source IDs for evidence: 11" in prompt
    assert "allowed source IDs for evidence: 22" in prompt


def test_parser_keeps_negation_qualifier_counterevidence_and_cross_paper_identity():
    raw = {
        "answers": [
            {
                "question_id": "population", "status": "supported",
                "answer": "Adults were measured.",
                "evidence": [{"source_id": 1, "quote": "In 20 adults, the intervention reduced marker X.",
                               "field": "results", "qualifier": "20 participants", "counterevidence": ""}],
                "qualifiers": ["observational"], "counterevidence": [], "unknowns": [],
            },
            {
                "question_id": "direction", "status": "partial",
                "answer": "The direction differs by study population.",
                "evidence": [
                    {"source_id": 1, "quote": "reduced marker X", "field": "results",
                     "qualifier": "adults", "counterevidence": ""},
                    {"source_id": 2, "quote": "marker X increased after exposure", "field": "abstract",
                     "qualifier": "mice", "counterevidence": "causality was not established"},
                ],
                "qualifiers": ["observational", "causality not established"],
                "counterevidence": ["Paper B reports an increase in mice."], "unknowns": [],
            },
        ]
    }
    answers = parse_verification_response(json.dumps(raw), _questions(), _passages())
    assert answers[0].evidence[0].quote_valid is True
    assert answers[0].qualifiers == ("observational",)
    assert answers[1].status == "partial"
    assert {e.source_id for e in answers[1].evidence} == {1, 2}
    assert answers[1].evidence[1].counterevidence == "causality was not established"


def test_unlocated_quote_is_not_treated_as_support_and_missing_question_is_unknown():
    raw = {"answers": [{"question_id": "population", "status": "supported",
                        "answer": "Adults", "evidence": [{"source_id": 1,
                        "quote": "Adults were randomized", "field": "results"}]}]}
    answers = parse_verification_response(json.dumps(raw), _questions(), _passages())
    assert answers[0].status == "supported"
    assert answers[0].evidence[0].quote_valid is False
    assert answers[0].evidence_status == "unlocated"
    assert answers[0].effective_status == "unknown"
    assert any("quote_not_located" in warning for warning in answers[0].parse_warnings)
    assert answers[1].status == "unknown"
    assert "question_unanswered" in answers[1].parse_warnings


def test_question_scope_prevents_cross_paper_quote_attribution():
    raw = {"answers": [{"question_id": "population", "status": "supported",
                        "answer": "Mice", "evidence": [{"source_id": 2,
                        "quote": "In mice, marker X increased after exposure; causality was not established.",
                        "field": "abstract"}]}]}
    answers = parse_verification_response(json.dumps(raw), _questions(), _passages())
    evidence = answers[0].evidence[0]
    assert evidence.quote_valid is False
    assert answers[0].effective_status == "unknown"
    assert any("outside_question_scope" in warning for warning in answers[0].parse_warnings)


def test_runner_never_exposes_draft_to_invoke():
    seen = []

    def invoke(prompt):
        seen.append(prompt)
        return json.dumps({"answers": [
            {"question_id": "population", "status": "unknown", "answer": "",
             "unknowns": ["not reported"]},
            {"question_id": "direction", "status": "unknown", "answer": "",
             "unknowns": ["not reported"]},
        ]})

    answers = run_independent_verification(invoke, _questions(), _passages())
    assert len(answers) == 2
    assert "Previous Knowledge" not in seen[0]
    assert "Draft claims causality" not in seen[0]
    assert "proposed answer" not in seen[0].lower()


def test_empty_inputs_fail_closed_without_inventing_evidence():
    with pytest.raises(ValueError):
        build_verification_prompt([], _passages())
    with pytest.raises(ValueError):
        build_verification_prompt(_questions(), [])


def test_question_planner_keeps_claim_scope_and_marks_uncited_claims_uncovered():
    claims = [
        ClaimPlanningInput("c1", "Adults had reduced marker X [1].", (1,), "prose_candidate", "heading", 0, 25),
        ClaimPlanningInput("c2", "The intervention was safe [2].", (2,), "table_candidate", "Outcome", 26, 55),
        ClaimPlanningInput("c3", "A proposed workflow is recommended.", (), "prose_candidate", "", 56, 95),
    ]
    prompt_seen = []

    def invoke(prompt):
        prompt_seen.append(prompt)
        return json.dumps({"plans": [
            {"claim_id": "c1", "questions": [{
                "question_id": "c1:q1",
                "text": "What population, direction and qualifier does source [1] report?",
                "source_ids": [1],
                "requested_fields": ["population", "direction", "qualifier"],
            }]},
            {"claim_id": "c2", "questions": [{
                "question_id": "c2:q1",
                "text": "What safety outcome and limitation does source [2] report?",
                "source_ids": [2],
                "requested_fields": ["outcome", "limitation"],
            }]},
            {"claim_id": "c3", "questions": []},
        ]})

    planned = plan_verification_questions(invoke, claims)
    assert len(planned.questions) == 2
    assert planned.questions[0].source_ids == (1,)
    assert planned.questions[1].source_ids == (2,)
    assert planned.uncovered_claim_ids == ("c3",)
    assert "Adults had reduced marker X" in prompt_seen[0]
    assert "verdict" in prompt_seen[0].lower()


def test_question_planner_scopes_model_reused_question_ids_instead_of_overwriting():
    claims = [ClaimPlanningInput("c1", "First relationship.", (1,)),
              ClaimPlanningInput("c2", "Second relationship.", (2,))]

    def invoke(_prompt):
        return json.dumps({"plans": [
            {"claim_id": "c1", "questions": [{"question_id": "q1", "text": "What relation is reported?", "source_ids": [1], "requested_fields": ["relation"]}]},
            {"claim_id": "c2", "questions": [{"question_id": "q1", "text": "What population is reported?", "source_ids": [2], "requested_fields": ["population"]}]},
        ]})

    result = plan_verification_questions(invoke, claims)
    assert [q.question_id for q in result.questions] == ["q1", "c2:q1"]
    assert "duplicate_question_id_scoped_q1_c2" in result.parse_warnings


def test_reconciliation_preserves_unresolved_as_unverifiable_with_raw_status():
    rows = parse_claim_reconciliation_response(
        json.dumps({"comparisons": [{"claim_id": "c1", "provisional_status": "unresolved", "reason": "missing answer"}]}),
        ["c1"],
    )
    assert rows[0]["status"] == "unverifiable"
    assert rows[0]["status_raw"] == "unresolved"


def test_reconciliation_keeps_partial_claim_unverifiable_when_one_linked_question_is_unknown():
    claims = [ClaimPlanningInput("c1", "A relation with two required attributes.", (1,))]
    links = [
        {"claim_id": "c1", "question_id": "q1"},
        {"claim_id": "c1", "question_id": "q2"},
    ]
    answers = [VerificationAnswer(
        "q1", "supported", "reported", (
            VerificationEvidence(1, "reported", field="abstract", quote_valid=True),
        ),
    ), VerificationAnswer("q2", "unknown", unknowns=("not supplied",), parse_warnings=("question_unanswered",))]
    raw = json.dumps({"comparisons": [{"claim_id": "c1", "provisional_status": "supported", "question_ids": [], "reason": "model said supported"}], "uncovered_claim_ids": []})
    rows = reconcile_claim_answers(lambda _prompt: raw, claims, answers, links)
    assert rows[0]["status"] == "unverifiable"
    assert rows[0]["status_raw"] == "supported"
    assert rows[0]["evidence_guard"] == "incomplete_claim_question_coverage"
    assert "no_located_quote" in rows[0]["parse_warnings"]


def test_reconciliation_requires_all_mapped_relationship_questions_even_when_quotes_exist():
    claims = [ClaimPlanningInput("c1", "A relation with two attributes.", (1,))]
    links = [{"claim_id": "c1", "question_id": "q1"}, {"claim_id": "c1", "question_id": "q2"}]
    answers = [
        VerificationAnswer("q1", "supported", "first", (VerificationEvidence(1, "first", quote_valid=True),)),
        VerificationAnswer("q2", "supported", "second", (VerificationEvidence(1, "second", quote_valid=True),)),
    ]
    raw = json.dumps({"comparisons": [{"claim_id": "c1", "provisional_status": "supported", "question_ids": ["q1"], "reason": "partial model mapping"}]})
    rows = reconcile_claim_answers(lambda _prompt: raw, claims, answers, links)
    assert rows[0]["status"] == "unverifiable"
    assert "claim_question_coverage_incomplete" in rows[0]["parse_warnings"]


def test_claim_answer_coverage_exposes_partial_and_unlocated_relationships():
    claims = [ClaimPlanningInput("c1", "A relation with two attributes.", (1,))]
    links = [{"claim_id": "c1", "question_id": "q1"},
             {"claim_id": "c1", "question_id": "q2"}]
    answers = [
        VerificationAnswer("q1", "supported", "first",
                           (VerificationEvidence(1, "first", quote_valid=True),)),
        VerificationAnswer("q2", "supported", "copied but unlocated",
                           (VerificationEvidence(1, "missing", quote_valid=False),)),
    ]
    coverage = summarize_claim_answer_coverage(claims, answers, links)["c1"]
    assert coverage["expected_question_ids"] == ["q1", "q2"]
    assert coverage["located_question_ids"] == ["q1"]
    assert coverage["unlocated_question_ids"] == ["q2"]
    assert coverage["state"] == "partial" and not coverage["complete"]


def test_reconciliation_prompt_is_separate_from_source_only_answer_prompt():
    claims = [ClaimPlanningInput("c1", "Adults had reduced marker X [1].", (1,))]
    answers = parse_verification_response(
        json.dumps({"answers": [{"question_id": "c1:q1", "status": "unknown",
                                  "answer": "", "unknowns": ["not supplied"]}]}),
        [VerificationQuestion("c1:q1", "What does source [1] report?", (1,))],
        _passages(),
    )
    prompt = build_claim_reconciliation_prompt(
        claims, answers, [{"question_id": "c1:q1", "claim_id": "c1"}],
    )
    assert "Adults had reduced marker X" in prompt
    assert "not supplied" in prompt
    assert "Do not delete" in prompt


def test_reconciliation_accepts_current_provisional_status_schema_and_notes():
    raw = {
        "comparisons": [
            {"claim_id": "c1", "provisional_status": "contradicted",
             "notes": "The source states the opposite relation."},
        ],
        "uncovered_claim_ids": [],
    }
    rows = parse_claim_reconciliation_response(json.dumps(raw), ["c1"])
    assert rows[0]["status"] == "contradicted"
    assert rows[0]["reason"] == "The source states the opposite relation."


def test_question_planner_keeps_structurally_valid_language_without_lexical_neutrality_gate():
    claims = [ClaimPlanningInput("opaque-1", "The intervention reduced marker X.", (1,))]

    def invoke(_prompt):
        return json.dumps({"plans": [{"claim_id": "opaque-1", "questions": [{
            "question_id": "q1",
            "text": "How did treatment X cure all patients in source 1?",
            "source_ids": [1],
            "requested_fields": ["relation", "population"],
        }]}]})

    result = plan_verification_questions(invoke, claims)
    assert len(result.questions) == 1
    assert result.parse_warnings == ()
    assert result.links[0]["neutrality_assessment"] == "unassessed"

