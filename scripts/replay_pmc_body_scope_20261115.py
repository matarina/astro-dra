"""Offline actual-XML replay of body availability and full-text preservation."""
import argparse
import hashlib
import json
from pathlib import Path
from types import ModuleType
import xml.etree.ElementTree as ET
from research_verify.pmc_identity import article_text


BASE = Path('evaluation/frontier-strategy-20261113')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(exist_ok=False)
    oldpath = BASE / 'xenium22-ncbi-pmc-live-20261115-v1/attempt/code/local_deep_research/research_verify/pmc_identity.py'
    legacy = ModuleType('research_verify._pmc_scope_snapshot')
    legacy.__package__ = 'research_verify'
    exec(compile(oldpath.read_text(), str(oldpath), 'exec'), legacy.__dict__)
    cases = [
        ('xenium-source1', 'report-01', '1', 'fragment-retention-source1-live-20261114-v1/acquisition/response-01.bin'),
        ('adipose-source2', 'report-04', '2', 'adipose-revision-primary-live-20261114-v1/acquisition/response-01.bin'),
        ('xenium-source22-embargo', 'report-01', '22', 'xenium22-ncbi-pmc-live-20261115-v1/attempt/response.bin'),
    ]
    results = []
    for name, report, sid, response in cases:
        pack = BASE / 'archive-pii-metadata-overlays-20261115-v1' / report / 'sources.json'
        source = next(s for s in json.loads(pack.read_text()) if s['index'] == sid)
        xmlpath = BASE / response
        raw = xmlpath.read_bytes()
        root = ET.fromstring(raw)
        article = root if root.tag == 'article' else root.find('./article')
        xml = ET.tostring(article, encoding='unicode')
        record = source | ({'pmcid': 'PMC12912775'} if sid == '22' else {})
        before = legacy.article_text(xml, record, source.get('pmid'))
        default = article_text(xml, record, source.get('pmid'))
        strict = article_text(xml, record, source.get('pmid'), require_body=True)
        assert default == before
        has_body = article.find('./body') is not None
        if has_body:
            assert strict == before == source['fetched_content']
            (args.out_dir / (name + '-text.txt')).write_text(strict)
        else:
            assert before and strict is None and not source.get('fetched_content')
        results.append(dict(case=name, xml_path=str(xmlpath), xml_sha256=digest(raw),
                            sourcepack_path=str(pack), sourcepack_sha256=digest(pack.read_bytes()),
                            body_present=has_body, legacy_chars=len(before or ''),
                            strict_chars=len(strict or ''), default_bytes_unchanged=default == before,
                            existing_fetched_body_unchanged=strict == source.get('fetched_content') if has_body else None,
                            legacy_text_sha256=digest(before.encode()) if before else None,
                            strict_text_sha256=digest(strict.encode()) if strict else None))
    receipt = dict(scope='Actual raw acquisition replay only; no semantic/generalization or historical incident claim',
                   legacy_parser_path=str(oldpath), legacy_parser_sha256=digest(oldpath.read_bytes()),
                   cases=results, model_calls=0, network_reads=0, report_modifications=0,
                   new_independently_credited_corrections=0)
    (args.out_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
