from types import SimpleNamespace
from research_verify.evidence_flow import (
    IDENTITY_ATTRIBUTE_INSTRUCTIONS,review_prompt,review_answer,normalize_atom_checks,literal_assertion_spans,
)


def test_opt_in_extends_native_prompt_without_changing_disabled_prompt():
    plain=review_prompt('Question','A finding [1].','Source material')
    enabled=review_prompt('Question','A finding [1].','Source material',identity_attributes=True)
    assert enabled==plain+'\n\n'+IDENTITY_ATTRIBUTE_INSTRUCTIONS
    assert 'Compare like date scopes' in enabled
    assert 'otherwise\nretain uncertainty' in enabled
    assert 'Retain its\nscientific attribute checks' in enabled


def test_identity_attributes_retain_explicit_roles_and_unknowns_stay_other():
    checks=normalize_atom_checks([{'attribute':'authors'},{'attribute':'journal'},
                                 {'attribute':'publication_year'},{'attribute':'invented_role'}])
    assert [c['attribute_role'] for c in checks]==['authors','journal','publication_year','other']


def test_candidate_keeps_literal_sentence_source_associations_without_borrowing():
    import json
    text='Journal Alpha reports a finding [8]. Uncited author assertion. Two studies [2, 3].'
    spans=literal_assertion_spans(text)
    assert [s['explicit_source_ids'] for s in spans]==[[8],[],[2,3]]
    assert all(text[s['start']:s['end']]==s['text'] for s in spans)
    claims={0:dict(claim_id=0,text=text,source_ids=[2,3,8])}
    before=json.dumps(claims)
    base=review_prompt('Question',text,'Sources',claims=claims)
    candidate=review_prompt('Question',text,'Sources',claims=claims,identity_attributes=True)
    assert 'literal_assertion_spans' not in base
    assert json.dumps(spans) in candidate
    assert json.dumps(claims)==before


def test_native_review_flag_reaches_actual_request_without_extra_calls_or_report_edits():
    class Handler:
        def __init__(self,on):self.on=on;self.prompts=[]
        def get_setting(self,key,default=None):return self.on if key=='citation.identity_attribute_review' else default
        def _invoke_text(self,prompt,**kwargs):
            self.prompts.append(prompt)
            return '{"issues":[{"claim_id":0,"status":"supported"}]}'
    class Trace:
        def record(self,*args,**kwargs):pass
    report='A finding [1].';doc=SimpleNamespace(page_content='A finding.',metadata={'index':1,'title':'Study'})
    for enabled in [False,True]:
        handler=Handler(enabled)
        result=review_answer(handler,'Question',report,[doc],[{'index':1}],Trace(),None,
                             1,60000,{},dict(remaining=1))
        assert result[0]==report and len(handler.prompts)==1
        assert (IDENTITY_ATTRIBUTE_INSTRUCTIONS in handler.prompts[0])==enabled
