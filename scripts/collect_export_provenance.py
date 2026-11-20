"""Verify frozen export fixtures, installed bytes, tests and temporary storage."""
import hashlib
import json
from pathlib import Path
import re
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    result = {"root": str(root), "overall_effectiveness": "unproven", "scientific_model_calls": 0}
    cases = json.loads((root / "cases.json").read_text())
    for arm in ["baseline", "candidate"]:
        data = json.loads((root / (arm + "-final-probe.json")).read_text())
        manifest = json.loads((root / (arm + "-code-hashes.json")).read_text())
        for name, expected in manifest.items():
            if sha(root / (arm + "-code") / name) != expected:
                raise ValueError("Frozen export code changed")
        for path, actual in data["installed"].items():
            name = "local_deep_research/overlay/" + Path(path).name
            if name in manifest and actual != manifest[name]:
                raise ValueError("Installed wrapper mismatch")
        if arm == "candidate" and data["helper_sha256"] != manifest["local_deep_research/research_verify/quarto_sources.py"]:
            raise ValueError("Installed helper mismatch")
        rows = data["rows"]
        if [r["case_id"] for r in rows] != [c["id"] for c in cases]:
            raise ValueError("Case IDs changed")
        result[arm] = {"url_contracts": sum(r["entries"] == c["expected"] for r, c in zip(rows, cases)),
                       "cases": len(cases), "invented_quarto_year2024": sum(r["invented_year2024"] for r in rows),
                       "ris_cases_with_unsupplied_metadata": sum(bool(re.search(r"(?m)^(?:Y1|PY|DA|LA|PB)  -", r["ris"])) for r in rows)}
    text = (root / "candidate-tests.log").read_text()
    summary = re.search(r"(\d+) failed, (\d+) passed", text)
    result["candidate_tests"] = {"passed": int(summary[2]), "failed": int(summary[1])}
    before = (root / "baseline-tests.log").read_text()
    names = lambda text: {line.split("::", 1)[1] for line in text.splitlines() if line.startswith("FAILED ")}
    if names(text) != names(before):
        raise ValueError("New unresolved failures")
    result["same37_failures_as_pre_export_candidate"] = True
    before_compat = json.loads((root / "before-citations-compatibility.json").read_text())
    after_compat = json.loads((root / "after-citations-compatibility.json").read_text())
    result["conventional_citations_label_followup"] = {"before_matches": sum(x["matches"] for x in before_compat),
        "after_matches": sum(x["matches"] for x in after_compat), "cases": len(after_compat),
        "scientific_comparison_includes_this_followup": False}
    compatibility = json.loads((root / "current-parser-science-publication-validation.json").read_text())
    if len(compatibility) != 104 or not all(x["valid"] and x["metadata_unchanged"] for x in compatibility):
        raise ValueError("Preserved science publication validation loss")
    result["preserved_science_publications_validated_without_mutation"] = 104
    storage = json.loads((root / "candidate-storage-final.log").read_text().splitlines()[-1])
    if not storage["checks_passed"] or len(storage["modes"]) != 2 or not storage["old_report_view_fixed_without_write"]:
        raise ValueError("Incomplete storage/export check")
    result["storage_and_exports"] = storage
    result["limitations"] = ["Syntax fixtures and temporary storage/export checks, not scientific citation entailment.",
        "Quarto ZIP/BibTeX checked, not rendered by Quarto; five formats returned bytes, only Quarto/RIS structured URL/key fields checked.",
        "37 legacy audit/scope/fixture failures remain red.",
        "Conventional bibliography grammar is limited; unfamiliar formats remain text but may lack structured records.",
        "Additional supplied entry text is retained as literal notes, not interpreted into verified author/year/publication fields.",
        "LaTeX/PDF/ODT bibliographic inference not exhaustively audited; no identity, peer review or truth certification."]
    result["artifact_sha256"] = {name: sha(root / name) for name in ["protocol.json", "cases.json", "ris-addendum-before-edits.json",
        "raw-notes-design.json", "candidate-code-hashes.json", "baseline-code-hashes.json", "candidate-final-probe.json", "baseline-final-probe.json",
        "candidate-tests.log", "baseline-tests.log", "candidate-storage-final.log", "test-contract-correction.json", "storage-policy-correction.json",
        "citations-compatibility-protocol.json", "before-citations-compatibility.json", "after-citations-compatibility.json",
        "current-parser-science-publication-validation.json", "probe-measurement-note.json"]}
    return result


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/data1/maxw/ldr-evaluation/export-provenance-20261111")
    result = collect(root)
    (root / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    Path("evaluation/export-provenance-results-20261111.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k in ["baseline", "candidate", "candidate_tests", "overall_effectiveness"]}))
