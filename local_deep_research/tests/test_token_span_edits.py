import json
import pytest
from research_verify.generation import SourceMaterial
from research_verify.request_fields import original_anchors
from research_verify.token_span_edits import anchor_token_registry,parse_token_edits
from research_verify.field_comparison import apply_confirmed_edits


def fixture():
    report='Intro.\n\n空间  SeekSpace  患者1至10  10例（均为男\n转录  方法  每切片细胞核数N\n性）[5]\n\nUnchanged [6].'
    anchors=original_anchors(report);reg=anchor_token_registry(report,anchors,{5});assert len(reg)==1
    aid=reg[0]['anchor_id'];tokens=reg[0]['tokens'];lookup={t['text']:t['token_id']for t in tokens}
    material=SourceMaterial('source', {5:dict(text='Actual source text.',metadata='')})
    p=dict(action='replace',anchor_id=aid,requirement_id=0,observation_ids=[0],citation_source_ids=[5],evidence_units=[dict(source_id=5,unit_id=0)],
        token_replacements=[dict(first_token=lookup['均为男'],last_token=lookup['均为男'],replacement='7男3女'),dict(first_token=lookup['性'],last_token=lookup['性'],replacement='例')])
    return report,anchors,material,p


def parse(case,p):
    report,anchors,material,_=case
    return parse_token_edits(json.dumps(dict(proposals=[p])),report,material,[dict(requirement_id=0)],anchors,{5},[dict(observation_id=0)])


def test_discontinuous_fields_copy_original_whitespace_and_other_columns_exactly():
    c=fixture();p=c[-1];result=parse(c,p);assert len(result['eligible'])==1
    decision=dict(candidate_index=0,explicitly_requested=True,source_supported=True,same_study_scope=True,edit_needed=True,retains_correct_content=True,no_new_error=True)
    answer,_,_=apply_confirmed_edits(json.dumps(dict(decisions=[decision])),c[0],result['eligible'])
    assert answer==c[0].replace('均为男','7男3女').replace('\n性）','\n例）')
    assert '转录  方法  每切片细胞核数N' in answer and '患者1至10' in answer
    # Scientific content is intentionally not checked; structural validity is not correctness.
    assert apply_confirmed_edits('{"decisions":[]}',c[0],result['eligible'])[0]==c[0]


@pytest.mark.parametrize('change',[
    dict(first_token=True,last_token=2,replacement='x'),dict(first_token=999,last_token=999,replacement='x'),
    dict(first_token=2,last_token=1,replacement='x'),dict(first_token=1,last_token=1,replacement=' '),
])
def test_invalid_ranges_never_infer_or_fallback_to_whole_row(change):
    c=fixture();p=dict(c[-1],token_replacements=[change]);r=parse(c,p)
    assert not r['eligible'] and r['unresolved']


def test_overlapping_ranges_and_foreign_anchor_are_unresolved():
    c=fixture();p=c[-1];r=parse(c,dict(p,token_replacements=[p['token_replacements'][0]]*2))
    assert not r['eligible'] and r['unresolved']
    r=parse(c,dict(p,anchor_id=0));assert not r['eligible'] and r['unresolved']
    r=parse(c,dict(p,addition='retyped row'));assert not r['eligible'] and r['unresolved']


def test_optional_line_local_mode_rejects_cross_row_span_but_keeps_split_field_edits():
    c=fixture();report,anchors,material,p=c
    args=(report,material,[dict(requirement_id=0)],anchors,{5},[dict(observation_id=0)])
    original=json.dumps(dict(proposals=[p]))
    assert parse_token_edits(original,*args,line_local=True)['eligible']
    first=p['token_replacements'][0]['first_token'];last=p['token_replacements'][1]['last_token']
    wide=dict(p,token_replacements=[dict(first_token=first,last_token=last,replacement='Narrow fact replacing unrelated middle columns')])
    assert parse_token_edits(json.dumps(dict(proposals=[wide])),*args)['eligible']
    r=parse_token_edits(json.dumps(dict(proposals=[wide])),*args,line_local=True)
    assert not r['eligible']and r['unresolved'][0]['reason']=='token_selection_crosses_original_line'
