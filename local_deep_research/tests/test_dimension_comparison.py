import copy,json
import pytest

from research_verify.dimension_comparison import DIMENSIONS,parse_dimension_comparisons,hypothetical_report
from research_verify.generation import SourceMaterial


def example():
    material=SourceMaterial('SOURCE ONE\nOriginal source text.',{5:dict(text='Original source text.',metadata='Source A'),
        6:dict(text='Other source text.',metadata='Source B')})
    anchors=[dict(anchor_id=0,text='First report occurrence.',start=0,end=24),dict(anchor_id=1,text='Second report occurrence.',start=26,end=51)]
    obs=[dict(observation_id=0,source_id=5),dict(observation_id=1,source_id=5)]
    row=dict(observation_id=0,source_supported='supported',source_evidence=[dict(source_id=5,quote='Original source text.')],
        report_dimensions={d:dict(source_fact='Source fact',report_fact='Report fact',state='match',reason='Fallible example opinion')for d in DIMENSIONS},
        mentions=[dict(anchor_id=i,relation='same_fact'if i==0 else'conflict')for i,a in enumerate(anchors)],
        state='conflict',request_quote='Original request',reason='Fallible model comparison')
    return material,anchors,obs,row


def test_multiple_literal_report_occurrences_survive_and_omission_stays_unassessed():
    m,a,o,row=example();before=copy.deepcopy(row)
    result=parse_dimension_comparisons(json.dumps(dict(comparisons=[row])),'Original request',m,a,o)
    assert [m['quote']for m in result[0]['mentions']]==[a['text']for a in a]and result[0]['report_anchor_ids']==[0,1]
    assert result[0]['mentions'][1]['start']==26
    assert result[0]['source_evidence'][0]['quote']=='Original source text.'
    assert result[1]['state']=='not_assessed'and row==before


@pytest.mark.parametrize('change',[
    lambda r:r['source_evidence'][0].update(source_id=6,quote='Other source text.'),
    lambda r:r['source_evidence'][0].update(quote='Paraphrased source'),
    lambda r:r['mentions'][0].update(anchor_id=99),
    lambda r:r['mentions'][0].update(quote='Paraphrased report'),
    lambda r:r['report_dimensions'].pop('group'),
    lambda r:r.update(observation_id=True),
    lambda r:r.update(request_quote='Invented criterion'),
])
def test_wrong_source_anchor_quote_or_request_never_binds(change):
    m,a,o,row=example();change(row)
    with pytest.raises(ValueError):parse_dimension_comparisons(json.dumps(dict(comparisons=[row])),'Original request',m,a,o)


def test_inconsistent_model_summary_is_preserved_as_diagnostic_not_rewritten_or_approved():
    m,a,o,row=example();row['state']='present';row['report_dimensions']['group']['state']='conflict'
    result=parse_dimension_comparisons(json.dumps(dict(comparisons=[row])),'Original request',m,a,o)[0]
    assert result['state']=='present'and result['dimension_summary_disagreement']is True
    assert result['assessment_status']=='unassessed_model_opinion'


def test_hypothetical_preview_keeps_untouched_occurrences_and_rejects_shifted_or_overlapping_spans():
    report='First A.\n\nSecond B.\n\nRepeated A.'
    p=dict(action='replace',anchor_start=0,anchor_end=8,anchor='First A.',addition='Revised A.')
    before=copy.deepcopy(p)
    assert hypothetical_report(report,[p])=='Revised A.'+report[8:]
    assert p==before and report.endswith('Repeated A.')
    with pytest.raises(ValueError):hypothetical_report(report,[p,p])
    with pytest.raises(ValueError):hypothetical_report(report,[dict(p,anchor_start=1)])
