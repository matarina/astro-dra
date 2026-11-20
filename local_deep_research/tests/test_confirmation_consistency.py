import json
from types import SimpleNamespace
from research_verify.evidence_flow import confirm_repairs,confirmation_conflicts
from research_verify.generation import format_source_documents


def test_conflict_detection_is_protocol_only_and_never_derives_support_from_empty_checks():
    assert confirmation_conflicts([{'candidate_index':0,'replacement_supported':True,
        'replacement_attribute_checks':[{'attribute':'label','result':'contradiction'}]}])
    assert confirmation_conflicts([{'candidate_index':0},{'candidate_index':0}])
    assert not confirmation_conflicts([{'candidate_index':0,'replacement_supported':False,
        'replacement_attribute_checks':[{'result':'supported'}]}])
    assert not confirmation_conflicts([{'candidate_index':0,'replacement_supported':True}])


def test_consistency_review_clarifies_once_then_preserves_original_on_rejection_or_conflict():
    original='A report claim [1].';replacement='A proposed claim [1].'
    material=format_source_documents([SimpleNamespace(page_content='Quoted source clause.',
        metadata={'index':1,'title':'Title','source':'https://example.org'})])
    issue={'statement':original,'replacement':replacement,'status':'contradiction','source_id':1,'evidence_quote':['Quoted source clause.']}
    first={'candidate_index':0,'original_supported':False,'replacement_supported':True,'same_analysis':True,
           'replacement_attribute_checks':[{'attribute':'label','result':'contradiction'}]}
    class Trace:
        def record(self,*args,**kw):pass
    for last in [first,{**first,'replacement_supported':False}]:
        calls=[]
        class Handler:
            def get_setting(self,k,d=None):return k=='citation.confirmation_consistency_review' or d
            def _invoke_text(self,prompt,**kw):
                calls.append(kw['stage']);return json.dumps({'decisions':[first if len(calls)==1 else last]})
        report,applied,pending=confirm_repairs(Handler(),original,[issue],material,'Question',Trace())
        assert report==original and applied==[] and pending
        assert calls==['repair_validation','repair_validation_clarification']


def test_default_request_unchanged_and_consistent_control_needs_no_clarification():
    original='Original claim [1].';issue=dict(statement=original,replacement='Changed claim [1].',
        status='contradiction',source_id=1,evidence_quote=['Source clause.'])
    material=format_source_documents([SimpleNamespace(page_content='Source clause.',metadata={'index':1,'title':'Title'})])
    prompts=[]
    response={'decisions':[dict(candidate_index=0,original_supported=False,replacement_supported=True,same_analysis=True,
        replacement_attribute_checks=[dict(result='supported')])]}
    for enabled in [False,True]:
        handler=SimpleNamespace(get_setting=lambda k,d=None:enabled if k=='citation.confirmation_consistency_review' else d,
            _invoke_text=lambda prompt,**kw:prompts.append(prompt) or json.dumps(response))
        report,applied,pending=confirm_repairs(handler,original,[issue],material,'Question',SimpleNamespace(record=lambda *args:None))
        assert report==issue['replacement'] and len(applied)==1 and pending==[]
    assert len(prompts)==2 and prompts[0]==prompts[1]
