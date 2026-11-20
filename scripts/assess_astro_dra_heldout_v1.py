"""Preliminary post-run claim assessment for the 18-case held-out pair.

This assessor runs only after both arms complete. It uses the sealed private
ledger and source packets to produce a structured preliminary review. Because
it uses the same local endpoint as generation, its result is diagnostic and
does not replace blinded human adjudication.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import re
import requests


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"
ENDPOINT = os.environ.get("LDR_HELDOUT_ENDPOINT", "http://127.0.0.1:8080").rstrip("/")
MODEL = os.environ.get("LDR_HELDOUT_MODEL", "deepseek-v4.1-flash-gsq-rco-iq2_xxs")
WORKERS = max(1, int(os.environ.get("LDR_HELDOUT_ASSESS_WORKERS", "2")))


def parse_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start:end + 1])
        raise


def load_case(case_id: str, run_root: Path) -> dict:
    manifest = [json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    row = next(row for row in manifest if row["case_id"] == case_id)
    packet = [json.loads(line) for line in (PACKAGE / row["source_packet_path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = [json.loads(line) for line in (PACKAGE / "gold.private" / f"{case_id}_claim_labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    outputs = {arm: json.loads((run_root / arm / f"{case_id}.json").read_text(encoding="utf-8"))["output"] for arm in ("baseline", "candidate")}
    source_text = "\n\n".join(f"SOURCE {item['source_id']}\n{item['text']}" for item in packet)
    return {"case_id": case_id, "labels": labels, "outputs": outputs, "source_text": source_text}


def assess_case(case: dict, output_dir: Path) -> dict:
    ledger = [{k: row[k] for k in ("claim_id", "claim_text", "expected_label", "claim_class", "source_ids", "rationale")} for row in case["labels"]]
    prompt = (
        "You are a preliminary evidence-faithfulness assessor. Compare two generated "
        "answers against the supplied frozen source packet and the private atomic "
        "ledger. For every ledger claim, classify each arm as one of supported, "
        "partly_supported, absent, overextended, contradicted, or unclear. "
        "Mark overextended or contradicted only when the answer makes that claim "
        "or an equivalent claim. Check cited source IDs and scope. Also list any "
        "new biological hallucination that is not represented by a ledger claim. "
        "Do not reward verbosity. Return JSON only with keys claims and new_errors."
        "\n\nPRIVATE LEDGER:\n" + json.dumps(ledger, ensure_ascii=False) +
        "\n\nFROZEN SOURCES:\n" + case["source_text"] +
        "\n\nBASELINE ANSWER:\n" + case["outputs"]["baseline"] +
        "\n\nCANDIDATE ANSWER:\n" + case["outputs"]["candidate"]
    )
    session = requests.Session(); session.trust_env = False
    try:
        response = session.post(ENDPOINT + "/v1/chat/completions", json={
            "model": MODEL, "temperature": 0, "max_tokens": 2400,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=(15, 900))
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"].get("content") or ""
        parsed = parse_json(raw)
        result = {"case_id": case["case_id"], "status": "completed", "assessment": parsed,
                  "assessor_model": MODEL, "assessor_endpoint": ENDPOINT,
                  "independence": "same_endpoint_preliminary", "prompt_chars": len(prompt)}
    except Exception as exc:
        result = {"case_id": case["case_id"], "status": "failed", "error_type": type(exc).__name__,
                  "error": str(exc)[:1000], "independence": "same_endpoint_preliminary"}
    (output_dir / f"{case['case_id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    run_root = Path(os.environ.get("LDR_HELDOUT_RUN_ROOT", ""))
    if not run_root:
        runs = sorted((PACKAGE / "runs").glob("matched-*"))
        run_root = runs[-1]
    output_dir = run_root / "preliminary_assessment"
    output_dir.mkdir(parents=True, exist_ok=True)
    case_ids = [json.loads(line)["case_id"] for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [load_case(case_id, run_root) for case_id in case_ids]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = [future.result() for future in as_completed([pool.submit(assess_case, case, output_dir) for case in cases])]
    summary = {"schema_version": "astro_dra_heldout_preliminary_assessment.v1",
               "run_root": str(run_root), "case_count": len(results),
               "completed": sum(row.get("status") == "completed" for row in results),
               "failed": sum(row.get("status") != "completed" for row in results),
               "assessor_model": MODEL, "assessor_endpoint": ENDPOINT,
               "independence": "same_endpoint_preliminary",
               "gold_used_after_both_arms": True,
               "human_acceptance": "pending"}
    (run_root / "preliminary_assessment.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
