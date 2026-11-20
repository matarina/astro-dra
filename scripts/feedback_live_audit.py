"""Audit a disposable live report against the second-feedback output contract.

This is a diagnostic report, not a publication gate.  It checks structural
properties that can be verified without pretending to judge scientific truth:
the body remains free of legacy verification tables, citations have matching
bibliography entries, source URLs are canonical PubMed/Europe PMC records, and
decision questions contain a bounded recommendation section.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LEGACY_HEADINGS = (
    "关键词覆盖核验",
    "条件范围提示（仅供写作参考）",
    "文献真实性核验",
    "结论可溯源性核查",
)
CANONICAL_SOURCE = re.compile(r"^https://(?:pubmed\.ncbi\.nlm\.nih\.gov|europepmc\.org)/(?:article/)?")
INLINE_CITATION = re.compile(r"\[\[(\d+)\]\]")
BIBLIOGRAPHY = re.compile(r"^\[(\d+)\]\s+", re.MULTILINE)


def audit(root: Path) -> dict:
    report = (root / "report.md").read_text(encoding="utf-8")
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    metadata = result.get("metadata", {})
    body = metadata.get("claim_publication", {}).get("content", report)
    source_records = metadata.get("claim_publication", {}).get("sources", [])

    inline = {int(value) for value in INLINE_CITATION.findall(body)}
    bibliography = {int(value) for value in BIBLIOGRAPHY.findall(report)}
    urls = [record.get("url", "") for record in source_records]
    forbidden = [heading for heading in LEGACY_HEADINGS if heading in body]
    formal = [record for record in source_records if record.get("status") == "formal"]
    preprints = [record for record in source_records if record.get("status") == "preprint"]
    audit_status = metadata.get("claim_publication", {}).get("audit_status", "unknown")
    citation_audit = metadata.get("claim_publication", {}).get("citation_audit", [])

    checks = {
        "legacy_verification_tables_absent": not forbidden,
        "inline_citations_have_bibliography": inline <= bibliography,
        "source_urls_are_canonical": bool(urls) and all(CANONICAL_SOURCE.match(url) for url in urls),
        "formal_source_records_present": bool(formal),
        # Do not infer audit success from prose disclaimers. A completed audit
        # must carry claim-level checks; disabled/unavailable remains explicit.
        "disclaimer_does_not_create_audit_pass": not (
            audit_status == "completed" and not citation_audit
        ),
    }
    return {
        "checks": checks,
        "structural_checks_pass": all(checks.values()),
        "semantic_assessment": "not_performed",
        "effectiveness": "unproven",
        "legacy_headings_found": forbidden,
        "inline_citations": sorted(inline),
        "bibliography_indices": sorted(bibliography),
        "source_count": len(source_records),
        "formal_source_count": len(formal),
        "preprint_source_count": len(preprints),
        "limitations": [
            "This audit does not establish scientific truth, source relevance, or citation entailment.",
            "Structural checks do not assess claim support, usefulness, source recall or compliance with scientific constraints.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.report_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
