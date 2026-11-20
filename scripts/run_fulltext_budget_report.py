"""Full-text budget comparison using real finalization and native synthesis.

No agent search, production writes, save-time audits or supplementary evidence.
The common adapters replace external evidence fetching and UI formatting only.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace


def main():
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
    import local_deep_research

    class FrozenEvidence:
        def record(self, *args, **kwargs): return None
        def pmc_identifiers(self, *args, **kwargs): return {}
        def article(self, *args, **kwargs): return ""
        def web(self, *args, **kwargs): return []

    original_init = source_evidence.ArticleEvidenceClient.__init__
    def frozen_init(self, *args, **kwargs):
        kwargs["fetcher"] = FrozenEvidence()
        original_init(self, *args, **kwargs)
    source_evidence.ArticleEvidenceClient.__init__ = frozen_init
    root = Path("/experiment")
    cfg = json.loads((root / "experiment.json").read_text())
    caseid = os.environ["PILOT_CASE_ID"]
    case = next(x for x in cfg["cases"] if x["case_id"] == caseid)
    arm = os.environ["PILOT_ARM"]
    out = root / arm
    out.mkdir(exist_ok=True)
    os.environ["LDR_DATA_DIR"] = str(out / "data" / caseid)
    os.environ["LDR_RESEARCH_TRACE_ENABLED"] = "true"
    os.environ["LDR_RESEARCH_TRACE_DIR"] = str(out / "traces")
    os.environ["LDR_VERIFY_ENABLE_DOI_VALIDATION"] = "false"
    os.environ["LDR_VERIFY_ENABLE_CITATION_QC"] = "false"
    defaults = Path(local_deep_research.__file__).parent / "defaults/default_settings.json"
    snapshot = apply_environment_overrides_to_snapshot({k:v.get("value") for k,v in json.loads(defaults.read_text()).items()})
    snapshot.update(cfg["settings"])
    snapshot.update({"report." + k:v for k,v in case["report_settings"].items()})
    public = {k:snapshot.get(k) for k in cfg["record_setting_keys"]}
    public["report_settings"] = case["report_settings"]
    source_path = root / case["source_pack"]
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != case["source_pack_sha256"]:
        raise ValueError("Source bytes changed")
    sources = json.loads(source_path.read_text())
    events = []
    class CountingModel:
        def __init__(self, model): self.model = model
        def __getattr__(self, name): return getattr(self.model, name)
        def invoke(self, prompt, *args, **kwargs):
            event = {"prompt":str(prompt), "started_unix":time.time()}
            events.append(event)
            begin = time.monotonic()
            try:
                response = self.model.invoke(prompt, *args, **kwargs)
                event.update(response=getattr(response, "content", str(response)),
                             usage=getattr(response, "usage_metadata", None), status="completed")
                return response
            except Exception as exc:
                event.update(status="error", error_type=type(exc).__name__)
                raise
            finally:
                event["latency_seconds"] = time.monotonic() - begin
    started = time.monotonic()
    row = {**case, "system":arm, "model":snapshot["llm.model"], "temperature":snapshot.get("llm.temperature"),
           "settings_sha256":hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest(),
           "source_pack_sha256":case["source_pack_sha256"], "settings":public}
    with settings_context(SimpleNamespace(username=None, get_setting=lambda k,d=None:snapshot.get(k,d))):
        try:
            model = CountingModel(get_llm(settings_snapshot=snapshot))
            strategy = LangGraphAgentStrategy.__new__(LangGraphAgentStrategy)
            strategy.model = model
            strategy.settings_snapshot = snapshot
            strategy.get_setting = lambda k,d=None:snapshot.get(k,d)
            strategy.collector = SearchResultsCollector()
            strategy.collector._results = copy.deepcopy(sources)
            strategy.collector._sources = [s["link"] for s in sources]
            strategy.all_links_of_system = []
            strategy._update_progress = lambda *args, **kwargs:None
            strategy._build_egress_context = lambda:None
            strategy._format_citations = lambda body, records:body
            strategy.citation_handler = CitationHandler(model, handler_type="standard", settings_snapshot=snapshot)
            handler = getattr(strategy.citation_handler, "_handler", strategy.citation_handler)
            handler.evidence_fetcher = FrozenEvidence()
            with trace_context("fulltext-budget-" + arm + "-" + caseid):
                result = strategy._finalize(case["query"], "", 0, 0, [])
                body = result["current_knowledge"]
                if not body.strip(): raise ValueError("No generated report")
                pub = publish_report(body, result["search_results"], cfg=VerifyConfig(enable_citation_qc=False))
            actual = result["search_results"]
            preserved = len(actual) == len(sources) and all(
                all(a.get(key) == value for key, value in b.items())
                for a,b in zip(actual,sources))
            row.update(status="completed", body=body, final_report=result["final_report"],
                       sources=actual, publication=pub.metadata(), sources_preserved=preserved)
        except Exception as exc:
            row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    row.update(latency_seconds=time.monotonic()-started, model_calls=len(events), claims=[], assessment_status="not_annotated")
    (out / (caseid + ".calls.json")).write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str))
    (out / (caseid + ".json")).write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({k:row.get(k) for k in ("case_id","system","status","error_type","error","latency_seconds","model_calls","sources_preserved")}), flush=True)


if __name__ == "__main__": main()
