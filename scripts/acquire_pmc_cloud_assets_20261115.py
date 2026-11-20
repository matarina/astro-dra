"""Bounded source-bound official PMC cloud acquisition; no production caller."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def ids(raw):
    root = ET.fromstring(raw)
    meta = next(n for n in root.iter() if n.tag.rsplit('}', 1)[-1] == 'article-meta')
    found = {n.get('pub-id-type'): ''.join(n.itertext()).strip()
             for n in meta if n.tag.rsplit('}', 1)[-1] == 'article-id'}
    return dict(pmid=found['pmid'], pmcid=found.get('pmc') or found['pmcid'], doi=found['doi'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source-xml', type=Path)
    source.add_argument('--source-pack', type=Path)
    parser.add_argument('--source-id', type=int)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--figure-id', action='append', default=[])
    parser.add_argument('--include-pdf', action='store_true')
    args = parser.parse_args()
    raw_xml = args.source_xml.read_bytes() if args.source_xml else None
    input_path = args.source_xml or args.source_pack
    if raw_xml is not None:
        assert args.source_id is None
        own = ids(raw_xml)
    else:
        assert args.source_id is not None and args.source_id > 0
        assert not args.figure_id, 'Figure selection needs a previously acquired own XML'
        records = json.loads(args.source_pack.read_text())
        assert isinstance(records, list)
        def same_id(record):
            value = record.get('index')
            return ((type(value) is int and value == args.source_id) or
                    (type(value) is str and value == str(args.source_id)))
        record, = [r for r in records if same_id(r)]
        own = {key: str(record[key]).strip() for key in ['pmid', 'pmcid', 'doi']}
    assert own['pmid'].isdigit() and own['doi'].startswith('10.')
    assert own['pmcid'].startswith('PMC') and own['pmcid'][3:].isdigit()
    figures = {n.get('id'): n for n in ET.fromstring(raw_xml).iter('fig')} if raw_xml else {}
    wanted = []
    for figure_id in args.figure_id:
        node = figures[figure_id]
        wanted.extend(n.get('{http://www.w3.org/1999/xlink}href') for n in node.iter('graphic'))
    assert len(wanted) <= 6 and all(wanted)
    args.out_dir.mkdir(exist_ok=False)
    freeze = {str(p): digest(p.read_bytes()) for p in (input_path, Path(__file__))}
    write(args.out_dir / 'prestart-freeze.json', freeze)
    (args.out_dir / 'code').mkdir()
    (args.out_dir / 'code' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    base = 'https://pmc-oa-opendata.s3.amazonaws.com/'
    plan = dict(own_ids=own, input_path=str(input_path), source_id=args.source_id,
                input_scope='own_article_xml' if raw_xml is not None else 'frozen_source_pack_metadata',
                figure_ids=args.figure_id, graphic_hrefs=wanted,
                include_pdf=args.include_pdf, max_requests=10, timeout_seconds=25,
                max_asset_bytes=25_000_000, max_total_bytes=60_000_000,
                version_policy='require exactly one discovered version; otherwise stop without choosing',
                documentation='https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/', model_calls=0)
    write(args.out_dir / 'plan.json', plan)
    requests = []
    context = ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')

    def fetch(url, name, limit, expected_md5=None):
        assert len(requests) < 10
        assert sum(r.get('bytes', 0) for r in requests) + limit <= 60_000_000
        parsed = urllib.parse.urlsplit(url)
        assert parsed.scheme == 'https' and parsed.netloc == 'pmc-oa-opendata.s3.amazonaws.com'
        receipt = dict(url=url, limit=limit, expected_md5=expected_md5)
        requests.append(receipt)
        try:
            with urllib.request.urlopen(url, timeout=25, context=context) as response:
                assert urllib.parse.urlsplit(response.url).netloc == parsed.netloc
                raw = response.read(limit + 1)
                receipt.update(http_status=response.status, content_type=response.headers.get('Content-Type'),
                               bytes=len(raw), final_url=response.url)
            assert len(raw) <= limit
            receipt.update(sha256=digest(raw), md5=hashlib.md5(raw).hexdigest())
            (args.out_dir / name).write_bytes(raw)
            if expected_md5:
                assert receipt['md5'] == expected_md5
            return raw
        except urllib.error.HTTPError as exc:
            receipt['http_status'] = exc.code
            raise

    def locator(value, prefix):
        parsed = urllib.parse.urlsplit(value)
        assert parsed.scheme == 's3' and parsed.netloc == 'pmc-oa-opendata'
        key = parsed.path.lstrip('/')
        assert key.startswith(prefix) and '..' not in key.split('/')
        md5, = urllib.parse.parse_qs(parsed.query)['md5']
        assert len(md5) == 32 and all(c in '0123456789abcdef' for c in md5)
        return base + urllib.parse.quote(key, safe='/'), md5, Path(key).name

    result = {}
    try:
        query = urllib.parse.urlencode({'list-type': '2', 'prefix': own['pmcid'] + '.',
                                       'delimiter': '/', 'max-keys': '20'})
        listing = ET.fromstring(fetch(base + '?' + query, 'versions.xml', 1_000_000))
        ns = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
        assert listing.findtext('s:IsTruncated', namespaces=ns) == 'false'
        prefixes = [n.text for n in listing.findall('s:CommonPrefixes/s:Prefix', ns)]
        result['discovered_versions'] = prefixes
        assert len(prefixes) == 1, 'version selection requires explicit review'
        prefix = prefixes[0]
        metadata = json.loads(fetch(base + prefix + prefix.rstrip('/') + '.json', 'metadata.json', 1_000_000))
        assert str(metadata['pmcid']) == own['pmcid']
        assert str(metadata['pmid']) == own['pmid'] and metadata['doi'] == own['doi']
        url, md5, name = locator(metadata['xml_url'], prefix)
        cloud_xml = fetch(url, name, 5_000_000, md5)
        assert ids(cloud_xml) == own
        result['cloud_xml_byte_identical'] = cloud_xml == raw_xml if raw_xml is not None else None
        media = [locator(v, prefix) for v in metadata.get('media_urls', [])]
        selected = []
        for href in wanted:
            matches = [item for item in media if Path(item[2]).stem == Path(href).stem]
            assert len(matches) == 1, 'ambiguous or unavailable graphic'
            selected.extend(matches)
        if args.include_pdf:
            selected.append(locator(metadata['pdf_url'], prefix))
        assets = []
        for url, md5, name in dict.fromkeys(selected):
            raw = fetch(url, name, 25_000_000, md5)
            if name.lower().endswith('.pdf'):
                assert raw.startswith(b'%PDF-')
            assets.append(dict(name=name, bytes=len(raw), sha256=digest(raw), md5=md5))
        result.update(status='acquired_identity_bound_assets' if assets else 'acquired_identity_bound_xml', assets=assets)
    except Exception as exc:
        result.update(status='unavailable', error_type=type(exc).__name__, reason=str(exc)[:300])
    result.update(requests=requests, own_ids=own, model_calls=0, report_edits=0,
                  frozen_inputs_unchanged=all(digest(Path(p).read_bytes()) == h for p, h in freeze.items()),
                  semantic_verification=False, new_independent_correction_credit=0)
    write(args.out_dir / 'result.json', result)
    print(json.dumps(result))
    if result['status'] == 'unavailable':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
