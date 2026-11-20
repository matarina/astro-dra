"""API-record provenance and literal metadata binding, without network requests.

These receipts document adapter processing, not cryptographic authentication,
peer review, relevance, source truth or claim entailment.
"""
from __future__ import annotations
import hashlib
import json
import re
from urllib.parse import urlsplit

from .textutil import extract_doi, normalize_title


ENDPOINTS = {
    "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
    "crossref": "https://api.crossref.org/works/",
}


def _title(value):
    from .retrieval import html_text
    if isinstance(value, list):
        value = " ".join(x for x in value if isinstance(x, str))
    return " ".join(html_text(value if isinstance(value, str) else "").split())


def _pmid(value):
    value = str(value or "")
    return value if re.fullmatch(r"[1-9][0-9]*", value) else None


def make_record_provenance(provider, record):
    """Describe a returned record, deriving identifiers from that record only."""
    if provider not in ENDPOINTS or not isinstance(record, dict):
        return None
    ids, record_source, record_type = {}, "", []
    if provider == "europepmc":
        record_id, record_source = str(record.get("id") or ""), str(record.get("source") or "")
        if not record_id or not record_source:
            return None
        if record_source == "MED" and not _pmid(record_id):
            return None
        if record_source in {"PMC", "PPR"} and not re.fullmatch(record_source+r"[1-9][0-9]*", record_id):
            return None
        pmid = _pmid(record.get("pmid") or (record_id if record_source == "MED" else None))
        pmcid = str(record.get("pmcid") or (record_id if record_source == "PMC" else "")).upper()
        doi = extract_doi(record.get("doi"))
        title = _title(record.get("title"))
        record_type = (record.get("pubTypeList") or {}).get("pubType") or []
        state = "preprint" if record_source == "PPR" else "indexed_record"
    elif provider == "pubmed":
        record_id = _pmid(record.get("uid"))
        if not record_id or record.get("error"):
            return None
        pmid, pmcid, doi = record_id, "", extract_doi(record.get("doi"))
        for item in record.get("articleids") or []:
            if not isinstance(item, dict):
                continue
            if item.get("idtype") == "doi" and not doi:
                doi = extract_doi(item.get("value"))
            if item.get("idtype") == "pmc":
                pmcid = str(item.get("value") or "").upper()
        title, record_type, state = _title(record.get("title")), record.get("pubtype") or [], "indexed_record"
    else:
        doi = extract_doi(record.get("DOI"))
        if not doi:
            return None
        record_id, pmid, pmcid = doi.casefold(), None, ""
        title = _title(record.get("title"))
        record_type = [record["type"]] if isinstance(record.get("type"), str) else []
        state = "preprint" if record.get("subtype") == "preprint" else "registered_record"
    if pmid:
        ids["pmid"] = pmid
    if re.fullmatch(r"PMC\d+", pmcid):
        ids["pmcid"] = pmcid
    if doi:
        ids["doi"] = doi.casefold()
    if provider == "europepmc" and record_source == "PPR":
        ids["ppr"] = record_id
    if provider == "europepmc":
        # Other indexed collections can have opaque IDs. Preserve the API's
        # source/ID namespace without a biomedical-only source-code gate.
        ids["epmc_record"] = record_source+":"+record_id
    if not ids:
        return None
    if isinstance(record_type, str):
        record_type = [record_type]
    if any(str(t).casefold() in {"preprint", "prepublication"} for t in record_type):
        state = "preprint"
    return {"schema_version": "api-record-1", "provider": provider,
            "endpoint": ENDPOINTS[provider], "record_id": record_id,
            "record_source": record_source, "identifiers": ids, "title": title,
            "record_types": record_type, "record_state": state,
            "record_sha256": hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "scope": "bibliographic_metadata_only"}


def bind_record_provenance(source, source_ids, receipt):
    """Check explicit identifiers/title against a receipt; never fuzzy match."""
    unknown = {"status": "candidate", "reason": "no_matching_api_record", "scope": "bibliographic_metadata_only"}
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "api-record-1":
        return unknown
    provider = receipt.get("provider")
    if provider not in ENDPOINTS or receipt.get("endpoint") != ENDPOINTS[provider]:
        return unknown
    if not re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("record_sha256") or "")):
        return unknown
    ids = receipt.get("identifiers")
    if not isinstance(ids, dict) or not ids:
        return unknown
    local = dict(source_ids)
    # A provider index record is stable even when no DOI/PMID is supplied.
    url = str(source.get("link") or source.get("url") or "")
    try:
        parsed = urlsplit(url)
        if provider == "europepmc" and parsed.hostname in {"europepmc.org", "www.europepmc.org"}:
            match = re.fullmatch(r"/article/([^/]+)/([^/]+)/?", parsed.path)
            if match:
                local["epmc_record"] = match[1]+":"+match[2]
    except ValueError:
        pass
    evidence = {"provider": provider, "record_id": receipt.get("record_id"),
                "record_sha256": receipt["record_sha256"], "scope": "bibliographic_metadata_only"}
    def key_value(key, value):
        # DOI syntax is case-insensitive; opaque provider IDs need not be.
        return str(value).casefold() if key == "doi" else str(value)
    if any(key in ids and key_value(key, ids[key]) != key_value(key, value) for key, value in local.items()):
        return {**evidence, "status": "conflict", "reason": "record_identifier_mismatch"}
    if not local or any(key not in ids for key in local):
        return {**evidence, "status": "candidate", "reason": "identifiers_not_all_in_record"}
    local_title, remote_title = _title(source.get("title") or source.get("name")), receipt.get("title")
    if local_title and not remote_title:
        return {**evidence, "status": "candidate", "reason": "record_title_unavailable"}
    # Same-ID bibliographic comparison uses the validator's existing cosmetic
    # normalization. This is not a title-only merge or scientific inference.
    if local_title and normalize_title(local_title) != normalize_title(remote_title):
        return {**evidence, "status": "conflict", "reason": "record_title_metadata_difference"}
    return {**evidence, "status": "confirmed", "reason": "api_record_metadata_bound",
            "record_state": receipt.get("record_state", "unknown"), "identifiers": ids,
            "record_types": receipt.get("record_types") or []}
