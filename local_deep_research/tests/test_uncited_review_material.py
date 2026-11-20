from types import SimpleNamespace

from research_verify.generation import SourceMaterial, format_source_documents
from research_verify.uncited_review_material import discovery_material


def doc(index, abstract, body=''):
    return SimpleNamespace(page_content=abstract + body, metadata=dict(index=index,
        title='Study ' + str(index), source='https://example.org/' + str(index), abstract=abstract))


def test_discovery_keeps_opposing_documents_without_assigning_attribution():
    documents = [doc(2, 'Treatment increased outcome.'), doc(7, 'Treatment did not increase outcome.')]
    material, receipt = discovery_material(documents, 'Treatment outcome', SourceMaterial(''), 6000)
    assert set(material.views) == {2, 7}
    assert all(d.metadata['abstract'] in material for d in documents)
    assert receipt['attribution'] == 'unassigned_search_candidates'
    assert receipt['claim_source_ids_modified'] is False
    assert receipt['semantic_support'] == 'not_assessed'


def test_budget_failure_preserves_original_and_does_not_pick_easy_source_subset():
    existing = format_source_documents([doc(9, 'Original cited evidence.')])
    material, receipt = discovery_material([doc(9, 'Original cited evidence.'),
        doc(2, 'X' * 3000), doc(7, 'Y' * 3000)], 'Question', existing, len(existing) + 3500)
    assert material is existing
    assert receipt['status'] == 'unavailable_complete_abstract_inventory_budget'
    assert receipt['attached_source_ids'] == []
    assert receipt['discovery_source_ids'] == [2, 7]


def test_original_cited_block_preserved_and_added_windows_bound_to_own_document():
    cited = doc(9, 'Existing source.')
    other = doc(2, 'Complete abstract.', '\n\n' + ('Background. ' * 170) + 'Target procedure preserves qualifiers.')
    existing = format_source_documents([cited])
    material, receipt = discovery_material([cited, other], 'Target procedure', existing, 9000)
    assert str(material).startswith(str(existing))
    assert material.views[9] == existing.views[9]
    assert 'Complete abstract.' in material.views[2]['text']
    for window in receipt['windows']:
        assert window['source_id'] == 2
        assert other.page_content[window['start']:window['end']] in material.views[2]['text']


def test_real_review_receives_candidates_while_uncited_claim_stays_uncited():
    import json
    from research_verify import evidence_flow as flow
    from research_verify.synthesis_trace import DISABLED
    report = 'Treatment always increased outcome.'
    prompts = []
    def invoke(prompt, **kwargs):
        prompts.append(prompt)
        return '{"issues":[{"claim_id":0,"status":"insufficient_evidence"}]}'
    handler = SimpleNamespace(get_setting=lambda k, d=None:
        True if k == 'citation.discover_uncited_source_context' else d,
        _invoke_text=invoke, settings_snapshot={})
    result = flow.review_answer(handler, 'What outcome was measured?', report,
        [doc(2, 'Treatment increased outcome.'), doc(7, 'Treatment did not increase outcome.')],
        [{'index': 2}, {'index': 7}], DISABLED, None, 1, 60000,
        {'fetcher': SimpleNamespace(web=lambda *args: [])}, {'remaining': 1})
    assert len(prompts) == 1 and len(prompts[0]) <= 60000
    assert 'UNASSIGNED SOURCE DISCOVERY' in prompts[0]
    assert 'Treatment did not increase outcome.' in prompts[0]
    claims = json.loads(prompts[0].split('\nFINAL ANSWER:\n')[1].split('\n\nSUPPLIED SOURCES:')[0])
    assert claims[0]['source_ids'] == []
    assert result[0] == report and result[2] == []
    assert result[3][0]['status'] == 'insufficient_evidence'


def test_discovery_unavailability_does_not_allow_oversized_uncited_followup(monkeypatch):
    from research_verify import evidence_flow as flow
    from research_verify.synthesis_trace import DISABLED
    report = 'A substantive uncited assertion.'
    # An existing source formatter that cannot reduce its output. Even when
    # discovery cannot attach, the opt-in path must enforce serialized size.
    monkeypatch.setattr(flow, '_review_material', lambda *args, **kwargs: ('X' * 90000, args[2]))
    calls = []
    handler = SimpleNamespace(get_setting=lambda k, d=None:
        True if k == 'citation.discover_uncited_source_context' else d,
        _invoke_text=lambda *args, **kwargs: calls.append(args))
    result = flow.review_answer(handler, 'Question', report, [], [], DISABLED,
        None, 1, 60000, {}, {'remaining': 2})
    assert not calls and result[0] == report
    assert result[3][0]['reason'] == 'uncited_discovery_prompt_budget'
