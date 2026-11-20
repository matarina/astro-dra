import json

import pytest

from research_verify.generation import SourceMaterial
from research_verify.request_fields import original_anchors
from research_verify.canonical_fields import source_units
from research_verify.citation_field_scope import citation_report_scope,observation_source_scope,parse_scoped_comparison


def test_all_target_citations_and_uncited_table_context_are_retained_without_attribution():
    report=('Study A reports ten male participants [5].\n\n'
        'An uncited table cell describes seven male and three female participants.\n\n'
        'A different paper reports a different group [6].\n\n'
        'Study A later reports a different sex composition [5].')
    scope=citation_report_scope(report,5,original_anchors(report))
    rows=scope['report_units'];joined='\n'.join(r['text']for r in rows)
    assert 'ten male participants'in joined and 'different sex composition'in joined
    context=next(r for r in rows if 'uncited table cell'in r['text'])
    assert context['attribution_status']=='unassigned_context_only'and context['explicit_source_ids']==[]
    assert 'A different paper'not in joined
    for row in rows:assert report[row['start']:row['end']]==row['text']


def test_source_scope_preserves_reference_tokens_and_rejects_stale_observation_binding():
    material=SourceMaterial('source',{5:dict(text='Context.\n\nMeasured 10 specimens ( [article-ref:2]).\n\nNeighbor context.',metadata='Study A')})
    units=source_units(material,{5});unit=next(u for u in units if 'specimens'in u['text'])
    observation=dict(source_id=5,unit_id=unit['unit_id'],unit_sha256=unit['text_sha256'],quote=unit['text'])
    scope=observation_source_scope(material,observation)
    assert unit in scope['units']and 'not the complete article'in scope['scope']
    with pytest.raises(ValueError):observation_source_scope(material,{**observation,'quote':'Measured 10 specimens ([article-ref:2]).'})


def test_unknown_and_unchecked_occurrences_stay_visible_and_unregistered_locations_fail():
    scope=dict(report_units=[dict(report_unit_id=1,anchor_id=8),dict(report_unit_id=2,anchor_id=9)])
    raw=dict(observation_id=3,request_quote='sample counts',checked_report_unit_ids=[1],
        quantity_present_anywhere=True,group_and_unit_consistent=None,missing_requested_detail=None,conflict_found=None,
        occurrences=[dict(report_unit_id=1,relation='uncertain')],reason='Insufficient source scope.')
    result=parse_scoped_comparison(json.dumps(raw),'Report sample counts',dict(observation_id=3),scope)
    assert result['unchecked_report_unit_ids']==[2]and result['group_and_unit_consistent']is None
    assert result['report_anchor_ids']==[8]
    for changed in [dict(checked_report_unit_ids=[99]),dict(request_quote='invented criterion'),dict(conflict_found='true')]:
        with pytest.raises(ValueError):parse_scoped_comparison(json.dumps({**raw,**changed}),'Report sample counts',dict(observation_id=3),scope)
