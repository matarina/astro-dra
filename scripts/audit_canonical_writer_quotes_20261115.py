"""Verify source-only Writer transport and exact replay, without grading science."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from research_verify.canonical_fields import selected_writer_units


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
    root = Path('evaluation/frontier-strategy-20261113')
    launch = read(args.run / 'launch.json')
    info = json.loads(subprocess.check_output(['docker', 'inspect', launch['container_id']]))[0]
    assert info['State']['Status'] == 'exited' and info['State']['ExitCode'] == 0
    assert info['Image'] == launch['image_id']
    assert info['HostConfig']['NetworkMode'] == 'host'
    assert info['Config']['Entrypoint'] == ['/install/.venv/bin/python']
    assert info['Config']['Healthcheck']['Test'] == ['NONE']
    for dest in ['/workspace', str(Path.cwd())]:
        assert not next(m for m in info['Mounts'] if m['Destination'] == dest)['RW']
    reference = json.loads(subprocess.check_output(['docker', 'inspect', launch['network_reference_container']]))[0]
    def overlays(value):
        return sorted((m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info) == overlays(reference) and len(overlays(info)) == 3
    assert all(not m[2] for m in overlays(info))
    attempt = args.run / 'attempt'
    done, plan, calls = [read(attempt / name) for name in ['completion.json', 'plan.json', 'calls.json']]
    assert done['status'] == 'completed_writer_stage' and done['fresh_model_calls'] == 1
    assert done['strict_reader_cached_calls'] == 4 and len(calls) == 5
    assert plan['maximum_fresh_calls'] == 1
    for freeze in [args.run / 'launch-freeze.json', attempt / 'prestart-freeze.json']:
        assert all(sha(Path(p)) == digest for p, digest in read(freeze).items())
    for path in (attempt / 'code').rglob('*'):
        if path.is_file():
            assert path.read_bytes() == resolve(path.relative_to(attempt / 'code')).read_bytes()
    reader = root / 'canonical-immune-writer-model-20261115-v1/attempt'
    for i, call in enumerate(calls):
        assert call['status'] == 'returned' and call['response_metadata']['finish_reason'] == 'stop'
        assert call['origin'] == ('fresh_model' if i == 4 else 'strict_reader_cache')
        assert call['prompt_chars'] <= (360000 if i == 4 else 140000)
        for kind in ['prompt', 'response']:
            path = attempt / f'call-{i:02d}-{kind}.txt'
            assert sha(path) == call[kind + '_sha256']
            if i < 4:
                assert path.read_bytes() == (reader / path.name).read_bytes()
        if i < 4:
            assert call['response_metadata'] == read(reader / 'calls.json')[i]['response_metadata']
    units, observations, requirements = [read(attempt / name) for name in ['source-units.json', 'observations.json', 'requirements.json']]
    transport = read(attempt / 'writer-field-transport.json')
    assert transport == selected_writer_units(observations, units, requirements)
    assert len(transport) == 44 and len(observations) == 51
    assert { (u['source_id'],u['unit_id']) for u in transport } == { (o['source_id'],o['unit_id']) for o in observations }
    assert all(set(u) == {'source_id', 'unit_id', 'kind', 'start', 'end', 'text', 'text_sha256', 'requirement_ids'} for u in transport)
    prefix = (root / 'section-writer-model-20261115-v1/attempt/native-writer-prefix.txt').read_text()
    prompt = (attempt / 'call-04-prompt.txt').read_text()
    assert prompt.startswith(prefix + '\nADDITIONAL SOURCE-ONLY SELECTED ORIGINAL UNITS:\n')
    assert json.dumps(transport, ensure_ascii=False) in prompt
    preflight = root / 'canonical-immune-writer-quotes-preflight-20261115-v2'
    assert (preflight / 'call-04-prompt.txt').read_text() == prompt
    replay = args.out_dir / 'strict-replay'
    proc = subprocess.run([sys.executable, 'scripts/run_canonical_immune_writer_quotes_20261115.py',
        '--out-dir', str(replay), '--replay-attempt', str(attempt), '--reader-cache', str(reader)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (args.out_dir / 'strict-replay-output.txt').write_text(proc.stdout)
    assert proc.returncode == 0
    assert read(replay / 'completion.json')['fresh_model_calls'] == 0
    for i in range(5):
        for kind in ['prompt', 'response']:
            name = f'call-{i:02d}-{kind}.txt'
            assert (attempt / name).read_bytes() == (replay / name).read_bytes()
    report = attempt / 'candidate-report.md'
    assert report.read_bytes() == (replay / report.name).read_bytes()
    write(args.out_dir / 'audit.json', dict(execution_provenance_verified=True,
        actual_fresh_calls=1, strict_reader_cache_calls=4, replay_fresh_calls=0,
        selected_original_units=44, source_observations=51,
        writer_prompt_chars=len(prompt), unchanged_prefix_chars=len(prefix),
        fresh_writer_token_usage=calls[4]['response_metadata']['token_usage'],
        report_chars=len(report.read_text()), report_sha256=sha(report),
        full_native_pipeline_complete=False, independent_assessment_complete=False,
        useful_retention_and_new_error_clearance=False, new_independent_correction_credit=0,
        limits='Known immune task. Source-only appendix changes representation/length; original draft/native reader interpretations remain in the unchanged prefix. This is not complete removal of interpretive anchoring, cost parity, independent correction or unseen-task validation.'))
    files = [p for folder in [args.run, args.out_dir] for p in folder.rglob('*') if p.is_file()]
    files.append(Path(__file__))
    manifest = {str(p): sha(p) for p in files}
    write(args.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(p)) == digest for p, digest in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest), manifest_sha256=sha(args.out_dir / 'MANIFEST.json'), audit=read(args.out_dir / 'audit.json'))))


if __name__ == '__main__':
    main()
