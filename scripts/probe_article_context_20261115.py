"""Frozen zero-network context attachment to actual prior Reader units."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research_verify.article_context import article_context_index, attach_article_context
from research_verify.source_explanations import explanation_prompt
from scripts.acquire_pmc_cloud_assets_20261115 import ids


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--article-xml', type=Path, action='append', required=True)
    args = parser.parse_args()
    root = Path('evaluation/frontier-strategy-20261113')
    prior = root / 'source-explanation-writer-pair-model-20261115-v2/attempt'
    casepath = root / 'immune-questioned-fact-inputs-20261115-v1/case-manifest.json'
    case = json.loads(casepath.read_text())['cases'][0]
    pack = Path(case['source'])
    assert sha(pack) == case['source_sha256']
    assert hashlib.sha256(case['query'].encode()).hexdigest() == case['query_sha256']
    records = json.loads(pack.read_text())
    units = json.loads((prior / 'source-units.json').read_text())
    assert explanation_prompt(case['query'], units) == (prior / 'reader-prompt.txt').read_text()
    files = [casepath, pack, prior / 'source-units.json', prior / 'reader-prompt.txt',
             Path(__file__), Path('scripts/acquire_pmc_cloud_assets_20261115.py'),
             *args.article_xml, *Path('local_deep_research/research_verify').glob('*.py')]
    args.out_dir.mkdir(exist_ok=False)
    frozen = {str(p): sha(p) for p in files}
    write(args.out_dir / 'prestart-freeze.json', frozen)
    for p in files:
        if str(p).startswith(('scripts/', 'local_deep_research/')):
            target = args.out_dir / 'code' / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    indexes, bindings = {}, []
    for p in args.article_xml:
        own = ids(p.read_bytes())
        record, = [r for r in records if all(str(r.get(k, '')) == v for k, v in own.items())]
        sid = int(record['index'])
        assert sid not in indexes, 'More than one supplied XML for source; do not choose silently'
        index = article_context_index(p.read_bytes(), record, record['pmid'])
        assert index is not None
        indexes[sid] = index
        bindings.append(dict(source_id=sid, xml_path=str(p), xml_sha256=sha(p), own_ids=own))
    enriched = attach_article_context(units, indexes)
    assert len(enriched) == len(units)
    assert all({k:v for k,v in row.items() if k != 'original_context'} == old for row, old in zip(enriched, units))
    prompt = explanation_prompt(case['query'], enriched)
    delimiter = '\nORIGINAL SOURCE UNITS:\n'
    assert prompt.split(delimiter)[0] == (prior / 'reader-prompt.txt').read_text().split(delimiter)[0]
    write(args.out_dir / 'article-indexes.json', indexes)
    write(args.out_dir / 'xml-bindings.json', bindings)
    write(args.out_dir / 'source-units-context.json', enriched)
    (args.out_dir / 'reader-prompt.txt').write_text(prompt)
    (args.out_dir / 'original-question.txt').write_text(case['query'])
    result = dict(status='completed_original_context_transport_not_semantic_assessment',
                  original_units=len(units), original_sources=len({u['source_id'] for u in units}),
                  own_xml_documents=len(indexes), all_original_fields_unchanged=True,
                  context_status_counts=dict(Counter(r['original_context']['status'] for r in enriched)),
                  old_prompt_chars=len((prior / 'reader-prompt.txt').read_text()), new_prompt_chars=len(prompt),
                  source_binding=bindings, network_requests=0, model_calls=0, report_edits=0,
                  frozen_inputs_unchanged=all(sha(Path(p)) == h for p,h in frozen.items()),
                  semantic_assessment=False, new_independent_correction_credit=0)
    write(args.out_dir / 'result.json', result)
    manifest = {str(p.relative_to(args.out_dir)): sha(p) for p in sorted(args.out_dir.rglob('*')) if p.is_file()}
    write(args.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(args.out_dir / p) == h for p,h in manifest.items())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
