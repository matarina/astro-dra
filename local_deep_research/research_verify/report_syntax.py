"""Original Markdown coordinates and explicit numeric citations, not meaning.

Uses the application's installed CommonMark parser. A role never establishes
that a sentence is factual, relevant, supported, or safe to remove.
"""
from dataclasses import dataclass
import re

from markdown_it import MarkdownIt


BIBLIOGRAPHY_LABELS = {"sources", "references", "bibliography", "citations", "参考文献", "文献列表", "引用文献"}
NUMERIC_LABEL = re.compile(r"(?<!\[)(?:\[\[([0-9]+(?:\s*,\s*[0-9]+)*)\]\]|\[([0-9]+(?:\s*,\s*[0-9]+)*)\]|【([0-9]+(?:\s*,\s*[0-9]+)*)】)(?!\])")
_URL = re.compile(r"https?://[^\s<>]+", re.I)


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    kind: str
    context: str = ""


@dataclass(frozen=True)
class Bibliography:
    start: int
    heading_end: int
    end: int


@dataclass(frozen=True)
class Citation:
    start: int
    end: int
    indices: tuple[int, ...]


def _indices(match):
    return tuple(int(x.strip()) for x in re.split(r"[,，]", next(g for g in match.groups() if g is not None)))


def _parser():
    md = MarkdownIt("commonmark").enable("table")
    rules = dict(zip(md.inline.ruler.get_active_rules(), md.inline.ruler.getRules("")))
    for name in ("backticks", "link", "image", "autolink", "html_inline", "escape"):
        original = rules[name]
        def capture(state, silent, rule=original, name=name):
            start, before = state.pos, len(state.tokens)
            ok = rule(state, silent)
            record = state.env.get("_report_coordinates")
            if not ok or silent or record is None:
                return ok
            end = state.pos
            if name == "link":
                label_end = state.md.helpers.parseLinkLabel(state, start, True)
                match = NUMERIC_LABEL.fullmatch(state.src[start:label_end+1])
                if match and (start == 0 or state.src[start-1] != "["):
                    record["linked"].append(Citation(start, end, _indices(match)))
                # A complete numeric link is handled above. Other links and
                # destinations are literal markup, not nested citation syntax.
                record["protected"].append((start, end))
            elif name != "backticks" or any(t.type == "code_inline" for t in state.tokens[before:]):
                record["protected"].append((start, end))
            return ok
        md.inline.ruler.at(name, capture)
    return md


def _label(inline):
    return "".join(t.content for t in inline.children or [] if t.type == "text").strip().rstrip(":：").casefold()


def _plain_label(line):
    # A whole conventional label is an explicit serialization convention,
    # never a substring/topic match. It may be bold in generated Markdown.
    line = line.strip().rstrip(":：").strip()
    if line.startswith("**") and line.endswith("**"):
        line = line[2:-2].strip().rstrip(":：")
    return line.casefold() in BIBLIOGRAPHY_LABELS


_BIBLIOGRAPHY_ENTRY = re.compile(r"(?:[-*] +)?" + NUMERIC_LABEL.pattern + r"[ \t]+\S")
_BIBLIOGRAPHY_FIELD = re.compile(r"(?:URL|DOI|PMID|Status|Identity):\s+\S")


def _bibliography(report, start, heading_end, limit):
    """Recognize a conventional heading followed by serialized entries."""
    end = heading_end
    has_entry = False
    for line in report[heading_end:limit].splitlines(keepends=True):
        value = line.strip()
        if _BIBLIOGRAPHY_ENTRY.match(value):
            has_entry = True
        elif value and value != "**Sources with unconfirmed identity**":
            if not has_entry or not _BIBLIOGRAPHY_FIELD.match(value):
                break
        end += len(line)
    if has_entry:
        return Bibliography(start, heading_end, end)


