"""Bounded publication-version and disputed-evidence retrieval, without LLMs.

Only explicit publisher version links are followed. New versions get separate
source IDs and text; no DOI replacement or silent mixing of text versions.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import time
from urllib.parse import urlsplit

from .retrieval import html_text, academic_snippet, pace
from .pmc_identity import europepmc_record, article_text
from .source_identity import identity_fields, reconcile_identities
from .source_relations import epmc_relations


class EvidenceFetcher:
    def __init__(self, settings=None, *, get=None, seconds=30, requests=6):
        self.settings = settings or {}
        self.get = get
        self.seconds_left = seconds
        self.deadline = time.monotonic() + seconds
        self.events = []
        self.article_cache = {}
        self.remaining = requests
        self._context = self.settings.get('_egress_context')

    def permit(self, engine=None, url=None):
        if self.get is not None:  # Explicit transport injection for offline tests.
            return
        from local_deep_research.security.egress.policy import (
            context_from_snapshot, resolve_run_primary_engine, evaluate_engine, evaluate_url)
        if self._context is None:
            primary = resolve_run_primary_engine(self.settings)
            self._context = context_from_snapshot(self.settings,primary,
                username=self.settings.get('_username'))
        decision = (evaluate_engine(engine,self._context,settings_snapshot=self.settings) if engine else
                    evaluate_url(url,self._context))
        if not decision.allowed:
            raise PermissionError('Evidence retrieval denied: '+decision.reason)

    def read(self, url, *, params=None, limit=2_000_000, service=None, internal=False,
             request_seconds=5):
        return self.read_bytes(url,params=params,limit=limit,service=service,
                               internal=internal, request_seconds=request_seconds).decode('utf-8',errors='replace')

    def read_bytes(self, url, *, params=None, limit=2_000_000, service=None, internal=False,
                   request_seconds=5):
        """Preserve binary primary documents under the same policy and budgets."""
        if self.remaining <= 0 or self.seconds_left <= 0:
            raise TimeoutError("Evidence retrieval budget exhausted")
        started = time.monotonic()
        self.deadline = started + self.seconds_left
        self.remaining -= 1
        response = None
        try:
            if not internal:self.permit(url=url)
            if service:pace(service, .35)
            if time.monotonic() >= self.deadline:
                raise TimeoutError("Evidence retrieval budget exhausted")
            if self.get is None:
                from local_deep_research.security.safe_requests import safe_get
                get = safe_get
            else:
                get = self.get
            timeout = max(.1, min(request_seconds, self.deadline - time.monotonic()))
            options = {'allow_private_ips':True} if internal else {}
            if not internal:
                import os
                proxy = (os.environ.get('LDR_SEARCH_PROXY_URL') or
                         os.environ.get('LDR_SEARCH_HTTP_PROXY') or '').strip()
                if proxy:
                    options['proxies'] = {'http': proxy, 'https': proxy}
            response = get(url, params=params, timeout=(min(3, timeout), timeout), stream=True, **options)
            if service and getattr(response, "status_code", None) == 429 and self.remaining:
                from .retrieval import _retry_delay
                delay = _retry_delay(response, 0, maximum=None)
                if delay < self.deadline - time.monotonic():
                    self.events.append({"host": urlsplit(url).hostname,
                                        "status": "rate_limited", "retry_after": delay})
                    response.close()
                    response = None
                    self.remaining -= 1
                    time.sleep(delay)
                    pace(service, .35)
                    timeout = min(request_seconds, self.deadline - time.monotonic())
                    if timeout <= 0:
                        raise TimeoutError("Evidence retrieval budget exhausted")
                    response = get(url, params=params, timeout=(min(3, timeout), timeout),
                                   stream=True, **options)
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > limit or time.monotonic() > self.deadline:
                    raise TimeoutError("Evidence response exceeds retrieval budget")
                chunks.append(chunk)
            self.events.append({'host':urlsplit(url).hostname,'status':'retrieved','bytes':size})
            return b''.join(chunks)
        except Exception as exc:
            self.events.append({'host':urlsplit(url).hostname,'error_type':type(exc).__name__,
                'http_status':getattr(getattr(exc,'response',None),'status_code',None)})
            raise
        finally:
            self.seconds_left = max(0,self.seconds_left-(time.monotonic()-started))
            if response is not None:response.close()

    def record(self, identifiers):
        import json
        self.permit(engine='europepmc')
        ids = identity_fields(identifiers)
        if ids.get('pmid'):
            query = f"EXT_ID:{ids['pmid']} AND SRC:MED"
        elif ids.get('doi'):
            query = f'DOI:"{ids["doi"]}"'
        elif ids.get('pmcid'):
            query = f"PMCID:{ids['pmcid']}"
        else:
            return None
        raw = json.loads(self.read('https://www.ebi.ac.uk/europepmc/webservices/rest/search',
            params={'query':query,'resultType':'core','format':'json','pageSize':1}, service='europepmc'))
        for record in raw.get('resultList', {}).get('result', []):
            found = {'pmid':str(record.get('pmid') or (record.get('id') if record.get('source')=='MED' else '') or ''),
                     'pmcid':record.get('pmcid'), 'doi':record.get('doi')}
            actual = identity_fields(found)
            if not any(actual.get(k) == v for k,v in ids.items()):
                continue
            if any(actual[k] != ids[k] for k in actual.keys() & ids.keys()):
                continue
            return record
        return None

    def pmc_identifiers(self, pmcid):
        """Official PMC metadata fallback; never download article text."""
        import json
        expected=identity_fields({'pmcid':pmcid}).get('pmcid')
        if not expected:return None
        self.permit(engine='pubmed')
        raw=json.loads(self.read('https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/',
            params={'ids':expected,'format':'json','tool':'astro-dra'},service='pubmed'))
        for record in raw.get('records',[]):
            if isinstance(record,dict) and str(record.get('pmcid','')).upper()==expected:
                return identity_fields(record)
        return None

    def article(self, source):
        identifiers = identity_fields(source)
        document_enabled = self.settings.get('citation.original_reference_document_followup') is True
        locator_enabled = document_enabled or self.settings.get('citation.original_reference_pdf_followup') is True
        anchors = []
        if not identifiers and locator_enabled:
            from .original_reference import original_reference_urls
            anchors = original_reference_urls(source)
        # Unknown records must not share the old empty-URL cache entry. A
        # literal original-reference digest is a locator key, never a paper ID.
        key = tuple(sorted(identifiers.items())) or (
            ('url', source.get('link', '')),
            ('original_reference', source.get('original_bibliography_sha256', '')),
            ('source_index', str(source.get('index', ''))),
            ('locators', tuple(a['url']for a in anchors)),
        )
        if key in self.article_cache:return self.article_cache[key]
        self.article_cache[key]=None
        if not identifiers and locator_enabled:
            if len(anchors) != 1:
                return None
            from .original_reference import extract_locator_pdf, extract_locator_document
            raw = self.read_bytes(anchors[0]['url'], limit=8_000_000)
            text = (extract_locator_document if document_enabled else extract_locator_pdf)(raw, anchors[0])
        else:
            text=self._article(source)
        self.article_cache[key]=text
        return text

    def _article(self, source):
        record = self.record(source)
        if not record or not record.get('pmcid') or record.get('isOpenAccess') != 'Y':
            return None
        xml = self.read('https://www.ebi.ac.uk/europepmc/webservices/rest/' + record['pmcid'] + '/fullTextXML', service='europepmc')
        text = article_text(xml, record, pmid=source.get('pmid'), require_body=True,
                            include_graphic_refs=self.settings.get('citation.preserve_article_graphic_links') is True)
        return text[:500_000] if text else None

    def source_article(self, source):
        """Read a body from the paper's identifiers and authoritative links."""
        from urllib.parse import quote
        from .pmc_identity import publisher_article_ids, publisher_article_text

        known = identity_fields(source)
        if not known:
            return None
        record = None
        endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest"
        pmcid = known.get("pmcid")
        if not pmcid:
            try:
                record = self.record(source)
            except (OSError, ValueError, ET.ParseError):
                pass
            pmcid = (record or {}).get("pmcid")
        if pmcid:
            known.setdefault("pmcid", pmcid)
        if pmcid:
            url = f"{endpoint}/{pmcid}/fullTextXML"
            try:
                self.permit(engine="europepmc")
                xml = self.read(url, service="europepmc")
                text = article_text(xml, {**(record or {}), **known, "pmcid": pmcid},
                                    pmid=known.get("pmid"), require_body=True)
                if text:
                    return {"url": url, "body": text[:500_000], "status": "retrieved_full_text",
                            "pmcid": pmcid}
                self.events.append({"url": url, "status": "body_or_identity_unavailable"})
            except (OSError, ValueError, ET.ParseError):
                pass

        links = []
        if pmcid:
            links.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
        if known.get("doi"):
            links.append(f"https://doi.org/{quote(known['doi'], safe='/')}")
        for item in (record or {}).get("fullTextUrlList", {}).get("fullTextUrl", []):
            if item.get("documentStyle") == "html" and item.get("url"):
                links.append(item["url"])
        if known.get("pmid"):
            try:
                pubmed = self.read(f"https://pubmed.ncbi.nlm.nih.gov/{known['pmid']}/",
                                   service="pubmed")
                _, publishers = publisher_article_ids(pubmed)
                links.extend(publishers)
            except (OSError, ValueError, ET.ParseError):
                pass
        for url in dict.fromkeys(links):
            if not self.remaining or self.seconds_left <= 0:
                break
            try:
                page = self.read(url, request_seconds=9)
            except (OSError, ValueError, ET.ParseError):
                continue
            actual, _ = publisher_article_ids(page)
            common = known.keys() & actual.keys()
            if not common:
                self.events.append({"url": url, "status": "identity_unverified"})
                continue
            if any(known[key] != actual[key] for key in common):
                self.events.append({"url": url, "status": "identity_mismatch"})
                continue
            if text := publisher_article_text(page):
                return {"url": url, "body": text[:500_000], "status": "retrieved_publisher_text",
                        "pmcid": pmcid}
        return None

    def supplements(self, pmcid):
        """Read bounded primary supplementary files provided by Europe PMC."""
        from io import BytesIO
        from pathlib import PurePosixPath
        from zipfile import BadZipFile, ZipFile
        from .retrieval import html_text

        self.permit(engine="europepmc")
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
        try:
            raw = self.read_bytes(url, limit=5_000_000, service="europepmc")
            with ZipFile(BytesIO(raw)) as archive:
                total = 0
                for info in archive.infolist():
                    suffix = PurePosixPath(info.filename).suffix.casefold()
                    if suffix not in {".txt", ".csv", ".tsv", ".xml", ".html", ".pdf"}:
                        continue
                    if info.file_size > 3_000_000 or total + info.file_size > 8_000_000:
                        continue
                    total += info.file_size
                    body = archive.read(info)
                    if suffix == ".pdf":
                        from pymupdf import open as open_pdf
                        with open_pdf(stream=body, filetype="pdf") as pdf:
                            text = "\n\n".join(page.get_text() for page in pdf)
                    else:
                        text = body.decode("utf-8", errors="replace")
                        if suffix in {".xml", ".html"}:
                            text = html_text(text)
                    if text.strip():
                        yield f"{url}#{PurePosixPath(info.filename).name}", text[:150_000]
        except (OSError, ValueError, BadZipFile):
            return

    def web(self, query, domain='', url=''):
        """Search candidate primary documentation; origin is visible, not certified."""
        import json
        import os
        self.permit(engine='searxng')
        value = self.settings.get('search.engine.web.searxng.default_params.instance_url')
        if isinstance(value,dict):value = value.get('value')
        endpoint = value or os.environ.get('SEARXNG_URL', 'http://searxng:8080')
        if domain:
            host = urlsplit('https://' + domain).hostname
            if not host or host != domain or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in domain):
                return []
            query = 'site:' + domain + ' ' + query
        direct = []
        if url:
            host = (urlsplit(url).hostname or '').lower()
            if urlsplit(url).scheme in {'http','https'} and (not domain or host==domain or host.endswith('.'+domain)):
                try:
                    raw = self.read(url,limit=4_000_000)
                    if not raw.lstrip().startswith('%PDF'):
                        text = html_text(raw)
                        if text:
                            direct.append({'title':query,'link':url,'fetched_content':text[:100_000],
                                'content_type':'retrieved_web_document','authority_status':'Requested primary-document candidate; origin and text supplied for verification.'})
                except Exception:
                    pass
        if direct:return direct
        url = str(endpoint).rstrip('/') + '/search'
        params = {'q':query,'format':'json','categories':'general','count':2}
        try:
            raw = json.loads(self.read(url, params=params, internal=True))
            results = [{'title':r.get('title',''),'link':r.get('url',''),'snippet':r.get('content','')}
                       for r in raw.get('results',[])[:2]]
        except Exception:
            from bs4 import BeautifulSoup
            params['format'] = 'html'
            soup = BeautifulSoup(self.read(url, params=params, internal=True), 'html.parser')
            results = []
            for item in soup.select('article.result, .result-item')[:2]:
                link = item.select_one('h3 a, .result-title a')
                if link:
                    results.append({'title':link.get_text(' ',strip=True),'link':link.get('href',''),
                                    'snippet':item.get_text(' ',strip=True)})
        output = []
        for item in results[:2]:
            host = (urlsplit(item.get('link') or '').hostname or '').lower()
            if domain and not (host == domain.lower() or host.endswith('.' + domain.lower())):
                continue
            try:
                raw = self.read(item['link'], limit=4_000_000)
                if raw.lstrip().startswith('%PDF'):continue
                text = html_text(raw)
            except Exception:
                continue
            if text:
                output.append({**item, 'fetched_content':text[:100_000], 'content_type':'retrieved_web_document',
                    'authority_status':'Candidate primary documentation; verify the visible publisher and content, not the search rank.'})
        return output


