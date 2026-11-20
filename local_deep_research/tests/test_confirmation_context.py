"""Confirmation evidence transport, not scientific quality or model-accuracy tests."""
import copy
import json
from types import SimpleNamespace

from research_verify.confirmation_context import expanded_confirmation_prompt
from research_verify.evidence_flow import confirm_repairs
from research_verify.generation import format_source_documents
from research_verify.synthesis_trace import DISABLED


def document(sid, text):
    return SimpleNamespace(page_content=text, metadata={'index':sid, 'title':f'Study {sid}', 'source':f'https://example.org/{sid}'})


def candidate(sid=7):
    return {'source_id':sid,'original':'Workflow B used method B [7].',
            'replacement':'Workflow B used method A [7].','evidence_quote':['Workflow A used method A.'],
            'source_metadata':'selected source','source_context':'Workflow A used method A.',
            'source_contexts':[{'source_id':sid,'metadata':'selected source','context':'Workflow A used method A.'}]}


def prompt_for(cs):
    return 'Existing instructions.\nCandidates:\n'+json.dumps(cs,ensure_ascii=False)+'\nExisting suffix.'


def test_complete_context_retains_parallel_branch_once_and_does_not_mutate_candidates():
    cs=[candidate()];before=copy.deepcopy(cs);text='Workflow A used method A.\n\nWorkflow B used method B.'
    old=prompt_for(cs);new,receipt=expanded_confirmation_prompt(old,cs,[document(7,text),document(9,'Uncited data.')])
    assert cs==before and receipt['status']=='expanded_complete_acquired_context'
    payload=json.loads(new.split('\nCandidates:\n')[1].removesuffix('\nExisting suffix.'))
    assert set(payload['source_context_registry'])=={'7'}
    assert payload['source_context_registry']['7']['context']==text
    assert payload['candidates'][0]['source_context']['context_ref']=='7'
    assert new.count('Workflow B used method B.')==1
    assert new.endswith('\nExisting suffix.')
    assert payload['source_context_registry']['7']['published_paper_completeness']=='unconfirmed'


def test_actual_complete_prompt_budget_is_atomic_and_fallback_is_byte_exact():
    cs=[candidate()];old=prompt_for(cs);docs=[document(7,'Workflow A used method A. '+('other data '*200))]
    expanded,receipt=expanded_confirmation_prompt(old,cs,docs,max_chars=20000)
    assert receipt['status']=='expanded_complete_acquired_context'
    exact,_=expanded_confirmation_prompt(old,cs,docs,max_chars=len(expanded));assert exact==expanded
    fallback,receipt=expanded_confirmation_prompt(old,cs,docs,max_chars=len(expanded)-1)
    assert fallback==old and receipt['reason']=='complete_acquired_context_exceeds_prompt_budget'


def test_missing_duplicate_or_changed_source_never_promotes_context():
    cs=[candidate()];old=prompt_for(cs)
    for docs in [[],[document(7,'Different acquired version.')],
                 [document(7,'Workflow A used method A.'),document(7,'Different acquired version.')]]:
        new,receipt=expanded_confirmation_prompt(old,cs,docs)
        assert new==old and receipt['status']=='not_expanded'


def test_all_explicit_citation_contexts_retained_without_adjacent_source_inference():
    cs=[candidate()];cs[0]['source_contexts'].append({'source_id':8,'metadata':'other cited study','context':'Other cited evidence.'})
    new,receipt=expanded_confirmation_prompt(prompt_for(cs),cs,[document(7,'Workflow A used method A.'),document(8,'Other cited evidence. More acquired text.'),document(9,'Uncited evidence.')])
    payload=json.loads(new.split('\nCandidates:\n')[1].removesuffix('\nExisting suffix.'))
    assert set(payload['source_context_registry'])=={'7','8'}
    assert len(payload['candidates'][0]['source_contexts'])==2


def test_native_confirmation_default_unchanged_and_flag_reaches_real_invoke():
    original='Workflow B used method B [7].';issue={'statement':original,'source_id':7,'status':'contradiction',
        'replacement':'Workflow B used method A [7].','evidence_quote':'Workflow A used method A.'}
    material=format_source_documents([document(7,'Workflow A used method A.')])
    full=[document(7,'Workflow A used method A.\n\nWorkflow B used method B.')]
    prompts=[]
    def invoke(prompt,**kwargs):
        prompts.append(prompt)
        return '{"decisions":[]}'
    base=SimpleNamespace(_invoke_text=invoke)
    out,applied,_=confirm_repairs(base,original,[issue],material,'Question',DISABLED)
    assert out==original and not applied
    baseline=prompts[-1]
    out,_,_=confirm_repairs(base,original,[issue],material,'Question',DISABLED,documents=full)
    assert prompts[-1]==baseline and out==original
    enabled=SimpleNamespace(_invoke_text=invoke,get_setting=lambda k,d=None:True if k=='citation.confirmation_acquired_context' else d)
    out,applied,_=confirm_repairs(enabled,original,[issue],material,'Question',DISABLED,documents=full)
    assert out==original and not applied
    assert 'source_context_registry' in prompts[-1] and 'Workflow B used method B.' in prompts[-1]
