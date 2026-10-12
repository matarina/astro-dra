"""Conservative report claim candidates and original report coordinates.

This is an auditable rules-based candidate extractor, not a semantic assertion
classifier. Ambiguous prose is retained rather than silently considered safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?:\([^\n)]*\))?")
_IGNORED = {"sources", "references", "bibliography", "参考文献", "文献列表",
            "文献真实性核验", "条件匹配核验", "条件匹配提示", "关键词覆盖核验",
            "结论可溯源性核查", "逐篇引用证据", "research metrics",
            "search questions by iteration", "detailed findings", "all sources"}
_FACT = re.compile(r"\d|\b(?:increases?|decreases?|reduces?|regulates?|causes?|associated|improves?|is|are|was|were)\b|增加|降低|导致|相关|表明|发现|显示|促进|抑制", re.I)
_PURE_ADVICE = re.compile(r"^(?:(?:we\s+)?(?:recommend|suggest)\s+(?:further|additional)\s+(?:research|studies)|(?:建议|推荐)(?:开展)?(?:进一步|更多)?(?:研究|验证|实验))[.!。！]?$", re.I)
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_ABBREVIATIONS = {"e.g", "i.e", "et al", "dr", "mr", "mrs", "fig", "vs", "al"}


@dataclass
class Claim:
    text: str
    citations: list[int] = field(default_factory=list)
    report_start: int | None = None
    report_end: int | None = None
    kind: str = "factual_candidate"
    context: str = ""


def _sentences(text: str):
    begin, pos = 0, 0
    while pos < len(text):
        char = text[pos]
        if char not in ".!?。！？":
            pos += 1
            continue
        if char == ".":
            if pos and pos+1 < len(text) and text[pos-1].isdigit() and text[pos+1].isdigit():
                pos += 1
                continue
            prefix = text[begin:pos].casefold()
            if any(re.search(r"(?:^|\s)" + re.escape(word) + r"$", prefix) for word in _ABBREVIATIONS):
                pos += 1
                continue
            if pos+1 < len(text) and text[pos+1].isalpha():
                pos += 1
                continue
        end = pos+1
        while end < len(text) and text[end] in ".!?。！？\"'”’":
            end += 1
        # Citation markers following a sentence belong to that sentence.
        while True:
            at = end
            while at < len(text) and text[at].isspace():
                at += 1
            cite = CITE_RE.match(text, at)
            if cite is None:
                break
            end = cite.end()
        if end < len(text) and text[end] == ".":
            end += 1
        yield begin, end
        begin, pos = end, end
    if begin < len(text):
        yield begin, len(text)


def extract_report_claims(report: str) -> list[Claim]:
    lines = report.splitlines(keepends=True)
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    claims = []
    skipped_level = None
    fence = None
    table_header = ""
    index = 0

    def add(start, end, kind="factual_candidate", context=""):
        while start < end and report[start].isspace():
            start += 1
        while end > start and report[end-1].isspace():
            end -= 1
        value = report[start:end]
        if not value or not re.search(r"[A-Za-z0-9\u3400-\u9fff]", CITE_RE.sub("", value)):
            return
        citations = sorted({int(n.strip()) for group in CITE_RE.findall(value) for n in group.split(",")})
        if not citations and value.rstrip().endswith(("?", "？")) and not _FACT.search(value):
            return
        if not citations and _PURE_ADVICE.fullmatch(value):
            return
        claims.append(Claim(value, citations, start, end, kind, context))

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        start = offsets[index]
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            if fence is None:
                fence = token
            elif fence == token:
                fence = None
            index += 1
            continue
        if fence:
            index += 1
            continue
        heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip().rstrip(":：").casefold()
            if title in _IGNORED:
                skipped_level = level if skipped_level is None else min(level, skipped_level)
            elif skipped_level is not None and level <= skipped_level:
                skipped_level = None
            if skipped_level is None and _FACT.search(title):
                a, b = heading.span(2)
                add(start+a, start+b, "heading_candidate")
            table_header = ""
            index += 1
            continue
        if stripped.rstrip(":：").casefold() in _IGNORED:
            skipped_level = 1
            index += 1
            continue
        if skipped_level is not None or not stripped:
            index += 1
            continue
        if "|" in line and (_SEPARATOR.match(stripped) or
                            index+1 < len(lines) and _SEPARATOR.match(lines[index+1].strip())):
            if not _SEPARATOR.match(stripped):
                table_header = stripped
            index += 1
            continue
        if "|" in stripped and table_header:
            add(start, start+len(line), "table_candidate", table_header)
            index += 1
            continue
        table_header = ""
        prefix = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)", line)
        block_start = start + (prefix.end() if prefix else 0)
        end_index = index
        # Join wrapped prose within a paragraph while preserving its raw newlines.
        if prefix is None:
            while end_index+1 < len(lines):
                following = lines[end_index+1]
                if not following.strip() or re.match(r"^\s*(?:#|[-*+]\s|\d+[.)]\s|>|\||`{3,}|~{3,})", following):
                    break
                if following.strip().rstrip(":：").casefold() in _IGNORED:
                    break
                end_index += 1
        block_end = offsets[end_index] + len(lines[end_index])
        block = report[block_start:block_end]
        for a, b in _sentences(block):
            add(block_start+a, block_start+b)
        index = end_index+1
    return claims
