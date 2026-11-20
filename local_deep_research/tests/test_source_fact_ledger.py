import json
from research_verify.source_fact_ledger import parse_ledger,parse_attribute_comparisons


def test_ledger_copies_original_units_and_retains_invalid_rows():
    unit=dict(source_id=5,unit_id=3,text='7 men\n3 women',text_sha256='test')
    fact=dict(fact_id=0,subject='cohort',attribute='composition',value='7/3',scope='one platform',unit_ids=[3])
    r=parse_ledger(json.dumps(dict(facts=[fact,{**fact,'fact_id':1,'unit_ids':[9]}],limitations='limited')),[unit])
    assert r['facts'][0]['evidence_units']==[unit]and len(r['unbound_facts'])==1


def test_attribute_unbound_row_does_not_suppress_other_claim_or_approve_missing():
    extracted=[dict(claims=[dict(claim_id=str(i))for i in range(3)])];units=[dict(source_id=5,unit_id=3,text='Original')]
    finding=dict(attribute='group',relation='differs',report_value='A',source_value='B',unit_ids=[3])
    good=dict(claim_id='0',relation='contradicted',attribute_findings=[finding],reason='different')
    bad={**good,'claim_id':'1','attribute_findings':[{**finding,'unit_ids':[99]}]}
    r=parse_attribute_comparisons(json.dumps(dict(comparisons=[good,bad])),extracted,units)['comparisons']
    assert r[0]['relation']=='contradicted'and r[0]['attribute_findings'][0]['evidence_units']==units
    assert r[1]['relation']is None and r[2]['relation']is None


def test_oversized_auxiliary_limit_does_not_hide_valid_fact():
    from research_verify.source_fact_ledger import parse_ledger_partial
    unit=dict(source_id=5,unit_id=0,text='Original')
    fact=dict(fact_id=0,subject='s',attribute='a',value='v',scope='scope',unit_ids=[0])
    raw=dict(facts=[fact],limitations='x'*801)
    r=parse_ledger_partial(json.dumps(raw),[unit])
    assert len(r['facts'])==1 and r['limitations']==''and r['unbound_limitations']['raw']==raw['limitations']


def test_reference_presentation_is_lossless_and_rejects_stale_units():
    import pytest
    from research_verify.source_fact_ledger import reference_ledger
    unit=dict(source_id=5,unit_id=0,text='Original 7 men\n3 women.')
    fact=dict(fact_id=0,subject='cohort',attribute='group',value='7/3',scope='platform',unit_ids=[0],source_id=5,evidence_units=[unit])
    ledger=dict(facts=[fact],limitations='limited',unbound_facts=[])
    shown=reference_ledger(ledger,[unit]);f=shown['facts'][0]
    assert {k:v for k,v in f.items()if k!='evidence_unit_refs'}=={k:v for k,v in fact.items()if k!='evidence_units'}
    assert f['evidence_unit_refs']==[dict(source_id=5,unit_id=0)]and ledger['facts'][0]['evidence_units']==[unit]
    with pytest.raises(ValueError):reference_ledger(ledger,[{**unit,'text':'Changed'}])
