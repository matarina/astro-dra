import json
import pytest
from research_verify.retention_inventory import parse_inventory
from research_verify.report_occurrences import occurrence_texts,parse_comparisons
from research_verify.report_occurrences import parse_occurrence_inventory


def test_all_direct_occurrences_kept_and_missing_inventory_or_comparison_unassessed():
    texts=occurrence_texts('One [5].\n\nDifferent [6].\n\nSecond [5].',{5})
    assert list(texts.values())==['One [5].','Second [5].']
    ids=list(texts)
    inv=parse_inventory(json.dumps(dict(inventories=[dict(text_id=ids[0],facts=[dict(fact_id=0,statement='A',line_ids=[0])])])),texts)
    parsed=parse_comparisons('{"comparisons":[]}',inv)
    assert parsed['unassessed_occurrences']==[ids[1]]
    assert parsed['uncompared_facts']==[dict(text_id=ids[0],fact_id=0,status='not_assessed')]


def test_only_actual_cross_occurrence_references_bound_without_certifying_semantics():
    inv=parse_inventory('{"inventories":[{"text_id":"a","facts":[{"fact_id":0,"statement":"A","line_ids":[0]}]},{"text_id":"b","facts":[{"fact_id":0,"statement":"B","line_ids":[0]}]}]}',{'a':'Literal A','b':'Literal B'})
    base=dict(fact_refs=[dict(text_id='a',fact_id=0),dict(text_id='b',fact_id=0)],relationship='compatible',reason='Fallible opinion')
    parsed=parse_comparisons(json.dumps(dict(comparisons=[base])),inv)
    assert parsed['comparisons'][0]['actual_facts'][0]['original_lines'][0]['text']=='Literal A'
    for refs in [[dict(text_id='a',fact_id=True),dict(text_id='b',fact_id=0)],[dict(text_id='x',fact_id=0),dict(text_id='b',fact_id=0)],[dict(text_id='a',fact_id=0)]*2]:
        with pytest.raises(ValueError):parse_comparisons(json.dumps(dict(comparisons=[dict(base,fact_refs=refs)])),inv)


def test_one_unlocated_fact_does_not_erase_other_bound_facts_or_become_absence():
    facts=[dict(fact_id=0,statement='Exact statement',line_ids=[0]),
           dict(fact_id=1,statement='Unlocated statement',line_ids=[0,1])]
    raw=json.dumps(dict(inventories=[dict(text_id='a',facts=facts)]))
    parsed=parse_occurrence_inventory(raw,{'a':'Only actual line','b':'Other actual line'})
    a,b=parsed['inventories']
    assert a['facts'][0]['original_lines']==[dict(line_id=0,text='Only actual line')]
    assert a['rejected_facts'][0]['raw']==facts[1] and a['rejected_facts'][0]['status']=='not_assessed'
    assert b['status']=='not_assessed' and not b['facts']
    with pytest.raises(ValueError):parse_comparisons(json.dumps(dict(comparisons=[dict(fact_refs=[dict(text_id='a',fact_id=0),dict(text_id='a',fact_id=1)],relationship='conflict',reason='Unbound')])),parsed['inventories'])


def test_duplicate_ids_or_rows_are_not_resolved_by_arbitrary_first_choice():
    fact=dict(fact_id=0,statement='A',line_ids=[0])
    parsed=parse_occurrence_inventory(json.dumps(dict(inventories=[dict(text_id='a',facts=[fact,fact]),dict(text_id='b',facts=[fact]),dict(text_id='b',facts=[fact])])),{'a':'A','b':'B'})
    a,b=parsed['inventories'];assert not a['facts']and len(a['rejected_facts'])==2
    assert b['status']=='not_assessed'and len(b['rejected_rows'])==2
