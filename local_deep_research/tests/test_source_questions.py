from research_verify.source_questions import parse_questions
import json


def test_question_references_cannot_reassign_a_claim_to_another_paper():
    claims=[dict(claim_id='c0',source_ids=[1]),dict(claim_id='c1',source_ids=[2])]
    raw=json.dumps({'questions':[dict(question_id='q0',claim_id='c0',source_id=2,question='Which method?'),dict(question_id='q1',claim_id='c1',source_id=2,question='What subjects?')]})
    r=parse_questions(raw,claims)
    assert len(r['unbound_rows'])==1 and r['claims_without_questions']==['c0']
    assert not r['semantic_coverage_verified'] and not r['answer_leakage_assessed']


def test_structural_validity_does_not_mark_a_leading_question_neutral():
    r=parse_questions(json.dumps({'questions':[dict(question_id='q0',claim_id='c0',source_id=1,question='Why did the treatment improve outcomes?')]}),[dict(claim_id='c0',source_ids=[1])])
    assert len(r['questions'])==1
    assert r['questions'][0]['status']=='fallible_question_not_evidence_or_verified_neutral'
