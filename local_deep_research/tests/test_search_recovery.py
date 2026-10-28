"""Retrieval constraints, shared pacing, complete records and source identity."""
import ast
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import re
import runpy
import sys
from types import SimpleNamespace
import typing
import xml.etree.ElementTree as ET

from loguru import logger
import pytest

from research_verify import retrieval
from research_verify.source_relations import epmc_relations, pubmed_relations

ROOT = Path(__file__).parents[1]


class Base:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.rate_tracker = SimpleNamespace(apply_rate_limit=lambda _: 0)
        self.engine_type = "pubmed"

    def _create_journal_filter(self, *args):
        return None

    def _scrub_error(self, value):
        return str(value)


def engine_class(file, name, **overrides):
    tree = ast.parse((ROOT / file).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    ns = {**vars(typing), "BaseSearchEngine": Base, "BaseLLM": object, "re": re,
          "ET": ET, "logger": logger, "SNIPPET_LENGTH_LONG": 1200,
          "Sensitivity": SimpleNamespace(NON_SENSITIVE=1),
          "Exposure": SimpleNamespace(EXPOSING=1), "html_text": retrieval.html_text,
          "academic_snippet": retrieval.academic_snippet,
          "xml_text": retrieval.xml_text, "epmc_relations": epmc_relations,
          "pubmed_relations": pubmed_relations,
          **overrides}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), file, "exec"), ns)
    return ns[name]


XML = ('<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article>'
       '<Abstract><AbstractText Label="RESULTS">Visium did <i>not</i> change GENE<sup>1</sup>.</AbstractText></Abstract>'
       '<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>'
       '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>')


def test_pubmed_abstract_and_metadata_reuse_one_real_record_request():
    calls = []
    def request(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=XML)
    cls = engine_class("search_engine_pubmed.py", "PubMedSearchEngine", safe_get=request,
                       service_get=lambda url, **kw: request(url, **kw))
    engine = cls(max_results=6)
    assert engine.max_results == 6
    assert engine._get_article_abstracts(["1"])["1"] == "RESULTS: Visium did not change GENE [superscript:1]."
    assert engine._get_article_detailed_metadata(["1"])["1"]["publication_types"] == ["Journal Article"]
    assert engine._get_article_abstracts(["1"])["1"].count("Visium") == 1
    assert len(calls) == 1
    assert calls[0]["params"]["id"] == "1"


def test_pubmed_preserves_explicit_scope_even_with_zero_results():
    cls = engine_class("search_engine_pubmed.py", "PubMedSearchEngine")
    model = SimpleNamespace(invoke=lambda prompt: pytest.fail("Structured query must not be rewritten"))
    engine = cls(llm=model)
    query = '"Visium HD"[Title/Abstract] AND ("2022/01/01"[dp] : "2026/10/19"[dp])'
    assert engine._optimize_query_for_pubmed(query) == query
    calls = []
    engine._search_pubmed = lambda q: calls.append(q) or []
    assert engine._adaptive_search(query) == ([], "requested_scope")
    assert calls == [query]
    assert engine._simplify_query(query) == query


def test_optimizer_losing_year_or_quoted_entity_keeps_original():
    cls = engine_class("search_engine_pubmed.py", "PubMedSearchEngine")
    engine = cls(llm=SimpleNamespace(invoke=lambda p: SimpleNamespace(content='spatial transcriptomics')))
    query = 'Find "Visium HD" studies from 2022 to 2026'
    assert engine._optimize_query_for_pubmed(query) == query


def test_europepmc_has_correct_identity_and_complete_inline_abstract():
    sent = []
    payload = {"resultList": {"result": [{"id": "1", "source": "MED", "pmcid": "PMC123",
        "doi": "10.1234/test", "title": "Visium study", "firstPublicationDate": "2024-01-02",
        "journalInfo": {"journal": {"title": "Journal A"}},
        "pubTypeList": {"pubType": ["Journal Article"]},
        "abstractText": "<h4>Results</h4><p>GENE<i>1</i> did <b>not</b> improve.</p>"}]}}
    def request(url, **kwargs):
        sent.append(kwargs)
        return SimpleNamespace(json=lambda: payload)
    cls = engine_class("overlay/search_engine_europepmc.py", "EuropePMCSearchEngine", service_get=request)
    query = 'Visium AND FIRST_PDATE:[2022-01-01 TO 2026-10-19]'
    item = cls()._get_previews(query)[0]["_full_result"]
    assert item["link"] == "https://europepmc.org/article/MED/1"
    assert item["pmid"] == "1" and item["pmcid"] == "PMC123"
    assert item["journal"] == "Journal A" and item["doi"] == "10.1234/test"
    assert item["abstract"] == "Results\nGENE1 did not improve."
    assert item["content_type"] == "abstract"
    assert sent[0]["params"]["query"] == query
    assert sent[0]["params"]["resultType"] == "core"


def test_europepmc_distinguishes_zero_results_from_invalid_response():
    payload = {"hitCount": 0}
    cls = engine_class("overlay/search_engine_europepmc.py", "EuropePMCSearchEngine",
                       service_get=lambda *a, **k: SimpleNamespace(json=lambda: payload))
    assert cls()._get_previews("nonexistent") == []
    payload.clear()
    payload.update({"error": "Invalid query"})
    with pytest.raises(ValueError):
        cls()._get_previews("invalid")


