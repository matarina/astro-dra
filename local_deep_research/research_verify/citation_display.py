"""Citation presentation only: visible brackets, first-use numbering and sources.

No semantic verdict or research-content filtering belongs in this module.
"""
from __future__ import annotations

import re
from .claims import extract_legacy_report_claims
from .report_syntax import citation_spans, layout, NUMERIC_LABEL

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
    return list(dict.fromkeys(i for citation in citation_spans(body) for i in citation.indices))


def legacy_cited_indices(body: str) -> list[int]:
    """Pre-2.2 identity order, only for stored-report compatibility."""
    seen = dict.fromkeys(
        int(number)
        for claim in extract_legacy_report_claims(body)
        for match in CITATION_RE.finditer(claim.text)
        for number in re.split(r"\s*,\s*", match.group(1))
    )
    return list(seen)


def format_sources(sources) -> str:
    confirmed, unconfirmed = [], []
    for source in sources:
        title = str(source.title).replace("\n", " ").replace("\r", " ")
        entry = f"[{source.index}] {title}"
        status = getattr(source, "status", "unverified")
        identity = getattr(source, "identity_status", "candidate")
        if status != "formal":
            reason = getattr(source, "status_reason", "")
            entry += f"\n   Status: {status}" + (f" ({reason})" if reason else "")
        dtype = getattr(source, "document_type", "unknown")
        pub_state = getattr(source, "publication_state", "unknown")
        peer = getattr(source, "peer_review_status", "unknown")
        entry += f"\n   Identity: {identity}; document type: {dtype}; publication state: {pub_state}; peer review: {peer}"
        if source.url:
            entry += f"\n   URL: {source.url}"
        if source.paper_id.startswith("doi:"):
            entry += f"\n   DOI: {source.paper_id[4:]}"
        if source.paper_id.startswith("pmid:"):
            entry += f"\n   PMID: {source.paper_id[5:]}"
        (confirmed if identity == "confirmed" else unconfirmed).append(entry)
    sections = []
    if confirmed:
        sections.append("\n\n".join(confirmed))
    if unconfirmed:
        # A paragraph label stays inside the enclosing bibliography at any
        # heading depth; it must not reopen prose claim extraction.
        sections.append("**Sources with unconfirmed identity**\n\n" + "\n\n".join(unconfirmed))
    return "\n\n".join(sections)


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

    for claim in reversed(extract_legacy_report_claims(body)):
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


def render_report_current(body: str, sources) -> str:
    """2.2 citation formatting preserves code, destinations and original prose."""
    mapped = {old: source for source in sources for old in source.original_indices}
    for citation in reversed(citation_spans(body)):
        if not any(i in mapped for i in citation.indices):
            continue  # Retain the literal unresolved label/link; never guess.
        labels = []
        for old in dict.fromkeys(citation.indices):
            source = mapped.get(old)
            label = (f"[[{source.index}]]({source.url})" if source and source.url
                     else f"[{source.index if source else old}]")
            if label not in labels:labels.append(label)
        body = body[:citation.start]+", ".join(labels)+body[citation.end:]
    _, sections = layout(body)
    if sections and sources:
        section = sections[-1]
        existing = body[section.heading_end:section.end]
        present = set()
        def relabel(match):
            label = NUMERIC_LABEL.fullmatch(match[2])
            originals = [int(i.strip()) for i in next(g for g in label.groups() if g is not None).split(",")]
            if not all(old in mapped for old in originals):return match[0]
            indices = list(dict.fromkeys(mapped[old].index for old in originals))
            present.update(indices)
            return match[1]+"["+", ".join(map(str,indices))+"]"
        # Preserve supplied bibliography text/unknown entries; only explicit
        # entry labels are renumbered. Do not delete facts to rebuild a table.
        existing = re.sub(r"(?m)^([ \t]*)("+NUMERIC_LABEL.pattern+r")", relabel, existing)
        additional = format_sources([s for s in sources if s.index not in present])
        replacement = existing
        if additional:replacement += "\n\n"+additional
        if section.end < len(body) and not replacement.endswith("\n\n"):
            replacement += "\n\n"
        body = body[:section.heading_end]+replacement+body[section.end:]
    return body
