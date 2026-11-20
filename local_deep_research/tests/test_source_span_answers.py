import json
from research_verify.source_span_answers import span_registry, parse_answers


def test_full_unicode_text_and_repeated_occurrence_coordinates_are_preserved():
    text = '重复段\n' * 450 + '10 [superscript:4] µm − IL‐3\n'
    views = [dict(source_id=8, text=text, evidence_questions=[dict(question_id='q10')])]
    _, spans = span_registry(views)
    assert ''.join(s['text']for s in spans.values()) == text
    selected = list(spans.values())[1]
    assert selected['start'] > 0
    raw = json.dumps({'sources':[dict(source_id=8,facts=[dict(text='模型读取仍可能错误。',quote_ids=[selected['quote_id']],question_ids=['q10'])])]})
    parsed = parse_answers(raw,views,transport='span_ids')
    quote = parsed['registry']['8:0']['quotes'][0]
    assert quote['start'] == selected['start'] and text[quote['start']:quote['end']] == quote['text']
    assert parsed['semantic_support_verified'] is False


def test_foreign_ids_value_injection_and_invented_ids_stay_unbound_with_raw_retained():
    views = [dict(source_id=1,text='A'),dict(source_id=2,text='B')]
    facts = [dict(text='foreign',quote_ids=['2:p0']),dict(text='invented',quote_ids=['1:p999']),
             dict(text='injected',quote_ids=['1:p0'],quotes=['changed']),
             dict(text='source answer',quote_ids=['1:p0'])]
    parsed = parse_answers(json.dumps({'sources':[dict(source_id=1,facts=facts)]}),views,transport='span_ids')
    assert list(parsed['registry']) == ['1:3']
    assert len(parsed['unbound_facts']) == 3
    assert [u['raw']for u in parsed['unbound_facts']] == facts[:3]


def test_located_quote_cannot_establish_semantic_truth_or_question_coverage():
    views = [dict(source_id=1,text='Seven male and three female participants.',evidence_questions=[dict(question_id='q7')])]
    raw = json.dumps({'sources':[dict(source_id=1,facts=[dict(text='十名男性。',quote_ids=['1:p0'],question_ids=['foreign'])])]})
    result = parse_answers(raw,views,transport='span_ids')
    assert result['registry']['1:0']['text'] == '十名男性。'
    assert result['registry']['1:0']['model_claimed_question_ids'] == []
    assert result['model_unaddressed_question_ids'] == {'1':['q7']}
    assert not result['semantic_support_verified'] and not result['semantic_question_coverage_verified']
