"""Audit isolated discovery pipeline and literal native quote provenance."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.audit_material_exposure_20261115 import extracted_review_material
from scripts.prepare_source_detail_material_20261114 import native_documents


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['attempt', 'default-replay', 'baseline', 'probe', 'probe-audit', 'out-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    for root in [a.attempt, a.default_replay]:
        frozen = read(root / 'prestart-freeze.json')
        for filename, expected in frozen.items():
            actual = root / 'code' / filename if filename.startswith(('scripts/', 'local_deep_research/')) else Path(filename)
            assert sha(actual) == expected
        completion = read(root / 'completion.json')
        assert completion['frozen_inputs_unchanged']
        assert completion['fresh_model_calls'] == completion['retrieval_network_reads'] == completion['unavailable_calls'] == 0
        for c in read(root / 'calls.json'):
            assert c['status'] == 'returned'
            pp, rp = [root / f"call-{c['index']:02d}-{kind}.txt" for kind in ['prompt', 'response']]
            assert sha(pp) == c['prompt_sha256'] and sha(rp) == c['response_sha256']
            if c.get('cached_from'):
                assert rp.read_bytes() == Path(c['cached_from']).read_bytes()
    assert read(a.default_replay / 'completion.json')['replay_exact']
    original_calls, replay_calls = [read(root / 'calls.json') for root in [a.baseline, a.default_replay]]
    assert len(original_calls) == len(replay_calls) == 32
    for old, new in zip(original_calls, replay_calls):
        assert (old['arm'], old['stage'], old['prompt_sha256'], old['response_sha256'], old['response_metadata']) == (new['arm'], new['stage'], new['prompt_sha256'], new['response_sha256'], new['response_metadata'])
    for arm in ['flat', 'section']:
        assert read(a.baseline / arm / 'result.json') == read(a.default_replay / arm / 'result.json')
    old = read(a.baseline / 'section/result.json')
    new = read(a.attempt / 'section/result.json')
    assert (a.baseline / 'section/report.txt').read_bytes() == (a.attempt / 'section/report.txt').read_bytes()
    assert not new['native_review']['parts'][0]['applied']
    events = [json.loads(line) for line in (a.attempt / 'section/trace.jsonl').read_text().splitlines()]
    requests = [e['data'] for e in events if e['stage'] == 'native_check_request']
    for req in requests:
        if req['review_group'] in [8, 9]:
            assert req['round'] == 1 and len(req['prompt']) <= 60000
            assert req['source_ids'] == list(range(1, 21))
    receipt_by_hash = {e['data'].get('material_sha256'): e['data'] for e in events if e['stage'] == 'uncited_source_discovery'}
    source_docs = {int(d.metadata['index']): d for d in native_documents(new['sources'])}
    observations = []
    for pair in read(a.probe / 'plan.json')['pairs']:
        folder = a.probe / pair['key']
        prompt = (folder / 'prompt.txt').read_text()
        req, = [r for r in requests if r['prompt'] == prompt]
        assert len(req['source_ids']) == 20
        material = prompt.split('SUPPLIED SOURCES:\n', 1)[1].split('\n\nUNASSIGNED SOURCE DISCOVERY', 1)[0]
        receipt = receipt_by_hash[hashlib.sha256(material.encode()).hexdigest()]
        assert receipt['claim_source_ids_modified'] is False
        for window in receipt['windows']:
            text = source_docs[window['source_id']].page_content[window['start']:window['end']]
            assert hashlib.sha256(text.encode()).hexdigest() == window['text_sha256'] and text in material
        views = extracted_review_material(prompt, req['source_ids']).views
        for sid, doc in source_docs.items():
            abstract = doc.metadata.get('abstract')
            if isinstance(abstract, str) and abstract:
                assert abstract in views[sid]['text']
        result = read(folder / 'result.json')
        for entry in result['native_checked'] + result['native_issues']:
            # Explicit outer source/quote pairs only. Do not guess which paper
            # an atom's unbound quotation belongs to or call paraphrase a lie.
            for pair_quote in entry.get('evidence_sources', []):
                sid, quote = pair_quote['source_id'], pair_quote['quote']
                if not quote:
                    continue
                observations.append(dict(group=req['review_group'], claim_id=entry.get('claim_id'),
                    native_status=entry.get('status'), source_id=sid, quote=quote,
                    exact_in_actual_source_block=sid in views and quote in views[sid]['block'],
                    exact_in_full_acquired_text=sid in source_docs and quote in source_docs[sid].page_content,
                    semantic_support='not_assessed'))
    manifest = read(a.probe_audit / 'MANIFEST.json')
    assert all(sha(Path(f)) == h for f, h in manifest.items())
    write(a.out_dir / 'literal-native-quote-provenance.json', observations)
    part = new['native_review']['parts'][0]
    issue66, = [x for x in part['unresolved'] if x.get('claim_id') == 66]
    assert issue66['source_id'] == 12 and issue66['request']['kind'] == 'web'
    write(a.out_dir / 'findings.json', dict(status='engineering_audit_passed',
        report_changed=False, report_chars=new['report_chars'], report_sha256=new['report_sha256'],
        original_pending_claim_ids=[x.get('claim_id') for x in old['native_review']['parts'][0]['unresolved']],
        current_pending_claim_ids=[x.get('claim_id') for x in part['unresolved']],
        native_status=new['native_review']['status'], applied_repairs=0,
        pipeline_logical_calls=32, pipeline_fresh_calls=0, previous_probe_fresh_calls=2,
        fallback_request_fix=dict(claim_id=66, retained_evidence_source=12, missing_evidence_request='web',
                                  reason='No original explicit citation; support provenance is not a missing-clause fetch target.'),
        remaining_fixed_source_unavailable_events=len(new['supplement_requests']),
        limits=['Two changed native checks on one KNOWN task; no new-task generalization.',
                'The report is unchanged, with no independently credited correction or useful retention/new-error clearance.',
                'Fewer native pending IDs do not measure correction; new gaps and changed model judgements coexist.',
                'Literal quote mismatch may be formatting/paraphrase, omitted context or wrong attribution; no automatic semantic verdict.',
                'The original naked list marker 5. still reaches native review; no scientific deletion added.',
                'Mixed final summary group11 cannot fit the full discovery abstract inventory; explicitly unavailable.',
                'Current parser/budget fixes postdate the live-stage freeze; complete pipeline has its own new freeze.',
                'Unchanged historical cited-only over-budget prompts remain a separate issue.'],
        new_independent_correction_credit=0))
    (a.out_dir / 'audit-script.py').write_bytes(Path(__file__).read_bytes())
    files = [f for root in [a.attempt, a.default_replay, a.out_dir] for f in root.rglob('*') if f.is_file()]
    files += [a.probe_audit / 'MANIFEST.json', a.probe_audit / 'completion.json']
    payload = {str(f): sha(f) for f in sorted(set(files))}
    write(a.out_dir / 'MANIFEST.json', payload)
    assert all(sha(Path(f)) == h for f, h in payload.items())
    write(a.out_dir / 'completion.json', dict(status='passed', payloads=len(payload),
        manifest_sha256=sha(a.out_dir / 'MANIFEST.json'), fresh_model_calls=0,
        new_independent_correction_credit=0))
    print((a.out_dir / 'completion.json').read_text())


if __name__ == '__main__':
    main()
