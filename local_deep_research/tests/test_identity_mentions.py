import json
from research_verify.identity_mentions import identity_units,parse_identity_mentions,identity_prompt


def test_report_only_literal_fields_keep_exact_coordinates_and_no_source_metadata():
    report='A paper in Journal of Calibration (2026) describes the instrument [7].'
    units=identity_units(report)
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{'journal':'Journal of Calibration','year':'2026'}}]})
    mentions,unresolved=parse_identity_mentions(raw,report,units)
    assert not unresolved and len(mentions)==1
    assert mentions[0]['mention'].source_id=='7'
    for field,(a,b) in mentions[0]['field_positions'].items():
        assert report[a:b]==mentions[0]['mention'].claims[field]
    assert 'Do not verify, correct' in identity_prompt(units)


def test_invented_field_and_multi_citation_association_stay_unresolved():
    report='A paper in Journal of Calibration reports measurements [3, 8].'
    units=identity_units(report)
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{'journal':'Journal of Calibration'}}]})
    mentions,unresolved=parse_identity_mentions(raw,report,units)
    assert not mentions and unresolved[0]['reason']=='ambiguous_multiple_citations'
    report='This study reports measurements [3].';units=identity_units(report)
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{'journal':'Science'}}]})
    mentions,unresolved=parse_identity_mentions(raw,report,units)
    assert not mentions and unresolved[0]['reason']=='unlocated_ambiguous_or_unknown_field'


def test_empty_proposal_is_not_an_invalid_field_or_a_verified_negative():
    report='A measurement was made [4].';units=identity_units(report)
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{}}]})
    assert parse_identity_mentions(raw,report,units)==([],[])


def test_uncited_identity_is_preserved_without_borrowing_following_citation():
    report='A paper in Journal of Calibration studied measurements. Its protocol used a sensor [17].'
    units=identity_units(report)
    assert units[0]['source_ids']==[] and units[1]['source_ids']==[17]
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{'journal':'Journal of Calibration'}}]})
    mentions,unknown=parse_identity_mentions(raw,report,units)
    assert mentions==[] and unknown[0]['reason']=='missing_explicit_citation'
    a,b=unknown[0]['field_positions']['journal']
    assert report[a:b]=='Journal of Calibration' and unknown[0]['source_ids']==[]
    assert len(identity_units(report,include_unbound=False))==1


def test_unbound_invented_fields_do_not_survive_provenance_validation():
    report='An uncited heading.';units=identity_units(report)
    raw=json.dumps({'mentions':[{'unit_id':units[0]['unit_id'],'claims':{'journal':'Invented'}}]})
    mentions,unknown=parse_identity_mentions(raw,report,units)
    assert not mentions and unknown[0]['reason']=='unlocated_ambiguous_or_unknown_field'
