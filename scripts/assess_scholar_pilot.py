#!/usr/bin/env python3
"""Blind, source-bound provisional assessment for the corrected scholar pilot."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CORRECTED = ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112"
NEW = ROOT / "evaluation/scholar-controlled-pilot-corrected-v2-20261112"
OUT = ROOT / "evaluation/scholar-strategy-20261112/pilot-assessment-20261112"


def cited_ids(text: str) -> list[int]:
    ids = []
    for match in re.finditer(r"\[\[?(\d+)\]?\]", text or ""):
        value = int(match.group(1))
        if value not in ids: ids.append(value)
    return ids


def make_packet(result_path: Path, source_path: Path, blind_id: str) -> dict:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    sources = json.loads(source_path.read_text(encoding="utf-8"))
    report = result.get("body", "")
    if not report and (result_path.parent / "report.md").exists(): report = (result_path.parent / "report.md").read_text(encoding="utf-8")
    by_id = {int(s["index"]): s for s in sources if str(s.get("index", "")).isdigit()}
    records = []
    for index in cited_ids(report):
        if index not in by_id: continue
        source = by_id[index]
        records.append({"index": index, "title": source.get("title"), "doi": source.get("doi"), "pmid": source.get("pmid"), "evidence_type": source.get("content_type") or "abstract", "text": source.get("full_content") or source.get("abstract") or source.get("content") or ""})
    return {"blind_id": blind_id, "case_id": result.get("case_id"), "report": report, "cited_sources": records, "source_sha256": result.get("source_sha256"), "report_sha256": hashlib.sha256(report.encode()).hexdigest(), "settings": result.get("settings", {})}


def build_packets() -> list[dict]:
    packets = []
    for path in sorted((CORRECTED / "results").glob("*/**/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("status") != "completed": continue
        source_path = ROOT / result["source_file"]
        packets.append(make_packet(path, source_path, f"blind-{len(packets)+1:02d}"))
    for path in sorted((NEW / "results").glob("*/**/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("status") != "completed": continue
        source_path = ROOT / result["source_file"]
        packets.append(make_packet(path, source_path, f"blind-{len(packets)+1:02d}"))
    return packets


def calibration_packet() -> dict:
    fixture = json.loads((ROOT / "local_deep_research/tests/fixtures/adjudicated_claims_20261112.json").read_text(encoding="utf-8"))
    selected = []
    for wanted in [(78, "supported"), (68, "contradicted"), (41, "partially supported")]:
        case = next(x for x in fixture["cases"] if int(x["claim_id"]) == wanted[0] and x["scientific_verdict"] == wanted[1])
        selected.append({"claim_id": case["claim_id"], "claim": case["claim_text"], "known_verdict": case["scientific_verdict"], "scope": case["writer_evidence_scope"], "adjudicator_evidence": case.get("evidence_links", [])})
    return {"claims": selected, "known_labels_are_calibration_only": True}


RUBRIC = """You are a provisional evidence assessor. Use only the supplied report and cited source records. Do not infer missing facts from general knowledge. Distinguish a scientific assertion from a transparent statement that the supplied material is incomplete. A citation ID that exists is not proof of entailment. For each report, sample up to 12 substantive factual claims and return supported, partially_supported, unsupported, contradicted or unverifiable. Also assess citation entailment, qualifier/counterevidence retention, important requested-information coverage, scope compliance and usefulness on 0-2 scales. Preserve uncertainty when the supplied source is abstract-only. This is not independent medical adjudication. Return JSON only."""


def call(endpoint: str, key: str, prompt: str) -> dict:
    payload = {"model": "deepseek-v4-flash", "messages": [{"role": "system", "content": RUBRIC}, {"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 3500}
    started = time.monotonic()
    response = requests.post(endpoint.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload, timeout=(20, 480))
    elapsed = round(time.monotonic() - started, 3)
    response.raise_for_status()
    data = response.json(); content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {"content": content, "elapsed_s": elapsed, "usage": data.get("usage"), "model": data.get("model"), "finish_reason": ((data.get("choices") or [{}])[0].get("finish_reason"))}


def parse_json(content: str):
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    return json.loads(clean)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    packets = build_packets(); (OUT / "packets.json").write_text(json.dumps(packets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    calibration = calibration_packet(); (OUT / "calibration-packet.json").write_text(json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    endpoint = os.environ.get("LDR_LLM_OPENAI_ENDPOINT_URL", "").rstrip("/"); key = os.environ.get("LDR_LLM_OPENAI_ENDPOINT_API_KEY", "")
    if not endpoint or not key: raise RuntimeError("assessment endpoint credentials must be supplied by isolated runtime")
    manifest = {"schema_version": "scholar_pilot_blind_assessment.v1", "status": "running", "packets": len(packets), "calibration_claims": len(calibration["claims"]), "method_identities_blinded": True, "source_bound": True, "model": "deepseek-v4-flash", "temperature": 0, "limitations": ["same model/provider used for assessment and generation", "not independent medical adjudication", "small bounded sample", "missing expert labels remain unresolved"]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    calibration_prompt = "CALIBRATION ONLY. Assess these claims and return {\"claims\":[{\"claim_id\":...,\"verdict\":\"...\"}]}\\n" + json.dumps(calibration, ensure_ascii=False)
    cal = call(endpoint, key, calibration_prompt); (OUT / "calibration-response.json").write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try: cal_obj = parse_json(cal["content"])
    except Exception: cal_obj = {"parse_error": True, "raw": cal["content"]}
    (OUT / "calibration-assessment.json").write_text(json.dumps(cal_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    results = []
    for packet in packets:
        prompt = "Assess this blinded report. Return JSON with keys claim_assessments (list of {claim, verdict, source_ids, evidence_quote}), citation_entailment (0-2), qualifier_retention (0-2), important_content_coverage (0-2), scope_compliance (0-2), usefulness (0-2), omissions, unresolved. Do not identify or guess the algorithm arm.\n\n" + json.dumps(packet, ensure_ascii=False)
        try:
            receipt = call(endpoint, key, prompt)
            try: assessment = parse_json(receipt["content"]); parse_error = False
            except Exception: assessment = {"raw": receipt["content"]}; parse_error = True
            row = {"blind_id": packet["blind_id"], "case_id": packet["case_id"], "report_sha256": packet["report_sha256"], "receipt": receipt, "assessment": assessment, "parse_error": parse_error}
        except Exception as exc:
            row = {"blind_id": packet["blind_id"], "case_id": packet["case_id"], "report_sha256": packet["report_sha256"], "status": "assessment_failed", "error_type": type(exc).__name__, "error": str(exc)}
        results.append(row); (OUT / f"{packet['blind_id']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"blind_id": packet["blind_id"], "status": row.get("status", "completed"), "parse_error": row.get("parse_error", False)}, ensure_ascii=False), flush=True)
    manifest.update(status="completed", completed=len(results), parse_errors=sum(bool(x.get("parse_error")) for x in results), failed=sum(x.get("status") == "assessment_failed" for x in results))
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__": main()
