"""Offline structural candidate tests; no model, report or evaluator fixtures."""

from dataclasses import replace
import hashlib

import pytest

from research_verify.coverage_planner import (
    StructureHeading, generate_paragraph_bundles, index_source_structure,
    paragraph_bundle_delivery_receipts, plan_paragraph_bundles,
    serialize_paragraph_bundles,
)


def test_multilingual_nested_repeated_headings_and_exact_offsets():
    text = '# 研究\n\n前段。\n\n## Δοκιμή\n条件 α。\n\n条件 β。\n\n## Δοκιμή\n別段。'
    source = index_source_structure(text)
    assert [p.heading_path for p in source.paragraphs] == [
        ('研究',), ('研究', 'Δοκιμή'), ('研究', 'Δοκιμή'), ('研究', 'Δοκιμή')]
    assert [text[p.start:p.end] for p in source.paragraphs] == ['前段。', '条件 α。', '条件 β。', '別段。']
    assert source.paragraphs[1].section_id != source.paragraphs[3].section_id
    options = generate_paragraph_bundles(source, {1: ('field',)}, adjacent_paragraphs=4)
    assert max(b.last for b in options) == 2
    assert min(b.first for b in options) == 1


def test_setext_acquisition_headings_and_fenced_markup():
    text = 'Überblick\n===\n\nText.\n\n```\n# literal\n```\n\n次節\n---\n\n終。'
    source = index_source_structure(text)
    assert source.paragraphs[0].heading_path == ('Überblick',)
    assert source.paragraphs[1].heading_path == ('Überblick',)
    assert source.paragraphs[-1].heading_path == ('Überblick', '次節')
    raw = 'TITLE\n\nBody.'
    external = index_source_structure(raw, headings=[StructureHeading(0, 6, 1, 'TITLE')])
    assert external.paragraphs[0].heading_path == ('TITLE',)
    with pytest.raises(ValueError):
        index_source_structure(raw, headings=[StructureHeading(0, 100, 1, 'invalid')])


def test_unknown_structure_and_oversized_paragraph_are_explicit():
    source = index_source_structure('First qualifier.\n\nSecond qualifier.')
    options = generate_paragraph_bundles(source, {0: ('x',)})
    plan = plan_paragraph_bundles(options, context_chars=10000)
    assert all(r['state'] == 'partial' and r['reason'] == 'unknown_structure'
               for r in plan.receipts)
    oversized = generate_paragraph_bundles(source, {0: ('x',)}, max_bundle_chars=3)
    omitted = plan_paragraph_bundles(oversized, context_chars=10000)
    assert omitted.selected == ()
    assert omitted.receipts[0]['state'] == 'omitted'


def test_adjacent_bundles_are_exact_and_remote_sections_stay_separate():
    text = '# A\n\nseed\n\nqualifier\n\n# B\n\nunrelated\n\n# C\n\nother protocol'
    source = index_source_structure(text)
    options = generate_paragraph_bundles(source, {0: ('x',), 3: ('x',)}, adjacent_paragraphs=3)
    plan = plan_paragraph_bundles(options, context_chars=10000)
    assert len(plan.selected) == 2
    assert [b.text for b in plan.selected] == ['seed\n\nqualifier', 'other protocol']
    for b in options:
        assert b.text == text[b.start:b.end]
        assert 'unrelated' not in b.text
    assert all(r['state'] == 'planned' for r in plan.receipts)


def test_dedup_unions_fields_and_seed_provenance_without_double_charging():
    source = index_source_structure('# S\n\nexact shared paragraph', source_id='opaque')
    a = generate_paragraph_bundles(source, {0: ('a',)})
    b = generate_paragraph_bundles(source, {0: ('b',)})
    plan = plan_paragraph_bundles((*a, *b, *a), context_chars=10000)
    assert len(plan.selected) == 1
    assert plan.selected[0].fields == ('a', 'b')
    assert plan.selected[0].seed_fields == ((0, ('a', 'b')),)
    assert {(r['seed'], r['field']) for r in plan.receipts} == {(0, 'a'), (0, 'b')}
    assert plan.context.count('exact shared paragraph') == 1
    assert plan.context_chars == len(serialize_paragraph_bundles(plan.selected))


def test_seed_memberships_do_not_cross_product_during_expansion():
    source = index_source_structure('# S\n\nfirst\n\nsecond')
    plan = plan_paragraph_bundles(
        generate_paragraph_bundles(source, {0: ('a',), 1: ('b',)}), context_chars=10000)
    assert {(r['seed'], r['field']) for r in plan.receipts} == {(0, 'a'), (1, 'b')}


