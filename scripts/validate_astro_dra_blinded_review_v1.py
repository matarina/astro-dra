"""Validate the P0 arm-blind review packet and frozen 36-answer denominator."""
from __future__ import annotations

import json
from pathlib import Path
import re
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"
REVIEW = PACKAGE / os.environ.get("LDR_REVIEW_ROOT", "blinded-review-v1")
RUN = PACKAGE / "runs" / "matched-20261118T052009Z"


def validate() -> dict:
    pass1 = json.loads((REVIEW / "pass1_manifest.json").read_text(encoding="utf-8"))
    reports = pass1["reports"]
    if len(reports) != 36 or len({row["opaque_report_id"] for row in reports}) != 36:
        raise ValueError("pass1 report denominator mismatch")
    if any(pass1.get(key) is not False for key in ("gold_visible", "arm_visible", "case_id_visible", "model_assessment_visible")):
        raise ValueError("pass1 disclosure flags are not sealed")
    opaque = {row["opaque_report_id"] for row in reports}
    packet_ids = {path.name for path in (REVIEW / "pass1_packets").iterdir() if path.is_dir()}
    if packet_ids != opaque:
        raise ValueError("opaque packet set mismatch")
    form_ids = {path.stem for path in (REVIEW / "review_forms").glob("*.json")}
    if form_ids != opaque:
        raise ValueError("review form set mismatch")
    private = json.loads((REVIEW / "private" / "arm_key.json").read_text(encoding="utf-8"))
    mapping = private["reports"]
    if set(mapping) != opaque:
        raise ValueError("arm key set mismatch")
    if {row["arm"] for row in mapping.values()} != {"baseline", "candidate"}:
        raise ValueError("missing arm in arm key")
    if sum(row["arm"] == "baseline" for row in mapping.values()) != 18:
        raise ValueError("baseline arm denominator mismatch")
    if sum(row["arm"] == "candidate" for row in mapping.values()) != 18:
        raise ValueError("candidate arm denominator mismatch")
    manifest = [json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    public_by_case = {row["case_id"]: row for row in manifest}
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "local_deep_research"))
    from run_astro_dra_heldout_v1 import prompt_for
    hashes_by_case = {"baseline": {}, "candidate": {}}
    for report in reports:
        opaque_id = report["opaque_report_id"]
        directory = REVIEW / "pass1_packets" / opaque_id
        packet_hashes = [
            ("prompt.md", "prompt_sha256"),
            ("source_packet.jsonl", "source_packet_sha256"),
            ("output.md", "output_sha256"),
        ]
        if "writer_visible_material_sha256" in report:
            packet_hashes.insert(2, ("writer_visible_material.txt", "writer_visible_material_sha256"))
        for name, key in packet_hashes:
            value = __import__("hashlib").sha256((directory / name).read_bytes()).hexdigest()
            if value != report[key]:
                raise ValueError(f"packet hash mismatch: {opaque_id}/{name}")
        original = mapping[opaque_id]
        case_id, arm = original["case_id"], original["arm"]
        hashes_by_case[arm][case_id] = report["output_sha256"]
        if public_by_case[case_id]["prompt_sha256"] != report["prompt_sha256"]:
            raise ValueError(f"prompt not frozen: {opaque_id}")
        private_row = private.get("reports", {}).get(opaque_id, {})
        if pass1.get("source_view") == "exact_writer_visible_source_material":
            if private_row.get("raw_source_packet_sha256") != public_by_case[case_id]["source_packet_sha256"]:
                raise ValueError(f"raw source packet provenance mismatch: {opaque_id}")
            if private_row.get("saved_receipt_sha256") != __import__("hashlib").sha256((ROOT / private_row["saved_output_path"]).read_bytes()).hexdigest():
                raise ValueError(f"origin receipt mismatch: {opaque_id}")
            if private_row.get("saved_response_sha256") != report["output_sha256"]:
                raise ValueError(f"origin output mismatch: {opaque_id}")
            raw_packet = PACKAGE / public_by_case[case_id]["source_packet_path"]
            raw_rows = [json.loads(line) for line in raw_packet.read_text(encoding="utf-8").splitlines() if line.strip()]
            visible_rows = [{"source_id": item["source_id"], "title": item.get("title", ""),
                             "source_type": item.get("source_type", "unknown"),
                             "content_type": item.get("content_type", "unknown"), "text": item["text"]}
                            for item in raw_rows]
            visible_material = "\n\n".join(
                f"SOURCE {item['source_id']}\nTitle: {item.get('title','')}\n"
                f"Type: {item.get('source_type','unknown')}\nContent basis: {item.get('content_type','unknown')}\n"
                f"Text:\n{item['text']}" for item in visible_rows)
            if __import__("hashlib").sha256(visible_material.encode()).hexdigest() != report["writer_visible_material_sha256"]:
                raise ValueError(f"writer-visible evidence mismatch: {opaque_id}")
            question = (PACKAGE / public_by_case[case_id]["prompt_path"]).read_text(encoding="utf-8").strip()
            prompt_hash = __import__("hashlib").sha256(
                prompt_for({"question": question, "source_text": visible_material}, arm).encode()
            ).hexdigest()
            saved = json.loads((ROOT / private_row["saved_output_path"]).read_text(encoding="utf-8"))
            if prompt_hash != saved.get("prompt_sha256"):
                raise ValueError(f"generator prompt receipt mismatch: {opaque_id}")
        elif public_by_case[case_id]["source_packet_sha256"] != report["source_packet_sha256"]:
            raise ValueError(f"source packet not frozen: {opaque_id}")
    if set(hashes_by_case["baseline"]) != set(public_by_case) or set(hashes_by_case["candidate"]) != set(public_by_case):
        raise ValueError("saved answer case set mismatch")
    if any(hashes_by_case["baseline"][case] == hashes_by_case["candidate"][case] for case in public_by_case):
        raise ValueError("paired answer hashes unexpectedly identical")
    pass2 = json.loads((REVIEW / "private" / "pass2_key.json").read_text(encoding="utf-8"))
    if len(pass2["reports"]) != 36 or {row["opaque_report_id"] for row in pass2["reports"]} != opaque:
        raise ValueError("pass2 gold denominator mismatch")
    return {"status": "blinded_review_packet_valid", "reports": 36,
            "baseline": 18, "candidate": 18, "paired_answer_hashes_differ": True,
            "gold_hidden_from_pass1": True}


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
