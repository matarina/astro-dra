"""Execution audit for two matched IF structural-scope Readers; no semantic verdict."""
import argparse
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
    ref = json.loads(subprocess.check_output(['docker', 'inspect', 'c333dd2028c92f7040b527964662abf39f820cfa567c448aada5888e2112682c']))[0]
    overlays = lambda value: sorted((m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info) == overlays(ref) and len(overlays(info)) == 3
    assert all(not m[2] for m in overlays(info))
    # Never persist Config.Env, endpoint credentials, or full inspect output.
    write(args.out_dir/'runtime.json', dict(state=info['State'], image=info['Image'], mounts=info['Mounts'],
        network=info['HostConfig']['NetworkMode'], entrypoint=info['Config']['Entrypoint']))
    attempt = args.run/'attempt'
    completion, calls, plan = [read(attempt/n) for n in ['completion.json','calls.json','plan.json']]
    assert completion['status'] == 'completed_reading_diagnostic' and completion['fresh_calls'] == 2
    assert completion['frozen_inputs_unchanged'] and len(calls) == 2 and plan['maximum_fresh_calls'] == 2
    assert all(sha(Path(p)) == digest for p,digest in read(attempt/'prestart-freeze.json').items())
    for p in (attempt/'code').rglob('*'):
        if p.is_file():
            assert p.read_bytes() == resolve(p.relative_to(attempt/'code')).read_bytes()
    usage = dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)
    case, = read(Path('evaluation/frontier-strategy-20261113/source-span-if-original-inputs-20261115-v1/case-manifest.json'))['cases']
    draft = Path(case['draft']).read_text()
    for i,call in enumerate(calls):
        assert call['origin'] == 'fresh_model' and call['status'] == 'returned'
        assert call['response_metadata']['finish_reason'] == 'stop'
        for kind,extension in [('prompt','txt'),('request','json'),('response','txt')]:
            assert sha(attempt/f'call-{i:02d}-{kind}.{extension}') == call[kind+'_sha256']
        prompt = (attempt/f'call-{i:02d}-prompt.txt').read_text()
        assert read(attempt/f'call-{i:02d}-request.json') == prompt and draft not in prompt
        for key in usage:
            usage[key] += call['response_metadata']['token_usage'][key]
    from scripts.run_if_structure_reading_pair_20261115 import prepare
    _,_,expected=prepare()
    assert [job['arm'] for job in expected]==['paragraph_context','xml_structure_scopes']
    assert all(job['source_id']==5 for job in expected)
    for i,job in enumerate(expected):
        assert (attempt/f'call-{i:02d}-prompt.txt').read_text()==job['prompt']
    baseline,candidate=[job['units'] for job in expected]
    assert all({k:v for k,v in row.items() if k!='original_structure'}==before for row,before in zip(candidate,baseline))
    replay = args.out_dir/'strict-replay'
    proc = subprocess.run([sys.executable,'scripts/run_if_structure_reading_pair_20261115.py',
        '--out-dir',str(replay),'--replay-attempt',str(attempt)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (args.out_dir/'strict-replay-output.txt').write_text(proc.stdout)
    assert proc.returncode == 0
    rc = read(replay/'completion.json')
    assert rc['fresh_calls'] == 0 and rc['results'] == completion['results']
    for i in range(2):
        for kind,ext in [('prompt','txt'),('request','json'),('response','txt')]:
            name=f'call-{i:02d}-{kind}.{ext}'
            assert (attempt/name).read_bytes() == (replay/name).read_bytes()
    write(args.out_dir/'audit.json',dict(execution_provenance_verified=True,fresh_calls=2,replay_fresh_calls=0,
        original_unit_fields_unchanged=True,original_xml_context_recomputed=True,
        reader_blind_to_original_draft=True,usage=usage,
        report_changes=0,independent_assessment_complete=False,new_independent_correction_credit=0,
        limits='Two matched known-paper Reader arms only; other papers/required full task unexercised. Candidate adds XML structural scope sets; common identity serialization is lossless. No repeated critical-pair variability validation. No Writer/native pipeline, scientific adjudication, correction/retention/new-error or generalization result. Endpoint checkpoint/tokenizer identity unverified.'))
    files = [p for d in [args.run,args.out_dir] for p in d.rglob('*') if p.is_file()]
    files.append(Path(__file__))
    manifest = {str(p):sha(p) for p in files}
    write(args.out_dir/'MANIFEST.json',manifest)
    assert all(sha(Path(p)) == digest for p,digest in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest),manifest_sha256=sha(args.out_dir/'MANIFEST.json'),audit=read(args.out_dir/'audit.json'))))


if __name__ == '__main__':
    main()
