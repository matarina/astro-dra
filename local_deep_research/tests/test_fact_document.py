import json
import pytest
from research_verify.fact_document import parse_answers, render


def test_source_answer_copy_preserves_complete_relationship_and_coordinates():
    views=[dict(source_id=1,text='Total ten participants: seven male and three female.')]
    raw=json.dumps({'sources':[{'source_id':1,'facts':[{'text':'共有十例，其中七男三女。','quotes':['seven male and three female']}]}]})
    parsed=parse_answers(raw,views);registry=parsed['registry']
    answer,receipt=render(json.dumps({'nodes':[{'kind':'text','text':'研究结果'}, {'kind':'fact','fact_id':'1:0'}]}),[dict(index=1)],registry)
    span=receipt['facts'][0]
    assert answer[span['start']:span['end']]=='共有十例，其中七男三女。 [1]'
    assert receipt['semantic_verdict'] is None


def test_other_source_quote_does_not_bind_and_invalid_row_does_not_lose_valid_fact():
    views=[dict(source_id=1,text='A'),dict(source_id=2,text='B')]
    raw=json.dumps({'sources':[{'source_id':1,'facts':[{'text':'valid','quotes':['A']},{'text':'wrong study','quotes':['B']}]}]})
    parsed=parse_answers(raw,views)
    assert list(parsed['registry'])==['1:0'] and len(parsed['unbound_facts'])==1
    assert parsed['source_accounting'][1]['status']=='missing_duplicate_or_invalid_source_row'


def test_writer_cannot_inject_value_into_selected_fact_and_omission_stays_visible():
    registry={'1:0':dict(source_id='1',text='original fact')}
    with pytest.raises(ValueError):
        render(json.dumps({'nodes':[dict(kind='fact',fact_id='1:0',text='altered')]}),[dict(index=1)],registry)
    answer,receipt=render(json.dumps({'nodes':[dict(kind='text',text='intro')]}),[dict(index=1)],registry)
    assert answer=='intro' and receipt['unselected_fact_ids']==['1:0']
