"""Large candidate pools retain complete abstracts and source identity."""
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from research_verify.generation import format_source_documents, page_excerpts
from research_verify.pmc_identity import academic_url_ids, article_text
from test_generation_grounding import handler
from test_runtime_repairs import downloader

ROOT = Path(__file__).parents[1]


def documents(count=500, length=1800):
    return [SimpleNamespace(page_content=(f'Original evidence {i}. ' + 'x' * length),
             metadata={'index': i, 'title': f'Paper {i}', 'source': f'https://example.org/{i}',
                       'evidence_type': 'abstract (not the full paper)',
                       'abstract': f'Original evidence {i}. ' + 'x' * length})
            for i in range(1, count + 1)]


def test_203_papers_keep_full_abstracts_instead_of_394_character_slices():
    docs = documents(203, 700)
    calls = []
    rendered = format_source_documents(docs, 'Evidence?', selector=lambda p: calls.append(p))
    assert calls == []
    assert all(doc.metadata['abstract'] in rendered for doc in docs)
    assert 'complete supplied abstract' in rendered


def test_large_pool_is_batched_then_writer_gets_original_abstracts_with_sparse_ids():
    docs = documents()
    original = [doc.page_content for doc in docs]
    prompts = []
    def select(prompt):
        prompts.append(prompt)
        ids = list(map(int, re.findall(r'^\[(\d+)\]$', prompt, re.M)))
        assert all(docs[i - 1].metadata['abstract'] in prompt for i in ids)
        return json.dumps({"selected_source_ids": ids[-4:][::-1]})
    rendered = format_source_documents(docs, 'Question', selector=select)
    ids = list(map(int, re.findall(r'^\[(\d+)\]$', rendered, re.M)))
    assert len(prompts) > 1 and 0 < len(ids) < 500
    assert len(rendered) <= 200000
    assert all(docs[i - 1].metadata['abstract'] in rendered for i in ids)
    assert max(ids) == 500  # late candidates participate, original IDs survive
    assert original == [doc.page_content for doc in docs]
    assert all(len(p) < 52000 for p in prompts)


@pytest.mark.parametrize('reply', ['I select 999.', '{"selected_source_ids": [999]}',
                                   '{"selected_source_ids": [true]}', '{"selected_source_ids": []}'])
def test_selection_outage_cannot_invent_sources_or_shorten_abstracts(reply):
    docs = documents(12, 1200)
    rendered = format_source_documents(docs, 'Question', selector=lambda p: reply, max_chars=6000)
    ids = list(map(int, re.findall(r'^\[(\d+)\]$', rendered, re.M)))
    assert not ids
    assert len(rendered) <= 6000
    assert all(docs[i - 1].metadata['abstract'] in rendered for i in ids)


def test_writer_retains_abstract_when_fetched_body_is_added():
    abstract = 'The abstract reports no benefit. ' * 60
    raw = 'Introduction.\n\n' * 1000 + 'Endpoint analysis found no benefit.'
    seen = []
    writer = handler(SimpleNamespace(invoke=lambda p: seen.append(p) or SimpleNamespace(content='No benefit [17].')))
    writer.analyze_followup('Endpoint analysis?', [{'index': 17, 'abstract': abstract,
                            'fetched_content': raw}], '', 0)
    assert abstract in seen[-1] and 'Endpoint analysis found no benefit.' in seen[-1]


def test_page_view_searches_beyond_old_10k_limit_and_retains_original_text():
    raw = 'Unrelated introduction.\n\n' * 1800 + 'Methods\n\nEndpoint regression analysis used a mixed-effects model.'
    assert raw.index('Endpoint regression') > 10000
    view = page_excerpts(raw, 'Endpoint regression mixed-effects', budget=18000)
    assert 'Endpoint regression analysis used a mixed-effects model.' in view
    assert len(view) < 18500
    assert raw.endswith('mixed-effects model.')


def test_claim_directed_query_reaches_distant_methods_passage_without_scientific_rules():
    abstract = 'The study analyzed a tumor cohort with transcriptomics.'
    body = ('Introduction.\n\n' * 900
            + 'Methods\n\nThe spatial assay used 10x Genomics Visium on seven samples.\n\n'
            + 'Results\n\nThe study found an association.')
    doc = SimpleNamespace(page_content=abstract + '\n\n' + body, metadata={
        'index': 13, 'title': 'Study', 'source': 'https://example.org/13',
        'abstract': abstract, 'evidence_type': 'retrieved text (completeness unconfirmed)'})
    query = 'Which spatial platform and sample count did the draft claim? Visium seven samples'
    rendered = format_source_documents([doc], query, max_chars=6000)
    assert '10x Genomics Visium' in rendered and 'seven samples' in rendered


@pytest.mark.parametrize('url, expected', [
    ('https://europepmc.org/article/MED/123', ('123', None)),
    ('https://www.europepmc.org/article/PMC/PMC456', (None, 'PMC456')),
    ('https://europepmc.org/articles/PMC456', (None, 'PMC456')),
    ('https://pmc.ncbi.nlm.nih.gov/articles/PMC456/', (None, 'PMC456')),
    ('https://example.org/?url=https://europepmc.org/article/MED/123', (None, None)),
    ('https://europepmc.org.evil.example/article/MED/123', (None, None)),
    ('https://europepmc.org/article/PPR/PPR123', (None, None)),
])
def test_academic_routing_uses_host_and_own_article_path(url, expected):
    assert academic_url_ids(url) == expected


def test_europepmc_med_download_reaches_text_api_without_html_or_pdf():
    d = downloader()
    calls = []
    d._fetch_text_from_europe_pmc = lambda pmid, pmcid: calls.append((pmid, pmcid)) or 'Verified original body.'
    d._download_pdf_content = lambda _: pytest.fail('Text API should succeed first')
    assert d._download_text('https://europepmc.org/article/MED/123') == b'Verified original body.'
    assert calls == [('123', None)]


def test_xml_body_does_not_spend_excerpt_budget_on_authors_and_references():
    xml = ('<article><front><article-meta><article-id pub-id-type="pmid">123</article-id>'
           '<title-group><article-title>Original title</article-title></title-group>'
           '<contrib-group><name>Irrelevant author</name></contrib-group>'
           '<abstract><p>Abstract finding.</p></abstract></article-meta></front>'
           '<body><sec><title>Methods</title><p>Endpoint regression did <italic>not</italic> improve.</p></sec></body>'
           '<back><ref-list><ref>Unrelated referenced claim.</ref></ref-list></back></article>')
    text = article_text(xml, {}, pmid='123')
    assert 'Abstract finding.' in text and 'Methods\n\nEndpoint regression did not improve.' in text
    assert 'Irrelevant author' not in text and 'Unrelated referenced claim' not in text
