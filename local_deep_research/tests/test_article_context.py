import hashlib

from research_verify.article_context import article_context_index, attach_article_context


META = ('<front><article-meta><article-id pub-id-type="pmid">123</article-id>'
        '<article-id pub-id-type="pmc">PMC456</article-id>'
        '<article-id pub-id-type="doi">10.1234/example</article-id>'
        '<abstract><p>Abstract-only result.</p></abstract></article-meta></front>')
BODY = ('<body><sec id="methods"><title>Methods</title>'
        '<sec id="A"><label>2.4.</label><title>Dataset A</title><p>Two fractions were pooled.</p></sec>'
        '<sec id="CD"><label>2.6.</label><title>Datasets C and D</title><p>Magnetic selection.</p></sec>'
        '<sec><p>Repeated control.</p></sec><sec><p>Repeated control.</p></sec>'
        '<fig id="F1"><caption><p>Figure caption.</p></caption></fig></sec></body>')
XML = '<article>' + META + BODY + '<back><ref-list><p>Unrelated cited paper.</p></ref-list></back></article>'
RECORD = dict(pmcid='PMC456', doi='10.1234/example')


def unit(source, number, text):
    return dict(material_id='source', source_id=source, unit_id=number, kind='text',
                text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())


def test_sibling_datasets_retain_own_ancestors_and_exact_paragraphs():
    index = article_context_index(XML, RECORD, '123')
    units = [unit(7, 0, 'Two fractions were pooled.'), unit(7, 1, 'Magnetic selection.')]
    enriched = attach_article_context(units, {7: index})
    assert [r['original_context']['section_path'][-1]['title'] for r in enriched] == ['Dataset A', 'Datasets C and D']
    assert [r['original_context']['section_path'][-1]['label'] for r in enriched] == ['2.4.', '2.6.']
    assert all(r['original_context']['section_path'][0]['title'] == 'Methods' for r in enriched)
    assert all({k:v for k,v in r.items() if k != 'original_context'} == u for r,u in zip(enriched,units))


def test_same_words_in_multiple_contexts_are_ambiguous_and_other_source_is_not_bound():
    index = article_context_index(XML, RECORD, '123')
    result = attach_article_context([unit(7, 0, 'Repeated control.'), unit(8, 0, 'Magnetic selection.')], {7: index})
    assert result[0]['original_context']['status'] == 'ambiguous_same_text'
    assert result[0]['original_context']['match_count'] == 2
    assert 'section_path' not in result[0]['original_context']
    assert result[1]['original_context']['status'] == 'no_identity_bound_xml'


def test_body_abstract_caption_and_reference_scopes_remain_distinct():
    index = article_context_index(XML, RECORD, '123')
    bytext = {r['text']:r for r in index['paragraphs']}
    assert bytext['Abstract-only result.']['evidence_scope'] == 'abstract'
    assert bytext['Magnetic selection.']['evidence_scope'] == 'body'
    assert [r['kind'] for r in bytext['Figure caption.']['containers']] == ['fig', 'caption']
    assert 'Unrelated cited paper.' not in bytext
    assert index['semantic_verification'] == 'not_performed'


def test_missing_or_wrong_requested_identity_never_binds():
    assert article_context_index(XML, RECORD, '999') is None
    assert article_context_index(XML, {**RECORD, 'doi':'10.1234/other'}, '123') is None
    assert article_context_index(XML.replace('<article-id pub-id-type="pmid">123</article-id>', ''), RECORD, '123') is None


def test_namespaced_jats_and_untitled_section_do_not_acquire_guessed_labels():
    xml = XML.replace('<article>', '<article xmlns="urn:jats">')
    index = article_context_index(xml, RECORD, '123')
    repeated = [r for r in index['paragraphs'] if r['text'] == 'Repeated control.']
    assert len(repeated) == 2
    assert all(r['section_path'][-1]['title'] == '' for r in repeated)
    assert repeated[0]['section_path'][-1]['xml_path'] != repeated[1]['section_path'][-1]['xml_path']


def test_nested_article_or_cited_reference_never_becomes_own_paragraph_context():
    foreign = '<sub-article><body><sec><title>Other article</title><p>Foreign protocol.</p></sec></body></sub-article>'
    xml = XML.replace('</body>', foreign + '<ref-list><p>Nested reference.</p></ref-list></body>', 1)
    index = article_context_index(xml, RECORD, '123')
    assert not {'Foreign protocol.', 'Nested reference.'} & {r['text'] for r in index['paragraphs']}
