"""Generic parser, article identity and generation-switch regression cases."""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from contextvars import copy_context
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace
import typing
from urllib.parse import urlparse

from loguru import logger
import pytest

from research_verify.pmc_identity import own_pmc_id, europepmc_record, article_text, academic_url_ids
from research_verify.config import VerifyConfig
from research_verify.publication import publish_report
from test_generation_grounding import handler
from research_verify.synthesis_trace import source_snapshot

ROOT = Path(__file__).parents[1]


def relevance():
    from local_deep_research.web_search_engines.relevance_filter import filter_previews_for_relevance
    return {'filter_previews_for_relevance': filter_previews_for_relevance}


@pytest.mark.parametrize('response', [
    '```JSON\n{"selected_source_ids": [0, 2]}\n```',
    '{"selected_source_ids": [0, 2, 2]}',
    '<think>ignore 99</think>{"selected_source_ids": [0, 2]}',
])
def test_only_explicit_selections_are_normalized(response):
    from research_verify.structured_output import source_ids
    assert source_ids(response, range(3)) == [0, 2]


def test_valid_empty_selection_is_not_an_error_or_retried():
    messages = io.StringIO(); sink = logger.add(messages)
    calls = []
    model = SimpleNamespace(invoke=lambda p: calls.append(p) or SimpleNamespace(content='{"selected_source_ids": []}'))
    try:
        result = relevance()['filter_previews_for_relevance'](model, [{'title': 'Example'}] * 3, 'query')
    finally:
        logger.remove(sink)
    assert result == [] and len(calls) == 1
    assert '| ERROR ' not in messages.getvalue() and '| WARNING ' not in messages.getvalue()


def test_bad_format_retries_once_without_mining_explanation_numbers():
    outputs = iter(['Reject 0 and 1 from 2024.', '{"selected_source_ids": [1]}']); calls = []
    model = SimpleNamespace(invoke=lambda p: calls.append(p) or SimpleNamespace(content=next(outputs)))
    rows = [{'title': 'First'}, {'title': 'Second'}]
    result = relevance()['filter_previews_for_relevance'](model, rows, 'query')
    assert result == [dict(rows[1], relevance_filter_status='screened')] and len(calls) == 2


def test_two_invalid_responses_are_labeled_unavailable_not_irrelevant():
    calls = []
    model = SimpleNamespace(invoke=lambda p: calls.append(p) or SimpleNamespace(content='Reject 0.'))
    result = relevance()['filter_previews_for_relevance'](model, [{'title': 'Example'}], 'query')
    assert len(calls) == 2 and result[0]['relevance_filter_status'] == 'screening_incomplete'


def downloader():
    tree = ast.parse((ROOT / 'overlay/pubmed_downloader.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PubMedDownloader')
    ns = {'BaseDownloader': object, 'ContentType': SimpleNamespace(PDF='pdf', TEXT='text'),
          'DownloadResult': SimpleNamespace, 'Optional': typing.Optional, 'logger': logger,
          're': re, 'time': time, 'urlparse': urlparse, 'own_pmc_id': own_pmc_id,
          'europepmc_record': europepmc_record, 'article_text': article_text,
          'academic_url_ids': academic_url_ids}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'pubmed_downloader', 'exec'), ns)
    return ns['PubMedDownloader'].__new__(ns['PubMedDownloader'])


def test_citing_article_is_never_a_fulltext_mapping_or_html_fallback():
    d = downloader(); calls = []
    data = {'linksets': [{'ids': ['123'], 'linksetdbs': [
        {'dbto': 'pmc', 'linkname': 'pubmed_pmc_refs', 'links': ['999']}]}]}
    def get(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: data)
    d.session = SimpleNamespace(get=get)
    assert d._get_pmc_id_from_pmid('123') is None
    assert len(calls) == 1 and calls[0]['params']['linkname'] == 'pubmed_pmc'
    data['linksets'][0]['linksetdbs'].append({'dbto': 'pmc', 'linkname': 'pubmed_pmc', 'links': ['456']})
    assert d._get_pmc_id_from_pmid('123') == 'PMC456'


def test_europepmc_metadata_must_identify_requested_medline_article():
    wrong = {'source': 'PAT', 'id': '123', 'pmcid': 'PMC999'}
    correct = {'source': 'MED', 'id': '123', 'pmcid': 'PMC456'}
    data = {'resultList': {'result': [wrong, correct]}}
    assert europepmc_record(data, pmid='123') is correct
    assert europepmc_record(data, pmid='123', pmcid='PMC999') is None


