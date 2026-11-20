"""Bibliographic identifiers, canonical URLs, and source provenance.

This module deliberately stays deterministic: it does not do title matching,
article-body DOI mining, or network requests.  Network-backed identity checks
belong to :mod:`doi_validator` and the PubMed/Europe PMC adapters.  The
provenance helpers here make it impossible for an arbitrary web hit to look
like a formally published paper merely because it has a title and a URL.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, unquote, urlunsplit, urlsplit

from .textutil import extract_doi

FIELDS = ("doi", "pmid", "pmcid")

_TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source", "utm_campaign",
    "utm_content", "utm_medium", "utm_name", "utm_source", "utm_term",
}
_PREPRINT_HOSTS = {
    "biorxiv.org", "medrxiv.org", "arxiv.org", "researchsquare.com",
    "ssrn.com", "preprints.org",
}
_WEB_SOURCE_HOSTS = {
    "10xgenomics.com", "bioconductor.org", "researchgate.net",
    "news-medical.net", "scitechdaily.com", "omicsempower.com",
    "cd-genomics.com", "sangerinstitute.blog", "youtube.com",
}
_PREPRINT_TYPES = {"preprint", "posted content", "prepublication"}
_PREPRINT_JOURNAL_MARKERS = {
    "biorxiv", "medrxiv", "research square", "arxiv", "ssrn",
    "preprints.org",
}
_NON_ARTICLE_TYPES = {
    "conference abstract", "meeting abstract", "poster", "editorial",
    "letter", "news", "comment", "published erratum", "correction",
}
_CONFERENCE_TYPES = {"conference abstract", "meeting abstract", "poster"}
_EDITORIAL_TYPES = {"editorial", "letter", "comment", "news"}
_REVIEW_TYPES = {"review", "systematic review", "meta-analysis"}
_SUPPLEMENT_TYPES = {"published erratum", "correction"}


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


def canonical_url(url) -> str:
    """Return a stable, credential-free URL key for an article or document.

    Tracking parameters and fragments are presentation details.  Query
    parameters that are not tracking fields are retained because some
    repositories use them to identify a document.  Invalid or non-http URLs
    return an empty string instead of becoming a citation identity.
    """
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parts.port
    except ValueError:
        return ""
    netloc = host
    if port and not ((parts.scheme.lower() == "http" and port == 80) or
                     (parts.scheme.lower() == "https" and port == 443)):
        netloc += f":{port}"
    path = unquote(parts.path or "/")
    path = re.sub(r"/{2,}", "/", path)
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                             if key.casefold() not in _TRACKING_PARAMS))
    return urlunsplit((parts.scheme.lower(), netloc, path or "/", query, ""))


def _host(url) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _host_matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def source_kind(source: dict) -> str:
    """Classify the origin of a source without claiming scientific validity."""
    if not isinstance(source, dict):
        return "unknown"
    content_type = str(source.get("content_type") or "").casefold().replace("-", "_")
    title = str(source.get("title") or source.get("name") or "").casefold()
    url = source.get("link") or source.get("url") or ""
    host = _host(url)
    try:
        path = str(urlsplit(str(url)).path or "").casefold() if url else ""
    except ValueError:
        path = ""
    engine = str(source.get("source_engine") or source.get("source") or "").casefold()
    types = {str(item).casefold().strip() for item in (source.get("publication_types") or [])}
    journal = str(
        source.get("journal") or source.get("journal_title")
        or source.get("publication_name") or source.get("container_title") or ""
    ).casefold()
    if content_type in {"search_results", "search_results_page", "search_page", "search"}:
        return "search_result"
    if path in {"/search", "/search/", "/query", "/query/"}:
        return "search_result"
    # Europe PMC uses /article/PPR/<id> for preprints; the path check is
    # intentionally separate from the host-only preprint domains.
    epmc_preprint = (host in {"europepmc.org", "www.europepmc.org"}
                     and re.match(r"^/article/ppr(?:/|$)", path) is not None)
    if (types & _PREPRINT_TYPES or epmc_preprint or _host_matches(host, _PREPRINT_HOSTS)
            or journal.strip() in _PREPRINT_JOURNAL_MARKERS):
        return "preprint"
    if _host_matches(host, _WEB_SOURCE_HOSTS):
        if host.endswith("10xgenomics.com"):
            return "vendor"
        if "researchgate" in host:
            return "repository_copy"
        return "web_document"
    if host in {"pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        return "pubmed_record"
    if host in {"europepmc.org", "www.europepmc.org"}:
        return "europepmc_record"
    if host in {"pmc.ncbi.nlm.nih.gov"}:
        return "pmc_record"
    if host in {"doi.org", "dx.doi.org"} or "doi" in content_type:
        return "doi_record"
    if source.get("publication_types") or source.get("journal") or source.get("pmid"):
        return "publisher_article"
    if engine in {"pubmed", "europepmc", "europe pmc"}:
        return "academic_record"
    if source.get("fetched_content") or source.get("content"):
        return "web_document"
    return "unknown"


def document_type(source: dict) -> str:
    """Classify the document artifact without inferring scientific meaning.

    The classification uses explicit publication-type metadata and explicit
    content/URL fields.  Titles alone never turn a normal article into a
    conference abstract, supplement, letter, or editorial.
    """
    if not isinstance(source, dict):
        return "unknown"
    content_type = str(source.get("content_type") or "").casefold().replace("-", "_")
    proof = identity_provenance(source)
    authoritative_types = proof.get("record_types") if proof["status"] == "confirmed" else None
    explicit = str(source.get("document_type") or "").casefold().strip()
    types = {str(item).casefold().strip() for item in (authoritative_types or source.get("publication_types") or [])}
    url = str(source.get("link") or source.get("url") or "")
    host = _host(url)
    if content_type in {"supplement", "supplementary", "supplementary_material"}:
        return "supplement"
    if explicit and not authoritative_types:
        return explicit
    if types & _CONFERENCE_TYPES:
        return "conference_abstract"
    if types & _EDITORIAL_TYPES:
        if "letter" in types:
            return "letter"
        if "comment" in types:
            return "comment"
        if "news" in types:
            return "news"
        return "editorial"
    if types & _REVIEW_TYPES:
        return "review"
    if types & _SUPPLEMENT_TYPES:
        return "correction_or_erratum"
    if types & {"research-article", "original article", "clinical trial"}:
        return "research_article"
    if types & {"journal article", "journal-article"}:
        return "journal_article"
    if proof.get("record_state") == "preprint" or source_kind(source) == "preprint" or host in _PREPRINT_HOSTS:
        return "preprint"
    return "unknown"


def publication_state(source: dict) -> str:
    """Describe indexed/registered metadata; origin does not establish publication."""
    proof = identity_provenance(source)
    return proof.get("record_state", "unknown") if proof["status"] == "confirmed" else "unknown"


def identity_provenance(source: dict) -> dict:
    """Bind supplied identifiers/title to processed API metadata, if available.

    A URL template, bare boolean or generic warning is not such evidence.
    Receipts document adapter processing, not a security/authenticity boundary.
    """
    from .record_identity import bind_record_provenance
    if not isinstance(source, dict):
        return {"status": "missing", "reason": "source_not_mapping"}
    ids = identity_fields(source)
    explicit = explicit_identifiers(source)
    linked = url_identifiers(source.get("link") or source.get("url"))
    if any(explicit[key] != linked[key] for key in explicit.keys() & linked.keys()):
        return {"status": "conflict", "reason": "explicit_identifier_url_conflict",
                "scope": "bibliographic_metadata_only"}
    verify = source.get("_verify") if isinstance(source.get("_verify"), dict) else {}
    check_ids = explicit_identifiers(verify)
    if any(ids[key] != check_ids[key] for key in ids.keys() & check_ids.keys()):
        return {"status": "conflict", "reason": "check_identifier_binding_conflict",
                "scope": "bibliographic_metadata_only"}
    receipts = [source.get("record_provenance")]
    if verify.get("verified") is True:
        receipts.append(verify.get("record_provenance"))
    checks = [bind_record_provenance(source, ids, receipt) for receipt in receipts if isinstance(receipt, dict)]
    confirmed = next((check for check in checks if check["status"] == "confirmed"), None)
    if confirmed:
        other = [check for check in checks if check is not confirmed and check["status"] != "confirmed"]
        return {**confirmed, **({"other_record_checks": other} if other else {})}
    conflict = next((check for check in checks if check["status"] == "conflict"), None)
    if conflict:
        return conflict
    return {"status": "candidate" if ids or canonical_url(source.get("link") or source.get("url")) else "missing",
            "reason": checks[0]["reason"] if checks else "no_matching_api_record",
            "lookup_status": verify.get("lookup_status", "unreported"),
            "scope": "bibliographic_metadata_only"}


def peer_review_status(source: dict) -> str:
    """Read a supplied boolean assertion; origin alone does not establish review.

    A preprint may acquire public reviews, and an index/journal record need not
    establish review of this version. This function performs no verification.
    """
    if not isinstance(source, dict):
        return "unknown"
    value = source.get("peer_reviewed")
    if isinstance(value, bool):
        return "peer_reviewed" if value else "not_peer_reviewed"
    return "unknown"


def publication_status(source: dict) -> tuple[str, str]:
    """Return ``(status, reason)`` for formal bibliography handling.

    ``formal`` means that the record has a stable identity and came from an
    authoritative academic record or a positively verified DOI/PMID. It says
    nothing by itself about research-article type, peer review, relevance, or
    whether the record satisfies a user scope. Those states are returned by
    :func:`document_type`, :func:`peer_review_status`, and
    :func:`publication_state`. A publisher-looking URL alone remains
    ``unverified``. This is a provenance label, not a report-wide gate.
    """
    if not isinstance(source, dict):
        return "unverified", "source_not_mapping"
    kind = source_kind(source)
    # URL-derived values are candidate identifiers. Fetched API metadata must
    # bind them before a record enters the confirmed bibliography group.
    ids = identity_fields(source)
    proof = identity_provenance(source)
    if proof["status"] == "conflict":
        return "conflict", proof["reason"]
    # Origin describes transport, not whether the identified record exists or
    # was published. A bound receipt establishes bibliographic metadata only.
    if proof["status"] == "confirmed":
        if proof.get("record_state") == "preprint":
            return "preprint", "api_record_metadata_bound"
        return "formal", "api_record_metadata_bound"
    if kind == "search_result":
        return "nonformal", "search_results_page"
    if kind == "preprint":
        return "preprint", "preprint_origin_identity_unconfirmed"
    if ids:
        return "unverified", "identity_not_confirmed"
    if proof["status"] == "candidate":
        return "unverified", proof["reason"]
    return "unverified", "missing_stable_identifier"


def classify_source(source: dict) -> dict:
    """Return deterministic provenance fields without mutating ``source``."""
    result = dict(source or {})
    ids = identity_fields(result)
    result.update(ids)
    status, reason = publication_status(result)
    result["canonical_url"] = canonical_url(result.get("link") or result.get("url"))
    result["source_kind"] = source_kind(result)
    result["document_type"] = document_type(result)
    result["publication_state"] = publication_state(result)
    result["peer_review_status"] = peer_review_status(result)
    result["identity_provenance"] = identity_provenance(result)
    value = result.get("peer_reviewed")
    result["peer_review_status_provenance"] = (
        {"source_field": "peer_reviewed", "value": value,
         "evidence_kind": "provided_metadata", "verification": "not_independently_verified"}
        if isinstance(value, bool) else
        {"source_field": None, "evidence_kind": "unknown",
         "reason": "no_explicit_peer_review_metadata"}
    )
    for state_key in ("relevance_status", "evidence_scope", "temporal_validity", "contradiction_status"):
        result[state_key] = result.get(state_key) or "unknown"
    result["publication_status"] = status
    result["publication_status_reason"] = reason
    result["identity_status"] = result["identity_provenance"]["status"]
    result["formal_citation_allowed"] = status == "formal"
    return result


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
    return classify_source(source)


def reconcile_identities(sources):
    """Backfill aliases without collapsing text records or conflicting IDs."""
    records = [with_identity(s) if isinstance(s, dict) else s for s in sources]
    parents = list(range(len(records)))
    identities = [identity_fields(s) if isinstance(s, dict) else {} for s in records]
    canonical_urls = [canonical_url((s.get("link") or s.get("url")) if isinstance(s, dict) else "")
                      for s in records]

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, ids in enumerate(identities):
        for item in ids.items():
            owners.setdefault(item, []).append(i)
        if canonical_urls[i]:
            owners.setdefault(("url", canonical_urls[i]), []).append(i)
    # First reconcile records that expose the same stable identifier.
    for key, indices in owners.items():
        if key[0] == "url":
            continue
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
    # A canonical URL may be an alias for a stable-ID record, but it must not
    # collapse two records that carry different identifiers.  Records without
    # stable IDs can still be deduplicated by the canonical URL.
    for key, indices in owners.items():
        if key[0] != "url":
            continue
        groups = list(dict.fromkeys(root(i) for i in indices))
        stable = {
            tuple(sorted(identities[group].items()))
            for group in groups
            if identities[group]
        }
        if len(stable) > 1:
            continue
        if not groups:
            continue
        target = groups[0]
        for group in groups[1:]:
            parents[group] = target
        if stable:
            identities[target].update(dict(next(iter(stable))))
    for i, source in enumerate(records):
        if isinstance(source, dict):
            for key, value in identities[root(i)].items():
                if not source.get(key):
                    source[key] = value
            source.update(classify_source(source))
    return records
