"""Shared retrieval transport and the explicitly selected biomedical sources."""
from __future__ import annotations

import email.utils
import fcntl
import os
from html.parser import HTMLParser
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET
import copy


def html_text(value):
    """Read inline scientific markup without losing text after nested tags."""
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
            self.inline = []
            self.tables = []
            self.hidden = 0

        def emit(self, text):
            target = self.inline[-1][2] if self.inline else (
                self.tables[-1]["cell"] if self.tables and self.tables[-1]["cell"] is not None else self.parts)
            target.append(text)

        def handle_starttag(self, tag, attrs):
            tag = tag.rsplit(":", 1)[-1]
            if tag in {'script','style'}:
                self.hidden += 1
                return
            if self.hidden:return
            tag = {"row": "tr", "entry": "td"}.get(tag, tag)
            if tag == "table":
                self.tables.append({"rows": [], "row": [], "cell": None, "spans": {}, "attrs": {}, "header":False})
            elif self.tables and tag in {"td", "th"}:
                self.tables[-1]["cell"] = []
                self.tables[-1]["attrs"] = dict(attrs)
                if tag == "th":self.tables[-1]["header"] = True
            if tag in {"sup", "sub"}:
                self.inline.append([tag, tag, []])
            elif tag == "xref" and dict(attrs).get("ref-type") == "bibr":
                self.inline.append([tag, "article-ref", []])
            if tag in {"p", "br", "h2", "h3", "h4", "div", "li"}:
                self.emit("\n")

        def handle_endtag(self, tag):
            tag = tag.rsplit(":", 1)[-1]
            if tag in {'script','style'} and self.hidden:
                self.hidden -= 1
                return
            if self.hidden:return
            tag = {"row": "tr", "entry": "td"}.get(tag, tag)
            if self.tables and tag in {"td", "th"}:
                t = self.tables[-1]
                value = " ".join("".join(t["cell"] or []).split()).replace("|", "\\|")
                def span(name):
                    try: return max(1, min(100, int(t["attrs"].get(name, 1))))
                    except (TypeError, ValueError): return 1
                t["row"].append((value, span("colspan"), span("rowspan")))
                t["cell"] = None
            elif self.tables and tag == "tr":
                t = self.tables[-1]; cells = []; column = 0
                def pending():
                    nonlocal column
                    while column in t["spans"]:
                        value, left = t["spans"].pop(column)
                        cells.append(value)
                        if left > 1: t["spans"][column] = (value, left - 1)
                        column += 1
                for value, cols, rows in t["row"]:
                    pending()
                    for _ in range(cols):
                        cells.append(value)
                        if rows > 1: t["spans"][column] = (value, rows - 1)
                        column += 1
                pending()
                while t['spans'] and column <= max(t['spans']):
                    if column not in t['spans']:
                        cells.append('');column += 1
                    else:pending()
                if cells: t["rows"].append(cells)
                t["row"] = []
            elif self.tables and tag == "table":
                t = self.tables.pop(); rows = t["rows"]
                if rows:
                    width = max(map(len, rows))
                    lines = ['| ' + ' | '.join(row + [''] * (width - len(row))) + ' |' for row in rows]
                    if t['header']:lines.insert(1, '| ' + ' | '.join(['---'] * width) + ' |')
                    self.emit('\n' + '\n'.join(lines) + '\n')
            if self.inline and self.inline[-1][0] == tag:
                _, kind, parts = self.inline.pop()
                value = "".join(parts)
                # Preserve untyped super/subscripts, do not guess whether
                # they are references, exponents, charges, or identifiers.
                label = {"sup": "superscript", "sub": "subscript"}.get(kind, kind)
                text = value if kind == "sup" and "[article-ref:" in value else f" [{label}:{value}]"
                self.emit(text)
            if tag in {"p", "h2", "h3", "h4", "div", "li"}:
                self.emit("\n")

        def handle_data(self, data):
            if not self.hidden:self.emit(data)

    parser = Text()
    parser.feed(value or "")
    parser.close()
    parser.hidden = 0
    # Malformed HTML still retains its text and formatting role.
    while parser.inline:
        parser.handle_endtag(parser.inline[-1][0])
    while parser.tables:
        if parser.tables[-1]['cell'] is not None:parser.handle_endtag('td')
        if parser.tables[-1]['row']:parser.handle_endtag('tr')
        parser.handle_endtag('table')
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())


