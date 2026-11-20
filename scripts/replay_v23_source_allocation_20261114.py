"""Offline engineering replay of frozen formatter blocks and selector responses.

No model/network call or scientific adjudication. Original run files are read-only.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_verify import generation as g
from research_verify.citation_display import cited_indices
from research_verify.paragraph_bundle_candidate import build_request_bundle_context, bundle_writer_receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    def load(pattern):
        return json.loads(gzip.decompress(next(args.trace_dir.glob(pattern)).read_bytes()))
    original = load('*paragraph_bundle_writer_context*')
    views = load('*source_material_views*')['sources']
    sources = load('*input_sources*')['sources']
    old_material = load('*writer_sources*')['text']
    requests = [json.loads(gzip.decompress(p.read_bytes()))
                for p in sorted(args.trace_dir.glob('*source_selection_request*'))]
    responses = [json.loads(gzip.decompress(p.read_bytes()))['response']
                 for p in sorted(args.trace_dir.glob('*source_selection_result*'))]
    query = requests[0]['prompt'].split('Question: ', 1)[1].split('\nThese are candidate', 1)[0]
    docs = [SimpleNamespace(page_content=g.source_material(s)[0], metadata={'index': int(s['index'])})
            for s in sources]
    assert all(hashlib.sha256(d.page_content.encode()).hexdigest() ==
               next(v for v in views if v['index'] == d.metadata['index'])['available_sha256'] for d in docs)
    context, plan, planning = build_request_bundle_context(docs, query, context_chars=20000)
    assert json.loads(json.dumps(planning)) == original['planning']
    # Derive actual required IDs from frozen selection inputs, not feedback.
    optional = {i for request in requests for i in request['allowed_ids']}
    required = {v['index'] for v in views} - optional
    def frozen_blocks(_docs, _query, collector=None, **_kwargs):
        if collector is not None:
            collector.extend(views)
        return iter((v['index'], v['block']) for v in views)
    calls = []
    def selector(prompt):
        # Ensure replay batching/prompt is identical before substituting responses.
        assert prompt == requests[len(calls)]['prompt']
        calls.append(prompt)
        return responses[len(calls)-1]
    native, selection = [], []
    with patch.object(g, '_source_blocks', frozen_blocks):
        material = g.format_source_documents(
            docs, query, max_chars=60000, selector=selector, required_ids=required,
            reading_scope=[], candidate_passages=context,
            candidate_attachment_receipts=native, selection_receipts=selection)
    receipt = bundle_writer_receipt(plan, planning, material, list(material.views), native)
    assert len(material) <= 60000
    assert required <= set(material.views)
    rows = []
    for b in plan.selected:
        v = next(v for v in views if v['index'] == b.source.source_id)
        rows.append(dict(source_id=b.source.source_id, offsets=[b.start, b.end],
                         old_exact_block_present=v['block'] in old_material,
                         replay_exact_block_present=v['block'] in material))
    code_files = ['local_deep_research/research_verify/generation.py',
                  'local_deep_research/research_verify/paragraph_bundle_candidate.py',
                  'scripts/replay_v23_source_allocation_20261114.py']
    out = dict(scope='Offline frozen-block allocation replay only; no report/model run or quality score',
               original_attempt='matched-production-packet-immune-bundles-v23-20261114T130000Z',
               code_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in code_files},
               required_ids=sorted(required),selector_responses_reused=len(calls),
               old_material_chars=len(old_material), replay_material_chars=len(material),
               selected_bundle_source_blocks=rows, selection=selection, native=native,
               bundle_receipt=receipt,quality_claim=None)
    (args.out_dir/'allocation-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    (args.out_dir/'material.txt').write_text(str(material))
    print(json.dumps(dict(old_present=sum(r['old_exact_block_present'] for r in rows),
                         replay_present=sum(r['replay_exact_block_present'] for r in rows),
                         chars=len(material),required=len(required))))


if __name__ == '__main__':
    main()
