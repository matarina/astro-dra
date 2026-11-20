import json

from research_verify.generation import SourceMaterial
from research_verify.request_fields import original_anchors
from research_verify.request_additions import apply_confirmed_additions
from research_verify.canonical_fields import source_units,parse_unit_fields,parse_unit_gaps,unit_field_prompt


def example():
    material=SourceMaterial('Actual supplied source material',{
        5:dict(text='Study A used 10 samples ( [article-ref:18]).\n\nIndependent spatial cohort: 24 specimens, 200 cells.',metadata='Date: 2026'),
        6:dict(text='Study B enrolled 900 participants.',metadata='')})
    req=[dict(requirement_id=0,request_quote='counts by modality',description='Counts by modality')]
    return material,req,source_units(material,{5})


def test_units_copy_original_intervals_reference_spacing_and_own_source_only():
    material,req,units=example()
    for unit in units:
        actual=material.views[5]['metadata'if unit['kind']=='metadata'else'text']
        assert actual[unit['start']:unit['end']]==unit['text']
    selected=next(u for u in units if 'article-ref'in u['text'])
    field=dict(requirement_id=0,study='A',modality='single-cell',group='original group',quantity_unit='samples',value='10',unit_id=selected['unit_id'])
    parsed=parse_unit_fields(json.dumps(dict(sources=[dict(source_id=5,fields=[field])])),req,units)
    assert parsed['sources'][0]['fields'][0]['quote']=='Study A used 10 samples ( [article-ref:18]).'
    assert parsed['quality_claim']is None
    bad={**field,'unit_id':999}
    parsed=parse_unit_fields(json.dumps(dict(sources=[dict(source_id=5,fields=[bad])])),req,units)
    assert not parsed['sources'][0]['fields']and parsed['sources'][0]['unresolved_requirements']==[0]
    assert 'COMPLETE ORIGINAL REPORT'not in unit_field_prompt('counts by modality',req,units)


def test_existing_source_units_exceeding_transport_bound_are_not_reported_as_missing_source():
    material=SourceMaterial('Actual material',{5:dict(text='A.\n\nB.\n\nC.\n\nD.\n\nE.',metadata='')})
    units=source_units(material,{5});assert len(units)==5
    report='Original [5].';req=[dict(requirement_id=0)]
    proposal=dict(requirement_id=0,anchor_id=0,citation_source_ids=[5],addition='Proposed different statement [5].',
        evidence_units=[dict(source_id=5,unit_id=u['unit_id'])for u in units])
    r=parse_unit_gaps(json.dumps(dict(proposals=[proposal])),report,material,req,original_anchors(report),{5})
    assert not r['eligible']and r['unresolved'][0]['reason']=='invalid_evidence_unit_count_namespace_or_duplicate'
    assert len(r['unresolved'][0]['proposal']['evidence_units'])==5
    assert r['unresolved'][0]['downstream_reason']=='missing_source_quotation'


def test_opt_in_attribute_reading_keeps_same_unit_different_stages_and_rejects_unbound_labels():
    material,req,units=example();u=next(u for u in units if u['kind']=='text')
    base=dict(requirement_id=0,study='A',modality='method',group='group',quantity_unit='not_applicable',value='Reported value',unit_id=u['unit_id'])
    fields=[dict(base,attribute='processing purpose',procedure_stage='before'),
            dict(base,attribute='processing purpose',procedure_stage='after')]
    raw=json.dumps(dict(sources=[dict(source_id=5,fields=fields)]))
    parsed=parse_unit_fields(raw,req,units,atomic_attributes=True)
    actual=parsed['sources'][0]['fields'];assert len(actual)==2
    assert actual[0]['quote']==actual[1]['quote']==u['text']
    assert actual[0]['scope']!=actual[1]['scope']
    bad=parse_unit_fields(json.dumps(dict(sources=[dict(source_id=5,fields=[base])])),req,units,atomic_attributes=True)
    assert not bad['sources'][0]['fields']and bad['rejected_fields']
    default=unit_field_prompt('Original question',req,units)
    assert '"attribute"'not in default
    assert '"attribute"'in unit_field_prompt('Original question',req,units,atomic_attributes=True)


def test_unit_binding_is_not_semantic_approval_and_unknown_confirmation_retains_report():
    material,req,units=example();report='Existing study summary [5].';anchors=original_anchors(report)
    uid=next(u['unit_id']for u in units if 'spatial cohort'in u['text'])
    proposal=dict(requirement_id=0,anchor_id=0,citation_source_ids=[5],addition='A proposed interpretation.',
                  evidence_units=[dict(source_id=5,unit_id=uid)])
    parsed=parse_unit_gaps(json.dumps(dict(proposals=[proposal])),report,material,req,anchors,{5})
    assert len(parsed['eligible'])==1
    assert parsed['eligible'][0]['evidence_sources'][0]['quote']=='Independent spatial cohort: 24 specimens, 200 cells.'
    answer,insertions,_=apply_confirmed_additions(json.dumps(dict(decisions=[dict(candidate_index=0,source_supported=None)])),report,parsed['eligible'])
    assert answer==report and insertions==[]
    for changed in [dict(evidence_units=[dict(source_id=6,unit_id=uid)]),dict(citation_source_ids=[6]),
                    dict(evidence_sources=[dict(source_id=5,quote='invented')])]:
        rejected=parse_unit_gaps(json.dumps(dict(proposals=[{**proposal,**changed}])),report,material,req,anchors,{5})
        assert not rejected['eligible']and rejected['unresolved']


def test_multi_requirement_observation_keeps_literal_scope_and_partial_unknowns():
    material,req,units=example()
    req.append(dict(requirement_id=1,request_quote='counts by modality',description='Group design'))
    unit=next(u for u in units if 'spatial cohort' in u['text'])
    field=dict(requirement_ids=[0,1],study='A',modality='spatial',group='independent',quantity_unit='specimens',value='24',unit_id=unit['unit_id'])
    raw=json.dumps(dict(sources=[dict(source_id=5,fields=[field],unresolved_requirements=[1])]))
    parsed=parse_unit_fields(raw,req,units,multi_requirement=True)
    result=parsed['sources'][0]
    assert len(result['fields'])==1 and result['fields'][0]['requirement_ids']==[0,1]
    assert result['fields'][0]['quote']==unit['text'] and result['unresolved_requirements']==[1]
    assert parsed['quality_claim'] is None
    assert '"requirement_ids":[0]' in unit_field_prompt('request',req,units,multi_requirement=True)
    assert '"requirement_ids"' not in unit_field_prompt('request',req,units)


def test_multi_requirement_rejects_unbound_or_ambiguous_associations():
    material,req,units=example();unit=next(u for u in units if u['kind']=='text')
    base=dict(study='A',modality='single-cell',group='new',quantity_unit='samples',value='10',unit_id=unit['unit_id'])
    for bad in [[],[0,0],[True],[99],'0']:
        raw=json.dumps(dict(sources=[dict(source_id=5,fields=[dict(base,requirement_ids=bad)])]))
        parsed=parse_unit_fields(raw,req,units,multi_requirement=True)
        assert not parsed['sources'][0]['fields'] and parsed['rejected_fields']
    mixed=dict(base,requirement_id=0,requirement_ids=[0])
    parsed=parse_unit_fields(json.dumps(dict(sources=[dict(source_id=5,fields=[mixed])])),req,units,multi_requirement=True)
    assert not parsed['sources'][0]['fields']
