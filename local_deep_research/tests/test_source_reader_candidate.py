import json
import pytest
from research_verify.source_reader_candidate import source_segments, reading_batches, read_source, parse_selection


def test_all_offsets_exposed_and_long_unknown_structure_late_fact_retained():
    text = 'x' * 21000 + '校准条件是低温；适用于测试仪器。' + 'y' * 12000
    calls = []
    def invoke(prompt):
        rows = json.loads(prompt.split('Original acquired segments with canonical offsets:\n')[1])
        calls.append(rows)
        return json.dumps({'selected_indices': [r['index'] for r in rows if '校准条件' in r['text']]})
    receipt = read_source('What are the calibration conditions?', 707, 'Instrument', text, invoke)
    assert receipt['unread_segment_indices'] == []
    assert set(receipt['completed_segment_indices']) == set(range(receipt['segment_count']))
    assert all(text[r['start']:r['end']] == r['text'] for batch in calls for r in batch)
    assert any('校准条件是低温；适用于测试仪器。' in span['text'] for span in receipt['spans'])
    assert all(len(json.dumps(batch, ensure_ascii=False)) <= 12000 for batch in calls)
    assert ''.join(s.text[:1200] for s in source_segments(text))  # bounded overlap


def test_failure_and_unrelated_are_distinct_and_no_partial_json_is_accepted():
    r = read_source('temperature?', 'opaque', 'no answer', 'no relevant evidence',
                    lambda _: '{"selected_indices": []}')
    assert not r['spans'] and not r['unread_segment_indices']
    r = read_source('temperature?', 'opaque', 'no answer', 'no relevant evidence',
                    lambda _: '{bad json')
    assert not r['spans'] and r['unread_segment_indices'] == [0]
    for raw in ['{"selected_indices": [true]}', '{"selected_indices": [1]}',
                '{"selected_indices": [0,0]}']:
        with pytest.raises(ValueError):
            parse_selection(raw, [{'index': 0}])


def test_id_permutation_does_not_change_prompt_or_selection():
    prompts = []
    def invoke(prompt):
        prompts.append(prompt)
        return '{"selected_indices": [0]}'
    a = read_source('request', 10, 'title', 'original text', invoke)
    b = read_source('request', 999, 'title', 'original text', invoke)
    assert prompts[0] == prompts[1]
    assert a['spans'] == b['spans']


def test_windows_cover_entire_source_and_empty_stays_empty():
    text = 'a' * 10001
    segments = source_segments(text)
    assert segments[0].start == 0 and segments[-1].end == len(text)
    assert all(a.end >= b.start for a,b in zip(segments,segments[1:]))
    batches = reading_batches(segments)
    assert {r['index'] for batch in batches for r in batch} == set(range(len(segments)))
    assert source_segments('') == reading_batches(()) == ()
    with pytest.raises(ValueError):
        source_segments(text, chars=100, overlap=100)


def test_detail_reader_rejects_wrong_quotes_and_unrequested_fields():
    from research_verify.source_reader_candidate import read_source_details
    text = 'The instrument calibration used a cold chamber and only valid reference devices.'
    raw = json.dumps({'passages': [
        {'field_indices':[0], 'quote':text},
        {'field_indices':[0], 'quote':'An invented source quotation with a numeric result.'},
        {'field_indices':[99], 'quote':text}]})
    receipt=read_source_details('Describe calibration',3,'instrument',text,lambda _:raw)
    assert len(receipt['spans']) == 1
    assert receipt['spans'][0]['text'] == text
    assert receipt['spans'][0]['start'] == 0
    assert len(receipt['calls'][0]['rejected']) == 2
    assert not receipt['unread_segment_indices']


def test_detail_indices_emit_source_original_bytes_without_transcription():
    from research_verify.source_reader_candidate import read_source
    text='The actual yield was 95%; the cells were CD45^{+} under the stated conditions.'
    prompts=[]
    def invoke(prompt):
        prompts.append(prompt)
        return '{"selected_indices":[0]}'
    r=read_source('What yield was measured?',12,'source',text,invoke,concrete_details=True)
    assert r['spans'][0]['text']==text
    assert 'never transcribe or normalize' in prompts[0]
