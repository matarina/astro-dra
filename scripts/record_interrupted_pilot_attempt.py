#!/usr/bin/env python3
"""Persist the terminal state of an operator-interrupted legacy pilot arm."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/scholar-controlled-pilot-20261112/results/historical-if/supplemented"
TRACE = OUT / "traces/scholar-pilot-historical-if-supplemented"
MANIFEST = json.loads((ROOT / "evaluation/scholar-controlled-pilot-20261112/manifest.json").read_text(encoding="utf-8"))
case = next(x for x in MANIFEST["runs"] if x["case_id"] == "historical-if" and x["arm"] == "supplemented")
events = list((TRACE / next(p.name for p in (TRACE).iterdir() if p.name.startswith("synthesis-")) / "events.jsonl").read_text(encoding="utf-8").splitlines())
row = {
    "case_id": "historical-if", "arm": "supplemented", "status": "interrupted",
    "error_type": "KeyboardInterrupt", "source_sha256": hashlib.sha256((ROOT / case["source_files"]["supplemented"]).read_bytes()).hexdigest(),
    "source_file": case["source_files"]["supplemented"], "query": case["query"],
    "trace_dir": str(TRACE), "trace_event_lines": len(events),
    "partial_stage": "source_reading_request_without_response",
    "calls_persisted": False,
    "note": "Operator stopped the legacy runner at a safe boundary after the response timeout; raw synthesis trace is preserved. The legacy runner did not persist its in-memory calls list on interruption.",
}
(OUT / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(row, ensure_ascii=False))
