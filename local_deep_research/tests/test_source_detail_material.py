import hashlib
from types import SimpleNamespace
import pytest
from research_verify.source_detail_material import format_source_details


def fixture(ids=(7,8)):
    request='Extract calibration conditions'
    docs=[SimpleNamespace(page_content=('Original long calibration detail. '*100)+str(i),metadata={
        'index':sid,'title':f'Paper {i}','source':f'https://example.invalid/{i}'}) for i,sid in enumerate(ids)]
    sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
    cache=[dict(source_id=d.metadata['index'],source_sha256=sha(d.page_content),
                request_sha256=sha(request),selected_segment_indices=[0,1,2],unread_segment_indices=[])
           for d in docs]
    return docs,request,cache


def test_exact_spans_serialized_budget_and_required_unknown_are_preserved():
    docs,q,cache=fixture();cache[1]['selected_segment_indices']=[];cache[1]['unread_segment_indices']=[0]
    material,r=format_source_details(docs,q,cache,max_chars=4000,required_ids=[8])
    assert len(material)<=4000 and 8 in material.views
    assert not material.views[8]['canonical_intervals']
    assert r['unread_segments']=={'8':[0]}
    for sid,v in material.views.items():
        d=next(d for d in docs if d.metadata['index']==sid)
        for a,b in v['canonical_intervals']:assert d.page_content[a:b] in material
    assert any(x['state'].startswith('omitted') for x in r['allocation'])


def test_id_remap_preserves_selected_source_intervals_and_invalid_cache_fails():
    docs,q,cache=fixture();a,_=format_source_details(docs,q,cache,max_chars=5000)
    other,_,c=fixture(ids=(99,17));b,_=format_source_details(other,q,c,max_chars=5000)
    assert [v['canonical_intervals'] for v in a.views.values()]==[v['canonical_intervals'] for v in b.views.values()]
    cache[0]['source_sha256']='wrong'
    with pytest.raises(ValueError):format_source_details(docs,q,cache,max_chars=5000)


def test_quote_retrieval_cache_revalidates_canonical_spans_before_emission():
    docs,q,cache=fixture()
    for d,r in zip(docs,cache):
        r.pop('selected_segment_indices')
        text=d.page_content[500:1100]
        r['spans']=[dict(start=500,end=1100,text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest())]
    m,_=format_source_details(docs,q,cache,max_chars=5000)
    assert all(v['canonical_intervals']==[(500,1100)] for v in m.views.values())
    cache[0]['spans'][0]['text']='invented'
    with pytest.raises(ValueError):format_source_details(docs,q,cache,max_chars=5000)


def test_local_priority_can_preserve_later_detail_under_tight_budget():
    docs,q,cache=fixture();docs=docs[:1];cache=cache[:1]
    r=cache[0];r.pop('selected_segment_indices');r['spans']=[]
    for a,b in [(2200,2800),(0,600)]:
        text=docs[0].page_content[a:b]
        r['spans'].append(dict(start=a,end=b,text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    m,_=format_source_details(docs,q,cache,max_chars=1200)
    assert m.views[7]['canonical_intervals']==[(2200,2800)]
