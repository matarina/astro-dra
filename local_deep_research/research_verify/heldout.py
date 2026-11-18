"""Versioned held-out evaluation manifest and manual-review packet.

This is an input-integrity harness.  It does not run a model, score a report,
or use review findings to alter production behavior.  A manifest can describe
prospective cases before output files exist, while its prompt and source-packet
hashes are always checked when they do exist.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def file_sha256(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


class HeldoutModelSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    case_id: str | None = None
    source_support: Literal["supported", "partial", "unsupported", "unknown"] = "unknown"
    citation_alignment: Literal["aligned", "misaligned", "unknown"] = "unknown"
    scope_adherence: Literal["adherent", "mismatch", "unknown"] = "unknown"
    identity_metadata_correctness: Literal["correct", "incorrect", "unknown"] = "unknown"
    abstention_correctness: Literal["correct", "incorrect", "unknown"] = "unknown"
    useful_content_retention: Literal["retained", "lost", "unknown"] = "unknown"
    newly_introduced_errors: list[str] = Field(default_factory=list)
    notes: str = ""


class CaseReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    assertion_count: int = Field(ge=0)
    no_assertions_reason: str = ""

    @model_validator(mode="after")
    def zero_assertion_requires_reason(self):
        if self.assertion_count == 0 and not self.no_assertions_reason.strip():
            raise ValueError("zero-assertion case requires an explicit reason")
        return self


class ManualReviewPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["manual_review.v1"] = "manual_review.v1"
    sealed: bool = False
    sealed_at: str | None = None
    candidate_outputs_inspected: bool = False
    claims: list[ClaimReview] = Field(default_factory=list)

    @model_validator(mode="after")
    def inspect_only_after_seal(self):
        if self.candidate_outputs_inspected and not self.sealed:
            raise ValueError("manual review packet must be sealed before candidate inspection")
        if self.sealed and not self.sealed_at:
            raise ValueError("sealed manual review packet requires sealed_at")
        return self


class HeldoutCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    prompt_file: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_packet_file: str = Field(min_length=1)
    source_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    edge_case_categories: list[str] = Field(default_factory=list)
    model: HeldoutModelSettings | None = None
    # Flat aliases keep the JSON format convenient for hand-authored packets.
    model_identity: str | None = None
    endpoint_identity: str | None = None
    settings_snapshot: dict[str, Any] = Field(default_factory=dict)
    baseline_output: str = ""
    candidate_output: str = ""
    baseline_output_location: str = ""
    candidate_output_location: str = ""
    manual_review_status: Literal["sealed", "pending", "complete", "unavailable"] = "pending"
    fixed_reference: bool = False
    excluded_from_tuning: bool = True

    @model_validator(mode="after")
    def fixed_reference_isolation(self):
        if self.model is None:
            if not self.model_identity or not self.endpoint_identity:
                raise ValueError("model and endpoint identity are required")
            self.model = HeldoutModelSettings(model=self.model_identity,
                                              endpoint=self.endpoint_identity,
                                              settings=self.settings_snapshot)
        if not self.baseline_output:
            self.baseline_output = self.baseline_output_location
        if not self.candidate_output:
            self.candidate_output = self.candidate_output_location
        if not self.baseline_output or not self.candidate_output:
            raise ValueError("baseline and candidate output locations are required")
        if self.fixed_reference and not self.excluded_from_tuning:
            raise ValueError("fixed reference cases must be excluded from tuning")
        return self


class HeldoutManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["heldout_evidence.v1"] = "heldout_evidence.v1"
    status: Literal["unsealed", "sealed"] = "unsealed"
    manual_packet: ManualReviewPacket = Field(default_factory=ManualReviewPacket)
    cases: list[HeldoutCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_cases_and_sealing(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate held-out case ID")
        if self.status == "sealed" and not self.manual_packet.sealed:
            raise ValueError("sealed manifest requires a sealed manual packet")
        if any(case.fixed_reference and not case.excluded_from_tuning for case in self.cases):
            raise ValueError("fixed reference case is eligible for tuning")
        return self


class AcceptanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    integrity_match: bool
    criteria: dict[str, bool]
    paired_effects: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    uncertainty: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


def _resolve(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else manifest_path.parent / path


def validate_manifest(path: str | Path, *, require_sealed: bool = False) -> HeldoutManifest:
    """Load and validate a manifest and every frozen input hash."""
    manifest_path = Path(path)
    if manifest_path.suffix == ".jsonl":
        raw_rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [{
            "case_id": row["case_id"],
            "prompt_file": row["prompt_path"],
            "prompt_sha256": row["prompt_sha256"],
            "source_packet_file": row["source_packet_path"],
            "source_packet_sha256": row["source_packet_sha256"],
            "model_identity": row.get("model_identity", "declared_at_run"),
            "endpoint_identity": row.get("endpoint_identity", "declared_at_run"),
            "settings_snapshot": {"settings_sha256": row.get("settings_sha256", "declared_at_run")},
            "baseline_output_location": row["baseline_output_path"],
            "candidate_output_location": row["candidate_output_path"],
        } for row in raw_rows]
        manifest = HeldoutManifest.model_validate({"status": "unsealed", "cases": rows})
    else:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = HeldoutManifest.model_validate(data)
    if require_sealed and manifest.status != "sealed":
        raise ValueError("held-out manifest is not sealed")
    for case in manifest.cases:
        prompt = _resolve(manifest_path, case.prompt_file)
        source_packet = _resolve(manifest_path, case.source_packet_file)
        if not prompt.is_file() or file_sha256(prompt) != case.prompt_sha256:
            raise ValueError(f"prompt hash mismatch: {case.case_id}")
        if not source_packet.is_file() or file_sha256(source_packet) != case.source_packet_sha256:
            raise ValueError(f"source packet hash mismatch: {case.case_id}")
    return manifest


def validate_pair_integrity(case: HeldoutCase) -> dict[str, Any]:
    """Return the frozen-input comparison used before a paired run."""
    return {
        "case_id": case.case_id,
        "prompt_sha256": case.prompt_sha256,
        "source_packet_sha256": case.source_packet_sha256,
        "model": case.model.model,
        "endpoint": case.model.endpoint,
        "settings": case.model.settings,
        "baseline_candidate_inputs_match": True,
        "manual_packet_required": True,
    }


def evaluate_acceptance(
    baseline: list[ClaimReview], candidate: list[ClaimReview], *,
    integrity_match: bool = True, zero_source_abstentions: bool = True,
    no_new_edge_case_failure: bool = True,
    manual_packet: ManualReviewPacket | None = None,
    expected_claim_ids: list[str] | None = None,
    expected_case_ids: list[str] | None = None,
    baseline_cases: list[CaseReview] | None = None,
    candidate_cases: list[CaseReview] | None = None,
) -> AcceptanceSummary:
    """Apply the predeclared paired manual-review criteria.

    The result is a review receipt, not a production switch.  Missing labels
    remain unknown and therefore do not manufacture a pass.
    """
    old_ids = [row.claim_id for row in baseline]
    new_ids = [row.claim_id for row in candidate]
    expected_ids = list(expected_claim_ids) if expected_claim_ids is not None else None
    duplicate_rows = (len(old_ids) != len(set(old_ids)) or len(new_ids) != len(set(new_ids)))
    duplicate_expected_ids = expected_ids is not None and len(expected_ids) != len(set(expected_ids))
    missing_or_extra_rows = bool(expected_ids is not None and
                                 (set(old_ids) != set(expected_ids) or set(new_ids) != set(expected_ids)))
    paired_claim_ids_match = set(old_ids) == set(new_ids)
    old = {row.claim_id: row for row in baseline}
    new = {row.claim_id: row for row in candidate}
    ids = sorted(set(old) | set(new))

    def count(rows, predicate):
        return sum(1 for row in rows if predicate(row))

    paired_effects: dict[str, dict[str, float | int]] = {}
    uncertainty: dict[str, dict[str, float | int]] = {}
    case_integrity = True
    zero_assertion_receipts = False
    if expected_case_ids is not None:
        expected_cases = list(expected_case_ids)
        duplicate_expected_cases = len(expected_cases) != len(set(expected_cases))

        def check_cases(rows, case_rows):
            row_ids = [row.case_id for row in rows]
            case_rows = case_rows or []
            case_ids = [row.case_id for row in case_rows]
            if (duplicate_expected_cases or len(case_ids) != len(set(case_ids)) or
                    set(case_ids) != set(expected_cases)):
                return False
            if len(row_ids) != len(rows) or any(case_id is None or case_id not in expected_cases for case_id in row_ids):
                return False
            counts = {case_id: 0 for case_id in expected_cases}
            for case_id in row_ids:
                counts[case_id] += 1
            return all(case.assertion_count == counts[case.case_id] for case in case_rows)
        case_integrity = check_cases(baseline, baseline_cases) and check_cases(candidate, candidate_cases)
        all_zero = bool(expected_cases) and all(
            case.assertion_count == 0 and case.no_assertions_reason.strip()
            for cases in (baseline_cases or [], candidate_cases or [])
            for case in cases
        )
        zero_assertion_receipts = case_integrity and all_zero and not baseline and not candidate
    # Empty review inputs are valid only when both arms provide a complete,
    # explicit zero-assertion receipt for every frozen case.
    empty_without_case_receipt = (not baseline or not candidate) and not zero_assertion_receipts
    row_integrity = (not duplicate_rows and not duplicate_expected_ids and
                     not missing_or_extra_rows and paired_claim_ids_match and
                     not empty_without_case_receipt and case_integrity)
    criteria = {"integrity": bool(integrity_match),
                "review_row_integrity": row_integrity,
                "zero_source_abstentions": bool(zero_source_abstentions),
                "no_new_edge_case_failure": bool(no_new_edge_case_failure),
                "manual_packet_sealed": bool(manual_packet and manual_packet.sealed)}
    label_fields = ("source_support", "citation_alignment", "scope_adherence",
                    "identity_metadata_correctness", "abstention_correctness",
                    "useful_content_retention")
    labelled_rows_complete = bool(baseline and candidate) and all(
        all(getattr(row, field) != "unknown" for field in label_fields)
        for row in [*baseline, *candidate]
    )
    criteria["manual_labels_complete"] = labelled_rows_complete or zero_assertion_receipts
    measures = {
        "citation_mismatch_rate": lambda row: row.citation_alignment == "misaligned",
        "unsupported_claim_rate": lambda row: row.source_support == "unsupported",
        "scope_mismatch_rate": lambda row: row.scope_adherence == "mismatch",
        "abstention_incorrect_rate": lambda row: row.abstention_correctness == "incorrect",
        "useful_content_loss_rate": lambda row: row.useful_content_retention == "lost",
    }
    for name, predicate in measures.items():
        old_n = count([old[i] for i in ids if i in old], predicate)
        new_n = count([new[i] for i in ids if i in new], predicate)
        old_d = len(old)
        new_d = len(new)
        old_rate = old_n / old_d if old_d else 0.0
        new_rate = new_n / new_d if new_d else 0.0
        paired_effects[name] = {"baseline_count": old_n, "candidate_count": new_n,
                                "baseline_rate": old_rate, "candidate_rate": new_rate,
                                "rate_delta": new_rate - old_rate}
        # A bounded binomial standard-error interval is descriptive only. It
        # is retained with the receipt so small packets are not overclaimed.
        uncertainty[name] = {"baseline_n": old_d, "candidate_n": new_d,
                             "baseline_se": (old_rate * (1 - old_rate) / old_d) ** 0.5 if old_d else 0.0,
                             "candidate_se": (new_rate * (1 - new_rate) / new_d) ** 0.5 if new_d else 0.0}
        criteria[name] = new_rate <= old_rate
    new_errors = sum(len(row.newly_introduced_errors) for row in candidate)
    old_errors = sum(len(row.newly_introduced_errors) for row in baseline)
    criteria["new_errors_not_increased"] = new_errors <= old_errors
    reasons = [name for name, passed in criteria.items() if not passed]
    return AcceptanceSummary(accepted=all(criteria.values()), integrity_match=bool(integrity_match),
                             criteria=criteria, paired_effects=paired_effects,
                             uncertainty=uncertainty, reasons=reasons)


def seal_manual_packet(packet: ManualReviewPacket, sealed_at: str) -> ManualReviewPacket:
    """Return a sealed copy.  Candidate results are never added here."""
    if not sealed_at:
        raise ValueError("sealed_at is required")
    return packet.model_copy(update={"sealed": True, "sealed_at": sealed_at})


__all__ = [
    "ClaimReview", "CaseReview", "HeldoutCase", "HeldoutManifest", "HeldoutModelSettings",
    "ManualReviewPacket", "file_sha256", "seal_manual_packet", "validate_manifest",
    "validate_pair_integrity", "AcceptanceSummary", "evaluate_acceptance",
]
