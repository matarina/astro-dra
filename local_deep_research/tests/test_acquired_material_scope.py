"""Explicit article-body contracts must survive the writer boundary."""
import pytest

from research_verify.generation import source_material
from research_verify.source_evidence import ArticleEvidenceClient, _body_available


@pytest.mark.parametrize('kind', ['full_text', 'fulltext', 'full-text', 'body'])
def test_declared_body_is_not_hidden_by_the_abstract(kind):
    source = {'abstract': 'Abstract omits the procedure.',
              'body': 'Methods: procedure and important exclusion.', 'content_type': kind}
    assert _body_available(source)
    text, scope = source_material(source)
    assert text == source['body']
    assert scope == 'retrieved full text (only the supplied text is available)'


def test_generic_page_and_untyped_body_do_not_become_article_fulltext():
    source = {'abstract': 'Original abstract.', 'body': 'Unclassified text.',
              'fetched_content': 'Publisher page or access notice.', 'content_type': 'abstract'}
    text, scope = source_material(source)
    assert source['abstract'] in text and source['fetched_content'] in text
    assert source['body'] not in text
    assert scope == 'supplied abstract and separately retrieved page excerpt (completeness unconfirmed)'


def test_article_fetch_and_unconfirmed_web_fallback_keep_different_scope():
    class CachedFetcher:
        def article(self, source):
            return 'Article body with supplied limitations.' if source['index'] == '1' else None

        def web(self, title, url):
            return [{'fetched_content': 'Access restricted. Abstract only.'}]

    client = ArticleEvidenceClient(fetcher=CachedFetcher())
    article = {'index': '1', 'abstract': 'Old abstract.', 'content_type': 'abstract'}
    page = {'index': '2', 'abstract': 'Old abstract.', 'link': 'https://example.org/paper'}
    article.update(client.fetch(article))
    page.update(client.fetch(page))
    assert source_material(article) == (article['body'], 'retrieved full text (only the supplied text is available)')
    text, scope = source_material(page)
    assert 'Old abstract.' in text and 'Access restricted.' in text
    assert 'full text' not in scope and 'page excerpt' in scope


def test_actual_writer_view_scope_does_not_apply_old_abstract_label_to_added_text():
    from types import SimpleNamespace
    from research_verify.generation import _source_blocks
    abstract='The supplied abstract.'
    body='Methods\n\nAn original procedure and its condition.'
    doc=SimpleNamespace(page_content=abstract+'\n\n'+body,metadata={
        'index':7,'title':'Study','abstract':abstract,'evidence_type':'abstract (not the full paper); page excerpt'})
    views=[]
    _,block=next(_source_blocks([doc],'Original request',views,complete_acquired=True))
    assert block.split('BEGIN SOURCE TEXT\n')[1].split('\nEND SOURCE TEXT')[0]==doc.page_content
    assert 'Evidence type: complete acquired text supplied; published-paper completeness unconfirmed' in block
    assert 'abstract (not the full paper)' not in block
    assert views[0]['acquisition_evidence_type']==doc.metadata['evidence_type']
    assert views[0]['view_kind']=='complete_acquired_text' and not views[0]['exhaustive_assessment']
    _,selected=next(_source_blocks([doc],'Original request'))
    assert 'Evidence type: complete supplied abstract and additional acquired excerpts' in selected
    doc.page_content=abstract
    _,abstract_only=next(_source_blocks([doc],'Original request'))
    assert 'Evidence type: abstract (not the full paper)' in abstract_only


def test_empty_acquired_view_is_metadata_only_even_in_complete_acquired_mode():
    from types import SimpleNamespace
    from research_verify.generation import _source_blocks
    doc=SimpleNamespace(page_content='',metadata={'index':1,'title':'Title only','evidence_type':'search snippet'})
    views=[]
    _,block=next(_source_blocks([doc],'Request',views,complete_acquired=True))
    assert views[0]['view_kind']=='metadata_only' and views[0]['text']==''
    assert 'Evidence type: metadata only; no source text supplied' in block
    assert 'complete acquired text' not in block
