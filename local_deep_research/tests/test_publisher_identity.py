import hashlib
from research_verify.publisher_identity import bind_original_pii,pubmed_pii_identity,publisher_url_pii


XML='''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">123</ArticleId><ArticleId IdType="doi">10.1000/example</ArticleId><ArticleId IdType="pii">S1234-5678(26)00001-2</ArticleId></ArticleIdList><ReferenceList><Reference><ArticleIdList><ArticleId IdType="pii">S9999-9999(26)00001-2</ArticleId></ArticleIdList></Reference></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>'''


def test_only_own_article_identifiers_bind_literal_original_locator():
    source=dict(index='4',original_bibliography_entry='[4] Partial title\nURL: https://www.sciencedirect.com/science/article/pii/S1234567826000012\n')
    source['original_bibliography_sha256']=hashlib.sha256(source['original_bibliography_entry'].encode()).hexdigest()
    known=dict(index='9',pmid='123',doi='10.1000/example')
    proof=bind_original_pii(source,known,XML)
    assert proof['pii']=='S1234567826000012' and proof['source_index']=='4'
    assert source.get('doi') is None
    wrong=dict(source,original_bibliography_entry='[4] Title\nURL: https://www.sciencedirect.com/science/article/pii/S9999999926000012\n')
    wrong['original_bibliography_sha256']=hashlib.sha256(wrong['original_bibliography_entry'].encode()).hexdigest()
    assert bind_original_pii(wrong,known,XML) is None
    assert bind_original_pii(dict(source,doi='10.1000/different'),known,XML) is None


def test_wrong_article_conflicting_ids_and_spoofed_hosts_remain_unknown():
    assert pubmed_pii_identity(XML,pmid='999',doi='10.1000/example') is None
    assert pubmed_pii_identity(XML,pmid='123',doi='10.1000/different') is None
    conflicting=XML.replace('</ArticleIdList><ReferenceList>','<ArticleId IdType="doi">10.1000/different</ArticleId></ArticleIdList><ReferenceList>')
    assert pubmed_pii_identity(conflicting,pmid='123',doi='10.1000/example') is None
    assert publisher_url_pii('https://www.sciencedirect.com.evil.test/science/article/pii/S1234567826000012') is None
    assert publisher_url_pii('https://example.com/?pii=S1234567826000012') is None


def test_cell_encoded_fulltext_and_pdf_are_exact_pii_not_title_matches():
    expected='S2211124724015808'
    assert publisher_url_pii('https://www.cell.com/cell-reports/pdf/S2211-1247%2824%2901580-8.pdf')==expected
    assert publisher_url_pii('https://www.cell.com/cell-reports/fulltext/S2211-1247%2824%2901580-8')==expected
    assert publisher_url_pii('https://cell.com/cell-reports/fulltext/S2211124724015808')==expected
    assert publisher_url_pii('https://www.cell.com.evil.test/cell-reports/fulltext/S2211124724015808')is None
    assert publisher_url_pii('https://www.cell.com/cell-reports/fulltext/other?pii=S2211124724015808')is None
    assert publisher_url_pii('https://www.cell.com/cell-reports/fulltext/S2211124724015808.pdf')is None


def test_cell_locator_still_requires_own_pubmed_article_id_proof():
    entry='[4] Partial title\nURL: https://www.cell.com/cell/fulltext/S1234-5678%2826%2900001-2\n'
    source=dict(index='4',original_bibliography_entry=entry,
                original_bibliography_sha256=hashlib.sha256(entry.encode()).hexdigest())
    known=dict(index='9',pmid='123',doi='10.1000/example')
    assert bind_original_pii(source,known,XML)['pii']=='S1234567826000012'
    assert bind_original_pii(source,dict(known,doi='10.1000/different'),XML)is None
