"""Figure links retain evidence boundaries, never a visual support verdict."""
from research_verify.pmc_identity import article_graphics, article_text
from research_verify.evidence_fetch import EvidenceFetcher


META = ('<front><article-meta><article-id pub-id-type="pmid">123</article-id>'
        '<article-id pub-id-type="pmc">PMC456</article-id>'
        '<article-id pub-id-type="doi">10.1234/example</article-id>'
        '<article-title>Study A</article-title></article-meta></front>')
BODY = '''<body><sec><title>Procedure X</title>
<p>Follow <xref ref-type="fig" rid="F1 F2">panels 1 and 2</xref>.</p>
<fig id="F1"><label>Chart</label><caption><p>A caption, without the actual chart labels.</p></caption>
<graphic xlink:href="image-one.jpg"/></fig></sec>
<sec><title>Procedure Y</title><p>See <xref ref-type="bibr" rid="F1">a reference</xref>.</p>
<fig id="F2"><label>Chart</label><caption><p>Same label, another experiment.</p></caption>
<graphic xlink:href="image-two.jpg"/></fig>
<p>See <xref ref-type="fig" rid="MISSING">an unavailable figure</xref>.</p></sec></body>'''
XML = '<article xmlns:xlink="http://www.w3.org/1999/xlink">' + META + BODY + '</article>'
RECORD = dict(pmcid='PMC456', doi='10.1234/example', isOpenAccess='Y')


def test_cross_references_stay_with_own_figure_and_exact_section_path():
    result = article_graphics(XML, RECORD, '123')
    assert result['own_article_ids'] == dict(pmid='123', pmc='PMC456', doi='10.1234/example')
    first, second = result['figures']
    assert first['figure_id'] == 'F1' and first['section_path'] == ['Procedure X']
    assert second['figure_id'] == 'F2' and second['section_path'] == ['Procedure Y']
    assert first['references'] == second['references']
    assert len(first['references']) == 1  # bibliographic F1 is not a figure reference
    assert first['assets'] == [dict(href='image-one.jpg', content_type='unknown')]
    assert result['unresolved_references'][0]['figure_id'] == 'MISSING'
    assert first['visual_content_status'] == 'not_inspected_or_transcribed'
    assert result['semantic_verification'] == 'not_performed'


def test_wrong_article_and_ambiguous_figure_do_not_bind():
    assert article_graphics(XML, RECORD, '999') is None
    assert article_graphics(XML, {**RECORD, 'doi': '10.1234/another'}, '123') is None
    assert article_graphics(XML.replace('id="F2"', 'id="F1"'), RECORD, '123') is None
    assert article_graphics(XML.replace(' id="F2"', ''), RECORD, '123') is None


def test_default_text_is_unchanged_and_opt_in_never_invents_chart_labels():
    old = article_text(XML, RECORD, '123', require_body=True)
    assert old == article_text(XML, RECORD, '123', require_body=True, include_graphic_refs=False)
    enhanced = article_text(XML, RECORD, '123', require_body=True, include_graphic_refs=True)
    assert 'image-one.jpg' not in old and 'image-one.jpg' in enhanced
    assert 'NOT INSPECTED OR TRANSCRIBED' in enhanced
    for paragraph in old.split('\n\n'):
        assert paragraph in enhanced
    empty = '<article>' + META + '<body/></article>'
    assert article_text(empty, RECORD, '123', require_body=True, include_graphic_refs=True) is None


def test_figure_nested_inside_paragraph_keeps_whole_original_text_and_locator():
    xml = ('<article xmlns:xlink="http://www.w3.org/1999/xlink">' + META +
           '<body><sec><p>Before figure.<fig id="F3"><label>Figure 3</label>'
           '<caption><p>The caption.</p></caption><graphic xlink:href="nested.jpg"/>'
           '</fig>After figure.</p></sec></body></article>')
    baseline = article_text(xml, RECORD, '123', require_body=True)
    enhanced = article_text(xml, RECORD, '123', require_body=True, include_graphic_refs=True)
    assert all(part in enhanced for part in baseline.split('\n\n'))
    assert enhanced.count('nested.jpg') == 1
    assert article_graphics(xml, RECORD, '123')['figures'][0]['assets'][0]['href'] == 'nested.jpg'


def test_actual_fetcher_flag_adds_links_without_any_image_request():
    for enabled in [False, True]:
        fetcher = EvidenceFetcher({'citation.preserve_article_graphic_links': enabled})
        fetcher.record = lambda _: RECORD
        urls = []
        def read(url, **kwargs):
            urls.append(url)
            return XML
        fetcher.read = read
        result = fetcher.article({'pmid': '123', 'pmcid': 'PMC456'})
        assert ('image-one.jpg' in result) is enabled
        assert len(urls) == 1 and urls[0].endswith('/PMC456/fullTextXML')
        assert fetcher.article({'pmid': '123', 'pmcid': 'PMC456'}) == result
        assert len(urls) == 1
