"""Export explicit bibliography syntax without inventing publication metadata."""
from datetime import datetime, timezone
import json
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

from .report_syntax import layout, NUMERIC_LABEL, citation_spans


def bibliography_entries(content):
    """Return supplied titles/URLs; conflicting URLs stay unavailable."""
    entries = {}
    _, sections = layout(content)
    for section in sections:
        text = content[section.heading_end:section.end]
        lines = text.splitlines(keepends=True)
        protected = set()
        for token in MarkdownIt("commonmark").parse(text):
            if token.map and token.type in {"fence", "code_block", "html_block"}:
                protected.update(range(*token.map))
        current = None
        for position, line in enumerate(lines):
            if position in protected:
                if current:
                    current["original_lines"].append(line)
                continue
            stripped = line.strip()
            label = NUMERIC_LABEL.match(stripped)
            if label and stripped[label.end():].startswith((" ", "\t")):
                indices = next(group for group in label.groups() if group is not None)
                title = stripped[label.end():].strip()
                current = {"title": title, "provided_urls": [], "identifiers": {}, "original_lines": [line]}
                for index in indices.split(","):
                    entries.setdefault(int(index.strip()), []).append(current)
            elif current:
                current["original_lines"].append(line)
                url = re.fullmatch(r"URL:[ \t]*(.+)", stripped)
                if url:
                    current["provided_urls"].append(url[1])
                identifier = re.fullmatch(r"(DOI|PMID):[ \t]*(\S+)", stripped)
                if identifier:
                    current["identifiers"].setdefault(identifier[1], set()).add(identifier[2])
    result = {}
    for index, candidates in entries.items():
        provided = {url for entry in candidates for url in entry["provided_urls"]}
        value = next(iter(provided)) if len(provided) == 1 else ""
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not any(c.isspace() for c in value)
        except ValueError:
            valid = False
        result[index] = {"title": candidates[0]["title"], "url": value if valid else "",
                         "url_status": "provided" if valid else "conflicting" if len(provided) > 1 else "unavailable",
                         "provided_text": "\n\n".join("".join(c["original_lines"]).rstrip("\r\n") for c in candidates)}
        identifiers = {}
        for kind in ("DOI", "PMID"):
            values = set().union(*(entry["identifiers"].get(kind, set()) for entry in candidates))
            if len(values) == 1:
                identifiers[kind] = next(iter(values))
        if identifiers:
            result[index]["provided_identifiers"] = identifiers
    return result


def bibliography(content):
    # Reuse the installed exporter's escaping only, not its assumed date or
    # immediate-next-line URL parser. These functions do not fetch sources.
    from local_deep_research.text_optimization.citation_formatter import _escape_bibtex, _safe_bibtex_url
    records = []
    for index, entry in sorted(bibliography_entries(content).items()):
        fields = [f'  title = "{{{_escape_bibtex(entry["title"])}}}"']
        url = _safe_bibtex_url(entry["url"])
        if url:
            fields.append(f"  url = {{{url}}}")
        doi = entry.get("provided_identifiers", {}).get("DOI")
        if doi:
            fields.append(f'  doi = "{{{_escape_bibtex(doi)}}}"')
        note = _escape_bibtex(entry["provided_text"])
        fields.append(f'  note = "{{{note}}}"')
        # Unknown year/authors/access date are absent. Export date is only the
        # document's date, never asserted as a paper publication/access date.
        records.append("@misc{ref" + str(index) + ",\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(records)


def document(content, title, bib_content):
    entries = bibliography_entries(content)
    body = content
    # Export exactly the labels present in the published Markdown. New reports
    # already expanded ranges; older reports only guaranteed their endpoints.
    for citation in reversed(citation_spans(content, expand_ranges=False)):
        if not all(i in entries for i in citation.indices):
            continue
        refs = "; ".join("@ref" + str(i) for i in dict.fromkeys(citation.indices))
        body = body[:citation.start] + "[" + refs + "]" + body[citation.end:]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = "---\ntitle: " + json.dumps(str(title), ensure_ascii=False) + '\nauthor: "Local Deep Research"\n'
    header += f'date: "{date}"\nformat:\n  html:\n    toc: true\n    toc-depth: 3\n    number-sections: true\n  pdf:\n    toc: true\n    number-sections: true\n    colorlinks: true\nbibliography: references.bib\ncsl: apa.csl\n---\n\n'
    note = ("\n\n::: {.callout-note}\n## Bibliography File Required\n\n"
            "This document requires a `references.bib` file in the same directory with the following content:\n\n"
            "```bibtex\n" + bib_content + "\n```\n:::\n")
    return header + body + note
