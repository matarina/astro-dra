"""Evidence boundaries, review order, private storage, and failure isolation."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
from types import SimpleNamespace

import pytest

from research_verify.synthesis_trace import (
    start_trace, trace_context, source_snapshot, record_model_response, text_digest,
)
from research_verify.publication import publish_report
from research_verify.config import VerifyConfig
from test_generation_grounding import handler


def read_stages(root):
    stages = {}
    for path in root.rglob('*.json.gz'):
        stage = path.name.split('-', 1)[1][:-8]
        stages.setdefault(stage, []).append(json.loads(gzip.decompress(path.read_bytes())))
    return stages


@pytest.fixture
def trace_root(tmp_path, monkeypatch):
    monkeypatch.setenv('LDR_RESEARCH_TRACE_ENABLED', 'true')
    root = tmp_path / 'traces'
    monkeypatch.setenv('LDR_RESEARCH_TRACE_DIR', str(root))
    return root


class ReviewThenWrite:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        text = 'Observed result [17].' if len(self.prompts) == 1 else '{"issues":[]}'
        return SimpleNamespace(content=text, response_metadata={'model_name': 'fixture', 'headers': {'Authorization': 'omit'}})


def source():
    return {'index': 17, 'title': 'Study', 'link': 'https://example.org/paper',
            'abstract': 'Two independent samples were measured twice.', 'content_type': 'abstract',
            'password': 'do-not-save', 'settings_snapshot': {'api_key': 'do-not-save'}}


def test_actual_draft_evidence_review_writer_and_citation_map_are_joinable(trace_root, native_review_only):
    model = ReviewThenWrite()
    writer = handler(model)
    writer.settings_snapshot = {'general.enable_fact_checking': True}
    with trace_context('task-one'):
        result = writer.analyze_followup('What did this study measure?', [source()], 'Working draft [17].', 0)
        publication = publish_report(result['content'], [source()], cfg=VerifyConfig(enable_verify=False))
    stages = read_stages(trace_root)
    assert stages['agent_draft'][0]['text'] == 'Working draft [17].'
    material = stages['writer_sources'][0]
    assert material['source_ids'] == [17] and source()['abstract'] in material['text']
    review = stages['native_check_request'][0]['prompt']
    assert 'What did this study measure?' in review and material['text'] in review
    assert 'headings and table categories' in review and 'what numbers count' in review
    final_request = stages['writer_request'][0]['prompt']
    assert material['text'] in final_request
    assert stages['writer_response'][0]['text_used'] in review
    assert stages['native_check_response'][0]['text_used'] not in final_request
    final_response = stages['writer_response'][0]
    assert final_response['text_used'] == result['content']
    assert final_response['text_sha256'] == stages['publication_input'][0]['text_sha256']
    mapped = stages['publication_output'][0]
    assert mapped['text'] == publication.content
    assert mapped['sources'][0]['original_indices'] == [17]
    assert mapped['sources'][0]['index'] == 1
    assert len(model.prompts) == 2  # Writer then native review; no repair needed.
    assert 'headers' not in final_response['model_metadata']
    assert stages['input_sources'][0]['sources'][0] == source_snapshot([source()])[0]
    assert 'settings_snapshot' not in stages['input_sources'][0]['sources'][0]
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in trace_root.rglob('*') if p.is_file())
    assert all(p.stat().st_mode & 0o777 == 0o700 for p in [trace_root, *[d for d in trace_root.rglob('*') if d.is_dir()]])


def test_trace_disabled_creates_no_files_and_does_not_change_answer(trace_root, monkeypatch):
    monkeypatch.setenv('LDR_RESEARCH_TRACE_ENABLED', 'false')
    with trace_context('disabled'):
        result = handler(ReviewThenWrite()).analyze_followup('Question', [source()], 'Draft', 0)
    assert result['content'] == 'Observed result [17].'
    assert not trace_root.exists()


def test_credentials_redacted_in_prompts_and_response(trace_root, monkeypatch):
    secret = 'test-secret-abcdef1234567890'
    monkeypatch.setenv('LDR_LLM_DEEPSEEK_API_KEY', secret)
    with trace_context('private'):
        with start_trace('synthesis') as trace:
            trace.record('request', {'prompt': secret + ' sk-12345678901234567890 Bearer token12345 https://user:pass@example.org', 'api_key': 'another-key'})
            record_model_response(trace, 'writer', SimpleNamespace(content=secret), 'clean answer')
    material = json.dumps(read_stages(trace_root))
    assert secret not in material and '12345678901234567890' not in material
    assert 'token12345' not in material and 'user:pass@' not in material
    assert 'another-key' not in material and '<REDACTED>' in material
    assert read_stages(trace_root)['writer_response'][0]['text_used'] == 'clean answer'


def test_oversize_is_explicitly_omitted_not_silently_truncated(trace_root, monkeypatch):
    monkeypatch.setenv('LDR_RESEARCH_TRACE_MAX_BYTES', '4096')
    with trace_context('bounded'):
        with start_trace('synthesis') as trace:
            row = trace.record('too_large', {'text': 'x' * 3000})
            assert row['status'] == 'omitted_size_limit' and 'file' not in row
            assert trace.record('small', {'text': 'kept'})['status'] == 'recorded'
    assert 'too_large' not in read_stages(trace_root)
    assert read_stages(trace_root)['small'][0]['text'] == 'kept'


def test_parallel_task_ids_and_nested_context_do_not_cross(trace_root):
    def write(task):
        with trace_context(task):
            with start_trace('synthesis') as trace:
                trace.record('identity', {'task': task})
                return trace.path
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(write, ['task-a', 'task-b']))
    assert paths[0].parent.name == 'task-a' and paths[1].parent.name == 'task-b'
    for task in ['task-a', 'task-b']:
        assert read_stages(trace_root / task)['identity'][0]['task'] == task
    with trace_context('outer'):
        write('inner')
        assert start_trace('synthesis').path.parent.name == 'outer'


def test_bad_storage_cannot_fail_generation(tmp_path, monkeypatch):
    target = tmp_path / 'blocked'
    target.write_text('file, not a directory')
    monkeypatch.setenv('LDR_RESEARCH_TRACE_DIR', str(target))
    monkeypatch.setenv('LDR_RESEARCH_TRACE_ENABLED', 'true')
    with trace_context('blocked'):
        result = handler(ReviewThenWrite()).analyze_followup('Question', [source()], 'Draft', 0)
    assert result['content'] == 'Observed result [17].'


def test_context_identifier_cannot_escape_trace_root(trace_root):
    with trace_context('../../escape'):
        trace = start_trace('synthesis')
    assert trace.path.is_relative_to(trace_root)
    assert trace.path.parent.name == text_digest('../../escape')[:32]


def test_stream_partial_is_recorded_without_second_model_request(trace_root):
    class PartialStream:
        def stream(self, _):
            yield SimpleNamespace(content='Partial [17].')
            raise TimeoutError('transport detail must not appear in trace')

        def invoke(self, _):
            raise AssertionError('Must not restart a stream after emitting content')
    writer = handler(PartialStream())
    received = []
    writer.set_stream_callback(received.append)
    with trace_context('stream'):
        result = writer.analyze_followup('Question', [source()], 'Draft', 0)
    assert result['content'] == ''.join(received) == 'Partial [17].'
    assert result['synthesis_error'] == 'writer_incomplete'
    response = read_stages(trace_root)['writer_response'][0]
    assert response['partial'] is True and response['error_type'] == 'TimeoutError'


def test_record_write_failure_does_not_escape(trace_root, monkeypatch):
    import research_verify.synthesis_trace as module
    with trace_context('write-error'):
        trace = start_trace('synthesis')
    def fail(*_, **__):
        raise OSError('not recorded verbatim')
    monkeypatch.setattr(module.os, 'open', fail)
    assert trace.record('request', {'text': 'still return a report'}) is None


def test_inventory_keeps_consumed_text_variants_but_not_credentials():
    s = source()
    s.update(content='HTML text', body='Body text', fetched_content='Fetched original')
    snapshot = source_snapshot([s])[0]
    assert snapshot['content'] == 'HTML text' and snapshot['body'] == 'Body text'
    assert snapshot['fetched_content'] == 'Fetched original'
    assert 'password' not in snapshot and 'settings_snapshot' not in snapshot
