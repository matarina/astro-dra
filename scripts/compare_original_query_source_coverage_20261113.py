#!/usr/bin/env python3
"""Compare legacy and canonical verifier source visibility on the original pack.

This is an offline input-boundary diagnostic.  It uses the exact original task
text and an unannotated 60-source pack, but does not call a model, select
reviewer-labelled passages, or score a report.  A visible method span is only
an input-visibility result, not an entailment or usefulness judgment.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/packet.json"
PACK = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/production-original-sourcepack.json"
OUT = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/original-query-coverage-20261113.json"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_runner():
    path = ROOT / "scripts/run_hallucination_next_phase_experiment_20261113.py"
    spec = importlib.util.spec_from_file_location("next_phase_runner_for_coverage", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def legacy_text(source: dict) -> tuple[str, str]:
    """The historical verifier adapter, retained only as a diagnostic baseline."""
    for field in ("abstract", "full_content", "content", "snippet"):
        value = source.get(field)
        if isinstance(value, str) and value.strip():
            return value, field
    return "", "none"


def main() -> int:
    packet = json.loads(PACKET.read_text())
    sources = json.loads(PACK.read_text())["sources"]
    runner = load_runner()
    rows = []
    by_id = {str(s.get("index")): s for s in sources}
    for source in sources:
        old, old_field = legacy_text(source)
        canonical = runner._passages([source])
        if canonical:
            passage = canonical[0]
            new, new_field, new_scope = passage.text, passage.field, passage.scope_note
        else:
            new, new_field, new_scope = "", "none", "no canonical material"
        rows.append({
            "source_id": str(source.get("index")),
            "title": source.get("title", ""),
            "legacy_field": old_field,
            "legacy_chars": len(old),
            "legacy_sha256": sha(old),
            "canonical_field": new_field,
            "canonical_scope": new_scope,
            "canonical_chars": len(new),
            "canonical_sha256": sha(new),
            "canonical_added_chars": max(0, len(new) - len(old)),
        })

    span_rows = []
    for item in packet["rows"]:
        source = by_id.get(str(item["production_source_id"]), {})
        old, old_field = legacy_text(source)
        canonical = runner._passages([source])
        new = canonical[0].text if canonical else ""
        spans = item.get("acquired_method_spans") or []
        span_rows.append({
            "row_id": item["row_id"],
            "production_source_id": str(item["production_source_id"]),
            "original_pdf_citation_id": item["original_pdf_citation_id"],
            "acquired_span_count": len(spans),
            "legacy_field": old_field,
            "legacy_chars": len(old),
            "canonical_chars": len(new),
            "legacy_span_visible": [bool(span.get("text") and span["text"] in old) for span in spans],
            "canonical_span_visible": [bool(span.get("text") and span["text"] in new) for span in spans],
            "span_sha256": [sha(str(span.get("text") or "")) for span in spans],
            "interpretation": "input visibility only; not support, entailment, or report usefulness",
        })

    original_query = (
        "目前关注嗜酸性粒细胞、嗜碱性粒细胞、肥大细胞、T细胞，针对于这些细胞，进行单细胞转录组测序，"
        "应该如何进行实验方案，提供文献中是否有能力去对目的细胞进行分选、富集及后续的单细胞实验文章，"
        "提取文章中的文选方案，单细胞测序平台，以及如此多的细胞如何分选？"
    )
    result = {
        "schema_version": "original_query_source_coverage.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_id": packet["task_id"],
        "original_query": original_query,
        "original_query_sha256": sha(original_query),
        "packet_sha256": sha(PACKET.read_text()),
        "sourcepack_sha256": sha(PACK.read_text()),
        "source_count": len(sources),
        "source_rows": rows,
        "feedback_rows": span_rows,
        "summary": {
            "legacy_total_chars": sum(x["legacy_chars"] for x in rows),
            "canonical_total_chars": sum(x["canonical_chars"] for x in rows),
            "legacy_sources_with_fetched_content_visible": sum(
                x["legacy_field"] == "fetched_content" for x in rows
            ),
            "canonical_sources_with_fetched_content_field": sum(
                "fetched_content" in x["canonical_field"] for x in rows
            ),
            "feedback_rows_with_acquired_spans": sum(bool(x["acquired_span_count"]) for x in span_rows),
            "feedback_rows_all_acquired_spans_visible_legacy": sum(
                bool(x["acquired_span_count"]) and all(x["legacy_span_visible"]) for x in span_rows
            ),
            "feedback_rows_all_acquired_spans_visible_canonical": sum(
                bool(x["acquired_span_count"]) and all(x["canonical_span_visible"]) for x in span_rows
            ),
        },
        "scope": {
            "request_text_is_preserved": True,
            "request_derived_questions_executed": False,
            "semantic_selection_executed": False,
            "reviewer_annotations_used": False,
            "report_generation_or_model_calls": False,
            "limits": [
                "Canonical source visibility is upstream of writer budget and selection; it does not prove the writer received every span.",
                "The six packet spans are supervisor annotations used only for offline validation, not generation inputs.",
                "No scientific support, contradiction, omission correction, usefulness, or hallucination-rate claim is made.",
            ],
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "summary": result["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
