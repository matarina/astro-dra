import json
import pytest
from research_verify.occurrence_groups import fact_registry,parse_groups,parse_group_comparisons


def fixture():
    inv=[dict(text_id='a',facts=[dict(fact_id=0,statement='A'),dict(fact_id=1,statement='B')]),dict(text_id='b',facts=[dict(fact_id=0,statement='C')])]
    group=dict(group_id=0,study='S',method='M',field='F',quantity_unit='samples',fact_keys=['f0','f2'])
    return inv,group


def test_cross_occurrence_binding_preserves_ungrouped_unknown_and_missing_comparison():
    inv,g=fixture();r=parse_groups(json.dumps(dict(groups=[g])),inv)
    assert r['groups'][0]['actual_facts'][1]['text_id']=='b'
    assert r['ungrouped_facts'][0]['fact_key']=='f1'and r['ungrouped_facts'][0]['status']=='not_assessed'
    assert parse_group_comparisons('{"results":[]}',r)==[dict(group_id=0,status='not_assessed')]
    row=dict(group_id=0,relationship='unknown',relevant_fact_keys=['f0','f2'],reason='Fallible unknown')
    assert parse_group_comparisons(json.dumps(dict(results=[row])),r)[0]['relationship']=='unknown'
    for bad in [dict(relevant_fact_keys=['f0','f1']),dict(group_id=True),dict(reason='x'*351)]:
        with pytest.raises(ValueError):parse_group_comparisons(json.dumps(dict(results=[{**row,**bad}])),r)


def test_same_occurrence_or_foreign_fact_group_remains_unresolved_never_semantically_approved():
    inv,g=fixture()
    for refs in [['f0','f1'],['f0','invented'],['f0','f0']]:
        r=parse_groups(json.dumps(dict(groups=[{**g,'fact_keys':refs}])),inv)
        assert not r['groups']and r['unresolved_groups']and len(r['ungrouped_facts'])==3
    with pytest.raises(ValueError):parse_groups(json.dumps(dict(groups=[g]*25)),inv)
