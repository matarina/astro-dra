"""Audit offline full-pipeline quotation transport, without scientific scoring."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def trace(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['attempt', 'replay', 'default-replay', 'baseline', 'out-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    roots = [a.attempt, a.replay, a.default_replay]
    freezes = []
    for root in roots:
        frozen = read(root / 'prestart-freeze.json')
        for filename, expected in frozen.items():
            original = Path(filename)
            if filename.startswith(('scripts/', 'local_deep_research/')):
                # Later harness hardening is allowed; verify then-frozen copies.
                original = root / 'code' / filename
            assert sha(original) == expected, (root, original)
        completion = read(root / 'completion.json')
        assert completion['frozen_inputs_unchanged']
        assert completion['fresh_model_calls'] == completion['retrieval_network_reads'] == 0
        assert completion['new_independent_correction_credit'] == 0
        calls = read(root / 'calls.json')
        for c in calls:
            pp = root / f"call-{c['index']:02d}-prompt.txt"
            rp = root / f"call-{c['index']:02d}-response.txt"
            assert c['status'] == 'returned'
            assert sha(pp) == c['prompt_sha256'] and sha(rp) == c['response_sha256']
            if c.get('cached_from'):
                assert rp.read_bytes() == Path(c['cached_from']).read_bytes()
        freezes.append(dict(root=str(root), frozen_files=len(frozen), calls=len(calls)))
    assert read(a.replay / 'completion.json')['replay_exact'] is True
    assert read(a.default_replay / 'completion.json')['replay_exact'] is True
    # Independently compare all replayed request/reply bytes, rather than trusting flags.
    for replay, original in [(a.replay, a.attempt), (a.default_replay, a.baseline)]:
        rc, oc = read(replay / 'calls.json'), read(original / 'calls.json')
        assert len(rc) == len(oc)
        for r, o in zip(rc, oc):
            assert (r['arm'], r['stage'], r['response_metadata']) == (o['arm'], o['stage'], o['response_metadata'])
            for suffix in ['prompt', 'response']:
                assert (replay / f"call-{r['index']:02d}-{suffix}.txt").read_bytes() == (original / f"call-{o['index']:02d}-{suffix}.txt").read_bytes()
        for arm in ['flat', 'section']:
            assert read(replay / arm / 'result.json') == read(original / arm / 'result.json')
    old = read(a.baseline / 'section/result.json')
    new = read(a.attempt / 'section/result.json')
    assert new == old  # Full report, unresolved review and supplement outcome identical.
    assert (a.attempt / 'section/report.txt').read_bytes() == (a.baseline / 'section/report.txt').read_bytes()
    events = trace(a.attempt / 'section/trace.jsonl')
    assert not any(e['stage'] == 'writer_quote_review_unavailable' for e in events)
    receipts = [e['data'] for e in events if e['stage'] == 'writer_quote_review_material']
    requests = [e['data'] for e in events if e['stage'] == 'native_check_request']
    assert len(receipts) == len(requests) == 11
    changed = []
    for receipt in receipts:
        assert not receipt['rejected_bindings']
        assert receipt['original_review_text_preserved'] and not receipt['report_modified']
        assert receipt['semantic_verification'] == 'not_performed'
        assert not any(r['status'] in ('review_source_absent', 'review_source_binding_changed') for r in receipt['quote_bindings'])
        if not receipt['additions']:
            continue
        req, = [r for r in requests if (r['review_group'], r['round']) == (receipt['review_group'], receipt['round'])]
        assert len(req['prompt']) <= 60000
        for window in receipt['additions']:
            assert window['text'] in req['prompt']
        for binding in receipt['quote_bindings']:
            assert binding['quote'] in req['prompt']
        changed.append(dict(group=receipt['review_group'], round=receipt['round'],
                            windows=len(receipt['additions']), prompt_chars=len(req['prompt']),
                            restored_bindings=sum(r['status'] == 'window_attached' for r in receipt['quote_bindings'])))
    assert [r['group'] for r in changed] == [2, 3, 5]
    part = new['native_review']['parts'][0]
    findings = dict(status='engineering_audit_passed', freezes=freezes,
        changed_groups=changed, report_sha256=new['report_sha256'], report_chars=new['report_chars'],
        report_changed=False, native_status=new['native_review']['status'],
        unresolved_claim_ids=[r.get('claim_id') for r in part['unresolved']],
        applied_repairs=len(part['applied']), remaining_supplement_events=len(new['supplement_requests']),
        native_calls_before=12, native_calls_after=11,
        unchanged_historical_prompts_above_declared_60000=[dict(group=r['review_group'], chars=len(r['prompt'])) for r in requests if len(r['prompt']) > 60000],
        fresh_model_calls=0, retrieval_network_reads=0, new_independent_correction_credit=0,
        limits=['Known immune task only; no unseen-task evaluation.',
                'Exact quote transport does not prove entailment, correction or useful content retention.',
                'The whole report and unresolved outcomes remain identical; no quality improvement established.',
                'Native source-gap follow-up skipped, not an independently adjudicated correction.',
                'Historical unchanged over-budget prompts replayed only; no fresh over-budget call.',
                'First replay freeze did not explicitly list replay inputs; this audit binds and compares every replay byte. Future harness now freezes them.',
                'Original Writer prefix is bound as the exact prefix of its frozen full prompt; later harness also freezes it separately.'])
    write(a.out_dir / 'findings.json', findings)
    (a.out_dir / 'audit-script.py').write_bytes(Path(__file__).read_bytes())
    files = [f for root in roots for f in root.rglob('*') if f.is_file()]
    files += [a.out_dir / 'findings.json', a.out_dir / 'audit-script.py']
    manifest = {str(f): sha(f) for f in sorted(set(files))}
    write(a.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(f)) == h for f, h in manifest.items())
    write(a.out_dir / 'completion.json', dict(status='passed', payloads=len(manifest),
          manifest_sha256=sha(a.out_dir / 'MANIFEST.json'), fresh_model_calls=0,
          new_independent_correction_credit=0))
    print((a.out_dir / 'completion.json').read_text())


if __name__ == '__main__':
    main()
