import copy
import hashlib
import json

import pytest

from research_verify.section_document import render as old_render
from research_verify.revisable_section_document import render


def inputs():
    source = 'Ten samples underwent assay A; a separate two samples underwent assay B.'
    views = [dict(source_id='1',text=source)]
    notes = {'1:0':dict(source_id='1',fact_id='1:0',text='错误的读书笔记。',quotes=[],
        source_view_sha256=hashlib.sha256(source.encode()).hexdigest())}
    block = dict(kind='paper',source_id=1,fields=['title'],fact_ids=['1:0'],additional_text='保留的补充内容。')
    doc = dict(title='报告',sections=[dict(heading='方法',blocks=[block])])
    return [dict(index=1,title='Actual title')], notes, views, doc


def test_no_revision_keeps_old_report_and_all_original_fact_receipts():
    sources,notes,views,doc = inputs()
    old, before = old_render(json.dumps(doc),sources,notes)
    actual, after = render(json.dumps(doc),sources,notes,views)
    assert actual == old
    for got,want in zip(after['facts'],before['facts']):
        assert {k:v for k,v in got.items() if k != 'writer_revised'} == want
    assert after['writer_revisions'] == [] and after['semantic_verdict'] is None


def test_occurrence_revision_keeps_original_note_and_unrevised_other_occurrence():
    sources,notes,views,doc = inputs()
    original = copy.deepcopy(notes)
    blocks = doc['sections'][0]['blocks'];blocks.append(copy.deepcopy(blocks[0]))
    blocks[0]['revisions'] = [dict(fact_id='1:0',text='十份样本使用A，另两份使用B。',quote_ids=['1:p0'])]
    text, receipt = render(json.dumps(doc),sources,notes,views)
    assert '十份样本使用A，另两份使用B。 [1]' in text
    assert '错误的读书笔记。 [1]' in text and text.count('保留的补充内容。') == 2
    assert notes == original and receipt['selected_fact_ids'] == ['1:0','1:0']
    assert receipt['repeated_fact_ids'] == ['1:0']
    lineage = receipt['writer_revisions'][0]
    assert lineage['original_note'] == original['1:0']
    assert lineage['original_passages'][0]['text'] == views[0]['text']
    assert lineage['semantic_support_verified'] is False
    assert receipt['automatic_scientific_edits'] == 0
    for span in receipt['facts']+receipt['identities']+receipt['generated_prose']:
        assert text[span['start']:span['end']] == span['rendered']


@pytest.mark.parametrize('failure',['foreign_span','unknown_span','stale_view','unselected','duplicate','citation'])
def test_revision_cannot_claim_other_original_evidence(failure):
    sources,notes,views,doc = inputs()
    change = dict(fact_id='1:0',text='模型改写。',quote_ids=['1:p0'])
    block = doc['sections'][0]['blocks'][0];block['revisions'] = [change]
    if failure == 'foreign_span':
        views.append(dict(source_id='2',text='Other study'));change['quote_ids'] = ['2:p0']
    elif failure == 'unknown_span':change['quote_ids'] = ['1:p999']
    elif failure == 'stale_view':views[0]['text'] += ' New text.'
    elif failure == 'unselected':block['fact_ids'] = []
    elif failure == 'duplicate':block['revisions'].append(copy.deepcopy(change))
    elif failure == 'citation':change['text'] += ' [2]'
    with pytest.raises(ValueError):render(json.dumps(doc),sources,notes,views)


def test_even_source_bound_nonsense_is_not_semantically_approved():
    sources,notes,views,doc = inputs()
    doc['sections'][0]['blocks'][0]['revisions'] = [dict(fact_id='1:0',text='毫无根据的模型表述。',quote_ids=['1:p0'])]
    text,receipt = render(json.dumps(doc),sources,notes,views)
    assert '毫无根据的模型表述。' in text
    assert receipt['semantic_verdict'] is None
    assert receipt['writer_revisions'][0]['semantic_support_verified'] is False
