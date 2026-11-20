"""One official PMC read bound to the requested article's own PubMed IDs.

Standalone acquisition experiment; no production fallback or semantic acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.pmc_identity import article_text
from research_verify.source_identity import identity_fields
from scripts.experiment_error_receipt import error_receipt


def bound_record(raw, source):
    expected = identity_fields(source)
    if not expected.get('pmid') or not expected.get('doi'):
        raise ValueError('Requested PMID and DOI required')
    records = []
    for node in ET.fromstring(raw).findall('./PubmedArticle'):
        if node.findtext('./MedlineCitation/PMID') != expected['pmid']:
            continue
        own = node.findall('./PubmedData/ArticleIdList/ArticleId')
        def unique(kind):
            values = {x.text.strip() for x in own if x.get('IdType') == kind and x.text}
            if len(values) != 1:
                raise ValueError('Missing or conflicting own ' + kind)
            return next(iter(values))
        record = identity_fields(dict(pmid=unique('pubmed'), doi=unique('doi'), pmcid=unique('pmc')))
        if not re.fullmatch(r'PMC\d+', record.get('pmcid', '')):
            raise ValueError('Invalid PMC identifier')
        if any(record.get(k) != v for k, v in expected.items()):
            raise ValueError('Source and own PubMed identity conflict')
        records.append(record)
    if len(records) != 1:
        raise ValueError('Exactly one own PubMed record required')
    return records[0]


def bound_body(raw, expected):
    root = ET.fromstring(raw)
    articles = [root] if root.tag == 'article' else root.findall('./article')
    if len(articles) != 1:
        raise ValueError('Exactly one PMC article required')
    article = articles[0]
    own = article.findall('./front/article-meta/article-id')
    found = {}
    for kind, key in [('pmid', 'pmid'), ('pmcid', 'pmcid'), ('doi', 'doi')]:
        kinds = {'pmc', 'pmcid'} if kind == 'pmcid' else {kind}
        values = {''.join(x.itertext()).strip() for x in own if x.get('pub-id-type') in kinds}
        if len(values) != 1:
            raise ValueError('Missing or conflicting own PMC ' + kind)
        value = next(iter(values))
        found[key] = ('PMC' + value.removeprefix('PMC')) if kind == 'pmcid' else value
    if identity_fields(found) != expected:
        raise ValueError('PMC response identity mismatch')
    if article.find('./body') is None:
        raise ValueError('PMC response has no article body')
    text = article_text(ET.tostring(article, encoding='unicode'), expected, expected['pmid'], require_body=True)
    if not text:
        raise ValueError('No parsed article text')
    return text


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--source-id', required=True)
    p.add_argument('--pubmed-xml', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    source = next(s for s in json.loads(a.sources.read_text()) if str(s['index']) == a.source_id)
    record = bound_record(a.pubmed_xml.read_bytes(), source)
    files = [a.sources, a.pubmed_xml, Path(__file__), Path('scripts/experiment_error_receipt.py'),
             *Path('local_deep_research/research_verify').glob('*.py')]
    freeze = {str(f): sha(f) for f in files}
    (a.out_dir / 'prestart-freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            dest = a.out_dir / 'code' / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    plan = dict(source_id=a.source_id, expected_ids=record, maximum_reads=1,
                url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
                params=dict(db='pmc', id=record['pmcid'].removeprefix('PMC'), retmode='xml'),
                scope='Public official PMC API; no login/access bypass, model, report edits or quality acceptance')
    (a.out_dir / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not a.execute:
        print(json.dumps(plan))
        return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    defaults = json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    settings = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()})
    fetch = EvidenceFetcher(settings, seconds=15, requests=1)
    receipt = dict(plan, status='unavailable', model_calls=0, report_modifications=0,
                   newly_credited_corrections=0, quality_claim=None)
    try:
        fetch.permit(engine='pubmed')
        raw = fetch.read_bytes(plan['url'], params=plan['params'], service='pubmed')
        dest = a.out_dir / 'response.bin'
        dest.write_bytes(raw)
        receipt.update(response_bytes=len(raw), response_sha256=sha(dest))
        text = bound_body(raw, record)
        body = a.out_dir / 'source-text.txt'
        body.write_text(text)
        receipt.update(status='identity_bound_body_received', text_chars=len(text), text_sha256=sha(body))
    except Exception as exc:
        receipt['failure'] = error_receipt(exc)
    receipt.update(transport=fetch.events, frozen_inputs_unchanged=all(sha(Path(f)) == h for f, h in freeze.items()))
    (a.out_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
