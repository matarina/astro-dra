#!/usr/bin/env python3
"""Build an archival diagnosis packet; never used to select production text.

Offsets and citation links below are manually inspected evidence annotations.
They are not scientific matching rules, model labels, or candidate repairs.
The unannotated original 60-source pack is kept separately for experiments.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/frontier-strategy-20261113/immune-evidence"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    captured_path = OUT / "production-selected-evidence.json"
    captured = json.loads(captured_path.read_text())
    report_path = OUT / "original-immune-report.txt"
    report = report_path.read_text()
    ledger = json.loads((ROOT / "evaluation/scholar-strategy-20261112/full-feedback-coverage-ledger.json").read_text())
    feedback = {r["row_id"]: r for r in ledger["topic_feedback_rows"]}
    sources = {int(s["index"]): s for s in captured["selected_input_sources"]}
    views = {int(s["index"]): s for s in captured["source_material_views"]["sources"]}
    writer = captured["writer_sources"]["text"]

    # Original PDF bibliography IDs differ from internal production source IDs.
    annotations = [
        ("topic-01", "issue-01", 3, 5, "FACS分选（脂肪组织）", [(9403, 10410), (11444, 13032)],
         "Original report gives a shortened Siglec-8 gate and later a fuller EMR1 alternative. Missing gate context is a completeness issue; it is not proof that all reported markers are false. The source discusses adipose tissue with a blood comparison, so the feedback's blood wording is not a universal gold answer."),
        ("topic-02", "issue-02", 8, 36, "一项Nature研究对小鼠嗜酸性粒细胞进行了全面", [],
         "The report only says the study performed comprehensive mouse eosinophil profiling. The requested enrichment method is omitted; no specific wrong magnetic-bead protocol is emitted in that sentence. Newly retrieved full text provides the missing protocol with age/strain qualifiers."),
        ("topic-03", "issue-03", 10, 37, "脐带血研究", [],
         "The report summarizes paired maternal/cord blood profiling but does not supply the isolation method. The captured source has an abstract; the feedback's kit protocol is not independently verified in this packet."),
        ("topic-04", "issue-04", 9, 13, "CITE-seq方案", [(5386, 6090), (7341, 8588), (10526, 12167), (12218, 13283), (13347, 13912)],
         "The report expands lineage markers and merges the primary paper with a review citation. Primary methods vary by donor: donor B includes a sorted c-Kit-positive fraction; donors C/D use CCR3 enrichment. A blanket CD117-negative feedback target would erase this distinction. Review the actual source-specific relationship, not marker-token agreement."),
        ("topic-05", "issue-05", 12, 25, "WEMP方案", [(10152, 11418), (19262, 20472)],
         "The report describes tissue dissociation but omits the source's detailed mast-cell gating. Both methods and results paragraphs are available in the captured acquired text. Preserve the distinction between tissue preparation, phenotyping, sorting and RNA analysis."),
        ("topic-06", "issue-06", 16, 39, "一项Science Immunology研究", [],
         "The report summarizes airway mast-cell phenotypes but not the sorting gate. A public PMC manuscript identity was recovered; machine full-text acquisition failed in this check. The feedback's full gate remains unverified here."),
    ]

    rows = []
    for row_id, issue_id, report_id, source_id, anchor, ranges, interpretation in annotations:
        source = sources[source_id]
        begin = writer.index(f"[{source_id}]\nTitle:")
        start = writer.index("BEGIN SOURCE TEXT\n", begin) + len("BEGIN SOURCE TEXT\n")
        end = writer.index("\nEND SOURCE TEXT", start)
        actual_view = writer[start:end]
        (OUT / f"source-{source_id}-writer-view.txt").write_text(actual_view)
        location = report.index(anchor)
        report_start = report.rfind("\n\n", 0, location) + 2
        report_end = report.find("\n\n", location)
        if report_end < 0:
            report_end = len(report)
        acquired = source.get("fetched_content", "")
        spans = []
        for lo, hi in ranges:
            quote = acquired[lo:hi]
            assert quote.strip() and hi <= len(acquired)
            spans.append({"field": "fetched_content", "start": lo, "end": hi,
                          "text": quote, "sha256": hashlib.sha256(quote.encode()).hexdigest(),
                          "exact_span_in_writer_view": quote in actual_view})
        row = {
            "row_id": row_id, "issue_id": issue_id,
            "original_pdf_citation_id": report_id, "production_source_id": source_id,
            "identity": {k: source.get(k) for k in ("title", "doi", "pmid", "pmcid", "link")},
            "original_feedback": feedback[row_id]["feedback"],
            "supplied_expected_effect_not_gold": feedback[row_id]["cells"].get("预期效果(正确结论)"),
            "original_report_span": {"start": report_start, "end": report_end,
                                     "text": report[report_start:report_end]},
            "recorded_source_view": views[source_id],
            "actual_writer_view_sha256": hashlib.sha256(actual_view.encode()).hexdigest(),
            "actual_writer_view_chars": len(actual_view),
            "acquired_method_spans": spans,
            "evidence_diagnosis": "decisive_method_text_acquired_but_not_in_writer_source_view" if spans else "method_not_in_captured_abstract_view",
            "provisional_original_issue_interpretation": interpretation,
            "candidate_correction_status": "not_evaluated",
        }
        if source_id == 36:
            p = OUT / "PMC9977678-body-paragraphs.json"
            paragraphs = json.loads(p.read_text())
            row["newly_acquired_evidence"] = {"path": str(p.relative_to(ROOT)), "sha256": digest(p),
                "primary_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9977678/",
                "paragraph_index": 42, "text": paragraphs[42],
                "scope": "New acquisition after the original run; never described as old writer-visible evidence."}
        if source_id in (37, 39):
            row["unresolved"] = "Exact full methods not read in this packet; supplied feedback remains an allegation."
        rows.append(row)

    packet = {
        "schema_version": "supervisor_immune_evidence_packet.v1",
        "checked_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task_id": "task-47c54edcc0eb",
        "original_report_pdf": str((OUT / "original-immune-report.pdf").relative_to(ROOT)),
        "original_report_pdf_sha256": digest(OUT / "original-immune-report.pdf"),
        "original_report_text_sha256": digest(report_path),
        "captured_evidence_sha256": digest(captured_path),
        "production_research_id": "509961a1-6ca0-49fa-81c4-c422f5c900a8",
        "production_synthesis_id": "synthesis-27affa0bdc65442394a897f48ca54278",
        "unannotated_sourcepack": str((OUT / "production-original-sourcepack.json").relative_to(ROOT)),
        "unannotated_sourcepack_sha256": digest(OUT / "production-original-sourcepack.json"),
        "source_count": 60,
        "rows": rows,
        "limits": [
            "Source-view loss is observed; its causal effect on final errors is not established. Drafts and later checks may carry additional details.",
            "Exact phrase absence alone is not a semantic entailment verdict. The displayed view and full methods were inspected by the supervisor.",
            "Most of these six complaints involve omitted requested methods; claim-only checking cannot recover an unstated obligation automatically.",
            "Feedback expected-effect text is not gold. Tissue, donor, assay and positive/negative gate qualifiers require source adjudication.",
            "This is assessment/diagnosis material, not a prompt to inject into candidate generation. Use the separate unannotated source pack for controlled tests.",
            "No candidate correction or majority hallucination reduction is established by this evidence packet.",
        ],
    }
    p = OUT / "packet.json"
    p.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"packet": str(p.relative_to(ROOT)), "rows": len(rows),
                      "method_view_loss_rows": sum(bool(r["acquired_method_spans"]) for r in rows),
                      "new_fulltext_acquisitions": 1, "remaining_full_method_unknowns": 2,
                      "sha256": digest(p)}, indent=2))


if __name__ == "__main__":
    main()
