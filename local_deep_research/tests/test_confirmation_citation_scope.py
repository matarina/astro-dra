"""Confirmation must see citations outside the critic's selected quotation."""
import json
from types import SimpleNamespace

from research_verify.evidence_flow import confirm_repairs
from research_verify.generation import format_source_documents


def test_confirmation_transports_original_replacement_and_evidence_citation_union():
    original = 'First analysis [1]; useful second analysis [2]; unresolved [3].'
    replacement = 'First analysis [1] with proposed qualification [4].'
    material = format_source_documents([
        SimpleNamespace(page_content=text, metadata={'index':i,'title':f'Source {i}'})
        for i,text in [(1,'First quotation.'),(2,'Second analysis method details.'),
                       (4,'Proposed qualification details.'),(5,'Other supplied evidence.')]])
    issue = dict(statement=original,replacement=replacement,status='contradiction',
                 source_id=1,source_ids=[1],evidence_quote=['First quotation.'],
                 evidence_sources=[{'source_id':5,'evidence_quote':'Other supplied evidence.'}])
    prompts=[]
    handler=SimpleNamespace(_invoke_text=lambda prompt,**kw:prompts.append(prompt) or json.dumps({
        'decisions':[{'candidate_index':0,'original_supported':None,
                     'replacement_supported':False,'same_analysis':None}]}))
    report,applied,pending=confirm_repairs(handler,original,[issue],material,'Question',
                                         SimpleNamespace(record=lambda *args:None))
    assert report==original and not applied and pending
    candidates=json.loads(prompts[0].split('\nCandidates:\n',1)[1])
    contexts={entry['source_id']:entry for entry in candidates[0]['source_contexts']}
    assert set(contexts)=={1,2,3,4,5}
    assert contexts[2]['context']=='Second analysis method details.'
    assert contexts[4]['context']=='Proposed qualification details.'
    assert contexts[3]==dict(source_id=3,metadata='',context='',context_status='not_supplied')
    # The critic's selected evidence is not relabeled as all cited evidence.
    assert candidates[0]['source_ids']==[1]
