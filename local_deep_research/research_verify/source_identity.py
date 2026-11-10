"""Bibliographic identifiers from explicit metadata and canonical article URLs.

No title matching, article-body DOI mining, or network requests.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from .textutil import extract_doi

FIELDS = ("doi", "pmid", "pmcid")


def url_identifiers(url):
    try:
        p = urlsplit(str(url or ""))
    except ValueError:
        return {}
    if p.scheme.lower() not in {"http", "https"}:
        return {}
    host, path = (p.hostname or "").lower().rstrip("."), unquote(p.path)
    if host in {"doi.org", "dx.doi.org"}:
        doi = extract_doi(path.lstrip("/"))
        return {"doi": doi.casefold()} if doi else {}
    if host in {"pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        m = re.fullmatch(r"/(?:pubmed/)?(\d+)/?", path)
        if m:
            return {"pmid": m[1]}
    if host in {"pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        m = re.fullmatch(r"/(?:pmc/)?articles/(PMC\d+)/?", path, re.I)
        if m:
            return {"pmcid": m[1].upper()}
    if host in {"europepmc.org", "www.europepmc.org"}:
        m = re.fullmatch(r"/article/(MED|PMC)/(\w+)/?", path, re.I)
        if m and m[1].upper() == "MED" and m[2].isdigit():
            return {"pmid": m[2]}
        if m and m[1].upper() == "PMC" and re.fullmatch(r"PMC\d+", m[2], re.I):
            return {"pmcid": m[2].upper()}
    if host in {"nature.com", "www.nature.com"}:
        m = re.fullmatch(r"/articles/([^/]+)/?", path)
        if m:
            doi = extract_doi("10.1038/" + m[1].removesuffix(".pdf"))
            if doi:
                return {"doi": doi.casefold()}
    if host in {"link.springer.com", "link.springernature.com"} or host.endswith(".biomedcentral.com"):
        m = re.fullmatch(r"/articles?/(10\.\d{4,9}/[^/]+)/?", path)
        if m:
            doi = extract_doi(m[1])
            if doi:
                return {"doi": doi.casefold()}
    return {}


def explicit_identifiers(source):
    result = {}
    doi = extract_doi(source.get("doi"), source.get("DOI"))
    if doi:
        result["doi"] = doi.casefold()
    pmid = str(source.get("pmid") or source.get("_pmid") or "").strip()
    if pmid.isdigit():
        result["pmid"] = pmid
    pmcid = str(source.get("pmcid") or "").strip().upper()
    if re.fullmatch(r"PMC\d+", pmcid):
        result["pmcid"] = pmcid
    return result


def identity_fields(source):
    explicit = explicit_identifiers(source)
    inferred = url_identifiers(source.get("link") or source.get("url"))
    # Contradictory metadata cannot establish an alias to the linked paper.
    if any(explicit[k] != inferred[k] for k in explicit.keys() & inferred.keys()):
        return explicit
    return {**inferred, **explicit}


def with_identity(source):
    result = dict(source)
    result.update(identity_fields(source))
    return result


def reconcile_identities(sources):
    """Backfill aliases without collapsing text records or conflicting IDs."""
    records = [with_identity(s) if isinstance(s, dict) else s for s in sources]
    parents = list(range(len(records)))
    identities = [identity_fields(s) if isinstance(s, dict) else {} for s in records]

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, ids in enumerate(identities):
        for item in ids.items():
            owners.setdefault(item, []).append(i)
    for indices in owners.values():
        groups = list(dict.fromkeys(root(i) for i in indices))
        combined = {}
        conflict = False
        for i in groups:
            if any(k in combined and combined[k] != v for k, v in identities[i].items()):
                conflict = True
                break
            combined.update(identities[i])
        if conflict:
            continue
        for i in groups[1:]:
            parents[i] = groups[0]
        identities[groups[0]] = combined
    for i, source in enumerate(records):
        if isinstance(source, dict):
            for key, value in identities[root(i)].items():
                if not source.get(key):
                    source[key] = value
    return records
