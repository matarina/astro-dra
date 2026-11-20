"""At most two native-stage probes of exact uncited-discovery cache misses."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.evidence_flow import parse_review
from scripts.experiment_error_receipt import error_receipt


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def claims(prompt):
    return json.loads(prompt.split('\nFINAL ANSWER:\n', 1)[1].split('\n\nSUPPLIED SOURCES:', 1)[0])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['preflight-attempt', 'baseline-attempt', 'out-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--replay-attempt', type=Path)
    a = p.parse_args()
    assert not (a.execute and a.replay_attempt)
    a.out_dir.mkdir(exist_ok=False)
    inputs = [a.preflight_attempt / name for name in ['plan.json', 'calls.json', 'completion.json',
        'prestart-freeze.json', 'section/trace.jsonl', 'section/report.txt']]
    inputs += [a.baseline_attempt / 'calls.json', a.baseline_attempt / 'section/trace.jsonl']
    # Preserve and check the complete source/code/input freeze behind the actual prompts.
    prior_freeze = read(a.preflight_attempt / 'prestart-freeze.json')
    assert all(sha(Path(f)) == h for f, h in prior_freeze.items())
    inputs += [Path(f) for f in prior_freeze]
    calls = read(a.preflight_attempt / 'calls.json')
    missing = [c for c in calls if c['status'] == 'unavailable']
    assert 0 < len(missing) <= 2
    events = [json.loads(line) for line in (a.preflight_attempt / 'section/trace.jsonl').read_text().splitlines()]
    old_events = [json.loads(line) for line in (a.baseline_attempt / 'section/trace.jsonl').read_text().splitlines()]
    old_calls = read(a.baseline_attempt / 'calls.json')
    pairs = []
    for c in missing:
        assert c['stage'] == 'native_check' and c['origin'] == 'strict_cache_miss'
        pp = a.preflight_attempt / f"call-{c['index']:02d}-prompt.txt"
        assert sha(pp) == c['prompt_sha256'] and len(pp.read_text()) <= 60000
        prompt = pp.read_text()
        req, = [e['data'] for e in events if e['stage'] == 'native_check_request' and e['data']['prompt'] == prompt]
        baseline, = [e['data'] for e in old_events if e['stage'] == 'native_check_request'
                      and (e['data']['review_group'], e['data']['round']) == (req['review_group'], req['round'])]
        old_prompt = baseline['prompt']
        assert claims(prompt) == claims(old_prompt)
        old_sha = hashlib.sha256(old_prompt.encode()).hexdigest()
        oc, = [o for o in old_calls if o['arm'] == 'section' and o['prompt_sha256'] == old_sha]
        op = a.baseline_attempt / f"call-{oc['index']:02d}-prompt.txt"
        rp = a.baseline_attempt / f"call-{oc['index']:02d}-response.txt"
        assert sha(op) == oc['prompt_sha256'] and sha(rp) == oc['response_sha256']
        assert 'UNASSIGNED SOURCE DISCOVERY' in prompt
        inputs += [pp, op, rp]
        pairs.append(dict(key='group-' + str(req['review_group']), prompt_path=str(pp),
            prompt_sha256=sha(pp), baseline_path=str(rp), baseline_prompt_path=str(op),
            baseline_response_metadata=oc['response_metadata'], claim_payload=claims(prompt)))
    inputs += [Path(__file__).resolve().relative_to(Path.cwd())]
    if a.replay_attempt:
        inputs += [a.replay_attempt / 'completion.json']
        inputs += [a.replay_attempt / pair['key'] / name for pair in pairs
                   for name in ['prompt.txt', 'response.txt', 'result.json']]
    freeze = {str(f): sha(f) for f in inputs}
    write(a.out_dir / 'prestart-freeze.json', freeze)
    for f in map(Path, freeze):
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            dest = a.out_dir / 'code' / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    settings = read(a.preflight_attempt / 'plan.json')['settings']
    write(a.out_dir / 'plan.json', dict(scope='Native-stage source discovery on one KNOWN immune report. '
        'Same claims and explicit citation IDs; all acquired-source abstract inventory plus original windows. '
        'No report generation or automatic repair; no independent quality/adoption conclusion.',
        pairs=pairs, settings=settings, maximum_fresh_calls=len(pairs), maximum_prompt_chars=60000,
        new_independent_correction_credit=0))
    results = []
    for pair in pairs:
        folder = a.out_dir / pair['key']
        folder.mkdir()
        prompt = Path(pair['prompt_path']).read_text()
        (folder / 'prompt.txt').write_text(prompt)
        (folder / 'baseline-response.txt').write_bytes(Path(pair['baseline_path']).read_bytes())
        row = dict(key=pair['key'], prompt_sha256=sha(folder / 'prompt.txt'))
        try:
            if a.replay_attempt:
                prev = a.replay_attempt / pair['key']
                old = read(prev / 'result.json')
                assert (prev / 'prompt.txt').read_text() == prompt
                assert sha(prev / 'response.txt') == old['response_sha256']
                raw, meta = (prev / 'response.txt').read_text(), old['response_metadata']
                row['origin'] = 'strict_saved_response_replay'
            elif a.execute:
                from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                from local_deep_research.config.thread_settings import settings_context
                from local_deep_research.config.llm_config import get_llm
                defaults = read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                effective = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()}) | settings | {'llm.provider': 'openai_endpoint', 'llm.request_timeout': 180, 'llm.max_retries': 0}
                with settings_context(type('Settings', (), {'username': None, 'get_setting': staticmethod(lambda k, d=None: effective.get(k, d))})()):
                    model = get_llm(settings_snapshot=effective)
                response = model.invoke(prompt)
                raw, meta = str(response.content), response.response_metadata
                row['origin'] = 'fresh_model'
            else:
                raw, meta = Path(pair['baseline_path']).read_text(), pair['baseline_response_metadata']
                row['origin'] = 'preflight_baseline_response_only_not_candidate_evaluation'
            (folder / 'response.txt').write_text(raw)
            row.update(response_sha256=sha(folder / 'response.txt'), response_metadata=meta)
            write(folder / 'result.json', row)
            issues, checked = parse_review(raw, {c['claim_id']: c for c in pair['claim_payload']}, include_checked=True)
            row.update(status='parsed', native_issues=issues, native_checked=checked)
            if a.replay_attempt:
                assert (issues, checked) == (old['native_issues'], old['native_checked'])
        except Exception as exc:
            row.update(status='unavailable', failure=error_receipt(exc))
        write(folder / 'result.json', row)
        results.append(row)
    completion = dict(results=results, frozen_inputs_unchanged=all(sha(Path(f)) == h for f, h in freeze.items()),
        fresh_calls=sum(r.get('origin') == 'fresh_model' for r in results),
        replay_exact=bool(a.replay_attempt) and all(r['status'] == 'parsed' for r in results),
        report_rewrites=0, new_independent_correction_credit=0)
    write(a.out_dir / 'completion.json', completion)
    print(json.dumps({k: v for k, v in completion.items() if k != 'results'}))
    if not completion['frozen_inputs_unchanged'] or any(r['status'] != 'parsed' for r in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
