"""Synthetic formatter-boundary checks; adapters below are test-only.

The existing formatter does not natively emit the helper's JSON card wire format.
An envelope test checks exact wire preservation; raw-source tests check its actual
candidate path with explicitly bound source/material coordinates, never prose-only
matching. No runner, model or production adapter is used.
"""

import hashlib
import json
from types import SimpleNamespace

from research_verify.coverage_planner import (
    generate_paragraph_bundles, index_source_structure,
    paragraph_bundle_delivery_receipts, plan_paragraph_bundles,
    serialize_paragraph_bundles,
)
from research_verify.generation import format_source_documents


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _fixtures():
    # Opaque synthetic handles, unrelated to any evaluated packet namespace.
    return [index_source_structure(text, source_id=handle) for handle, text in (
        (401, '# Alpha\n\nShared synthetic sentence.\n\nAlpha qualifier.'),
        (402, '# 第二節\n\n独立した段落。\n\n別の条件。'),
        (403, '# Gamma\n\nShared synthetic sentence.\n\nGamma qualifier.'),
    )]


def _plan(sources):
    candidates = [b for s in sources for b in generate_paragraph_bundles(
        s, {0: ('requested_attribute',)}, adjacent_paragraphs=0)]
    plan = plan_paragraph_bundles(candidates, context_chars=10000, canonical_sources=sources)
    assert len(plan.selected) == len(sources)
    assert all(r['delivery_state'] == 'not_observed' for r in plan.receipts)
    return plan


def _document(source, text=None, *, padding=''):
    return SimpleNamespace(page_content=source.text if text is None else text, metadata={
        'index': source.source_id, 'title': f'Synthetic {source.source_id}' + padding,
        'source': f'https://example.invalid/synthetic/{source.source_id}',
    })


def _candidate_rows(plan):
    return [dict(source_id=b.source.source_id, field='requested_attribute',
                 start=b.start, end=b.end, text=b.text,
                 source_text_sha256=b.source.sha256, text_sha256=_sha(b.text),
                 method='synthetic_bundle_adapter') for b in plan.selected]


def _raw_source_spans(plan, material):
    """Bind from actual registry blocks/complete text, not global text search.

    This adapter deliberately supports only the complete source-body view used by
    these small fixtures. It rejects excerpts and does not guess their offsets.
    """
    spans = []
    for bundle in plan.selected:
        view = material.views.get(bundle.source.source_id)
        if view is None:
            continue
        assert view['text'] == bundle.source.text
        assert view['available_sha256'] == bundle.source.sha256
        block = view['block']
        # Require a unique source-scoped block even when its prose is duplicated.
        assert str(material).count(block) == 1
        block_start = str(material).index(block)
        marker = 'BEGIN SOURCE TEXT\n'
        body_start = block_start + block.index(marker) + len(marker)
        assert str(material)[body_start:body_start + len(bundle.source.text)] == bundle.source.text
        spans.append(dict(source_id=bundle.source.source_id,
                          source_sha256=bundle.source.sha256,
                          source_start=bundle.start, source_end=bundle.end,
                          material_start=body_start + bundle.start,
                          material_end=body_start + bundle.end))
    return spans


def _assert_provenance(plan, sources, material, receipts):
    by_source = {b.source.source_id: b for b in plan.selected}
    registry = sorted(str(i) for i in material.views)
    registry_sha = _sha(json.dumps(registry, ensure_ascii=False))
    assert len(receipts) == len(plan.selected)
    for receipt in receipts:
        bundle = by_source[receipt['source_id']]
        assert receipt['source_sha256'] == bundle.source.sha256 == _sha(bundle.source.text)
        assert (receipt['start'], receipt['end']) == (bundle.start, bundle.end)
        assert bundle.text == bundle.source.text[receipt['start']:receipt['end']]
        assert receipt['text_sha256'] == _sha(bundle.text)
        assert receipt['final_material_sha256'] == _sha(str(material))
        assert receipt['final_material_chars'] == len(str(material))
        assert receipt['final_source_registry'] == registry
        assert receipt['final_registry_sha256'] == registry_sha
        assert receipt['serialized_chars'] == len(serialize_paragraph_bundles([bundle]))
    # Independent canonical binding remains required at this boundary.
    assert all(s.sha256 == _sha(s.text) for s in sources)