def from_epmc(record):
    abstract = html_text(record.get('abstractText'))
    pmid = str(record.get('pmid') or (record.get('id') if record.get('source') == 'MED' else '') or '')
    source = {'pmid':pmid,'pmcid':record.get('pmcid',''),'doi':record.get('doi',''),
        'title':html_text(record.get('title','')), 'link':('https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/' if pmid else
            'https://europepmc.org/article/'+str(record.get('source',''))+'/'+str(record.get('id',''))),
        'journal':((record.get('journalInfo') or {}).get('journal') or {}).get('title',''),
        'pubdate':record.get('firstPublicationDate') or record.get('pubYear',''),
        'language':record.get('language') or record.get('languageOfFullText') or '',
        'abstract':abstract,'content':abstract,'full_content':abstract,
        'content_type':'abstract' if abstract else 'metadata',
        'publication_types':(record.get('pubTypeList') or {}).get('pubType',[]),
        'related_articles':epmc_relations(record)}
    source['snippet'] = academic_snippet(source, abstract)
    return source


def register_source(sources, source, register=None):
    ids = identity_fields(source)
    for existing in sources:
        old = identity_fields(existing)
        same_url = bool(source.get('link') and (existing.get('link') or '').rstrip('/') == source['link'].rstrip('/'))
        if (same_url or ids and any(old.get(k) == v for k,v in ids.items())) and not any(old[k] != ids[k] for k in old.keys() & ids.keys()):
            return existing
    index = register(source, 'evidence_supplement') if register else max([int(s['index']) for s in sources] + [0]) + 1
    for existing in sources:
        if int(existing['index']) == int(index):
            return existing
    record = {**source, 'index':str(index)}
    sources.append(record)
    return record


