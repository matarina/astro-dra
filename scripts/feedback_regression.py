#!/usr/bin/env python3
"""Extract archived feedback for inspection; no semantic pass is inferred."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "LDR第二次调研.rar"
WORKBOOK_MARKER = "文献检索智能体问题搜集表"


def _merged_lookup(sheet):
    """Return a structural value lookup for merged cells.

    Feedback workbooks use merged prompt/sequence cells.  A blank cell inside
    a merged range is a continuation of the top-left value, not a missing row.
    Keep the range name in each record so later audits can distinguish a true
    repeated row from a merged continuation.
    """
    merged = {}
    for rng in sheet.merged_cells.ranges:
        min_col, min_row, max_col, max_row = rng.bounds
        value = sheet.cell(min_row, min_col).value
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                merged[(row, col)] = (value, str(rng))
    return merged


def _load_rows(directory: Path, *, include_examples: bool = True) -> list[dict]:
    from openpyxl import load_workbook

    rows: list[dict] = []
    for path in sorted(directory.rglob("*.xlsx")):
        if WORKBOOK_MARKER not in path.name:
            continue
        # MergedCell objects are only reliably represented in normal mode.
        workbook = load_workbook(path, read_only=False, data_only=True)
        for sheet in workbook.worksheets:
            merged = _merged_lookup(sheet)
            header_values = [sheet.cell(1, col).value for col in range(1, sheet.max_column + 1)]
            headers = [str(value).strip() if value is not None else "" for value in header_values]
            if "引用编号" in headers and "报告中的描述 / 出处" in headers:
                for row_number in range(2, sheet.max_row + 1):
                    values = [sheet.cell(row_number, col).value for col in range(1, sheet.max_column + 1)]
                    if not any(value not in (None, "") for value in values):
                        continue
                    rows.append({
                        "kind": "xenium_detail",
                        "workbook": path.name,
                        "sheet": sheet.title,
                        "row": row_number,
                        "cells": {header: values[i] if i < len(values) and values[i] is not None else "" for i, header in enumerate(headers)},
                    })
                continue
            if "提示词" not in headers:
                continue
            prompt_index = headers.index("提示词")
            for row_number in range(2, sheet.max_row + 1):
                values = [sheet.cell(row_number, col).value for col in range(1, sheet.max_column + 1)]
                prompt_value, prompt_merge = merged.get((row_number, prompt_index + 1), (values[prompt_index] if prompt_index < len(values) else None, None))
                prompt = str(prompt_value).strip() if prompt_value is not None else ""
                seq_index = headers.index("序号") if "序号" in headers else None
                seq_value, seq_merge = merged.get((row_number, (seq_index + 1) if seq_index is not None else 1), (values[seq_index] if seq_index is not None and seq_index < len(values) else None, None))
                sequence = str(seq_value).strip() if seq_value is not None else ""
                if not prompt:
                    continue
                is_overall = prompt == "其他"
                is_example = sequence == "示例" or sequence.lower() == "example"
                if is_example and not include_examples:
                    continue
                feedback_index = headers.index("异常结论（位置，错误原因）") if "异常结论（位置，错误原因）" in headers else None
                row_record = {
                    "kind": "general_feedback" if is_overall else "topic_feedback",
                    "workbook": path.name,
                    "sheet": sheet.title,
                    "row": row_number,
                    "sequence": sequence,
                    "prompt": prompt,
                    "resolved_prompt": prompt,
                    "prompt_merged_range": prompt_merge,
                    "is_overall": is_overall,
                    "is_template_example": is_example,
                    "feedback": str(values[feedback_index]).strip()
                    if feedback_index is not None
                    and feedback_index < len(values)
                    and values[feedback_index]
                    else "",
                    "cells": {header: values[i] if i < len(values) and values[i] is not None else "" for i, header in enumerate(headers)},
                }
                # Resolve merged prompt ranges explicitly for all continuation rows.
                rows.append(row_record)
    return rows


def _extract_archive(archive: Path, output: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    if not seven_zip:
        raise RuntimeError("7z is required to read the RAR archive")
    subprocess.run(
        [seven_zip, "x", "-y", f"-o{output}", str(archive)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--extracted-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    import sys
    sys.path.insert(0, str(ROOT / "local_deep_research"))
    try:
        import loguru  # type: ignore  # optional in the host preflight env
    except ModuleNotFoundError:
        class _QuietLogger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None
        import types
        sys.modules["loguru"] = types.SimpleNamespace(logger=_QuietLogger())
    from research_verify.research_spec import parse_research_spec

    if args.extracted_dir:
        rows = _load_rows(args.extracted_dir)
        source = str(args.extracted_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="ldr-feedback-") as temp:
            directory = Path(temp)
            _extract_archive(args.archive, directory)
            rows = _load_rows(directory)
            source = str(args.archive)

    cases = []
    seen = set()
    for row in rows:
        if row.get("kind") != "topic_feedback" or row.get("is_template_example"):
            continue
        name = "archive-" + hashlib.sha256(row["prompt"].encode()).hexdigest()[:12]
        # The workbook repeats the same prompt for every checked citation. Keep
        # one frozen case while preserving the feedback rows in the manifest.
        if (name, row["prompt"]) in seen:
            continue
        seen.add((name, row["prompt"]))
        spec = parse_research_spec(row["prompt"])
        checks = []
        feedback_examples = [
            item["feedback"] for item in rows
            if item.get("kind") == "topic_feedback"
            and not item.get("is_template_example")
            and item.get("prompt") == row["prompt"] and item.get("feedback")
        ]
        cases.append({
            "case": name,
            "prompt": row["prompt"],
            "source_workbook": row["workbook"],
            "scope": spec.as_dict(),
            "checks": checks,
            "feedback_examples": list(dict.fromkeys(feedback_examples)),
        })
    result = {
        "status": "archive_extracted_not_evaluated",
        "semantic_assessment": "not_performed",
        "source": source,
        "case_count": len(cases),
        "cases": cases,
        "interpretation": (
            "Original prompts and feedback are preserved. Query intent is not "
            "validated by topic-specific assertions; no scientific or report-quality pass is assigned."
        ),
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
