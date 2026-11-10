"""Exercise actual overlay methods without importing the full LDR/LangGraph app.

Only the enclosing application's dependencies and metadata checks are stubbed;
claim checking, revision, finalization, and service selection execute real code.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict

from loguru import logger
import pytest

from research_verify.config import get_config
from research_verify.evidence import SourceLookup
from research_verify.citation_qc import NO_VERIFIED_CLAIMS

ROOT = Path(__file__).resolve().parents[1]


def load_overlay_methods(path, names, class_name=None):
    tree = ast.parse(path.read_text())
    body = tree.body
    if class_name:
        body = next(
            node
            for node in body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ).body
    methods = [
        node
        for node in body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in methods} == set(names)
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "re": re,
        "logger": logger,
        "hashlib": hashlib,
        "json": json,
        "NO_RESULTS_MESSAGE": "No results",
    }
    code = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *methods,
        ],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(code), str(path), "exec"), namespace)
    return namespace


@pytest.fixture(autouse=True)
def fixed_config(monkeypatch, tmp_path):
    monkeypatch.setenv("LDR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LDR_VERIFY_ENABLE_VERIFY", "true")
    monkeypatch.setenv("LDR_VERIFY_ENABLE_CITATION_QC", "true")
    monkeypatch.setenv("LDR_VERIFY_QC_REVIEW_ROUNDS", "0")
    monkeypatch.setenv("LDR_VERIFY_QC_REPAIR_ROUNDS", "0")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


class EvidenceJudge:
    def invoke(self, prompt):
        claim = json.loads(prompt.rsplit("\n", 1)[-1])["claim"]
        payload = (
            {
                "verdict": "supported",
                "evidence_quotes": ["The method improves accuracy."],
            }
            if "improves" in claim
            else {"verdict": "insufficient_evidence"}
        )
        return type("Response", (), {"content": json.dumps(payload)})()


def strategy():
    methods = load_overlay_methods(
        ROOT / "langgraph_agent_strategy.py",
        ["_finalize", "_attach_citation_qc", "_write_citation_qc_json"],
        "LangGraphAgentStrategy",
    )

    class Strategy:
        _finalize = methods["_finalize"]
        _attach_citation_qc = methods["_attach_citation_qc"]
        _write_citation_qc_json = methods["_write_citation_qc_json"]
        model = EvidenceJudge()

        def _attach_doi_verification(self, sources):
            pass

        def _attach_constraint_match(self, query, sources):
            return False

        def _attach_keyword_coverage(self, query, sources):
            pass

        def _render_constraint_section(self, sources):
            return ""

        def _render_keyword_section(self, sources):
            return ""

        def _render_verify_section(self, sources):
            return ""

        def _update_progress(self, *args):
            pass

        def _format_citations(self, content, sources):
            return content + "\n\n## Sources\n[1] Test paper"

    sources = [
        {"index": "1", "doi": "10.test/paper", "body": "The method improves accuracy."}
    ]
    instance = Strategy()
    instance.collector = SourceLookup(sources)
    instance.collector.results = sources
    instance.collector.sources = ["https://example.test/paper"]
    instance.all_links_of_system = sources
    instance.citation_handler = type(
        "Handler",
        (),
        {
            "analyze_followup": lambda self, query, sources, previous_knowledge, nr_of_links: {
                "content": previous_knowledge
            }
        },
    )()
    return instance


def test_finalize_publishes_the_checked_body_to_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("LDR_DATA_DIR", str(tmp_path))
    instance = strategy()
    result = instance._finalize(
        "question",
        "The method improves accuracy [1]. Invented uncited result.",
        1,
        0,
        [],
    )
    body = result["current_knowledge"].split("### 摘要支持情况")[0]
    assert "improves accuracy" in body and "Invented" not in body
    assert result["findings"][0]["content"] == result["current_knowledge"]
    assert result["formatted_findings"].startswith(result["current_knowledge"])
    assert result["final_report"]["content"] == result["current_knowledge"]
    assert (
        result["final_report"]["content_sha256"]
        == hashlib.sha256(result["current_knowledge"].encode()).hexdigest()
    )
    audit = json.loads(next((tmp_path / "logs").glob("citation_qc_*.json")).read_text())
    assert audit["removed_claims"] == 1
    assert audit["scope"] == "claim_grounding_only"
    assert audit["checks"][0]["source_checks"][0]["evidence"][0]["field"] == "body"


def test_api_service_prefers_checked_report_over_old_final_synthesis():
    extract = load_overlay_methods(
        ROOT / "research_service.py", ["_extract_synthesized_answer"]
    )["_extract_synthesized_answer"]
    results = {
        "final_report": {"content": "Checked body"},
        "findings": [{"phase": "Final synthesis", "content": "Unverified old draft"}],
        "current_knowledge": "Another draft",
    }
    assert extract(results) == "Checked body"
    results["final_report"]["content"] = ""
    assert extract(results) == ""


@pytest.mark.parametrize("gate", ["strategy", "detailed_service"])
def test_publishing_gates_fetch_original_before_judging(gate, monkeypatch, tmp_path):
    from research_verify.source_evidence import ArticleEvidenceClient

    monkeypatch.setenv("LDR_DATA_DIR", str(tmp_path))
    fetched = []
    monkeypatch.setattr(ArticleEvidenceClient, "__enter__", lambda self: self)
    monkeypatch.setattr(ArticleEvidenceClient, "__exit__", lambda *args: None)

    def fetch(self, source):
        fetched.append(source["index"])
        return {"body": "The method improves accuracy.", "content_type": "full_text"}

    monkeypatch.setattr(ArticleEvidenceClient, "fetch", fetch)
    draft = "The method improves accuracy [1]. Invented uncited result."
    if gate == "strategy":
        instance = strategy()
        del instance.collector.find_by_index(1)["body"]
        content, _ = instance._attach_citation_qc(draft, instance.collector.results)
        audit = instance._citation_audit
    else:
        ground = load_overlay_methods(ROOT / "research_service.py", ["_ground_report_content"])["_ground_report_content"]
        content, audit = ground(draft, [{"index": "1", "doi": "10.test/paper"}], EvidenceJudge())
    assert fetched == ["1"]
    body = content.split("### 摘要支持情况")[0]
    assert "improves accuracy" in body and "Invented" not in body
    assert audit["evidence_preparation"]["body_sources"] == 1
    assert audit["checks"][0]["source_checks"][0]["body_verdict"] == "supported"


def test_disabled_qc_is_explicit_and_clears_previous_state(monkeypatch):
    monkeypatch.setenv("LDR_VERIFY_ENABLE_CITATION_QC", "false")
    get_config.cache_clear()
    instance = strategy()
    instance._citation_checks = ["stale"]
    content, checks = instance._attach_citation_qc("A draft.", [])
    assert content == "A draft." and checks == []
    assert (
        instance._citation_checks == []
        and instance._citation_audit["status"] == "disabled"
    )


def test_qc_exception_does_not_publish_raw_draft(monkeypatch):
    from research_verify.citation_qc import CitationQc

    monkeypatch.setattr(
        CitationQc,
        "verify_report",
        lambda *args: (_ for _ in ()).throw(RuntimeError("SECRET")),
    )
    content, checks = strategy()._attach_citation_qc("Unchecked raw draft [1].", [])
    assert "Unchecked" not in content and "SECRET" not in content and not checks


def test_detailed_final_gate_rechecks_new_synthesis():
    ground = load_overlay_methods(
        ROOT / "research_service.py", ["_ground_report_content"]
    )["_ground_report_content"]
    sources = [{"index": "1", "body": "The method improves accuracy."}]
    content, audit = ground(
        "## New synthesis\nThe method improves accuracy [1].\nUnsupported new claim [1].",
        sources,
        EvidenceJudge(),
    )
    body = content.split("### 摘要支持情况")[0]
    assert "Unsupported" not in body and "improves accuracy" in body
    assert audit["removed_claims"] == 1
    assert (
        audit["rendered_content_sha256"] == hashlib.sha256(content.encode()).hexdigest()
    )


def test_detailed_gate_discards_old_subsection_audits():
    ground = load_overlay_methods(
        ROOT / "research_service.py", ["_ground_report_content"]
    )["_ground_report_content"]
    content, audit = ground(
        "## First\nThe method improves accuracy [1].\n### 结论可溯源性核查\nOLD_AUDIT_CONTENT\n## Next\nThe method improves accuracy [1].",
        [{"index": "1", "body": "The method improves accuracy."}],
        EvidenceJudge(),
    )
    assert "OLD_AUDIT_CONTENT" not in content
    assert len(audit["checks"]) == 2


def test_detailed_gate_without_model_cannot_pass():
    ground = load_overlay_methods(
        ROOT / "research_service.py", ["_ground_report_content"]
    )["_ground_report_content"]
    content, audit = ground(
        "An invented result [1].", [{"index": "1", "body": "Some evidence."}], None
    )
    assert content.startswith(NO_VERIFIED_CLAIMS)
    assert audit["status"] == "unverifiable"


def test_detailed_gate_is_called_before_compaction_and_save():
    """Control-flow guard against fallback bypass in the real service function."""
    tree = ast.parse((ROOT / "research_service.py").read_text())
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    caller = next(
        f
        for f in funcs
        if any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "generate_report"
            for n in ast.walk(f)
        )
    )
    calls = [n for n in ast.walk(caller) if isinstance(n, ast.Call)]
    generate = next(
        n
        for n in calls
        if isinstance(n.func, ast.Attribute) and n.func.attr == "generate_report"
    )
    grounding = next(
        n
        for n in calls
        if isinstance(n.func, ast.Name)
        and n.func.id == "_ground_report_content"
        and n.lineno > generate.lineno
    )
    compact = next(
        n
        for n in calls
        if isinstance(n.func, ast.Name)
        and n.func.id == "_format_checked_answer"
        and n.lineno > grounding.lineno
    )
    save = next(
        n
        for n in calls
        if isinstance(n.func, ast.Attribute)
        and n.func.attr == "save_report"
        and n.lineno > compact.lineno
    )
    assert generate.lineno < grounding.lineno < compact.lineno < save.lineno
