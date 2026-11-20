"""Exact article identity checks for PubMed/PMC downloads."""
import re
import hashlib
import json
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from .retrieval import xml_text


def academic_url_ids(url):
    """Identify supported article URLs by host and path, never by query text."""
    parsed = urlparse(url)
    host, path = (parsed.hostname or "").lower(), parsed.path
    if host in {"pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov"}:
        match = re.fullmatch(r"/(?:pubmed/)?(\d+)/?", path)
        if match:
            return match[1], None
    if host in {"www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"}:
        match = re.match(r"/(?:pmc/)?articles/(PMC\d+)(?:/|$)", path, re.I)
        if match:
            return None, match[1].upper()
    if host == "europepmc.org" or host.endswith(".europepmc.org"):
        match = re.fullmatch(r"/article/MED/(\d+)/?", path, re.I)
        if match:
            return match[1], None
        match = re.match(r"/(?:articles?|article/PMC)/(PMC\d+)(?:/|$)", path, re.I)
        if match:
            return None, match[1].upper()
    return None, None


def own_pmc_id(data, pmid):
    """ELink citation relations are not the requested article's full text."""
    for group in data.get("linksets", []):
        ids = group.get("ids") or []
        if ids and str(pmid) not in {str(i) for i in ids}:
            continue
        for link in group.get("linksetdbs", []):
            if link.get("dbto") != "pmc" or link.get("linkname") != "pubmed_pmc":
                continue
            for value in link.get("links", []):
                if re.fullmatch(r"\d+", str(value)):
                    return "PMC" + str(value)
    return None


def europepmc_record(data, pmid=None, pmcid=None):
    """Select the requested article, never the first search result blindly."""
    for record in data.get("resultList", {}).get("result", []):
        if pmid and not (record.get("source") == "MED" and str(record.get("id")) == str(pmid)):
            continue
        if pmcid and str(record.get("pmcid", "")).upper() != str(pmcid).upper():
            continue
        return record
    return None


def _doi(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value or "").strip(), flags=re.I).casefold()


def article_text(xml, record, pmid=None, *, require_body=False, include_graphic_refs=False):
    """Read own-article text; full-text callers must require an actual body.

    A PMC identifier can resolve to embargoed front matter and abstracts only.
    Identity agreement does not establish that the article body was supplied.
    """
    if include_graphic_refs and require_body:
        # An emitted bookkeeping marker cannot manufacture a textual body.
        if article_text(xml, record, pmid, require_body=True) is None:
            return None
    root = ET.fromstring(xml)
    local = lambda element: element.tag.rsplit("}", 1)[-1]
    meta = next((e for e in root.iter() if local(e) == "article-meta"), None)
    if meta is None:
        return None
    ids = {e.get("pub-id-type"): "".join(e.itertext()).strip()
           for e in meta if local(e) == "article-id"}
    expected = {"pmid": str(pmid or ""), "pmc": str(record.get("pmcid") or ""),
                "doi": _doi(record.get("doi"))}
    found = {"pmid": ids.get("pmid", ""), "pmc": ids.get("pmc") or ids.get("pmcid", ""),
             "doi": _doi(ids.get("doi"))}
    normalize = lambda name, value: value.upper().removeprefix("PMC") if name == "pmc" else value
    matches = []
    for name, value in expected.items():
        if value and found[name]:
            matches.append(normalize(name, value) == normalize(name, found[name]))
    if not matches or not all(matches):
        return None
    # Exclude affiliations, funding and the reference list before any excerpt
    # budget is applied. Preserve paragraph and section boundaries for retrieval.
    def paragraphs(node):
        if include_graphic_refs and local(node) == 'fig':
            parts = [text for child in node for text in paragraphs(child)]
            assets = _graphic_assets(node)
            if assets:
                parts.append('FIGURE ASSETS NOT INSPECTED OR TRANSCRIBED: ' + json.dumps(
                    {'figure_id': node.get('id'), 'assets': assets}, ensure_ascii=False))
            return parts
        if local(node) in {"article-title", "title", "p", "table-wrap", "caption"}:
            text = xml_text(node).strip()
            parts = [text] if text else []
            # Some JATS publishers nest a whole fig inside p. The legacy text
            # parser intentionally flattens that p, so retain its bytes and add
            # the nested locators separately rather than silently skipping them.
            if include_graphic_refs:
                for figure in node.iter():
                    if local(figure) == 'fig' and _graphic_assets(figure):
                        parts.append('FIGURE ASSETS NOT INSPECTED OR TRANSCRIBED: ' + json.dumps(
                            {'figure_id': figure.get('id'), 'assets': _graphic_assets(figure)}, ensure_ascii=False))
            return parts
        if not len(node):
            text = " ".join(xml_text(node).split())
            return [text] if text else []
        return [text for child in node for text in paragraphs(child)]

    title = next((e for e in meta.iter() if local(e) == "article-title"), None)
    abstracts = [e for e in meta if local(e) == "abstract"]
    body = next((e for e in root if local(e) == "body"), None)
    body_parts = paragraphs(body) if body is not None else []
    if require_body and not any(text.strip() for text in body_parts):
        return None
    parts = paragraphs(title) if title is not None else []
    for abstract in abstracts:
        parts.extend(["Abstract", *paragraphs(abstract)])
    parts.extend(body_parts)
    return "\n\n".join(parts) or None


