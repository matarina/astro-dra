"""Small, dependency-free text/normalisation helpers for ``research_verify``.

The normalisation rules deliberately mirror
``SearchResultsCollector._identity_keys`` (title casefold + non-word stripping)
so that identity/title comparisons across the chain stay consistent with the
collector's dedup logic.

Everything here is pure and synchronous: safe to unit-test without network or
a running event loop.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

# DOI: matches the canonical ``10.<registrant>/<suffix>`` shape, stopping at
# whitespace or common trailing punctuation.
_DOI_RE = re.compile(r"10\.\d+/[^\s\"'<>]+", re.IGNORECASE)
# Trailing punctuation that is commonly glued to a DOI in prose/parentheses.
_DOI_TRAILING = ".,;)]}>"
# PubMed IDs are 7-9 digit numbers.
_PMID_RE = re.compile(r"\b(\d{7,9})\b")
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def normalize_title(s: str | None) -> str:
    """Casefold + collapse non-word chars, matching the collector's identity key."""
    if not s:
        return ""
    out = str(s).casefold()
    out = re.sub(r"[^\w]+", " ", out, flags=re.UNICODE).strip()
    return out


def normalize_year(value: Any) -> int | None:
    """Extract a 4-digit publication year from a variety of field shapes."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2100 else None
    m = _YEAR_RE.search(str(value))
    return int(m.group(0)) if m else None


def first_year(source: dict, keys: Iterable[str] = (
    "year", "published", "publication_date", "pubdate", "date",
)) -> int | None:
    """Return the first parsable year among *keys* on *source*."""
    for key in keys:
        if key in source:
            year = normalize_year(source.get(key))
            if year is not None:
                return year
    return None


def normalize_doi(raw: str | None) -> str | None:
    """Strip ``doi:``/``https://doi.org/`` prefixes and trailing punctuation."""
    if not raw:
        return None
    s = str(raw).strip()
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.IGNORECASE)
    s = s.rstrip(_DOI_TRAILING).strip()
    return s or None


def extract_doi(*candidates: Any) -> str | None:
    """Return the first normalised DOI found among *candidates* (str or dict-less)."""
    for cand in candidates:
        if not cand:
            continue
        m = _DOI_RE.search(str(cand))
        if m:
            doi = normalize_doi(m.group(0))
            if doi:
                return doi
    return None


def extract_pmid(*candidates: Any) -> str | None:
    """Return the first plausible PMID found among *candidates*."""
    for cand in candidates:
        if cand is None or cand == "":
            continue
        s = str(cand).strip()
        if s.isdigit() and 7 <= len(s) <= 9:
            return s
        m = _PMID_RE.search(s)
        if m:
            return m.group(1)
    return None


def first_nonempty(source: dict, keys: Iterable[str]) -> Any:
    """Return the first non-empty value among *keys* on *source*, else ``None``."""
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def truncate(text: str | None, limit: int = 1500) -> str:
    """Bound *text* to *limit* chars, appending an ellipsis when cut."""
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 (seconds precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
