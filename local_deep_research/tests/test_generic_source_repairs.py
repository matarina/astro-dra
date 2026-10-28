"""General markup, source aliases, notice propagation, and private tool records."""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from research_verify.retrieval import html_text, xml_text, academic_snippet
from research_verify.source_identity import identity_fields, reconcile_identities
from research_verify.source_relations import epmc_relations, pubmed_relations, associated_notices
from research_verify.publication import publish_report
from research_verify.config import VerifyConfig
from research_verify.synthesis_trace import trace_context, record_tool_results
from test_source_collection import collector
from test_generation_grounding import handler
from test_synthesis_trace import read_stages
from research_verify.generation import format_source_documents


def test_markup_roles_do_not_become_name_suffixes_or_disappear():
    text = html_text('Instrument<sup>3</sup>; 10<sup>−3</sup>; H<sub>2</sub>O; Ca<sup>2+</sup>.')
    assert 'Instrument3' not in text and '[superscript:3]' in text
    assert '[superscript:−3]' in text and '[subscript:2]' in text
    assert '[superscript:2+]' in text
    assert html_text('GENE<i>1</i> did <b>not</b> improve. Version 3′.') == 'GENE1 did not improve. Version 3′.'


def test_typed_article_reference_remains_distinct_from_math_superscript():
    node = ET.fromstring('<p>Method<sup><xref ref-type="bibr" rid="R3">3</xref></sup> with 10<sup>3</sup> features.</p>')
    text = xml_text(node)
    assert 'Method3' not in text and '[article-ref:3]' in text
    assert '[superscript:3]' in text
    assert 'superscript: [article-ref' not in text


@pytest.mark.parametrize('url,expected', [
    ('https://www.nature.com/articles/s41467-024-54715-y?utm_source=test', {'doi': '10.1038/s41467-024-54715-y'}),
    ('https://doi.org/10.1000/Example', {'doi': '10.1000/example'}),
    ('https://pubmed.ncbi.nlm.nih.gov/12345/', {'pmid': '12345'}),
    ('https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/', {'pmcid': 'PMC12345'}),
    ('https://europepmc.org/article/MED/12345', {'pmid': '12345'}),
    ('https://link.springer.com/article/10.1186/s13046-025-03479-4', {'doi': '10.1186/s13046-025-03479-4'}),
    ('https://www.nature.com.evil.example/articles/s41467-024-54715-y', {}),
    ('https://example.org/?doi=10.1000/example&pmid=12345', {}),
    ('https://www.nature.com/articles/s41467-024-54715-y/figures/1', {}),
])
def test_identity_uses_only_known_article_url_structure(url, expected):
    assert identity_fields({'link': url}) == expected


def test_fetch_reuses_existing_article_and_keeps_acquired_text():
    c = collector()
    hits = [{'title': 'Study', 'doi': '10.1038/s41467-024-54715-y', 'pmid': '12345',
             'link': 'https://pubmed.ncbi.nlm.nih.gov/12345/', 'abstract': 'Original abstract.'}]
    c.add_results(hits)
    n = c.find_or_add_result({'title': 'Study | Publisher',
          'link': 'https://www.nature.com/articles/s41467-024-54715-y', 'fetched_content': 'Acquired original methods.'}, 'fetch')
    assert n == 1 and len(c.results) == 1
    assert c.results[0]['abstract'] == 'Original abstract.'
    assert c.results[0]['fetched_content'] == 'Acquired original methods.'


def test_publication_resolves_aliases_in_both_citation_orders_without_mutating_text():
    sources = [{'index': 8, 'link': 'https://pubmed.ncbi.nlm.nih.gov/12345/', 'abstract': 'Abstract.'},
               {'index': 9, 'pmid': '12345', 'doi': '10.1000/article', 'link': 'https://example.org/article', 'fetched_content': 'Methods.'}]
    original = [dict(s) for s in sources]
    for text in ['A [8]. B [9].', 'B [9]. A [8].']:
        p = publish_report(text, sources, cfg=VerifyConfig(enable_verify=False))
        assert len(p.sources) == 1 and set(p.sources[0].original_indices) == {8, 9}
        assert p.report_body == text and p.sources[0].paper_id == 'doi:10.1000/article'
    assert sources == original


def test_conflicting_identifiers_and_same_titles_do_not_force_merge():
    records = [{'index': 1, 'pmid': '12', 'doi': '10.1000/a', 'title': 'Same title'},
               {'index': 2, 'pmid': '12', 'doi': '10.1000/b', 'title': 'Same title'}]
    normalized = reconcile_identities(records)
    assert normalized[0]['doi'] != normalized[1]['doi']
    p = publish_report('A [1]. B [2].', records, cfg=VerifyConfig(enable_verify=False))
    assert len(p.sources) == 2
    assert identity_fields({'doi': '10.1000/explicit', 'link': 'https://doi.org/10.1000/other'}) == {'doi': '10.1000/explicit'}


