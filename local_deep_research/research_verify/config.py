"""Configuration for the LDR research-verification chain (``research_verify``).

Every knob is overridable through environment variables prefixed with
``LDR_VERIFY_`` (e.g. ``LDR_VERIFY_ENABLE_DOI_VALIDATION=false``).

Design contract (see ``LDR-四需求-行动文档.md`` §0.1):
    verification = annotate / drop / leave a trace.
It must *never* silently pass a bad item, and must *never* fail the whole
report.  When the network is unavailable the chain degrades to
``unverified`` and records that fact, rather than blocking the research.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VerifyConfig(BaseSettings):
    """Runtime configuration for the verification modules."""

    model_config = SettingsConfigDict(
        env_prefix="LDR_VERIFY_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- global switches (one per module; ``enable_verify`` is the master) ---
    enable_verify: bool = True
    enable_doi_validation: bool = True
    enable_constraint_match: bool = True
    enable_keyword_coverage: bool = True
    enable_citation_qc: bool = True

    # --- shared HTTP client ---
    http_timeout: float = Field(default=10.0, gt=0, le=120)
    http_max_retries: int = Field(default=2, ge=0, le=5)
    http_concurrency: int = Field(default=8, ge=1, le=32)
    crossref_mailto: str = "ldr-research-verify@example.com"

    # --- requirement 2: constraint matching defaults ---
    min_if: float | None = None
    strict_year: bool = False

    # --- requirement 3: keyword coverage ---
    min_keyword_hits: int = Field(default=3, ge=1)
    keyword_threshold_ratio: float = Field(default=0.75, ge=0, le=1)

    # --- requirement 4: citation QC ---
    qc_batch_size: int = Field(default=5, ge=1)
    judge_temperature: float = 0.0
    qc_require_body: bool = True
    qc_max_claims: int = Field(default=80, ge=1)
    qc_max_model_calls: int = Field(default=200, ge=1)
    qc_context_chars: int = Field(default=6000, ge=1000)
    qc_chunk_chars: int = Field(default=1200, ge=200)
    qc_top_k: int = Field(default=4, ge=1, le=12)
    qc_review_rounds: int = Field(default=1, ge=0, le=2)
    qc_repair_rounds: int = Field(default=1, ge=0, le=2)

    def module_enabled(self, name: str) -> bool:
        """Return True only if the master switch AND the module switch are on.

        ``name`` is the module suffix, e.g. ``"doi_validation"`` maps to the
        ``enable_doi_validation`` field.
        """
        if not self.enable_verify:
            return False
        return bool(getattr(self, f"enable_{name}", True))


@lru_cache(maxsize=1)
def get_config() -> VerifyConfig:
    """Return a process-wide cached :class:`VerifyConfig`."""
    return VerifyConfig()
