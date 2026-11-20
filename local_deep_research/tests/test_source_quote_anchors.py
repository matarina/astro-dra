import pytest
from research_verify.source_quote_anchors import locate_quote_hint


def test_modified_value_in_hint_never_changes_original_evidence():
    first='This is the unique beginning of the source passage. '
    last=' This is the unique qualifier at the end of the source passage.'
    source='prefix '+first+'yield was 95%; CD45^{+} cells'+last+' suffix'
    hint=first+'yield was 99%; CD45+ cells'+last
    r=locate_quote_hint(hint,source)
    assert r['hint_verbatim'] is False
    assert '95%' in r['text'] and '99%' not in r['text']
    assert 'CD45^{+}' in r['text']
    assert r['text']==source[r['start']:r['end']]
    assert r['method']=='unique_boundary_anchors_nonverbatim_hint'


def test_ambiguous_reversed_outside_view_and_excess_extent_fail():
    quote='A'*40+' details '+'B'*40
    assert locate_quote_hint(quote,quote+' '+quote) is None
    assert locate_quote_hint(quote,'B'*40+' details '+'A'*40) is None
    assert locate_quote_hint(quote,'not supplied '+quote,view_end=12) is None
    assert locate_quote_hint(quote,'A'*40+'x'*2500+'B'*40) is None
    assert locate_quote_hint('tiny','unrelated') is None
    with pytest.raises(ValueError):locate_quote_hint(quote,quote,view_start=-1)


def test_exact_repeated_quote_is_not_disambiguated_by_guessing():
    quote='A complete source sentence with enough detail.'
    assert locate_quote_hint(quote,quote+' '+quote) is None
    r=locate_quote_hint(quote,quote+' '+quote,view_start=len(quote)+1)
    assert r['hint_verbatim'] is True
    assert r['start']==len(quote)+1


def test_interior_anchors_retrieve_original_context_when_boundary_markup_changed():
    middle=('One uniquely anchored instrument measurement was made at the stated temperature. '
            'A second unique original qualifier limits the population and duration. ')
    source='PREFIX α-value: '+middle+'β-reference1 SUFFIX'
    hint='normalized start: '+middle+'normalized ending'
    r=locate_quote_hint(hint,source)
    assert r['method']=='unique_interior_anchors_source_context_retrieval'
    assert r['text']==source[r['start']:r['end']]
    assert 'α-value' in r['text'] and 'normalized start' not in r['text']


def test_shuffled_unique_anchors_cannot_manufacture_a_source_extent():
    one='Unique first anchor with forty exact characters here. '
    two='Unique second anchor with forty exact characters here. '
    assert locate_quote_hint('fake '+one+two+' fake',two+one) is None
