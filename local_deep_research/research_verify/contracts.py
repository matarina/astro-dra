"""Versioned foundation contracts; not yet wired into report production.

Legacy models remain compatible. A gate is scoped to its required checks:
passing claim traceability never implies passing all literature requirements.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class GateDecision(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    PENDING = "pending"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JifSnapshot(Contract):
    metric_year: int = Field(ge=1900, le=2100)
    release_version: str = Field(min_length=1)
    source: str = Field(min_length=1)
    latest_release_confirmed: bool = False


class TaskPolicy(Contract):
    policy_version: Literal["1.0"] = "1.0"
    task_id: str = Field(min_length=1)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    date_basis: Literal["version_of_record_first_online"] = "version_of_record_first_online"
    min_jif: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    jif_operator: Literal["gt", "gte"] = "gt"
    jif_selection: Literal["latest_published"] = "latest_published"
    jif_snapshot: JifSnapshot | None = None
    language: str | None = None
    keywords: tuple[str, ...] = ()
    keyword_min_hits: int | None = Field(default=None, ge=1)
    keyword_scope: Literal["body_excluding_references"] = "body_excluding_references"
    required_checks: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_policy(self):
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("year_from must not exceed year_to")
        words = [word.strip().casefold() for word in self.keywords]
        if any(not word for word in words) or len(words) != len(set(words)):
            raise ValueError("keywords must be nonempty and distinct")
        if self.keywords:
            if self.keyword_min_hits is None or self.keyword_min_hits > len(self.keywords):
                raise ValueError("explicit achievable keyword_min_hits required")
        elif self.keyword_min_hits is not None:
            raise ValueError("keyword_min_hits requires keywords")
        if any(not key.strip() for key in self.required_checks):
            raise ValueError("required check IDs must be nonempty")
        if len(self.required_checks) != len(set(self.required_checks)):
            raise ValueError("required check IDs must be distinct")
        return self


class EvidenceLocator(Contract):
    paper_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str | None = None
    basis: Literal["fulltext", "abstract", "snippet"]
    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.end <= self.start:
            raise ValueError("end must exceed start")
        return self


class CheckResult(Contract):
    check_id: str = Field(min_length=1)
    status: CheckStatus
    reason_code: str = Field(min_length=1)
    evidence: tuple[EvidenceLocator, ...] = ()
    checked_at: str | None = None
    verifier_version: str = Field(min_length=1)


class ClaimEvidence(Contract):
    claim_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    verdict: Literal["supported", "partial", "unsupported", "unverifiable"]
    locator: EvidenceLocator | None = None
    quote_verified: bool = False
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_located_quote(self):
        if self.locator is not None and self.locator.paper_id != self.paper_id:
            raise ValueError("evidence paper identity mismatch")
        if self.verdict == "supported" and (self.locator is None or not self.quote_verified):
            raise ValueError("supported requires a located, verified quote")
        return self


def evaluate_gate(required_checks: tuple[str, ...], results: tuple[CheckResult, ...]) -> GateDecision:
    """Missing, unknown, disabled and malformed checks never admit an item.

    Unexpected optional checks do not alter the explicitly scoped gate.
    Duplicate outcomes are ambiguous and remain pending.
    """
    if not required_checks or len(set(required_checks)) != len(required_checks):
        return GateDecision.PENDING
    by_id: dict[str, CheckResult] = {}
    for result in results:
        if result.check_id not in required_checks:
            continue
        if result.check_id in by_id:
            return GateDecision.PENDING
        by_id[result.check_id] = result
    if any(r.status == CheckStatus.FAIL for r in by_id.values()):
        return GateDecision.REJECTED
    if any(key not in by_id or by_id[key].status != CheckStatus.PASS for key in required_checks):
        return GateDecision.PENDING
    return GateDecision.ADMITTED
