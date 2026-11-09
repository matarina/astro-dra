"""Reproduce citation QC coverage gaps without calling a real model.

Run from the repository root with research_verify's test dependencies installed:
  PYTHONPATH=local_deep_research python docs/evidence/abstract_summary_probe.py

The deliberately fabricated judge response tests validation, not model accuracy.
JSON is written to stdout; this script does not modify the application or data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import runpy
import subprocess

from research_verify.citation_qc import CitationQc, Claim


class Collector:
    def __init__(self, items):
        self.items = items

    def find_by_index(self, index):
        return self.items.get(index)


class SyntheticJudge:
    prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = json.dumps({
                "verdict": "supported",
                "supporting_fragment": "THIS QUOTE DOES NOT EXIST",
                "reason": "synthetic response for validation probe",
            })

        return Response()


def main():
    root = Path(__file__).resolve().parents[2]
    source = root / "local_deep_research/research_verify/citation_qc.py"
    judge = SyntheticJudge()
    qc = CitationQc(judge_model=judge)
    claim = Claim("A finding [1]", [1])

    report = "The method improves accuracy [1].\nAn uncited invented conclusion."
    claims = qc.extract_claims(report)
    probes = [{
        "id": "uncited_claim_coverage",
        "observed": {"extracted": [c.text for c in claims]},
        "gap_reproduced": not any("uncited" in c.text for c in claims),
    }]

    qc.check([claim], Collector({1: {"full_content": "x" * 1700 + " LATE_RESULT_314159"}}))
    visible = "LATE_RESULT_314159" in judge.prompt
    probes.append({
        "id": "evidence_after_1500_characters",
        "observed": {"late_evidence_visible": visible},
        "gap_reproduced": not visible,
    })

    check = qc.check([claim], Collector({1: {"abstract": "Actual source has no such quote."}}))[0]
    probes.append({
        "id": "fabricated_supporting_quote",
        "observed": {"verdict": check.verdict, "quote": check.supporting_fragment},
        "gap_reproduced": check.verdict == "supported" and check.supporting_fragment == "THIS QUOTE DOES NOT EXIST",
    })

    qc.check([claim], Collector({1: {"abstract": "ABSTRACT_MARKER", "body": "BODY_EVIDENCE_MARKER"}}))
    body_visible = "BODY_EVIDENCE_MARKER" in judge.prompt
    probes.append({
        "id": "abstract_preferred_over_body",
        "observed": {"abstract_visible": "ABSTRACT_MARKER" in judge.prompt, "body_visible": body_visible},
        "gap_reproduced": not body_visible,
    })

    namespace = runpy.run_path(str(root / "local_deep_research/tests/test_citation_qc.py"))
    passed = []
    for name, function in sorted(namespace.items()):
        if name.startswith("test_") and callable(function):
            function()
            passed.append(name)

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "python_version": platform.python_version(),
        "source": str(source.relative_to(root)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "deterministic probes with a synthetic judge; no model accuracy or end-to-end evaluation",
        "probes": probes,
        "existing_tests": {"runner": "direct invocation of test functions, not pytest", "passed": passed, "count": len(passed)},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
