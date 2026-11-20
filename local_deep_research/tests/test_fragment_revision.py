import json
import pytest
from research_verify.fragment_revision import parse_proposals,apply_proposals,confirmation_decisions


def test_minimal_revision_preserves_other_numbers_citations_and_original_coordinates():
    report='A 302 genes [1]. Wrong journal. 11/22 clusters [2].'
    anchors=[dict(anchor_id=0,start=0,end=len(report),text=report)]
    units=[dict(source_id=1,unit_id=0,text='Actual journal')]
    raw=dict(proposals=[dict(anchor_id=0,original='Wrong journal',replacement='Actual journal',evidence_units=[dict(source_id=1,unit_id=0)],reason='journal identity')])
    result=parse_proposals(json.dumps(raw),report,anchors,units)
    assert apply_proposals(report,result['proposals'])=='A 302 genes [1]. Actual journal. 11/22 clusters [2].'
    raw['proposals'][0]['original']='Wrong\njournal'
    assert len(parse_proposals(json.dumps(raw),report,anchors,units)['unlocated_proposals'])==1


def test_unknown_confirmation_keeps_atomic_batch_unapproved_and_wrong_source_rejected():
    proposals=[dict(candidate_index=0)]
    fields=['original_conflicts','replacement_supported','same_source_scope','useful_content_retained','no_new_error','language_layout_retained']
    row={f:True for f in fields};row['candidate_index']=0;row['same_source_scope']=None
    assert not confirmation_decisions(json.dumps(dict(decisions=[row])),proposals)['batch_approved']
    assert confirmation_decisions('{"decisions":[]}',proposals)['missing_candidate_indices']==[0]
    with pytest.raises(ValueError):apply_proposals('abc',[dict(start=0,end=2,original_text='ab',replacement='A'),dict(start=1,end=3,original_text='bc',replacement='B')])


def test_compact_indices_preserve_complete_report_source_text_and_binding_fields():
    from research_verify.fragment_revision import _context
    report='A complete report with important qualifiers and a table. ' * 4
    source='Original primary paragraph with identities, numbers and limits. ' * 4
    anchors=[dict(anchor_id=0,start=0,end=len(report),text=report,preview=report[:100],citation_ids=[1],kind='paragraph')]
    units=[dict(source_id=1,unit_id=7,kind='text',text=source)]
    default=_context('Original question',report,source,anchors,units)
    compact=_context('Original question',report,source,anchors,units,24)
    assert default==_context('Original question',report,source,anchors,units,100)
    assert '\nCOMPLETE REPORT:\n'+report+'\nSOURCE UNIT INDEX' in compact
    assert compact.endswith('\nACTUAL REGISTERED SOURCE MATERIAL:\n'+source)
    for start,end in [('REPORT ANCHOR INDEX:\n','\nCOMPLETE REPORT:'),('SOURCE UNIT INDEX (not extra evidence):\n','\nACTUAL REGISTERED SOURCE MATERIAL:')]:
        before=json.loads(default.split(start)[1].split(end)[0])
        after=json.loads(compact.split(start)[1].split(end)[0])
        assert [{k:v for k,v in row.items() if k!='preview'}for row in before]==[{k:v for k,v in row.items() if k!='preview'}for row in after]
        assert after[0]['preview']==before[0]['preview'][:24]
