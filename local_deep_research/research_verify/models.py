"""Shared pydantic models for the ``research_verify`` chain.

All four requirement modules read/write these models, so they live in one
place to avoid circular imports.  The models are intentionally thin and
JSON-serialisable: callers stash ``model_dump()`` results onto the source
dicts and the report renderer reads the badge/status back off them.

Status vocabularies (never silently pass a bad item):

* requirement 1 ``VerifyResult.verified`` -- ``True`` / ``False`` / ``None``
  (``None`` == unverified, e.g. offline).
* requirement 2 ``ConstraintMatch.hard_violations`` -- non-empty means the
  source must be flagged/dropped for the report's condition.
* requirement 3 ``KeywordCov.threshold_ok`` -- ``False`` means under-covered.
* requirement 4 ``ClaimCheck.verdict`` -- one of
  ``supported``/``partial``/``unsupported``/``unverifiable``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .contracts import ClaimEvidence


class VerifyResult(BaseModel):
    """Outcome of a DOI/PMID authenticity check (requirement 1)."""

    doi: str | None = None
    pmid: str | None = None
    # True = exists & consistent / False = definitively absent / None = unverified
    verified: bool | None = None
    source: str = "unavailable"  # crossref | pubmed | link | unavailable
    title_ok: bool | None = None
    year_ok: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    verified_at: str = ""


class ResearchConstraint(BaseModel):
    """Parsed user hard-constraints (requirement 2)."""

    year_from: int | None = None
    year_to: int | None = None
    min_if: float | None = None
    language: str | None = None
    is_hard_default: bool = True

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.year_from, self.year_to, self.min_if, self.language)
        )


class ConstraintMatch(BaseModel):
    """Per-source result of matching against a :class:`ResearchConstraint`."""

    year_ok: bool | None = None
    if_ok: bool | None = None
    lang_ok: bool | None = None
    hard_violations: list[str] = Field(default_factory=list)
    if_unknown: bool = False
    detail: dict = Field(default_factory=dict)

    @property
    def excluded(self) -> bool:
        return bool(self.hard_violations)


class KeywordCov(BaseModel):
    """Keyword-coverage statistics for one source (requirement 3)."""

    total: int = 0
    hits: list[str] = Field(default_factory=list)
    missed: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    threshold_ok: bool = True
    basis: str = "unavailable"  # fulltext | abstract | unavailable


class CitationSupport(BaseModel):
    """One cited work's outcome; missing citations remain explicit audit rows."""
    citation_index: int
    paper_id: str | None = None
    artifact_id: str | None = None
    basis: str | None = None
    source_field: str | None = None
    text_version: str = "raw-text-v1"
    assessed_chars: int = 0
    verdict: str = "unverifiable"
    reason_code: str = "unresolved_citation"
    model_reason: str = ""
    evidence: ClaimEvidence | None = None


class ClaimCheck(BaseModel):
    """Support verdict for one report claim and its citations (requirement 4)."""

    claim: str
    claim_id: str = ""
    citation_checks: list[CitationSupport] = Field(default_factory=list)
    citations: list[int] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    verdict: str = "unverifiable"  # supported | partial | unsupported | unverifiable
    supporting_fragment: str | None = None
    reason: str = ""
