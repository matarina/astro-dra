"""Offline known-task view audit and exact default-prompt compatibility check."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import research_verify.evidence_flow as flow
from research_verify.generation import SourceMaterial
from research_verify.material_exposure import capture_writer_exposure, review_exposure_context


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')


def extracted_review_material(prompt, expected_ids):
    raw = prompt.split('SUPPLIED SOURCES:\n', 1)[1].split('\n\nSTRUCTURAL REPORT SPANS', 1)[0]
    views = {}
    for m in re.finditer(r'^\[(\d+)\]\nTitle:.*?\nBEGIN SOURCE TEXT\n(.*?)\nEND SOURCE TEXT', raw, re.S | re.M):
        sid, text = int(m[1]), m[2]
        assert sid not in views
        # The serialized historical prompt is authoritative for its bytes.
        # Acquired/source scope is NOT reconstructed from an excerpt's size.
        views[sid] = dict(index=sid, text=text, block=m[0], model_view_chars=len(text),
                          model_view_sha256=digest(text), available_chars=None,
                          available_sha256=None, view_kind='historical_prompt_extracted',
                          scope='historical review bytes; acquisition completeness unconfirmed')
    assert set(views) == set(expected_ids)
    return SourceMaterial(raw, views)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    root = Path('evaluation/frontier-strategy-20261113')
    cases = {'immune': root / 'section-native-model-20261115-v1/attempt/section/trace.jsonl',
             'xenium': root / 'questioned-fact-document-model-20261115-v1/attempt/fact_document/trace.jsonl'}
    frozen_file = root / 'section-native-model-20261115-v1/attempt/code/local_deep_research/research_verify/evidence_flow.py'
    files = [Path(__file__), *cases.values(), frozen_file,
             Path('local_deep_research/tests/test_material_exposure.py'),
             *Path('local_deep_research/research_verify').glob('*.py')]
    frozen = {str(f): sha(f) for f in files}
    write(a.out_dir / 'prestart-freeze.json', frozen)
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            target = a.out_dir / 'code' / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    tree = ast.parse(frozen_file.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'review_prompt')
    ns = dict(json=json, IDENTITY_ATTRIBUTE_INSTRUCTIONS=flow.IDENTITY_ATTRIBUTE_INSTRUCTIONS,
              literal_assertion_spans=flow.literal_assertion_spans)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(frozen_file), 'exec'), ns)
    compatibility = []
    for identity in [False, True]:
        for budget in [None, 9000, 60000]:
            kwargs = dict(question='Original request', answer='Claim [9].', material='Source bytes.',
                          claims={0: dict(text='Claim [9].', source_ids=[9])},
                          structure_spans=[dict(kind='heading', text='# Study')],
                          prompt_budget=budget, identity_attributes=identity)
            assert flow.review_prompt(**kwargs) == ns['review_prompt'](**kwargs)
            compatibility.append(dict(identity_attributes=identity, budget=budget, exact=True))
    outcomes = {}
    for label, path in cases.items():
        events = [json.loads(line) for line in path.read_text().splitlines()]
        rows = next(e['data']['sources'] for e in events if e['stage'] == 'source_material_views')
        text = next(e['data']['text'] for e in events if e['stage'] == 'writer_sources')
        writer = SourceMaterial(text, {int(v['index']): v for v in rows})
        snapshot = capture_writer_exposure(writer)
        write(a.out_dir / (label + '-writer-snapshot.json'), snapshot)
        observations, contexts = [], []
        for event in events:
            if event['stage'] != 'native_check_request':
                continue
            data = event['data']
            reviewer = extracted_review_material(data['prompt'], data['source_ids'])
            context = review_exposure_context(snapshot, reviewer, data['source_ids'])
            contexts.append(dict(group=data['review_group'], round=data['round'], context=context,
                                 historical_prompt_sha256=digest(data['prompt'])))
            for sid, view in reviewer.views.items():
                old = writer.views.get(sid)
                observations.append(dict(group=data['review_group'], round=data['round'], source_id=sid,
                    writer_chars=len(old['text']) if old else None, reviewer_chars=len(view['text']),
                    same_text=old['text'] == view['text'] if old else None,
                    reviewer_shorter=len(view['text']) < len(old['text']) if old else None,
                    writer_sha256=old['model_view_sha256'] if old else None,
                    reviewer_sha256=view['model_view_sha256']))
        write(a.out_dir / (label + '-exposure-contexts.json'), contexts)
        write(a.out_dir / (label + '-view-pairs.json'), observations)
        outcomes[label] = dict(writer_sources=len(writer.views), native_requests=len(contexts),
                               view_pairs=len(observations), pair_byte_states=dict(Counter(
                                   'not_in_writer_batch' if row['writer_chars'] is None else
                                   'same' if row['same_text'] else 'shorter' if row['reviewer_shorter'] else 'different'
                                   for row in observations)),
                               context_budget_unavailable=sum('exposure_context_unavailable_budget' in c['context'] for c in contexts))
    assert all(sha(Path(f)) == h for f, h in frozen.items())
    receipt = dict(scope='Offline view-byte audit across TWO KNOWN tasks; not unseen generalization, semantic coverage or quality scoring',
                   cases=outcomes, default_prompt_compatibility=compatibility,
                   real_model_calls=0, network_reads=0, frozen_inputs_unchanged=True,
                   new_independent_correction_credit=0,
                   limit='Historical reviewer registries reconstructed from exact serialized prompt blocks, '
                         'with acquisition scope explicitly unknown. Pair counts are source-view exposures, '
                         'not scientific claims, omitted useful fields, errors or corrections.')
    write(a.out_dir / 'receipt.json', receipt)
    payloads = {str(f.relative_to(a.out_dir)): sha(f) for f in a.out_dir.rglob('*') if f.is_file()}
    write(a.out_dir / 'MANIFEST.json', payloads)
    assert all(sha(a.out_dir / f) == h for f, h in payloads.items())
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
