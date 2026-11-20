"""RETIRED diagnostic: OA Web Service removed August 2026; use acquire_pmc_cloud_assets_20261115.py."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import ssl
import tarfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def ids(raw):
    root = ET.fromstring(raw)
    local = lambda node: node.tag.rsplit('}', 1)[-1]
    meta = next(node for node in root.iter() if local(node) == 'article-meta')
    found = {node.get('pub-id-type'): ''.join(node.itertext()).strip()
             for node in meta if local(node) == 'article-id'}
    return dict(pmid=found['pmid'], pmcid=found.get('pmc') or found['pmcid'], doi=found['doi'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-xml', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    parser.error("Retired OA Web Service; use acquire_pmc_cloud_assets_20261115.py instead")
    args.out_dir.mkdir(exist_ok=False)
    own = ids(args.source_xml.read_bytes())
    assert own['pmcid'].startswith('PMC') and own['pmcid'][3:].isdigit()
    files = [args.source_xml, Path(__file__)]
    freeze = {str(path): sha(path) for path in files}
    write(args.out_dir / 'prestart-freeze.json', freeze)
    (args.out_dir / 'code').mkdir()
    (args.out_dir / 'code' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    endpoint = 'https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=' + own['pmcid']
    write(args.out_dir / 'plan.json', dict(own_ids=own, endpoint=endpoint,
        maximum_network_requests=2, metadata_limit=1_000_000, package_limit=25_000_000,
        uncompressed_limit=75_000_000, timeout_seconds=25,
        model_calls=0, source_pack_changes=False, production_changes=False))
    requests = []
    context = ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    def fetch(url, limit, name):
        receipt = dict(url=url, limit=limit)
        requests.append(receipt)
        with urllib.request.urlopen(url, timeout=25, context=context) as response:
            raw = response.read(limit + 1)
            receipt.update(http_status=response.status, final_url=response.url,
                           content_type=response.headers.get('Content-Type'), bytes=len(raw))
        assert len(raw) <= limit
        path = args.out_dir / name
        path.write_bytes(raw)
        receipt['sha256'] = sha(path)
        return raw
    result = {}
    try:
        raw = fetch(endpoint, 1_000_000, 'oa-metadata.xml')
        record, = [node for node in ET.fromstring(raw).iter('record') if node.get('id') == own['pmcid']]
        link, = [node for node in record.iter('link') if node.get('format') == 'tgz']
        locator = urllib.parse.urlsplit(link.get('href'))
        assert locator.scheme in {'ftp', 'https'} and locator.hostname == 'ftp.ncbi.nlm.nih.gov'
        url = urllib.parse.urlunsplit(('https', locator.netloc, locator.path, locator.query, ''))
        package = fetch(url, 25_000_000, 'package.tar.gz')
        with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
            members = archive.getmembers()
            assert sum(member.size for member in members if member.isfile()) <= 75_000_000
            bound_xml = []
            for member in members:
                if member.isfile() and member.name.lower().endswith(('.xml', '.nxml')):
                    item = archive.extractfile(member).read()
                    try:
                        if ids(item) == own:
                            bound_xml.append(member.name)
                    except (ValueError, KeyError, StopIteration, ET.ParseError):
                        pass
            assert len(bound_xml) == 1
            assets = []
            folder = args.out_dir / 'assets'
            folder.mkdir()
            for member in members:
                if not member.isfile() or not member.name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff')):
                    continue
                original = PurePosixPath(member.name)
                assert not original.is_absolute() and '..' not in original.parts
                target = folder / original.name
                assert not target.exists()
                target.write_bytes(archive.extractfile(member).read())
                assets.append(dict(package_path=member.name, path=str(target), bytes=target.stat().st_size, sha256=sha(target)))
            result.update(status='acquired_identity_bound_package', bound_xml=bound_xml, assets=assets)
    except Exception as exc:
        result.update(status='unavailable', error_type=type(exc).__name__)
    result.update(requests=requests, own_ids=own, model_calls=0, report_edits=0,
        frozen_inputs_unchanged=all(sha(Path(path)) == value for path, value in freeze.items()),
        semantic_verification=False, new_independent_correction_credit=0)
    write(args.out_dir / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'assets'}))
    if result['status'] == 'unavailable':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
