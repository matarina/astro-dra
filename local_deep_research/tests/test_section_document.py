import json
import pytest
from research_verify.section_document import render


def document(blocks):return json.dumps(dict(title='问题',sections=[dict(heading='结果',blocks=blocks)]),ensure_ascii=False)
def paper(ids,extra=''):return dict(kind='paper',source_id=1,fields=['title'],fact_ids=ids,additional_text=extra)


def test_complete_facts_metadata_and_new_prose_have_separate_exact_coordinates():
    sources=[dict(index=1,title='Actual title')];registry={'1:0':dict(source_id='1',text='完整分组与方法。')}
    text,receipt=render(document([paper(['1:0'],'需要独立评估的补充事实。'),dict(kind='analysis',purpose='recommendation',text='假设性建议。',source_ids=[1])]),sources,registry)
    assert '完整分组与方法。 [1]'in text and '需要独立评估的补充事实。 [1]'in text
    for span in receipt['facts']+receipt['identities']+receipt['generated_prose']:assert text[span['start']:span['end']]==span['rendered']
    assert len(receipt['generated_prose'])==2 and receipt['semantic_verdict']is None


def test_no_automatic_scientific_deduplication_or_approval():
    sources=[dict(index=1,title='Title')];registry={'1:0':dict(source_id='1',text='四名参与者。')}
    text,r=render(document([paper(['1:0','1:0'],'全部是儿童。')]),sources,registry)
    assert text.count('四名参与者。')==2 and r['repeated_fact_ids']==['1:0']
    assert '全部是儿童。'in text and r['automatic_prose_deletions']==0 and r['semantic_verdict']is None


def test_foreign_fact_and_retyped_value_cannot_impersonate_registry_fact():
    sources=[dict(index=1)];registry={'2:0':dict(source_id='2',text='other study')}
    with pytest.raises(ValueError):render(document([paper(['2:0'])]),sources,registry)
    block=paper([]);block['fact_text']='injected'
    with pytest.raises(ValueError):render(document([block]),sources,{})
