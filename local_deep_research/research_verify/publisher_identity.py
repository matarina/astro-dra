"""Explicit publisher PII to PubMed identifiers; no title matching or merging.

This optional metadata helper has no production caller. A binding identifies a
paper, not whether the paper supports any report assertion or was read before.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from .original_reference import original_reference_urls
from .source_identity import identity_fields


def normalized_pii(value):
    if not isinstance(value,str):return None
    value=re.sub(r'[-()\s]','',value).upper()
    return value if re.fullmatch(r'S[0-9X]{16}',value) else None


def publisher_url_pii(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https'):return None
    host=(parsed.hostname or '').lower()
    if host in ('sciencedirect.com','www.sciencedirect.com'):
        pattern=r'/science/article/(?:abs/)?pii/([^/]+)/?'
    elif host=='linkinghub.elsevier.com':
        pattern=r'/retrieve/pii/([^/]+)/?'
    elif host in ('cell.com','www.cell.com'):
        # Cell article routes embed the same publisher PII. Decode literal
        # URL punctuation; never infer a paper from the journal slug/title.
        path=unquote(parsed.path)
        match=re.fullmatch(r'/[A-Za-z0-9_-]+/(fulltext|pdf)/([^/]+)/?',path)
        if not match:return None
        value=match[2]
        if match[1]=='pdf' and value.endswith('.pdf'):value=value[:-4]
        return normalized_pii(value)
    else:return None
    match=re.fullmatch(pattern,unquote(parsed.path))
    return normalized_pii(match[1]) if match else None


def pubmed_pii_identity(xml,*,pmid,doi):
    """Read ONLY the requested article's PubmedData, never cited-paper IDs."""
    expected=identity_fields(dict(pmid=pmid,doi=doi))
    if not expected.get('pmid') or not expected.get('doi'):return None
    root=ET.fromstring(xml)
    records=[node for node in root.findall('./PubmedArticle')
             if node.findtext('./MedlineCitation/PMID')==expected['pmid']]
    if len(records)!=1:return None
    ids={}
    for node in records[0].findall('./PubmedData/ArticleIdList/ArticleId'):
        kind=node.get('IdType');value=(node.text or '').strip()
        ids.setdefault(kind,set()).add(value)
    dois={identity_fields({'doi':value}).get('doi') for value in ids.get('doi',())}
    piis={normalized_pii(value) for value in ids.get('pii',())}
    pubmed_ids=ids.get('pubmed',set())
    if dois!={expected['doi']} or len(piis)!=1 or None in piis:return None
    if pubmed_ids and pubmed_ids!={expected['pmid']}:return None
    return dict(pmid=expected['pmid'],doi=expected['doi'],pii=next(iter(piis)))


def bind_original_pii(source,known_record,xml):
    """Return an exact alias proof; do not edit records or renumber citations."""
    target=identity_fields(known_record);existing=identity_fields(source)
    if any(target.get(k)!=v for k,v in existing.items()):return None
    anchors=original_reference_urls(source)
    candidates=[(a['url'],publisher_url_pii(a['url'])) for a in anchors]
    candidates=[(url,pii) for url,pii in candidates if pii]
    if len({pii for _,pii in candidates})!=1:return None
    identity=pubmed_pii_identity(xml,pmid=target.get('pmid'),doi=target.get('doi'))
    if not identity or identity['pii']!=candidates[0][1]:return None
    return dict(kind='exact_original_publisher_pii_pubmed_article_ids',
                source_index=str(source.get('index','')),known_source_index=str(known_record.get('index','')),
                original_locator=candidates[0][0],**identity,
                scope='Article identity only; no claim entailment, full-text access or historical exposure')
