"""Fault injection at the diagnostic cloud helper's scientific identity boundary."""
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.parse
import xml.etree.ElementTree as ET

import pytest

from scripts import acquire_pmc_cloud_assets_20261115 as acquire


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'evaluation/frontier-strategy-20261113/wemp-primary-cloud-acquisition-20261115-v1'
SOURCE = ROOT / 'evaluation/frontier-strategy-20261113/immune-evidence/PMC6183502.xml'


class Response(io.BytesIO):
    status = 200
    headers = {'Content-Type': 'binary/octet-stream'}

    def __init__(self, raw, url):
        super().__init__(raw)
        self.url = url


@pytest.mark.parametrize('fault,requests', [
    ('wrong_metadata_identity', 2),
    ('wrong_xml_identity_with_matching_checksum', 3),
    ('damaged_xml_checksum', 3),
    ('multiple_versions', 1),
])
def test_untrusted_cloud_responses_never_become_accepted_article(tmp_path, monkeypatch, fault, requests):
    listing = (FIXTURE / 'versions.xml').read_bytes()
    metadata = json.loads((FIXTURE / 'metadata.json').read_text())
    xml = (FIXTURE / 'PMC6183502.1.xml').read_bytes()
    if fault == 'wrong_metadata_identity':
        metadata['doi'] = '10.1234/another-article'
    elif fault == 'wrong_xml_identity_with_matching_checksum':
        tree = ET.fromstring(xml)
        own = tree.find('.//article-meta/article-id[@pub-id-type="doi"]')
        assert own is not None
        own.text = '10.1234/another-article'
        xml = ET.tostring(tree)
        parts = urllib.parse.urlsplit(metadata['xml_url'])
        metadata['xml_url'] = urllib.parse.urlunsplit(parts._replace(
            query='md5=' + hashlib.md5(xml).hexdigest()))
    elif fault == 'damaged_xml_checksum':
        xml += b'\n'
    else:
        tree = ET.fromstring(listing)
        ns = '{http://s3.amazonaws.com/doc/2006-03-01/}'
        extra = ET.SubElement(tree, ns + 'CommonPrefixes')
        ET.SubElement(extra, ns + 'Prefix').text = 'PMC6183502.2/'
        listing = ET.tostring(tree)
    seen = []

    def fetch(url, **kwargs):
        seen.append(url)
        if '?list-type=' in url:
            raw = listing
        elif url.endswith('.json'):
            raw = json.dumps(metadata).encode()
        elif url.endswith('.xml'):
            raw = xml
        else:
            pytest.fail('An unbound asset was requested')
        return Response(raw, url)

    out = tmp_path / 'attempt'
    monkeypatch.setattr(acquire.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(sys, 'argv', ['acquire', '--source-xml', str(SOURCE), '--out-dir', str(out)])
    with pytest.raises(SystemExit) as exc:
        acquire.main()
    assert exc.value.code == 2
    result = json.loads((out / 'result.json').read_text())
    assert result['status'] == 'unavailable' and 'assets' not in result
    assert len(seen) == requests
    assert result['model_calls'] == result['report_edits'] == 0


def test_duplicate_source_namespace_stops_before_network_or_attempt(tmp_path, monkeypatch):
    record = dict(index='11', pmcid='PMC10195816', pmid='37202383', doi='10.1038/s41467-023-38356-1')
    pack = tmp_path / 'sources.json'
    pack.write_text(json.dumps([record, {**record, 'index': 11}]))
    out = tmp_path / 'attempt'
    monkeypatch.setattr(acquire.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Unexpected network request'))
    monkeypatch.setattr(sys, 'argv', ['acquire', '--source-pack', str(pack), '--source-id', '11', '--out-dir', str(out)])
    with pytest.raises(ValueError):
        acquire.main()
    assert not out.exists()
