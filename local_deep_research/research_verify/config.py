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

from pydantic import Field, model_validator
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
    enable_constraint_match: bool = False
    enable_keyword_coverage: bool = False
    enable_citation_qc: bool = True

    # --- shared HTTP client ---
    http_timeout: float = 10.0
    http_max_retries: int = 2
    http_concurrency: int = 8
    crossref_mailto: str = "ldr-research-verify@example.com"

    # --- requirement 2: constraint matching defaults ---
    min_if: float | None = None
    strict_year: bool = False

    # --- requirement 3: keyword coverage ---
    min_keyword_hits: int = 3
    keyword_threshold_ratio: float = 0.75

    # --- requirement 4: citation QC ---
    qc_batch_size: int = 5
    qc_passage_chars: int = Field(default=1600, ge=128, le=8192)
    qc_max_passages: int = Field(default=3, ge=1, le=8)
    qc_passage_overlap_chars: int = Field(default=200, ge=0, le=1024)
    judge_temperature: float = 0.0

    @model_validator(mode="after")
    def validate_passage_budget(self):
        if self.qc_passage_overlap_chars >= self.qc_passage_chars:
            raise ValueError("passage overlap must be smaller than passage size")
        return self

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
