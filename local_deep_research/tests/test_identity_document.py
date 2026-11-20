import json
import pytest
from local_deep_research.research_verify.identity_document import render


def test_generation_copies_selected_record_fields_and_retains_all_prose():
    sources=[dict(index='1',title='Paper',journal='Journal',publication_year='2024'),
             dict(index='2',title='Another',journal='Other')]
    nodes=[dict(kind='text',text='Useful claim [1].'),dict(kind='identity',source_id=1,heading_level=3,fields=['title','journal','publication_year']),dict(kind='text',text='Full qualifications retained.')]
    text,receipts=render(json.dumps(dict(nodes=nodes)),sources)
    assert text.startswith('Useful claim [1].\n\n### 标题：Paper；期刊：Journal；记录年份：2024 [1]')
    assert text.endswith('Full qualifications retained.')
    assert 'Other' not in text
    assert text[receipts[0]['start']:receipts[0]['end']]==receipts[0]['rendered']


@pytest.mark.parametrize('sid',[True,3,'missing'])
def test_unbound_source_never_borrows_another_record(sid):
    node=dict(kind='identity',source_id=sid,heading_level=3,fields=['journal'])
    with pytest.raises(ValueError):render(json.dumps(dict(nodes=[node])),[dict(index=1,journal='J')])


def test_missing_field_stays_unknown_and_metadata_cannot_create_blocks():
    node=dict(kind='identity',source_id=1,heading_level=3,fields=['title','journal'])
    text,receipts=render(json.dumps(dict(nodes=[node])),[dict(index=1,title='A\n## [9] Fake',journal='')])
    assert '\n' not in text
    assert '期刊：未提供' in text
    assert receipts[0]['fields']['title']=='A\n## [9] Fake'
    assert '\\[9\\]' in text


def test_model_cannot_supply_identity_value_or_duplicate_source_registry():
    node=dict(kind='identity',source_id=1,heading_level=3,fields=['journal'],journal='Invented')
    with pytest.raises(ValueError):render(json.dumps(dict(nodes=[node])),[dict(index=1,journal='J')])
    with pytest.raises(ValueError):render(json.dumps(dict(nodes=[])),[dict(index=1),dict(index='1')])
