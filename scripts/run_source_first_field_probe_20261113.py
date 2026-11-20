#!/usr/bin/env python3
"""Bounded source-first field ranking probe with literal offset validation.

The model sees only generic request-derived field questions and bounded source
chunks. Feedback annotations, report claims and reviewer labels never enter the
ranking prompt. The packet is loaded after model calls only to score whether
predeclared acquired spans were visible; this is a retrieval diagnostic, not a
support verdict or report rewrite.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/production-original-sourcepack.json"
PACKET = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence/packet.json"

FIELD_QUESTIONS = {
    "sorting_enrichment": "原文报告了什么细胞分选或富集方法？ Translation: What cell sorting or enrichment method does the source report?",
    "assay_platform": "原文报告了什么单细胞实验和测序平台？ Translation: What single-cell assay and sequencing platform does the source report?",
    "population_quantity": "原文报告了什么研究对象、样本或细胞数量？ Translation: What population, sample or cell quantity does the source report?",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources():
    payload = json.loads(PACK.read_text(encoding="utf-8"))
    rows = payload.get("sources", payload) if isinstance(payload, dict) else payload
    return {int(row["index"]): row for row in rows}


def chunks(text: str, *, chunk_chars: int = 1800):
    """Make bounded original-text chunks with absolute offsets."""
    rows = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.S):
        start, end = match.span()
        if end - start <= chunk_chars:
            rows.append((start, end, text[start:end]))
            continue
        cursor = start
        while cursor < end:
            stop = min(cursor + chunk_chars, end)
            rows.append((cursor, stop, text[cursor:stop]))
            cursor = stop
    return rows


def structural_chunks(text: str, *, chunk_chars: int = 1800):
    """Use the audited paragraph/heading/sentence chunker with tuple offsets."""
    from assess_first_stage_filters_20261113 import overlap_chunks
    return [(row["start"], row["end"], row["text"]) for row in overlap_chunks(text, chunk_chars=chunk_chars)]


def evenly_bounded(items, maximum):
    if maximum <= 0 or len(items) <= maximum:
        return list(range(len(items)))
    return sorted(set(round(i * (len(items) - 1) / max(1, maximum - 1))
                    for i in range(maximum)))


def parse_scores(raw, count):
    content = getattr(raw, "content", raw)
    if not isinstance(content, str):
        raise ValueError("ranker response is not text")
    obj = json.loads(content.strip())
    rankings = obj.get("rankings") if isinstance(obj, dict) else obj
    if not isinstance(rankings, list):
        raise ValueError("ranker response has no rankings")
    scores = [None] * count
    for item in rankings:
        if not isinstance(item, dict):
            raise ValueError("ranking item is not an object")
        index, score = item.get("index"), item.get("score")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            raise ValueError("ranking index invalid")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            raise ValueError("ranking score invalid")
        if scores[index] is not None:
            raise ValueError("duplicate ranking index")
        scores[index] = float(score)
    if any(score is None for score in scores):
        raise ValueError("ranking incomplete")
    return [float(score) for score in scores]


def packet_spans():
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    rows = []
    for row in packet.get("rows", []):
        for index, span in enumerate(row.get("acquired_method_spans") or []):
            rows.append({"row_id": row["row_id"], "source_id": int(row["production_source_id"]),
                         "span_index": index, "text": span["text"]})
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evaluation/frontier-strategy-20261113/source-first-field-probe-20261113.json")
    parser.add_argument("--source-ids", default="5,13,25")
    parser.add_argument("--chunk-chars", type=int, default=1800)
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--candidate-filter", choices=("uniform", "all", "e5", "lexical"), default="uniform")
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-windows-per-field", type=int, default=2)
    parser.add_argument("--context-chars", type=int, default=6000)
    args = parser.parse_args()

    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm

    defaults = Path("/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json")
    values = json.loads(defaults.read_text())
    snapshot = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in values.items()})
    snapshot.update({"llm.provider": "openai_endpoint", "llm.model": "deepseek-v4-flash",
                     "llm.temperature": 0, "llm.max_tokens": 1200,
                     "llm.request_timeout": 120, "llm.max_retries": 1})
    source_rows = load_sources()
    target_ids = [int(value) for value in args.source_ids.split(",")]
    spans = packet_spans()
    calls = []
    selections = []

    local_prefilter = None
    if args.candidate_filter == "e5":
        from sentence_transformers import SentenceTransformer
        local_prefilter = SentenceTransformer(args.model if hasattr(args, "model") else "intfloat/multilingual-e5-small")

    def setting(key, default=None):
        return snapshot.get(key, default)

    with settings_context(type("Settings", (), {"username": None, "get_setting": staticmethod(setting)})()):
        model = get_llm(settings_snapshot=snapshot)
        for source_id in target_ids:
            source = source_rows[source_id]
            text = str(source.get("fetched_content") or source.get("full_content")
                       or source.get("content") or source.get("abstract") or "")
            all_chunks = structural_chunks(text, chunk_chars=args.chunk_chars)
            prefilter_scores = None
            if args.candidate_filter == "all":
                candidate_indices = list(range(len(all_chunks)))
            elif args.candidate_filter == "e5":
                # Local embedding prefilter only; it never supplies a support
                # verdict and the paid ranker still sees original text.
                query_texts = list(FIELD_QUESTIONS.values())
                qv = local_prefilter.encode(["query: " + q for q in query_texts], normalize_embeddings=True)
                pv = local_prefilter.encode(["passage: " + row[2] for row in all_chunks],
                                            normalize_embeddings=True, batch_size=32, show_progress_bar=False)
                prefilter_scores = [max(float(sum(a * b for a, b in zip(q, p))) for q in qv) for p in pv]
                candidate_indices = sorted(range(len(all_chunks)),
                                           key=lambda i: (-prefilter_scores[i], all_chunks[i][0]))[:args.max_candidates]
            elif args.candidate_filter == "lexical":
                query_terms = set().union(*(re.findall(r"[A-Za-z0-9]+|[\u3400-\u9fff]", q.casefold())
                                            for q in FIELD_QUESTIONS.values()))
                candidate_indices = sorted(range(len(all_chunks)),
                                           key=lambda i: (-sum(token in all_chunks[i][2].casefold() for token in query_terms), all_chunks[i][0]))[:args.max_candidates]
            else:
                candidate_indices = evenly_bounded(all_chunks, args.max_candidates)
            candidate_rows = [all_chunks[index] for index in candidate_indices]
            field_rows = []
            for field, question in FIELD_QUESTIONS.items():
                scores_by_index = {}
                failures = []
                for begin in range(0, len(candidate_rows), args.batch_size):
                    batch = candidate_rows[begin:begin + args.batch_size]
                    prompt = (
                        "Rank original source passages for relevance to the request field.\n"
                        "Relevance only; do not decide support, infer facts, rewrite claims or cite feedback. "
                        "Return strict JSON {\"rankings\":[{\"index\":0,\"score\":0.0}]} for every supplied index.\n"
                        f"REQUEST FIELD\n{question}\n\n" +
                        "\n\n".join(f"PASSAGE {i}\n{row[2]}" for i, row in enumerate(batch))
                    )
                    started = time.monotonic()
                    try:
                        response = model.invoke(prompt)
                        scores = parse_scores(response, len(batch))
                        metadata = getattr(response, "response_metadata", {}) or {}
                        calls.append({"source_id": source_id, "field": field,
                                      "candidate_count": len(batch), "prompt_chars": len(prompt),
                                      "elapsed_s": round(time.monotonic() - started, 3),
                                      "status": "completed", "token_usage": metadata.get("token_usage")})
                        for index, score in enumerate(scores):
                            scores_by_index[begin + index] = score
                    except Exception as exc:
                        calls.append({"source_id": source_id, "field": field,
                                      "candidate_count": len(batch), "prompt_chars": len(prompt),
                                      "elapsed_s": round(time.monotonic() - started, 3),
                                      "status": "failed", "error_type": type(exc).__name__,
                                      "error": str(exc)[:300]})
                        failures.append(type(exc).__name__)
                ranked = sorted(scores_by_index, key=lambda index: (-scores_by_index[index], candidate_rows[index][0]))
                selected = []
                used = 0
                for index in ranked:
                    start, end, value = candidate_rows[index]
                    if len(selected) >= args.max_windows_per_field or used + len(value) > args.context_chars // len(FIELD_QUESTIONS):
                        continue
                    if any(max(0, min(end, old["end"]) - max(start, old["start"])) > 0.5 * min(end - start, old["end"] - old["start"]) for old in selected):
                        continue
                    selected.append({"start": start, "end": end, "score": scores_by_index[index],
                                     "text_sha256": hashlib.sha256(value.encode()).hexdigest()})
                    used += len(value)
                field_rows.append({"field": field, "question": question,
                                   "candidate_chunks": len(candidate_rows),
                                   "candidate_indices": candidate_indices,
                                   "selected": selected, "failures": failures})
            selections.append({"source_id": source_id, "available_chars": len(text),
                               "chunk_count": len(all_chunks), "candidate_count": len(candidate_rows),
                               "candidate_filter": args.candidate_filter,
                               "candidate_indices": candidate_indices,
                               "prefilter_score_range": ([min(prefilter_scores), max(prefilter_scores)]
                                                           if prefilter_scores else None),
                               "fields": field_rows})

    scored_spans = []
    for span in spans:
        if span["source_id"] not in target_ids:
            continue
        text = str(source_rows[span["source_id"]].get("fetched_content") or source_rows[span["source_id"]].get("full_content") or source_rows[span["source_id"]].get("content") or "")
        start = text.find(span["text"])
        windows = [window for selection in selections if selection["source_id"] == span["source_id"] for field in selection["fields"] for window in field["selected"]]
        scored_spans.append({**{key: span[key] for key in ("row_id", "source_id", "span_index")},
                             "source_start": start,
                             "covered": start >= 0 and any(window["start"] <= start and start + len(span["text"]) <= window["end"] for window in windows)})
    receipt = {"schema_version": "source_first_field_probe.v2", "source_pack": str(PACK),
               "source_pack_sha256": sha(PACK), "packet_sha256": sha(PACKET),
               "field_questions": FIELD_QUESTIONS, "source_ids": target_ids,
               "chunk_chars": args.chunk_chars, "max_candidates": args.max_candidates,
               "candidate_filter": args.candidate_filter,
               "batch_size": args.batch_size, "max_windows_per_field": args.max_windows_per_field,
               "context_chars": args.context_chars, "selections": selections,
               "span_coverage": scored_spans, "calls": calls,
               "limits": ["Model ranking is relevance only; literal quotes and offsets are validated offline.",
                          "Feedback annotations and report claims are excluded from ranking prompts.",
                          "Candidate passage visibility is not support, entailment, report usefulness or hallucination reduction."]}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": sha(out), "calls": len(calls),
                      "completed": sum(call["status"] == "completed" for call in calls),
                      "span_covered": sum(item["covered"] for item in scored_spans)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
