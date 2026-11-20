import json
from types import SimpleNamespace
from research_verify.evidence_flow import confirm_repairs,ATTRIBUTE_CONFIRMATION_INSTRUCTIONS
from research_verify.generation import format_source_documents


def test_confirmation_opt_in_preserves_default_prompt_and_original_on_rejection():
    original='A study of population B [7].'
    issue=dict(statement=original,replacement='A study of population A [7].',status='contradiction',
               source_id=7,evidence_quote='A study of population A.')
    material=format_source_documents([SimpleNamespace(page_content='A study of population A.',
        metadata=dict(index=7,title='Study',source='https://example.org/7'))])
    prompts=[];events=[]
    response={'decisions':[dict(candidate_index=0,original_supported=True,replacement_supported=True,
        same_analysis=True,original_attribute_checks=[dict(result='contradiction')])],'needs_evidence':[]}
    def invoke(prompt,**kwargs):prompts.append(prompt);return json.dumps(response)
    for enabled in [False,True]:
        handler=SimpleNamespace(_invoke_text=invoke,get_setting=lambda key,default=None:enabled if key=='citation.attribute_confirmation_review' else default)
        trace=SimpleNamespace(record=lambda stage,data:events.append((stage,data)))
        revised,applied,pending=confirm_repairs(handler,original,[issue],material,'Question',trace)
        assert revised==original and not applied and pending[0]['status']=='repair_not_confirmed'
    assert prompts[1]==prompts[0]+'\n\n'+ATTRIBUTE_CONFIRMATION_INSTRUCTIONS
    decisions=[data for stage,data in events if stage=='repair_validation_decisions']
    assert len(decisions)==2 and decisions[0]['decisions']==response['decisions']
    # Added explanation fields never override the existing approval decision.
    assert 'indexing' in ATTRIBUTE_CONFIRMATION_INSTRUCTIONS
