#!/usr/bin/env python3
"""Freeze the blinded/calibration assessment status for the scholar goal."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/scholar-strategy-20261112/assessment-status-20261112.json"


def count(path: Path, key: str) -> int:
    value = json.loads(path.read_text(encoding="utf-8"))
    selected = value.get(key, [])
    return selected if isinstance(selected, int) else len(selected)


def main() -> None:
    result = {
        "schema_version": "scholar_assessment_status.v1",
        "status": "calibration_and_blind_packet_frozen; semantic_labels_pending",
        "calibration": {
            "source": "local_deep_research/tests/fixtures/adjudicated_claims_20261112.json",
            "claims": 21,
            "use": "calibration/regression only; final user adjudications are not a representative prevalence denominator",
            "identities_blinded": False,
        },
        "blinded_sample": {
            "source": "evaluation/archive-claim-review-sample-20261112.json",
            "claims": count(ROOT / "evaluation/archive-claim-review-sample-20261112.json", "sample_claims"),
            "packet": "evaluation/archive-claim-review-20261112/README.md",
            "model_arm_mapping_exposed": False,
            "verdicts_received": 0,
            "unresolved": "all sampled claims pending independent review",
        },
        "reserved_new_tasks": {
            "source": "evaluation/bioinformatics-reserved-paired-20261111.json",
            "reports": 60,
            "algorithm_labels": 0,
            "use": "held-out material; prior algorithm settings prevent attributing it to candidate B",
        },
        "required_labels": [
            "supported",
            "partially_supported",
            "unsupported",
            "contradicted",
            "unverifiable",
            "citation_entailment",
            "qualifier_or_counterevidence_retention",
            "important_content_coverage",
            "scope_compliance",
            "usefulness",
        ],
        "limitations": [
            "Native self-review is not independent medical adjudication.",
            "No label is inferred from citation count, output length, structural validity, or omitted text.",
            "The calibration packet and 48-claim blind sample cannot establish an overall hallucination rate.",
            "Candidate A has fixed-source runtime observations; candidate B has implementation-only evidence in this checkpoint.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