def _persist_case(tmp_path, plan, sources, material, receipts, budget, mode, native_receipts):
    # Persist synthetic execution receipts for the integration audit, not reports.
    record = dict(mode=mode, budget_chars=budget, final_material_chars=len(material),
                  final_material_sha256=_sha(str(material)),
                  registry_ids=sorted(material.views),
                  plan_context_sha256=plan.context_sha256,
                  plan_context_chars=plan.context_chars,
                  canonical_sources=[dict(source_id=s.source_id, sha256=s.sha256)
                                     for s in sources], receipts=receipts,
                  native_candidate_attachment_receipts=native_receipts)
    (tmp_path / 'integration.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))


def test_formatter_preserves_exact_bundle_wire_envelopes(tmp_path):
    sources = _fixtures()
    plan = _plan(sources)
    # Wire-envelope docs are intentionally not original acquired-source docs.
    docs = [_document(b.source, serialize_paragraph_bundles([b])) for b in plan.selected]
    views = []
    native_receipts = []
    material = format_source_documents(docs, max_chars=20000, reading_scope=views,
                                       candidate_attachment_receipts=native_receipts)
    receipts = paragraph_bundle_delivery_receipts(
        plan, str(material), final_source_registry=list(material.views), canonical_sources=sources)
    assert {r['delivery_state'] for r in receipts} == {'attached_exact'}
    assert set(material.views) == {401, 402, 403}
    assert len(material) <= 20000
    assert native_receipts[0]['final_source_material_sha256'] == _sha(str(material))
    for b in plan.selected:
        assert material.views[b.source.source_id]['available_sha256'] == _sha(
            serialize_paragraph_bundles([b]))
    _assert_provenance(plan, sources, material, receipts)
    _persist_case(tmp_path, plan, sources, material, receipts, 20000, 'wire_envelope', native_receipts)


def test_formatter_raw_candidates_have_bound_partial_delivery(tmp_path):
    sources = _fixtures()
    plan = _plan(sources)
    native_receipts = []
    material = format_source_documents(
        [_document(s) for s in sources], max_chars=20000, reading_scope=[],
        candidate_passages=_candidate_rows(plan), candidate_attachment_receipts=native_receipts)
    receipts = paragraph_bundle_delivery_receipts(
        plan, str(material), delivered_spans=_raw_source_spans(plan, material),
        final_source_registry=list(material.views), canonical_sources=sources)
    assert {r['delivery_state'] for r in receipts} == {'partial_after_formatting'}
    assert all(r['bound_delivered_offsets'] == [(r['start'], r['end'])] for r in receipts)
    assert native_receipts[0]['attached_count'] == 3
    assert native_receipts[0]['final_registry_ids'] == [401, 402, 403]
    assert native_receipts[0]['final_source_material_sha256'] == _sha(str(material))
    for card in native_receipts[0]['cards']:
        bundle = next(b for b in plan.selected if b.source.source_id == card['source_id'])
        assert card['source_text_sha256'] == bundle.source.sha256
        assert card['offsets'] == {'start': bundle.start, 'end': bundle.end}
        assert card['delivery_binding']['source_id'] == bundle.source.source_id
        assert card['delivery_binding']['source_text_sha256'] == bundle.source.sha256
    _assert_provenance(plan, sources, material, receipts)
    _persist_case(tmp_path, plan, sources, material, receipts, 20000, 'raw_source_candidates', native_receipts)


def test_formatter_omission_with_duplicate_text_does_not_fake_delivery(tmp_path):
    sources = _fixtures()
    plan = _plan(sources)
    docs = [_document(s, padding='x' * 900) for s in sources]
    # Measure the actual block size, including its source wrapper and candidates.
    probe = format_source_documents([docs[0]], max_chars=20000, reading_scope=[],
                                    candidate_passages=_candidate_rows(plan))
    budget = 1000 + len(probe) + 2
    calls = []

    def offline_selector(prompt):
        calls.append(prompt)
        return '[401]'  # Deterministic synthetic stub; no API/model call.

    native_receipts = []
    material = format_source_documents(
        docs, max_chars=budget, selector=offline_selector, reading_scope=[],
        candidate_passages=_candidate_rows(plan), candidate_attachment_receipts=native_receipts)
    assert calls and set(material.views) == {401}
    assert len(material) <= budget
    assert native_receipts[0]['final_registry_ids'] == [401]
    assert native_receipts[0]['final_source_material_sha256'] == _sha(str(material))
    receipts = paragraph_bundle_delivery_receipts(
        plan, str(material), delivered_spans=_raw_source_spans(plan, material),
        final_source_registry=list(material.views), canonical_sources=sources)
    by_id = {r['source_id']: r for r in receipts}
    assert by_id[401]['delivery_state'] == 'partial_after_formatting'
    assert by_id[402]['delivery_state'] == 'omitted_after_formatting'
    assert by_id[403]['delivery_state'] == 'omitted_after_formatting'
    assert by_id[403]['registry_state'] == 'registry_absent'
    omitted = next(b for b in plan.selected if b.source.source_id == 403)
    assert omitted.text in str(material)  # Duplicate prose is genuinely present.
    assert by_id[403]['bound_delivered_offsets'] == []
    # The receipt-only fix must agree with the helper despite duplicated prose.
    duplicate_card = next(c for c in native_receipts[0]['cards'] if c['source_id'] == 403)
    assert duplicate_card['status'] == 'omitted'
    assert duplicate_card['omission_reason'] == 'source_block_not_in_final_material'
    assert native_receipts[0]['attached_count'] == 1
    assert native_receipts[0]['omitted_count'] == 2
    _assert_provenance(plan, sources, material, receipts)
    _persist_case(tmp_path, plan, sources, material, receipts, budget, 'formatter_omission_duplicate_text', native_receipts)


def test_candidate_sources_are_prioritized_within_selection_budget():
    sources = _fixtures()
    plan = _plan(sources)
    docs = [_document(s, padding='x' * 900) for s in sources]
    candidate_rows = _candidate_rows(plan)
    # Keep only one source as an explicit candidate while the selector returns
    # all IDs. The bounded formatter should retain that source before an
    # unrelated source when only two blocks fit.
    candidate_rows = [row for row in candidate_rows if row['source_id'] == 403]
    probe = format_source_documents([docs[2]], max_chars=20000, reading_scope=[],
                                    candidate_passages=candidate_rows)
    budget = 1000 + len(probe) + 2
    material = format_source_documents(
        docs, max_chars=budget, selector=lambda _prompt: '[401, 402, 403]',
        reading_scope=[], candidate_passages=candidate_rows)
    assert 403 in material.views


def test_required_candidate_keeps_binding_in_over_budget_selection():
    sources = _fixtures()
    plan = _plan(sources)
    docs = [_document(s, padding='x' * 900) for s in sources]
    rows = _candidate_rows(plan)
    probe = format_source_documents([docs[0]], max_chars=20000, reading_scope=[],
                                    candidate_passages=rows)
    budget = 1000 + len(probe) + 2
    native = []
    material = format_source_documents(
        docs, max_chars=budget, required_ids=[401],
        selector=lambda _prompt: '[402, 403]', reading_scope=[],
        candidate_passages=rows, candidate_attachment_receipts=native)
    cards = {c['source_id']: c for c in native[0]['cards']}
    assert set(material.views) == {401}
    assert cards[401]['status'] == 'attached'
    proof = cards[401]['delivery_binding']
    assert str(material)[proof['material_start']:proof['material_end']] == material.views[401]['block']
    assert cards[402]['status'] == cards[403]['status'] == 'omitted'
    assert len(material) <= budget


def test_caller_candidate_is_eligible_when_source_selector_does_not_return_it():
    sources = _fixtures()
    plan = _plan(sources)
    docs = [_document(s, padding='x' * 900) for s in sources]
    rows = [r for r in _candidate_rows(plan) if r['source_id'] == 403]
    probe = format_source_documents([docs[2]], max_chars=20000, reading_scope=[],
                                    candidate_passages=rows)
    budget = 1000 + len(probe) + 2
    receipts, selection = [], []
    material = format_source_documents(
        docs, max_chars=budget, selector=lambda _prompt: '[401]',
        reading_scope=[], candidate_passages=rows,
        candidate_attachment_receipts=receipts, selection_receipts=selection)
    assert set(material.views) == {403}
    assert receipts[0]['cards'][0]['status'] == 'attached'
    allocation = selection[-1]['candidate_allocation']
    assert allocation[0]['source_id'] == 403
    assert allocation[0]['state'] == 'selected'
    assert allocation[1]['source_id'] == 401
    assert allocation[1]['state'] == 'omitted_budget'
    assert selection[-1]['optional_used_chars'] <= selection[-1]['optional_budget_chars']
    assert len(material) <= budget
    # No explicit candidate: retain the selector's decision exactly.
    legacy = format_source_documents(
        docs, max_chars=budget, selector=lambda _prompt: '[401]', reading_scope=[])
    assert set(legacy.views) == {401}
