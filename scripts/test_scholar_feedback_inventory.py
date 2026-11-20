#!/usr/bin/env python3
"""Regression checks for the archive extractor and corrected ledger."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts/feedback_regression.py"
    spec = importlib.util.spec_from_file_location("feedback_regression", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = _load_module()
    archive = ROOT / "LDR第二次调研.rar"
    with tempfile.TemporaryDirectory(prefix="feedback-inventory-") as directory:
        subprocess.run(["7z", "x", "-y", f"-o{directory}", str(archive)], check=True, stdout=subprocess.DEVNULL)
        rows = module._load_rows(pathlib.Path(directory))
    topic = [x for x in rows if x.get("kind") == "topic_feedback" and not x.get("is_template_example")]
    examples = [x for x in rows if x.get("is_template_example")]
    overall = [x for x in rows if x.get("kind") == "general_feedback"]
    xenium = [x for x in rows if x.get("kind") == "xenium_detail"]
    assert len(topic) == 32, len(topic)
    assert len({x["prompt"] for x in topic}) == 6
    assert len(examples) == 3
    assert len(overall) == 1
    assert len(xenium) == 38
    assert {x["prompt_merged_range"] for x in topic if x["prompt_merged_range"]} == {"B3:B8", "B2:B6", "B7:B12"}

    ledger = json.loads((ROOT / "evaluation/scholar-strategy-20261112/full-feedback-coverage-ledger.json").read_text(encoding="utf-8"))
    recount = json.loads((ROOT / "evaluation/scholar-strategy-20261112/archive-recount.json").read_text(encoding="utf-8"))
    assert ledger["counts"] == {
        "actual_tasks": 6,
        "topic_feedback_rows": 32,
        "overall_feedback_rows": 1,
        "template_example_rows_excluded": 3,
        "xenium_detail_rows_overlapping": 38,
    }
    assert len({x["row_id"] for x in ledger["topic_feedback_rows"]}) == 32
    assert len({x["row_id"] for x in ledger["xenium_details"]}) == 38
    expected_locations = {(x["workbook"], x["sheet"], x["row"]) for x in recount["topic_feedback_rows"]}
    actual_locations = {(x["workbook"], x["sheet"], x["row"]) for x in ledger["topic_feedback_rows"]}
    assert actual_locations == expected_locations
    for source, stored in zip(recount["topic_feedback_rows"], ledger["topic_feedback_rows"]):
        assert source["cells"] == stored["cells"]
        assert source["resolved_prompt"] == stored["prompt"]
    assert [x["citation_number"] for x in ledger["xenium_details"]] == [
        x["cells"].get("引用编号", "") for x in recount["xenium_details"]
    ]
    print("scholar feedback inventory regression OK")


if __name__ == "__main__":
    main()
