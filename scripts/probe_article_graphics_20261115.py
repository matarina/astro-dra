"""Frozen offline JATS figure-link contrast; no model, image fetch or scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from research_verify.pmc_identity import article_graphics, article_text
from research_verify.evidence_fetch import EvidenceFetcher


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xml', type=Path, action='append', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(exist_ok=False)
    inputs = [*args.xml, Path(__file__), *Path('local_deep_research/research_verify').glob('*.py')]
    frozen = {str(path): sha(path) for path in inputs}
    write(args.out_dir / 'prestart-freeze.json', frozen)
    for path in inputs:
        target = args.out_dir / 'code' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    results = []
    for index, path in enumerate(args.xml):
        xml = path.read_text()
        root = ET.fromstring(xml)
        local = lambda node: node.tag.rsplit('}', 1)[-1]
        meta = next(node for node in root.iter() if local(node) == 'article-meta')
        ids = {node.get('pub-id-type'): ''.join(node.itertext()).strip() for node in meta if local(node) == 'article-id'}
        pmcid = ids.get('pmc') or ids.get('pmcid')
        assert pmcid and ids.get('pmid') and ids.get('doi')
        record = dict(pmcid=pmcid, doi=ids['doi'], isOpenAccess='Y')
        base = article_text(xml, record, ids['pmid'], require_body=True)
        enhanced = article_text(xml, record, ids['pmid'], require_body=True, include_graphic_refs=True)
        assert base and enhanced
        assert all(part in enhanced for part in base.split('\n\n'))
        graphics = article_graphics(xml, record, ids['pmid'])
        assert graphics is not None
        calls = []
        fetcher = EvidenceFetcher({'citation.preserve_article_graphic_links': True})
        fetcher.record = lambda _: record
        def read(url, **kwargs):
            calls.append(url)
            return xml
        fetcher.read = read
        fetched = fetcher.article(dict(pmid=ids['pmid'], pmcid=pmcid))
        assert fetched == enhanced and len(calls) == 1
        folder = args.out_dir / f'article-{index:02d}'
        folder.mkdir()
        (folder / 'baseline.txt').write_text(base)
        (folder / 'with-graphic-links.txt').write_text(enhanced)
        write(folder / 'graphic-manifest.json', graphics)
        results.append(dict(input=str(path), xml_sha256=sha(path), own_ids=ids,
            baseline_chars=len(base), with_graphics_chars=len(enhanced),
            figures=len(graphics['figures']), unresolved_refs=len(graphics['unresolved_references']),
            explicit_figure_reference_links=sum(len(f['references']) for f in graphics['figures']),
            actual_fetcher_result_equal=True, source_text_paragraphs_preserved=True,
            offline_xml_reads=len(calls), image_reads=0, visual_content_transcribed=False))
    write(args.out_dir / 'result.json', dict(status='offline_transport_verified', results=results,
        model_calls=0, network_requests=0, report_edits=0,
        frozen_inputs_unchanged=all(sha(Path(p)) == value for p, value in frozen.items()),
        new_independent_correction_credit=0, limits='Known acquired sources, not held-out tasks. Figure locators and captions remain uninspected evidence; no image-reading capability or semantic correction is established.'))
    files = [path for path in args.out_dir.rglob('*') if path.is_file()]
    manifest = {str(path): sha(path) for path in files}
    write(args.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(p)) == value for p, value in manifest.items())
    print(json.dumps(dict(results=results, payloads=len(manifest), manifest_sha256=sha(args.out_dir / 'MANIFEST.json'))))


if __name__ == '__main__':
    main()
