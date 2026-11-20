import json
import pytest
from research_verify.question_batches import claim_batches,merge_questions
from research_verify.source_questions import parse_questions


def test_more_than_per_response_question_cap_keeps_global_claim_ids_and_qid_collisions_distinct():
    claims=[dict(claim_id=str(i),text='完整关系',source_ids=[1],start=i,end=i+1)for i in range(221)]
    batches=claim_batches(claims)
    assert [r for batch in batches for r in batch]==claims
    assert len(batches)>1 and all(len(b)<=40 for b in batches)
    parsed=[]
    for batch in batches:
        raw=json.dumps({'questions':[dict(question_id='q'+str(i),claim_id=c['claim_id'],source_id=1,question='是否报告该关系？')for i,c in enumerate(batch)]})
        parsed.append(parse_questions(raw,batch))
    merged=merge_questions(parsed)
    assert len(merged['questions'])==221 and len({q['question_id']for q in merged['questions']})==221
    assert merged['questions'][0]['model_question_id']==merged['questions'][40]['model_question_id']=='q0'
    assert not merged['claims_without_questions']and not merged['semantic_coverage_verified']


def test_oversized_or_duplicate_claim_is_explicit_failure_never_silent_truncation():
    row=dict(claim_id='original',text='A'*100)
    with pytest.raises(ValueError):claim_batches([row],max_chars=50)
    with pytest.raises(ValueError):claim_batches([row,row])
