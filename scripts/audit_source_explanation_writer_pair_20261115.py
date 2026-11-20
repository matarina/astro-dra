"""Audit paired Writer source explanations and exact replay; no scientific verdict."""
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
    assert completion['status'] == 'completed_paired_writer_stage' and completion['fresh_calls'] == 2
    assert len(calls) == 3 and plan['maximum_fresh_calls'] == 2
    assert plan['settings']['llm.model'] == 'deepseek-v4-flash'
    for freeze in [args.run / 'launch-freeze.json', attempt / 'prestart-freeze.json']:
        assert all(sha(Path(p)) == digest for p, digest in read(freeze).items())
    for path in (attempt / 'code').rglob('*'):
        if path.is_file():
            assert path.read_bytes() == resolve(path.relative_to(attempt / 'code')).read_bytes()
    usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    for index, call in enumerate(calls):
        assert call['status'] == 'returned'
        assert call['origin'] == ('strict_reader_cache' if index==0 else 'fresh_model')
        assert call['response_metadata']['finish_reason'] == 'stop'
        for kind in ['prompt', 'response']:
            extension = 'json' if kind == 'request' else 'txt'
            assert sha(attempt / f'call-{index:02d}-{kind}.{extension}') == call[kind + '_sha256']
        if index>0:
            for key in usage:
                usage[key] += call['response_metadata']['token_usage'][key]
    from scripts.run_source_explanation_writer_pair_20261115 import writer_prompt
    from research_verify.source_explanations import parse_explanations
    units = read(attempt / 'source-units.json')
    notes = parse_explanations((attempt / 'call-00-response.txt').read_text(), units)
    assert notes == read(attempt / 'source-explanations.json')
    common = (attempt / 'common-writer-context.txt').read_text()
    prefix = Path('evaluation/frontier-strategy-20261113/section-writer-model-20261115-v1/attempt/native-writer-prefix.txt').read_text()
    assert common.startswith(prefix)
    reader = (attempt / 'call-00-prompt.txt').read_text()
    assert reader == (attempt / 'reader-prompt.txt').read_text() and prefix not in reader
    original_draft = Path('evaluation/frontier-strategy-20261113/immune-evidence/original-immune-report.txt').read_text()
    assert original_draft not in reader
    for i, supplied_notes in enumerate([[], notes]):
        expected = writer_prompt(common, supplied_notes)
        assert (attempt / f'call-{i+1:02d}-prompt.txt').read_text() == expected
        assert (attempt / f'writer-{i}-precall-prompt.txt').read_text() == expected
        assert sha(attempt / f'writer-{i}-precall-prompt.txt') == read(attempt / 'writer-precall-freeze.json')[f'writer-{i}-precall-prompt.txt']
        assert expected.startswith(common)
    assert [r['stage'] for r in calls] == ['source_explanations', 'baseline_writer', 'explanation_writer']
    budget=read(attempt/'writer-token-budget.json')
    assert budget['both_within_estimated_budget'] and budget['context_limit']==131072
    assert all(n+budget['output_tokens']+budget['reserve_tokens']<=budget['context_limit'] for n in budget['conservative_estimated_prompt_tokens'])
    assert budget['prompt_sha256s']==[sha(attempt/f'writer-{i}-precall-prompt.txt') for i in range(2)]
    replay = args.out_dir / 'strict-replay'
    proc = subprocess.run([sys.executable, 'scripts/run_source_explanation_writer_pair_20261115.py',
        '--out-dir', str(replay), '--replay-attempt', str(attempt)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (args.out_dir / 'strict-replay-output.txt').write_text(proc.stdout)
    assert proc.returncode == 0
    rc = read(replay / 'completion.json')
    assert rc['fresh_calls'] == 0 and rc['status'] == completion['status']
    for index in range(3):
        for kind, extension in [('prompt', 'txt'), ('response', 'txt')]:
            name = f'call-{index:02d}-{kind}.{extension}'
            assert (attempt / name).read_bytes() == (replay / name).read_bytes()
    for name in ['baseline-report.md', 'candidate-report.md', 'source-explanations.json']:
        assert (attempt / name).read_bytes() == (replay / name).read_bytes()
    write(args.out_dir / 'audit.json', dict(execution_provenance_verified=True,
        fresh_calls=2, strict_reader_cached_calls=1, replay_fresh_calls=0, usage=usage, identical_writer_common_material=True,
        source_explanation_reader_blind_to_original_draft=True, report_post_edits=0,
        full_native_pipeline_complete=False,
        independent_assessment_complete=False, new_independent_correction_credit=0,
        cached_reader_historical_usage=calls[0]['response_metadata']['token_usage'],
        actual_writer_prompt_tokens=[r['response_metadata']['token_usage']['prompt_tokens'] for r in calls[1:]],
        tokenizer_proxy_counts=budget['proxy_prompt_tokens'],
        limits='Paired complete Writers, not full native pipeline. Extra source-reader compute belongs to candidate. Both arms include same new primary body; historical outputs have different evidence. No pure acquisition-effect or independent semantic/retention/new-error claim. Plan native_fact_consistency_setting records production constraint, not proof the isolated Writer-only stage executed native checking.'))
    files = [p for directory in [args.run, args.out_dir] for p in directory.rglob('*') if p.is_file()]
    files.append(Path(__file__))
    manifest = {str(p): sha(p) for p in files}
    write(args.out_dir / 'MANIFEST.json', manifest)
    assert all(sha(Path(p)) == digest for p, digest in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest), manifest_sha256=sha(args.out_dir / 'MANIFEST.json'), audit=read(args.out_dir / 'audit.json'))))


if __name__ == '__main__':
    main()
