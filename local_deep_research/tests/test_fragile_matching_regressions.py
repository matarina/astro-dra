"""Regression coverage for syntax-preserving fallbacks and evidence windows."""

import ast
from pathlib import Path
from types import SimpleNamespace

from research_verify.evidence import Artifact, retrieve, source_artifacts
from research_verify.passages import retrieve_passages
from research_verify.retrieval import fallback_query_candidates, has_structured_query_syntax
from research_verify.textutil import normalize_year
from overlay.url_classifier import URLClassifier, URLType


def test_boolean_exclusion_is_never_rewritten_as_positive_fallback():
    assert fallback_query_candidates("cancer NOT pediatric") == []
    assert fallback_query_candidates('"lung cancer"[Title/Abstract] AND adult') == []


def test_no_overlap_samples_distant_sections_instead_of_opening_only():
    text = "Abstract overview.\n\nMethods: distant cohort and assay.\n\nResults: distant outcome."
    passages = retrieve_passages(text, "完全不同的中文问题", window_chars=48, max_passages=3)
    assert len(passages) >= 2
    assert any("Methods" in item.text for item in passages)
    assert any("Results" in item.text for item in passages)


def test_evidence_retrieval_uses_same_selector_and_preserves_offsets():
    text = "Preamble.\n\nMethods: cohort and assay.\n\nResults: outcome and qualifier."
    artifact = Artifact("body", "body", text, start=0, end=len(text))
    chunks = retrieve(artifact, "unrelated 中文 claim", chunk_chars=48, top_k=3, context_chars=140)
    assert len(chunks) >= 2
    assert any("Methods" in item.text for item in chunks)
    assert all(text[item.start:item.end] == item.text for item in chunks)


def test_unusual_body_heading_is_preserved_as_uncertain_scope():
    abstract = "Abstract evidence."
    body = "Abstract\nAbstract evidence.\n\nExperimental details under a publisher-specific heading."
    abstract_artifact, body_artifact = source_artifacts({
        "content_type": "full_text", "abstract": abstract, "body": body,
        "link": "https://example.org/article",
    })
    assert abstract_artifact is not None
    assert body_artifact is not None
    assert "Experimental details" in body_artifact.text[body_artifact.start:body_artifact.end]
    assert "uncertain" in body_artifact.basis


def test_pubmed_simplifier_keeps_structured_query_semantics():
    query = '(cancer[Title/Abstract] NOT pediatric[Title/Abstract]) AND "last 5 years"[pdat]'
    tree = ast.parse((Path(__file__).parents[1] / "search_engine_pubmed.py").read_text())
    methods = {node.name: node for node in next(node for node in tree.body
              if isinstance(node, ast.ClassDef) and node.name == "PubMedSearchEngine").body
               if isinstance(node, ast.FunctionDef) and node.name in {"_simplify_query", "_extract_core_terms"}}
    namespace = {"re": __import__("re"), "has_structured_query_syntax": has_structured_query_syntax,
                 "logger": SimpleNamespace(info=lambda *a, **k: None, debug=lambda *a, **k: None)}
    for method in methods.values():
        exec(compile(ast.Module(body=[method], type_ignores=[]), "search_engine_pubmed.py", "exec"), namespace)
    engine = SimpleNamespace(_simplify_query=namespace["_simplify_query"].__get__(None, object),
                             _extract_core_terms=namespace["_extract_core_terms"].__get__(None, object))
    # Bind the extracted functions to a minimal instance.
    engine._simplify_query = lambda value: namespace["_simplify_query"](engine, value)
    engine._extract_core_terms = lambda value: namespace["_extract_core_terms"](engine, value)
    assert engine._simplify_query(query) == query
    assert engine._extract_core_terms(query) == query


def test_year_parser_does_not_mine_doi_or_prose():
    assert normalize_year("2024-06-01") == 2024
    assert normalize_year("DOI 10.1234/2024abc") is None
    assert normalize_year("cohort 2024") is None


def test_url_identity_requires_authoritative_host_and_path():
    assert URLClassifier.classify("https://pubmed.ncbi.nlm.nih.gov/123/") == URLType.PUBMED
    assert URLClassifier.extract_id("https://pubmed.ncbi.nlm.nih.gov/123/") == "123"
    for hostile in (
        "https://evil.example/pubmed.ncbi.nlm.nih.gov/123",
        "https://evil.example/?next=https://pubmed.ncbi.nlm.nih.gov/123",
    ):
        assert URLClassifier.classify(hostile) != URLType.PUBMED
        assert URLClassifier.extract_id(hostile) is None


def test_json_recovery_preserves_url_slashes_while_removing_real_comment():
    tree = ast.parse((Path(__file__).parents[1] / "overlay/utilities/json_utils.py").read_text())
    namespace = {}
    definition = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_strip_json_comments")
    exec(compile(ast.Module(body=[definition], type_ignores=[]), "json_utils.py", "exec"), namespace)
    raw = '{"url":"https://example.org/a//b", "value": 1 // comment\n}'
    cleaned = namespace["_strip_json_comments"](raw)
    assert 'https://example.org/a//b' in cleaned
    assert 'comment' not in cleaned


