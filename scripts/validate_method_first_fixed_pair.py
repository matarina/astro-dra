"""Validate the correctly matched method-first fixed-source pair receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIR = ROOT / "evaluation/method-first-20261112/immune-fixed-true-pair-summary.json"
ARMS = ROOT / "evaluation/method-first-20261112"

pair = json.loads(PAIR.read_text())
assert pair["status"] == "evaluation_only_fixed_source"
assert pair["source_count"] == 81
assert pair["question_sha256"] == hashlib.sha256(pair["question"].encode()).hexdigest()
for arm_name, expected_arm in (("baseline", "baseline"), ("candidate", "candidate")):
    arm = pair[arm_name]
    assert arm["status"] == "completed"
    result_dir = ARMS / ("immune-fixed-true-baseline-immune" if arm_name == "baseline" else "immune-fixed-true-candidate-immune")
    result = json.loads((result_dir / "result.json").read_text())
    assert result["arm"] == expected_arm
    assert result["source_sha256"] == pair["source_sha256"]
    assert (result_dir / "report.md").read_text().strip()
old = json.loads((ARMS / "immune-fixed-current-summary.json").read_text())
assert old["status"] == "superseded_invalid_label"
print("method_first_fixed_pair_valid", pair["source_sha256"], pair["question_sha256"])
