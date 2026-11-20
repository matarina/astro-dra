import copy
import json
from types import SimpleNamespace

import pytest

from research_verify.generation import format_source_documents
from research_verify.material_exposure import capture_writer_exposure, review_exposure_context


def material(text):
    return format_source_documents([SimpleNamespace(page_content=text,
        metadata={'index': 9, 'title': 'Study', 'source': 'https://example.org/study'})])


def payload(context):
    return json.loads(context.split('\n')[-1])


def test_stage_views_are_distinct_and_no_semantic_absence_is_inferred():
    writer = material('Abstract.\n\nMethods: unabridged supplied procedure.')
    reviewer = material('Abstract.')
    snapshot = capture_writer_exposure(writer)
    result = payload(review_exposure_context(snapshot, reviewer, [9, 10]))
    row = result['source_views'][0]
    writer_text = result['texts'][result['views'][row['writer']]['text']]
    reviewer_text = result['texts'][result['views'][row['reviewer']]['text']]
    assert writer_text['chars'] > reviewer_text['chars']
    assert writer_text['sha256'] != reviewer_text['sha256']
    assert result['views'][result['source_views'][1]['writer']]['state'] == 'not_in_this_stage_view'
    assert result['semantic_support'] == 'not_assessed'
    assert result['published_paper_completeness'] == 'unconfirmed'
    unknown = payload(review_exposure_context(None, 'plain text with no registry', [9]))
    assert unknown['views'][unknown['source_views'][0]['writer']]['state'] == 'unknown'
    assert unknown['views'][unknown['source_views'][0]['reviewer']]['state'] == 'unknown'


def test_mismatched_source_binding_and_mutated_snapshot_are_rejected():
    writer = material('Original source.')
    snapshot = capture_writer_exposure(writer)
    changed = copy.deepcopy(snapshot)
    changed['records']['9']['chars'] = 100000
    with pytest.raises(ValueError, match='snapshot changed'):
        review_exposure_context(changed, writer, [9])
    forged = material('Different view bytes.')
    forged.views[9].update({k: writer.views[9][k] for k in ['text', 'model_view_chars', 'model_view_sha256']})
    with pytest.raises(ValueError, match='binding mismatch'):
        capture_writer_exposure(forged)
    writer.views[9]['text'] = 'Unbound replacement'
    with pytest.raises(ValueError, match='binding mismatch'):
        capture_writer_exposure(writer)


def test_overflow_records_unavailable_instead_of_dropping_rows_as_absent():
    writer = capture_writer_exposure(material('Body.'))
    result = payload(review_exposure_context(writer, material('Excerpt.'), range(200), max_chars=900))
    assert result['status'] == 'exposure_context_unavailable_budget'
    assert result['requested_source_count'] == 200
    assert 'source_views' not in result


@pytest.mark.parametrize('enabled', [False, True])
def test_actual_synthesis_transports_exposure_only_in_opt_in_native_review(enabled):
    from test_generation_grounding import handler
    class Model:
        def __init__(self):
            self.prompts = []

        def invoke(self, prompt):
            self.prompts.append(prompt)
            return SimpleNamespace(content='A finding [9].' if len(self.prompts) == 1 else '{"issues":[]}')
    model = Model()
    writer = handler(model)
    writer.settings_snapshot = {'general.enable_fact_checking': True,
                               'citation.max_review_calls': 1,
                               'citation.include_writer_exposure_context': enabled}
    result = writer.analyze_followup('Question', [{'index': 9, 'abstract': 'Actual supplied source.'}],
                                    'Unverified nonempty draft [9].', 0)
    assert len(model.prompts) == 2
    assert 'STAGE-LOCAL SOURCE EXPOSURE' not in model.prompts[0]
    assert ('STAGE-LOCAL SOURCE EXPOSURE' in model.prompts[1]) == enabled
    assert result['content'] == 'A finding [9].'
    assert result['evidence_review']['status'] == 'review_incomplete'
    if enabled:
        context = model.prompts[1].split('STAGE-LOCAL SOURCE EXPOSURE', 1)[1].split('\n\nSTRUCTURAL REPORT SPANS', 1)[0]
        value = json.loads(context.splitlines()[-1])
        row = value['source_views'][0]
        assert value['texts'][value['views'][row['writer']]['text']]['chars'] == 23


def test_unfittable_exposure_prompt_preserves_report_without_model_call(monkeypatch):
    import research_verify.evidence_flow as flow
    from research_verify.synthesis_trace import DISABLED
    original = 'A finding [9].'
    # Deliberately ignores the reduced source budget, exercising the terminal
    # unavailable path rather than silently sending an oversized model request.
    monkeypatch.setattr(flow, '_review_material', lambda *args, **kwargs: ('X' * 100000, args[2]))
    calls = []
    reviewer = SimpleNamespace(get_setting=lambda k, d=None: k == 'citation.include_writer_exposure_context',
                               _invoke_text=lambda *args, **kwargs: calls.append(args))
    result = flow.review_answer(reviewer, 'Question', original, [], [{'index': 9}],
                                DISABLED, None, 1, 60000, {}, {'remaining': 2})
    assert result[0] == original and not calls
    assert any(x.get('reason') == 'exposure_prompt_budget' for x in result[3])
