"""Source-only Writer transport must not promote fallible reader labels."""
import hashlib

import pytest

from research_verify.canonical_fields import selected_writer_units


def unit(sid, uid, text):
    return dict(source_id=sid, unit_id=uid, kind='text', start=7,
                end=7 + len(text), text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest())


def observation(u, req=0):
    return dict(source_id=u['source_id'], unit_id=u['unit_id'],
                quote=u['text'], unit_sha256=u['text_sha256'],
                requirement_ids=[req], value='Invented unconditional result',
                modality='Incorrect experiment')


REQS = [dict(requirement_id=0), dict(requirement_id=1)]


def test_preserves_conditional_source_and_discards_interpretation():
    u = unit(1, 2, 'Only after treatment A, the assay measured B.\nControl C remained.')
    first = observation(u)
    changed = {**first, 'value': 'Opposite result', 'modality': 'Another assay'}
    actual = selected_writer_units([first], [u], REQS)
    assert actual == selected_writer_units([changed], [u], REQS)
    assert actual == [{**u, 'requirement_ids': [0]}]


def test_same_source_unit_combines_requests_but_other_sources_stay_distinct():
    a, b = unit(1, 2, 'Same literal paragraph'), unit(2, 2, 'Same literal paragraph')
    result = selected_writer_units([observation(a), observation(a, 1), observation(b)], [a, b], REQS)
    assert [(u['source_id'], u['requirement_ids']) for u in result] == [(1, [0, 1]), (2, [0])]


@pytest.mark.parametrize('mutation', [
    {'quote': 'Changed source quote'}, {'unit_sha256': 'bad'},
    {'source_id': 99}, {'source_id': True}, {'requirement_ids': [99]},
    {'requirement_ids': [False]}, {'requirement_ids': []},
])
def test_rejects_unbound_model_selection(mutation):
    u = unit(1, 2, 'Original source, not a support verdict.')
    with pytest.raises(ValueError):
        selected_writer_units([{**observation(u), **mutation}], [u], REQS)


def test_changed_source_bytes_and_ambiguous_registry_rejected():
    u = unit(1, 2, 'Original source')
    with pytest.raises(ValueError):
        selected_writer_units([observation(u)], [{**u, 'text': 'Tampered source'}], REQS)
    with pytest.raises(ValueError):
        selected_writer_units([observation(u)], [u, u], REQS)
