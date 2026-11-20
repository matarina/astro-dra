import pytest
from scripts.probe_pubmed_bound_pmc_20261115 import bound_record, bound_body


SOURCE = dict(pmid='123', doi='10.1000/paper')
EXPECTED = dict(pmid='123', doi='10.1000/paper', pmcid='PMC456')
PUBMED = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">123</ArticleId><ArticleId IdType="doi">10.1000/paper</ArticleId><ArticleId IdType="pmc">PMC456</ArticleId></ArticleIdList><ReferenceList><ArticleIdList><ArticleId IdType="pmc">PMC999</ArticleId></ArticleIdList></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>'''
PMC = b'''<pmc-articleset><article><front><article-meta><article-id pub-id-type="pmid">123</article-id><article-id pub-id-type="pmc">456</article-id><article-id pub-id-type="doi">10.1000/paper</article-id><title-group><article-title>Actual title</article-title></title-group></article-meta></front><body><sec><title>Methods</title><p>Complete useful method.</p></sec></body><back><ref-list><ref><mixed-citation>Unrelated evidence.</mixed-citation></ref></ref-list></back></article></pmc-articleset>'''


def test_only_own_identity_and_body_are_used():
    assert bound_record(PUBMED, SOURCE) == EXPECTED
    body = bound_body(PMC, EXPECTED)
    assert 'Complete useful method.' in body
    assert 'Unrelated evidence.' not in body


def test_reference_only_pmc_and_conflicting_own_ids_are_rejected():
    with pytest.raises(ValueError):
        bound_record(PUBMED.replace(b'<ArticleId IdType="pmc">PMC456</ArticleId>', b''), SOURCE)
    with pytest.raises(ValueError):
        bound_record(PUBMED.replace(b'PMC456</ArticleId>', b'PMC456</ArticleId><ArticleId IdType="pmc">PMC777</ArticleId>'), SOURCE)
    with pytest.raises(ValueError):
        bound_body(PMC.replace(b'>123</article-id>', b'>999</article-id>'), EXPECTED)
    with pytest.raises(ValueError):
        bound_body(PMC.replace(b'<article-id pub-id-type="pmc">456</article-id>', b''), EXPECTED)


def test_multiple_articles_or_abstract_only_do_not_count_as_body():
    article = PMC.removeprefix(b'<pmc-articleset>').removesuffix(b'</pmc-articleset>')
    with pytest.raises(ValueError):
        bound_body(b'<pmc-articleset>' + article + article + b'</pmc-articleset>', EXPECTED)
    with pytest.raises(ValueError):
        bound_body(PMC.replace(b'<body>', b'<abstract>').replace(b'</body>', b'</abstract>'), EXPECTED)
