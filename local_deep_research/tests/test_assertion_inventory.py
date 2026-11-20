import pytest
from research_verify.assertion_inventory import inventory_prompt,parse_inventory


def test_repeated_literal_occurrences_and_unlocated_assertions_are_retained_without_truth():
    units={'u0':'Concept: body about Concept [2].','u1':'Unreturned unit'}
    result=parse_inventory('{"units":[{"unit_id":"u0","status":"inventoried","assertions":[{"attribute":"concept","quote":"Concept"},{"attribute":"scope","quote":"invented"}]}]}',units)
    assert [(x['start'],x['end']) for x in result['u0']['spans']]==[(0,7),(20,27)]
    assert result['u0']['unlocated'][0]['quote']=='invented'
    assert result['u1']['model_status']=='unknown'
    assert all('supported' not in row for row in result.values())
    for span in result['u0']['spans']:assert units['u0'][span['start']:span['end']]==span['quote']


def test_inventory_rejects_ambiguous_units_and_is_source_blind():
    with pytest.raises(TypeError):inventory_prompt({'u0':'text'},sources='paper')
    with pytest.raises(ValueError):parse_inventory('{"units":[{"unit_id":"bad"}]}',{'u0':'text'})
    raw='{"units":[{"unit_id":"u0","status":"unknown","assertions":[]},{"unit_id":"u0","status":"unknown","assertions":[]}]}'
    with pytest.raises(ValueError):parse_inventory(raw,{'u0':'text'})