def resolve_source_identities(sources, fetcher, *, required_ids, trace=None):
    """Bridge cited PMC-only records using exact service metadata, not titles.

    Keep text snapshots and allocated source IDs. Lookup failure is non-fatal;
    the caller supplies an independent bounded network budget.
    """
    cache={}
    for source in sources:
        ids=identity_fields(source)
        if (int(source['index']) not in required_ids or not ids.get('pmcid')
            or ids.get('pmid') or ids.get('doi')):continue
        key=ids['pmcid']
        try:
            if key not in cache:
                cache[key]=None
                record=fetcher.record(source)
                found=identity_fields(from_epmc(record)) if record else {}
                if found and found.get('pmcid')!=key:
                    raise ValueError('Identifier bridge conflict')
                if not (found.get('pmid') or found.get('doi')) and hasattr(fetcher,'pmc_identifiers'):
                    mapped=fetcher.pmc_identifiers(key) or {}
                    if any(mapped[k]!=v for k,v in found.items() if k in mapped):
                        raise ValueError('Identifier bridge conflict')
                    found={**found,**mapped}
                cache[key]=found
            found=cache[key]
            if not found or not (found.get('pmid') or found.get('doi')):
                if trace:trace.record('source_identity_bridge',{'source_index':source['index'],'status':'no_alias'})
                continue
            if found.get('pmcid')!=key or any(found[k]!=v for k,v in ids.items() if k in found):
                raise ValueError('Identifier bridge conflict')
            source.update({k:v for k,v in found.items() if not source.get(k)})
            if trace:trace.record('source_identity_bridge',{'source_index':source['index'],
                'status':'resolved','identifiers':found})
        except Exception as exc:
            if trace:trace.record('source_identity_bridge',{'source_index':source['index'],
                'status':'unavailable','error_type':type(exc).__name__})
    for source,resolved in zip(sources,reconcile_identities(sources)):
        source.update({k:v for k,v in identity_fields(resolved).items() if not source.get(k)})


