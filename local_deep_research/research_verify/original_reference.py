"""Literal archived reference locators; no title matching or identity promotion."""
import hashlib
import re


def _reference_url_fragments(source):
    text=source.get('original_bibliography_entry');expected=source.get('original_bibliography_sha256')
    if not isinstance(text,str)or not text:return []
    if expected!=hashlib.sha256(text.encode()).hexdigest():
        raise ValueError('Original reference hash mismatch')
    blocks=[]
    for match in re.finditer(r'(?im)^URL:[ \t]*(https?://[^\s<>]+)[ \t]*\r?$',text):
        spans=[dict(start=match.start(1),end=match.end(1),text=match[1])]
        offset=match.end()
        if text[offset:offset+1]=='\n':offset+=1
        for line in text[offset:].splitlines(keepends=True):
            fragment=line.strip()
            # A new serialized field (for example DOI:) is not a URL suffix.
            if not fragment or re.match(r'^[A-Za-z][A-Za-z0-9 _-]*:\s',fragment):break
            start=offset+len(line)-len(line.lstrip())
            spans.append(dict(start=start,end=start+len(fragment),text=fragment))
            offset+=len(line)
        blocks.append(spans)
    return blocks


def matching_pdf_annotations(source, annotations, pdf_sha256):
    """Bind literal locator fragments to actual supplied PDF URI annotations.

    The caller owns extraction/hash verification of the PDF. This checks exact
    URI-prefix correspondence, not a title or paper-identity interpretation.
    """
    prefixes=[''.join(s['text']for s in block)for block in _reference_url_fragments(source)]
    result=[]
    for annotation in annotations:
        uri=annotation.get('url')
        if isinstance(uri,str)and any(uri.startswith(prefix)for prefix in prefixes):
            result.append({**annotation,'pdf_sha256':pdf_sha256,
                'url_sha256':hashlib.sha256(uri.encode()).hexdigest(),
                'original_reference_sha256':source['original_bibliography_sha256']})
    return result


def extract_locator_document(raw, anchor, *, max_chars=200_000):
    """Read original-locator PDF or HTML; never assign a scientific source type."""
    if raw.lstrip().startswith(b'%PDF'):
        return extract_locator_pdf(raw,anchor,max_chars=max_chars)
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(raw,'html.parser')
    if not soup.find('html'):
        raise ValueError('Original locator response is neither PDF nor HTML')
    encoding=soup.original_encoding or 'utf-8'
    from .retrieval import html_text
    text=html_text(raw.decode(encoding,errors='replace'))
    if len(text)>max_chars:
        text=text[:max_chars]
        scope='HTML text excerpt; remaining page text not supplied'
    else:
        scope='extracted HTML page text; document completeness unconfirmed'
    if not text.strip():return None
    return (f'ORIGINAL REFERENCE LOCATOR DOCUMENT; paper identity, requested eligibility '
            f'and extraction completeness NOT independently confirmed.\n'
            f"Requested URL: {anchor['url']}\n"
            f"Original reference SHA-256: {anchor['original_reference_sha256']}\n"
            f'Retrieved response SHA-256: {hashlib.sha256(raw).hexdigest()}\n'
            f'Encoding used: {encoding}; scope: {scope}.\n'
            'This page may be navigation, commentary, a review or an article. '
            'Do not infer publication type, identity or scientific authority from acquisition.\n\n'+text)


def extract_locator_pdf(raw, anchor, *, max_pages=40, max_chars=200_000):
    """Extract candidate locator text without asserting paper identity/completeness."""
    import io

    if not raw.lstrip().startswith(b'%PDF'):
        raise ValueError('Original locator response is not a PDF')
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    if len(reader.pages) > max_pages:
        raise ValueError('Original locator PDF exceeds page bound')
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ''
        if sum(map(len, pages)) + 2 * len(pages) + len(text) > max_chars:
            raise ValueError('Original locator PDF exceeds text bound')
        pages.append(text)
    text = '\n\n'.join(pages)
    if not text.strip():
        return None
    # This warning travels WITH the actual model text, not just a private receipt.
    warning = ('ORIGINAL REFERENCE LOCATOR DOCUMENT; paper identity, requested '
               'eligibility and extraction completeness NOT independently confirmed.\n'
               f"Requested URL: {anchor['url']}\n"
               f"Original reference SHA-256: {anchor['original_reference_sha256']}\n"
               f"Retrieved PDF SHA-256: {hashlib.sha256(raw).hexdigest()}\n"
               'Do not infer identity, publication date or support from this locator.\n\n')
    return warning + text


def original_reference_urls(source):
    result=[]
    for spans in _reference_url_fragments(source):
        common=dict(source_index=source.get('index'),original_reference_sha256=source['original_bibliography_sha256'],
                    binding_status='original_reference_locator_only')
        if len(spans)==1:
            s=spans[0];result.append(dict(**common,url=s['text'],start=s['start'],end=s['end']))
            continue
        prefix=''.join(s['text']for s in spans)
        annotations=[]
        for a in source.get('original_locator_annotations',[]):
            uri=a.get('url','')
            if (isinstance(uri,str)and uri.startswith(prefix)and
                a.get('original_reference_sha256')==common['original_reference_sha256']and
                a.get('url_sha256')==hashlib.sha256(uri.encode()).hexdigest()and
                re.fullmatch(r'[a-f0-9]{64}',str(a.get('pdf_sha256','')))):
                annotations.append(a)
        if not annotations:
            raise ValueError('Wrapped original reference requires matching PDF URI annotation')
        for uri in dict.fromkeys(a['url']for a in annotations):
            result.append(dict(**common,url=uri,start=None,end=None,reference_fragment_spans=spans,
                locator_origin='archived_pdf_uri_annotation',
                annotation_occurrences=[a for a in annotations if a['url']==uri]))
    return result
