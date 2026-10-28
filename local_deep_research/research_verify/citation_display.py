"""Citation presentation only: visible brackets, first-use numbering and sources.

No semantic verdict or research-content filtering belongs in this module.
"""
from __future__ import annotations

import re
from .claims import extract_report_claims

# Raw, linked, double-bracketed and Chinese numeric citations share one parser.
CITATION_RE = re.compile(
    r"(?<![\\\[])\[?[\[【](\d+(?:\s*,\s*\d+)*)[\]】]\]?(?:\([^\n)]*\))?"
)
_REFERENCES = re.compile(
    r"^(#{1,6})[ \t]+(?:Sources|References|Bibliography|参考文献|文献列表|引用文献)[:：]?[ \t]*#*[ \t]*$",
    re.M | re.I,
)


def cited_indices(body: str) -> list[int]:
    """First appearance in prose; bibliography labels and code are not citations."""
    seen = dict.fromkeys(
        int(number)
        for claim in extract_report_claims(body)
        for match in CITATION_RE.finditer(claim.text)
        for number in re.split(r"\s*,\s*", match.group(1))
    )
    return list(seen)


def format_sources(sources) -> str:
    entries = []
    for source in sources:
        title = str(source.title).replace("\n", " ").replace("\r", " ")
        entry = f"[{source.index}] {title}"
        if source.url:
            entry += f"\n   URL: {source.url}"
        if source.paper_id.startswith("doi:"):
            entry += f"\n   DOI: {source.paper_id[4:]}"
        entries.append(entry)
    return "\n\n".join(entries)


def render_report(body: str, sources) -> str:
    mapped = {old: source for source in sources for old in source.original_indices}

    def hyperlink(match):
        labels = []
        seen = set()
        for old in map(int, re.split(r"\s*,\s*", match.group(1))):
            source = mapped.get(old)
            # Unknown numbers stay distinct; never attach another paper's URL.
            number = source.index if source else old
            if number in seen:
                continue
            seen.add(number)
            labels.append(
                f"[[{number}]]({source.url})" if source and source.url
                else f"[{number}]"
            )
        return ", ".join(labels)

    for claim in reversed(extract_report_claims(body)):
        if CITATION_RE.search(claim.text):
            body = (body[:claim.report_start] + CITATION_RE.sub(hyperlink, claim.text)
                    + body[claim.report_end:])

    # Detailed generators already append a bibliography. Rebuild its entries in
    # the same display numbering, preserving any following substantive sections.
    offset, fence, headings = 0, None, []
    for line in body.splitlines(keepends=True):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            fence = token if fence is None else None if fence == token else fence
        elif fence is None and re.match(r"^#{1,6}[ \t]+", line):
            headings.append((offset, offset + len(line.rstrip("\r\n")),
                             bool(_REFERENCES.fullmatch(line.rstrip("\r\n")))))
        offset += len(line)
    sections = [i for i, (_, _, reference) in enumerate(headings) if reference]
    if sections and sources:
        position = sections[-1]
        start, heading_end, _ = headings[position]
        end = headings[position + 1][0] if position + 1 < len(headings) else len(body)
        bibliography = body[start:heading_end] + "\n\n" + format_sources(sources)
        body = body[:start] + bibliography + ("\n\n" + body[end:] if end < len(body) else "")
    return body
