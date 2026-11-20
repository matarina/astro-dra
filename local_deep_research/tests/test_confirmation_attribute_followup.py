"""Returned not_reported attributes trigger investigation, not a truth label."""
import json
from types import SimpleNamespace
import pytest
from research_verify.evidence_flow import confirm_repairs,supplement,review_answer
from research_verify.generation import format_source_documents


def docs(sources):
    return [SimpleNamespace(page_content=s.get('fetched_content',s['abstract']),metadata={'index':s['index'],'title':'Study'})for s in sources]


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('source_id,expected',[(2,[2]),(999,[1,2]),(None,[1,2])])
def test_source_specific_investigation_preserves_ambiguous_citation_scope(enabled,source_id,expected):
    original='General result [1]; method P [2].';replacement='General result [1].'
    sources=[dict(index=1,abstract='General result.'),dict(index=2,abstract='Second abstract.')]
    issue=dict(statement=original,replacement=replacement,status='contradiction',source_id=1,evidence_quote=['General result.'])
    h=SimpleNamespace(get_setting=lambda k,d=None:enabled if k=='citation.confirmation_attribute_evidence_followup'else d,
        _invoke_text=lambda *a,**kw:json.dumps(dict(decisions=[dict(candidate_index=0,original_supported=False,replacement_supported=True,same_analysis=True,
            original_attribute_checks=[dict(attribute='method',report_value='P',source_id=source_id,result='not_reported')])],needs_evidence=[])))
    report,applied,pending=confirm_repairs(h,original,[issue],format_source_documents(docs(sources)),'Question',SimpleNamespace(record=lambda *a:None))
    assert report==(original if enabled else replacement)
    if enabled:
        assert not applied and pending[0]['request']['source_ids']==expected
        assert pending[0]['status']=='insufficient_evidence'


def test_supplement_uses_each_registered_requested_source_once_without_overriding_identity():
    sources=[dict(index=i,abstract='Abstract.')for i in [1,2]];seen=[]
    fetch=SimpleNamespace(article=lambda source:seen.append(source['index']) or f"Actual source {source['index']} text.")
    acquired=supplement([dict(status='insufficient_evidence',source_id=1,request=dict(kind='article',source_ids=[2,2,999,'1',False]))],
        sources,fetch,register=None,trace=SimpleNamespace(record=lambda *a:None))
    assert acquired==[2,1] and seen==[2,1]
    assert all(s['fetched_content']==f"Actual source {s['index']} text."for s in sources)


def test_actual_native_loop_investigates_original_attribute_on_second_cited_source():
    original='General result [1]; method P [2].';sources=[dict(index=1,abstract='General result.'),dict(index=2,abstract='Second abstract.')];calls=[];fetched=[]
    def invoke(prompt,**kw):
        calls.append(kw['stage'])
        if calls==['native_check']:
            return json.dumps({'issues':[dict(statement=original,replacement='General result [1].',status='contradiction',source_id=1,evidence_quote='General result.')]})
        if kw['stage']=='repair_validation':
            return json.dumps(dict(decisions=[dict(candidate_index=0,original_supported=False,replacement_supported=True,same_analysis=True,
                original_attribute_checks=[dict(attribute='method',result='not_reported',source_id=2)])],needs_evidence=[]))
        assert original in prompt and 'Primary methods used P.' in prompt
        return json.dumps(dict(issues=[],checked_claims=[dict(claim_id=0,status='supported')]))
    h=SimpleNamespace(_invoke_text=invoke,_create_documents=docs,get_setting=lambda k,d=None:True if k=='citation.confirmation_attribute_evidence_followup'else d)
    fetch=SimpleNamespace(article=lambda source:fetched.append(source['index']) or 'Primary methods used P.')
    report,_,applied,pending,_=review_answer(h,'Question',original,docs(sources),sources,SimpleNamespace(record=lambda *a:None),None,1,60000,dict(fetcher=fetch),dict(remaining=5))
    assert report==original and not applied and fetched==[2]
    assert calls==['native_check','repair_validation','native_check']
