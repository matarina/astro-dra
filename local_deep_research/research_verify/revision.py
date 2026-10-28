"""Read-only schemas for reports saved by the retired rule-based revision pipeline.

No automatic deletion, rewriting or publication gating remains here.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from .models import ClaimCheck


class RevisionAction(BaseModel):
    original: ClaimCheck
    action: Literal["retained", "revised", "removed", "pending"]
    reason_code: str
    parent_claim_id: str = ""
    proposed: list[str] = Field(default_factory=list)
    checks: list[ClaimCheck] = Field(default_factory=list)


class RevisionResult(BaseModel):
    schema_version: str = "1.0"
    status: Literal["traceability_checked", "partial", "withheld"]
    verified_body: str = ""
    pending_section: str = ""
    final_checks: list[ClaimCheck] = Field(default_factory=list)
    actions: list[RevisionAction] = Field(default_factory=list)
    repair_requests: int = 0
    reason_code: str = ""
    body_sha256: str = ""
