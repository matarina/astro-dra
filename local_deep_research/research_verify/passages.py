"""Deterministic lexical passage retrieval with untouched source coordinates."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

_STOP = set("a an the of to in on for with by at from and or is are was were be been this that it its study trial observed conclusion".split())
_REFERENCES = re.compile(r"(?im)^\s*(?:#{1,6}\s*)?(?:references|bibliography|参考文献)\s*:?\s*$")


@dataclass(frozen=True)
class Passage:
    start: int
    end: int
    text: str
    score: float


def terms(text: str) -> set[str]:
    out = {t.casefold() for t in re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*", text)
           if t.casefold() not in _STOP}
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        out.update(run[i:i+2] for i in range(len(run)-1))
    return out


def retrieve_passages(text: str, claim: str, *, window_chars: int = 1600,
                      max_passages: int = 3, overlap_chars: int = 200) -> tuple[Passage, ...]:
    """Rank paragraph windows; use bounded opening context if no term overlaps.

    Scan all supplied text, not merely its opening. Selection is not a proof of
    support or an exhaustive proof of absence. Reference sections are excluded.
    """
    if window_chars < 32 or not 0 <= overlap_chars < window_chars or max_passages < 1:
        raise ValueError("invalid passage budget")
    cutoff = _REFERENCES.search(text)
    eligible_end = cutoff.start() if cutoff else len(text)
    query_terms = terms(claim)
    candidates = []
    boundaries = [0] + [m.end() for m in re.finditer(r"\n\s*\n", text[:eligible_end])]
    ends = [m.start() for m in re.finditer(r"\n\s*\n", text[:eligible_end])] + [eligible_end]
    for begin, finish in zip(boundaries, ends):
        while begin < finish and text[begin].isspace():
            begin += 1
        while finish > begin and text[finish-1].isspace():
            finish -= 1
        start = begin
        while start < finish:
            end = min(start + window_chars, finish)
            passage_terms = terms(text[start:end])
            common = query_terms & passage_terms
            # Distinct lexical hits with a small density preference.
            score = len(common) + (len(common) / math.sqrt(max(1, len(passage_terms))))
            candidates.append(Passage(start, end, text[start:end], score))
            if end == finish:
                break
            start = end - overlap_chars
    if not candidates:
        return ()
    ranked = sorted(candidates, key=lambda p: (-p.score, p.start))
    if ranked[0].score == 0:
        return (min(candidates, key=lambda p: p.start),)
    selected = []
    for item in ranked:
        if item.score == 0:
            break
        # Avoid spending the whole budget on near-identical overlapping windows.
        if any(max(0, min(item.end, p.end)-max(item.start, p.start))
               > 0.5 * min(item.end-item.start, p.end-p.start) for p in selected):
            continue
        selected.append(item)
        if len(selected) == max_passages:
            break
    return tuple(sorted(selected, key=lambda p: p.start))
