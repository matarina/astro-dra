"""Derive source spans from frozen Evidence Inference annotations.

The raw annotation text, label, offsets and source bytes remain unchanged.
This script records a derived exact-text location only when HTML decoding
produces one unique match in the original distributed article text. It does
not repair or reinterpret the author annotations.
"""
from __future__ import annotations

import argparse
from html import unescape
import hashlib
import json
from pathlib import Path


def occurrences(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    result, start = [], 0
    while True:
        position = text.find(needle, start)
        if position < 0:
            return result
        result.append(position)
        start = position + 1


def reconcile_row(row: dict, body: str) -> dict:
    annotation = row.get("Annotations") or ""
    decoded = unescape(annotation)
    starts = occurrences(body, decoded)
    raw_start = raw_end = None
    try:
        raw_start = int(row.get("Evidence Start"))
        raw_end = int(row.get("Evidence End"))
    except (TypeError, ValueError):
        pass

    derived = {
        "raw_annotation": annotation,
        "decoded_annotation": decoded,
        "raw_evidence_start": raw_start,
        "raw_evidence_end": raw_end,
        "raw_offset_contract": "inclusive_end_preserved",
        "unique_exact_match_count": len(starts),
        "normalized_status": "unknown",
        "normalized_start": None,
        "normalized_end_exclusive": None,
        "declared_inclusive_text": None,
        "declared_half_open_text": None,
    }
    if raw_start is not None and raw_end is not None and 0 <= raw_start <= raw_end < len(body):
        derived["declared_inclusive_text"] = body[raw_start : raw_end + 1]
        derived["declared_half_open_text"] = body[raw_start:raw_end]
    if len(starts) == 1:
        start = starts[0]
        derived.update(
            normalized_status="unique_exact_decoded_annotation",
            normalized_start=start,
            normalized_end_exclusive=start + len(decoded),
        )
    elif not decoded:
        derived["normalized_status"] = "empty_annotation"
    elif len(starts) > 1:
        derived["normalized_status"] = "ambiguous_exact_decoded_annotation"
    else:
        derived["normalized_status"] = "no_exact_decoded_annotation"
    return derived


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    inputs = json.loads((root / "inputs.json").read_text())
    gold = json.loads((root / "reference-gold.json").read_text())
    by_case = {row["case_id"]: row for row in inputs}
    result = {
        "status": "derived_span_ledger_raw_gold_preserved",
        "source_pool": str(root),
        "source_pool_manifest": json.loads((root / "pool-freeze.json").read_text()),
        "normalization": {
            "annotation_text": "html.unescape applied once for matching only",
            "offsets": "raw author offsets retained; derived span uses unique exact text match",
            "source_bytes": "original distributed text read without rewriting",
            "unresolved": "kept unknown and excluded from normalized exact-span counts",
        },
        "cases": [],
    }
    for case in gold:
        input_row = by_case[case["case_id"]]
        source_path = root / input_row["source_text_file"]
        source_bytes = source_path.read_bytes()
        body = source_bytes.decode("utf-8")
        annotations = []
        for item in case.get("annotations", []):
            raw = item.get("annotation") or {}
            annotations.append(
                {
                    "annotation_index": len(annotations),
                    "raw_author_record": raw,
                    "derived_span": reconcile_row(raw, body),
                }
            )
        result["cases"].append(
            {
                "case_id": case["case_id"],
                "article_id": case["article_id"],
                "source_text_file": input_row["source_text_file"],
                "source_text_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "annotations": annotations,
                "majority_author_label_code": case["majority_author_label_code"],
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    counts = {}
    for case in result["cases"]:
        for item in case["annotations"]:
            status = item["derived_span"]["normalized_status"]
            counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"cases": len(result["cases"]), "annotations": sum(counts.values()), "statuses": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
