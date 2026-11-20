#!/usr/bin/env python3
"""Build a blinded claim-review packet from frozen archive reports.

This prepares human review; it does not assign support labels, edit reports, or
estimate hallucination rates. Arm identity is written to a separate mapping so
the packet can be reviewed blind.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_claims(report: str):
    from research_verify.claims import extract_report_claims
    return extract_report_claims(report)


def source_record(source_by_id, index):
    source = source_by_id.get(int(index), {})
    keep = ("index", "title", "link", "url", "doi", "pmid", "pmcid", "journal",
            "publication_date", "pubdate", "year", "language", "publication_types",
            "impact_factor", "impact_factor_provenance", "abstract", "content",
            "full_content", "fetched_content", "content_type", "evidence_type",
            "source_kind", "document_type", "publication_status", "peer_review_status",
            "evidence_scope")
    return {key: source[key] for key in keep if key in source}


def trace_scope(trace_dir: Path | None):
    if not trace_dir or not trace_dir.exists():
        return {"reading_scope": [], "reading_notes": [], "trace_available": False}
    scopes, notes = [], []
    for path in sorted(trace_dir.rglob("*.json.gz")):
        try:
            payload = json.loads(gzip.open(path, "rt", encoding="utf-8").read())
        except (OSError, ValueError):
            continue
        name = path.name
        if "writer_reading_scope" in name:
            scopes.append(payload)
        elif "source_reading_notes" in name:
            notes.append(payload)
    return {"reading_scope": scopes, "reading_notes": notes, "trace_available": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rng = random.Random(20261112)
    packet_cases, mapping = [], []
    for case in manifest["cases"]:
        source_path = Path(case["source_path"])
        sources = json.loads(source_path.read_text(encoding="utf-8"))
        by_id = {int(row["index"]): row for row in sources if str(row.get("index", "")).isdigit()}
        rows = []
        arms = list(case["arms"])
        rng.shuffle(arms)
        for position, arm in enumerate(arms):
            report_path = Path(arm["report_path"])
            report = report_path.read_text(encoding="utf-8")
            claims = []
            for claim_id, claim in enumerate(read_claims(report)):
                claims.append({
                    "claim_id": claim_id,
                    "text": claim.text,
                    "citations": claim.citations,
                    "kind": claim.kind,
                    "context": claim.context,
                    "source_records": [source_record(by_id, index) for index in claim.citations
                                       if int(index) in by_id],
                })
            trace = trace_scope(Path(arm["trace_dir"]) if arm.get("trace_dir") else None)
            blind_id = f"{case['case_id']}-arm-{position + 1}"
            rows.append({"blind_id": blind_id, "report": report, "claims": claims,
                         "source_snapshot_sha256": digest(source_path), "trace": trace})
            mapping.append({"blind_id": blind_id, "case_id": case["case_id"],
                            "arm_label": arm["arm_label"], "report_sha256": digest(report_path)})
        packet_cases.append({"case_id": case["case_id"], "question": case["question"],
                             "source_snapshot_sha256": digest(source_path), "arms": rows})
    packet = {
        "schema_version": "archive_claim_review_packet_v1",
        "status": "prepared_for_blind_human_review",
        "cases": packet_cases,
        "assessment_protocol": {
            "labels": ["supported", "partially_supported", "unsupported", "contradicted",
                        "scope_limited", "unverifiable", "invalid_claim_unit"],
            "citation_entailment": ["yes", "partial", "no", "unknown"],
            "usefulness": "1-5 or unknown",
            "instructions": [
                "Assess each factual claim against the supplied source record and reading scope.",
                "Treat missing detail in an abstract as scope_limited/unverifiable, not as proof that the full paper lacks it.",
                "Keep source-scope limits separate from unsupported scientific findings.",
                "Retain every unresolved, malformed, and invalid item in denominators.",
                "Do not use citation-index validity as medical accuracy."
            ],
            "independence_limit": "This packet is designed for an independent biomedical reviewer; no labels are assigned here."
        }
    }
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.mapping.write_text(json.dumps({"schema_version": "archive_claim_review_mapping_v1",
                                        "mapping": mapping}, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"cases": len(packet_cases), "blind_arms": len(mapping),
                      "claims": sum(len(arm["claims"]) for case in packet_cases for arm in case["arms"]),
                      "packet": str(args.output), "mapping": str(args.mapping)}))


if __name__ == "__main__":
    main()