def layout(report, *, include_env=False, require_entries=False):
    """Return leaf-block spans and conventional bibliography sections."""
    md = _parser()
    env = {}
    tokens = md.parse(report, env)
    # CommonMark normalizes CRLF/CR/LF only. str.splitlines also splits PDF
    # form feeds and Unicode separators, shifting token.map off the raw text.
    lines = [m.group() for m in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", report)
             if m.group()]
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line))
    blocks, sections = [], []
    skipped = None
    if require_entries:
        # Limit parsing to the next top-level heading, even when it is nested
        # under the bibliography in the document's heading hierarchy.
        headings = iter([offsets[t.map[0]] for t in tokens
                         if t.type == "heading_open" and t.level == 0 and t.map])
        next_heading = next(headings, len(report))
    table_depth, table_header = 0, ""
    for i, token in enumerate(tokens):
        if token.map and require_entries:
            start, end = (offsets[n] for n in token.map)
            while next_heading <= start and next_heading < len(report):
                next_heading = next(headings, len(report))
            if sections and end <= sections[-1].end and start >= sections[-1].start:
                continue
        if token.type == "heading_open" and token.map:
            start, end = (offsets[n] for n in token.map)
            level = int(token.tag[1:])
            root = token.level == 0
            if root and skipped and (skipped[0] is None or level <= skipped[0]):
                sections.append(Bibliography(skipped[1], skipped[2], start))
                skipped = None
            if root and skipped is None and _label(tokens[i+1]) in BIBLIOGRAPHY_LABELS:
                if require_entries:
                    if section := _bibliography(report, start, end, next_heading):
                        sections.append(section)
                        continue
                else:
                    skipped = (level, start, end)
            if skipped is None:
                blocks.append(Block(start, end, "heading_candidate"))
        elif token.type == "table_open":
            table_depth += 1
            table_header = ""
        elif token.type == "table_close":
            table_depth -= 1
        elif token.type == "tr_open" and token.map:
            start, end = (offsets[n] for n in token.map)
            if tokens[i-1].type == "thead_open":
                table_header = report[start:end].strip()
            elif skipped is None:
                blocks.append(Block(start, end, "table_candidate", table_header))
        elif token.type in {"inline", "html_block"} and token.map and not table_depth:
            if token.type == "inline" and i and tokens[i-1].type == "heading_open":
                continue
            start, end = (offsets[n] for n in token.map)
            if skipped is None and token.type == "inline" and token.level <= 1 and _plain_label(lines[token.map[0]]):
                heading_end = offsets[token.map[0]+1]
                if require_entries:
                    if section := _bibliography(report, start, heading_end, next_heading):
                        sections.append(section)
                else:
                    skipped = (None, start, heading_end)
            if require_entries and sections and sections[-1].start <= start < sections[-1].end:
                start = sections[-1].end
            if skipped is None and start < end:
                if token.type != "html_block" or not token.content.lstrip().startswith("<!--"):
                    blocks.append(Block(start, end, "prose_candidate"))
    if skipped:
        sections.append(Bibliography(skipped[1], skipped[2], len(report)))
    return (blocks, sections, env) if include_env else (blocks, sections)


def inline_coordinates(text, env=None):
    """Protected inline syntax/URLs and numeric links in original coordinates."""
    md = _parser()
    record = {"protected": [], "linked": []}
    # Direct inline parsing avoids newline normalization changing CRLF offsets.
    md.inline.parse(text, md, {**(env or {}), "_report_coordinates": record}, [])
    for match in _URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end-1] in ".,;!?。！？":
            end -= 1
        record["protected"].append((match.start(), end))
    return record


_EXTENDED_NUMERIC_LABEL = re.compile(NUMERIC_LABEL.pattern.replace(r"\s*,\s*", r"\s*[,，]\s*"))


def citations_in(text, env=None, *, extended=False):
    record = inline_coordinates(text, env)
    result = list(record["linked"])
    labels = _EXTENDED_NUMERIC_LABEL if extended else NUMERIC_LABEL
    for match in labels.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in record["protected"]):
            continue
        result.append(Citation(match.start(), match.end(), _indices(match)))
    return sorted(result, key=lambda c:c.start)


def citation_spans(report, *, require_entries=False):
    blocks, _, env = layout(report, include_env=True, require_entries=require_entries)
    return [Citation(block.start+c.start, block.start+c.end, c.indices)
            for block in blocks for c in citations_in(report[block.start:block.end], env, extended=require_entries)]
