"""Offline adapter and draft contracts; no report-quality success claim."""
import ast
import os
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

import pytest

from research_verify.generation import prepare_draft_for_writing
from research_verify.retrieval import has_structured_query_syntax, xml_text


ROOT = Path(__file__).parents[1]


def adapter_methods(*names, response=None):
    # Execute the actual overlay methods with a frozen transport. This isolates
    # XML/query behavior from optional upstream app imports, without model calls.
    tree = ast.parse((ROOT / "search_engine_pubmed.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PubMedSearchEngine")
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    nodes.extend(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_search_proxy_kwargs")
    ns = dict(os=os, List=List, Dict=Dict, Tuple=Tuple, ET=ET, re=re, xml_text=xml_text,
              has_structured_query_syntax=has_structured_query_syntax,
              logger=SimpleNamespace(**{k: lambda *a, **kw: None for k in ("debug", "info", "warning")}),
              safe_get=lambda *a, **kw: response)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pubmed_overlay", "exec"), ns)
    return ns


@pytest.mark.parametrize("annotation", [
    "Interpretation: A measured decrease was reported [17].",
    "**Interpretation:** Could a follow-up distinguish the explanations [17]?",
    "解读：原文记录了关联，但不能推出因果关系 [17]。",
    "**解读（Interpretation）：** 这一观察是否可用于下一步实验 [17]？",
])
def test_original_annotation_and_useful_table_are_preserved(annotation):
    draft = "## Notes\n\n" + annotation + "\n\n| Patient | Value |\n| --- | --- |\n| ID-9 | 12 [17] |"
    prepared, notes = prepare_draft_for_writing(draft)
    assert prepared == draft
    assert notes == [dict(original=annotation, source_ids=[17], kind="draft_annotation", scientific_status="unknown")]


def test_primary_abstract_preserves_sections_nested_text_and_translation_boundary():
    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article>
    <Abstract><AbstractText Label="METHODS">CD<sup>4</sup> cells &lt; 5.</AbstractText>
    <AbstractText Label="RESULTS">No improvement in <i>either</i> group.</AbstractText></Abstract>
    </Article><OtherAbstract><AbstractText>Separate translation.</AbstractText></OtherAbstract>
    </MedlineCitation></PubmedArticle><PubmedArticle><MedlineCitation><PMID>456</PMID><Article/>
    <OtherAbstract><AbstractText>Only a translation.</AbstractText></OtherAbstract>
    </MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    response = SimpleNamespace(text=xml, status_code=200, raise_for_status=lambda: None)
    methods = adapter_methods("_get_article_abstracts", "_fetch_article_xml", response=response)
    obj = SimpleNamespace(api_key=None, rate_tracker=SimpleNamespace(apply_rate_limit=lambda *a: 0),
                          engine_type="pubmed", fetch_url="frozen-xml", _scrub_error=str)
    obj._fetch_article_xml = lambda ids: methods["_fetch_article_xml"](obj, ids)
    result = methods["_get_article_abstracts"](obj, ["123", "456"])
    assert result == {"123": "METHODS: CD [superscript:4] cells < 5.\n\nRESULTS: No improvement in either group."}


@pytest.mark.parametrize("query", [
    'cells NOT cancer', 'cells OR cancer', 'cells[Title]', '"exact phrase"',
    '(cells OR cancer) AND human', 'cells AND "last 365 days"[pdat]',
    'cells AND ("2025/01/01"[dp] : "2026/11/11"[dp])',
    'specific tumor assay without prior treatment',
])
def test_pubmed_queries_are_not_broadened_on_zero_hits(query):
    names = ("_optimize_query_for_pubmed", "_adaptive_search", "_get_previews")
    methods = adapter_methods(*names)
    obj = SimpleNamespace(llm=SimpleNamespace(invoke=lambda *a: pytest.fail("unexpected model call")),
                          optimize_queries=has_structured_query_syntax(query))
    calls = []
    obj._search_pubmed = lambda q: calls.append(q) or []
    for name in names:
        setattr(obj, name, lambda *a, _name=name: methods[_name](obj, *a))
    assert obj._get_previews(query) == []
    assert calls == [query]


def test_unscoped_search_does_not_infer_a_recency_requirement():
    calls = []
    obj = SimpleNamespace(_search_pubmed=lambda q: calls.append(q) or ["123"])
    method = adapter_methods("_adaptive_search")["_adaptive_search"]
    assert method(obj, "cell signaling") == (["123"], "requested_scope")
    assert calls == ["cell signaling"]
