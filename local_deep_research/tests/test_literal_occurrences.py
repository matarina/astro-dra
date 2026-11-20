import json
import pytest
from research_verify.literal_occurrences import parse_extraction,parse_comparison


def test_literal_claim_cannot_borrow_other_unit_or_normalize_number():
    rows=[dict(report_unit_id=1,text='Group A has 10 men.',start=20,end=39,explicit_source_ids=[5],attribution_status='explicit_citation')]
    good={'units':[{'report_unit_id':1,'claims':[{'quote':'10 men','assertion':'ten men'}],'limit':''}]}
    result=parse_extraction(json.dumps(good),rows)
    assert result[0]['claims'][0]['report_start']==32
    good['units'][0]['claims'][0]['quote']='7 men'
    with pytest.raises(ValueError):parse_extraction(json.dumps(good),rows)
    assert parse_extraction('{"units":[]}',rows)[0]['status']=='unassessed'


def test_comparison_evidence_binds_source_and_unknown_does_not_approve():
    extracted=[{'claims':[{'claim_id':'1:0'},{'claim_id':'1:1'}]}]
    units=[{'source_id':5,'unit_id':3,'text':'Seven men and three women.'}]
    raw={'comparisons':[{'claim_id':'1:0','relation':'contradicted','evidence':[{'source_id':5,'unit_id':3,'quote':'Seven men and three women.'}],'reason':'different group'}]}
    result=parse_comparison(json.dumps(raw),extracted,units)
    assert result[1]['status']=='unassessed'and result[1]['relation']is None
    raw['comparisons'][0]['evidence'][0]['source_id']=6
    with pytest.raises(ValueError):parse_comparison(json.dumps(raw),extracted,units)


def test_partial_binding_preserves_original_bytes_and_rejects_changed_science():
    from research_verify.literal_occurrences import parse_extraction_partial
    text='Group A: 7 men\nand 3 women. Group B: 10 men.'
    rows=[dict(report_unit_id=1,text=text,start=50,end=50+len(text),explicit_source_ids=[5],attribution_status='explicit_citation')]
    raw={'units':[{'report_unit_id':1,'claims':[
        {'quote':'7 men and 3 women.','assertion':'original composition'},
        {'quote':'Group B: 7 men.','assertion':'changed number'},
        {'quote':'Group B: 10 men.','assertion':'ten men'}],'limit':''}]}
    result=parse_extraction_partial(json.dumps(raw),rows)[0]
    assert len(result['claims'])==2 and len(result['unlocated_claims'])==1
    assert result['claims'][0]['binding']=='whitespace_only_original_span'
    assert result['claims'][0]['quote']=='7 men\nand 3 women.'
    for c in result['claims']:assert text[c['report_start']-50:c['report_end']-50]==c['quote']
    assert result['claims'][1]['claim_id']=='1:2'


def test_partial_comparison_isolates_bad_quote_duplicate_and_foreign_rows():
    from research_verify.literal_occurrences import parse_comparison_partial
    extracted=[{'claims':[{'claim_id':str(i)}for i in range(4)]}]
    units=[dict(source_id=5,unit_id=0,text='Original source.')]
    good=dict(claim_id='0',relation='supported',reason='x',evidence=[dict(source_id=5,unit_id=0,quote='Original source.')])
    bad={**good,'claim_id':'1','evidence':[dict(source_id=5,unit_id=0,quote='Changed source.')]}
    raw=dict(comparisons=[good,bad,{**good,'claim_id':'2'},{**good,'claim_id':'2'},{**good,'claim_id':'foreign'}])
    r=parse_comparison_partial(json.dumps(raw),extracted,units)
    assert r['comparisons'][0]['relation']=='supported'
    assert all(c['relation']is None for c in r['comparisons'][1:])
    assert len(r['unbound_rows'])==1 and r['comparisons'][1]['raw_rows']==[bad]
