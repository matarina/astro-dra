#!/usr/bin/env python3
"""Run the installed/default LDR research pipeline in a disposable traced container.

Artifact directories must be private and outside Git. Instrumentation records
source delivery and final writing, without changing tool decisions or prompts.
"""
import argparse
from contextvars import ContextVar
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def worker(config):
    os.umask(0o077)
    os.environ.update(config["environment"])
    os.environ["LDR_DATA_DIR"] = "/data"
    out = Path("/trace")
    started = time.monotonic()
    lock = threading.RLock()
    counts = {}
    stage = ContextVar("diagnostic_stage", default="agent")
    secrets = [v for k, v in config["environment"].items()
               if any(part in k.lower() for part in ("api_key", "secret", "password", "token")) and len(v) >= 6]

    def redact(value):
        text = str(value)
        for secret in secrets:
            text = text.replace(secret, "<redacted>")
        return re.sub(r"(?i)(bearer\s+|api_key=|apikey=|token=)[^\s&\"']+", r"\1<redacted>", text)

    def write_json(name, value, compressed=False):
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = redact(json.dumps(value, ensure_ascii=False, default=str))
        if compressed:
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content + "\n")
        return name

    def event(kind, **values):
        with lock:
            counts[kind] = counts.get(kind, 0) + 1
            row = {"at": datetime.now(timezone.utc).isoformat(),
                   "elapsed_s": round(time.monotonic() - started, 3),
                   "kind": kind, "thread": threading.current_thread().name, **values}
            with (out / "events.jsonl").open("a") as f:
                f.write(redact(json.dumps(row, ensure_ascii=False, default=str)) + "\n")
            write_json("status.json", {"state": "running", "elapsed_s": row["elapsed_s"],
                                      "counts": counts, "last_event": row})
            return counts[kind]

    def artifact(kind, value):
        with lock:
            count = counts.get("artifact", 0) + 1
            counts["artifact"] = count
        return write_json(f"artifacts/{count:04d}-{kind}.json.gz", value, compressed=True)

    from loguru import logger
    logger.remove()
    logger.add(lambda m: event("warning", message=redact(m.record["message"])[:1200]), level="WARNING")

    if config["variant"] in {"patched", "search-only", "collection-only"}:
        manifest = "search-overlay-manifest.json" if config["variant"] != "patched" else "overlay-manifest.json"
        command = [sys.executable, "/workspace/deployment/install_overlays.py",
                   "--source", "/workspace/local_deep_research", "--manifest",
                   "/workspace/deployment/" + manifest]
        if config["variant"] == "search-only":
            command.append("--search-only")
        elif config["variant"] == "collection-only":
            command.append("--collection-only")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

    import local_deep_research
    from langchain_openai import ChatOpenAI
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.search_config import get_search
    from local_deep_research.search_system import AdvancedSearchSystem
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import SearchResultsCollector, LangGraphAgentStrategy
    from local_deep_research.web_search_engines.search_engine_base import BaseSearchEngine
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.utilities.json_utils import get_llm_response_text
    from research_verify.citation_qc import CitationQc
    import research_verify.publication as publication_module
    import importlib
    fetch_module = importlib.import_module("local_deep_research.advanced_search_system.tools.fetch")

    # Only allowlisted public search parameters and response headers are saved.
    # Never record credentials, request headers or model API transport bodies.
    import requests
    from urllib.parse import parse_qs, urlsplit
    original_send = requests.sessions.Session.send
    def send(self, request, **kwargs):
        began = time.monotonic()
        target = urlsplit(request.url)
        try:
            response = original_send(self, request, **kwargs)
            parameters = {k: v for k, v in parse_qs(target.query).items()
                          if k in {"q", "pq", "term", "query", "db", "id", "retmode", "sort", "format", "retmax", "pageSize", "resultType"}}
            response_artifact = None
            if target.path.endswith("efetch.fcgi") and target.hostname == "eutils.ncbi.nlm.nih.gov":
                response_artifact = artifact("pubmed-raw-response", {
                    "parameters": parameters, "status": response.status_code, "body": response.text})
            elif target.path.endswith("/europepmc/webservices/rest/search"):
                response_artifact = artifact("europepmc-raw-response", {
                    "parameters": parameters, "status": response.status_code, "body": response.text})
            elif target.path.rstrip("/") == "/search" and parameters.get("format") == ["json"]:
                response_artifact = artifact("web-search-raw-response", {
                    "parameters": parameters, "status": response.status_code, "body": response.text})
            event("http", host=target.hostname, path=target.path, status=response.status_code,
                  seconds=round(time.monotonic() - began, 3), parameters=parameters,
                  response_headers={k: v for k, v in response.headers.items()
                                    if k.lower() in {"age", "date", "via", "x-cache", "cache-control", "content-type"}},
                  artifact=response_artifact)
            return response
        except Exception as exc:
            event("http_error", host=target.hostname, path=target.path, error=type(exc).__name__)
            raise
    requests.sessions.Session.send = send

    original_generate = ChatOpenAI._generate
    def generate(self, messages, *args, **kwargs):
        began = time.monotonic()
        text = "\n".join(str(m.content) for m in messages)
        kind = stage.get()
        if "Select source IDs for writing a research answer." in text:
            kind = "source_context_selection"
        elif "Analyze these sources for factual consistency:" in text:
            kind = "native_fact_check"
        if kind == "agent":
            if "Transform this natural language question into an optimized PubMed" in text:
                kind = "pubmed_query_optimizer"
            elif "relevance-filtering step" in text:
                kind = "relevance_filter"
            elif "focus" in text.lower() and len(messages) <= 2 and "research assistant writing a research report" not in text:
                kind = "focused_extraction_or_helper"
        payload = None
        if kind != "agent":
            payload = artifact("model-input-" + kind, {"messages": [{"type": m.type, "content": m.content} for m in messages]})
        event("model_start", phase=kind, input_chars=len(text), input_sha256=sha256(text.encode()).hexdigest(), artifact=payload)
        try:
            result = original_generate(self, messages, *args, **kwargs)
            message = result.generations[0].message
            content = get_llm_response_text(message)
            tool_calls = getattr(message, "tool_calls", [])
            response_path = artifact("model-output-" + kind, {"content": content}) if kind != "agent" else None
            info = result.generations[0].generation_info or {}
            event("model_end", phase=kind, seconds=round(time.monotonic() - began, 3),
                  output_chars=len(content), finish_reason=info.get("finish_reason"),
                  tool_calls=[{"name": c.get("name"), "args": c.get("args")} for c in tool_calls],
                  artifact=response_path)
            return result
        except Exception as exc:
            event("model_error", phase=kind, error=type(exc).__name__, message=redact(exc)[:600])
            raise
    ChatOpenAI._generate = generate

    original_run = BaseSearchEngine.run
    def search_run(self, query, *args, **kwargs):
        name = getattr(self, "_engine_name", None) or type(self).__name__
        event("search_start", engine=name, query=query)
        result = original_run(self, query, *args, **kwargs)
        path = artifact("search-results", {"engine": name, "query": query, "results": result})
        event("search_end", engine=name, count=len(result or []), artifact=path)
        return result
    BaseSearchEngine.run = search_run

    original_filter = BaseSearchEngine._filter_for_relevance
    def filter_results(self, previews, query):
        name = getattr(self, "_engine_name", None) or type(self).__name__
        path = artifact("relevance-input", {"engine": name, "query": query, "results": previews})
        result = original_filter(self, previews, query)
        event("relevance_end", engine=name, before=len(previews), after=len(result),
              input_artifact=path, output_artifact=artifact("relevance-output", result))
        return result
    BaseSearchEngine._filter_for_relevance = filter_results

    original_add = SearchResultsCollector.add_results
    def add(self, results, *args, **kwargs):
        path = artifact("collector-input", results)
        before = len(results)
        pool_before = len(self.results)
        result = original_add(self, results, *args, **kwargs)
        event("collector_add", before=before, after=len(results), indices=[r.get("index") for r in results],
              pool_before=pool_before, pool_after=len(self.results),
              added=getattr(result, "added", None), reused=getattr(result, "reused", None),
              unregistered=len(getattr(result, "unregistered", [])),
              input_artifact=path, output_artifact=artifact("collector-output", results))
        return result
    SearchResultsCollector.add_results = add
    original_find = SearchResultsCollector.find_or_add_result
    def find(self, source, *args, **kwargs):
        path = artifact("fetch-registration", source)
        result = original_find(self, source, *args, **kwargs)
        event("fetch_registration", index=result, input_artifact=path,
              stored_artifact=artifact("fetch-stored-source", self.find_by_index(result)))
        return result
    SearchResultsCollector.find_or_add_result = find

    original_fetch = fetch_module._fetch_raw_content
    def fetch(*args, **kwargs):
        result = original_fetch(*args, **kwargs)
        path = artifact("page-fetch", {"requested_url": args[0], "result": result})
        event("page_fetch", url=args[0], artifact=path,
              chars=len((result[0] or {}).get("content") or ""), status=(result[0] or {}).get("status"))
        return result
    fetch_module._fetch_raw_content = fetch

    original_write = StandardCitationHandler.analyze_followup
    def write(self, question, sources, previous_knowledge, nr_of_links):
        path = artifact("writer-input", {"question": question, "sources": sources,
                        "previous_knowledge": previous_knowledge, "nr_of_links": nr_of_links})
        token = stage.set("final_writer")
        event("writer_start", artifact=path, sources=len(sources), draft_chars=len(previous_knowledge))
        try:
            result = original_write(self, question, sources, previous_knowledge, nr_of_links)
            event("writer_end", artifact=artifact("writer-output", result.get("content", "")))
            return result
        finally:
            stage.reset(token)
    StandardCitationHandler.analyze_followup = write

    original_finalize = LangGraphAgentStrategy._finalize
    def finalize(self, query, answer, *args, **kwargs):
        event("agent_draft", artifact=artifact("agent-draft", {"query": query, "draft": answer,
              "current_sources": self.collector.results, "all_sources": self.all_links_of_system}))
        return original_finalize(self, query, answer, *args, **kwargs)
    LangGraphAgentStrategy._finalize = finalize

    original_fallback = LangGraphAgentStrategy._synthesize_from_collector
    def fallback(self, query):
        event("fallback_start", source_count=len(self.collector.results),
              artifact=artifact("fallback-sources", self.collector.results))
        token = stage.set("fallback_writer")
        try:
            result = original_fallback(self, query)
            event("fallback_end", artifact=artifact("fallback-output", result))
            return result
        finally:
            stage.reset(token)
    LangGraphAgentStrategy._synthesize_from_collector = fallback

    original_judge = CitationQc._judge_claim
    def judge(self, claim, fragments):
        token = stage.set("citation_audit")
        try:
            return original_judge(self, claim, fragments)
        finally:
            stage.reset(token)
    CitationQc._judge_claim = judge

    package = Path(local_deep_research.__file__).parent
    defaults = json.loads((package / "defaults/default_settings.json").read_text())
    snapshot = {k: v.get("value") for k, v in defaults.items()}
    snapshot = apply_environment_overrides_to_snapshot(snapshot)
    snapshot["llm.model"] = config["model"]
    provider = "openai_endpoint"
    snapshot["llm.provider"] = provider
    selected = {k: snapshot.get(k) for k in ["llm.model", "llm.provider", "llm.temperature", "llm.max_tokens",
        "search.tool", "search.search_strategy", "search.iterations", "search.questions_per_iteration",
        "search.max_results", "search.max_filtered_results", "search.snippets_only", "search.fetch.mode",
        "search.skip_relevance_filter", "langgraph_agent.max_unique_sources", "rate_limiting.enabled", "rate_limiting.profile",
        "langgraph_agent.max_iterations", "langgraph_agent.max_sub_iterations", "langgraph_agent.max_subagent_workers",
        "search.engine.web.pubmed.default_params.get_full_text", "policy.egress_scope"]}
    selected.update({k: snapshot.get(k) for k in [
        "general.enable_fact_checking",
        "search.engine.web.pubmed.default_params.optimize_queries",
        "search.engine.web.pubmed.default_params.enable_llm_relevance_filter",
        "search.engine.web.searxng.default_params.enable_llm_relevance_filter",
        "search.engine.web.europepmc.default_params.enable_llm_relevance_filter"]})
    write_json("manifest.json", {"variant": config["variant"], "mode": config["mode"], "settings": selected,
        "base_image_id": config["image_id"], "query": config["query"],
        "scope": "Actual installed/default research strategy and publication/storage/export; programmatic mode skips web authentication, per-user settings and DB metrics. Monitoring does not change prompts or search decisions.",
        "module_sha256": {str(p.relative_to(package)): sha256(p.read_bytes()).hexdigest() for p in [
            package / "advanced_search_system/strategies/langgraph_agent_strategy.py",
            package / "citation_handlers/standard_citation_handler.py", package / "citation_handlers/base_citation_handler.py",
            package / "advanced_search_system/tools/fetch/__init__.py", package / "web_search_engines/engines/search_engine_pubmed.py"]}})
    extra_modules = ["web_search_engines/relevance_filter.py", "web_search_engines/search_engines_config.py",
                     "web_search_engines/engine_registry.py", "security/module_whitelist.py",
                     "web_search_engines/engines/search_engine_europepmc.py"]
    module_info = {}
    for relative in extra_modules:
        path = package / relative
        if path.is_file():
            module_info[relative] = sha256(path.read_bytes()).hexdigest()
    write_json("retrieval-modules.json", module_info)
    last_print = [0.0]
    def progress(message, percent, metadata):
        phase = metadata.get("phase")
        if phase in {"termination_check", "agent_reasoning"}:
            return
        event("progress", message=message, percent=percent, phase=phase)
        if time.monotonic() - last_print[0] > 8 or phase in {"complete", "synthesis"}:
            print("PROGRESS " + redact(message)[:220], flush=True)
            last_print[0] = time.monotonic()

    model = None
    system = None
    try:
        settings = SimpleNamespace(username=None, get_setting=lambda key, default=None: snapshot.get(key, default))
        with settings_context(settings):
            model = get_llm(model_name=config["model"], provider=provider, settings_snapshot=snapshot)
            search = get_search(search_tool=snapshot["search.tool"], llm_instance=model,
                                settings_snapshot=snapshot, programmatic_mode=True)
            system = AdvancedSearchSystem(llm=model, search=search, strategy_name=snapshot["search.search_strategy"],
                max_iterations=snapshot["search.iterations"], questions_per_iteration=snapshot["search.questions_per_iteration"],
                settings_snapshot=snapshot, programmatic_mode=True)
            system.set_progress_callback(progress)
            event("research_start", strategy=type(system.strategy).__name__, effective_iterations=system.strategy.max_iterations,
                  max_unique_sources=getattr(system.strategy, "max_unique_sources", None))
            result = system.analyze_topic(config["query"])
            from local_deep_research.web.services.research_service import _extract_synthesized_answer, export_report_to_memory
            if config["mode"] == "detailed":
                from local_deep_research.report_generator import IntegratedReportGenerator
                generated = IntegratedReportGenerator(search_system=system, settings_snapshot=snapshot).generate_report(
                    result, config["query"], progress_callback=progress)
                publication = publication_module.publication_for_report(generated["content"], generated.get("metadata"),
                    publication_module.collect_publication_sources(system, system.all_links_of_system), model)
            else:
                draft = _extract_synthesized_answer(result) or result.get("formatted_findings") or ""
                publication = publication_module.publish_report(draft,
                    publication_module.collect_publication_sources(system, system.all_links_of_system), model)
            publication_module.validate_publication(publication.content, publication.metadata())
            artifact("all-final-sources", system.all_links_of_system)
            artifact("publication", publication.model_dump(mode="json"))
            (out / "report-body.md").write_text(publication.content)
            event("publication_end", source_count=len(publication.sources), warnings=publication.warnings,
                  audit_status=publication.audit_status, audited_claims=len(publication.citation_audit))

            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            from local_deep_research.database.models import ResearchHistory
            from local_deep_research.database.models.base import Base
            from local_deep_research.storage.database import DatabaseReportStorage
            from local_deep_research.web.services.report_assembly_service import assemble_full_report
            engine = create_engine("sqlite:////trace/research.sqlite")
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                row = ResearchHistory(id="diagnostic-run", query=config["query"], mode=config["mode"], status="completed",
                    created_at=datetime.now(timezone.utc).isoformat(), research_meta={})
                session.add(row)
                session.commit()
                assert DatabaseReportStorage(session).save_report(row.id, publication.content, publication.metadata())
                session.expire_all()
                row = session.query(ResearchHistory).filter_by(id="diagnostic-run").one()
                assert row.report_content == publication.content
                assembled = assemble_full_report(row, session)
                (out / "report.md").write_text(assembled)
                exports = {}
                for fmt in ("pdf", "ris"):
                    try:
                        data, name, mime = export_report_to_memory(assembled, fmt)
                        (out / ("report." + fmt)).write_bytes(data)
                        exports[fmt] = {"bytes": len(data), "mime": mime}
                    except Exception as exc:
                        exports[fmt] = {"error": type(exc).__name__}
            summary = {"state": "complete", "variant": config["variant"], "mode": config["mode"],
                "elapsed_s": round(time.monotonic() - started, 3), "model": config["model"],
                "strategy": snapshot["search.search_strategy"], "research_error": result.get("error"),
                "report_chars": len(publication.content), "sources_collected": len(system.all_links_of_system),
                "sources_cited": len(publication.sources), "audit_status": publication.audit_status,
                "audited_claims": len(publication.citation_audit), "warnings": publication.warnings,
                "exports": exports, "counts": dict(counts)}
            write_json("summary.json", summary)
            write_json("status.json", summary)
            print("RESULT " + json.dumps(summary, ensure_ascii=False), flush=True)
    except Exception as exc:
        import traceback
        failure = {"state": "failed", "error": type(exc).__name__, "message": redact(exc)[:1200],
            "frames": [{"file": Path(f.filename).name, "line": f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-8:]],
            "counts": dict(counts)}
        write_json("summary.json", failure)
        write_json("status.json", failure)
        print("FAILURE " + json.dumps(failure, ensure_ascii=False), flush=True)
        raise SystemExit(1)
    finally:
        if system is not None:
            system.close()
        if model is not None:
            from local_deep_research.utilities.resource_utils import safe_close
            safe_close(model, "diagnostic model")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--query-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--container", default="astro-dra-test-5002-local-deep-research-1")
    parser.add_argument("--variant", choices=["installed", "patched", "search-only", "collection-only"], default="installed")
    parser.add_argument("--mode", choices=["quick", "detailed"], default="quick")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--image", help="Test a candidate image without replacing the web container")
    parser.add_argument("--max-unique-sources", type=int, choices=range(10, 501), metavar="10..500")
    args = parser.parse_args()
    if args.worker:
        worker(json.load(sys.stdin))
        return
    if not args.output or args.output.exists() or not args.query_file:
        parser.error("provide --query-file and a new --output directory")
    args.output.mkdir(parents=True, mode=0o700)
    info = json.loads(subprocess.check_output(["docker", "inspect", args.container], text=True))[0]
    if args.image:
        info["Image"] = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", args.image], text=True).strip()
    environment = {k: v for k, v in (item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
                   if k.startswith("LDR_") or k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}}
    if args.max_unique_sources is not None:
        environment["LDR_LANGGRAPH_AGENT_MAX_UNIQUE_SOURCES"] = str(args.max_unique_sources)
    config = {"environment": environment, "model": args.model, "mode": args.mode, "variant": args.variant,
              "query": args.query_file.read_text(), "image_id": info["Image"]}
    command = ["docker", "run", "--rm", "-i", "--network", "container:" + args.container,
               "--tmpfs", "/data:rw,size=512m", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-v", str(ROOT) + ":/workspace:ro", "-v", str(args.output.resolve()) + ":/trace",
               "--entrypoint", "/install/.venv/bin/python", info["Image"], "-u",
               "/workspace/scripts/trace_research_run.py", "--worker"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    process.stdin.write(json.dumps(config))
    process.stdin.close()
    for line in process.stdout:
        if line.startswith(("PROGRESS ", "RESULT ", "FAILURE ")):
            print(line.strip(), flush=True)
    return_code = process.wait()
    # The application image can run as root. Keep private diagnostic artifacts
    # readable by the invoking workspace user after either success or failure.
    ownership_code = (
        "import os; uid=int(os.environ['ARTIFACT_UID']); gid=int(os.environ['ARTIFACT_GID']); "
        "[(os.chown(root,uid,gid,follow_symlinks=False), "
        "[os.chown(os.path.join(root,n),uid,gid,follow_symlinks=False) for n in files]) "
        "for root,dirs,files in os.walk('/trace')]"
    )
    subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--user", "0:0",
        "-e", "ARTIFACT_UID=" + str(os.getuid()), "-e", "ARTIFACT_GID=" + str(os.getgid()),
        "-v", str(args.output.resolve()) + ":/trace", "--entrypoint", "/install/.venv/bin/python",
        info["Image"], "-c", ownership_code,
    ], check=True)
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
