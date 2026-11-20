#!/usr/bin/env python3
"""Diagnose zero-source feedback reproductions without a model call.

The reproduction runner stores provider I/O, progress, and a final summary, but
the search adapters historically collapsed transport errors into ``[]``.  This
tool makes that distinction visible from an existing run and, optionally,
probes the same disposable Docker network with and without the inherited proxy.
It never starts or restarts a production container.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def assistant_tool_calls(value, counts: Counter[str]) -> None:
    if isinstance(value, dict):
        if value.get("role") == "assistant":
            for call in value.get("tool_calls") or []:
                name = (call.get("function") or {}).get("name")
                if name:
                    counts[name] += 1
        for item in value.values():
            assistant_tool_calls(item, counts)
    elif isinstance(value, list):
        for item in value:
            assistant_tool_calls(item, counts)


def inspect_cases(root: Path) -> list[dict]:
    rows = []
    for case in sorted(root.glob("*-task-*")):
        summary_path = case / "results" / "summary.json"
        if not summary_path.is_file():
            continue
        summary = load(summary_path)
        counts: Counter[str] = Counter()
        responses = 0
        for response_path in sorted(case.glob("provider-io/*/response.json")):
            responses += 1
            try:
                assistant_tool_calls(load(response_path), counts)
            except (OSError, json.JSONDecodeError):
                continue
        rows.append(
            {
                "case": case.name,
                "summary": summary,
                "provider_response_files": responses,
                "actual_assistant_tool_calls": dict(counts),
                "source_file_sha256": sha256(case / "results" / "sources.json"),
                "progress_file_sha256": sha256(case / "results" / "progress.jsonl"),
            }
        )
    return rows


def docker_json(args: list[str]):
    try:
        return json.loads(subprocess.check_output(args, text=True))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def probe_network(image: str, network: str, extra_host: str, env: dict[str, str]):
    code = r'''
import json, os, urllib.request
urls = {
  "searxng": "http://host.docker.internal:8888/search?q=cancer&format=json",
  "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=cancer&retmode=json",
  "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=cancer&format=json",
}
out = {"proxy_present": bool(os.environ.get("HTTP_PROXY"))}
for name, url in urls.items():
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            body = response.read(200000)
            row = {"status": response.status, "bytes": len(body)}
            if name == "searxng":
                payload = json.loads(body.decode("utf-8"))
                row["result_count"] = len(payload.get("results") or [])
                row["unresponsive_engines"] = len(payload.get("unresponsive_engines") or [])
            elif name == "pubmed":
                payload = json.loads(body.decode("utf-8"))
                row["hit_count"] = int(payload.get("esearchresult", {}).get("count", 0))
            else:
                payload = json.loads(body.decode("utf-8"))
                row["hit_count"] = int(payload.get("hitCount", 0))
            out[name] = row
    except Exception as exc:
        out[name] = {"error_type": type(exc).__name__, "error": str(exc)[:240]}
print(json.dumps(out, ensure_ascii=False))
'''

    def run(extra_env: dict[str, str]):
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--add-host",
            extra_host,
            "--entrypoint",
            "/install/.venv/bin/python",
        ]
        for key, value in extra_env.items():
            command += ["-e", f"{key}={value}"]
        command += [image, "-c", code]
        try:
            raw = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)
            return json.loads(raw.strip().splitlines()[-1])
        except Exception as exc:
            return {"error_type": type(exc).__name__, "error": str(exc)[:240]}

    proxy_env = {
        key: value
        for key, value in env.items()
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    direct_env = {key: "" for key in proxy_env if key.lower() != "no_proxy"}
    direct_env["NO_PROXY"] = ""
    return {"inherited_proxy": run(proxy_env), "direct": run(direct_env)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-network", action="store_true")
    args = parser.parse_args()
    root = args.run.resolve()
    cases = inspect_cases(root)
    summaries = [row["summary"] for row in cases]
    output = {
        "schema_version": "feedback-zero-source-diagnosis.v1",
        "generated_unix": time.time(),
        "run": str(root),
        "cases": cases,
        "all_source_pools_zero": bool(cases) and all(item.get("source_pool") == 0 for item in summaries),
        "all_reference_counts_zero": bool(cases) and all(item.get("references") == 0 for item in summaries),
        "interpretation": {
            "primary": "retrieval infrastructure returned no usable records; this is not evidence that journal screening rejected all papers",
            "journal_metric": "The journal tool can only screen an identified candidate; zero source_pool means no paper-level screening occurred",
            "failure_mode": "search adapter messages report empty results while transport failures are collapsed to empty lists",
        },
    }
    if args.probe_network:
        ref = docker_json(["docker", "inspect", "local_deep_research-local-deep-research-1"])
        if ref:
            ref = ref[0]
            env = dict(item.split("=", 1) for item in ref.get("Config", {}).get("Env", []) if "=" in item)
            image = ref.get("Config", {}).get("Image")
            network = load(root / "03-tumor-20-task-6ac5d65ed736" / "launch.json").get("network")
            extra_hosts = ref.get("HostConfig", {}).get("ExtraHosts") or []
            host_entry = next((item for item in extra_hosts if item.startswith("host.docker.internal:")), "host.docker.internal:host-gateway")
            output["network_probe"] = probe_network(image, network, host_entry, env)
        output["docker_network_containers_now"] = docker_json(["docker", "network", "inspect", "local_deep_research_ldr-network"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(cases), "all_source_pools_zero": output["all_source_pools_zero"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
