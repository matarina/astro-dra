"""Summarize the completed preliminary held-out assessment."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import os


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"


def normalize(row: dict, arm: str) -> str:
    return row.get(arm) or row.get(f"{arm}_label") or "unclear"


def main() -> None:
    run_root = Path(os.environ.get("LDR_HELDOUT_RUN_ROOT", ""))
    if not run_root:
        run_root = sorted((PACKAGE / "runs").glob("matched-*"))[-1]
    assessment_dir = run_root / "preliminary_assessment"
    manifest = [json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    totals = {arm: Counter() for arm in ("baseline", "candidate")}
    expected_label_counts = Counter()
    claim_rows = []
    case_summary = defaultdict(dict)
    for row in manifest:
        case_id = row["case_id"]
        labels = [json.loads(line) for line in (PACKAGE / "gold.private" / f"{case_id}_claim_labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assessment = json.loads((assessment_dir / f"{case_id}.json").read_text(encoding="utf-8"))["assessment"]
        judged = {item["claim_id"]: item for item in assessment.get("claims", [])}
        outputs = {arm: json.loads((run_root / arm / f"{case_id}.json").read_text(encoding="utf-8"))["output"] for arm in ("baseline", "candidate")}
        for gold in labels:
            item = judged.get(gold["claim_id"], {})
            expected = gold["expected_label"]
            expected_label_counts[expected] += 1
            row_out = {"case_id": case_id, "claim_id": gold["claim_id"], "expected": expected}
            for arm in ("baseline", "candidate"):
                status = normalize(item, arm)
                cites = sorted(set(re.findall(r"SRC-[A-Z0-9-]+", outputs[arm])))
                source_ids = set(gold.get("source_ids", []))
                hallucination = (
                    expected == "supported" and status in {"contradicted", "overextended"}
                ) or (
                    expected in {"unsupported", "unverifiable"} and status == "supported"
                )
                citation_aligned = bool(source_ids & set(cites)) if source_ids else None
                totals[arm]["claims"] += 1
                totals[arm][f"expected:{expected}"] += 1
                totals[arm][f"status:{status}"] += 1
                totals[arm]["preliminary_hallucination_flags"] += int(hallucination)
                totals[arm]["citation_source_overlap"] += int(bool(citation_aligned))
                row_out[arm] = {"status": status, "cited_source_ids": cites,
                                "citation_source_overlap": citation_aligned,
                                "preliminary_hallucination_flag": hallucination}
            claim_rows.append(row_out)
        case_summary[case_id] = {
            arm: {"flags": sum(int(row[arm]["preliminary_hallucination_flag"]) for row in claim_rows if row["case_id"] == case_id),
                  "claims": sum(1 for row in claim_rows if row["case_id"] == case_id)}
            for arm in ("baseline", "candidate")
        }
    result = {
        "schema_version": "astro_dra_heldout_preliminary_summary.v1",
        "run_root": str(run_root), "case_count": len(manifest),
        "baseline": dict(totals["baseline"]), "candidate": dict(totals["candidate"]),
        "expected_label_counts": dict(expected_label_counts),
        "claim_rows": claim_rows, "case_summary": dict(case_summary),
        "assessment_independence": "same_endpoint_preliminary",
        "human_acceptance": "pending",
        "interpretation": "Deterministic ledger comparison plus same-endpoint model assessment. This is diagnostic evidence, not independent human adjudication.",
    }
    (run_root / "preliminary_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_root": str(run_root), "baseline": result["baseline"], "candidate": result["candidate"], "human_acceptance": "pending"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
