import json
from local_deep_research.research_verify.segment_review import segments, parse_review


def test_partition_preserves_context_coordinates_and_numeric_commas():
    text = 'In 1,234 samples，A was observed; this does not establish B。 [2][9]'
    rows = segments(text)
    assert ''.join(r['text'] for r in rows) == text
    assert rows[0]['text'] == 'In 1,234 samples，'
    assert all(text[r['start']:r['end']] == r['text'] for r in rows)


def test_missing_duplicate_and_foreign_rows_remain_unchecked():
    row = dict(segment_id=0, asserted_relation='A', source_relation='A', additional_premise='', status='supported', quotes=['A'])
    result = parse_review(json.dumps({'segments':[row,row,{**row,'segment_id':True}]}), 'A，B。C', 'A')
    assert not result['fully_returned']
    assert [r['reason'] for r in result['segments']] == ['duplicate_rows','missing_row','missing_row']
    assert len(result['foreign_rows']) == 1


def test_quote_location_is_required_but_does_not_prove_inference():
    row = dict(segment_id=0, asserted_relation='A therefore B', source_relation='A', additional_premise='A implies B', status='supported', quotes=['A'])
    result = parse_review(json.dumps({'segments':[row]}), 'B', 'A')
    assert result['fully_returned']
    assert result['segments'][0]['model']['additional_premise'] == 'A implies B'
    row['quotes'] = ['invented']
    result = parse_review(json.dumps({'segments':[row]}), 'B', 'A')
    assert not result['fully_returned']
