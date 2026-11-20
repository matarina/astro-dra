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
from .evidence_grounding import (
    EvidenceGrounding,
    EvidenceGroundingV1,
    GroundingClaim,
    GroundingLocator,
    GroundingResearchSpec,
    GroundingSource,
    SourceEnrichment,
    SourceIdentityEnrichment,
    SourceRegistry,
    apply_source_enrichments,
    build_evidence_grounding,
    identity_hash,
    pending_native_findings,
    validate_evidence_locator,
)
from .heldout import (
    AcceptanceSummary,
    CaseReview,
    ClaimReview,
    HeldoutCase,
    HeldoutManifest,
    HeldoutModelSettings,
    ManualReviewPacket,
    evaluate_acceptance,
    seal_manual_packet,
    validate_manifest,
    validate_pair_integrity,
)
from .research_spec import ResearchSpec, format_research_spec, parse_research_spec
from .debug_capture import capture_chat_completion
from .source_identity import canonical_url, classify_source

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
    "ResearchSpec",
    "parse_research_spec",
    "format_research_spec",
    "EvidenceGrounding",
    "EvidenceGroundingV1",
    "GroundingClaim",
    "GroundingLocator",
    "GroundingResearchSpec",
    "GroundingSource",
    "SourceEnrichment",
    "SourceIdentityEnrichment",
    "SourceRegistry",
    "apply_source_enrichments",
    "build_evidence_grounding",
    "identity_hash",
    "pending_native_findings",
    "validate_evidence_locator",
    "AcceptanceSummary",
    "CaseReview",
    "ClaimReview",
    "HeldoutCase",
    "HeldoutManifest",
    "HeldoutModelSettings",
    "ManualReviewPacket",
    "evaluate_acceptance",
    "seal_manual_packet",
    "validate_manifest",
    "validate_pair_integrity",
    "capture_chat_completion",
    "canonical_url",
    "classify_source",
]

__version__ = "0.1.0"
