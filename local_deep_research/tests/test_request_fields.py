import json

import pytest

from research_verify.generation import SourceMaterial
from research_verify.request_fields import original_anchors,source_field_prompt,parse_source_fields
from research_verify.request_additions import parse_gaps,apply_confirmed_additions


def example():
    requirements=[dict(requirement_id=0,request_quote='sample counts',description='Counts by group')]
    material=SourceMaterial('ACTUAL SOURCE ONLY',{
        1:dict(text='Study A enrolled 12 treated and 8 control participants.',metadata=''),
        2:dict(text='Study B had 100 cells.',metadata='')})
    return requirements,material


def test_source_reader_has_no_report_and_wrong_source_or_stitched_quote_remain_unresolved():
    req,material=example()
    prompt=source_field_prompt('Report sample counts',req,material)
    assert 'ACTUAL SOURCE ONLY'in prompt and 'COMPLETE ORIGINAL REPORT'not in prompt
    fields=[dict(requirement_id=0,value='12 treated and 8 control',scope='Study A participants',quote='12 treated and 8 control participants'),
            dict(requirement_id=0,value='100 cells',scope='Study B',quote='Study B had 100 cells.'),
            dict(requirement_id=0,value='12 and 8',scope='Study A',quote='12 treated ... 8 control')]
    result=parse_source_fields(json.dumps(dict(sources=[dict(source_id=1,fields=fields)])),req,material)
    assert len(result['sources'][0]['fields'])==1 and len(result['rejected_fields'])==2
    assert result['sources'][1]['observation_status']=='not_assessed'
    assert result['sources'][1]['unresolved_requirements']==[0]
    assert result['quality_claim']is None
    with pytest.raises(ValueError):
        parse_source_fields(json.dumps(dict(sources=[dict(source_id=77)])),req,material)


def test_position_registry_disambiguates_repeated_original_text_without_fuzzy_rewriting():
    req,material=example();report='Study A used sequencing [1].\n\nStudy A used sequencing [1].\n'
    anchors=original_anchors(report)
    assert len(anchors)==2 and anchors[0]['text']==anchors[1]['text']
    proposal=dict(requirement_id=0,anchor_id=anchors[1]['anchor_id'],citation_source_ids=[1],
        addition='The same study enrolled 12 treated and 8 control participants.',
        evidence_sources=[dict(source_id=1,quote='12 treated and 8 control participants')],
        anchor_start=0,anchor_end=1)
    parsed=parse_gaps(json.dumps(dict(proposals=[proposal])),report,material,req,anchors=anchors)
    eligible=parsed['eligible'];assert len(eligible)==1
    assert eligible[0]['anchor_start']==anchors[1]['start']
    assert eligible[0]['addition'].endswith('[1]')
    decision=dict(candidate_index=0,explicitly_requested=True,source_supported=True,same_study_scope=True,
                  placement_suitable=True,not_already_present=True,no_new_contradiction=True)
    answer,insertions,_=apply_confirmed_additions(json.dumps(dict(decisions=[decision])),report,eligible)
    assert insertions[0]['position']==anchors[1]['end']
    assert answer[:anchors[1]['end']]==report[:anchors[1]['end']]
    assert answer.replace(insertions[0]['inserted_text'],'',1)==report
    decision['source_supported']=None
    assert apply_confirmed_additions(json.dumps(dict(decisions=[decision])),report,eligible)[0]==report


def test_registered_anchor_cannot_authorize_unquoted_or_conflicting_citation_scope():
    req,material=example();report='Study A used sequencing [1].';anchors=original_anchors(report)
    base=dict(requirement_id=0,anchor_id=0,citation_source_ids=[1],addition='A useful factual addition',
        evidence_sources=[dict(source_id=1,quote='12 treated and 8 control participants')])
    for changed in [dict(anchor_id=99),dict(citation_source_ids=[2]),dict(citation_source_ids=[{}]),
                    dict(addition='A useful factual addition [2]')]:
        result=parse_gaps(json.dumps(dict(proposals=[{**base,**changed}])),report,material,req,anchors=anchors)
        assert not result['eligible']and result['unresolved']
