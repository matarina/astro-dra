"""Date-scoped PubMed retries through the installed adapter."""
from types import SimpleNamespace

import pytest

from local_deep_research.web_search_engines.engines.search_engine_pubmed import (
    PubMedSearchEngine,
)


@pytest.mark.parametrize("scope", [
    '("2025/01/01"[Date - Publication] : "2026/11/11"[Date - Publication])',
    '"last 365 days"[pdat]',
])
def test_lexical_retries_retain_explicit_date_scope(monkeypatch, scope):
    optimized = []
    model = SimpleNamespace(invoke=lambda prompt: optimized.append(prompt))
    engine = PubMedSearchEngine(llm=model, optimize_queries=True)
    requests = []
    monkeypatch.setattr(engine, "_search_pubmed", lambda query: requests.append(query) or [])
    query = f"(responsive insertion technology colonoscopy cecal intubation time) AND {scope}"

    assert engine._get_previews(query) == []
    assert not optimized
    assert requests[0] == query and len(requests) > 1
    assert all(request.endswith(f" AND {scope}") for request in requests)


@pytest.mark.parametrize("query", [
    'responsive insertion colonoscopy OR 2025[dp]',
    'responsive insertion colonoscopy AND NOT 2025[dp]',
    'responsive insertion AND (colonoscopy OR 2025[dp])',
    'colonoscopy[Title] AND 2025[dp]',
    'colonoscopy OR endoscopy AND 2025[dp]',
])
def test_other_date_expressions_keep_the_exact_query(monkeypatch, query):
    engine = PubMedSearchEngine(llm=None, optimize_queries=False)
    requests = []
    monkeypatch.setattr(engine, "_search_pubmed", lambda term: requests.append(term) or [])

    assert engine._get_previews(query) == []
    assert requests == [query]


@pytest.mark.parametrize("scope", [
    '2025/01/01:2026/11/11[dp]',
    '2025:2026[Publication Date]',
])
def test_ambiguous_unquoted_date_range_is_not_broadened(monkeypatch, scope):
    engine = PubMedSearchEngine(llm=None, optimize_queries=False)
    requests = []
    monkeypatch.setattr(engine, "_search_pubmed", lambda term: requests.append(term) or [])
    query = f"responsive insertion technology AND {scope}"

    assert engine._get_previews(query) == []
    assert requests == [query]


def test_unscoped_queries_still_use_lexical_fallback(monkeypatch):
    engine = PubMedSearchEngine(llm=None, optimize_queries=False)
    requests = []
    monkeypatch.setattr(engine, "_search_pubmed", lambda term: requests.append(term) or [])

    assert engine._get_previews("responsive insertion technology colonoscopy cecal intubation time") == []
    assert requests[1] == "responsive insertion technology"