def resolve_versions(sources, fetcher, *, register=None, trace=None):
    for source in list(sources):
        if source.get('version_resolution'):
            continue
        for relation in source.get('related_articles') or []:
            if relation.get('relation_type') not in {'update_in', 'published_in'}:
                continue
            try:
                ids = identity_fields(relation)
                target = next((s for s in sources if s is not source
                    and any(identity_fields(s).get(k) == v for k,v in ids.items())
                    and not any(identity_fields(s)[k] != v for k,v in ids.items() if k in identity_fields(s))),None)
                if target is None:
                    record = fetcher.record(relation)
                    if record is None:
                        raise LookupError('Linked publication unavailable')
                    target = register_source(sources, from_epmc(record), register)
                if str(target['index']) == str(source['index']):
                    raise ValueError('Self-referencing publication update')
                source.setdefault('publication_versions', []).append({'relation_type':relation['relation_type'],
                    'index':target['index'],'doi':target.get('doi','')})
                source['version_resolution'] = 'Linked publication retrieved as a separate source; compare its text before citing it in place of this version.'
            except Exception as exc:
                source['version_resolution'] = 'Linked publication not retrieved (' + type(exc).__name__ + '); retain the original version and its evidence scope.'
            if trace:
                trace.record('publication_version', {'source_index':source.get('index'),
                    'relations':source.get('publication_versions', []),'status':source['version_resolution']})
