import json
from types import SimpleNamespace

import pytest
from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
from research_verify.citation_display import cited_indices, render_report_current
from research_verify.evidence_flow import review_answer
from research_verify.generation import ModelOutputTruncated
from research_verify.synthesis_trace import DISABLED
from research_verify.task_evidence import task_coverage


def message(text, finish):
    return SimpleNamespace(content=text, response_metadata={"finish_reason": finish})


def test_range_preserves_identity_including_middle_only_missing_and_merged_sources():
    sources = [SimpleNamespace(original_indices=[1], index=1, url='https://a'),
               SimpleNamespace(original_indices=[2, 4], index=4, url='https://b'),
               SimpleNamespace(original_indices=[3], index=5, url='https://c')]
    body = 'Earlier [3]. Range [1]–[3]. More [2] - [5]. Literal `[6]–[8]`.'
    assert cited_indices(body) == [3, 1, 2, 4, 5]
    assert render_report_current(body, sources) == (
        'Earlier [[5]](https://c). Range [[1]](https://a), [[4]](https://b), [[5]](https://c). '
        'More [[4]](https://b), [[5]](https://c), [5]. Literal `[6]–[8]`.')


@pytest.mark.parametrize('stream', [False, True])
def test_writer_continues_only_from_the_existing_boundary(stream):
    text = 'An example [1].\n\nThe remaining '
    chunks = []
    class Model:
        def stream(self, prompt):
            yield message(text.rstrip(), 'length')
            yield message('', '')
        def invoke(self, prompt):
            if 'Exact anchor to repeat:' in prompt:
                return message(text + 'result [2].', 'stop')
            return message(text.rstrip(), 'length')
    writer = StandardCitationHandler(Model())
    if stream:
        writer.set_stream_callback(chunks.append)
    output = writer._invoke_with_streaming('write the report', trace=DISABLED)
    assert output == text + 'result [2].'
    assert not writer._writer_incomplete
    if stream:
        assert ''.join(chunks) == output


def test_repeated_length_keeps_longest_verified_prefix_and_incomplete_status():
    class Model:
        calls = 0
        def invoke(self, prompt):
            self.calls += 1
            return message('prefix' if self.calls == 1 else prompt.split('Exact anchor to repeat:\n')[-1] + ' added', 'length')
    model = Model()
    writer = StandardCitationHandler(model)
    assert writer._invoke_text('write', stage='writer') == 'prefix added added'
    assert writer._writer_incomplete and model.calls == 3


@pytest.mark.parametrize('limit,expected', [(3, []), (2, ['review_budget_exhausted'])])
def test_truncated_native_check_splits_only_pending_claims(limit, expected):
    class Trace:
        batches = []
        def record(self, stage, data):
            if stage == 'native_check_request':
                self.batches.append(data['claim_ids'])
    trace = Trace()
    class Model:
        def invoke(self, prompt):
            ids = trace.batches[-1]
            if len(ids) > 1:
                # A parser could accept this prefix as valid JSON.
                return message('{"issues":[]}', 'length')
            return message(json.dumps({'issues':[{'claim_id':ids[0],'status':'report_context'}]}), 'stop')
    handler = StandardCitationHandler(Model())
    answer = 'The first section describes the setting.\n\nThe next section provides context.'
    budget = {'remaining':limit}
    result = review_answer(handler, 'question', answer, [], [], trace, None, 1, 60000, {}, budget)
    assert trace.batches == [[0,1], [0], [1]][:limit]
    assert [r['status'] for r in result[3]] == expected
    assert budget['remaining'] == 0


def test_coverage_recovers_from_length_without_accepting_partial_json():
    calls = []
    def invoke(prompt, *, stage, trace):
        calls.append(stage)
        if stage == 'task_coverage':
            raise ModelOutputTruncated(stage)
        if stage == 'task_coverage_compact':
            return json.dumps({'questions':[{'question':'What?', 'status':'partial','passage_ids':[1]}]})
        return json.dumps({'questions':[{'id':1,'status':'partial','reviewed_scope':'example',
            'open_scope':'others unavailable','quote_ids':[1],'source_ids':[7]}]})
    coverage = task_coverage(None, {}, 'One example [7].', DISABLED, user_request='What?', invoke=invoke)
    assert coverage[1]['status'] == 'partial'
    assert coverage[1]['report_quotes'] == ['One example [7].']
    assert calls == ['task_coverage','task_coverage_compact','task_coverage_scope']


def test_preexisting_range_publications_still_validate_with_original_numbering():
    from research_verify.publication import _publish_report, publish_report, validate_publication
    from research_verify.config import VerifyConfig

    rows = [dict(index=i,title=f'Paper {i}',link=f'https://example.org/{i}') for i in (1,2,3)]
    text = 'Previously cited [3]. Then [1]–[3].'
    cfg = VerifyConfig(enable_citation_qc=False)
    old = _publish_report(text, rows, cfg=cfg, _schema_version='2.2')
    current = publish_report(text, rows, cfg=cfg)
    assert '–' in old.content and '–' not in current.content
    assert len(old.sources) == 2 and len(current.sources) == 3
    for publication in (old,current):
        assert validate_publication(publication.content, publication.metadata()).content == publication.content


@pytest.mark.parametrize('reason', ['content_filter', 'cancelled', ''])
def test_unconfirmed_writer_continuation_preserves_truncation(reason):
    replies = iter([message('First part', 'length'), message('First part with more', reason)])
    writer = StandardCitationHandler(SimpleNamespace(invoke=lambda prompt:next(replies)))
    assert writer._invoke_text('write', stage='writer') == 'First part'
    assert writer._writer_incomplete


def test_streaming_continuation_preserves_already_emitted_paragraph_boundary():
    class Model:
        def stream(self, prompt):
            yield message('First paragraph.\n\n', 'length')
        def invoke(self, prompt):
            return message('First paragraph.\n\nSecond paragraph.', 'stop')
    writer = StandardCitationHandler(Model())
    chunks = []
    writer.set_stream_callback(chunks.append)
    result = writer._invoke_with_streaming('write', stage='writer')
    assert ''.join(chunks) == result == 'First paragraph.\n\nSecond paragraph.'


def test_legacy_quarto_export_keeps_only_published_endpoint_links():
    from research_verify.quarto_sources import document
    archived = ('Claim [[1]](https://a)–[[3]](https://c).\n\n## Sources\n\n'
                '[1] First\n\n[2] Second\n\n[3] Third\n')
    rendered = document(archived, 'Title', '')
    assert 'Claim [@ref1]–[@ref3].' in rendered
    assert '@ref2' not in rendered
