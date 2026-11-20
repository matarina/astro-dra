import json

from research_verify.generation import SourceMaterial
from research_verify.request_fields import original_anchors
from research_verify.field_comparison import apply_confirmed_edits
from research_verify.span_edits import parse_span_edits


def setup_case():
    # Flattened Unicode table; a local field correction must not regenerate row.
    report = 'Introduction.\n\n空间  SeekSpace  患者1至10  10例（均为男\n性）  每切片细胞核数（N）[5]\n\nLater correct content.'
    anchors = original_anchors(report)
    aid = next(a['anchor_id'] for a in anchors if 'SeekSpace' in a['text'])
    material = SourceMaterial('Supplied text', {5: dict(text='The spatial cohort has ten participants.', metadata='')})
    req = [dict(requirement_id=0)]
    proposal = dict(action='replace', observation_ids=[0], requirement_id=0, anchor_id=aid,
        citation_source_ids=[5], addition='10例（7男3女）', evidence_units=[dict(source_id=5, unit_id=0)],
        replacement_span=dict(original_text='10例（均为男\n性）', occurrence=0))
    return report, material, req, anchors, proposal


def parse(case, proposal):
    report, material, req, anchors, _ = case
    return parse_span_edits(json.dumps(dict(proposals=[proposal])), report, material, req,
                            anchors, {5}, [dict(observation_id=0)])


def test_flattened_row_subspan_keeps_identifiers_metric_method_and_surrounding_bytes():
    case = setup_case();report, _, _, _, proposal = case
    parsed = parse(case, proposal)
    assert len(parsed['eligible']) == 1
    # Deliberately unsupported numerical interpretation can bind syntactically:
    # this test proves preservation, never source entailment or correction.
    decision = dict(candidate_index=0, explicitly_requested=True, source_supported=True,
        same_study_scope=True, edit_needed=True, retains_correct_content=True, no_new_error=True)
    answer, changes, _ = apply_confirmed_edits(json.dumps(dict(decisions=[decision])), report, parsed['eligible'])
    assert answer == report.replace('10例（均为男\n性）', '10例（7男3女）')
    assert all(text in answer for text in ['SeekSpace', '患者1至10', '每切片细胞核数（N）[5]'])
    assert len(changes) == 1
    assert apply_confirmed_edits('{"decisions":[]}', report, parsed['eligible'])[0] == report


def test_unlocated_whole_anchor_or_empty_subspan_is_unresolved_not_fallback_to_row_replace():
    case = setup_case();_, _, _, anchors, p = case
    whole = next(a['text'] for a in anchors if a['anchor_id'] == p['anchor_id'])
    for spec in [dict(original_text='invented', occurrence=0), dict(original_text=whole, occurrence=0),
                 dict(original_text='', occurrence=0), dict(original_text='SeekSpace', occurrence=True),
                 dict(original_text='SeekSpace', occurrence=7)]:
        result = parse(case, dict(p, replacement_span=spec))
        assert not result['eligible'] and result['unresolved']
    assert not parse(case, dict(p, addition='  '))['eligible']


def test_repeated_literal_uses_model_selected_occurrence_without_changing_other_occurrence():
    case = list(setup_case());case[0] = 'Alpha 10; Beta 10 [5].';case[3] = original_anchors(case[0])
    p = dict(case[4], anchor_id=0, addition='11', replacement_span=dict(original_text='10', occurrence=1))
    result = parse(case, p)
    assert result['eligible'][0]['addition'] == 'Alpha 10; Beta 11 [5].'
    assert result['eligible'][0]['subspan_binding']['start'] == case[0].rindex('10')
