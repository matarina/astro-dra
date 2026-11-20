"""Offline candidate seams; exercise formatter/persistence without writer/model."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_verify.generation import format_source_documents, refresh_candidate_attachment_receipts
from research_verify.paragraph_bundle_candidate import (
    SETTING, build_request_bundle_context, persist_bundle_writer_receipt,
    prepare_bundle_candidate,
)


def _runner():
    path = Path(__file__).parents[2] / 'scripts/run_hallucination_next_phase_experiment_20261113.py'
    spec = importlib.util.spec_from_file_location('bundle_candidate_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documents():
    return [SimpleNamespace(page_content=text, metadata={
        'index': source_id, 'title': f'Synthetic {source_id}',
        'source': f'https://example.invalid/{source_id}'}) for source_id, text in (
            (701, '# Calibration\n\nCalibration uses a reference.\n\nKeep this adjacent qualifier.'),
            (702, '# その他\n\nUnrelated acquired prose.'),
        )]


class _Trace:
    def __init__(self):
        self.events = []

    def record(self, name, value):
        self.events.append((name, value))


def _handler(enabled):
    return SimpleNamespace(get_setting=lambda key, default=None: enabled if key == SETTING else default)


def test_enabled_candidate_prepares_formats_and_persists_final_receipts(tmp_path):
    docs = _documents()
    request = 'Explain calibration'
    context, plan, planning = prepare_bundle_candidate(
        _handler(True), request, docs, [], context_chars=5000)
    assert len(plan.selected) >= 1
    assert plan.selected[0].text.endswith('Keep this adjacent qualifier.')
    assert [f['text'] for f in planning['fields']] == [request]
    assert any(o['state'] in {'seeded', 'structural_seed_fallback', 'unseeded_unknown'} for o in planning['opportunities'])
    native = []
    material = format_source_documents(docs, max_chars=20000, reading_scope=[],
                                       candidate_passages=context, candidate_attachment_receipts=native)
    refresh_candidate_attachment_receipts(native, material, material.views, context)
    rows = [dict(batch=1, context_chars=len(material),
                 context_sha256=hashlib.sha256(str(material).encode()).hexdigest(),
                 candidate_attachment_receipts=native)]
    trace = _Trace()
    persist_bundle_writer_receipt(rows, plan, planning, material, list(material.views), native, trace, 1)
    receipt = rows[0]['paragraph_bundle_receipts']
    delivered = receipt['delivery_receipts'][0]
    assert delivered['delivery_state'] == 'partial_after_formatting'
    assert delivered['bound_delivered_offsets'] == [(plan.selected[0].start, plan.selected[0].end)]
    assert delivered['source_sha256'] == hashlib.sha256(docs[0].page_content.encode()).hexdigest()
    assert receipt['final_material_sha256'] == rows[0]['context_sha256']
    assert receipt['final_registry_ids'] == [701, 702]
    assert trace.events[0][0] == 'paragraph_bundle_writer_context'
    # Same nested row shape is copied by the existing result/summary serializer.
    restored = json.loads(json.dumps({'candidate_attachment_receipts': rows}))
    assert restored['candidate_attachment_receipts'][0]['paragraph_bundle_receipts']['planning']['enabled']
    (tmp_path / 'wiring.json').write_text(json.dumps(restored, ensure_ascii=False, indent=2))


@pytest.mark.parametrize('enabled,gap_context', [(False, None), (False, []), (False, [{'text': 'legacy'}]), (True, None)])
def test_disabled_baseline_and_existing_gap_hooks_are_identity_preserved(enabled, gap_context, monkeypatch):
    import research_verify.paragraph_bundle_candidate as candidate
    def forbidden(*args, **kwargs):
        raise AssertionError('disabled path must not index/plan bundles')
    monkeypatch.setattr(candidate, 'build_request_bundle_context', forbidden)
    actual, plan, planning = prepare_bundle_candidate(
        _handler(enabled), 'request', _documents(), gap_context, context_chars=5000)
    assert actual is gap_context and plan is planning is None
    rows = [{'legacy': 'unchanged'}]
    before = copy.deepcopy(rows)
    trace = _Trace()
    persist_bundle_writer_receipt(rows, plan, planning, '', [], [], trace, 1)
    assert rows == before and trace.events == []


def test_runner_flag_is_candidate_only_and_default_off():
    runner = _runner()
    assert runner.PARAGRAPH_BUNDLES is False
    assert not any(runner._paragraph_bundle_enabled(arm) for arm in runner.ARMS)
    runner.PARAGRAPH_BUNDLES = True
    assert [arm for arm in runner.ARMS if runner._paragraph_bundle_enabled(arm)] == ['evidence_gap']


def test_enabled_runner_ignores_case_questions_feedback_and_draft_citations():
    runner = _runner()
    docs = _documents()
    sources = [dict(index=d.metadata['index'], title=d.metadata['title'], body=d.page_content,
                    content_type='full_text') for d in docs]
    case = dict(query='Explain calibration', questions=['EVALUATOR_SENTINEL'])
    first = runner._gap_receipt(case, sources, context_budget=5000,
                                draft='priority [702]', paragraph_bundles=True)
    second = runner._gap_receipt({**case, 'questions': ['DIFFERENT_SENTINEL'],
                                 'feedback': 'FORBIDDEN_FEEDBACK'}, sources, context_budget=5000,
                                draft='priority [701]', paragraph_bundles=True)
    assert first == second
    assert 'SENTINEL' not in json.dumps(first) and 'FORBIDDEN_FEEDBACK' not in json.dumps(first)
    assert first['paragraph_bundle_planning']['fields'][0]['text'] == case['query']
    assert first['writer_context'][0]['source_id'] == 701
    assert all(row['field'] != 'priority_source' for row in first['writer_context'])


def test_disabled_runner_gap_receipt_matches_legacy_default():
    runner = _runner()
    source = dict(index=701, body='Calibration uses a reference.', content_type='full_text')
    case = dict(query='Explain calibration', questions=['calibration'])
    assert runner._gap_receipt(case, [source], draft='[701]') == runner._gap_receipt(
        case, [source], draft='[701]', paragraph_bundles=False)


def test_writer_flow_uses_prepare_and_final_persistence_seams():
    from research_verify import evidence_flow
    tree = ast.parse(Path(evidence_flow.__file__).read_text())
    calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert 'prepare_bundle_candidate' in calls
    assert 'persist_bundle_writer_receipt' in calls


def test_unserved_fields_and_zero_budget_stay_explicit():
    context, plan, planning = build_request_bundle_context(_documents(), 'Explain calibration', context_chars=0)
    assert context == [] and plan.context_chars == 0
    assert any(r['state'] == 'omitted' for r in planning['planning_receipts'])
    assert all(o['state'] in {'seeded', 'structural_seed_fallback', 'unseeded_unknown'} for o in planning['opportunities'])


def test_formatter_omitted_bundle_is_persisted_as_omitted():
    docs = _documents()
    context, plan, planning = build_request_bundle_context(docs, 'Explain calibration', context_chars=5000)
    native = []
    material = format_source_documents([docs[1]], max_chars=20000, reading_scope=[],
                                       candidate_passages=context, candidate_attachment_receipts=native)
    rows = [{}]
    persist_bundle_writer_receipt(rows, plan, planning, material, list(material.views), native, _Trace(), 1)
    receipt = rows[0]['paragraph_bundle_receipts']['delivery_receipts'][0]
    assert receipt['delivery_state'] == 'omitted_after_formatting'
    assert receipt['registry_state'] == 'registry_absent'
