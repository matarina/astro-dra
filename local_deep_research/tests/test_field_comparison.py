import json

import pytest

from research_verify.field_comparison import observations_from_notes,parse_comparisons,apply_confirmed_edits


def test_exact_observation_dedup_keeps_distinct_source_and_modality_scope():
    f=dict(requirement_id=0,study='A',modality='RNA',group='treated',quantity_unit='people',value='12',unit_id=1,unit_sha256='sha',quote='Original data')
    notes=[dict(sources=[dict(source_id=5,fields=[f,{**f,'requirement_id':1},{**f,'modality':'spatial'}]),
                         dict(source_id=6,fields=[f])])]
    observations=observations_from_notes(notes)
    assert len(observations)==3 and observations[0]['requirement_ids']==[0,1]
    assert observations[1]['modality']=='spatial'and observations[2]['source_id']==6


def test_mixed_associations_preserve_literal_scope_and_do_not_mutate_notes():
    f=dict(study='A',modality='RNA',group='treated',quantity_unit='people',value='12',
           unit_id=1,unit_sha256='sha',quote='Original data',scope='new samples')
    notes=[dict(sources=[dict(source_id=5,fields=[dict(f,requirement_id=0),
        dict(f,requirement_ids=[1,0]),dict(f,requirement_ids=[1],quote='Other literal data'),
        dict(f,requirement_ids=[1],quantity_unit='specimens')]),
        dict(source_id=6,fields=[dict(f,requirement_ids=[0,1])])])]
    before=json.dumps(notes,sort_keys=True)
    obs=observations_from_notes(notes,[dict(requirement_id=i)for i in [0,1]])
    assert len(obs)==4 and obs[0]['requirement_ids']==[0,1]
    assert obs[0]['quote']=='Original data'and obs[1]['quote']=='Other literal data'
    assert obs[2]['quantity_unit']=='specimens'and obs[3]['source_id']==6
    obs[0]['requirement_ids'].append(3)
    assert json.dumps(notes,sort_keys=True)==before


@pytest.mark.parametrize('association',[
    {},dict(requirement_id=0,requirement_ids=[0]),dict(requirement_ids=[]),
    dict(requirement_ids=[0,0]),dict(requirement_ids=[True]),
    dict(requirement_ids=[-1]),dict(requirement_ids=[9]),dict(requirement_ids='0'),
])
def test_ambiguous_or_unregistered_associations_are_not_silently_inferred(association):
    notes=[dict(sources=[dict(source_id=5,fields=[association])])]
    with pytest.raises(ValueError):
        observations_from_notes(notes,[dict(requirement_id=0)])


def test_missing_comparisons_remain_unassessed_and_original_matches_must_locate():
    obs=[dict(observation_id=0),dict(observation_id=1)];anchors=[dict(anchor_id=4)]
    result=parse_comparisons(json.dumps(dict(comparisons=[dict(observation_id=0,state='missing',request_quote='group counts',report_anchor_ids=[])])),
        'Report group counts',anchors,obs)
    assert result[1]['state']=='not_assessed'
    for change in [dict(state='present'),dict(request_quote='invented criterion'),dict(report_anchor_ids=[99])]:
        row={**result[0],**change}
        with pytest.raises(ValueError):parse_comparisons(json.dumps(dict(comparisons=[row])),'Report group counts',anchors,obs)


def test_addition_and_source_corrected_replacement_preserve_untouched_report_and_unknown_rejects():
    report='Original A [5].\n\nCorrect B [6].\n\nOriginal C [5].'
    a='Original A [5].';c='Original C [5].';start=report.index(c)
    proposals=[dict(action='add',anchor_start=0,anchor_end=len(a),anchor=a,addition='New requested fact [5].'),
        dict(action='replace',anchor_start=start,anchor_end=start+len(c),anchor=c,addition='Corrected C [5].')]
    flags=dict(explicitly_requested=True,source_supported=True,same_study_scope=True,edit_needed=True,retains_correct_content=True,no_new_error=True)
    decisions=[dict(candidate_index=i,**flags)for i in range(2)]
    answer,changes,_=apply_confirmed_edits(json.dumps(dict(decisions=decisions)),report,proposals)
    assert answer==a+'\n\nNew requested fact [5].\n'+report[len(a):start]+'Corrected C [5].'
    assert 'Correct B [6].'in answer and len(changes)==2
    for field in flags:
        withheld=[{**d,field:None}for d in decisions]
        assert apply_confirmed_edits(json.dumps(dict(decisions=withheld)),report,proposals)[0]==report
    overlap=[proposals[1],proposals[1]]
    with pytest.raises(ValueError):apply_confirmed_edits(json.dumps(dict(decisions=decisions)),report,overlap)
