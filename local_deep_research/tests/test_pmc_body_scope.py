"""Full-text acquisition cannot promote abstract-only PMC metadata to a body."""
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.pmc_identity import article_text
from types import SimpleNamespace
from test_runtime_repairs import downloader


FRONT = ('<front><article-meta><article-id pub-id-type="pmid">123</article-id>'
         '<article-id pub-id-type="pmc">PMC456</article-id>'
         '<abstract><p>Useful abstract remains available.</p></abstract>'
         '</article-meta></front>')
RECORD = dict(source='MED', id='123', pmcid='PMC456', isOpenAccess='Y')


def test_abstract_remains_parseable_but_is_not_fulltext():
    for body in ('', '<body/>', '<body><p>  </p></body>'):
        xml = '<article>' + FRONT + body + '</article>'
        assert 'Useful abstract remains available.' in article_text(xml, RECORD, '123')
        assert article_text(xml, RECORD, '123', require_body=True) is None


def test_fulltext_keeps_abstract_and_body_qualifiers():
    xml = '<article>' + FRONT + '<body><p>Method did <italic>not</italic> improve.</p></body></article>'
    old = article_text(xml, RECORD, '123')
    assert article_text(xml, RECORD, '123', require_body=True) == old
    assert 'Method did not improve.' in old


def test_fetcher_does_not_register_abstract_as_new_article_body():
    fetch = EvidenceFetcher(get=lambda *a, **k: None)
    fetch.record = lambda source: RECORD
    fetch.read = lambda *a, **k: '<article>' + FRONT + '</article>'
    source = dict(index='7', pmid='123', abstract='Existing abstract.')
    assert fetch.article(source) is None
    assert source == dict(index='7', pmid='123', abstract='Existing abstract.')


def test_downloader_fulltext_path_requires_body_without_losing_abstract_parser():
    d = downloader()
    for body in ('', '<body><p>Actual method.</p></body>'):
        responses = iter([
            SimpleNamespace(status_code=200, json=lambda: {'resultList': {'result': [RECORD]}}),
            SimpleNamespace(status_code=200, text='<article>' + FRONT + body + '</article>'),
        ])
        d.session = SimpleNamespace(get=lambda *args, **kwargs: next(responses))
        result = d._fetch_text_from_europe_pmc('123', None)
        if body:
            assert 'Actual method.' in result and 'Useful abstract remains available.' in result
        else:
            assert result is None
