"""Source-scoped retrieval and exact quote offsets; no embedding dependencies."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
import re

from .models import EvidenceSpan


@dataclass(frozen=True)
class Artifact:
    field: str
    basis: str
    text: str
    start: int = 0
    end: int | None = None

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode()).hexdigest()


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str


class SourceLookup:
    """Resolve explicit citation indices, including accumulated report sources."""

    def __init__(self, sources):
        self._sources = {}
        self._ambiguous = set()
        for source in sources:
            if not isinstance(source, dict):
                continue
            try:
                if isinstance(source.get("index"), bool) or not str(source["index"]).isdigit():
                    continue
                index = int(source["index"])
            except (KeyError, ValueError, TypeError):
                continue
            if index < 1:
                continue
            if index in self._sources and self._sources[index] != source:
                self._ambiguous.add(index)
            self._sources[index] = source

    def find_by_index(self, index):
        return None if index in self._ambiguous else self._sources.get(index)

    def snapshot(self, indices):
        return SourceLookup([deepcopy(source) for index in indices
                             if (source := self.find_by_index(index)) is not None])

    def records(self):
        return [deepcopy(source) for index, source in self._sources.items() if index not in self._ambiguous]


_REFERENCES = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\d+[.\s]+)?(?:references|bibliography|参考文献)\s*:?\s*$"
)
_ABSTRACT_HEADING = re.compile(r"(?im)^\s*(?:#{1,6}\s*)?(?:abstract|摘要)\s*:?\s*$")
_BODY_HEADING = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\d+[.\s]+)?(?:introduction|background|methods|materials and methods|results|discussion|conclusions?|引言|背景|方法|结果|讨论|结论)\s*:?\s*$"
)


def source_artifacts(source: dict) -> tuple[Artifact | None, Artifact | None]:
    """Never infer body availability from length or the name full_content."""
    from .source_evidence import is_search_page, normalize_source
    if is_search_page(source):
        return None, None
    normalize_source(source)
    abstract = source.get("abstract")
    abstract_field = "abstract"
    kind = str(source.get("content_type") or "").lower()
    if not abstract and kind == "abstract":
        abstract_field = "full_content" if source.get("full_content") else "content"
        abstract = source.get(abstract_field)
    abs_art = (
        Artifact(abstract_field, "abstract", abstract)
        if isinstance(abstract, str) and abstract.strip()
        else None
    )
    if kind in {"abstract", "summary", "search_results", "search_results_page"}:
        return abs_art, None

    body_field = "body"
    body = source.get(body_field)
    if not body and kind in {"full_text", "fulltext", "body"}:
        body_field = "full_content" if source.get("full_content") else "content"
        body = source.get(body_field)
    if not isinstance(body, str) or not body.strip():
        return abs_art, None
    # An explicitly mislabeled abstract cannot become body evidence.
    if abs_art and re.sub(r"\s+", "", body) == re.sub(r"\s+", "", abs_art.text):
        return abs_art, None
    start, end = 0, len(body)
    references = _REFERENCES.search(body)
    if references:
        end = references.start()
    abstract_heading = _ABSTRACT_HEADING.search(body, 0, end)
    if abstract_heading:
        marker = re.match(r"\s*(#{1,6})[ \t]+", abstract_heading[0])
        heading = None
        if marker:
            heading = next(
                (
                    h
                    for h in re.finditer(r"(?m)^ {0,3}(#{1,6})[ \t]+[^\n]+", body)
                    if abstract_heading.end() <= h.start() < end
                    and len(h[1]) <= len(marker[1])
                ),
                None,
            )
        else:
            heading = _BODY_HEADING.search(body, abstract_heading.end(), end)
        if not heading:
            return abs_art, None  # Cannot separate abstract from body reliably.
        start = heading.start()
    return (
        abs_art,
        Artifact(body_field, "body", body, start, end)
        if body[start:end].strip()
        else None,
    )


def _tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"[a-z][a-z0-9_-]{1,}|\d+(?:\.\d+)?|[\u4e00-\u9fff]", text.casefold()
        )
    )


def retrieve(
    artifact: Artifact, claim: str, *, chunk_chars: int, top_k: int, context_chars: int
) -> list[Chunk]:
    """Rank windows across the entire body, preserving original field offsets."""
    size = min(chunk_chars, context_chars)
    end = artifact.end if artifact.end is not None else len(artifact.text)
    step = max(1, size - min(200, size // 4))
    chunks = [
        Chunk(p, min(p + size, end), artifact.text[p : min(p + size, end)])
        for p in range(artifact.start, end, step)
    ]
    if not chunks:
        return []
    query = _tokens(claim)
    tokens = [_tokens(c.text) for c in chunks]
    counts = Counter(t for terms in tokens for t in terms)
    scores = [
        sum(math.log(1 + len(chunks) / counts[t]) for t in query & terms)
        for terms in tokens
    ]
    # With no lexical overlap (e.g. Chinese claim / English paper), sample the
    # complete document rather than silently restricting evidence to its head.
    if not any(scores):
        n = min(top_k, len(chunks))
        order = [round(i * (len(chunks) - 1) / max(1, n - 1)) for i in range(n)]
    else:
        order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    selected, used = [], 0
    for i in order:
        chunk = chunks[i]
        if len(selected) >= top_k:
            break
        if used + len(chunk.text) <= context_chars:
            selected.append(chunk)
            used += len(chunk.text)
    return sorted(selected, key=lambda c: c.start)


def _normalized(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace only, with a mapping back to the original text."""
    chars, offsets = [], []
    for i, char in enumerate(text):
        if char.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                offsets.append(i)
        else:
            chars.append(char)
            offsets.append(i)
    return "".join(chars), offsets


def locate_quote(
    quote: str, artifact: Artifact, chunks: list[Chunk], citation: int, source: str
) -> EvidenceSpan | None:
    """Only accept a quote actually shown to the judge, never a fuzzy match."""
    quote = quote.strip()
    if not quote:
        return None
    for chunk in chunks:
        pos = chunk.text.find(quote)
        if pos >= 0:
            start, end = chunk.start + pos, chunk.start + pos + len(quote)
        else:
            normalized, offsets = _normalized(chunk.text)
            needle, _ = _normalized(quote)
            needle = needle.strip()
            pos = normalized.find(needle) if needle else -1
            if pos < 0:
                continue
            start = chunk.start + offsets[pos]
            end = chunk.start + offsets[pos + len(needle) - 1] + 1
        return EvidenceSpan(
            citation=citation,
            source=source,
            field=artifact.field,
            basis=artifact.basis,
            content_sha256=artifact.sha256,
            quote=artifact.text[start:end],
            start=start,
            end=end,
        )
    return None
