"""Build the read-only Pane 2 full-feedback inventory and candidate audit.

This script consumes frozen ledger/receipt files and writes only Pane 2 artifacts.
It does not run models, alter production, or score a candidate as a scientific win.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/pane2-independent-review-20261113"
OUT.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = ROOT / "evaluation/scholar-strategy-20261112/full-feedback-coverage-ledger.json"
LEDGER = json.loads(LEDGER_PATH.read_text())
ARCHIVE_SHA = LEDGER["archive_sha256"]
CHECKED = "2026-11-13T02:45:00Z"

def digest(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def write(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

TASKS = {t["task_id"]: t for t in LEDGER["tasks"]}
TOPICS = {r["row_id"]: r for r in LEDGER["topic_feedback_rows"]}
XENIUM = {r["row_id"]: r for r in LEDGER["xenium_details"]}

def source_row(row_id: str) -> dict:
    r = TOPICS[row_id]
    return {
        "row_id": r["row_id"],
        "task_id": r["task_id"],
        "workbook": r["workbook"],
        "sheet": r["sheet"],
        "row": r["row"],
        "feedback": r["feedback"],
        "expected_effect": r.get("cells", {}).get("预期效果(正确结论)", ""),
        "checked_count_note": r.get("cells", {}).get("本次测试报告中核对的条数", ""),
        "diagnostic_triage": r.get("diagnostic_triage", []),
        "assessment_status": r.get("assessment_status"),
        "overlap_links": r.get("overlap_links", []),
        "row_sha256": digest(r),
    }

# The issue universe is frozen before any candidate quality score. Rows with the
# same underlying failure are merged; clearly independent clauses are split.
ISSUE_DEFS = [
    ("issue-01", "task-47c54edcc0eb", ["topic-01"], "source_specific_method", "Source [3] eosinophil FACS marker strategy", "One source-specific sorting method; independently checkable."),
    ("issue-02", "task-47c54edcc0eb", ["topic-02"], "source_specific_method", "Source [8] eosinophil magnetic-bead marker strategy", "One source-specific enrichment method; independently checkable."),
    ("issue-03", "task-47c54edcc0eb", ["topic-03"], "source_specific_method", "Source [10] basophil sorting strategy", "One source-specific enrichment method; independently checkable."),
    ("issue-04", "task-47c54edcc0eb", ["topic-04"], "source_specific_method", "Source [9] basophil FACS strategy", "One source-specific sorting method; independently checkable."),
    ("issue-05", "task-47c54edcc0eb", ["topic-05"], "source_specific_method", "Source [12] mast-cell sorting strategy", "One source-specific sorting method; independently checkable."),
    ("issue-06", "task-47c54edcc0eb", ["topic-06"], "source_specific_method", "Source [16] mast-cell sorting strategy", "One source-specific sorting method; independently checkable."),
    ("issue-07", "task-47c54edcc0eb", ["topic-07", "topic-08"], "technology_taxonomy", "Sequencing technologies/workflows/read length were labeled as platforms, including summary-table errors", "Rows 7 and 8 point to the same platform/type conflation across prose and table; merged to avoid double counting."),
    ("issue-08", "task-41d13d68b84e", ["topic-09"], "missing_claim_or_misinterpretation", "Low-level bacterial contamination consumes reads but usually does not greatly lower mapping rate", "One QC interpretation allegation; source adjudication is still required."),
    ("issue-09", "task-6ac5d65ed736", ["topic-10"], "metadata_request_fulfillment", "Paper with IF 4 included despite IF >10", "One paper eligibility allegation."),
    ("issue-10", "task-6ac5d65ed736", ["topic-11"], "metadata_request_fulfillment", "Paper with IF 9.5 included despite IF >10", "One paper eligibility allegation."),
    ("issue-11", "task-6ac5d65ed736", ["topic-12"], "metadata_request_fulfillment", "Paper with IF 1.9 included despite IF >10", "One paper eligibility allegation."),
    ("issue-12", "task-6ac5d65ed736", ["topic-15"], "metadata_request_fulfillment", "Paper with IF 4.6 included despite IF >10", "One paper eligibility allegation."),
    ("issue-13", "task-6ac5d65ed736", ["topic-13"], "requested_field_omission", "Group design and sample counts were not extracted for a paper where the supplied review says they were present", "One source-specific requested-field omission."),
    ("issue-14", "task-6ac5d65ed736", ["topic-14"], "requested_field_omission", "Group design and sample counts were not extracted for a second paper", "One source-specific requested-field omission."),
    ("issue-15", "task-90ad0dce1609", ["topic-16"], "scope_request_fulfillment", "Chinese-only request included many English journal articles", "One language-scope allegation."),
    ("issue-16", "task-90ad0dce1609", ["topic-17"], "source_identity_and_entailment", "Non-academic/web source was used for key efficacy data", "First independently checkable source-quality/claim-support clause from topic 17."),
    ("issue-17", "task-90ad0dce1609", ["topic-17"], "source_identity_and_entailment", "Hanspub review was used as a main mechanism/treatment authority", "Second independently checkable source-quality/claim-support clause from topic 17."),
    ("issue-18", "task-90ad0dce1609", ["topic-18"], "identity_link_mismatch", "Citation [33] link points to a different guideline PDF", "One bibliographic identity/link allegation."),
    ("issue-19", "task-90ad0dce1609", ["topic-19"], "ontology_translation", "Paraptosis was translated as necroptosis", "One ontology/entity relation allegation; the original wording already includes candidate status, so no extra qualifier issue is counted."),
    ("issue-20", "task-90ad0dce1609", ["topic-20"], "evidence_availability_and_identity", "Two cited URLs are inaccessible or return errors", "One source-access allegation retained as unresolved until source identity/content is checked."),
    ("issue-21", "task-a9b2517baf83", ["topic-21"], "identity_link_mismatch", "SLACS title/link/method/sample description allegedly mismatched or fabricated", "One identity allegation; frozen source review must distinguish absent evidence from false identity."),
    ("issue-22", "task-a9b2517baf83", ["topic-22"], "deduplication", "Repeated papers/citations inflated apparent evidence count", "Four duplicate groups are retained in provenance but grouped as one deduplication issue in the primary denominator."),
    ("issue-23", "task-a9b2517baf83", ["topic-23"], "ontology_translation", "hEOS end-of-trajectory signature was misread as endothelial", "One terminology/entity interpretation allegation."),
    ("issue-24", "task-a9b2517baf83", ["topic-24"], "identity_link_mismatch", "Same DOI was assigned three different journal identities", "One document-consistency/identity issue."),
    ("issue-25", "task-a9b2517baf83", ["topic-25"], "bibliographic_metadata", "Year and first-author attribution were wrong for a cited study", "One bibliographic metadata issue."),
    ("issue-26", "task-a9b2517baf83", ["topic-26"], "scope_misrepresentation", "Subcutaneous-only adipose sampling was expanded to subcutaneous plus visceral", "One population/sample-scope issue."),
    ("issue-27", "task-6e8e8d113e76", ["topic-28"], "identity_metadata", "PMC was presented as a journal and year was wrong", "One source identity/year clause."),
    ("issue-28", "task-6e8e8d113e76", ["topic-28"], "identity_metadata", "eLife publication year was wrong", "Independent year clause from topic 28."),
    ("issue-29", "task-6e8e8d113e76", ["topic-29"], "identity_and_scope", "SAGE Journals was presented as journal and cancer scope was wrong", "Independent source-type and content clause from topic 29."),
    ("issue-30", "task-6e8e8d113e76", ["topic-29"], "publication_state", "SITC 2024 conference abstract was presented as a formal research paper", "Independent publication-state clause from topic 29."),
    ("issue-31", "task-6e8e8d113e76", ["topic-30"], "deduplication", "One paper was split into multiple citations", "One citation deduplication issue; detail rows provide multiple examples."),
    ("issue-32", "task-6e8e8d113e76", ["topic-31"], "publication_state_and_source_type", "Official/vendor/blog/institute pages were counted as published literature", "One source-type/publication-state issue."),
    ("issue-33", "task-6e8e8d113e76", ["topic-32"], "unsupported_scope_claim", "Largest-scale claim lacked original-text support", "Independent unsupported scale clause from topic 32."),
    ("issue-34", "task-6e8e8d113e76", ["topic-32"], "unsupported_scope_claim", "Cross-cancer sample composition claim lacked original-text support", "Independent unsupported cancer-scope clause from topic 32."),
]

issues = []
for issue_id, task_id, row_ids, category, allegation, basis in ISSUE_DEFS:
    rows = [source_row(rid) for rid in row_ids]
    issues.append({
        "issue_id": issue_id,
        "task_id": task_id,
        "category": category,
        "atomic_allegation": allegation,
        "distinctness_basis": basis,
        "source_row_ids": row_ids,
        "source_rows": rows,
        "original_task_prompt_sha256": text_sha(TASKS[task_id]["prompt"]),
        "status": "unresolved_unadjudicated",
        "candidate_status": "not_scored",
        "counting": {"primary_denominator": True, "substantiated_hallucination": None, "correction": None},
    })

# Xenium rows are linked audit evidence, never additive denominator units.
def map_xenium(problem: str) -> str:
    p = problem
    if "PMC" in p or "年份错误" in p:
        return "issue-27/issue-28"
    if "SAGE" in p or "癌种内容错误" in p:
        return "issue-29"
    if "会议摘要" in p:
        return "issue-30"
    if "非文献" in p or "正式出处" in p:
        return "issue-32"
    if "规模最大" in p or "癌种描述" in p or "研究类型描述" in p:
        return "issue-33/issue-34"
    if "重复计数" in p or "编号重复" in p:
        return "issue-31"
    return "positive_or_uncertain_control"

overlap_details = []
for x in LEDGER["xenium_details"]:
    overlap_details.append({
        "row_id": x["row_id"], "workbook": x["workbook"], "sheet": x["sheet"], "row": x["row"],
        "citation_number": x["citation_number"], "report_description": x["report_description"],
        "verified_record": x["verified_record"], "problem_type": x["problem_type"],
        "supplied_judgement": x["supplied_judgement"], "assessment_status": x["assessment_status"],
        "overlap_links": x["overlap_links"], "mapped_issue_family": map_xenium(x["problem_type"]),
        "denominator_inclusion": False,
    })

tasks = []
for task_id, t in TASKS.items():
    tasks.append({
        "task_id": task_id, "original_prompt": t["prompt"], "original_prompt_sha256": text_sha(t["prompt"]),
        "topic_row_ids": t["topic_row_ids"],
        "issue_ids": [i["issue_id"] for i in issues if i["task_id"] == task_id],
    })

inventory = {
    "schema_version": "pane2_full_feedback_unique_issue_inventory.v1",
    "checked_utc": CHECKED,
    "status": "frozen_allegation_universe_before_candidate_scoring",
    "archive": {"path": "LDR第二次调研.rar", "sha256": ARCHIVE_SHA, "ledger_path": str(LEDGER_PATH.relative_to(ROOT)), "ledger_sha256": hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()},
    "scope": {"actual_tasks": 6, "topic_rows": 32, "pointer_rows_excluded": ["topic-27"], "overall_rows_retained_outside_scientific_denominator": ["overall-01"], "template_examples_excluded": [x["row_id"] for x in LEDGER["template_examples_excluded"]], "xenium_detail_rows": 38, "xenium_details_additive_denominator": False},
    "denominator": {
        "row_level_lower_bound": 31,
        "primary_unique_atomic_units": 34,
        "stress_expanded_units": 38,
        "strict_majority_threshold": 20,
        "policy": "Freeze the 34 primary units before scoring. Require at least 20 independently source-backed corrected units to claim a majority under the 38-unit stress bound. Unresolved, omitted, not-exercised and persistent cases remain visible and do not silently leave the denominator.",
        "substantiation": "The 34 units are allegations, not all proven hallucinations. Later source adjudication must report confirmed, not_hallucination, unresolved and inaccessible subsets separately; it may not erase unresolved allegations from the inventory.",
    },
    "tasks": tasks,
    "issues": issues,
    "xenium_overlap_audit": {"rows": overlap_details, "supplied_judgement_counts": {"合格": 20, "不合格": 16, "部分不合格": 1, "存疑": 1}, "interpretation": "These supplied labels are audit evidence and positive/negative control candidates, not independent scientific gold."},
    "overall_feedback": [r for r in LEDGER["overall_feedback_rows"]],
    "unresolved_policy": {"allowed_states": ["corrected", "explicitly_justified_uncertainty", "persistent_error", "omission_or_avoidance", "not_exercised", "unresolved_source", "not_hallucination"], "correction_rule": "A sentence deletion, generic unknown-only rewrite, or omitted requested field is not a correction. Explicit justified uncertainty may be useful but is scored separately from factual correction."},
}
write("full-feedback-issue-inventory.json", inventory)

# Coverage criteria are task-specific obligations, but no issue-specific regex or answer patch.
coverage = {
    "schema_version": "pane2_full_feedback_coverage_rubric.v1",
    "checked_utc": CHECKED,
    "denominator_reference": "full-feedback-issue-inventory.json",
    "frozen_issue_units": 34,
    "strict_majority_threshold": 20,
    "per_task_useful_obligations": {
        "task-47c54edcc0eb": ["four named cell populations", "source-specific sorting/enrichment markers and protocols", "downstream single-cell workflow", "technology/workflow/platform type distinction", "population/species/tissue qualifiers"],
        "task-41d13d68b84e": ["interpret non-18S/28S QC peak", "state mapping-rate/read consequences with uncertainty", "give a conditional sequencing decision", "name minimum follow-up QC or control"],
        "task-6ac5d65ed736": ["2026 date", "IF >10 state and descending order", "20 only if eligibility is evidenced", "research article rather than review/abstract", "both single-cell and spatial modalities", "allowed platform when stated", "group design and sample count per omics", "no unrelated expansion"],
        "task-90ad0dce1609": ["Chinese-language scope", "last two years", "research progress", "treatment summary", "formal source identity", "qualifiers and evidence limits"],
        "task-a9b2517baf83": ["last three years", "adipose sample", "spatial transcriptomics", "platform when stated", "high-impact ranking only when metadata exists", "study type and identity", "sample/tissue scope"],
        "task-6e8e8d113e76": ["published Xenium literature", "formal journal/source type", "publication year", "Xenium evidence", "deduplicated identity", "no unsupported scale/cancer claims"],
    },
    "issue_scoring": {"corrected": "Source-backed claim fixed while original obligation remains useful and report identity/scope is preserved.", "explicitly_justified_uncertainty": "Unknown or unavailable field is stated with the best supported useful alternative; report separately, not as factual correction by default.", "persistent_error": "Original allegation remains or is repeated.", "omission_or_avoidance": "Claim disappears, source omitted, or answer shrinks without resolving the obligation; never count as correction.", "not_exercised": "Original task/issue was not present in the candidate input or report.", "unresolved_source": "Source or exact report span inaccessible; retain allegation and do not score as passed.", "not_hallucination": "Source adjudication disproves the allegation; report separately from candidate correction."},
    "useful_coverage": {"formula": "requested_supported_units_retained / requested_units_in_original_task", "required": ["report headings/tables/conclusions included", "citation identity and source scope preserved", "qualifiers/negative findings retained", "unknown fields explicit", "no credit for fewer claims alone"], "compare": "Compare baseline and candidate only when original prompt hash, source hash/scope, model/settings and output budget are matched; report omitted and newly unsupported units."},
    "majority_rule": "No majority claim until at least 20 of the 34 primary units are source-adjudicated and corrected, with no silent unresolved/omission cases and useful coverage not materially reduced. Report lower/primary/stress denominators and every unresolved unit.",
    "candidate_integrity": ["original task hash must match", "source/input hash and scope must match", "candidate activation and final writer context must be recorded", "same-model self-review is provisional", "finish_reason=length or incomplete verifier answers remain failures", "generic unknown-only rewriting is not repair"],
}
write("full-feedback-coverage-rubric.json", coverage)

# Reserved controls: no scoring or tuning in this milestone.
controls = {
    "schema_version": "pane2_heldout_controls.v1",
    "checked_utc": CHECKED,
    "status": "reserved_not_scored",
    "leakage_policy": "Controls are declared before any future candidate score; do not use their labels or text to tune a report-specific rule.",
    "controls": [
        {"control_id": "heldout-xenium-positive-02", "kind": "identity_positive", "source_rows": ["xenium-detail-02"], "expected": "formal record identity and Xenium claim remain intact", "score": "identity, year, source type, citation and useful detail", "denominator": False},
        {"control_id": "heldout-xenium-positive-03", "kind": "identity_positive", "source_rows": ["xenium-detail-03"], "expected": "abstract-supported benchmark wording remains qualified", "score": "relation and qualifier retention", "denominator": False},
        {"control_id": "heldout-xenium-negative-07", "kind": "identity_negative", "source_rows": ["xenium-detail-07"], "expected": "database/journal and year fields are not conflated", "score": "source-type and year correction without deleting useful record", "denominator": False},
        {"control_id": "heldout-xenium-negative-16", "kind": "identity_negative", "source_rows": ["xenium-detail-16"], "expected": "publisher platform is not treated as journal and cancer scope stays source-bound", "score": "identity plus relationship attributes", "denominator": False},
        {"control_id": "heldout-xenium-negative-26", "kind": "publication_state_negative", "source_rows": ["xenium-detail-26"], "expected": "conference abstract is not silently promoted to formal paper", "score": "publication state and useful lead retention", "denominator": False},
        {"control_id": "heldout-new-art001", "kind": "cross_domain_multi_attribute", "source_paths": ["evaluation/scholar-controlled-pilot-corrected-v2-20261112/results/new-art001-gene-editing"], "expected": "safety/tolerability claims preserve population and follow-up qualifiers", "score": "claim relation, qualifier, source scope", "denominator": False},
        {"control_id": "heldout-new-crustacean", "kind": "cross_domain_multi_attribute", "source_paths": ["evaluation/scholar-controlled-pilot-corrected-v2-20261112/results/new-crustacean-single-cell"], "expected": "single-cell/metabolomics findings preserve model and assay boundaries", "score": "method/population/outcome relation", "denominator": False},
        {"control_id": "heldout-verifier-scope", "kind": "protocol_control", "source_paths": ["evaluation/frontier-strategy-20261113/completed-verifier-audit.json"], "expected": "every generated relationship gets a bounded source-scoped question; truncated batches stay incomplete", "score": "coverage of all questions, source IDs, finish reason and revision provenance", "denominator": False},
    ],
    "negative_control_requirements": ["same gene names with different ontology/relation", "correct identity and publication-state examples", "unknown IF/platform/date fields", "abstract-only versus full-text scope", "requested content retained while correcting an error"],
}
write("heldout-controls.json", controls)

# Actual Pane 0 outputs: record protocol fidelity and provisional assessment only.
def load(path):
    p = ROOT / path
    return json.loads(p.read_text()) if p.exists() else None

def result_summary(path, original_task_id=None):
    d = load(path)
    if not d:
        return {"path": path, "exists": False}
    q = d.get("query", "")
    original_sha = text_sha(TASKS[original_task_id]["prompt"]) if original_task_id else None
    return {"path": path, "exists": True, "case_id": d.get("case_id"), "arm": d.get("arm"), "status": d.get("status"), "query_sha256": text_sha(q), "query_chars": len(q), "original_task_id": original_task_id, "original_query_sha256": original_sha, "query_matches_original": (original_sha == text_sha(q)) if original_sha else None, "source_file": d.get("source_file"), "source_sha256": d.get("source_sha256"), "report_sha256": d.get("report_sha256"), "report_chars": d.get("report_chars"), "model_calls": d.get("model_calls"), "claim_protocol_deviation": d.get("claim_protocol_deviation"), "independent_verification": d.get("independent_verification"), "semantic_ranking": d.get("semantic_ranking")}

pane0 = {
    "schema_version": "pane2_pane0_output_review.v1",
    "checked_utc": CHECKED,
    "scope": "Read-only review of actual Pane 0 receipts; no candidate is scored as a full-feedback correction until question/source scope is matched.",
    "runner_protocol_audit": load("evaluation/frontier-strategy-20261113/runner-protocol-audit.json"),
    "completed_verifier_audit": load("evaluation/frontier-strategy-20261113/completed-verifier-audit.json"),
    "next_phase_outputs": [
        result_summary("evaluation/hallucination-next-phase-20261113/runs/pilot-immune-v2-20261113T0937Z/historical-immune/baseline/result.json", "task-47c54edcc0eb"),
        result_summary("evaluation/hallucination-next-phase-20261113/runs/pilot-immune-v2-20261113T0937Z/historical-immune/semantic_ranking/result.json", "task-47c54edcc0eb"),
        result_summary("evaluation/hallucination-next-phase-20261113/runs/pilot-immune-v2-20261113T0937Z/historical-immune/evidence_gap/result.json", "task-47c54edcc0eb"),
        result_summary("evaluation/hallucination-next-phase-20261113/runs/pilot-immune-v2-20261113T0937Z/historical-immune/independent_verification/result.json", "task-47c54edcc0eb"),
    ],
    "corrected_scholar_outputs": [
        result_summary(f"evaluation/scholar-controlled-pilot-corrected-20261112/results/{case}/{arm}/result.json", task)
        for case, task in [("historical-immune", "task-47c54edcc0eb"), ("historical-if", "task-6ac5d65ed736"), ("historical-adipose", "task-a9b2517baf83")]
        for arm in ["baseline_with_draft", "candidate_a_with_draft", "candidate_b_draft_removed", "supplemented_with_draft"]
        if (ROOT / f"evaluation/scholar-controlled-pilot-corrected-20261112/results/{case}/{arm}/result.json").exists()
    ],
    "assessment_summary": load("evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113/summary.json"),
    "eligibility": {
        "full_feedback_scoring": False,
        "reasons": ["next-phase runner uses abbreviated diagnostic queries rather than the original archive prompts", "independent verification uses empty source_ids and handwritten case questions while passing all passages", "q1/q2 verifier responses hit finish_reason=length and only q3 parsed", "historical IF candidate B has a ten-claim protocol deviation against an eight-claim limit", "same-model/provider assessment is provisional and source-bound", "none of these outputs covers all six original tasks"],
    },
    "observed_coverage": {
        "independent_verification": "1/3 questions answered (q3 only); q1/q2 are unresolved failures, not repairs.",
        "revision": "14254 to 7561 characters; generic qualifier/unknown rewriting cannot be counted as issue correction without relationship-level coverage.",
        "candidate_a": "historical immune output had unchanged report hash from baseline in v2 assessment; IF/adipose candidate A did not establish a stable advantage.",
        "candidate_b": "changed outputs but draft removal also changes reading-note context; no full-feedback majority evidence.",
        "new_controls": "ART001 and crustacean tasks are cross-domain held-out controls, not corrections of the six customer tasks.",
    },
    "decision": "diagnostic_only_defer_full_feedback_scoring",
}
write("pane0-output-review.json", pane0)

# Update durable Pane 2 review without touching any shared progress log.
doc = ROOT / "docs/hallucination-pane2-review-20261113.md"
text = doc.read_text() if doc.exists() else "# Pane 2 independent review (2026-11-13)\n"
marker = "\n## Full-feedback inventory milestone\n"
if marker not in text:
    text += marker + '''\nThe full archive denominator is now frozen in [`full-feedback-issue-inventory.json`](../evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json). It preserves the six original task prompts, 32 topic rows, workbook coordinates, exact feedback, expected effects, archive/ledger hashes, and all 38 Xenium detail rows. The Xenium details are linked audit evidence and are not additive denominator units; the KRAS examples and pointer row are excluded, while the overall usefulness row remains visible outside the scientific denominator.\n\nThe primary inventory has **34 unique atomic allegation units**: 31 substantive topic rows after excluding the Xenium pointer, with clearly independent clauses split and the topic-07/topic-08 platform-location duplicate merged. A 38-unit stress bound splits the duplicate groups separately. The conservative majority threshold is therefore **20 corrected units**, with unresolved, not-exercised, omitted and persistent cases retained. No units are yet source-adjudicated as corrected. See [`full-feedback-coverage-rubric.json`](../evaluation/pane2-independent-review-20261113/full-feedback-coverage-rubric.json).\n\nPane 0 output review is in [`pane0-output-review.json`](../evaluation/pane2-independent-review-20261113/pane0-output-review.json). The completed independent verifier answered only q3 of 3; q1/q2 reached the 5,000-token limit and failed JSON parsing. The revision shrank from 14,254 to 7,561 characters. This is a terminal transport/completeness receipt, not a semantic repair. The current runner also uses empty source IDs and handwritten case questions over all passages, so it is not source-scoped verification of emitted relationships.\n\nThe current candidate reports remain diagnostic: the next-phase runner uses abbreviated diagnostic questions, and the corrected scholar pilot does not cover all six tasks with exact original prompt/source scopes (IF and adipose queries differ from the archive prompt). Candidate outputs therefore receive no full-feedback correction score in this milestone. Reserved controls are declared in [`heldout-controls.json`](../evaluation/pane2-independent-review-20261113/heldout-controls.json) and are not yet scored or used for tuning.\n'''
    doc.write_text(text)

# Update package README and manifest.
readme = OUT / "README.md"
rt = readme.read_text() if readme.exists() else "# Pane 2 review package\n"
addition = '''\n- [`full-feedback-issue-inventory.json`](full-feedback-issue-inventory.json): frozen six-task/38-Xenium provenance inventory and conservative denominator.\n- [`full-feedback-coverage-rubric.json`](full-feedback-coverage-rubric.json): useful-content and majority criteria.\n- [`heldout-controls.json`](heldout-controls.json): reserved positive/negative and cross-domain controls.\n- [`pane0-output-review.json`](pane0-output-review.json): actual Pane 0 output/protocol review, including incomplete verifier coverage.\n'''
if "full-feedback-issue-inventory.json" not in rt:
    readme.write_text(rt.rstrip() + "\n" + addition)

manifest = {"schema_version": "pane2_review_manifest.v2", "checked_utc": CHECKED, "files": {}}
for p in sorted(OUT.iterdir()):
    if p.name == "MANIFEST.json" or not p.is_file():
        continue
    manifest["files"][str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
write("MANIFEST.json", manifest)
print(json.dumps({"issues": len(issues), "tasks": len(tasks), "xenium_details": len(overlap_details), "denominator": inventory["denominator"], "manifest_sha256": hashlib.sha256((OUT / "MANIFEST.json").read_bytes()).hexdigest()}, ensure_ascii=False, indent=2))