def test_fulltext_identity_is_checked_in_front_metadata_not_references():
    xml = '<article><front><article-meta><article-id pub-id-type="pmid">999</article-id><article-id pub-id-type="pmc">PMC999</article-id></article-meta></front><body><p>No improvement.</p></body><back><ref><article-id pub-id-type="pmid">123</article-id></ref></back></article>'
    assert article_text(xml, {'pmcid': 'PMC456'}, pmid='123') is None
    correct = xml.replace('>999<', '>123<').replace('>PMC999<', '>PMC456<')
    assert 'No improvement.' in article_text(correct, {'pmcid': 'PMC456'}, pmid='123')


def test_native_consistency_reviews_actual_final_writer_output(native_review_only):
    calls = []
    def invoke(prompt):
        calls.append(prompt)
        return SimpleNamespace(content='No improvement [7].' if len(calls) == 1 else '{"issues":[]}')
    writer = handler(SimpleNamespace(invoke=invoke))
    writer.settings_snapshot['general.enable_fact_checking'] = True
    result = writer.analyze_followup('Outcome?', [{'index': '7', 'abstract': 'No improvement.',
                       'title': 'Example', 'link': 'https://example.org/paper', 'doi': '10.1000/paper',
                       'journal': 'Example Journal', 'pubdate': '2024 Nov'}], 'Improvement [7].', 0)
    assert len(calls) == 2 and 'FINAL ANSWER' in calls[1]
    assert 'No improvement [7].' in calls[1]
    assert 'DOI: 10.1000/paper' in calls[0] and 'Date: 2024 Nov' in calls[1]
    assert 'Journal: Example Journal' in calls[0]
    assert result['content'] == 'No improvement [7].'


def test_empty_length_response_retries_with_larger_completion_budget():
    class LengthThenText:
        def __init__(self):
            self.calls = 0
            self.bound_tokens = None

        def invoke(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    content='',
                    response_metadata={
                        'finish_reason': 'length',
                        'token_usage': {'completion_tokens': 6000},
                    },
                )
            return SimpleNamespace(content='{"issues": []}', response_metadata={
                'finish_reason': 'stop',
            })

        def bind(self, **kwargs):
            self.bound_tokens = kwargs.get('max_tokens')
            return self

    model = LengthThenText()
    writer = handler(model)
    writer.settings_snapshot['citation.empty_response_retry_max_tokens'] = 12000
    assert writer._invoke_text('structured review', stage='source_reading') == '{"issues": []}'
    assert model.calls == 2 and model.bound_tokens == 12000


def test_source_reading_retries_and_writer_rejects_unanchored_continuation():
    class LengthThenComplete:
        def __init__(self):
            self.calls = 0
            self.bound_tokens = None

        def invoke(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(content='```json {"readings": [', response_metadata={
                    'finish_reason': 'length', 'token_usage': {'completion_tokens': 6000}})
            return SimpleNamespace(content='{"readings": []}', response_metadata={
                'finish_reason': 'stop'})

        def bind(self, **kwargs):
            self.bound_tokens = kwargs.get('max_tokens')
            return self

    model = LengthThenComplete()
    writer = handler(model)
    writer.settings_snapshot['citation.empty_response_retry_max_tokens'] = 12000
    assert writer._invoke_text('source reading', stage='source_reading') == '{"readings": []}'
    assert model.calls == 2 and model.bound_tokens == 12000

    prose = LengthThenComplete()
    prose_writer = handler(prose)
    assert prose_writer._invoke_text('writer prose', stage='writer') == '```json {"readings": ['
    assert prose.calls == 2 and prose.bound_tokens is None
    assert prose_writer._writer_incomplete is True


def test_source_snapshot_preserves_scope_and_evidence_metadata():
    result = source_snapshot([{
        'index': 1, 'title': 'Study', 'language': ['zh'],
        'platform': 'Visium', 'technology': 'spatial transcriptomics',
        'population': 'human', 'sample_size': 12, 'groups': 'case/control',
        'outcome': 'spatial pattern', 'impact_factor': 4.2,
        'impact_factor_provenance': {'source': 'journal_quality'}, 'abstract': 'Evidence.',
    }])
    assert result[0]['language'] == ['zh']
    assert result[0]['platform'] == 'Visium'
    assert result[0]['technology'] == 'spatial transcriptomics'
    assert result[0]['population'] == 'human'
    assert result[0]['impact_factor'] == 4.2
    assert result[0]['impact_factor_provenance']['source'] == 'journal_quality'


def test_citation_qc_can_be_disabled_independently_of_publication(monkeypatch):
    monkeypatch.setenv('LDR_VERIFY_ENABLE_CITATION_QC', 'false')
    model = SimpleNamespace(invoke=lambda p: pytest.fail('Post-report judge must not run'))
    p = publish_report('Observed [7].', [{'index': '7', 'abstract': 'Observed.',
                        'link': 'https://example.org/paper', 'title': 'Example'}], model, VerifyConfig())
    assert p.audit_status == 'disabled' and not p.citation_audit
    assert '[[1]](https://example.org/paper)' in p.content