def test_serialized_budget_includes_unicode_headers_and_separators():
    source = index_source_structure('# 節\n\nfirst\n\nqualifier')
    options = generate_paragraph_bundles(source, {0: ('field',)})
    smallest = min(options, key=lambda b: len(b.text))
    exact_cost = len(serialize_paragraph_bundles([smallest]))
    assert exact_cost > len(smallest.text)
    fits = plan_paragraph_bundles(options, context_chars=exact_cost)
    assert fits.context_chars == exact_cost
    assert fits.receipts[0]['state'] == 'partial'
    assert fits.context_sha256 == hashlib.sha256(fits.context.encode()).hexdigest()
    misses = plan_paragraph_bundles(options, context_chars=exact_cost - 1)
    assert not misses.context and misses.receipts[0]['state'] == 'omitted'
    second = index_source_structure('# Other\n\nextra', source_id='second')
    combined = [smallest, *generate_paragraph_bundles(second, {0: ('other',)})]
    full = plan_paragraph_bundles(combined, context_chars=10000)
    assert full.context_chars == sum(len(serialize_paragraph_bundles([b]))
                                     for b in full.selected) + 2
    tight = plan_paragraph_bundles(combined, context_chars=full.context_chars - 1)
    assert len(tight.selected) == 1
    assert any(r['state'] == 'omitted' for r in tight.receipts)


def test_overlap_upgrades_do_not_bypass_bundle_limit():
    source = index_source_structure('# S\n\naaaaa\n\nbbbbb\n\nccccc')
    options = generate_paragraph_bundles(source, {0: ('x',), 2: ('y',)}, max_bundle_chars=12)
    plan = plan_paragraph_bundles(options, context_chars=10000)
    assert all(len(b.text) <= 12 for b in plan.selected)
    assert all(a.end <= b.start for a, b in zip(plan.selected, plan.selected[1:]))


def test_delivery_observer_distinguishes_plan_text_and_absence():
    source = index_source_structure('# S\n\nverbatim paragraph')
    plan = plan_paragraph_bundles(generate_paragraph_bundles(source, {0: ('x',)}),
                                  context_chars=10000)
    assert plan.receipts[0]['delivery_state'] == 'not_observed'
    exact = paragraph_bundle_delivery_receipts(plan, 'prefix\n' + plan.context)
    assert exact[0]['delivery_state'] == 'attached_exact'
    partial = paragraph_bundle_delivery_receipts(plan, plan.selected[0].text)
    assert partial[0]['state'] == 'omitted'
    assert partial[0]['delivery_state'] == 'omitted_after_formatting'
    omitted = paragraph_bundle_delivery_receipts(plan, 'registry only')
    assert omitted[0]['state'] == 'omitted'


def test_zero_budget_and_empty_candidates_are_nonblocking():
    source = index_source_structure('text')
    candidates = generate_paragraph_bundles(source, {0: ('x',)})
    plan = plan_paragraph_bundles(candidates, context_chars=0)
    assert plan.context_chars == 0 and plan.receipts[0]['state'] == 'omitted'
    assert plan_paragraph_bundles([], context_chars=0).receipts == ()
    with pytest.raises(ValueError):
        generate_paragraph_bundles(source, {4: ('x',)})


def test_numeric_handle_permutation_does_not_prioritize_citations():
    a = index_source_structure('# A\n\nfirst', source_id=1)
    b = index_source_structure('# B\n\nsecond', source_id=2)
    def run(sources):
        candidates = [c for s in sources for c in generate_paragraph_bundles(s, {0: ('x',)})]
        cost = max(len(serialize_paragraph_bundles([c])) for c in candidates)
        return plan_paragraph_bundles(candidates, context_chars=cost)
    original = run([a, b])
    permuted = run([replace(a, source_id=2), replace(b, source_id=1)])
    assert [x.source.sha256 for x in original.selected] == [x.source.sha256 for x in permuted.selected]


def test_remote_seeds_in_same_unknown_section_do_not_bridge_a_gap():
    source = index_source_structure('left\n\nunrelated\n\nright')
    options = generate_paragraph_bundles(source, {0: ('a',), 2: ('b',)}, adjacent_paragraphs=0)
    plan = plan_paragraph_bundles(options, context_chars=10000)
    assert [b.text for b in plan.selected] == ['left', 'right']
    assert 'unrelated' not in plan.context
    assert len(plan.selected) == 2


@pytest.mark.parametrize('tamper', ['hash', 'negative', 'out_of_bounds', 'shifted', 'overlap'])
def test_reject_tampered_source_and_paragraph_offsets_at_all_boundaries(tamper):
    source = index_source_structure('# S\n\nfirst paragraph\n\nsecond paragraph')
    candidate = generate_paragraph_bundles(source, {0: ('field',)}, adjacent_paragraphs=0)[0]
    if tamper == 'hash':
        bad_source = replace(source, sha256='0' * 64)
    else:
        paragraphs = list(source.paragraphs)
        p = paragraphs[0]
        if tamper == 'negative':
            paragraphs[0] = replace(p, start=-1)
        elif tamper == 'out_of_bounds':
            paragraphs[0] = replace(p, end=len(source.text) + 20)
        elif tamper == 'shifted':
            paragraphs[0] = replace(p, start=p.start + 1)
        else:
            paragraphs[1] = replace(paragraphs[1], start=p.start)
        bad_source = replace(source, paragraphs=tuple(paragraphs))
    bad = replace(candidate, source=bad_source)
    with pytest.raises(ValueError):
        serialize_paragraph_bundles([bad])
    with pytest.raises(ValueError):
        plan_paragraph_bundles([bad], context_chars=10000)
    valid_plan = plan_paragraph_bundles([candidate], context_chars=10000)
    with pytest.raises(ValueError):
        paragraph_bundle_delivery_receipts(replace(valid_plan, selected=(bad,)), valid_plan.context)


