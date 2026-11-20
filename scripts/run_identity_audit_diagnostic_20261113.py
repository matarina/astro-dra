#!/usr/bin/env python3
"""Offline identity-audit diagnostic using issue-24 and a correct control."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from research_verify.identity_audit import AuthoritativeIdentity, IdentityMention, audit_identity_mentions

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/frontier-strategy-20261113/identity-audit-20261113.json"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    adjudication = json.loads((ROOT / "evaluation/pane2-independent-review-20261113/nonimmune-adjudication.json").read_text())
    record = next(item for item in adjudication["records"] if item.get("issue_id") == "issue-24")
    evidence = json.loads((ROOT / "evaluation/pane2-independent-review-20261113/nonimmune-primary-evidence.json").read_text())
    crossref = evidence["records"]["doi-10.3390/cells15181645"]
    metadata = crossref["metadata"]
    authoritative = {
        "8": AuthoritativeIdentity("8", {
            "journal": (metadata.get("container-title") or metadata.get("short-container-title") or [None])[0],
            "year": (metadata.get("published") or {}).get("date-parts", [[None]])[0][0],
            "publication_type": metadata.get("type"),
            "publication_state": "published",
        }, {"kind": "Crossref", "record_sha256": crossref["body_sha256"], "doi": "10.3390/cells15181645"}),
        # Correct identity control from the same preserved authoritative pack.
        "control-42014051": AuthoritativeIdentity("control-42014051", {
            "journal": evidence["records"]["pmid-42014051"]["metadata"]["journalTitle"],
            "year": int(evidence["records"]["pmid-42014051"]["metadata"]["pubYear"]),
            "publication_type": evidence["records"]["pmid-42014051"]["metadata"]["pubType"],
        }, {"kind": "Europe PMC", "record_sha256": evidence["records"]["pmid-42014051"]["body_sha256"], "pmid": "42014051"}),
    }
    spans = record["report_spans"]
    mentions = [
        IdentityMention("issue-24-overview", "8", claims={"journal": "Pharmacological Research"}, report_start=spans[0].get("line_start"), report_end=spans[0].get("line_end"), report_text_sha256=spans[0]["text_sha256"]),
        IdentityMention("issue-24-pvat", "8", claims={"journal": "Cells"}, report_start=spans[1].get("line_start"), report_end=spans[1].get("line_end"), report_text_sha256=spans[1]["text_sha256"]),
        IdentityMention("issue-24-translation", "8", claims={"journal": "Experimental & Molecular Medicine"}, report_start=spans[2].get("line_start"), report_end=spans[2].get("line_end"), report_text_sha256=spans[2]["text_sha256"]),
        IdentityMention("correct-control", "control-42014051", claims={"journal": "Diabetes Metab J", "year": 2026}),
    ]
    rows = audit_identity_mentions(mentions, authoritative)
    result = {
        "schema_version": "identity_audit_diagnostic.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "issue_id": "issue-24",
        "authoritative_input_hashes": {key: value.provenance.get("record_sha256") for key, value in authoritative.items()},
        "mentions": [m.__dict__ for m in mentions],
        "results": list(rows),
        "summary": {"mismatch": sum(row["status"] == "mismatch" for row in rows), "match": sum(row["status"] == "match" for row in rows), "unknown": sum(row["status"] == "unknown" for row in rows)},
        "interpretation": {
            "status": "offline_identity_diagnostic",
            "auto_deletion": False,
            "publication_gate": False,
            "hallucination_reduction_claim": False,
            "limits": [
                "Mentions are structured spans from the preserved adjudication artifact, not a new generated report.",
                "Metadata identity mismatches are separate from scientific claim entailment and useful-content retention.",
                "The diagnostic does not establish correction of issue-24 or any majority outcome.",
            ],
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "summary": result["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