def test_notice_metadata_from_both_engines_is_explicit_not_title_guessed():
    raw = {'commentCorrectionList': {'commentCorrection': [{'type': 'Erratum in', 'source': 'MED', 'id': '200',
             'reference': 'Correction doi: 10.1000/notice.'}]}}
    relationships = epmc_relations(raw)
    assert relationships[0]['relation_type'] == 'erratum_in'
    xml = ET.fromstring('<PubmedArticle><CommentsCorrectionsList><CommentsCorrections RefType="ErratumIn"><PMID>200</PMID><RefSource>doi: 10.1000/notice.</RefSource></CommentsCorrections></CommentsCorrectionsList></PubmedArticle>')
    assert pubmed_relations(xml) == relationships
    assert 'https://pubmed.ncbi.nlm.nih.gov/200/' in academic_snippet({'related_articles': relationships}, 'Abstract')


def test_notice_stays_with_selected_article_even_when_not_selected_itself():
    sources = [{'index': 9, 'title': 'Original', 'pmid': '100', 'link': 'https://pubmed.ncbi.nlm.nih.gov/100/',
                'abstract': 'Relevant original abstract. ' * 40,
                'related_articles': [{'relation_type': 'erratum_in', 'pmid': '200'}]},
               {'index': 10, 'title': 'Notice', 'pmid': '200', 'link': 'https://pubmed.ncbi.nlm.nih.gov/200/',
                'snippet': 'Correction published. No abstract available.', 'content_type': 'metadata'},
               {'index': 11, 'title': 'Other study', 'abstract': 'Other original material. ' * 220}]
    docs = handler(SimpleNamespace())._create_documents(sources)
    text = format_source_documents(docs, 'Question', selector=lambda _: '[9]', max_chars=4000)
    assert '[9]\nTitle: Original' in text and '[10]\nTitle:' not in text
    assert 'RELATED PUBLICATION NOTICE' in text and 'Notice source index: 10' in text
    assert 'https://pubmed.ncbi.nlm.nih.gov/200/' in text and 'metadata only' in text
    assert len(text) <= 4000


def test_reverse_notice_relation_and_unretrieved_notice_are_carried():
    sources = [{'index': 1, 'pmid': '100', 'abstract': 'Original.',
                'related_articles': [{'relation_type': 'erratum_in', 'pmid': '300'}]},
               {'index': 2, 'pmid': '200', 'snippet': 'Published notice.',
                'related_articles': [{'relation_type': 'erratum_for', 'pmid': '100'}]}]
    docs = handler(SimpleNamespace())._create_documents(sources)
    first = format_source_documents(docs[:1], 'Question')
    assert '/300/' in first and '/200/' in first
    assert 'Notice text not retrieved' in first


def test_conflicting_notice_identifiers_do_not_attach_another_papers_text():
    sources = [{'index': 1, 'pmid': '100', 'abstract': 'Original.',
                'related_articles': [{'relation_type': 'erratum_in', 'pmid': '200', 'doi': '10.1000/notice'}]},
               {'index': 2, 'pmid': '200', 'doi': '10.1000/other', 'abstract': 'Unrelated notice text.'}]
    notice = associated_notices(sources)['1'][0]
    assert notice['source_index'] is None and notice['text'] == ''
    assert notice['doi'] == '10.1000/notice'


def test_nonrecord_entries_remain_ignored_by_document_adapter():
    docs = handler(SimpleNamespace())._create_documents([None, 'ignored', {'abstract': 'Original.'}])
    assert len(docs) == 1 and docs[0].page_content == 'Original.'


def test_tool_returns_are_private_and_keep_call_id(tmp_path, monkeypatch):
    monkeypatch.setenv('LDR_RESEARCH_TRACE_ENABLED', 'true')
    monkeypatch.setenv('LDR_RESEARCH_TRACE_DIR', str(tmp_path))
    with trace_context('tool-task'):
        record_tool_results([SimpleNamespace(type='tool', content='Actual tool return.', tool_call_id='call-123')])
    rows = read_stages(tmp_path)['tool_messages'][0]['messages']
    assert rows[0]['role'] == 'tool' and rows[0]['tool_call_id'] == 'call-123'
    assert rows[0]['content'] == 'Actual tool return.'