def test_external_canonical_binding_rejects_consistent_replacement_source():
    original = index_source_structure('original', source_id='opaque')
    substituted = index_source_structure('replacement', source_id='opaque')
    candidate = generate_paragraph_bundles(substituted, {0: ('field',)})[0]
    with pytest.raises(ValueError, match='canonical source binding'):
        plan_paragraph_bundles([candidate], context_chars=10000, canonical_sources=[original])
    with pytest.raises(ValueError, match='canonical source binding'):
        serialize_paragraph_bundles([candidate], canonical_sources=[original])


def test_heading_title_binding_and_plan_context_hash_are_revalidated():
    with pytest.raises(ValueError, match='heading title'):
        index_source_structure('Title\n\nBody', headings=[StructureHeading(0, 6, 1, 'Fabricated')])
    source = index_source_structure('paragraph')
    plan = plan_paragraph_bundles(generate_paragraph_bundles(source, {0: ('field',)}),
                                  context_chars=10000)
    with pytest.raises(ValueError, match='plan context'):
        paragraph_bundle_delivery_receipts(replace(plan, context_sha256='0' * 64), plan.context)


def test_duplicate_prose_at_another_offset_does_not_prove_partial_delivery():
    source = index_source_structure('# A\n\nidentical prose\n\n# B\n\nidentical prose', source_id='s')
    original = generate_paragraph_bundles(source, {0: ('x',)}, adjacent_paragraphs=0)[0]
    other = generate_paragraph_bundles(source, {1: ('x',)}, adjacent_paragraphs=0)[0]
    plan = plan_paragraph_bundles([original], context_chars=10000)
    material = serialize_paragraph_bundles([other])
    assert paragraph_bundle_delivery_receipts(plan, material)[0]['delivery_state'] == 'omitted_after_formatting'
    span = dict(source_id='s', source_sha256=source.sha256,
                source_start=other.start, source_end=other.end,
                material_start=len(material) - len(other.text), material_end=len(material))
    receipt = paragraph_bundle_delivery_receipts(plan, material, delivered_spans=[span])[0]
    assert receipt['delivery_state'] == 'omitted_after_formatting'
    assert receipt['invalid_delivery_spans'] == 1


def test_bound_partial_formatter_delivery_and_registry_receipts():
    source = index_source_structure('# A\n\nfirst paragraph\n\nsecond paragraph', source_id='s')
    plan = plan_paragraph_bundles(generate_paragraph_bundles(source, {0: ('x',)}),
                                  context_chars=10000)
    selected = plan.selected[0]
    p = source.paragraphs[0]
    material = 'wrapper\n' + source.text[p.start:p.end] + '\nfooter'
    span = dict(source_id='s', source_sha256=source.sha256,
                source_start=p.start, source_end=p.end,
                material_start=8, material_end=8 + p.end - p.start)
    receipt = paragraph_bundle_delivery_receipts(
        plan, material, delivered_spans=[span], final_source_registry=['s'])[0]
    assert receipt['delivery_state'] == 'partial_after_formatting'
    assert receipt['bound_delivered_offsets'] == [(p.start, p.end)]
    assert receipt['registry_state'] == 'present' and receipt['final_registry_sha256']
    wrong = {**span, 'material_start': 0}
    assert paragraph_bundle_delivery_receipts(
        plan, material, delivered_spans=[wrong])[0]['delivery_state'] == 'omitted_after_formatting'
    assert paragraph_bundle_delivery_receipts(
        plan, plan.context, final_source_registry=[])[0]['delivery_state'] == 'attached_text_registry_absent'
    assert selected.text == source.text[selected.start:selected.end]


def test_union_and_exact_serialized_boundary_are_deterministic():
    source = index_source_structure('shared text', source_id='opaque')
    a = generate_paragraph_bundles(source, {0: ('z', 'a', 'z')})[0]
    b = generate_paragraph_bundles(source, {0: ('b',)})[0]
    combined = plan_paragraph_bundles([a, b], context_chars=10000)
    reversed_plan = plan_paragraph_bundles([b, a], context_chars=10000)
    assert combined.context == reversed_plan.context
    assert combined.selected[0].fields == ('a', 'b', 'z')
    cost = combined.context_chars
    exact = plan_paragraph_bundles([a, b], context_chars=cost)
    assert exact.context == combined.context and exact.context_chars <= exact.budget_chars
    tight = plan_paragraph_bundles([a, b], context_chars=cost - 1)
    assert tight.context_chars <= cost - 1
    assert any(r['state'] == 'omitted' for r in tight.receipts)
