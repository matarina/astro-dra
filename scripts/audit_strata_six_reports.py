"""Audit citation/source alignment and obvious evidence-tier pollution in the Strata six-run.

This is a deterministic offline audit. It does not call a model and does not
claim to adjudicate every scientific fact. It flags observable metadata and
scope problems for manual review.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CASE_RULES = {
    "01-immune": ("immune", ("eosinoph", "basophil", "mast", "t cell", "lymphocyte", "immune")),
    "02-rna-qc": ("rna-qc", ("rna", "sequenc", "contamin", "mycoplasma", "quality", "ribosom")),
    "03-tumor-20": ("tumor-20", ("cancer", "tumor", "tumour", "carcinoma", "oncolog", "neoplasm", "spatial")),
    "04-diabetes": ("diabetes", ("diabet", "neuropath", "glucose", "glycemic", "insulin")),
    "05-adipose": ("adipose", ("adipos", "adipocyt", "fat tissue", "obes", "lipid", "thermogenic")),
    "06-xenium": ("xenium", ("xenium",)),
}


def source_text(source: dict) -> str:
    fields = (source.get("title"), source.get("journal"), source.get("abstract"), source.get("snippet"))
    return " ".join(str(x or "") for x in fields).lower()


def citation_links(report: str) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for n, url in re.findall(r"\[\[(\d+)\]\]\(([^)]+)\)", report):
        out.setdefault(int(n), set()).add(url)
    return out


def source_section_indices(report: str) -> set[int]:
    marker = report.find("\n## Sources")
    text = report[marker:] if marker >= 0 else ""
    return {int(n) for n in re.findall(r"^\[(\d+)\]\s", text, flags=re.M)}


def audit_case(case_dir: Path) -> dict:
    report_path = case_dir / "results" / "report.md"
    sources_path = case_dir / "results" / "sources.json"
    report = report_path.read_text(encoding="utf-8")
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    by_index = {int(s.get("index", i + 1)): s for i, s in enumerate(sources)}
    case_key = next((k for k in CASE_RULES if case_dir.name.startswith(k + "-")), None)
    label, keywords = CASE_RULES.get(case_key, (case_key or case_dir.name, ()))
    links = citation_links(report)
    section_ids = source_section_indices(report)
    publication_flags = []
    topic_flags = []
    missing_abstract = []
    for idx, source in sorted(by_index.items()):
        types = " ".join(str(x) for x in (source.get("publication_types") or [])).lower()
        title = str(source.get("title") or "")
        text = source_text(source)
        if any(term in types for term in ("review", "protocol", "preprint", "editorial", "commentary")):
            publication_flags.append({"index": idx, "title": title, "publication_types": source.get("publication_types")})
        if keywords and not any(k in text for k in keywords):
            topic_flags.append({"index": idx, "title": title, "journal": source.get("journal")})
        if not str(source.get("abstract") or "").strip() and not str(source.get("full_content") or "").strip():
            missing_abstract.append({"index": idx, "title": title, "link": source.get("link")})
    return {
        "case": case_dir.name,
        "label": label,
        "source_count": len(sources),
        "report_citation_ids": sorted(links),
        "source_section_ids": sorted(section_ids),
        "citation_ids_without_source": sorted(set(links) - set(by_index)),
        "source_ids_not_cited_in_report": sorted(set(by_index) - set(links)),
        "citation_links_per_id": {str(k): sorted(v) for k, v in links.items()},
        "publication_type_flags": publication_flags,
        "topic_keyword_flags": topic_flags,
        "metadata_only_flags": missing_abstract,
        "report_has_sources_section": "\n## Sources" in report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [audit_case(p) for p in sorted(args.run.glob("[0-9][0-9]-*/")) if (p / "results" / "report.md").is_file()]
    result = {"schema": "strata-six-offline-audit.v1", "run": str(args.run), "cases": cases}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
