"""Bound draft-question requests without dropping original claim identities."""
import json


def claim_batches(claims, max_claims=40, max_chars=12000):
    if type(max_claims) is not int or max_claims < 1 or type(max_chars) is not int or max_chars < 1:
        raise ValueError('Invalid question batch bounds')
    seen=set();batches=[];batch=[];size=0
    for claim in claims:
        cid=claim.get('claim_id')if isinstance(claim,dict)else None
        if not isinstance(cid,str)or cid in seen:
            raise ValueError('Invalid or duplicate original claim identity')
        seen.add(cid);count=len(json.dumps(claim,ensure_ascii=False))+2
        if count>max_chars:
            raise ValueError('One complete claim exceeds question-request budget; not truncated')
        if batch and(len(batch)>=max_claims or size+count>max_chars):
            batches.append(batch);batch=[];size=0
        batch.append(claim);size+=count
    if batch:batches.append(batch)
    return batches


def merge_questions(parsed_batches):
    questions=[];unbound=[];missing=[]
    for batch_index,parsed in enumerate(parsed_batches):
        for row in parsed['questions']:
            questions.append(dict(row,question_id=f"b{batch_index}:"+row['question_id'],
                                  model_question_id=row['question_id'],question_batch=batch_index))
        unbound.extend(dict(row,question_batch=batch_index)for row in parsed['unbound_rows'])
        missing.extend(parsed['claims_without_questions'])
    assert len({q['question_id']for q in questions})==len(questions)
    return dict(questions=questions,unbound_rows=unbound,claims_without_questions=missing,
                semantic_coverage_verified=False,answer_leakage_assessed=False)
