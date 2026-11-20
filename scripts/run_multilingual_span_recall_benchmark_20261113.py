#!/usr/bin/env python3
"""Offline/isolated multilingual evidence-window recall benchmark.

This benchmark measures whether bounded candidate windows contain predeclared
source offsets.  It does not judge entailment, report quality, or scientific
correctness, and it never writes a report or changes the production source
pool.  The semantic arm is opt-in and requires an injected multilingual
sentence-transformers checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/production-original-sourcepack.json"
PACKET = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/packet.json"

FIELD_QUERIES = {
    "sorting_enrichment": ("分选和富集方法是什么？", "What cell sorting or enrichment method was used?"),
    "assay_platform": ("单细胞实验和测序平台是什么？", "What single-cell assay and sequencing platform were used?"),
    "population_quantity": ("研究对象和样本数量是什么？", "What population and sample quantity were studied?"),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_sources(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("sources", payload) if isinstance(payload, dict) else payload


def _packet_spans(packet: dict):
    rows = []
    for row in packet.get("rows", []):
        for index, span in enumerate(row.get("acquired_method_spans") or []):
            rows.append({
                "row_id": row["row_id"],
                "source_id": int(row["production_source_id"]),
                "span_index": index,
                "text": span["text"],
                "sha256": hashlib.sha256(span["text"].encode()).hexdigest(),
            })
    return rows


def _source_text(source):
    for key in ("fetched_content", "full_content", "content", "abstract", "snippet"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value, key
    return "", "unavailable"


def _run_case(text, field_queries, *, source_id, semantic_ranker, window_chars, max_windows, context_chars):
    from research_verify.evidence_selection import select_request_field_windows

    rows = select_request_field_windows(
        text, field_queries, source_id=source_id, window_chars=window_chars,
        max_windows_per_field=max_windows, context_chars=context_chars,
        semantic_ranker=semantic_ranker,
    )
    windows = []
    for row in rows:
        for window in row.windows:
            windows.append({"field": row.field, "start": window.start, "end": window.end,
                            "method": window.method, "score": window.score,
                            "text_sha256": hashlib.sha256(window.text.encode()).hexdigest()})
    return {"fields": [
        {"field": row.field, "queries": list(row.queries), "status": row.status,
         "window_count": len(row.windows),
         "windows": [{"start": w.start, "end": w.end, "method": w.method,
                      "score": w.score, "text_sha256": hashlib.sha256(w.text.encode()).hexdigest()}
                     for w in row.windows]}
        for row in rows
    ], "windows": windows}


def _coverage(text, spans, result):
    windows = [(w["start"], w["end"]) for w in result["windows"]]
    rows = []
    for span in spans:
        start = text.find(span["text"])
        end = start + len(span["text"]) if start >= 0 else -1
        covered = start >= 0 and any(a <= start and end <= b for a, b in windows)
        rows.append({"row_id": span.get("row_id"), "source_id": span.get("source_id"),
                     "span_index": span.get("span_index"), "source_start": start,
                     "source_end": end, "covered": covered})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "semantic"), default="baseline")
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    parser.add_argument("--out", default="evaluation/frontier-strategy-20261113/multilingual-span-recall-20261113.json")
    parser.add_argument("--window-chars", type=int, default=2000)
    parser.add_argument("--max-windows-per-field", type=int, default=2)
    parser.add_argument("--context-chars", type=int, default=6000)
    args = parser.parse_args()

    sources = {int(s["index"]): s for s in _load_sources(PACK)}
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    spans = _packet_spans(packet)
    selected_ids = sorted({5, 13, 25})
    ranker = None
    model_receipt = {"enabled": False}
    if args.mode == "semantic":
        from sentence_transformers import SentenceTransformer
        from research_verify.semantic_reranker import SentenceTransformerRanker

        model = SentenceTransformer(args.model)
        ranker = SentenceTransformerRanker(model, query_prefix="query: ", passage_prefix="passage: ")
        model_receipt = {"enabled": True, "name": args.model,
                         "query_prefix": "query: ", "passage_prefix": "passage:",
                         "device": str(getattr(model, "device", "unknown"))}

    source_rows = []
    for source_id in selected_ids:
        text, field = _source_text(sources[source_id])
        result = _run_case(text, FIELD_QUERIES, source_id=source_id,
                           semantic_ranker=ranker, window_chars=args.window_chars,
                           max_windows=args.max_windows_per_field,
                           context_chars=args.context_chars)
        source_spans = [span for span in spans if span["source_id"] == source_id]
        source_rows.append({"source_id": source_id, "field": field, "available_chars": len(text),
                            "selection": result, "span_coverage": _coverage(text, source_spans, result)})

    controls = [
        {"control_id": "heldout-cn-en-method", "text": "研究使用流式细胞术分选细胞，随后进行单细胞RNA测序。",
         "field_queries": {"assay": ("采用什么实验方法？", "What assay was used?")},
         "expected": "untranslated English method passage is absent; this control tests original-language text handling"},
        {"control_id": "heldout-en-method", "text": "Peripheral blood cells were sorted by flow cytometry and processed for single-cell RNA sequencing.",
         "field_queries": {"assay": ("采用什么实验方法？", "What assay was used?")},
         "expected_span": "Peripheral blood cells were sorted by flow cytometry and processed for single-cell RNA sequencing."},
        {"control_id": "unrelated-negative", "text": "Weather observations were recorded at three sites; no biological experiment was performed.",
         "field_queries": {"assay": ("采用什么实验方法？", "What assay was used?")},
         "expected": "no assay evidence"},
    ]
    control_rows = []
    for control in controls:
        result = _run_case(control["text"], control["field_queries"], source_id=control["control_id"],
                           semantic_ranker=ranker, window_chars=args.window_chars,
                           max_windows=1, context_chars=1000)
        expected = control.get("expected_span")
        start = control["text"].find(expected) if expected else -1
        covered = bool(expected and any(w["start"] <= start and start + len(expected) <= w["end"]
                                        for w in result["windows"]))
        control_rows.append({"control_id": control["control_id"], "selection": result,
                             "expected_span_present": bool(expected), "expected_span_covered": covered,
                             "expected_note": control.get("expected")})

    receipt = {
        "schema_version": "multilingual_span_recall.v1",
        "mode": args.mode, "model": model_receipt,
        "source_pack": str(PACK), "source_pack_sha256": _sha(PACK),
        "packet_sha256": _sha(PACKET), "source_ids": selected_ids,
        "field_queries": FIELD_QUERIES,
        "budget": {"window_chars": args.window_chars, "max_windows_per_field": args.max_windows_per_field,
                   "context_chars": args.context_chars},
        "source_rows": source_rows, "heldout_controls": control_rows,
        "limits": ["Candidate windows and offset coverage are not entailment or report quality.",
                   "The 9 packet spans are acquired-method annotations, not a prevalence estimate.",
                   "A semantic model result requires equal-budget writer-input and useful-content evaluation."],
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": _sha(out),
                      "mode": args.mode, "spans": len(spans),
                      "covered": sum(item["covered"] for row in source_rows for item in row["span_coverage"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
