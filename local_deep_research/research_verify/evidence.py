"""Source-scoped retrieval and exact quote offsets; no embedding dependencies."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import re

from .models import EvidenceSpan
from .source_identity import canonical_url, identity_fields


@dataclass(frozen=True)
class Artifact:
    field: str
    basis: str
    text: str
    start: int = 0
    end: int | None = None
    paper_id: str = ""
    source_url: str = ""

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def artifact_id(self):
        return self.sha256

    @property
    def content_sha256(self):
        return self.sha256


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

    @property
    def ambiguous_indices(self):
        """Indices with differing supplied records; no identity is selected."""
        return frozenset(self._ambiguous)

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
    paper_id = paper_identity(source) or ""
    source_url = _source_url(source)
    abstract = source.get("abstract")
    abstract_field = "abstract"
    kind = str(source.get("content_type") or "").lower()
    if not abstract and kind == "abstract":
        abstract_field = "full_content" if source.get("full_content") else "content"
        abstract = source.get(abstract_field)
    abs_art = (
        Artifact(abstract_field, "abstract", abstract, paper_id=paper_id, source_url=source_url)
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
    body_basis = "body"
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
            # Do not discard supplied body text merely because the publisher
            # used an unconventional heading.  Preserve it with an explicit
            # uncertain boundary; the model-facing scope records that this is
            # not a verified abstract/body split.
            start = abstract_heading.end()
            body_basis = "body (abstract boundary uncertain)"
        else:
            start = heading.start()
    return (
        abs_art,
        Artifact(body_field, body_basis, body, start, end,
                 paper_id=paper_id, source_url=source_url)
        if body[start:end].strip()
        else None,
    )


def paper_identity(source: dict) -> str | None:
    """Return a conservative work identity independent of display numbering."""
    if not isinstance(source, dict):
        return None
    ids = identity_fields(source)
    if ids.get("doi"):
        return "doi:" + ids["doi"].casefold()
    if ids.get("pmid"):
        return "pmid:" + str(ids["pmid"])
    if ids.get("pmcid"):
        return "pmcid:" + str(ids["pmcid"]).upper()
    value = canonical_url(source.get("link") or source.get("url"))
    return "url:" + value if value else None


def _source_url(source: dict) -> str:
    """Resolve a stable display URL without inventing a publisher link."""
    value = canonical_url(source.get("link") or source.get("url"))
    if value:
        return value
    identity = identity_fields(source)
    if identity.get("doi"):
        return "https://doi.org/" + identity["doi"]
    if identity.get("pmid"):
        return "https://pubmed.ncbi.nlm.nih.gov/" + str(identity["pmid"]) + "/"
    if identity.get("pmcid"):
        return "https://pmc.ncbi.nlm.nih.gov/articles/" + str(identity["pmcid"]).upper() + "/"
    return ""


def _tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"[a-z][a-z0-9_-]{1,}|\d+(?:\.\d+)?|[\u4e00-\u9fff]", text.casefold()
        )
    )


def retrieve(
    artifact: Artifact, claim: str, *, chunk_chars: int, top_k: int, context_chars: int,
    semantic_ranker=None,
) -> list[Chunk]:
    """Select shared structural windows while preserving artifact offsets."""
    from .evidence_selection import select_context_windows
    start = artifact.start
    end = artifact.end if artifact.end is not None else len(artifact.text)
    size = min(chunk_chars, context_chars)
    windows = select_context_windows(artifact.text[start:end], claim,
                                     window_chars=size,
                                     max_windows=top_k,
                                     overlap_chars=min(size - 1, max(1, chunk_chars // 4)),
                                     context_chars=context_chars,
                                     semantic_ranker=semantic_ranker)
    return [Chunk(start + item.start, start + item.end, item.text) for item in windows]


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
