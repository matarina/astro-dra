#!/usr/bin/env python3
"""No-API first-stage candidate-filter recall audit.

The E5 model is local and opt-in; this script makes no network/model API calls.
Packet offsets are used only after candidate selection to score containment.
``candidate_possible`` is a filter ceiling before budget packing; the
budgeted result is an offset check, not entailment or report quality.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from run_multilingual_span_recall_benchmark_20261113 import FIELD_QUERIES, PACK, PACKET, _load_sources, _packet_spans

ROOT = Path(__file__).resolve().parents[1]


def _is_heading(line: str) -> bool:
    """Recognize structural line boundaries without scientific semantics."""
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if stripped.endswith((".", ";", ",", ":", "。", "；", "，", "：")):
        return False
    words = stripped.split()
    return len(words) <= 12 and (
        stripped.isupper() or len(words) <= 5 or stripped[:1].isdigit()
    )


def _structural_blocks(text: str):
    """Return blank-line paragraphs with section labels and source offsets."""
    blocks, section, cursor = [], None, 0
    paragraph_start = paragraph_section = None

    def flush(end):
        nonlocal paragraph_start, paragraph_section
        if paragraph_start is None:
            return
        raw = text[paragraph_start:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        start, stop = paragraph_start + left, paragraph_start + right
        if start < stop:
            blocks.append({"start": start, "end": stop, "text": text[start:stop],
                           "section": paragraph_section})
        paragraph_start = paragraph_section = None

    for line in text.splitlines(keepends=True):
        line_start = cursor
        cursor += len(line)
        if not line.strip():
            flush(line_start)
            continue
        if _is_heading(line):
            flush(line_start)
            section = line.strip()
            continue
        if paragraph_start is None:
            paragraph_start, paragraph_section = line_start, section
    flush(len(text))
    return blocks


def _sentence_spans(start: int, text: str):
    """Split only at punctuation/whitespace boundaries; retain offsets."""
    spans, begin = [], 0
    for match in re.finditer(r"(?<=[.!?。！？])\s+", text):
        end, part = match.start(), text[begin:match.start()]
        if part.strip():
            left = begin + len(part) - len(part.lstrip())
            right = begin + len(part.rstrip())
            spans.append((start + left, start + right))
        begin = match.end()
    part = text[begin:]
    if part.strip():
        left = begin + len(part) - len(part.lstrip())
        right = begin + len(part.rstrip())
        spans.append((start + left, start + right))
    return spans


def overlap_chunks(text: str, chunk_chars=1800, overlap=300):
    """Create paragraph/section-aware chunks with stable source offsets."""
    rows, chunk_id = [], 0
    for block in _structural_blocks(text):
        start, end = block["start"], block["end"]
        if end - start <= chunk_chars:
            rows.append({"chunk_id": chunk_id, "start": start, "end": end,
                         "text": text[start:end], "section": block["section"],
                         "boundary": "paragraph"})
            chunk_id += 1
            continue
        sentence_spans = _sentence_spans(start, block["text"]) or [(start, end)]
        current = []
        for sentence_start, sentence_end in sentence_spans:
            if sentence_end - sentence_start > chunk_chars:
                if current:
                    a, b = current[0][0], current[-1][1]
                    rows.append({"chunk_id": chunk_id, "start": a, "end": b,
                                 "text": text[a:b], "section": block["section"],
                                 "boundary": "sentence_pack"})
                    chunk_id += 1
                    current = []
                cursor = sentence_start
                while cursor < sentence_end:
                    stop = min(cursor + chunk_chars, sentence_end)
                    rows.append({"chunk_id": chunk_id, "start": cursor, "end": stop,
                                 "text": text[cursor:stop], "section": block["section"],
                                 "boundary": "long_sentence_overlap"})
                    chunk_id += 1
                    if stop == sentence_end:
                        break
                    cursor = stop - min(overlap, max(1, chunk_chars - 1))
                continue
            proposed_start = current[0][0] if current else sentence_start
            if current and sentence_end - proposed_start > chunk_chars:
                a, b = current[0][0], current[-1][1]
                rows.append({"chunk_id": chunk_id, "start": a, "end": b,
                             "text": text[a:b], "section": block["section"],
                             "boundary": "sentence_pack"})
                chunk_id += 1
                current = []
            current.append((sentence_start, sentence_end))
        if current:
            a, b = current[0][0], current[-1][1]
            rows.append({"chunk_id": chunk_id, "start": a, "end": b,
                         "text": text[a:b], "section": block["section"],
                         "boundary": "sentence_pack"})
            chunk_id += 1
    return rows


def terms(text):
    return set(re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*|[\u3400-\u9fff]", text.casefold()))


def lexical_scores(chunks, queries):
    query_terms = set().union(*(terms(q) for q in queries))
    counts = {}
    for chunk in chunks:
        for token in terms(chunk["text"]):
            counts[token] = counts.get(token, 0) + 1
    n = len(chunks)
    return [sum(math.log(1 + n / counts[token]) for token in query_terms & terms(chunk["text"]))
            for chunk in chunks]


def _occurrences(text: str, needle: str):
    if not needle:
        return []
    rows, start = [], 0
    while True:
        at = text.find(needle, start)
        if at < 0:
            return rows
        rows.append((at, at + len(needle)))
        start = at + 1


def span_score(text, spans, windows):
    rows = []
    for span in spans:
        occurrences = _occurrences(text, span["text"])
        covered_offsets, selected_chunk_ids = [], []
        for start, end in occurrences:
            containing = [w for w in windows if w["start"] <= start and end <= w["end"]]
            if containing:
                covered_offsets.append({"start": start, "end": end})
                selected_chunk_ids.extend(w["chunk_id"] for w in containing)
        first = occurrences[0] if occurrences else (-1, -1)
        rows.append({"row_id": span["row_id"], "source_id": span["source_id"],
                     "span_index": span["span_index"], "span_sha256": span["sha256"],
                     "span_length": len(span["text"]), "source_start": first[0],
                     "source_end": first[1], "occurrence_count": len(occurrences),
                     "covered": bool(covered_offsets), "covered_offsets": covered_offsets,
                     "selected_chunk_ids": sorted(set(selected_chunk_ids))})
    return rows


def ranked_indices(chunks, scores, filter_name, k):
    if filter_name == "all":
        return list(range(len(chunks)))
    if filter_name == "union":
        lexical = sorted(range(len(chunks)), key=lambda i: (-scores["lexical"][i], chunks[i]["start"]))[:k]
        semantic = sorted(range(len(chunks)), key=lambda i: (-scores["e5"][i], chunks[i]["start"]))[:k]
        candidates = sorted(set(lexical) | set(semantic),
                           key=lambda i: (-max(scores["lexical"][i], scores["e5"][i]), chunks[i]["start"]))
        return candidates[:k]
    return sorted(range(len(chunks)), key=lambda i: (-scores[filter_name][i], chunks[i]["start"]))[:k]


def choose(chunks, scores, filter_name, k, budget):
    order = ranked_indices(chunks, scores, filter_name, k)
    kept, used, skipped_for_budget, skipped_overlap = [], 0, 0, 0
    for index in order:
        chunk = chunks[index]
        if used + len(chunk["text"]) > budget:
            skipped_for_budget += 1
            continue
        if any(max(0, min(chunk["end"], old["end"]) - max(chunk["start"], old["start"])) >
               0.5 * min(chunk["end"]-chunk["start"], old["end"]-old["start"])
               for old in kept):
            skipped_overlap += 1
            continue
        kept.append(chunk)
        used += len(chunk["text"])
    return kept, {"used_chars": used, "skipped_for_budget": skipped_for_budget,
                   "skipped_overlap": skipped_overlap}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evaluation/frontier-strategy-20261113/first-stage-filter-recall-20261113-v4.json")
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    sources = {int(s["index"]): s for s in _load_sources(PACK)}
    spans = _packet_spans(json.loads(PACKET.read_text(encoding="utf-8")))
    filters = ("all", "lexical", "e5", "union")
    ks = (16, 32, 64)
    budgets = (6000, 12000)
    rows = []
    for source_id in (5, 13, 25):
        source = sources[source_id]
        text = str(source.get("fetched_content") or source.get("full_content") or source.get("content") or "")
        chunks = overlap_chunks(text)
        queries = tuple(value for values in FIELD_QUERIES.values() for value in values)
        lexical = lexical_scores(chunks, queries)
        query_vectors = model.encode(["query: " + query for query in queries], normalize_embeddings=True)
        passage_vectors = model.encode(["passage: " + item["text"] for item in chunks], normalize_embeddings=True,
                                       batch_size=32, show_progress_bar=False)
        e5 = [max(float(sum(a*b for a,b in zip(query_vector, passage))) for query_vector in query_vectors)
              for passage in passage_vectors]
        score_map = {"lexical": lexical, "e5": e5}
        source_spans = [span for span in spans if span["source_id"] == source_id]
        for filter_name in filters:
            for k in ks:
                for budget in budgets:
                    ranked = ranked_indices(chunks, score_map, filter_name, k)
                    # For ``all``, the complete chunk set is the ceiling;
                    # for other filters, the top-K set is the ceiling.
                    possible_windows = [chunks[i] for i in (range(len(chunks)) if filter_name == "all" else ranked)]
                    windows, pack_meta = choose(chunks, score_map, filter_name, k, budget)
                    scored = span_score(text, source_spans, windows)
                    possible = span_score(text, source_spans, possible_windows)
                    rows.append({"source_id": source_id, "chunking": "paragraph_sentence_overlap_300",
                                 "chunk_count": len(chunks), "filter": filter_name, "k": k,
                                 "budget_chars": budget, "candidate_count": len(possible_windows),
                                 "window_count": len(windows), "budget_used_chars": pack_meta["used_chars"],
                                 "skipped_for_budget": pack_meta["skipped_for_budget"],
                                 "skipped_overlap": pack_meta["skipped_overlap"],
                                 "candidate_possible_count": sum(item["covered"] for item in possible),
                                 "candidate_possible_coverage": possible, "span_coverage": scored,
                                 "selected_offsets": [{"chunk_id": w["chunk_id"], "start": w["start"],
                                                       "end": w["end"], "section": w["section"],
                                                       "boundary": w["boundary"]} for w in windows],
                                 "covered_count": sum(item["covered"] for item in scored)})
    controls = []
    # Includes Chinese/English held-out methods, a long method sentence that
    # crosses a naive fixed boundary, and an explicit no-answer negative.
    prefix = "Context " + ("about the study design and cohort. " * 35)
    long_method = ("The investigators sorted peripheral blood cells by flow cytometry and performed "
                   "single-cell RNA sequencing " + ("with preserved sample metadata " * 30) + ".")
    control_cases = (
        ("heldout-cn-en-method", "研究使用流式细胞术分选细胞，随后进行单细胞RNA测序。",
         "研究使用流式细胞术分选细胞，随后进行单细胞RNA测序。", "Chinese method passage."),
        ("heldout-en-method", "Peripheral blood cells were sorted by flow cytometry and processed for single-cell RNA sequencing.",
         "Peripheral blood cells were sorted by flow cytometry and processed for single-cell RNA sequencing.", "Short English method passage."),
        ("heldout-long-method-boundary", "Methods\n\n" + prefix + " " + long_method + "\n\nResults\n\nThe downstream analysis was descriptive.",
         long_method, "Expected span crosses a naive 1800-character boundary."),
        ("no-answer-unrelated", "Weather observations were recorded at three sites; no biological experiment was performed.",
         None, "No method answer; selected windows are false-positive candidates."),
    )
    for control_id, text, expected, note in control_cases:
        c = overlap_chunks(text)
        queries = tuple(value for values in FIELD_QUERIES.values() for value in values)
        lexical = lexical_scores(c, queries)
        qv = model.encode(["query: " + q for q in queries], normalize_embeddings=True)
        pv = model.encode(["passage: " + item["text"] for item in c], normalize_embeddings=True, show_progress_bar=False)
        e5 = [max(float(sum(a*b for a,b in zip(q, p))) for q in qv) for p in pv]
        score_map = {"lexical": lexical, "e5": e5}
        occurrences = _occurrences(text, expected) if expected else []
        expected_start = occurrences[0][0] if occurrences else -1
        naive = [(start, min(start + 1800, len(text))) for start in range(0, len(text), 1800)]
        result_rows = []
        for filter_name in filters:
            for k in ks:
                ranked = ranked_indices(c, score_map, filter_name, k)
                possible = [c[i] for i in (range(len(c)) if filter_name == "all" else ranked)]
                for budget in budgets:
                    selected, meta = choose(c, score_map, filter_name, k, budget)
                    candidate_possible = bool(expected and any(w["start"] <= expected_start and
                                                               expected_start + len(expected) <= w["end"]
                                                               for w in possible))
                    expected_covered = bool(expected and any(w["start"] <= expected_start and
                                                             expected_start + len(expected) <= w["end"]
                                                             for w in selected))
                    result_rows.append({"filter": filter_name, "k": k, "budget_chars": budget,
                                        "candidate_count": len(possible), "window_count": len(selected),
                                        "budget_used_chars": meta["used_chars"],
                                        "candidate_possible": candidate_possible,
                                        "expected_covered": expected_covered,
                                        "false_positive_window_count": 0 if expected else len(selected),
                                        "selected_offsets": [{"chunk_id": w["chunk_id"], "start": w["start"],
                                                              "end": w["end"], "section": w["section"],
                                                              "boundary": w["boundary"]} for w in selected]})
        controls.append({"control_id": control_id, "expected_span": bool(expected),
                         "expected_occurrences": [{"start": a, "end": b} for a, b in occurrences],
                         "expected_length": len(expected or ""),
                         "naive_fixed_chunk_covered": bool(expected and any(a <= expected_start and
                             expected_start + len(expected) <= b for a, b in naive)),
                         "structural_chunk_covered": bool(expected and any(w["start"] <= expected_start and
                             expected_start + len(expected) <= w["end"] for w in c)),
                         "structural_chunk_count": len(c), "results": result_rows, "note": note})
    obj = {"schema_version":"first_stage_filter_recall.v2","model":args.model,
           "source_pack_sha256":hashlib.sha256(PACK.read_bytes()).hexdigest(),
           "packet_sha256":hashlib.sha256(PACKET.read_bytes()).hexdigest(),
           "filters":filters,"ks":ks,"budgets":budgets,"rows":rows,"controls":controls,
           "k_semantics":{"all":"complete_chunk_set; k retained for grid comparability",
                          "lexical":"top_k","e5":"top_k","union":"top_k_union_capped_to_k"},
           "model_calls":0,
           "chunking":{"chunk_chars":1800,"overlap_chars":300,
                       "structure":"blank-separated paragraphs, line headings, sentence packing for long paragraphs",
                       "offsets":"candidate and selected windows retain source start/end offsets"},
           "limits":["E5 is local CPU inference; no network or model API calls.",
                    "candidate_possible is a filter ceiling, not a reranker result or entailment.",
                    "budgeted coverage is order-dependent packing and not report quality.",
                    "The nine annotated spans are a regression set, not a prevalence estimate."]}
    out=ROOT/args.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({"out":str(out),"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"rows":len(rows)},ensure_ascii=False))

if __name__ == "__main__": main()
