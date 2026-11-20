"""Inventory saved job artifacts without models, network or private labels.

This is structural review, not scientific adjudication. Reports are not edited.
Run: PYTHONPATH=local_deep_research python scripts/review_saved_jobs.py --output PATH
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from research_verify.citation_display import cited_indices
from research_verify.evidence import SourceLookup
from research_verify.generation_receipt import output_completeness


ROOT = Path(__file__).resolve().parents[1]


def review(root: Path) -> dict:
    paths = sorted(subprocess.check_output(
        ["rg", "--files", "--hidden", "-g", "!.git", "-g", "!node_modules"],
        cwd=root, text=True).splitlines())
    rows, errors = [], []
    for name in paths:
        path = Path(name)
        # Preserve arm blindness and reserved labels; do not inspect copies
        # made for human review or raw provider reasoning/debug responses.
        if any("private" in part or "blinded-review" in part for part in path.parts):
            continue
        paired = path.parent.name in {"baseline", "candidate"} and path.suffix == ".json"
        if path.name not in {"report.md", "summary.json"} and not paired:
            continue
        raw = (root / path).read_bytes()
        row = {"path": name, "sha256": sha256(raw).hexdigest()}
        try:
            if path.name == "report.md":
                report = raw.decode("utf-8")
                row.update(kind="research_report", chars=len(report),
                           cited_ids=cited_indices(report))
                source_path = root / path.parent / "sources.json"
                if source_path.is_file():
                    source_bytes = source_path.read_bytes()
                    sources = json.loads(source_bytes)
                    if not isinstance(sources, list):
                        raise ValueError("sources must be a list")
                    lookup = SourceLookup(sources)
                    known = {int(s["index"]) for s in lookup.records()}
                    row.update(source_packet_sha256=sha256(source_bytes).hexdigest(),
                               source_records=len(sources),
                               ambiguous_ids=sorted(lookup.ambiguous_indices),
                               unresolved_citation_ids=sorted(set(row["cited_ids"]) - known),
                               uncited_source_ids=sorted(known - set(row["cited_ids"])))
                else:
                    row["source_binding"] = "unavailable"
            else:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    continue
                if paired and "case_id" in data and "output" in data:
                    content = data.get("output")
                    completeness = output_completeness(content, data.get("finish_reason"))
                    row.update(kind="generation", case_id=data["case_id"], arm=path.parent.name,
                               status=data.get("status", "unknown"),
                               finish_reason=data.get("finish_reason"),
                               output_completeness=completeness,
                               output_sha256=sha256((content or "").encode()).hexdigest(),
                               prompt_sha256=data.get("prompt_sha256"),
                               source_packet_sha256=data.get("source_packet_sha256"),
                               completion_not_established=data.get("status") == "completed" and completeness != "complete")
                elif paired and "case_id" in data:
                    row.update(kind="generation_without_output", case_id=data["case_id"],
                               status=data.get("status", "unknown"))
                elif path.name == "summary.json":
                    row.update(kind="summary", summary={k: data[k] for k in (
                        "completed", "failed", "incomplete", "case_count", "source_pool",
                        "references", "report_chars", "research_error") if k in data})
                else:
                    row.update(kind="unrecognized_receipt", status=data.get("status", "unknown"))
            rows.append(row)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            errors.append({**row, "error_type": type(exc).__name__})
    generations = [row for row in rows if row["kind"] == "generation"]
    return {"schema_version": "saved_job_review.v1",
            "scope": "All rg-visible report.md and summary.json files and direct baseline/candidate JSON receipts; private/blinded copies excluded",
            "limitation": "Structural artifact inventory only; historical receipts are immutable; no semantic hallucination score or live-service inventory",
            "counts": dict(Counter(row["kind"] for row in rows)),
            "completeness": dict(Counter(row["output_completeness"] for row in generations)),
            "completed_without_completion_evidence": sum(row["completion_not_established"] for row in generations),
            "truncated_marked_completed": sum(row["status"] == "completed" and row["output_completeness"] == "truncated" for row in generations),
            "artifacts": rows, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("counts", "completeness", "completed_without_completion_evidence", "truncated_marked_completed")}))


if __name__ == "__main__":
    main()
