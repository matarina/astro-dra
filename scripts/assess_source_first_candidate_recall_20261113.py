#!/usr/bin/env python3
"""Measure source-first candidate recall before paying for LLM ranking.

The packet offsets are used only after candidate generation to score whether
the high-recall chunk set contains the annotated spans. No annotations or
feedback labels are passed into a selection prompt, and this script makes no
model calls.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from run_source_first_field_probe_20261113 import PACK, PACKET, chunks, load_sources, packet_spans, sha

ROOT = Path(__file__).resolve().parents[1]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ids", default="5,13,25")
    parser.add_argument("--chunk-chars", type=int, default=1800)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--field-count", type=int, default=3)
    parser.add_argument("--out", default="evaluation/frontier-strategy-20261113/source-first-candidate-recall-20261113.json")
    args = parser.parse_args()
    source_rows = load_sources()
    target_ids = [int(value) for value in args.source_ids.split(",")]
    spans = packet_spans()
    rows = []
    total_batches = 0
    for source_id in target_ids:
        source = source_rows[source_id]
        text = str(source.get("fetched_content") or source.get("full_content")
                   or source.get("content") or source.get("abstract") or "")
        all_chunks = chunks(text, chunk_chars=args.chunk_chars)
        candidate_windows = [(start, end) for start, end, _ in all_chunks]
        total_batches += math.ceil(len(all_chunks) / args.batch_size) * args.field_count
        source_spans = [span for span in spans if span["source_id"] == source_id]
        scored = []
        for span in source_spans:
            start = text.find(span["text"])
            end = start + len(span["text"]) if start >= 0 else -1
            scored.append({"row_id": span["row_id"], "source_id": source_id,
                           "span_index": span["span_index"], "source_start": start,
                           "candidate_contained": start >= 0 and any(a <= start and end <= b
                                                                       for a, b in candidate_windows)})
        rows.append({"source_id": source_id, "available_chars": len(text),
                     "chunk_count": len(all_chunks), "candidate_mode": "all_chunks",
                     "candidate_count": len(candidate_windows), "span_coverage": scored})
    obj = {
        "schema_version": "source_first_candidate_recall.v1",
        "source_pack": str(PACK), "source_pack_sha256": sha(PACK),
        "packet_sha256": sha(PACKET), "source_ids": target_ids,
        "chunk_chars": args.chunk_chars, "batch_size": args.batch_size,
        "field_count": args.field_count, "model_calls": 0,
        "estimated_llm_ranker_calls_if_all_chunks": total_batches,
        "rows": rows,
        "limits": ["Offset annotations are used only for post-selection scoring.",
                   "All-chunk candidate recall does not establish ranking precision, entailment or report quality.",
                   "The estimated paid-call count must be weighed against a defensible high-recall prefilter before execution."],
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    covered = sum(item["candidate_contained"] for row in rows for item in row["span_coverage"])
    total = sum(len(row["span_coverage"]) for row in rows)
    print(json.dumps({"out": str(out), "sha256": sha(out), "covered": covered,
                      "total": total, "estimated_calls": total_batches}, ensure_ascii=False))


if __name__ == "__main__":
    main()
