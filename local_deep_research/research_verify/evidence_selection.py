"""Shared bounded evidence-window selection.

Selection is a context-retrieval operation.  It preserves source offsets and
explicitly reports no lexical match; it never decides whether a claim is true.
Paragraph/heading structure is used first, with lexical ranking only as a
transparent bounded hint.  An explicitly injected semantic ranker can reorder
the same windows, while offsets, raw text and bounded structural anchors are
still owned by the application.  Selection never decides whether a claim is
true.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Callable, Mapping, Sequence

from .coverage_planner import CoverageCandidate, plan_coverage
from .evidence_cards import build_passage_card


_REFERENCES = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:references|bibliography|参考文献)\s*:?\s*$"
)


@dataclass(frozen=True)
class EvidenceWindow:
    start: int
    end: int
    text: str
    score: float
    method: str
    lexical_match: bool
    # A model/ranker score is bookkeeping only.  It is never a support
    # verdict and may be absent when the opt-in ranker is unavailable.
    ranker_score: float | None = None


@dataclass(frozen=True)
class EvidenceGapSelection:
    """A bounded answer-seeking selection for one factual follow-up question.

    ``status`` describes availability of candidate text, not whether the text
    supports the question.  ``unresolved`` is retained when no supplied or
    follow-up text was available; callers must not turn that state into a
    scientific negative claim.
    """

    question: str
    source_id: str | int | None
    basis: str
    status: str
    windows: tuple[EvidenceWindow, ...]
    source_text: str = ""
    source_text_sha256: str = ""


@dataclass(frozen=True)
class RequestFieldSelection:
    """Bounded candidate windows for one requested report field.

    ``queries`` may contain the original-language wording and independently
    supplied translations or paraphrases.  The selector preserves offsets in
    the original source text and reports candidate availability only; it never
    infers support, entailment, or a missing scientific fact.
    """

    field: str
    queries: tuple[str, ...]
    source_id: str | int | None
    status: str
    windows: tuple[EvidenceWindow, ...]
    source_text: str = ""
    passage_cards: tuple[dict[str, Any], ...] = ()


def select_request_field_windows(
    text: str,
    field_queries: Mapping[str, str | Sequence[str]],
    *,
    source_id: str | int | None = None,
    window_chars: int = 1600,
    max_windows_per_field: int = 2,
    context_chars: int | None = None,
    semantic_ranker: Callable[..., Any] | Any | None = None,
    adjacent_windows: bool = False,
) -> tuple[RequestFieldSelection, ...]:
    """Select source windows for multiple request fields with a shared budget.

    Each field receives a first bounded opportunity before remaining budget is
    allocated by score.  Query variants are kept explicit so a caller can
    compare original-language and translated wording without hiding the
    translation or treating lexical overlap as semantic evidence.  Windows
    retain their exact source coordinates and are deduplicated by offset.
    """
    if window_chars < 32 or max_windows_per_field < 1:
        raise ValueError("invalid request-field evidence-window budget")
    if not isinstance(field_queries, Mapping):
        raise TypeError("field_queries must be a mapping")
    if not isinstance(text, str) or not text:
        return tuple(RequestFieldSelection(str(field), (), source_id, "unresolved", (), text, ())
                     for field in field_queries)
    fields = []
    for raw_field, raw_queries in field_queries.items():
        field = str(raw_field)
        values = (raw_queries,) if isinstance(raw_queries, str) else tuple(raw_queries or ())
        queries = tuple(str(value).strip() for value in values if str(value).strip())
        fields.append((field, queries))
    if not fields:
        return ()
    total_budget = context_chars if context_chars is not None else (
        window_chars * max_windows_per_field * len(fields)
    )
    if total_budget < 1:
        return tuple(RequestFieldSelection(field, queries, source_id, "unresolved", (), text, ())
                     for field, queries in fields)

    # Collect candidates independently for each field/variant.  The source
    # offsets are owned by select_context_windows, so translated wording never
    # changes citation identity or coordinates.
    candidates: list[tuple[str, tuple[str, ...], list[EvidenceWindow]]] = []
    per_field_budget = max(1, total_budget // len(fields))
    if adjacent_windows:
        # Adjacent windows intentionally span paragraph boundaries and may be
        # wider than a single paragraph. Do not discard every such candidate
        # merely because the shared budget divided by field count is smaller
        # than one window; the global coverage plan enforces the real limit.
        per_field_budget = max(window_chars * max_windows_per_field, per_field_budget)
    for field, queries in fields:
        by_offset: dict[tuple[int, int], EvidenceWindow] = {}
        for query in queries:
            windows = select_context_windows(
                text, query, window_chars=window_chars,
                max_windows=max_windows_per_field,
                overlap_chars=min(200, window_chars - 1),
                context_chars=per_field_budget,
                semantic_ranker=semantic_ranker,
                adjacent_windows=adjacent_windows,
            )
            # A structural sample is useful as an explicit diagnostic, but it
            # is not request-field coverage when neither lexical nor semantic
            # relevance exists. Keep the zero-match state visible.
            if semantic_ranker is None:
                windows = tuple(window for window in windows
                                if window.method != "structural_sample_no_lexical_match")
            for window in windows:
                key = (window.start, window.end)
                previous = by_offset.get(key)
                if previous is None or window.score > previous.score:
                    by_offset[key] = window
        ordered = sorted(by_offset.values(), key=lambda item: (-item.score, item.start))
        candidates.append((field, queries, ordered))

    coverage_candidates = [
        CoverageCandidate(
            source_id=source_id, start=window.start, end=window.end,
            text=window.text, fields=(field,), score=window.score,
            method=window.method, lexical_match=window.lexical_match,
            ranker_score=window.ranker_score,
        )
        for field, _, windows in candidates for window in windows
    ]
    plan = plan_coverage(
        coverage_candidates, [field for field, _ in fields],
        context_chars=total_budget,
        min_sources=1 if source_id is not None else 0,
        max_items=max_windows_per_field * len(fields),
    )
    selected: dict[str, list[EvidenceWindow]] = {field: [] for field, _ in fields}
    for item in plan.selected:
        field = item.fields[0] if item.fields else ""
        if field in selected and len(selected[field]) < max_windows_per_field:
            selected[field].append(EvidenceWindow(
                item.start, item.end, item.text, item.score,
                item.method, item.lexical_match, item.ranker_score,
            ))

    return tuple(
        RequestFieldSelection(
            field=field,
            queries=queries,
            source_id=source_id,
            status="candidate_passages" if selected[field] else "unresolved",
            windows=tuple(sorted(selected[field], key=lambda item: item.start)),
            source_text=text,
            passage_cards=tuple(
                build_passage_card(
                    source_id, text, item.start, item.end, item.text,
                    field=field, method=item.method, score=item.score,
                    lexical_match=item.lexical_match,
                )
                for item in sorted(selected[field], key=lambda item: item.start)
            ),
        )
        for field, queries in fields
    )


def _terms(text: str, *, compound_terms: bool = False) -> set[str]:
    """Tokenize for retrieval only; this function carries no topic meaning."""
    out = set(re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*|[\u3400-\u9fff]", text.casefold()))
    if compound_terms:
        # Retrieval hint only: retain the complete token AND hyphen parts.
        # No numeric conversion, scientific synonym or semantic equivalence.
        out |= {part for token in tuple(out) for part in token.split('-') if part}
    return out


def _paragraphs(text: str, end: int):
    boundaries = [0]
    boundaries.extend(m.end() for m in re.finditer(r"\n\s*\n", text[:end]))
    finishes = [m.start() for m in re.finditer(r"\n\s*\n", text[:end])] + [end]
    for begin, finish in zip(boundaries, finishes):
        while begin < finish and text[begin].isspace():
            begin += 1
        while finish > begin and text[finish - 1].isspace():
            finish -= 1
        if begin < finish:
            yield begin, finish


def _semantic_scores(
    ranker: Callable[..., Any] | Any,
    query: str,
    candidates: Sequence[tuple[int, int, str]],
    *,
    error_sink: list[dict[str, str]] | None = None,
) -> list[float] | None:
    """Call an injected semantic ranker with strict, non-semantic parsing.

    The ranker is deliberately an interface, not a hidden keyword heuristic:
    it may be a cross-encoder/embedding service or an LLM-based scorer owned by
    the caller.  We accept either a sequence of numeric scores aligned with
    candidates or ``[{"index": i, "score": value}, ...]``.  Malformed,
    incomplete or non-finite output returns ``None`` so the existing bounded
    selector remains the transparent fallback.
    """
    def fail(reason: str):
        if error_sink is not None:
            error_sink.append({"error_type": "ValueError", "error": reason})
        return None

    try:
        if hasattr(ranker, "rank"):
            raw = ranker.rank(query, [item[2] for item in candidates])
        else:
            raw = ranker(query, [item[2] for item in candidates])
    except Exception as exc:
        if error_sink is not None:
            error_sink.append({"error_type": type(exc).__name__, "error": str(exc)[:300]})
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return fail("ranker_response_not_sequence")
    scores: list[float | None] = [None] * len(candidates)
    if len(raw) == len(candidates) and all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in raw
    ):
        scores = [float(item) for item in raw]
    elif all(isinstance(item, Mapping) for item in raw):
        for item in raw:
            index, score = item.get("index"), item.get("score")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(candidates):
                return fail("ranking_index_invalid")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                return fail("ranking_score_invalid")
            if scores[index] is not None:
                return fail("ranking_scores_duplicate_or_incomplete")
            scores[index] = float(score)
        if any(score is None for score in scores):
            return fail("ranking_scores_incomplete")
    else:
        return fail("ranking_output_shape_invalid")
    if not all(math.isfinite(score) for score in scores if score is not None):
        return fail("ranking_score_non_finite")
    return [float(score) for score in scores]  # type: ignore[arg-type]


def select_context_windows(text: str, query: str, *, window_chars: int,
                           max_windows: int, overlap_chars: int = 200,
                           context_chars: int | None = None,
                           semantic_ranker: Callable[..., Any] | Any | None = None,
                           selection_receipts: list[dict[str, Any]] | None = None,
                           adjacent_windows: bool = False,
                           compound_terms: bool = False,
                           ) -> tuple[EvidenceWindow, ...]:
    if window_chars < 32 or max_windows < 1 or not 0 <= overlap_chars < window_chars:
        raise ValueError("invalid evidence-window budget")
    if not isinstance(text, str) or not text:
        return ()
    cutoff = _REFERENCES.search(text)
    eligible_end = cutoff.start() if cutoff else len(text)
    candidates = []
    paragraphs = list(_paragraphs(text, eligible_end))
    for begin, finish in paragraphs:
        if adjacent_windows:
            # A factual passage can begin in one paragraph and finish in the
            # next. Keep one bounded window from each paragraph start so the
            # complete span can be selected without merging source bytes or
            # changing the default paragraph-local selector.
            end = min(begin + window_chars, eligible_end)
            candidates.append((begin, end, text[begin:end]))
            if finish - begin <= window_chars:
                continue
            start = begin + window_chars - overlap_chars
            while start < finish:
                end = min(start + window_chars, finish)
                candidates.append((start, end, text[start:end]))
                if end == finish:
                    break
                start = end - overlap_chars
            continue
        start = begin
        while start < finish:
            end = min(start + window_chars, finish)
            candidates.append((start, end, text[start:end]))
            if end == finish:
                break
            start = end - overlap_chars
    if not candidates:
        if selection_receipts is not None:
            selection_receipts.append({
                "schema_version": "evidence_selection_receipt.v1",
                "candidate_count": 0,
                "candidate_offsets": [],
                "selected_offsets": [],
                "method": "no_candidates",
                "lexical_match": False,
                "semantic_ranker_injected": semantic_ranker is not None,
                "ranker_errors": [],
                "context_chars": 0,
                "context_sha256": hashlib.sha256(b"").hexdigest(),
            })
        return ()
    query_terms = _terms(query, compound_terms=compound_terms)
    term_sets = [_terms(item[2], compound_terms=compound_terms) for item in candidates]
    counts = Counter(term for terms in term_sets for term in terms)
    scores = [sum(math.log(1 + len(candidates) / counts[t]) for t in query_terms & terms)
              for terms in term_sets]
    matched = any(score > 0 for score in scores)
    ranker_errors: list[dict[str, str]] = []
    semantic_scores = (
        _semantic_scores(semantic_ranker, query, candidates, error_sink=ranker_errors)
        if semantic_ranker is not None else None
    )
    structural_anchor_indices: list[int] = []
    if semantic_scores is not None:
        # Reserve half of the bounded windows for evenly spaced structural
        # anchors. This keeps high-relevance passages while retaining generic
        # coverage of long sources whose decisive paragraph may rank poorly.
        ranked_order = sorted(range(len(candidates)),
                              key=lambda i: (-semantic_scores[i], -scores[i], candidates[i][0]))
        anchor_count = min(max_windows // 2, len(candidates))
        if anchor_count:
            structural_anchor_indices = [
                round(i * (len(candidates) - 1) / max(1, anchor_count - 1))
                for i in range(anchor_count)
            ]
        order = ranked_order[:max_windows - anchor_count] + structural_anchor_indices
        method = "semantic_ranker_with_structural_anchors"
    elif matched:
        order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i][0]))
        method = "lexical_hint_with_structural_anchors"
    else:
        count = min(max_windows, len(candidates))
        order = [round(i * (len(candidates) - 1) / max(1, count - 1)) for i in range(count)]
        method = "structural_sample_no_lexical_match"
    budget = context_chars if context_chars is not None else window_chars * max_windows
    selected: list[EvidenceWindow] = []
    used = 0
    for index in order:
        start, end, value = candidates[index]
        if len(selected) >= max_windows:
            break
        if used + len(value) > budget:
            continue
        if any(max(0, min(end, item.end) - max(start, item.start)) >
               0.5 * min(end - start, item.end - item.start) for item in selected):
            continue
        selected.append(EvidenceWindow(
            start, end, value,
            semantic_scores[index] if semantic_scores is not None else scores[index],
            method, matched and scores[index] > 0,
            semantic_scores[index] if semantic_scores is not None else None,
        ))
        used += len(value)
    if matched and len(selected) < max_windows:
        for index in (0, len(candidates) - 1):
            if len(selected) >= max_windows:
                break
            start, end, value = candidates[index]
            if used + len(value) > budget or any(item.start == start for item in selected):
                continue
            if any(max(0, min(end, item.end) - max(start, item.start)) >
                   0.5 * min(end - start, item.end - item.start) for item in selected):
                continue
            selected.append(EvidenceWindow(
                start, end, value,
                semantic_scores[index] if semantic_scores is not None else scores[index],
                method, False,
                semantic_scores[index] if semantic_scores is not None else None,
            ))
            used += len(value)
    selected = tuple(sorted(selected, key=lambda item: item.start))
    if selection_receipts is not None:
        context = "\n\n".join(item.text for item in selected)
        receipt = {
            "schema_version": "evidence_selection_receipt.v1",
            "candidate_count": len(candidates),
            "candidate_offsets": [
                {"start": start, "end": end,
                 "sha256": hashlib.sha256(value.encode()).hexdigest()}
                for start, end, value in candidates
            ],
            "selected_offsets": [
                {"start": item.start, "end": item.end,
                 "sha256": hashlib.sha256(item.text.encode()).hexdigest()}
                for item in selected
            ],
            "method": method,
            "lexical_match": matched,
            "semantic_ranker_injected": semantic_ranker is not None,
            "structural_anchor_indices": structural_anchor_indices,
            "ranker_errors": ranker_errors,
            "context_chars": len(context),
            "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
        }
        if compound_terms:
            receipt['compound_terms'] = True
            receipt['query_sha256'] = hashlib.sha256(query.encode()).hexdigest()
        selection_receipts.append(receipt)
    return selected


def retrieve_evidence_gaps(
    text: str,
    questions: Sequence[str],
    *,
    source_id: str | int | None = None,
    basis: str = "supplied_text",
    window_chars: int = 1600,
    max_windows: int = 2,
    context_chars: int | None = None,
    semantic_ranker: Callable[..., Any] | Any | None = None,
    follow_up: Callable[[str], Any] | None = None,
) -> tuple[EvidenceGapSelection, ...]:
    """Retrieve passages for neutral, factual follow-up questions.

    A ``follow_up`` callable may return a string or a mapping containing
    ``text``, ``source_id`` and ``basis``.  This keeps acquisition separate
    from ranking and preserves the identity/scope of newly acquired text.  A
    missing response remains ``unresolved``; no absence or contradiction is
    inferred from an empty result.
    """
    results: list[EvidenceGapSelection] = []
    for raw_question in questions or ():
        question = str(raw_question or "").strip()
        if not question:
            results.append(EvidenceGapSelection(
                question="", source_id=source_id, basis=basis,
                status="unresolved", windows=(), source_text="",
                source_text_sha256=hashlib.sha256(b"").hexdigest()))
            continue
        selected_text, selected_id, selected_basis = text, source_id, basis
        acquired_already = False
        def acquire():
            if not follow_up:
                return None
            try:
                acquired = follow_up(question)
            except Exception:
                acquired = None
            if isinstance(acquired, Mapping):
                return (acquired.get("text", ""), acquired.get("source_id", selected_id),
                        str(acquired.get("basis") or "follow_up_acquired"))
            if isinstance(acquired, str):
                return acquired, selected_id, "follow_up_acquired"
            return None

        if (not isinstance(selected_text, str) or not selected_text.strip()) and follow_up:
            acquired_values = acquire()
            if acquired_values:
                selected_text, selected_id, selected_basis = acquired_values
                acquired_already = True
        if not isinstance(selected_text, str) or not selected_text.strip():
            results.append(EvidenceGapSelection(
                question=question, source_id=selected_id, basis=selected_basis,
                status="unresolved", windows=(), source_text="",
                source_text_sha256=hashlib.sha256(b"").hexdigest()))
            continue
        windows = select_context_windows(
            selected_text, question, window_chars=window_chars,
            max_windows=max_windows,
            overlap_chars=min(200, max(1, window_chars - 1)),
            context_chars=context_chars,
            semantic_ranker=semantic_ranker,
        )
        # A structural sample with no lexical match is a diagnostic fallback,
        # not evidence that the question was answered.  Give the bounded
        # acquisition callback one opportunity to supply a more relevant
        # source, then rank only that returned text.
        if follow_up and not acquired_already and not any(window.lexical_match for window in windows):
            acquired_values = acquire()
            if acquired_values and acquired_values[0] != selected_text:
                selected_text, selected_id, selected_basis = acquired_values
                if isinstance(selected_text, str) and selected_text.strip():
                    windows = select_context_windows(
                        selected_text, question, window_chars=window_chars,
                        max_windows=max_windows,
                        overlap_chars=min(200, max(1, window_chars - 1)),
                        context_chars=context_chars,
                        semantic_ranker=semantic_ranker,
                    )
        results.append(EvidenceGapSelection(
            question=question, source_id=selected_id, basis=selected_basis,
            status="candidate_passages" if windows else "unresolved",
            windows=windows, source_text=selected_text,
            source_text_sha256=hashlib.sha256(selected_text.encode()).hexdigest()))
    return tuple(results)