def xml_text(element):
    node = copy.copy(element)
    node.tail = None
    return html_text(ET.tostring(node, encoding="unicode"))


def academic_snippet(record, abstract):
    """Expose identity and available abstract to the existing Agent formatter."""
    types = record.get("publication_types") or []
    lines = [f"Title: {record.get('title', '')}",
             f"Journal: {record.get('journal', '')}", f"Date: {record.get('pubdate', '')}",
             f"DOI: {record.get('doi', '')}", f"PMID: {record.get('pmid', '')}",
             f"Publication types: {', '.join(types)}",
             "Evidence level: abstract" if abstract else "Evidence level: metadata only"]
    if abstract:
        lines.append("Abstract: " + abstract[:8000])
        if len(abstract) > 8000:
            lines.append("[Abstract truncated for tool display; complete text retained in source record.]")
    else:
        lines.append("Abstract unavailable.")
    if record.get("related_articles"):
        from .source_relations import notice_url
        lines.append("Publisher-supplied publication relationships:")
        for relation in record["related_articles"]:
            lines.append(f"{relation.get('relation_type', '')}: {notice_url(relation)} (notice text not implied by metadata)")
    return "\n".join(lines)


EUROPEPMC_CONFIG = {
    "module_path": ".engines.search_engine_europepmc",
    "class_name": "EuropePMCSearchEngine",
    "display_name": "Europe PMC",
    "description": (
        "Search Europe PMC life-sciences publications and abstracts. Use its "
        "query syntax, e.g. Visium AND FIRST_PDATE:[2022-01-01 TO 2026-12-31]. "
        "Keep named platforms and date constraints required; use OR only for "
        "equivalent terms. PubMed field tags are not Europe PMC syntax. "
        "Results include publication types; an abstract is not a full paper."
    ),
    "requires_api_key": False,
    "requires_llm": True,
    "is_public": True,
    "is_scientific": True,
    "agent_enabled": True,
    "use_in_auto_search": True,
    "default_params": {},
}

_LOCK = threading.Lock()
_LAST = {}


def pace(service: str, interval: float, *, directory=None, clock=time.monotonic,
         sleep=time.sleep):
    """Coordinate local engine/worker request starts using the shared data dir.

    Other deployments sharing the outbound IP need their own coordination.
    """
    directory = Path(directory or os.environ.get("LDR_DATA_DIR", "/data")) / ".request-pacing"
    with _LOCK:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(directory / (service + ".lock"),
                             os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            value = handle.read().strip()
            try:
                previous = float(value) if value else _LAST.get(service, 0.0)
            except ValueError:
                previous = 0.0
            now = clock()
            if previous > now:  # stale monotonic value from before a reboot
                previous = 0.0
            wait = max(0.0, previous + interval - now)
            if wait:
                sleep(wait)
            now = clock()
            handle.seek(0)
            handle.truncate()
            handle.write(str(now))
            handle.flush()
            _LAST[service] = now


def _retry_delay(response, attempt):
    value = response.headers.get("Retry-After", "")
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = email.utils.parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            delay = 2 ** attempt
    return min(15.0, max(0.0, delay))


def service_get(url, *, service, interval, get=None, sleep=time.sleep, **kwargs):
    """Use LDR's protected client with shared pacing and bounded retries."""
    if get is None:
        from local_deep_research.security.safe_requests import safe_get
        get = safe_get
    kwargs.setdefault("timeout", 30)
    for attempt in range(3):
        pace(service, interval)
        try:
            response = get(url, **kwargs)
        except OSError:
            if attempt == 2:
                raise
            sleep(2 ** attempt)
            continue
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
            response.raise_for_status()
            return response
        delay = _retry_delay(response, attempt)
        response.close()
        sleep(delay)
    raise AssertionError("unreachable")
