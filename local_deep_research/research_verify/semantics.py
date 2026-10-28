"""Model judgment plus read-only compatibility fields for historical audit data.

Semantic decisions are model suggestions. No regex contradiction or scope gates.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from .contracts import EvidenceLocator

# Historical audit readers and pilot fixtures use these names, not a required schema.
DIMENSIONS = ("population", "quantities", "direction", "causality", "study_design", "scope")


class SemanticJudgment(BaseModel):
    verdict: Literal["supported", "partial", "unsupported", "unverifiable"]
    supporting_fragment: str = ""
    reason: str = ""


class SemanticCheck(BaseModel):
    dimension: Literal["population", "quantities", "direction", "causality", "study_design", "scope"]
    status: Literal["matched", "partial", "mismatch", "uncertain", "not_applicable"]
    origin: Literal["model", "rule"]
    reason_code: str
    reason: str = ""
    locator: EvidenceLocator | None = None
