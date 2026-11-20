import json

import pytest
from research_verify.generation import SourceMaterial
from research_verify.request_additions import parse_request_plan,parse_gaps,apply_confirmed_additions


def fixture():
    report='Title\nStudy A used RNA sequencing [1].\n\nOther supported detail [2].\n'
    requirements=[dict(requirement_id=0,request_quote='group sizes',description='Report per-group sample counts')]
    material=SourceMaterial('actual supplied material',{1:dict(text='Study A recruited 12 treated and 8 control participants.',metadata='')})
    proposal=dict(requirement_id=0,anchor='Study A used RNA sequencing [1].',
        addition='Study A recruited 12 treated and 8 control participants [1].',
        evidence_sources=[dict(source_id=1,quote='12 treated and 8 control participants')])
    return report,requirements,material,proposal


def test_only_explicit_located_request_plan_admitted():
    plan=parse_request_plan(json.dumps(dict(requirements=[dict(request_quote='group sizes',description='Counts by group')])), 'Please extract group sizes.')
    assert plan[0]['requirement_id']==0
    with pytest.raises(ValueError):parse_request_plan(json.dumps(dict(requirements=[dict(request_quote='impact factors',description='An invented requirement')])), 'Please extract group sizes.')


def test_omitted_coverage_stays_visible_and_quote_stitching_or_cross_source_cannot_authorize_addition():
    report,requirements,material,proposal=fixture()
    parsed=parse_gaps(json.dumps(dict(proposals=[proposal])),report,material,requirements)
    assert parsed['eligible']==[proposal]and parsed['coverage'][0]['status']=='not_assessed'
    for evidence in [[dict(source_id=2,quote='12 treated and 8 control participants')],
                     [dict(source_id=1,quote='12 treated ... 8 control')]]:
        changed={**proposal,'evidence_sources':evidence}
        parsed=parse_gaps(json.dumps(dict(proposals=[changed])),report,material,requirements)
        assert not parsed['eligible']and parsed['unresolved']


def test_independent_rejection_or_uncertainty_preserves_whole_report():
    report,_,_,proposal=fixture()
    fields=dict(explicitly_requested=True,source_supported=True,same_study_scope=True,
        placement_suitable=True,not_already_present=True,no_new_contradiction=True)
    for key in fields:
        decision=dict(candidate_index=0,**{**fields,key:None})
        answer,insertions,_=apply_confirmed_additions(json.dumps(dict(decisions=[decision])),report,[proposal])
        assert answer==report and insertions==[]
    answer,insertions,_=apply_confirmed_additions(json.dumps(dict(decisions=[dict(candidate_index=0,**fields)])),report,[proposal])
    assert proposal['addition']in answer
    assert answer.replace(insertions[0]['inserted_text'],'',1)==report
    assert 'Other supported detail [2].'in answer


def test_repeated_anchor_or_duplicate_confirmation_cannot_multiply_or_change_report():
    report,requirements,material,proposal=fixture()
    parsed=parse_gaps(json.dumps(dict(proposals=[proposal])),report+report,material,requirements)
    assert not parsed['eligible']
    with pytest.raises(ValueError):apply_confirmed_additions(json.dumps(dict(decisions=[dict(candidate_index=0),dict(candidate_index=0)])),report,[proposal])
