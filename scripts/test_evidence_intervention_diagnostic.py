#!/usr/bin/env python3
"""Regression checks for the prespecified evidence intervention diagnostic."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = json.loads((ROOT / "evaluation/scholar-strategy-20261112/evidence-intervention-diagnostic-manifest-20261112.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "evaluation/scholar-strategy-20261112/evidence-intervention-diagnostic-results-20261112.json").read_text(encoding="utf-8"))
    assert manifest["subset"]["claims"] == 21
    assert result["aggregates"]["claims"] == 21
    assert result["aggregates"]["selection_loss_labels"] == 0
    assert result["aggregates"]["draft_anchoring_labels"] == 0
    assert result["aggregates"]["document_consistency_labels"] == 0
    assert result["status"] == "visibility_stage_completed; selection_and_anchoring_unresolved"
    assert all(row["draft_anchoring"].startswith("untested") for row in result["rows"])
    print("evidence intervention diagnostic regression OK")


if __name__ == "__main__":
    main()
