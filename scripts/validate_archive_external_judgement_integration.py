#!/usr/bin/env python3
"""Validate the two-output model-assisted review integration artifact."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "evaluation/archive-claim-review-20261112"
SAMPLE = ROOT / "evaluation/archive-claim-review-sample-20261112.json"
INTEGRATION = REVIEW_DIR / "external-judgement-integration-20261112.json"


def main() -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    payload = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    expected = {(a["blind_id"], int(c["claim_id"])): c["text"] for a in sample["arms"] for c in a["claims"]}
    assert len(expected) == 48
    assert payload["status"] == "model_assisted_unadjudicated"
    claims = payload["claims"]
    assert len(claims) == 48
    actual = {(c["blind_id"], int(c["claim_id"])): c["claim_text"] for c in claims}
    assert actual == expected, "integration keys or claim text do not match sample"
    assert payload["counts"]["exact_agreement"] + payload["counts"]["disagreement"] == 48
    assert sum(payload["counts"]["integration_status"].values()) == 48
    for c in claims:
        assert c["chatgpt_pro"]["verdict"] in {"supported", "partially supported", "unsupported", "contradicted", "unverifiable"}
        assert c["grok_manual"]["verdict"] in {"supported", "partially supported", "unsupported", "contradicted", "unverifiable"}
        assert isinstance(c["agreement"], bool)
        assert c["integration_status"]
    for name in ("external-chatgpt-response-20261112.txt", "external-grok-output-20261112.txt", "external-review-prompt-20261112.txt"):
        content = (REVIEW_DIR / name).read_text(encoding="utf-8")
        assert "/data1/" not in content and "/home/" not in content, f"private path leaked into {name}"
    adjudication_path = REVIEW_DIR / "human-adjudication-20261112.json"
    if adjudication_path.is_file():
        adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
        disagreement_keys = {(c["blind_id"], int(c["claim_id"])) for c in claims if not c["agreement"]}
        adjudication_keys = {(c["blind_id"], int(c["claim_id"])) for c in adjudication.get("claims", [])}
        assert len(adjudication_keys) == 21 and adjudication_keys == disagreement_keys, "human adjudication does not cover exactly the 21 disagreements"
        assert {c["verdict"] for c in adjudication["claims"]} <= {"supported", "partially supported", "unsupported", "contradicted", "unverifiable"}
    print(json.dumps({"status": "valid", "claims": 48, "exact_agreement": payload["counts"]["exact_agreement"], "disagreement": payload["counts"]["disagreement"], "human_adjudication": 21 if adjudication_path.is_file() else 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
