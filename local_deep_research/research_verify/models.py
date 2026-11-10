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
  ``supported``/``partial``/``unsupported``/``contradicted``/``unverifiable``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerifyResult(BaseModel):
    """Outcome of a DOI/PMID authenticity check (requirement 1)."""

    doi: str | None = None
    pmid: str | None = None
    # True = exists & consistent / False = definitively absent / None = unverified
    verified: bool | None = None
    source: str = "unavailable"  # crossref | pubmed | link | unavailable
    title_ok: bool | None = None
    year_ok: bool | None = None
    retracted: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    verified_at: str = ""


class ResearchConstraint(BaseModel):
    """Parsed user hard-constraints (requirement 2)."""

    year_from: int | None = None
    year_to: int | None = None
    min_if: float | None = None
    min_if_inclusive: bool = True
    language: str | None = None
    unresolved: list[str] = Field(default_factory=list)
    is_hard_default: bool = True

    @property
    def is_empty(self) -> bool:
        return not (any(value is not None for value in (self.year_from, self.year_to, self.min_if, self.language)) or self.unresolved)


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


class EvidenceSpan(BaseModel):
    """An exact quote located in a specific source field, not model prose."""

    citation: int
    source: str
    field: str
    basis: str  # abstract | body
    content_sha256: str
    quote: str
    start: int
    end: int


class SourceClaimCheck(BaseModel):
    """Separate abstract/body assessments for one claim and one citation."""

    citation: int
    source: str = ""
    abstract_verdict: str = "unverifiable"
    body_verdict: str = "unverifiable"
    verdict: str = "unverifiable"
    reason: str = ""
    reason_code: str = ""
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    review_count: int = 0
    assessments: list[dict] = Field(default_factory=list)


class ClaimCheck(BaseModel):
    """Support verdict for one report claim and its citations (requirement 4)."""

    claim: str
    citations: list[int] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    verdict: str = "unverifiable"  # supported | partial | unsupported | contradicted | unverifiable
    supporting_fragment: str | None = None
    reason: str = ""
    reason_code: str = ""
    start: int | None = None
    end: int | None = None
    source_checks: list[SourceClaimCheck] = Field(default_factory=list)
    retained: bool = False
    replacement: str | None = None


class ReportCheck(BaseModel):
    """One checked body shared by every report output, plus revision history."""

    content: str
    content_sha256: str
    status: str  # supported | partial | unverifiable
    input_content_sha256: str = ""
    checks: list[ClaimCheck] = Field(default_factory=list)
    original_checks: list[ClaimCheck] = Field(default_factory=list)
    paper_checks: list[dict] = Field(default_factory=list)
    removed_claims: int = 0
    revised_claims: int = 0
    model_calls: int = 0
    policy_version: str = "abstract-body-v2"
    scope: str = "claim_grounding_only"
