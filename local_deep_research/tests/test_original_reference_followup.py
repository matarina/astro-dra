import hashlib
import sys
from types import SimpleNamespace

import pytest
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify import original_reference


def source(index):
    text=f'[{index}] Paper\nURL: https://publisher.example/{index}.pdf\n'
    return dict(index=index,original_bibliography_entry=text,
                original_bibliography_sha256=hashlib.sha256(text.encode()).hexdigest())


def test_unknown_source_cache_is_isolated_and_default_has_no_locator_fetch(monkeypatch):
    fetch=EvidenceFetcher(get=lambda *a,**k:pytest.fail('No default HTTP'))
    seen=[]
    monkeypatch.setattr(fetch,'_article',lambda s:seen.append(s['index']))
    assert fetch.article(source(1))is None
    assert fetch.article(source(2))is None
    assert seen==[1,2]


def test_opt_in_uses_exact_locator_and_retains_cache_scope_without_identity_promotion(monkeypatch):
    seen=[]
    def get(url,**kw):
        seen.append(url)
        return SimpleNamespace(raise_for_status=lambda:None,
            iter_content=lambda size:[b'%PDF-fixture'],close=lambda:None)
    monkeypatch.setattr(original_reference,'extract_locator_pdf',lambda raw,a:raw.decode()+a['url'])
    fetch=EvidenceFetcher({'citation.original_reference_pdf_followup':True},get=get,requests=2)
    one,two=source(1),source(2)
    assert fetch.article(one).endswith('/1.pdf')
    assert fetch.article(two).endswith('/2.pdf')
    assert fetch.article(one).endswith('/1.pdf')and len(seen)==2
    assert not any(k in one for k in ('doi','pmid','fetched_content'))
    with pytest.raises(ValueError):
        fetch.article({**one,'original_bibliography_entry':'tampered'})


def test_ambiguous_locator_does_not_choose_a_paper_or_make_http():
    s=source(1);s['original_bibliography_entry']+='URL: https://publisher.example/other.pdf\n'
    s['original_bibliography_sha256']=hashlib.sha256(s['original_bibliography_entry'].encode()).hexdigest()
    fetch=EvidenceFetcher({'citation.original_reference_pdf_followup':True},get=lambda *a,**k:pytest.fail('Ambiguous HTTP'))
    assert fetch.article(s)is None and fetch.remaining==6


def test_existing_identifiers_keep_identity_checked_article_route(monkeypatch):
    fetch=EvidenceFetcher({'citation.original_reference_pdf_followup':True},get=lambda *a,**k:pytest.fail('No locator HTTP'))
    seen=[]
    monkeypatch.setattr(fetch,'_article',lambda s:seen.append(s['doi'])or'Identity-checked article')
    s={**source(1),'doi':'10.1234/identified'}
    assert fetch.article(s)=='Identity-checked article'
    assert seen==['10.1234/identified']and fetch.remaining==6


def test_document_opt_in_reads_html_while_pdf_only_retains_explicit_format_limit():
    raw=b'<html><head><meta charset="utf-8"></head><body>Actual supplied page</body></html>'
    def get(*a,**kw):
        return SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[raw],close=lambda:None)
    fetch=EvidenceFetcher({'citation.original_reference_document_followup':True},get=get,requests=1)
    assert 'Actual supplied page'in fetch.article(source(1))
    pdf=EvidenceFetcher({'citation.original_reference_pdf_followup':True},get=get,requests=1)
    with pytest.raises(ValueError,match='not a PDF'):pdf.article(source(1))


def test_extraction_preserves_uncertainty_and_enforces_real_page_text_bounds(monkeypatch):
    pages=[SimpleNamespace(extract_text=lambda:'First page.'),SimpleNamespace(extract_text=lambda:'Second page.')]
    monkeypatch.setitem(sys.modules,'pypdf',SimpleNamespace(PdfReader=lambda stream:SimpleNamespace(pages=pages)))
    anchor=original_reference.original_reference_urls(source(1))[0]
    text=original_reference.extract_locator_pdf(b'%PDF-example',anchor)
    assert 'First page.\n\nSecond page.'in text
    assert 'NOT independently confirmed'in text
    assert hashlib.sha256(b'%PDF-example').hexdigest()in text
    with pytest.raises(ValueError,match='page bound'):
        original_reference.extract_locator_pdf(b'%PDF-example',anchor,max_pages=1)
    with pytest.raises(ValueError,match='text bound'):
        original_reference.extract_locator_pdf(b'%PDF-example',anchor,max_chars=23)
    with pytest.raises(ValueError,match='not a PDF'):
        original_reference.extract_locator_pdf(b'HTML',anchor)
