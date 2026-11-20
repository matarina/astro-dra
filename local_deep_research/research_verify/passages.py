"""Compatibility wrapper around the shared evidence-window selector."""
from __future__ import annotations

from dataclasses import dataclass
from .evidence_selection import select_context_windows


@dataclass(frozen=True)
class Passage:
    start: int
    end: int
    text: str
    score: float


def terms(text: str) -> set[str]:
    # Kept as a compatibility helper; selection itself is centralized below.
    from .evidence_selection import _terms
    return _terms(text)


def retrieve_passages(text: str, claim: str, *, window_chars: int = 1600,
                      max_passages: int = 3, overlap_chars: int = 200,
                      semantic_ranker=None, selection_receipts=None,
                      compound_terms=False) -> tuple[Passage, ...]:
    windows = select_context_windows(text, claim, window_chars=window_chars,
                                     max_windows=max_passages,
                                     overlap_chars=min(overlap_chars, window_chars - 1),
                                     semantic_ranker=semantic_ranker,
                                     selection_receipts=selection_receipts,
                                     compound_terms=compound_terms)
    return tuple(Passage(item.start, item.end, item.text, item.score) for item in windows)
