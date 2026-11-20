"""Audit actual image request bytes and zero-fresh replay; never grade science."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def resolve(path):
    return Path.cwd() / path.relative_to('/workspace') if str(path).startswith('/workspace/') else path


def sha(path):
    return hashlib.sha256(resolve(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(exist_ok=False)
    launch = read(args.run / 'launch.json')
    info = json.loads(subprocess.check_output(['docker', 'inspect', launch['container_id']]))[0]
    assert info['State']['Status'] == 'exited' and info['State']['ExitCode'] == 0
    assert info['Image'] == launch['image_id']
    assert info['HostConfig']['NetworkMode'] == 'host'
    assert info['Config']['Entrypoint'] == ['/install/.venv/bin/python']
    assert info['Config']['Healthcheck']['Test'] == ['NONE']
    for dest in ['/workspace', str(Path.cwd())]:
        assert not next(m for m in info['Mounts'] if m['Destination'] == dest)['RW']
    ref = json.loads(subprocess.check_output(['docker', 'inspect', launch['network_reference_container']]))[0]
    def overlays(value):
        return sorted((m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info) == overlays(ref) and len(overlays(info)) == 3
    assert all(not row[2] for row in overlays(info))
    attempt = args.run / 'attempt'
    completion, calls, plan = [read(attempt / name) for name in ['completion.json', 'calls.json', 'plan.json']]
    assert completion['status'] == 'completed_reading_diagnostic' and completion['fresh_calls'] == 4
    assert len(calls) == 4 and plan['maximum_fresh_calls'] == 4
    assert plan['settings']['llm.model'] == 'qwen3-vl-235b-a22b-instruct-fp8'
    for freeze in [args.run / 'launch-freeze.json', attempt / 'prestart-freeze.json']:
        assert all(sha(Path(p)) == digest for p, digest in read(freeze).items())
    for path in (attempt / 'code').rglob('*'):
        if path.is_file():
            assert path.read_bytes() == resolve(path.relative_to(attempt / 'code')).read_bytes()
    usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    for index, call in enumerate(calls):
        assert call['status'] == 'returned' and call['origin'] == 'fresh_model'
        assert call['response_metadata']['finish_reason'] == 'stop'
        for kind in ['prompt', 'request', 'response']:
            extension = 'json' if kind == 'request' else 'txt'
            assert sha(attempt / f'call-{index:02d}-{kind}.{extension}') == call[kind + '_sha256']
        for key in usage:
            usage[key] += call['response_metadata']['token_usage'][key]
    for left, right in [(0, 1), (2, 3)]:
        text = read(attempt / f'call-{left:02d}-request.json')
        image = read(attempt / f'call-{right:02d}-request.json')
        assert text == image[:1] and len(text) == 1 and len(image) == 2
        assert (attempt / f'call-{left:02d}-prompt.txt').read_bytes() == (attempt / f'call-{right:02d}-prompt.txt').read_bytes()
        raw = base64.b64decode(image[1]['image_url']['url'].split(',', 1)[1], validate=True)
        job = plan['jobs'][right]
        assert raw == resolve(Path(job['image_path'])).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == job['image_sha256']
    replay = args.out_dir / 'strict-replay'
    proc = subprocess.run([sys.executable, 'scripts/run_source_figure_reading_20261115.py',
        '--out-dir', str(replay), '--replay-attempt', str(attempt)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (args.out_dir / 'strict-replay-output.txt').write_text(proc.stdout)
    assert proc.returncode == 0
    rc = read(replay / 'completion.json')
    assert rc['fresh_calls'] == 0 and rc['results'] == completion['results']
    for index in range(4):
        for kind, extension in [('prompt', 'txt'), ('request', 'json'), ('response', 'txt')]:
            name = f'call-{index:02d}-{kind}.{extension}'
            assert (attempt / name).read_bytes() == (replay / name).read_bytes()
    write(args.out_dir / 'audit.json', dict(execution_provenance_verified=True,
        fresh_calls=4, replay_fresh_calls=0, usage=usage, original_image_bytes_verified=True,
        identical_pair_text_verified=True, known_figures=2, report_edits=0,
        independent_assessment_complete=False, new_independent_correction_credit=0,
        limits='Exact request/image bytes and raw replies, not provider-side visual preprocessing or verified checkpoint. Source-only known-paper diagnostic, no complete report or semantic success.'))
    files = [p for directory in [args.run, args.out_dir] for p in directory.rglob('*') if p.is_file()]
    files.append(Path(__file__))
    manifest = {str(p): sha(p) for p in files}
    write(args.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(p)) == digest for p, digest in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest), manifest_sha256=sha(args.out_dir / 'MANIFEST.json'), audit=read(args.out_dir / 'audit.json'))))


if __name__ == '__main__':
    main()
