#!/usr/bin/env python3
"""Run existing CitationQc with a real configured model on controlled synthetic cases.

No production research task, service mutation, fake model or implicit optimization.
Only explicitly supplied synthetic text is sent to the endpoint.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import httpx
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_deep_research"))
from research_verify.citation_qc import CitationQc
from research_verify.config import VerifyConfig


class RealJudge:
    def __init__(self, endpoint, key, model, timeout):
        self.endpoint, self.key, self.model = endpoint, key, model
        self.timeout = timeout
        self.calls = []
        self.errors = []

    def invoke(self, prompt):
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                response = client.post(
                    self.endpoint + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.key},
                    json={"model": self.model, "temperature": 0, "max_tokens": 2048,
                          "messages": [{"role": "user", "content": prompt}]},
                )
            if not response.is_success:
                self.errors.append("model_http_" + str(response.status_code))
                raise RuntimeError(self.errors[-1])
            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            self.calls.append({"elapsed_s": round(time.monotonic()-started, 3),
                               "finish_reason": data["choices"][0].get("finish_reason"),
                               "usage": data.get("usage"), "response_model": data.get("model"), "response_content": content})
            return SimpleNamespace(content=content)
        except httpx.HTTPError:
            self.errors.append("model_transport_error")
            raise RuntimeError("model_transport_error") from None


class Collector:
    def __init__(self, case):
        if case.get("_source_records"):
            self.sources=case["_source_records"]
            return
        self.sources = {
            int(index): {"index": index, "paper_id": f"synthetic:{case['id']}:{index}",
                         "full_content": text, "content_type": "full_text"}
            for index, text in case["sources"].items()
        }

    def find_by_index(self, index):
        return self.sources.get(index)


def prepare_verified_excerpts(fixture):
    """Verify DOI and short excerpts against PubMed before sending them to a model."""
    papers = fixture.get("papers", {})
    if not papers or any(not str(pmid).isdigit() for pmid in papers):
        raise ValueError("verified fixtures require numeric PubMed IDs")
    with httpx.Client(timeout=20, trust_env=False) as client:
        r = client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                       params={"db":"pubmed","id":",".join(papers),"retmode":"xml"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    actual = {node.findtext(".//PMID"):node for node in root.findall("PubmedArticle")}
    verified = {}
    for pmid, record in papers.items():
        node = actual[pmid]
        doi = next((n.text for n in node.findall(".//ArticleId") if n.get("IdType")=="doi"),None)
        abstract = " ".join("".join(n.itertext()) for n in node.findall(".//AbstractText"))
        if doi.casefold()!=record["doi"].casefold():
            raise ValueError("DOI mismatch in real fixture")
        if sum(len(s["text"].split()) for s in record["segments"])>25:
            raise ValueError("real fixture exceeds short-excerpt budget")
        parts = []
        for segment in record["segments"]:
            if abstract[segment["abstract_start"]:segment["abstract_end"]]!=segment["text"]:
                raise ValueError("source excerpt no longer matches PubMed")
            parts.append(segment["text"])
        verified[pmid]={"pmid":pmid,"doi":doi,"link":record["source_url"],
                        "full_content":"\n\n".join(parts),"content_type":"abstract"}
    cases = []
    for case in fixture["cases"]:
        copy = dict(case)
        copy["_source_records"]={int(index):{"index":index,**verified[pmid]}
                                 for index,pmid in case["source_ids"].items()}
        cases.append(copy)
    return cases


def redact_real_result(value):
    """Keep unique short excerpts in the fixture; results retain hashes and coordinates."""
    sensitive = {"quote","reason","model_reason","response_content","claim","supporting_fragment"}
    if isinstance(value,list):
        return [redact_real_result(v) for v in value]
    if isinstance(value,dict):
        return {(k+"_sha256" if k in sensitive and isinstance(v,str) else k):
                (sha256(v.encode()).hexdigest() if k in sensitive and isinstance(v,str)
                 else redact_real_result(v)) for k,v in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="local_deep_research-local-deep-research-1")
    parser.add_argument("--cases", type=Path, default=ROOT/"local_deep_research/tests/fixtures/semantic_pilot_cases.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--allow-verified-excerpts", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        parser.error("workers must be 1 or 2")
    if args.output.exists():
        parser.error("output already exists; use a new path for each run")
    fixture = json.loads(args.cases.read_text())
    if fixture.get("synthetic") is not True and not args.allow_verified_excerpts:
        parser.error("real excerpts require explicit verification mode")
    cases = fixture["cases"] if fixture.get("synthetic") is True else prepare_verified_excerpts(fixture)
    info = json.loads(subprocess.check_output(["docker","inspect",args.container],text=True))[0]
    env = dict(item.split("=",1) for item in info["Config"].get("Env",[]) if "=" in item)
    endpoint = env.get("LDR_LLM_OPENAI_ENDPOINT_URL","").rstrip("/")
    model = env.get("LDR_LLM_MODEL","")
    key = env.get("LDR_LLM_OPENAI_ENDPOINT_API_KEY") or "EMPTY"
    if not endpoint or not model or "your-provider.example" in endpoint:
        parser.error("container has no usable configured model")
    code = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    logger.remove()  # Do not emit model/provider exception payloads to the console.
    cfg = VerifyConfig()
    started = time.monotonic()

    def evaluate(case):
        judge = RealJudge(endpoint,key,model,args.timeout)
        qc = CitationQc(judge_model=judge,cfg=cfg)
        claims = qc.extract_claims(case["claim"])
        checks = qc.check(claims,Collector(case))
        verdict = checks[0].verdict if len(checks)==1 else "extraction_mismatch"
        expected = case["expected"]
        row = {"id":case["id"],"category":case["category"],"expected":expected,
               "actual":verdict,"exact_match":expected==verdict,
               "negative_fully_supported":expected!="supported" and verdict=="supported",
               "checks":[check.model_dump() for check in checks],
               "model_calls":judge.calls,"model_errors":judge.errors}
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(evaluate,cases):
            rows.append(row)
            print(f"{row['id']} {row['category']}: expected={row['expected']} actual={row['actual']}",flush=True)
    positives = [row for row in rows if row["expected"]=="supported"]
    negatives = [row for row in rows if row["expected"]!="supported"]
    summary = {
        "cases":len(rows),"positive_cases":len(positives),"negative_cases":len(negatives),
        "exact_matches":sum(r["exact_match"] for r in rows),
        "negative_fully_supported":sum(r["negative_fully_supported"] for r in rows),
        "positive_supported":sum(r["actual"]=="supported" for r in positives),
        "model_calls":sum(len(r["model_calls"])+len(r["model_errors"]) for r in rows),
        "transport_or_http_errors":sum(len(r["model_errors"]) for r in rows),
        "elapsed_s":round(time.monotonic()-started,3),
    }
    result = {"run_at_utc":datetime.now(timezone.utc).isoformat(),"code_commit":code,
              "model":model,"temperature":0,"synthetic":fixture["synthetic"],
              "working_tree_dirty":bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip()),
              "fixture_sha256":sha256(args.cases.read_bytes()).hexdigest(),
              "verification_source_sha256":{p.name:sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"local_deep_research/research_verify").glob("*.py"))},
              "label_provenance":fixture["label_provenance"],"config":cfg.model_dump(),
              "scope":"Existing branch CitationQc with real model; verified abstract excerpts or synthetic controls, not complete report validation.",
              "summary":summary,"cases":rows}
    if not fixture["synthetic"]:
        result=redact_real_result(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("SUMMARY "+json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
