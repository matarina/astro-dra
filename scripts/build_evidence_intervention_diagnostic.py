#!/usr/bin/env python3
"""Freeze the evidence-intervention diagnostic before any new model run.

This diagnostic classifies what the archived writer packet exposed and what an
independently adjudicated source link could add. It does not treat the
adjudicator's evidence note as a model result, and it leaves draft-removal
untested until a separately approved paired call is run.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "local_deep_research/tests/fixtures/adjudicated_claims_20261112.json"
ADJUDICATION = ROOT / "evaluation/archive-claim-review-20261112/human-adjudication-20261112.json"
PACKET = ROOT / "evaluation/archive-claim-review-packet-20261112.json"
OUT_DIR = ROOT / "evaluation/scholar-strategy-20261112"
MANIFEST = OUT_DIR / "evidence-intervention-diagnostic-manifest-20261112.json"
RESULTS = OUT_DIR / "evidence-intervention-diagnostic-results-20261112.json"


def _arm_claim(arm: dict, claim_id: int | str) -> dict | None:
    for claim in arm.get("claims", []):
        if str(claim.get("claim_id")) == str(claim_id):
            return claim
    return None


def _visibility(scope: str) -> str:
    if scope == "missing_source_record":
        return "writer_source_record_missing"
    if "methods_unseen" in scope or scope in {"abstract_only", "abstract_only_spatial_unseen"}:
        return "decisive_detail_not_in_writer_view"
    if "partial" in scope or "excerpts" in scope:
        return "partial_writer_view"
    return "writer_view_scope_recorded"


def build() -> tuple[dict, dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    fixture_by_key = {(x["blind_id"], str(x["claim_id"])): x for x in fixture["cases"]}
    adjudicated_by_key = {(x["blind_id"], str(x["claim_id"])): x for x in adjudication["claims"]}
    arms = {arm["blind_id"]: arm for case in packet["cases"] for arm in case["arms"]}

    rows = []
    for key, case in sorted(fixture_by_key.items()):
        blind_id, claim_id = key
        arm = arms.get(blind_id, {})
        packet_claim = _arm_claim(arm, claim_id) or {}
        adjudicated = adjudicated_by_key.get(key, {})
        records = packet_claim.get("source_records") or []
        rows.append({
            "blind_id": blind_id,
            "claim_id": int(claim_id) if claim_id.isdigit() else claim_id,
            "claim_text": case.get("claim_text", ""),
            "scientific_verdict": case.get("scientific_verdict"),
            "writer_evidence_scope": case.get("writer_evidence_scope"),
            "writer_visibility_observation": _visibility(case.get("writer_evidence_scope", "")),
            "writer_cited_source_ids": packet_claim.get("citations", []),
            "writer_source_record_count": len(records),
            "writer_source_records_with_body": sum(bool(x.get("fetched_content") or x.get("full_content")) for x in records),
            "decisive_evidence_links_available": adjudicated.get("links", []),
            "adjudicator_evidence_note_present": bool(adjudicated.get("evidence")),
            "selection_loss": "unresolved_without matched supplemented-material writer call",
            "draft_anchoring": "untested; requires same evidence with inherited draft removed",
            "scientific_misreading": "unresolved by this diagnostic; verdict is preserved separately",
            "document_consistency": "untested for this claim instance",
        })

    manifest = {
        "schema_version": "evidence_intervention_diagnostic_manifest.v1",
        "status": "prespecified_archived_packet; no_new_model_calls",
        "subset": {
            "source": str(FIXTURE.relative_to(ROOT)),
            "claims": len(rows),
            "selection": "all 21 user-adjudicated regression claims, stratified by writer evidence scope and scientific verdict",
            "identities": "blind IDs retained; model/algorithm arm is not used as a diagnostic label",
        },
        "arms": [
            {"id": "current_writer_material", "material": "archived writer-visible source records and excerpts", "model_calls": 0},
            {"id": "decisive_evidence_supplement", "material": "independently adjudicated primary-source links/notes, injected only for diagnosis", "model_calls": 0, "causal_quality_claim": False},
            {"id": "draft_removed", "material": "same writer material with inherited draft withheld", "model_calls": 0, "status": "pending_separate_frozen_model_run"},
        ],
        "controls": {
            "model": "not run in this diagnostic checkpoint",
            "source_pool": "archived packet only; no live retrieval",
            "output_budget": "must be matched in any future run",
            "review_budget": "must be matched in any future run",
            "production_changed": False,
        },
        "measurements": [
            "writer evidence visibility and source-record/body availability",
            "supported/partially supported/unsupported/contradicted/unverifiable claim labels",
            "selection loss under decisive supplementation",
            "draft anchoring under inherited-draft removal",
            "document consistency across heading/table/summary/body",
            "important-content coverage and usefulness",
            "latency/tokens/tool calls and memory",
        ],
        "limits": [
            "The 21 adjudications are calibration/regression labels, not a representative prevalence sample.",
            "A source link or adjudicator evidence note is not a same-model generation result.",
            "No claim about intervention effectiveness is made until matched writer calls and blinded assessment exist.",
        ],
    }
    result = {
        "schema_version": "evidence_intervention_diagnostic_results.v1",
        "status": "visibility_stage_completed; selection_and_anchoring_unresolved",
        "manifest_sha256": hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "rows": rows,
        "aggregates": {
            "claims": len(rows),
            "scientific_verdicts": dict(collections.Counter(x["scientific_verdict"] for x in rows)),
            "writer_visibility": dict(collections.Counter(x["writer_visibility_observation"] for x in rows)),
            "writer_source_record_missing": sum(x["writer_source_record_count"] == 0 for x in rows),
            "writer_records_with_body": sum(x["writer_source_records_with_body"] > 0 for x in rows),
            "decisive_links_available": sum(bool(x["decisive_evidence_links_available"]) for x in rows),
            "selection_loss_labels": 0,
            "draft_anchoring_labels": 0,
            "document_consistency_labels": 0,
        },
        "interpretation": [
            "The archived packet confirms multiple writer-view limitations, including abstract-only and missing-record cases.",
            "The scientific verdict distribution is preserved for calibration and regression; it is not an intervention score.",
            "Selection loss, draft anchoring and document inconsistency remain unresolved because no matched supplemented-material or draft-removed writer calls were run here.",
            "No hallucination-rate reduction is inferred from this diagnostic.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RESULTS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, result


if __name__ == "__main__":
    manifest, result = build()
    print(json.dumps(result["aggregates"], ensure_ascii=False, sort_keys=True))
