"""Identity consistency and search feedback, independent of a research topic."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import threading
from urllib.parse import urlparse

from research_verify.source_collection import SourceCollectionMixin, format_collection_results


def collector(limit=80):
    path = Path(__file__).parents[1] / "langgraph_agent_strategy.py"
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SearchResultsCollector")
    namespace = {"threading": threading, "re": re, "urlparse": urlparse,
                 "DEFAULT_MAX_UNIQUE_SOURCES": 80, "PREPRINT_HOSTS": set(),
                 "canonical_url_key": lambda url: url.rstrip("/")}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    class Collector(SourceCollectionMixin, namespace["SearchResultsCollector"]):
        pass
    return Collector(max_results=limit)


def record(doi="10.1000/published", **extra):
    return {"doi": doi, "title": "A reproducible benchmark for robot navigation",
            "link": "https://example.org/" + doi, "journal": "Robotics Journal",
            "pubdate": "2025", "abstract": "No improvement was observed.",
            "snippet": "Published record.", **extra}


def test_same_title_different_identifiers_keeps_versions_separate():
    c = collector()
    first = [record()]
    c.add_results(first)
    second = [record("10.1000/preprint", pubdate="2024", journal="",
                     snippet="Preprint identity. " * 100)]
    c.add_results(second)
    assert len(c.results) == 2
    assert c.results[0]["doi"] == "10.1000/published"
    assert c.results[0]["snippet"] == "Published record."
    assert second[0]["index"] == "2"


def test_same_identifier_reuses_index_and_renders_consistent_identity():
    c = collector()
    c.add_results([record(pmid="123")])
    batch = [record("https://doi.org/10.1000/published", pmid="123",
                    abstract="Longer abstract. No improvement was observed.",
                    snippet="Conflicting embedded header. " * 100)]
    offset = c.add_results(batch)
    assert len(c.results) == 1 and batch[0]["index"] == "1"
    assert offset.reused == 1 and offset.added == 0
    assert "DOI: 10.1000/published" in batch[0]["snippet"]
    assert "Conflicting embedded header" not in batch[0]["snippet"]
    assert "No improvement was observed." in batch[0]["snippet"]


def test_full_budget_reports_new_hits_and_still_returns_later_known_hit():
    c = collector(limit=10)
    c.add_results([record(f"10.1000/{i}") for i in range(10)])
    batch = [record("10.1000/new"), record("10.1000/1")]
    offset = c.add_results(batch)
    assert len(c.results) == 10 and len(batch) == 1 and batch[0]["index"] == "2"
    assert len(offset.unregistered) == 1 and offset.reused == 1
    text = format_collection_results(batch, offset, lambda rows, start: "Known [2]")
    assert "budget is full" in text and "Known [2]" in text
    assert "10.1000/new" in text and "[11]" not in text
    assert "No results." not in text


def test_concurrent_duplicate_returns_one_stable_source_to_each_caller():
    c = collector()
    def add(_):
        batch = [record()]
        c.add_results(batch)
        return batch[0]["index"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(add, range(12))) == ["1"] * 12
    assert len(c.results) == 1
