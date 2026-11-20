"""A model's own evidence request can reach the bounded native supplement loop."""
import json
from types import SimpleNamespace
import pytest
from research_verify.evidence_flow import confirm_repairs,review_answer
from research_verify.generation import format_source_documents


def documents(sources):
    return [SimpleNamespace(page_content=s.get('fetched_content',s['abstract']),
        metadata={'index':s['index'],'title':'Study'}) for s in sources]


@pytest.mark.parametrize('enabled',[False,True])
def test_provisional_approval_with_evidence_request_preserves_default_and_routes_followup(enabled):
    original='Method P was used [1].';replacement='Method Q was used [1].'
    sources=[dict(index=1,abstract='The study used a method.')]
    issue=dict(statement=original,replacement=replacement,status='contradiction',source_id=1,
               evidence_quote=['The study used a method.'])
    h=SimpleNamespace(get_setting=lambda k,d=None:enabled if k=='citation.confirmation_evidence_followup' else d,
        _invoke_text=lambda *a,**kw:json.dumps(dict(decisions=[dict(candidate_index=0,original_supported=False,
            replacement_supported=True,same_analysis=True)],needs_evidence=[0])))
    report,applied,pending=confirm_repairs(h,original,[issue],format_source_documents(documents(sources)),
        'Question',SimpleNamespace(record=lambda *a:None))
    assert report==(original if enabled else replacement)
    assert len(applied)==(0 if enabled else 1)
    if enabled:assert pending[0]['status']=='insufficient_evidence' and pending[0]['request']['kind']=='article'


@pytest.mark.parametrize('acquired',[True,False])
def test_real_native_followup_rechecks_original_after_acquisition_and_retains_on_unavailable(acquired):
    original='Method P was used [1].';sources=[dict(index=1,abstract='The study used a method.')];stages=[]
    class Fetch:
        calls=0
        def article(self,source):
            self.calls+=1
            return 'Methods explicitly used P.' if acquired else None
    fetch=Fetch()
    def invoke(prompt,**kw):
        stages.append(kw['stage'])
        if stages==['native_check']:
            return json.dumps({'issues':[dict(statement=original,replacement='Method Q was used [1].',
                status='contradiction',source_id=1,evidence_quote='The study used a method.')]})
        if stages[-1]=='repair_validation':
            return json.dumps(dict(decisions=[dict(candidate_index=0,original_supported=False,
                replacement_supported=True,same_analysis=True)],needs_evidence=[0]))
        assert 'Methods explicitly used P.' in prompt and original in prompt
        return json.dumps(dict(issues=[],checked_claims=[dict(claim_id=0,status='supported')]))
    handler=SimpleNamespace(get_setting=lambda k,d=None:True if k=='citation.confirmation_evidence_followup' else d,
        _invoke_text=invoke,_create_documents=documents)
    report,docs,applied,pending,shown=review_answer(handler,'Question',original,documents(sources),sources,
        SimpleNamespace(record=lambda *a:None),None,1,60000,dict(fetcher=fetch),dict(remaining=5))
    assert report==original and not applied and fetch.calls==1
    assert stages==(['native_check','repair_validation','native_check'] if acquired else ['native_check','repair_validation'])
    if not acquired:assert any(i['status']=='insufficient_evidence' for i in pending)
