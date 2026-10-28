#!/usr/bin/env python3
"""Compare installed, restored and search-only patched retrieval in isolation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(config):
    os.environ.update(config["environment"])
    os.environ["LDR_DATA_DIR"] = "/data"
    package_before = Path(next(iter(importlib.util.find_spec("local_deep_research").submodule_search_locations)))
    guards = [package_before / "advanced_search_system/strategies/langgraph_agent_strategy.py",
              package_before / "web/services/research_service.py",
              package_before / "report_generator.py"]
    before = {str(p.relative_to(package_before)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in guards if p.is_file()}
    if config["variant"] == "patched":
        os.environ["LDR_SEARCH_TOOL"] = "searxng"
        subprocess.run([sys.executable, "/workspace/deployment/install_overlays.py",
                        "--source", "/workspace/local_deep_research", "--manifest",
                        "/workspace/deployment/search-overlay-manifest.json", "--search-only"], check=True)
    from loguru import logger
    logger.remove()
    from types import SimpleNamespace
    from urllib.parse import urlsplit, parse_qs
    import requests
    import local_deep_research
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.web_search_engines.search_engine_factory import create_search_engine
    from local_deep_research.web_search_engines.search_engines_config import list_eligible_engine_configs
    from local_deep_research.utilities.resource_utils import safe_close
    from local_deep_research.web_search_engines import relevance_filter
    judgments = []
    original_batch = relevance_filter._run_batch
    def observe_batch(*args, **kwargs):
        captured = []
        actual = args[0]
        def invoke(prompt, **invoke_kwargs):
            result = actual.invoke(prompt, **invoke_kwargs)
            captured.append(getattr(result, "content", result))
            return result
        observed = SimpleNamespace(base_llm=actual, invoke=invoke)
        try:
            indices = original_batch(observed, *args[1:], **kwargs)
            judgments.append({"indices": indices, "responses": captured})
            return indices
        except Exception as exc:
            from local_deep_research.security.log_sanitizer import scrub_error
            judgments.append({"error_type": type(exc).__name__, "message": scrub_error(exc)})
            raise
    relevance_filter._run_batch = observe_batch
    package = Path(local_deep_research.__file__).parent
    defaults = json.loads((package / "defaults/default_settings.json").read_text())
    snapshot = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in defaults.items()})
    if config["variant"] == "restored":
        snapshot.update(json.loads(Path("/workspace/deployment/search-restoration-profile.json").read_text())["settings"])
    selected = {k: snapshot.get(k) for k in ["search.tool", "search.skip_relevance_filter",
                "search.max_results", "search.max_filtered_results",
                "search.engine.web.pubmed.default_params.optimize_queries"]}
    requests_seen = []
    send = requests.sessions.Session.send
    def observe(self, request, **kwargs):
        url = urlsplit(request.url)
        began = time.monotonic()
        response = send(self, request, **kwargs)
        requests_seen.append({"start": began, "host": url.hostname, "path": url.path,
                              "status": response.status_code,
                              "query": {k: v for k, v in parse_qs(url.query).items()
                                        if k in {"term", "query", "q", "retmax", "pageSize"}}})
        return response
    requests.sessions.Session.send = observe
    rows = []
    model = None
    with settings_context(SimpleNamespace(username=None, get_setting=lambda k, default=None: snapshot.get(k, default))):
        try:
            model = get_llm(model_name="deepseek-v4-flash", provider="openai_endpoint", settings_snapshot=snapshot)
            eligible = sorted(list_eligible_engine_configs(settings_snapshot=snapshot, check_agent_enabled=True))
            cases = [("searxng", '"Visium HD" spatial transcriptomics')]
            if config["variant"] == "patched":
                cases += [
                    ("pubmed", "41107232[PMID]"),
                    ("pubmed", '"Visium HD"[Title/Abstract] AND ("2022/01/01"[Date - Publication] : "2026/10/19"[Date - Publication])'),
                    ("europepmc", "EXT_ID:41107232 AND SRC:MED"),
                    ("europepmc", '"Visium HD" AND FIRST_PDATE:[2022-01-01 TO 2026-10-19]'),
                ]
            for name, query in cases:
                engine = None
                try:
                    engine = create_search_engine(name, llm=model, settings_snapshot=snapshot,
                        programmatic_mode=True, max_results=snapshot["search.max_results"],
                        max_filtered_results=snapshot["search.max_filtered_results"])
                    raw = []
                    original = engine._get_previews
                    def previews(q):
                        result = original(q)
                        raw.extend(result)
                        return result
                    engine._get_previews = previews
                    start = len(requests_seen)
                    judgment_start = len(judgments)
                    result = engine.run(query)
                    rows.append({"engine": name, "query": query, "raw_count": len(raw),
                        "raw_titles": [r.get("title") for r in raw],
                        "returned_count": len(result), "sources": result,
                        "requests": requests_seen[start:], "filter_has_model": engine.llm is not None,
                        "filter_enabled": getattr(engine, "enable_llm_relevance_filter", False),
                        "judgments": judgments[judgment_start:]})
                    print("PROGRESS " + config["variant"] + " " + name + " " + str(len(result)), flush=True)
                except Exception as exc:
                    rows.append({"engine": name, "query": query, "error_type": type(exc).__name__})
                finally:
                    safe_close(engine, "retrieval probe")
            # Hold the exact irrelevant previews constant; only restore the
            # factory's original relevance filtering setting.
            engine = create_search_engine("searxng", llm=model, settings_snapshot=snapshot,
                                          programmatic_mode=True,
                                          max_filtered_results=snapshot["search.max_filtered_results"])
            filter_enabled = bool(getattr(engine, "enable_llm_relevance_filter", False))
            judgment_start = len(judgments)
            frozen = (engine._filter_for_relevance(config["frozen_previews"], config["frozen_query"])
                      if filter_enabled and engine.llm else config["frozen_previews"])
            frozen_judgments = judgments[judgment_start:]
            positive = next((s for row in rows for s in row.get("sources", [])
                             if row["engine"] == "pubmed" and s.get("id") == "41107232"), None)
            mixed_check = None
            if positive:
                mixed = config["frozen_previews"][:4] + [positive] + config["frozen_previews"][4:8]
                mixed_kept = engine._filter_for_relevance(mixed, '"Visium HD" spatial transcriptomics')
                mixed_check = {"input_count": len(mixed), "kept_count": len(mixed_kept),
                               "positive_kept": any(s.get("id") == "41107232" for s in mixed_kept),
                               "irrelevant_kept": sum(s.get("id") != "41107232" for s in mixed_kept)}
            safe_close(engine, "frozen retrieval probe")
            if config["variant"] == "patched":
                from local_deep_research.search_system import AdvancedSearchSystem
                from local_deep_research.config.search_config import get_search
                primary = get_search(search_tool=snapshot["search.tool"], llm_instance=model,
                                     settings_snapshot=snapshot, programmatic_mode=True)
                system = AdvancedSearchSystem(llm=model, search=primary, settings_snapshot=snapshot,
                                              strategy_name="langgraph-agent", programmatic_mode=True)
                tools = [tool.name for tool in system.strategy._build_tools()]
                system.close()
                from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import SearchResultsCollector
                links = []
                collector = SearchResultsCollector(all_links=links)
                shared = [row["sources"][0] for row in rows
                          if row["engine"] in {"pubmed", "europepmc"}
                          and "41107232" in row["query"] and row.get("sources")]
                for record in shared:
                    collector.add_results([dict(record)], engine_name=record["source"])
                deduplication = {"input_records": len(shared), "collected_records": len(links),
                                 "same_doi": len({r["doi"] for r in shared}) == 1,
                                 "same_abstract": len({r["abstract"] for r in shared}) == 1}
            else:
                tools = None
                deduplication = None
            unchanged = {path: hashlib.sha256((package / path).read_bytes()).hexdigest() == digest
                         for path, digest in before.items()}
            result = {"variant": config["variant"], "settings": selected, "eligible_engines": eligible,
                      "cases": rows, "frozen_filter": {"input_count": len(config["frozen_previews"]),
                      "kept_count": len(frozen), "enabled": filter_enabled,
                      "judgments": frozen_judgments}, "mixed_filter": mixed_check, "agent_tools": tools,
                      "cross_engine_identity": deduplication,
                      "unrelated_modules_unchanged": unchanged}
            print("RESULT " + json.dumps(result, ensure_ascii=False, default=str), flush=True)
        finally:
            safe_close(model, "retrieval probe model")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--variant", choices=["installed", "restored", "patched"], default="patched")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(json.load(sys.stdin))
        return
    if not args.output or args.output.exists():
        parser.error("provide a new --output path outside Git")
    info = json.loads(subprocess.check_output(["docker", "inspect", "astro-dra-test-5002-local-deep-research-1"], text=True))[0]
    environment = {k: v for k, v in (x.split("=", 1) for x in info["Config"]["Env"] if "=" in x)
                   if k.startswith("LDR_") or k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}}
    old = json.loads(Path("/data/ningh/nh/ldr-experiments/spatial-20261019-installed/writer-sources.json").read_text())
    config = {"environment": environment, "variant": args.variant,
              "frozen_previews": [{k: x[k] for k in ["title", "link", "snippet"]} for x in old[:10]],
              "frozen_query": "10x Genomics Visium spatial transcriptomics 2023 Nature impact factor analysis methods"}
    command = ["docker", "run", "--rm", "-i", "--network", "container:astro-dra-test-5002-local-deep-research-1",
               "--tmpfs", "/data:rw,size=256m", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-v", str(ROOT) + ":/workspace:ro", "--entrypoint", "/install/.venv/bin/python",
               info["Image"], "-u", "/workspace/scripts/check_search_recovery.py", "--worker"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    process.stdin.write(json.dumps(config))
    process.stdin.close()
    found = None
    for line in process.stdout:
        if line.startswith("PROGRESS "):
            print(line.rstrip(), flush=True)
        elif line.startswith("RESULT "):
            found = json.loads(line[7:])
    return_code = process.wait()
    if found is None:
        raise RuntimeError("Probe ended without structured result (exit " + str(return_code) + ")")
    found["image_id"] = info["Image"]
    os.umask(0o077)
    args.output.write_text(json.dumps(found, ensure_ascii=False, indent=2))
    print("Saved " + str(args.output), flush=True)
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