def _graphic_assets(figure):
    """Keep original JATS locators; never synthesize or fetch an image URL."""
    assets = []
    for node in figure.iter():
        if node.tag.rsplit('}', 1)[-1] != 'graphic':
            continue
        href = node.get('{http://www.w3.org/1999/xlink}href') or node.get('href')
        if href:
            assets.append(dict(href=href, content_type=node.get('content-type', 'unknown')))
    return assets


def article_graphics(xml, record, pmid=None):
    """Index own-body JATS figure links and explicit cross references.

    Captions and reference paragraphs are text, not the content of the image.
    This index performs no visual reading, model call, retrieval or entailment.
    Every asset locator remains exactly as supplied, possibly relative.
    """
    if article_text(xml, record, pmid, require_body=True) is None:
        return None
    root = ET.fromstring(xml)
    local = lambda node: node.tag.rsplit('}', 1)[-1]
    meta = next(node for node in root.iter() if local(node) == 'article-meta')
    own_ids = {node.get('pub-id-type'): ''.join(node.itertext()).strip()
               for node in meta if local(node) == 'article-id'}
    body = next((node for node in root if local(node) == 'body'), None)
    parents = {child: parent for parent in body.iter() for child in parent}
    def path(node):
        titles = []
        while node in parents:
            node = parents[node]
            if local(node) == 'sec':
                title = next((child for child in node if local(child) == 'title'), None)
                if title is not None:
                    titles.append(xml_text(title).strip())
        return list(reversed(titles))
    figures = []
    by_id = {}
    for node in body.iter():
        if local(node) != 'fig':
            continue
        figure_id = node.get('id')
        # Missing/duplicate IDs cannot bind an xref unambiguously.
        if not figure_id or figure_id in by_id:
            return None
        label = next((child for child in node if local(child) == 'label'), None)
        caption = next((child for child in node if local(child) == 'caption'), None)
        row = dict(figure_id=figure_id, label=xml_text(label).strip() if label is not None else '',
                   caption=xml_text(caption).strip() if caption is not None else '',
                   section_path=path(node), assets=_graphic_assets(node), references=[],
                   visual_content_status='not_inspected_or_transcribed')
        figures.append(row)
        by_id[figure_id] = row
    unresolved = []
    for ordinal, node in enumerate(n for n in body.iter() if local(n) == 'p'):
        targets = []
        for ref in node.iter():
            if local(ref) == 'xref' and ref.get('ref-type') == 'fig':
                targets.extend((ref.get('rid') or '').split())
        for target in dict.fromkeys(targets):
            entry = dict(paragraph_ordinal=ordinal, section_path=path(node),
                         text=xml_text(node).strip())
            if target in by_id:
                by_id[target]['references'].append(entry)
            else:
                unresolved.append(dict(figure_id=target, **entry))
    raw = xml.encode() if isinstance(xml, str) else xml
    return dict(xml_sha256=hashlib.sha256(raw).hexdigest(), own_article_ids=own_ids, figures=figures,
                unresolved_references=unresolved, semantic_verification='not_performed',
                visual_content_status='not_inspected_or_transcribed')
