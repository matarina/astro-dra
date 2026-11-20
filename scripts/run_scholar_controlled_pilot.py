#!/usr/bin/env python3
"""Run bounded frozen-source scholar arms in an isolated container.

The runner never searches or fetches evidence.  It records each arm's exact
source hash, settings, model responses, latency and failure state.  A
supplemented arm is deliberately labelled as an evidence intervention rather
than a retrieval comparison.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(case: dict, arm: str, root: Path, out_root: Path) -> dict:
    from loguru import logger
    logger.remove()
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handler import CitationHandler
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy, SearchResultsCollector
    from research_verify.synthesis_trace import trace_context
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    from research_verify import source_evidence

    class FrozenEvidence:
        def record(self, *args, **kwargs): return None
        def pmc_identifiers(self, *args, **kwargs): return {}
        def article(self, *args, **kwargs): return ''
        def web(self, *args, **kwargs): return []

    source_path = root / case["source_files"]["supplemented" if "supplemented" in arm else "base"]
    sources = json.loads(source_path.read_text(encoding="utf-8"))
    out = out_root / case["case_id"] / arm
    out.mkdir(parents=True, exist_ok=True)
    os.environ["LDR_DATA_DIR"] = str(out / "data")
    os.environ["LDR_RESEARCH_TRACE_ENABLED"] = "true"
    os.environ["LDR_RESEARCH_TRACE_DIR"] = str(out / "traces")
    os.environ["LDR_VERIFY_ENABLE_DOI_VALIDATION"] = "false"
    os.environ["LDR_VERIFY_ENABLE_CITATION_QC"] = "false"

    defaults = Path(__import__("local_deep_research").__file__).parent / "defaults/default_settings.json"
    snapshot = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in json.loads(defaults.read_text()).items()})
    snapshot.update({
        "llm.provider": "openai_endpoint", "llm.model": "deepseek-v4-flash", "llm.temperature": 0,
        "llm.max_tokens": 5000, "llm.request_timeout": 600, "llm.max_retries": 1,
        "general.enable_fact_checking": True, "citation.enable_source_reading": True,
        "citation.enable_source_reading_roles": "candidate_a" in arm,
        "citation.fresh_evidence_synthesis": "candidate_b" in arm,
        "citation.max_review_calls": 6,
        "citation.empty_response_retry_max_tokens": 10000,
        "search.tool": "pubmed", "search.iterations": 1, "search.questions_per_iteration": 1,
    })

    class CountingModel:
        def __init__(self, model): self.model, self.events = model, []
        def __getattr__(self, name): return getattr(self.model, name)
        def invoke(self, prompt, *args, **kwargs):
            event = {"prompt": str(prompt), "started": time.time()}
            started = time.monotonic()
            try:
                response = self.model.invoke(prompt, *args, **kwargs)
                event.update(status="completed", response=getattr(response, "content", str(response)),
                             metadata=getattr(response, "response_metadata", {}))
                return response
            except Exception as exc:
                event.update(status="error", error_type=type(exc).__name__)
                raise
            finally:
                event["elapsed_s"] = round(time.monotonic() - started, 3)
                self.events.append(event)

    row = {
        "case_id": case["case_id"], "arm": arm, "model": "deepseek-v4-flash",
        "query": case["query"], "source_file": str(source_path),
        "source_sha256": digest_file(source_path), "source_count": len(sources),
        "settings": {k: snapshot.get(k) for k in (
            "llm.model", "llm.temperature", "llm.max_tokens", "general.enable_fact_checking",
            "citation.enable_source_reading_roles", "citation.fresh_evidence_synthesis",
            "citation.max_review_calls")},
        "status": "running", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    draft_path = case.get("draft_files", {}).get(arm) or case.get("draft_files", {}).get("default")
    draft = ""
    if draft_path:
        draft_file = root / draft_path
        draft = draft_file.read_text(encoding="utf-8")
        row["draft_file"] = str(draft_file)
        row["draft_sha256"] = hashlib.sha256(draft.encode()).hexdigest()
    else:
        row["draft_sha256"] = hashlib.sha256(b"").hexdigest()
    row["draft_chars"] = len(draft)
    original_init = source_evidence.ArticleEvidenceClient.__init__
    def frozen_init(self, *args, **kwargs):
        kwargs["fetcher"] = FrozenEvidence()
        original_init(self, *args, **kwargs)
    source_evidence.ArticleEvidenceClient.__init__ = frozen_init
    started = time.monotonic()
    model = None
    try:
        with settings_context(SimpleNamespace(username=None, get_setting=lambda k, d=None: snapshot.get(k, d))):
            model = CountingModel(get_llm(settings_snapshot=snapshot))
            strategy = LangGraphAgentStrategy.__new__(LangGraphAgentStrategy)
            strategy.model = model; strategy.settings_snapshot = snapshot
            strategy.get_setting = lambda k, d=None: snapshot.get(k, d)
            strategy.collector = SearchResultsCollector()
            strategy.collector._results = copy.deepcopy(sources)
            strategy.collector._sources = [s.get("link", "") for s in sources]
            strategy.all_links_of_system = []; strategy._update_progress = lambda *a, **k: None
            strategy._build_egress_context = lambda: None; strategy._format_citations = lambda body, records: body
            strategy.citation_handler = CitationHandler(model, handler_type="standard", settings_snapshot=snapshot)
            handler = getattr(strategy.citation_handler, "_handler", strategy.citation_handler)
            handler.evidence_fetcher = FrozenEvidence()
            with trace_context(f"scholar-pilot-{case['case_id']}-{arm}"):
                result = strategy._finalize(case["query"], draft, 0, 0, [])
            body = result.get("current_knowledge") or ""
            if not body.strip():
                raise RuntimeError("empty_report")
            publication = publish_report(body, result.get("search_results", sources), cfg=VerifyConfig(enable_citation_qc=False))
            row.update(status="completed", body=body, references=len(publication.sources), report_chars=len(body),
                       publication=publication.metadata(), research_result={k: result.get(k) for k in ("error", "iterations")},
                       model_calls=len(model.events))
            (out / "report.md").write_text(body, encoding="utf-8")
    except BaseException as exc:
        row.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                   error_type=type(exc).__name__, error=str(exc), model_calls=len(model.events) if model is not None else 0)
    finally:
        # Persist partial API events and the terminal state even on timeout or
        # operator interruption. A missing response remains an explicit failure.
        if model is not None:
            (out / "calls.json").write_text(json.dumps(model.events, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            row["model_calls"] = len(model.events)
        row["elapsed_s"] = round(time.monotonic() - started, 3)
        row["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: row.get(k) for k in ("case_id", "arm", "status", "references", "report_chars", "elapsed_s", "model_calls", "error_type")}, ensure_ascii=False), flush=True)
    return row


def main() -> None:
    root = Path(os.environ.get("SCHOLAR_PILOT_ROOT", "/workspace"))
    manifest_path = root / os.environ.get("SCHOLAR_PILOT_MANIFEST", "evaluation/scholar-controlled-pilot-20261112/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_root = manifest_path.parent / "results"
    for item in manifest["runs"]:
        target = out_root / item["case_id"] / item["arm"] / "result.json"
        if target.exists():
            continue
        run_case(item, item["arm"], root, out_root)


if __name__ == "__main__":
    main()
