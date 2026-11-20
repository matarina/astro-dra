import copy
import json
from types import SimpleNamespace

from research_verify.fact_document import render
from research_verify.generation import format_source_documents
from research_verify.writer_quote_evidence import carry_writer_quotes


def material(text):
    return format_source_documents([SimpleNamespace(page_content=text,
        metadata={'index': 9, 'title': 'Study', 'source': 'https://example.org/paper'})])


def inputs():
    text = 'Earlier background.\n\nNo effect was observed in the measured population.\n\nImportant later limitation.'
    writer = material(text)
    quote = 'No effect was observed in the measured population.'
    start = text.index(quote)
    fact = dict(fact_id='9:0', source_id='9', text='A positive effect was observed.',
                quotes=[dict(text=quote, start=start, end=start+len(quote))],
                source_view_sha256=writer.views[9]['model_view_sha256'])
    registry = {'9:0': fact}
    report, rendering = render(json.dumps({'nodes': [{'kind': 'fact', 'fact_id': '9:0'}]}), [], registry)
    claims = [dict(claim_id=0, text=report, source_ids=[9])]
    reviewer = material('Earlier background.')
    # A selected excerpt of the SAME original acquired document.
    reviewer.views[9]['available_chars'] = writer.views[9]['available_chars']
    reviewer.views[9]['available_sha256'] = writer.views[9]['available_sha256']
    return writer, reviewer, report, registry, rendering, claims


def test_exact_window_reaches_review_and_a_located_quote_does_not_approve_false_prose():
    writer, reviewer, report, registry, rendering, claims = inputs()
    new, receipt = carry_writer_quotes(writer, reviewer, report, registry, rendering, claims)
    assert new.views[9]['text'].startswith(reviewer.views[9]['text'])
    assert registry['9:0']['quotes'][0]['text'] in new.views[9]['text']
    assert 'Important later limitation.' in new.views[9]['text']
    assert receipt['semantic_verification'] == 'not_performed'
    assert not receipt['report_modified']
    assert report == 'A positive effect was observed. [9]'
    for added in receipt['additions']:
        assert added['text'] == writer.views[9]['text'][added['start']:added['end']]


def test_tampered_source_coordinates_and_report_receipts_are_not_attached():
    writer, reviewer, report, registry, rendering, claims = inputs()
    altered = copy.deepcopy(rendering)
    altered['facts'][0]['start'] = 1
    new, receipt = carry_writer_quotes(writer, reviewer, report, registry, altered, claims)
    assert str(new) == str(reviewer) and receipt['rejected_bindings']
    registry['9:0']['quotes'][0]['start'] = 0
    report, rendering = render(json.dumps({'nodes': [{'kind': 'fact', 'fact_id': '9:0'}]}), [], registry)
    new, receipt = carry_writer_quotes(writer, reviewer, report, registry, rendering, claims)
    assert str(new) == str(reviewer)
    assert receipt['rejected_bindings'][0]['reason'] == 'quote_coordinate_mismatch'


def test_quotes_already_visible_are_retained_without_duplicate_append():
    writer, _, report, registry, rendering, claims = inputs()
    new, receipt = carry_writer_quotes(writer, writer, report, registry, rendering, claims)
    assert str(new) == str(writer)
    assert not receipt['additions']
    assert receipt['quote_bindings'][0]['status'] == 'already_present'


def test_matching_words_do_not_route_quotes_to_a_different_cited_source():
    writer, reviewer, report, registry, rendering, claims = inputs()
    claims[0]['source_ids'] = [10]
    new, receipt = carry_writer_quotes(writer, reviewer, report, registry, rendering, claims)
    assert str(new) == str(reviewer) and not receipt['quote_bindings']


def test_changed_underlying_source_is_not_treated_as_the_same_quote_namespace():
    writer, _, report, registry, rendering, claims = inputs()
    different = material('A different acquired document under the same numeric ID.')
    new, receipt = carry_writer_quotes(writer, different, report, registry, rendering, claims)
    assert str(new) == str(different)
    assert receipt['quote_bindings'][0]['status'] == 'review_source_binding_changed'


def test_real_review_entry_transports_quote_without_approving_or_changing_report(monkeypatch):
    import research_verify.evidence_flow as flow
    from research_verify.synthesis_trace import DISABLED
    writer, reviewer, report, registry, rendering, claims = inputs()
    monkeypatch.setattr(flow, '_review_material', lambda *args, **kwargs: (reviewer, args[2]))
    prompts = []
    def invoke(prompt, **kwargs):
        prompts.append(prompt)
        return '{"issues":[]}'
    handler = SimpleNamespace(get_setting=lambda key, default=None: (
        True if key == 'citation.preserve_writer_quote_evidence' else default),
        writer_quote_registry=registry, writer_quote_rendering=rendering, _invoke_text=invoke)
    result = flow.review_answer(handler, 'Question', report, [], [{'index': 9}],
                                DISABLED, None, 1, 60000, {}, {'remaining': 1}, writer_material=writer)
    assert registry['9:0']['quotes'][0]['text'] in prompts[0]
    assert result[0] == report
    assert result[3][0]['status'] == 'review_claims_unchecked'