def test_relevance_parser_never_selects_indices_from_rejected_prose():
    import json
    tree = ast.parse((ROOT / "overlay/relevance_filter.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_parse_indices")
    ns = {"json": json, "re": re, "List": typing.List}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "relevance_filter", "exec"), ns)
    parse = ns["_parse_indices"]
    assert parse("[]") == []
    assert parse("NONE") == []
    assert parse("[0, 2]") == [0, 2]
    assert parse("```json\n[1]\n```") == [1]
    assert parse("0, 2") == [0, 2]
    assert parse('["1"]') == [1]
    for invalid in ("Reject 0, 1 and 2: unrelated sports from 2024.", "[true]", "[-1]", '{}', ''):
        with pytest.raises(ValueError):
            parse(invalid)


def test_screening_sees_assay_past_the_display_snippet():
    from datetime import datetime, UTC
    tree = ast.parse((ROOT / "overlay/relevance_filter.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_build_batch_prompt")
    ns = {**vars(typing), "datetime": datetime, "UTC": UTC, "_SNIPPET_CHAR_CAP": 800}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "relevance_filter", "exec"), ns)
    abstract = "Context. " * 120 + "We used Visium HD and observed no improvement."
    prompt = ns["_build_batch_prompt"]("Visium HD", [{"title": "Study", "snippet": abstract[:500],
                        "abstract": abstract, "journal": "Journal", "pubdate": "2025"}], 1, "{preview_text}")
    assert "We used Visium HD and observed no improvement." in prompt
    assert "2025" in prompt


def test_agent_snippet_keeps_identity_and_abstract_without_duplicate_prefixes():
    abstract = "Opening context. " * 100 + "Visium HD had no improvement."
    snippet = retrieval.academic_snippet({"title": "Study", "pmid": "123", "doi": "10.1234/paper",
                   "journal": "Journal", "pubdate": "2024", "publication_types": ["Journal Article"]}, abstract)
    assert "PMID: 123" in snippet and "DOI: 10.1234/paper" in snippet
    assert snippet.count("Abstract:") == 1 and snippet.count("Title:") == 1
    assert snippet.endswith(abstract) and "Evidence level: abstract" in snippet
    empty = retrieval.academic_snippet({"title": "Study"}, "")
    assert "metadata only" in empty and "Abstract unavailable" in empty


def test_search_only_installer_preserves_existing_publication_modules(tmp_path, monkeypatch):
    import importlib.util
    import sysconfig
    installed = tmp_path / "site/local_deep_research"
    source = tmp_path / "source"
    verify = tmp_path / "site/research_verify"
    (installed / "web_search_engines/engines").mkdir(parents=True)
    (installed / "defaults").mkdir()
    (source / "research_verify").mkdir(parents=True)
    verify.mkdir()
    (verify / "__init__.py").write_text("")
    (verify / "publication.py").write_text("ORIGINAL = True\n")
    (source / "research_verify/publication.py").write_text("UNRELATED = True\n")
    (source / "research_verify/retrieval.py").write_text("RETRIEVAL = True\n")
    (source / "engine.py").write_text("class Engine: pass\n")
    (installed / "defaults/default_settings.json").write_text(json.dumps({"search.tool": {"value": "searxng", "options": []}}))
    (source / "search_defaults.json").write_text(json.dumps({"search.max_results": 12}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"engine.py": "web_search_engines/engines/search_engine_europepmc.py"}))
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: SimpleNamespace(submodule_search_locations=[str(installed)]))
    monkeypatch.setattr(sysconfig, "get_path", lambda _: str(tmp_path / "site"))
    monkeypatch.setattr(sys, "argv", ["install_overlays", "--source", str(source), "--manifest", str(manifest), "--search-only"])
    installer = ROOT.parent / "deployment/install_overlays.py"
    runpy.run_path(str(installer), run_name="__main__")
    assert (verify / "publication.py").read_text() == "ORIGINAL = True\n"
    assert (verify / "retrieval.py").read_text() == "RETRIEVAL = True\n"
    assert (installed / "web_search_engines/engines/search_engine_europepmc.py").is_file()
    defaults = json.loads((installed / "defaults/default_settings.json").read_text())
    assert defaults["search.max_results"]["value"] == 12
    manifest.write_text(json.dumps({"engine.py": "report_generator.py"}))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(installer), run_name="__main__")
    assert exc.value.code == 2


def test_retry_after_is_honored_and_retries_are_bounded(monkeypatch):
    monkeypatch.setattr(retrieval, "pace", lambda *a, **k: None)
    sleeps, calls = [], []
    def request(url, **kwargs):
        calls.append(url)
        status = 429 if len(calls) == 1 else 200
        return SimpleNamespace(status_code=status, headers={"Retry-After": "2"},
                               close=lambda: None, raise_for_status=lambda: None)
    response = retrieval.service_get("https://example.test", service="ncbi", interval=.37,
                                     get=request, sleep=sleeps.append)
    assert response.status_code == 200 and len(calls) == 2 and sleeps == [2]
    calls.clear()
    def fail(url, **kwargs):
        calls.append(url)
        raise OSError("transient connection failure")
    with pytest.raises(OSError):
        retrieval.service_get("https://example.test", service="ncbi", interval=.37,
                              get=fail, sleep=lambda _: None)
    assert len(calls) == 3


def _paced_worker(directory):
    import time
    retrieval.pace("process-test", .03, directory=directory)
    return time.monotonic()


def test_pacing_is_shared_by_separate_processes(tmp_path):
    with ProcessPoolExecutor(max_workers=4) as workers:
        values = sorted(workers.map(_paced_worker, [str(tmp_path)] * 4))
    assert all(b - a >= .025 for a, b in zip(values, values[1:]))
