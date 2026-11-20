import json
import pytest
from research_verify.occurrence_assignment import parse_assignments,assignment_prompt


def fixture():
    inv=[dict(text_id='a',facts=[dict(fact_id=0,statement='Value A',original_lines=[dict(line_id=0,text='A')])]),dict(text_id='b',facts=[dict(fact_id=0,statement='Value B',original_lines=[dict(line_id=0,text='B')])])]
    descriptors=[dict(group_id=4,study='S',method='M',field='F',quantity_unit='people',fact_keys=['hiddenOldMembership'])]
    return inv,descriptors


def test_every_fact_retained_and_missing_assignments_are_not_unknown_semantic_success():
    inv,ds=fixture();r=parse_assignments('{"assignments":[["f0",[4],"reported_fact","unspecified"]]}',inv,ds)
    assert len(r['assignments'])==2 and r['assignments'][1]['status']=='not_assessed'
    assert r['ungrouped_facts'][0]['fact_key']=='f1'and not r['groups']
    assert 'hiddenOldMembership'not in assignment_prompt('Original question',inv,ds)


def test_different_values_share_field_but_scope_tags_remain_fallible_not_a_truth_rule():
    inv,ds=fixture();raw=json.dumps(dict(assignments=[['f0',[4],'availability_statement','abstract'],['f1',[4],'reported_fact','unspecified']]))
    r=parse_assignments(raw,inv,ds);assert len(r['groups'])==1 and not r['ungrouped_facts']
    assert r['groups'][0]['actual_facts'][0]['availability_scope']=='abstract'
    assert r['groups'][0]['actual_facts'][1]['statement']=='Value B'
    for rows in [[['f0',[True],'reported_fact','abstract']],[['f9',[],'unknown','unknown']],[['f0',[],'unknown','unknown']]*2]:
        with pytest.raises(ValueError):parse_assignments(json.dumps(dict(assignments=rows)),inv,ds)
