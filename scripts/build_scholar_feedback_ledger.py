#!/usr/bin/env python3
"""Build the complete, source-preserving scholar feedback coverage ledger.

The recount is an archival extraction, not a scientific gold set.  This script
copies row text and provenance without deciding whether an allegation is true.
The Xenium worksheet is linked as an overlapping audit and is never added to
the topic-feedback denominator.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOUNT = ROOT / "evaluation/scholar-strategy-20261112/archive-recount.json"
OUT = ROOT / "evaluation/scholar-strategy-20261112/full-feedback-coverage-ledger.json"
MD = ROOT / "docs/scholar-feedback-coverage-ledger-20261112.md"


def _topic_id(prompt: str) -> str:
    return "task-" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def _diagnostic_tags(feedback: str) -> list[str]:
    """Conservative triage labels for review routing, never verdicts."""
    text = feedback or ""
    tags: list[str] = []
    if any(x in text for x in ("链接", "访问", "无原文", "没有", "未提供")):
        tags.append("evidence-availability")
    if any(x in text for x in ("错误", "不符", "误译", "错写", "无依据", "捏造")):
        tags.append("scientific-or-identity-interpretation")
    if any(x in text for x in ("重复", "不一致", "编号", "同一篇", "期刊不正确")):
        tags.append("document-consistency")
    if any(x in text for x in ("遗漏", "未准确描述", "缺少", "没有提取")):
        tags.append("selection-or-coverage")
    return tags or ["unclassified-awaiting-source-review"]


def build() -> dict:
    recount = json.loads(RECOUNT.read_text(encoding="utf-8"))
    topic_rows = []
    task_by_prompt: dict[str, str] = {}
    for index, row in enumerate(recount["topic_feedback_rows"], start=1):
        prompt = row["resolved_prompt"]
        task = task_by_prompt.setdefault(prompt, _topic_id(prompt))
        feedback = row["cells"].get("异常结论（位置，错误原因）", "") or ""
        topic_rows.append({
            "row_id": f"topic-{index:02d}",
            "kind": "topic_feedback",
            "task_id": task,
            "workbook": row["workbook"],
            "sheet": row["sheet"],
            "row": row["row"],
            "prompt": prompt,
            "prompt_merged_range": row.get("prompt_merged_range"),
            "cells": row["cells"],
            "feedback": feedback,
            "diagnostic_triage": _diagnostic_tags(feedback),
            "assessment_status": "unadjudicated-allegation",
            "overlap_links": (["xenium-detail-01..38"] if "10X Xenium" in prompt else []),
        })

    overall = []
    for index, row in enumerate(recount["general_feedback_rows"], start=1):
        overall.append({
            "row_id": f"overall-{index:02d}",
            "kind": "overall_feedback",
            "workbook": row["workbook"],
            "sheet": row["sheet"],
            "row": row["row"],
            "prompt": row["resolved_prompt"],
            "cells": row["cells"],
            "feedback": row["cells"].get("异常结论（位置，错误原因）", "") or "",
            "diagnostic_triage": ["cross-cutting-document-and-usefulness"],
            "assessment_status": "unadjudicated-overall-feedback",
        })

    examples = []
    for index, row in enumerate(recount["template_examples"], start=1):
        examples.append({
            "row_id": f"template-example-{index:02d}",
            "kind": "template_example_excluded",
            "workbook": row["workbook"],
            "sheet": row["sheet"],
            "row": row["row"],
            "prompt": row["resolved_prompt"],
            "cells": row["cells"],
            "exclusion_reason": "KRAS template/example; excluded from six actual task and feedback denominators",
        })

    xenium = []
    for index, row in enumerate(recount["xenium_details"], start=1):
        cells = row["cells"]
        xenium.append({
            "row_id": f"xenium-detail-{index:02d}",
            "kind": "xenium_overlapping_audit",
            "workbook": row["workbook"],
            "sheet": row["sheet"],
            "row": row["row"],
            "citation_number": cells.get("引用编号", ""),
            "report_description": cells.get("报告中的描述 / 出处", ""),
            "verified_record": cells.get("核验后的真实题录与事实", ""),
            "problem_type": cells.get("问题类型", ""),
            "supplied_judgement": cells.get("判定", ""),
            "assessment_status": "supplied-audit-label-not-independent-gold",
            "overlap_links": ["topic-27..32"],
        })

    tasks = []
    for task_id, prompt in ((v, k) for k, v in task_by_prompt.items()):
        task_rows = [r["row_id"] for r in topic_rows if r["task_id"] == task_id]
        tasks.append({"task_id": task_id, "prompt": prompt, "topic_row_ids": task_rows})

    result = {
        "status": "archival-coverage-ledger; semantic-adjudication-not-performed",
        "archive": recount["archive"],
        "archive_sha256": recount["sha256"],
        "counts": {
            "actual_tasks": len(tasks),
            "topic_feedback_rows": len(topic_rows),
            "overall_feedback_rows": len(overall),
            "template_example_rows_excluded": len(examples),
            "xenium_detail_rows_overlapping": len(xenium),
        },
        "tasks": tasks,
        "topic_feedback_rows": topic_rows,
        "overall_feedback_rows": overall,
        "template_examples_excluded": examples,
        "xenium_details": xenium,
        "limits": [
            "Feedback and supplied Xenium judgments are preserved allegations/audit labels, not automatic scientific gold.",
            "Xenium rows overlap the Xenium topic feedback and are not added to the independent error denominator.",
            "The 21 separately adjudicated claims are a regression set and are not substituted for this archive inventory.",
            "Missing writer-visible evidence, selection loss, draft anchoring, scientific misreading and document inconsistency require source-level review; triage tags are routing hypotheses only.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Scholar feedback coverage ledger (2026-11-12)",
        "",
        "This is a source-preserving inventory of the original feedback archive. It does not adjudicate whether a scientific allegation is true. The three KRAS rows are retained for traceability but excluded from actual-task totals. The 38 Xenium detail rows overlap the Xenium topic feedback and are linked rather than added to an independent error denominator.",
        "",
        f"Archive: `{recount['archive']}`  ",
        f"Archive SHA-256: `{recount['sha256']}`",
        "",
        "## Coverage",
        "",
        f"- Actual tasks: **{len(tasks)}**",
        f"- Topic-feedback rows: **{len(topic_rows)}**",
        f"- Overall-feedback rows: **{len(overall)}**",
        f"- KRAS template/example rows excluded from task denominators: **{len(examples)}**",
        f"- Overlapping Xenium audit rows: **{len(xenium)}**",
        "",
        "## Diagnostic reading rule",
        "",
        "The `diagnostic_triage` values are review-routing hypotheses. A missing passage is an evidence-availability finding; it is not by itself proof that the report claim is false. Selection loss, draft anchoring, scientific misreading and document inconsistency must be assessed separately against the original report and source records. No omission, citation count, or structural check establishes a hallucination-rate reduction.",
        "",
        "## Six actual tasks",
        "",
    ]
    for task in tasks:
        lines += [f"### `{task['task_id']}`", "", task["prompt"], "", "Rows: " + ", ".join(f"`{x}`" for x in task["topic_row_ids"]), ""]
    lines += ["## Topic-feedback rows", "", "| ID | Task | Workbook/sheet/row | Merged prompt range | Triage | Feedback |", "|---|---|---|---|---|---|"]
    for row in topic_rows:
        loc = f"{row['workbook']} / {row['sheet']} / {row['row']}"
        triage = ", ".join(row["diagnostic_triage"])
        feedback = row["feedback"].replace("\n", "<br>").replace("|", "\\|")
        lines.append(f"| `{row['row_id']}` | `{row['task_id']}` | `{loc}` | `{row.get('prompt_merged_range') or ''}` | {triage} | {feedback} |")
    lines += ["", "## Overall feedback", "", "| ID | Workbook/sheet/row | Feedback |", "|---|---|---|"]
    for row in overall:
        lines.append(f"| `{row['row_id']}` | `{row['workbook']} / {row['sheet']} / {row['row']}` | {row['feedback'].replace(chr(10), '<br>').replace('|', '\\|')} |")
    lines += ["", "## Excluded KRAS template examples", "", "These rows remain in the JSON for provenance and are excluded from the six-task/32-row denominators.", "", "| ID | Workbook/sheet/row | Prompt |", "|---|---|---|"]
    for row in examples:
        lines.append(f"| `{row['row_id']}` | `{row['workbook']} / {row['sheet']} / {row['row']}` | {row['prompt'].replace(chr(10), '<br>').replace('|', '\\|')} |")
    lines += ["", "## Overlapping Xenium audit (38 rows)", "", "The complete row-level content is in the JSON. It is retained as an overlapping audit, including positive controls and supplied labels; it is not independent gold.", "", "| ID | Citation | Problem type | Supplied judgement | Overlap |", "|---|---|---|---|---|"]
    for row in xenium:
        lines.append(f"| `{row['row_id']}` | {row['citation_number']} | {row['problem_type'].replace('|', '\\|')} | {row['supplied_judgement']} | topic-27..32 |")
    lines += ["", "## Remaining limits", ""] + [f"- {x}" for x in result["limits"]] + [""]
    MD.write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = build()
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))
