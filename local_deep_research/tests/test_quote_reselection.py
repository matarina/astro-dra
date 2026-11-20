import json
from types import SimpleNamespace
import pytest
from research_verify.generation import format_source_documents
from research_verify.quote_reselection import quotation_prompt,parse_quote_updates
from research_verify.evidence_flow import confirm_repairs


def test_separate_literal_quotes_preserve_fixed_proposal_and_still_require_confirmation():
    issue=dict(statement='Original assertion [1].',replacement='Proposed assertion [1].',status='contradiction',
        source_id=1,evidence_quote=['First passage... Last passage.'])
    material=format_source_documents([SimpleNamespace(page_content='First passage. Middle context. Last passage.',metadata={'index':1,'title':'Study'})])
    raw=json.dumps(dict(quote_updates=[dict(issue_index=0,status='selected',evidence_sources=[dict(source_id=1,quote='First passage.'),dict(source_id=1,quote='Last passage.')])]))
    issues,receipt=parse_quote_updates(raw,[issue],material)
    assert issues[0]['statement']==issue['statement'] and issues[0]['replacement']==issue['replacement']
    assert receipt[0]['semantic_status']=='not_assessed'
    h=SimpleNamespace(_invoke_text=lambda *a,**kw:'{"decisions":[{"candidate_index":0,"original_supported":true,"replacement_supported":false,"same_analysis":true}]}')
    report,applied,pending=confirm_repairs(h,issue['statement'],issues,material,'Question',SimpleNamespace(record=lambda *a:None))
    assert report==issue['statement']and not applied and pending
    assert 'NOT a decision' in quotation_prompt([issue],material)


@pytest.mark.parametrize('pair',[dict(source_id=1,quote='First... Last.'),dict(source_id=2,quote='First.')])
def test_reselection_cannot_stitch_or_reassign_papers(pair):
    issue=dict(statement='Original [1].',replacement='Proposal [1].',source_id=1)
    material=format_source_documents([SimpleNamespace(page_content='First. Last.',metadata={'index':i,'title':'Study'})for i in [1,2]])
    with pytest.raises(ValueError):parse_quote_updates(json.dumps(dict(quote_updates=[dict(issue_index=0,status='selected',evidence_sources=[pair])])),[issue],material)


def test_unavailable_reselection_does_not_silently_admit_prior_quote():
    issue=dict(statement='Original [1].',replacement='Proposal [1].',source_id=1,evidence_quote=['invented'])
    result,receipt=parse_quote_updates('{"quote_updates":[]}',[issue],'')
    assert result==[issue]and receipt[0]['status']=='missing_update'
