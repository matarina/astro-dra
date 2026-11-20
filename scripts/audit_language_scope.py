#!/usr/bin/env python3
"""Report source-language scope without filtering or inferring semantics.

The requested language is an explicit evaluation input. The audit counts cited
source IDs whose authoritative language field matches, mismatches, or is
unknown. It never infers language from titles, URLs, prompt language, journals,
or report prose, and it never edits the report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from local_deep_research.research_verify.citation_display import cited_indices
except ModuleNotFoundError:  # installed overlay exposes research_verify directly
    from research_verify.citation_display import cited_indices


ALIASES = {
    "en": "en", "eng": "en", "english": "en",
    "zh": "zh", "chi": "zh", "zho": "zh", "chinese": "zh",
}


def normalize(value):
    if isinstance(value, list):
        values = [normalize(item) for item in value]
        values = [item for item in values if item]
        return values[0] if len(set(values)) == 1 else None
    if not isinstance(value, str):
        return None
    return ALIASES.get(value.strip().casefold())


def canonical_url(value):
    if not isinstance(value, str) or not value.strip():
        return None
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip().rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(),
                       parts.path.rstrip("/"), parts.query, ""))


def report_bibliography(report):
    """Map publication display IDs to URLs from the report's own bibliography."""
    section = report.split("\n## Sources", 1)[-1]
    rows = {}
    current = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            value = stripped[1:stripped.index("]")]
            current = int(value) if value.isdigit() else None
        elif current is not None and stripped.casefold().startswith("url:"):
            rows[current] = stripped.split(":", 1)[1].strip()
            current = None
    return rows


def audit(report, sources, requested_language):
    by_id = {int(item["index"]): item for item in sources if isinstance(item, dict)
             and str(item.get("index", "")).isdigit()}
    by_url = {}
    for item in sources:
        if not isinstance(item, dict):
            continue
        for key in ("link", "url"):
            value = canonical_url(item.get(key))
            if value:
                by_url[value] = item
                break
    bibliography = report_bibliography(report)
    cited = sorted(cited_indices(report))
    rows = []
    for index in cited:
        display_url = bibliography.get(index)
        source = by_url.get(canonical_url(display_url), {}) if display_url else {}
        if not source:
            source = by_id.get(index, {})
        language = normalize(source.get("language") or source.get("languages") or source.get("lang"))
        status = ("match" if language == requested_language else
                  "mismatch" if language is not None else "unknown")
        rows.append({"display_source_id": index,
                     "source_id": source.get("index"),
                     "source_url": display_url,
                     "language": language, "status": status,
                     "title": source.get("title", "")})
    counts = {name: sum(row["status"] == name for row in rows)
              for name in ("match", "mismatch", "unknown")}
    return {"requested_language": requested_language, "cited_source_ids": cited,
            "bibliography_bindings": bibliography,
            "counts": counts, "rows": rows,
            "scope_note": "Metadata-only audit; unknown does not mean mismatch."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--requested-language", required=True)
    args = parser.parse_args()
    report = args.report.read_text(encoding="utf-8")
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    print(json.dumps(audit(report, sources, args.requested_language), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
