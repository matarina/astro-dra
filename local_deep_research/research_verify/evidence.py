"""Source snapshots and verbatim quote locations (no network or semantic inference)."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from urllib.parse import urlsplit, urlunsplit

from .contracts import EvidenceLocator
from .textutil import extract_doi


@dataclass(frozen=True)
class SourceArtifact:
    paper_id: str
    artifact_id: str
    text: str
    content_sha256: str
    basis: str
    source_url: str | None
    field: str

    def locate(self, quote: str | None, *,
               within: tuple[tuple[int, int], ...] | None = None) -> EvidenceLocator | None:
        """Locate a contiguous quote inside one allowed range, using raw offsets.

        Whitespace differences are allowed; no case, punctuation, numbers,
        negation or ellipsis are rewritten. A quote cannot bridge passage gaps.
        """
        if not isinstance(quote, str) or not quote.strip():
            return None
        quote = quote.strip()
        ranges = ((0, len(self.text)),) if within is None else within
        for begin, finish in ranges:
            if not 0 <= begin < finish <= len(self.text):
                continue
            segment = self.text[begin:finish]
            start = segment.find(quote)
            if start >= 0:
                end = start + len(quote)
            else:
                normalized, offsets = _whitespace_map(segment)
                needle = re.sub(r"\s+", " ", quote)
                pos = normalized.find(needle)
                if pos < 0:
                    continue
                start = offsets[pos][0]
                end = offsets[pos + len(needle) - 1][1]
            start, end = begin + start, begin + end
            return EvidenceLocator(
                paper_id=self.paper_id, artifact_id=self.artifact_id,
                content_sha256=self.content_sha256, source_url=self.source_url,
                basis=self.basis, start=start, end=end, quote=self.text[start:end],
            )
        return None


def _whitespace_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    chars, offsets = [], []
    for match in re.finditer(r"\s+|\S", text):
        chars.append(" " if match.group().isspace() else match.group())
        offsets.append((match.start(), match.end()))
    return "".join(chars), offsets


def paper_identity(source: dict) -> str | None:
    doi = extract_doi(source.get("doi"), source.get("DOI"))
    if doi:
        return "doi:" + doi.casefold()
    for field in ("pmid", "_pmid"):
        value = str(source.get(field) or "").strip()
        if value.isdigit():
            return "pmid:" + value
    url = source.get("link") or source.get("url")
    if isinstance(url, str):
        try:
            parts = urlsplit(url.strip())
            if parts.scheme.lower() in {"http", "https"} and parts.hostname:
                doi = extract_doi(url) if parts.hostname.lower() in {"doi.org", "dx.doi.org"} else None
                if doi:
                    return "doi:" + doi.casefold()
                canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                                       parts.path or "/", parts.query, ""))
                return "url:" + sha256(canonical.encode()).hexdigest()
        except ValueError:
            pass
    value = source.get("paper_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def source_artifacts(source: dict) -> tuple[SourceArtifact, ...]:
    """Retain field provenance; a field named full_content is not proof of full text."""
    paper_id = paper_identity(source)
    if not paper_id:
        return ()
    url = source.get("link") or source.get("url")
    url = url if isinstance(url, str) else None
    if not url and paper_id.startswith("doi:"):
        url = "https://doi.org/" + paper_id[4:]
    elif not url and paper_id.startswith("pmid:"):
        url = "https://pubmed.ncbi.nlm.nih.gov/" + paper_id[5:] + "/"
    content_type = str(source.get("content_type") or "").lower()
    artifacts = []
    for field in ("full_content", "body", "content", "abstract", "snippet"):
        text = source.get(field)
        if not isinstance(text, str) or not text.strip():
            continue
        if field == "abstract" or content_type == "abstract" and field != "snippet":
            basis = "abstract"
        elif field != "snippet" and content_type in {"full_text", "fulltext"}:
            basis = "fulltext"
        else:
            basis = "snippet"
        digest = sha256(text.encode("utf-8")).hexdigest()
        artifact_id = "text-v1:" + sha256((paper_id + "\0" + field + "\0" + digest).encode()).hexdigest()
        artifacts.append(SourceArtifact(paper_id, artifact_id, text, digest, basis, url, field))
    return tuple(artifacts)
