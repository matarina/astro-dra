"""Carry publisher-supplied notice relationships without scientific inference."""
import re

from .source_identity import identity_fields
from .textutil import extract_doi

NOTICE_IN = {"erratum_in", "correction_in", "retraction_in"}
NOTICE_FOR = {"erratum_for": "erratum_in", "correction_of": "correction_in",
              "retraction_of": "retraction_in", "retraction_for": "retraction_in"}


def _kind(value):
    return re.sub(r"[\s-]+", "_", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value))).lower()


def _relation(kind, identifier, reference="", source="MED"):
    result = {"relation_type": _kind(kind)}
    value = str(identifier or "").strip()
    if source.upper() == "MED" and value.isdigit():
        result["pmid"] = value
    elif source.upper() == "PMC" and re.fullmatch(r"PMC\d+", value, re.I):
        result["pmcid"] = value.upper()
    doi = extract_doi(reference)
    if doi:
        result["doi"] = doi.casefold()
    return result if len(result) > 1 else None


def epmc_relations(record):
    return [r for item in (record.get("commentCorrectionList") or {}).get("commentCorrection", [])
            if (r := _relation(item.get("type", ""), item.get("id"), item.get("reference", ""), item.get("source", "MED")))]


def pubmed_relations(article):
    return [r for item in article.findall(".//CommentsCorrectionsList/CommentsCorrections")
            if (r := _relation(item.get("RefType", ""), item.findtext("PMID"), item.findtext("RefSource") or ""))]


def notice_url(record):
    if record.get("pmid"):
        return "https://pubmed.ncbi.nlm.nih.gov/" + record["pmid"] + "/"
    if record.get("pmcid"):
        return "https://pmc.ncbi.nlm.nih.gov/articles/" + record["pmcid"] + "/"
    if record.get("doi"):
        return "https://doi.org/" + record["doi"]
    return ""


def associated_notices(sources):
    """Attach known notice metadata/text to its article before source selection.

    No extra fetch. Unavailable notice text is explicit, never reconstructed.
    """
    sources = [source for source in sources if isinstance(source, dict)]
    lookup = {}
    for source in sources:
        for identifier in identity_fields(source).items():
            lookup.setdefault(identifier, []).append(source)

    def resolve(ids):
        matches = {id(s): s for item in ids.items() for s in lookup.get(item, [])}
        return [s for s in matches.values()
                if all(ids[k] == value for k, value in identity_fields(s).items() if k in ids)]

    result = {}
    for source in sources:
        for relation in source.get("related_articles") or []:
            kind = relation.get("relation_type")
            matches = resolve(identity_fields(relation))
            if kind in NOTICE_IN:
                articles, notices = [source], matches or [relation]
                label = kind
            elif kind in NOTICE_FOR:
                articles, notices, label = matches, [source], NOTICE_FOR[kind]
            else:
                continue
            for article in articles:
                for notice in notices:
                    if notice is article:
                        continue
                    ids = identity_fields(notice)
                    fetched, abstract = notice.get("fetched_content"), notice.get("abstract")
                    text = fetched or abstract or notice.get("snippet") or ""
                    item = {**ids, "relation_type": label, "source_index": notice.get("index"),
                            "title": notice.get("title", ""), "url": notice.get("link") or notice_url(ids),
                            "text": text, "evidence_type": "retrieved excerpt" if fetched else "abstract" if abstract else "metadata only"}
                    bucket = result.setdefault(str(article.get("index")), [])
                    identity = (label, tuple(sorted(ids.items())))
                    if not any((x["relation_type"], tuple(sorted(identity_fields(x).items()))) == identity for x in bucket):
                        bucket.append(item)
    return result
