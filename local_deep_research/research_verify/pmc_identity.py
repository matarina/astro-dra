"""Exact article identity checks for PubMed/PMC downloads."""
import re
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


def article_text(xml, record, pmid=None):
    """Read identifiers from article metadata, excluding the reference list."""
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
        if local(node) in {"article-title", "title", "p", "table-wrap", "caption"}:
            text = xml_text(node).strip()
            return [text] if text else []
        if not len(node):
            text = " ".join(xml_text(node).split())
            return [text] if text else []
        return [text for child in node for text in paragraphs(child)]

    title = next((e for e in meta.iter() if local(e) == "article-title"), None)
    abstracts = [e for e in meta if local(e) == "abstract"]
    body = next((e for e in root if local(e) == "body"), None)
    parts = paragraphs(title) if title is not None else []
    for abstract in abstracts:
        parts.extend(["Abstract", *paragraphs(abstract)])
    if body is not None:
        parts.extend(paragraphs(body))
    return "\n\n".join(parts) or None
