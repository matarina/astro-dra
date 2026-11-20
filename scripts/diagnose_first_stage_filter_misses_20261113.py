#!/usr/bin/env python3
"""Offline diagnosis of first-stage span ranks; no external/API calls."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from assess_first_stage_filters_20261113 import _occurrences, lexical_scores, overlap_chunks, terms
from run_multilingual_span_recall_benchmark_20261113 import FIELD_QUERIES, PACK, PACKET, _load_sources, _packet_spans

ROOT = Path(__file__).resolve().parents[1]


def _rank(values, index):
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    return order.index(index) + 1, len(order)


def _score_lexical(chunks, query):
    qterms = terms(query)
    counts = {}
    for chunk in chunks:
        for token in terms(chunk["text"]):
            counts[token] = counts.get(token, 0) + 1
    n = len(chunks)
    return [sum(math.log(1 + n / counts[token]) for token in qterms & terms(chunk["text"]))
            for chunk in chunks]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evaluation/frontier-strategy-20261113/first-stage-filter-miss-diagnosis-20261113.json")
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    sources = {int(s["index"]): s for s in _load_sources(PACK)}
    spans = _packet_spans(json.loads(PACKET.read_text(encoding="utf-8")))
    field_rows = []
    for source_id in (5, 13, 25):
        source = sources[source_id]
        text = str(source.get("fetched_content") or source.get("full_content") or source.get("content") or "")
        chunks = overlap_chunks(text)
        fields = []
        for field, queries in FIELD_QUERIES.items():
            for query in queries:
                fields.append((field, query))
        query_vectors = model.encode(["query: " + query for _, query in fields], normalize_embeddings=True)
        passage_vectors = model.encode(["passage: " + chunk["text"] for chunk in chunks],
                                       normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        e5_by_query = [[float(sum(a * b for a, b in zip(qv, pv))) for pv in passage_vectors]
                        for qv in query_vectors]
        lexical_by_query = [_score_lexical(chunks, query) for _, query in fields]
        source_spans = [span for span in spans if span["source_id"] == source_id]
        for span in source_spans:
            occurrences = _occurrences(text, span["text"])
            containing = [chunk for chunk in chunks for start, end in occurrences
                          if chunk["start"] <= start and end <= chunk["end"]]
            rows = []
            for field_index, (field, query) in enumerate(fields):
                best = None
                for chunk in containing:
                    index = chunk["chunk_id"]
                    e5_rank, total = _rank(e5_by_query[field_index], index)
                    lexical_rank, _ = _rank(lexical_by_query[field_index], index)
                    candidate = {
                        "field": field, "query": query, "chunk_id": index,
                        "chunk_start": chunk["start"], "chunk_end": chunk["end"],
                        "chunk_boundary": chunk["boundary"], "section": chunk["section"],
                        "e5_score": e5_by_query[field_index][index], "e5_rank": e5_rank,
                        "lexical_score": lexical_by_query[field_index][index],
                        "lexical_rank": lexical_rank, "chunk_count": total,
                    }
                    if best is None or (candidate["e5_score"], -candidate["e5_rank"]) > (best["e5_score"], -best["e5_rank"]):
                        best = candidate
                if best is not None:
                    rows.append(best)
            rows.sort(key=lambda item: (-item["e5_score"], item["e5_rank"], item["field"], item["query"]))
            top = rows[0] if rows else None
            field_rows.append({"row_id": span["row_id"], "source_id": source_id,
                               "span_index": span["span_index"], "span_sha256": span["sha256"],
                               "span_length": len(span["text"]),
                               "source_offsets": [{"start": a, "end": b} for a, b in occurrences],
                               "containing_chunk_ids": sorted({c["chunk_id"] for c in containing}),
                               "best_e5": top, "all_field_query_ranks": rows})

    obj = {
        "schema_version": "first_stage_filter_miss_diagnosis.v1",
        "model": args.model, "model_calls": 0,
        "source_pack_sha256": hashlib.sha256(PACK.read_bytes()).hexdigest(),
        "packet_sha256": hashlib.sha256(PACKET.read_bytes()).hexdigest(),
        "chunking": {"chunk_chars": 1800, "overlap_chars": 300,
                     "structure": "same paragraph/heading/sentence chunker as first-stage v2"},
        "field_queries": FIELD_QUERIES,
        "spans": field_rows,
        "limits": ["Ranks diagnose candidate ordering only; they are not entailment or support.",
                    "Packet offsets are used only after generic scoring to locate regression spans.",
                    "The nine spans are not a prevalence estimate and this receipt does not test report usefulness."],
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                      "spans": len(field_rows), "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
