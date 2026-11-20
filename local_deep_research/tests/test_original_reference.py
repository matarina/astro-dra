import hashlib
import pytest
from research_verify.original_reference import original_reference_urls, matching_pdf_annotations, extract_locator_document


def test_only_explicit_original_locator_with_exact_reference_hash_is_returned():
    text='[7] Original title\nURL: https://publisher.example/paper.pdf\n\n'
    source=dict(index=7,original_bibliography_entry=text,original_bibliography_sha256=hashlib.sha256(text.encode()).hexdigest())
    anchors=original_reference_urls(source);assert len(anchors)==1
    a=anchors[0];assert text[a['start']:a['end']]==a['url']
    assert a['binding_status']=='original_reference_locator_only'
    with pytest.raises(ValueError):original_reference_urls({**source,'original_bibliography_entry':text+'changed'})


def test_wrapped_url_requires_real_annotation_not_concatenated_guessed_target():
    text='[7] Paper\nURL: https://publisher.example/path/\nwrapped-file.pdf\n\n'
    source=dict(index=7,original_bibliography_entry=text,original_bibliography_sha256=hashlib.sha256(text.encode()).hexdigest())
    with pytest.raises(ValueError,match='requires matching PDF URI annotation'):original_reference_urls(source)
    uri='https://publisher.example/path/wrapped-file.pdf'
    annotations=[dict(url=uri,page=4,rect=[1,2,3,4],annotation_index=0)]
    evidence=matching_pdf_annotations(source,annotations,'0'*64)
    found=original_reference_urls({**source,'original_locator_annotations':evidence})
    assert len(found)==1 and found[0]['url']==uri
    assert found[0]['start']is None and found[0]['locator_origin']=='archived_pdf_uri_annotation'
    assert all(text[s['start']:s['end']]==s['text']for s in found[0]['reference_fragment_spans'])
    assert found[0]['annotation_occurrences'][0]['page']==4
    bad={**evidence[0],'url':'https://other.example/unrelated'}
    with pytest.raises(ValueError):original_reference_urls({**source,'original_locator_annotations':[bad]})


def test_truncated_display_can_match_multiple_annotations_without_choosing_identity():
    text='[7] Paper\nURL: https://publisher.example/\npaper-\n\n'
    s=dict(index=7,original_bibliography_entry=text,original_bibliography_sha256=hashlib.sha256(text.encode()).hexdigest())
    annotations=[dict(url='https://publisher.example/paper-'+n)for n in ['a.pdf','b.pdf']]
    found=original_reference_urls({**s,'original_locator_annotations':matching_pdf_annotations(s,annotations,'0'*64)})
    assert len(found)==2


def test_serialized_metadata_field_is_not_mistaken_for_url_continuation():
    text='[7] Paper\nURL: https://publisher.example/paper\nDOI: 10.1234/example\n'
    s=dict(index=7,original_bibliography_entry=text,original_bibliography_sha256=hashlib.sha256(text.encode()).hexdigest())
    assert original_reference_urls(s)[0]['url']=='https://publisher.example/paper'


def test_html_encoding_scope_and_literal_text_without_authority_promotion():
    raw='<html><head><meta charset="gb18030"></head><body><h1>中文页面</h1><p>原文内容</p><script>hidden</script></body></html>'.encode('gb18030')
    anchor=dict(url='https://publisher.example/page',original_reference_sha256='0'*64)
    text=extract_locator_document(raw,anchor)
    assert '中文页面'in text and '原文内容'in text and 'hidden'not in text
    assert 'NOT independently confirmed'in text and 'not supplied'not in text
    limited=extract_locator_document(raw,anchor,max_chars=4)
    assert 'remaining page text not supplied'in limited
    with pytest.raises(ValueError):extract_locator_document(b'unsupported bytes',anchor)
