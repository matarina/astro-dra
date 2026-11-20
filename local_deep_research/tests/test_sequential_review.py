import json
import pytest
from research_verify.sequential_review import english_review_prompt,sequential_english_review


def test_english_presentation_keeps_source_context_and_nontext_identity_fields():
    claim={'claim_id':3,'text':'原文[7]。','source_ids':[7],'section_context':['Section']}
    base='Question\nFINAL ANSWER:\n'+json.dumps([claim],ensure_ascii=False)+'\n\nSUPPLIED SOURCES:\nUNCHANGED SOURCE\nSTRUCTURE'
    result=english_review_prompt(base,{3:{'text':'Literal reading [7].'}})
    payload=json.loads(result.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
    assert payload[0]['source_ids']==[7] and payload[0]['section_context']==['Section']
    assert result.split('\n\nSUPPLIED SOURCES:',1)[1].startswith('\nUNCHANGED SOURCE\nSTRUCTURE')
    with pytest.raises(ValueError):english_review_prompt(base,{4:{'text':'wrong scope'}})


def test_exhausted_extra_budget_preserves_entire_already_reviewed_report():
    from types import SimpleNamespace
    report='Already repaired report [1].'
    docs=[SimpleNamespace(page_content='Source.',metadata={'index':1,'title':'Source'})]
    events=[];trace=SimpleNamespace(record=lambda stage,data:events.append((stage,data)))
    handler=SimpleNamespace(_invoke_text=lambda *a,**kw:pytest.fail('No call budget'))
    revised,applied,pending,receipts=sequential_english_review(handler,'Question',report,docs,[{'index':1}],trace,{'remaining':0})
    assert revised==report and applied==[] and receipts==[]
    assert pending[0]['status']=='sequential_budget_exhausted'


@pytest.mark.parametrize('approve',[False,True])
def test_additional_pass_renders_original_language_and_requires_native_confirmation(approve):
    from types import SimpleNamespace
    report='Previously repaired journal; estimate B [1].'
    expected='Previously repaired journal; estimate A [1].'
    docs=[SimpleNamespace(page_content='The estimate is A.',metadata={'index':1,'title':'Study'})]
    called=[]
    def invoke(prompt,**kw):
        stage=kw['stage'];called.append(stage)
        if stage=='sequential_translation':
            assert report in prompt
            return json.dumps({'translations':[{'claim_id':0,'text':'A literal reading of estimate B [1].'}]})
        if stage=='sequential_english_check':
            assert 'The estimate is A.' in prompt
            return json.dumps({'issues':[{'claim_id':0,'evidence_source_id':1,'status':'contradiction',
                'evidence_quote':'The estimate is A.','replacement':'English proposal A [1].'}]})
        if stage=='sequential_proposal_rendering':
            assert report in prompt and 'English proposal A' in prompt
            assert 'The estimate is A.' not in prompt
            return json.dumps({'translations':[{'claim_id':0,'text':expected}]})
        assert stage=='repair_validation'
        assert expected in prompt and report in prompt
        return json.dumps({'decisions':[{'candidate_index':0,'original_supported':False,
            'replacement_supported':approve,'same_analysis':True}]})
    handler=SimpleNamespace(_invoke_text=invoke,get_setting=lambda k,d=None:True if k in {
        'citation.attribute_confirmation_review','citation.confirmation_consistency_review'} else d)
    trace=SimpleNamespace(record=lambda *args,**kw:None);budget={'remaining':8}
    revised,applied,pending,receipts=sequential_english_review(handler,'Question',report,docs,[{'index':1}],trace,budget)
    assert revised==(expected if approve else report)
    assert len(applied)==int(approve)
    assert len(called)==4 and budget['remaining']==4
    assert receipts[0]['status']=='checked'


@pytest.mark.parametrize('acquire',[False,True])
def test_optional_followup_reuses_original_reading_and_rechecks_acquired_text(acquire):
    from types import SimpleNamespace
    report='Original method P [1].';sources=[dict(index=1,abstract='Source abstract.')]
    def docs(records):return [SimpleNamespace(page_content=s.get('fetched_content',s['abstract']),metadata={'index':s['index'],'title':'Study'})for s in records]
    class Fetch:
        calls=0
        def article(self,source):
            self.calls+=1;return 'Primary methods used P.' if acquire else None
    fetch=Fetch();stages=[];checks=[]
    def invoke(prompt,**kw):
        stage=kw['stage'];stages.append(stage)
        if stage=='sequential_translation':
            return json.dumps({'translations':[dict(claim_id=0,text='Original method P [1].')]})
        if stage=='sequential_english_check':
            checks.append(prompt)
            if len(checks)==1:return json.dumps({'issues':[dict(claim_id=0,evidence_source_id=1,status='contradiction',evidence_quote='Source abstract.',replacement='Suggested method Q [1].')]})
            assert 'Primary methods used P.' in prompt and 'Original method P [1].' in prompt
            assert 'Suggested method Q' not in prompt
            return json.dumps({'issues':[],'checked_claims':[dict(claim_id=0,status='supported')]})
        if stage=='sequential_proposal_rendering':
            return json.dumps({'translations':[dict(claim_id=0,text='Suggested method Q [1].')]})
        assert stage=='repair_validation'
        return json.dumps(dict(decisions=[dict(candidate_index=0,original_supported=False,replacement_supported=True,same_analysis=True)],needs_evidence=[0]))
    h=SimpleNamespace(_invoke_text=invoke,_create_documents=docs,
        get_setting=lambda k,d=None:True if k=='citation.confirmation_evidence_followup'else d)
    revised,applied,pending,receipts=sequential_english_review(h,'Question',report,docs(sources),sources,
        SimpleNamespace(record=lambda *a:None),dict(remaining=12),network_state=dict(fetcher=fetch))
    assert revised==report and not applied and fetch.calls==1
    assert stages.count('sequential_translation')==1
    assert len(checks)==(2 if acquire else 1)
    assert receipts[0]['rounds']==(2 if acquire else 1)
    if not acquire:assert any(i.get('status')=='insufficient_evidence' for i in pending)


@pytest.mark.parametrize('valid,approve',[(False,False),(True,False),(True,True)])
def test_quote_followup_only_recovers_literal_evidence_and_separate_confirmation_decides(valid,approve):
    from types import SimpleNamespace
    report='Original B [1].';proposal='Proposal A [1].';stages=[]
    docs=[SimpleNamespace(page_content='First clause. Middle. Last clause.',metadata={'index':1,'title':'Study'})]
    def invoke(prompt,**kw):
        stage=kw['stage'];stages.append(stage)
        if stage=='sequential_translation':return json.dumps({'translations':[dict(claim_id=0,text='Original B [1].')]})
        if stage=='sequential_english_check':return json.dumps({'issues':[dict(claim_id=0,status='contradiction',evidence_source_id=1,
            evidence_quote='First clause... Last clause.',replacement=proposal)]})
        if stage=='sequential_proposal_rendering':return json.dumps({'translations':[dict(claim_id=0,text=proposal)]})
        if stage=='sequential_quote_reselection':
            return json.dumps({'quote_updates':[dict(issue_index=0,status='selected',evidence_sources=[dict(source_id=1,quote='First clause.'if valid else 'invented')])]})
        assert stage=='repair_validation'and valid
        return json.dumps({'decisions':[dict(candidate_index=0,original_supported=False,replacement_supported=approve,same_analysis=True)]})
    handler=SimpleNamespace(_invoke_text=invoke,get_setting=lambda k,d=None:True if k=='citation.literal_quote_reselection'else d)
    result,applied,pending,receipts=sequential_english_review(handler,'Question',report,docs,[dict(index=1)],SimpleNamespace(record=lambda *a:None),dict(remaining=8))
    assert result==(proposal if valid and approve else report)
    assert stages.count('sequential_quote_reselection')==1
    assert stages.count('repair_validation')==int(valid)
