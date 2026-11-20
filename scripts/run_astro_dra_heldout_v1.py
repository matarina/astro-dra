"""Run the public 18-case held-out package in matched baseline/candidate arms.

The runner sends only public prompt/source-packet bytes to the local
OpenAI-compatible endpoint. Private gold labels are deliberately outside the
input path. The candidate arm adds the current generic evidence-grounding
instructions, while the baseline uses the same source-bound task with a short
neutral instruction.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os
import requests
import time

from research_verify.generation import GROUNDING_INSTRUCTIONS
from research_verify.debug_capture import capture_chat_completion
from research_verify.generation_receipt import output_completeness


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"
ENDPOINT = os.environ.get("LDR_HELDOUT_ENDPOINT", "http://127.0.0.1:8080").rstrip("/")
MODEL = os.environ.get("LDR_HELDOUT_MODEL", "deepseek-v4.1-flash-gsq-rco-iq2_xxs")
TEMPERATURE = float(os.environ.get("LDR_HELDOUT_TEMPERATURE", "0"))
MAX_TOKENS = int(os.environ.get("LDR_HELDOUT_MAX_TOKENS", "3000"))
WORKERS = max(1, int(os.environ.get("LDR_HELDOUT_WORKERS", "2")))
DEBUG_CAPTURE_DIR = os.environ.get("LDR_HELDOUT_DEBUG_DIR")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def read_case(row: dict) -> dict:
    prompt_path = PACKAGE / row["prompt_path"]
    packet_path = PACKAGE / row["source_packet_path"]
    packet = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    source_text = "\n\n".join(
        f"SOURCE {item['source_id']}\n"
        f"Title: {item.get('title','')}\n"
        f"Type: {item.get('source_type','unknown')}\n"
        f"Content basis: {item.get('content_type','unknown')}\n"
        f"Text:\n{item['text']}"
        for item in packet
    )
    return {
        **row,
        "question": prompt_path.read_text(encoding="utf-8").strip(),
        "question_sha256": digest_bytes(prompt_path.read_bytes()),
        "source_packet": packet,
        "source_text": source_text,
        "source_packet_sha256": digest_bytes(packet_path.read_bytes()),
    }


def prompt_for(case: dict, arm: str) -> str:
    if arm == "baseline":
        instruction = (
            "Answer the user request using only the supplied frozen source packet. "
            "Cite the source IDs exactly as shown. Preserve study scope, species, "
            "population, tissue, assay, quantities, uncertainty, and evidence limits. "
            "If the packet does not establish a detail, say that it is not established. "
            "Do not invent sources or citations."
        )
    else:
        instruction = (
            "Answer the user request using only the supplied frozen source packet. "
            "The following generic evidence-grounding contract applies. It is a "
            "candidate evaluation arm, not a truth guarantee.\n\n" + GROUNDING_INSTRUCTIONS
        )
    return (
        f"{instruction}\n\nUSER REQUEST:\n{case['question']}\n\n"
        f"FROZEN SOURCE PACKET:\n{case['source_text']}\n\n"
        "Return the answer only. Keep source IDs explicit in citations."
    )


def call_model(prompt: str, *, arm: str | None = None, case_id: str | None = None) -> tuple[str, dict]:
    session = requests.Session()
    # The model is local. Do not route loopback calls through the lab proxy.
    session.trust_env = False
    payload = {"model": MODEL, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
               "messages": [{"role": "user", "content": prompt}]}
    data, receipt = capture_chat_completion(
        session, ENDPOINT + "/v1/chat/completions", payload,
        timeout=(15, 900), capture_dir=DEBUG_CAPTURE_DIR, arm=arm, case_id=case_id,
    )
    content = data["choices"][0]["message"].get("content") or ""
    return content, {"status_code": receipt.get("status_code"), "elapsed_s": receipt["elapsed_s"],
                     "provider_model": data.get("model"),
                     "usage": data.get("usage"),
                     "finish_reason": receipt.get("finish_reason"),
                     "response_sha256": digest_text(content),
                     "debug_capture_dir": receipt.get("capture_dir"),
                     "returned_thinking_fields": sorted(receipt.get("thinking_fields", {}))}


def run_one(case: dict, arm: str, output: Path) -> dict:
    prompt = prompt_for(case, arm)
    row = {
        "case_id": case["case_id"], "arm": arm, "model": MODEL, "endpoint": ENDPOINT,
        "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
        "prompt_sha256": digest_text(prompt), "prompt_chars": len(prompt),
        "source_packet_sha256": case["source_packet_sha256"], "status": "started",
    }
    try:
        content, metadata = call_model(prompt, arm=arm, case_id=case["case_id"])
        completeness = output_completeness(content, metadata.get("finish_reason"))
        row.update(metadata, status="completed" if completeness == "complete" else "incomplete",
                   output_completeness=completeness, output_chars=len(content), output=content)
    except Exception as exc:
        row.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:1000])
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{case['case_id']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def main() -> None:
    from validate_astro_dra_heldout_v1 import validate

    validation = validate(PACKAGE)
    manifest = [json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [read_case(row) for row in manifest]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = Path(os.environ["LDR_HELDOUT_RUN_ROOT"]) if os.environ.get("LDR_HELDOUT_RUN_ROOT") else PACKAGE / "runs" / f"matched-{stamp}"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "protocol.json").write_text(json.dumps({
        "schema_version": "astro_dra_heldout_run.v1", "status": "started",
        "case_count": len(cases), "arms": ["baseline", "candidate"],
        "endpoint": ENDPOINT, "model": MODEL, "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS, "workers": WORKERS,
        "debug_capture_enabled": bool(DEBUG_CAPTURE_DIR),
        "public_manifest_sha256": digest_bytes((PACKAGE / "manifest.public.jsonl").read_bytes()),
        "gold_private_used": False, "candidate_outputs_inspected": False,
        "package_validation": validation,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    all_rows = []
    for arm in ("baseline", "candidate"):
        arm_dir = run_root / arm
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(run_one, case, arm, arm_dir) for case in cases]
            rows = [future.result() for future in as_completed(futures)]
        completed = sum(row.get("status") == "completed" for row in rows)
        all_rows.extend(rows)
        (arm_dir / "summary.json").write_text(json.dumps({
            "arm": arm, "case_count": len(rows), "completed": completed,
            "incomplete": sum(row.get("status") == "incomplete" for row in rows),
            "failed": sum(row.get("status") == "failed" for row in rows),
            "gold_private_used": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "protocol.json").write_text(json.dumps({
        "schema_version": "astro_dra_heldout_run.v1",
        "status": "completed" if all(row.get("status") == "completed" for row in all_rows) else "incomplete",
        "case_count": len(cases), "arms": ["baseline", "candidate"],
        "endpoint": ENDPOINT, "model": MODEL, "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS, "workers": WORKERS,
        "public_manifest_sha256": digest_bytes((PACKAGE / "manifest.public.jsonl").read_bytes()),
        "gold_private_used": False, "candidate_outputs_inspected": False,
        "package_validation": validation,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_root": str(run_root), "case_count": len(cases),
                      "gold_private_used": False, "candidate_outputs_inspected": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
