"""Compare the method-first archive replay with the preserved reviewed replay.

This is an evaluation receipt only. It does not score scientific correctness
from lexical markers, and it deliberately records live-retrieval mismatches as
confounders rather than treating them as model effects.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evaluation/archive-prompt-reviewed-20261112/results"
CAND = ROOT / "evaluation/archive-prompt-method-candidate-20261112/results"
OUT = ROOT / "evaluation/archive-prompt-method-candidate-comparison-20261112.json"
TRACE_SUMMARY = ROOT / "evaluation/archive-prompt-method-candidate-review-trace-summary-20261112.json"

CASES = {
    "archive-6927b167c196": "KRAS G12C机制",
    "archive-47c54edcc0eb": "四类免疫细胞单细胞方案",
    "archive-41d13d68b84e": "RNA额外峰",
    "archive-6ac5d65ed736": "2026 IF>10/20篇/空间",
    "archive-90ad0dce1609": "中文糖尿病神经病变",
    "archive-a9b2517baf83": "脂肪空间转录组",
    "archive-6e8e8d113e76": "Xenium",
}

OBSERVATIONS = {
    "archive-6927b167c196": {"status": "report_level_boundary_preserved_but_semantics_unassessed", "note": "The candidate report retains the KRAS-GTP to RAF/MEK/ERK chain. No independent biomedical labels establish entailment or contradiction."},
    "archive-47c54edcc0eb": {"status": "general_scope_boundary_present_remaining_recommendation_risk", "note": "The report explicitly labels the four-cell workflow as a combined recommendation rather than a single-paper protocol. Population and platform assignments still require claim-level review."},
    "archive-41d13d68b84e": {"status": "evidence_boundary_preserved", "note": "The report says the supplied sources do not directly answer whether extra peaks imply bacterial contamination or whether sequencing should proceed, then labels follow-up checks as decision support."},
    "archive-6ac5d65ed736": {"status": "metadata_and_count_boundary_preserved", "note": "The report keeps IF unknown, refuses to claim the requested 20-paper set, and keeps platform/group/sample gaps visible. It does not satisfy the requested count."},
    "archive-90ad0dce1609": {"status": "language_scope_disclosed_strict_only_unresolved", "note": "The report identifies one Chinese source and labels the English material as supplemental. Strict Chinese-only fulfillment remains unresolved."},
    "archive-a9b2517baf83": {"status": "scope_disclosed_semantic_precision_unassessed", "note": "The report preserves unknown IF and separates study types, but the live source pool still contains secondary/background material and no independent spatial-relevance labels."},
    "archive-6e8e8d113e76": {"status": "identity_and_platform_disclosed_semantics_unassessed", "note": "The report preserves platform limitations and preprint status. Claim support and contradiction were not independently adjudicated."},
}
TRACE_ROWS = json.loads(TRACE_SUMMARY.read_text())["rows"] if TRACE_SUMMARY.exists() else {}


def summary(path: Path) -> dict:
    value = json.loads((path / "summary.json").read_text())
    report = (path / "report.md").read_text(errors="replace")
    sources = json.loads((path / "sources.json").read_text()) if (path / "sources.json").exists() else []
    ids = [str(item.get("index")) for item in sources]
    urls = [str(item.get("link") or item.get("url") or "") for item in sources]
    value.update({
        "citation_occurrences": len(re.findall(r"\[\[\d+\]\]", report)),
        "source_id_duplicates": len(ids) - len(set(ids)),
        "source_url_duplicates": len(urls) - len(set(urls)),
        "numeric_if_mentions": len(re.findall(r"\bIF\s*[=:>]?\s*\d", report, flags=re.I)),
        "unknown_if_mentions": report.lower().count("impact-factor metadata"),
    })
    return value


def row(case_id: str) -> dict:
    base_id = next((p for p in BASE.iterdir() if p.name.endswith(case_id)), None)
    cand_id = next((p for p in CAND.iterdir() if p.name.endswith(case_id)), None)
    if base_id is None or cand_id is None:
        raise FileNotFoundError(case_id)
    b, c = summary(base_id), summary(cand_id)
    trace = TRACE_ROWS.get(case_id, {})
    c.update(trace)
    return {
        "case": case_id,
        "label": CASES[case_id],
        "baseline": b,
        "method_candidate": c,
        "deltas": {
            "elapsed_s": round(c.get("elapsed_s", 0) - b.get("elapsed_s", 0), 3),
            "source_pool": c.get("source_pool", 0) - b.get("source_pool", 0),
            "references": c.get("references", 0) - b.get("references", 0),
            "report_chars": c.get("report_chars", 0) - b.get("report_chars", 0),
        },
        "observation": OBSERVATIONS[case_id],
        "confounders": [
            "Retrieval was live and not source-frozen; source pools are not matched.",
            "The candidate changes a general grounding contract, but native review and the same model are not independent semantic adjudicators.",
            "Citation count, report length, completion and latency are not hallucination measures.",
        ],
    }


result = {
    "schema_version": "archive_prompt_method_first_comparison.v1",
    "status": "evaluation_only",
    "prompt_source": "LDR第二次调研.rar",
    "candidate": "generic proposal/attribution grounding contract in generation.py",
    "policy": {
        "model": "deepseek-v4-flash",
        "search_tool": "pubmed",
        "iterations": 10,
        "questions_per_iteration": 2,
        "general.enable_fact_checking": True,
        "save_time_citation_qc": False,
        "production_changed": False,
    },
    "rows": [row(case_id) for case_id in CASES],
    "interpretation": [
        "All seven candidate runs completed without research_error under the recorded isolated configuration.",
        "The two arms are not a causal paired comparison because retrieval was live and source pools differ.",
        "The candidate improves explicit evidence-boundary wording on several prompts, but independent unsupported/contradicted and citation-entailment labels are absent.",
        "Overall hallucination reduction and cross-domain usefulness remain unproven.",
    ],
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(OUT)
