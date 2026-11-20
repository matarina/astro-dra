import json
from research_verify.questioned_fact_document import parse_answers


def test_question_coverage_remains_model_accounting_and_unknown_binding_is_visible():
    views=[dict(source_id=1,text='A',evidence_questions=[dict(question_id='q0'),dict(question_id='q1')])]
    raw=json.dumps({'sources':[dict(source_id=1,facts=[dict(text='source answer',quotes=['A'],question_ids=['foreign'])])]})
    r=parse_answers(raw,views)
    assert r['registry']['1:0']['text']=='source answer'
    assert r['model_unaddressed_question_ids']=={'1':['q0','q1']}
    assert len(r['invalid_question_bindings'])==1 and not r['semantic_question_coverage_verified']
