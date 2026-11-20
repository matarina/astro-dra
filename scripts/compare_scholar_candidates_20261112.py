#!/usr/bin/env python3
"""Record the two scholar candidates without treating mechanics as quality."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIR = ROOT / "evaluation/hallucination-steering-20261112/fixed-paired-comparison-v2.json"
OUT = ROOT / "evaluation/scholar-strategy-20261112/candidate-comparison-20261112.json"


def structural_counts(report: Path) -> dict:
    text = report.read_text(encoding="utf-8", errors="replace")
    # This is a Markdown-coordinate inventory only: it does not interpret
    # scientific words or infer support from lexical overlap.
    return {
        "report_chars": len(text),
        "headings": len(re.findall(r"(?m)^#{1,6}\s+", text)),
        "table_rows": sum(1 for line in text.splitlines() if line.lstrip().startswith("|") and not set(line.strip()) <= {"|", "-", ":", " "}),
    }


def main() -> None:
    pair = json.loads(PAIR.read_text(encoding="utf-8"))
    rows = []
    for row in pair["rows"]:
        baseline = ROOT / "evaluation/hallucination-steering-20261112" / row["baseline"]["report"]
        candidate_a = ROOT / "evaluation/hallucination-steering-20261112" / row["candidate"]["report"]
        rows.append({
            "case": row["case"],
            "source_sha256": row["source_sha256"],
            "baseline": structural_counts(baseline),
            "candidate_a_quote_backed_units": structural_counts(candidate_a),
            "candidate_b_fresh_synthesis": {
                "implementation": "citation.fresh_evidence_synthesis plus source-mapped structural spans in native review",
                "default": False,
                "live_model_run": False,
                "reason_not_run": "This checkpoint avoids unplanned additional API calls; the mode is reversible and requires a separately frozen paired run.",
                "prompt_contract_smoke": "implemented and covered by test_document_consistency_candidate.py / fresh-synthesis regression",
            },
            "semantic_labels": 0,
        })
    result = {
        "schema_version": "scholar_candidate_comparison.v1",
        "status": "candidate_a_executed_candidate_b_implementation_only",
        "candidates": {
            "A": {
                "name": "quote-backed evidence-unit plan",
                "setting": "citation.enable_source_reading_roles=true",
                "hypothesis": "Exact source/offset quotes plus qualifier context may reduce selection/attribution loss without changing retrieval.",
                "evidence": "fixed-paired-comparison-v2.json",
            },
            "B": {
                "name": "fresh evidence-conditioned synthesis with document consistency diagnostics",
                "setting": "citation.fresh_evidence_synthesis=true; structural spans passed to native review",
                "hypothesis": "Withholding a previous draft may reduce anchoring, while cross-location structural context can expose heading/table/body mismatches without automatic deletion.",
                "evidence": "implementation and contract smoke only; no semantic model comparison yet",
            },
        },
        "rows": rows,
        "heldout_reference": {
            "artifact": "evaluation/bioinformatics-reserved-paired-20261111.json",
            "reports": 60,
            "use": "reserved evidence/context for future blinded assessment",
            "attribution": "not attributable to candidate B; prior settings and algorithm snapshot differ",
        },
        "interpretation": [
            "Candidate A has a real fixed-source runtime comparison, but no independent semantic labels and a material report-coverage risk.",
            "Candidate B is implemented as an opt-in path and mechanically checked, but has not been run against a model in this checkpoint; no quality claim is made.",
            "Structural spans, quote existence, report length, citation count and native self-review are not hallucination measures.",
            "The correct decision is defer adoption until a frozen A/B/held-out run supplies blinded claim-level support, contradiction, citation entailment, qualifier retention and usefulness labels.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
