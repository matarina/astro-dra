"""Terminal and provenance audit; native outcomes are not independent labels."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from research_verify.evidence_flow import parse_review


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['run', 'out-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    launch = read(a.run / 'launch.json')
    info = json.loads(subprocess.check_output(['docker', 'inspect', launch['container_id']]))[0]
    assert info['State']['Status'] == 'exited' and info['State']['ExitCode'] == 0
    assert info['Image'] == launch['image_id']
    assert info['HostConfig']['NetworkMode'] == 'host'
    assert info['Config']['Healthcheck']['Test'] == ['NONE']
    assert info['Config']['Entrypoint'] == ['/install/.venv/bin/python']
    overlays = [m for m in info['Mounts'] if m['Destination'].startswith('/install/')]
    reference = json.loads(subprocess.check_output(['docker', 'inspect', launch['network_reference_container']]))[0]
    old = [m for m in reference['Mounts'] if m['Destination'].startswith('/install/')]
    fields = lambda rows: sorted((m['Source'], m['Destination'], m['RW']) for m in rows)
    assert fields(overlays) == fields(old) and len(old) == 3
    assert all(not m['RW'] for m in overlays)
    assert next(m for m in info['Mounts'] if m['Destination'] == '/workspace')['RW'] is False
    assert next(m for m in info['Mounts'] if m['Destination'] == str(Path.cwd()))['RW'] is False
    attempt = a.run / 'attempt'
    frozen = read(attempt / 'prestart-freeze.json')
    assert all(sha(Path(f)) == h for f, h in frozen.items())
    assert all(sha(Path(f)) == h for f, h in read(a.run / 'launch-freeze.json').items())
    for filename, expected in frozen.items():
        if filename.startswith(('scripts/', 'local_deep_research/')):
            assert sha(attempt / 'code' / filename) == expected
    completed = read(attempt / 'completion.json')
    assert completed['frozen_inputs_unchanged'] and completed['fresh_calls'] == 2
    assert completed['report_rewrites'] == completed['new_independent_correction_credit'] == 0
    plan = read(attempt / 'plan.json')
    assert plan['maximum_fresh_calls'] == 2
    preflight = Path(info['Config']['Cmd'][info['Config']['Cmd'].index('--preflight-attempt') + 1])
    baseline = Path(info['Config']['Cmd'][info['Config']['Cmd'].index('--baseline-attempt') + 1])
    replay = a.out_dir / 'strict-replay'
    subprocess.run([sys.executable, 'scripts/run_uncited_discovery_probe_20261115.py',
        '--preflight-attempt', str(preflight), '--baseline-attempt', str(baseline),
        '--out-dir', str(replay), '--replay-attempt', str(attempt)], check=True)
    assert read(replay / 'completion.json')['replay_exact']
    observations = []
    for pair in plan['pairs']:
        folder = attempt / pair['key']
        result = read(folder / 'result.json')
        assert result['status'] == 'parsed' and result['origin'] == 'fresh_model'
        assert sha(folder / 'prompt.txt') == pair['prompt_sha256'] == result['prompt_sha256']
        assert sha(folder / 'response.txt') == result['response_sha256']
        prompt = (folder / 'prompt.txt').read_text()
        assert len(prompt) <= 60000
        assert 'UNASSIGNED SOURCE DISCOVERY' in prompt
        claims = {c['claim_id']: c for c in pair['claim_payload']}
        old_issues, old_checked = parse_review((folder / 'baseline-response.txt').read_text(), claims, include_checked=True)
        new_issues, new_checked = parse_review((folder / 'response.txt').read_text(), claims, include_checked=True)
        assert (new_issues, new_checked) == (result['native_issues'], result['native_checked'])
        for name in ['prompt.txt', 'response.txt', 'baseline-response.txt']:
            assert (folder / name).read_bytes() == (replay / pair['key'] / name).read_bytes()
        observations.append(dict(key=pair['key'], claims=pair['claim_payload'],
            prompt_chars=len(prompt), baseline_issues=old_issues, baseline_checked=old_checked,
            new_issues=new_issues, new_checked=new_checked,
            response_metadata=result['response_metadata'],
            classification='Native model observations only; no independent correction or retention/new-error assessment.'))
    write(a.out_dir / 'native-observations.json', observations)
    write(a.out_dir / 'terminal.json', dict(container_id=launch['container_id'],
        state=info['State']['Status'], exit_code=info['State']['ExitCode'],
        image_id=info['Image'], maximum_fresh_calls=2, fresh_calls=2,
        report_rewrites=0, new_independent_correction_credit=0))
    (a.out_dir / 'audit-script.py').write_bytes(Path(__file__).read_bytes())
    files = [f for root in [a.run, a.out_dir] for f in root.rglob('*') if f.is_file()]
    manifest = {str(f): sha(f) for f in sorted(set(files))}
    write(a.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(f)) == h for f, h in manifest.items())
    write(a.out_dir / 'completion.json', dict(status='passed', payloads=len(manifest),
        manifest_sha256=sha(a.out_dir / 'MANIFEST.json'), audit_fresh_calls=0,
        new_independent_correction_credit=0))
    print((a.out_dir / 'completion.json').read_text())


if __name__ == '__main__':
    main()
