"""Validate the public/private boundaries of the Astro-DRA held-out package."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def text_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def validate(package: Path = PACKAGE) -> dict:
    public_path = package / "manifest.public.jsonl"
    rows = [json.loads(line) for line in public_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 18:
        raise ValueError(f"expected 18 public cases, found {len(rows)}")
    ids = [row["case_id"] for row in rows]
    expected = {*(f"E{i:02d}" for i in range(1, 9)), *(f"P{i:02d}" for i in range(1, 5)), *(f"C{i:02d}" for i in range(1, 7))}
    if set(ids) != expected or len(ids) != len(set(ids)):
        raise ValueError("public case denominator or IDs are incorrect")
    for row in rows:
        prompt = package / row["prompt_path"]
        packet = package / row["source_packet_path"]
        if digest(prompt) != row["prompt_sha256"]:
            raise ValueError(f"prompt hash mismatch: {row['case_id']}")
        if digest(packet) != row["source_packet_sha256"]:
            raise ValueError(f"source packet hash mismatch: {row['case_id']}")
        for line in packet.read_text(encoding="utf-8").splitlines():
            source = json.loads(line)
            if text_digest(source["text"]) != source["text_sha256"]:
                raise ValueError(f"source text hash mismatch: {row['case_id']}:{source['source_id']}")
    seal = json.loads((package / "gold.private" / "SEAL.json").read_text(encoding="utf-8"))
    if seal.get("status") != "sealed" or seal.get("candidate_outputs_inspected", False):
        raise ValueError("private gold packet is not sealed-before-run")
    if sorted(seal.get("case_ids", [])) != sorted(ids):
        raise ValueError("private gold denominator does not match public denominator")
    for expected_hash, name in (item.split("  ", 1) for item in seal.get("label_hashes", [])):
        if digest(package / "gold.private" / name) != expected_hash:
            raise ValueError(f"gold label hash mismatch: {name}")
        case_id = name.split("_claim_labels", 1)[0]
        # The source packet is selected below from the public row for this case.
        public = next(row for row in rows if row["case_id"] == case_id)
        packet_rows = {json.loads(line)["source_id"]: json.loads(line)
                       for line in (package / public["source_packet_path"]).read_text(encoding="utf-8").splitlines()
                       if line.strip()}
        for claim in (json.loads(line) for line in (package / "gold.private" / name).read_text(encoding="utf-8").splitlines() if line.strip()):
            for exact in claim.get("exact_locators", []):
                source = packet_rows[exact["source_id"]]
                if source["text_sha256"] != exact["content_sha256"] or source["text"][exact["start"]:exact["end"]] != exact["quote"]:
                    raise ValueError(f"gold locator mismatch: {case_id}:{claim['claim_id']}")
    return {"status": "sealed_inputs_valid", "case_count": len(rows),
            "gold_case_count": len(seal["case_ids"]), "candidate_outputs_inspected": False}


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
