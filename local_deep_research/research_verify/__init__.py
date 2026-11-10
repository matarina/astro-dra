"""``research_verify`` -- LDR research-verification chain (four requirements).

This package implements the "scientific verification chain" inserted between
retrieval and report generation:

* requirement 1 -- DOI/PMID authenticity        (``doi_validator``)
* requirement 2 -- year / IF / language matching (``constraint_matcher``)
* requirement 3 -- keyword coverage              (``keyword_cov``)
* requirement 4 -- claim traceability            (``citation_qc``)

Public baseline entry points available from this skeleton:

* :class:`VerifyConfig` / :func:`get_config` -- configuration + feature switches
* :class:`HttpClient` / :class:`HttpResult`   -- shared async HTTP helper
"""

from .config import VerifyConfig, get_config
from .http_client import HttpClient, HttpResult
from .models import (
    ClaimCheck,
    EvidenceSpan,
    SourceClaimCheck,
    ReportCheck,
    ConstraintMatch,
    KeywordCov,
    ResearchConstraint,
    VerifyResult,
)

__all__ = [
    "VerifyConfig",
    "get_config",
    "HttpClient",
    "HttpResult",
    "ClaimCheck",
    "EvidenceSpan",
    "SourceClaimCheck",
    "ReportCheck",
    "ConstraintMatch",
    "KeywordCov",
    "ResearchConstraint",
    "VerifyResult",
]

__version__ = "0.1.0"
