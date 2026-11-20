#!/usr/bin/env python3
"""Prepare the corrected nonempty-draft and genuinely-new-task pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "evaluation/scholar-controlled-pilot-20261112"
OUT = ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112"
INPUT = OUT / "inputs"
EXTERNAL = Path("/data1/maxw/ldr-evaluation/bioinformatics-retrieval-20261111/source-packs")


def copy_input(source: Path, target: Path) -> str:
    target.write_bytes(source.read_bytes())
    return hashlib.sha256(target.read_bytes()).hexdigest()


def main() -> None:
    raise RuntimeError("Deprecated: its certolizumab/DEE validation labels were corrected. Use prepare_scholar_new_validation_v2.py; preserve existing v1 receipts.")
    OUT.mkdir(parents=True, exist_ok=True); INPUT.mkdir(parents=True, exist_ok=True)
    old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    historical = ["historical-immune", "historical-if", "historical-adipose"]
    runs = []
    draft_bindings = []
    for case_id in historical:
        old_case = next(x for x in old_manifest["runs"] if x["case_id"] == case_id)
        base_src = ROOT / old_case["source_files"]["base"]
        supp_src = ROOT / old_case["source_files"]["supplemented"]
        base_target = INPUT / f"{case_id}-base.json"; supp_target = INPUT / f"{case_id}-supplemented.json"
        base_sha = copy_input(base_src, base_target); supp_sha = copy_input(supp_src, supp_target)
        draft_src = OLD / "results" / case_id / "baseline" / "report.md"
        if not draft_src.exists() and case_id == "historical-adipose":
            # This prior fixed-source report used the same case-6 source pack;
            # retain its provenance rather than inventing a missing draft.
            draft_src = ROOT / "evaluation/fixed-source-role-20261112/baseline/report.md"
        if not draft_src.exists(): raise FileNotFoundError(draft_src)
        draft_target = INPUT / f"{case_id}-inherited-draft.md"; draft_sha = copy_input(draft_src, draft_target)
        draft_bindings.append({"case_id": case_id, "source_sha256": base_sha, "draft_sha256": draft_sha, "draft_chars": len(draft_target.read_text(encoding="utf-8"))})
        query = old_case["query"]
        for arm in ("baseline_with_draft", "candidate_a_with_draft", "candidate_b_draft_removed", "supplemented_with_draft"):
            runs.append({"case_id": case_id, "query": query,
                         "source_files": {"base": str(base_target.relative_to(ROOT)), "supplemented": str(supp_target.relative_to(ROOT))},
                         "draft_files": {"default": str(draft_target.relative_to(ROOT)),
                                         "baseline_with_draft": str(draft_target.relative_to(ROOT)),
                                         "candidate_a_with_draft": str(draft_target.relative_to(ROOT)),
                                         "supplemented_with_draft": str(draft_target.relative_to(ROOT))},
                         "arm": arm})

    # These two families were frozen as reserved source packs but were not part
    # of the earlier report-generation/assessment runs (patatin and Dst1 are
    # intentionally excluded because the supervisor identified them as already
    # evaluated).
    new = [
        ("new-certolizumab", "f_ea0305f6eefa", "Show results of randomised controlled trials for certolizumab pegol. Write an evidence-grounded research report of about 700 words with citations, useful synthesis, limitations and one bounded next research step."),
        ("new-xlinked-epilepsy", "f_5bfd4ff2a26d", "Missense mutations in which genes cause X-linked developmental and epileptic encephalopathy? Write an evidence-grounded research report of about 700 words with citations, useful synthesis, limitations and one bounded next research step."),
    ]
    new_records = []
    for case_id, stem, query in new:
        src = EXTERNAL / f"{stem}.json"
        if not src.exists(): raise FileNotFoundError(src)
        target = INPUT / f"{case_id}-base.json"; sha = copy_input(src, target)
        new_records.append({"case_id": case_id, "source_sha256": sha, "source_path": str(target.relative_to(ROOT)), "prior_report_generation": False})
        for arm in ("baseline_empty", "candidate_a_empty", "candidate_b_empty"):
            runs.append({"case_id": case_id, "query": query,
                         "source_files": {"base": str(target.relative_to(ROOT)), "supplemented": str(target.relative_to(ROOT))},
                         "draft_files": {}, "arm": arm})

    manifest = {
        "schema_version": "scholar_controlled_pilot_corrected.v1",
        "status": "frozen_before_corrected_outputs",
        "supersedes": str((OLD / "manifest.json").relative_to(ROOT)),
        "model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 5000,
        "native_fact_consistency": True, "max_review_calls": 6,
        "live_search": False, "body_fetch": False, "save_time_citation_qc": False,
        "historical_cases": historical, "new_cases": [x[0] for x in new],
        "arms": {
            "baseline_with_draft": "same nonempty inherited pilot draft and base evidence",
            "candidate_a_with_draft": "same draft/evidence plus quote-backed source-reading roles",
            "candidate_b_draft_removed": "same base evidence, inherited draft withheld, fresh synthesis enabled",
            "supplemented_with_draft": "same inherited draft plus deliberate primary full-text evidence intervention",
            "baseline_empty": "new task, no inherited draft",
            "candidate_a_empty": "new task, quote-backed source-reading roles, no inherited draft",
            "candidate_b_empty": "new task, fresh synthesis, no inherited draft; no anchoring claim",
        },
        "draft_bindings": draft_bindings,
        "new_task_bindings": new_records,
        "runs": runs,
        "controls": [
            "Historical baseline/A/B use the same source file and same nonempty pilot draft hash; only roles/fresh-draft settings differ.",
            "Supplemented historical arm deliberately changes writer-visible evidence and is not a retrieval comparison.",
            "New task arms are validation of current code on reserved families not previously used for report-generation assessment.",
            "All attempted, completed and failed API calls must retain result.json, calls.json and trace metadata.",
        ],
        "assessment_frozen_before_outputs": {
            "claim_labels": ["supported", "partially_supported", "unsupported", "contradicted", "unverifiable"],
            "additional_axes": ["citation_entailment", "qualifier_retention", "important_content_coverage", "scope_compliance", "usefulness"],
            "blinding": "assessment packets omit arm labels; unresolved remains explicit",
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": len(runs), "historical": historical, "new": new_records, "drafts": draft_bindings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
