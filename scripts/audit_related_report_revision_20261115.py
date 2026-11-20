"""Integrity and zero-call replay only; no scientific adjudication."""
import json,subprocess,collections
from pathlib import Path
from scripts.run_related_report_revision_20261115 import R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
    root=R/'related-report-revision-model-20261115-v1';attempt=root/'attempt'
    replay=R/'related-report-revision-replay-20261115-v1';ra=replay/'attempt'
    launch=read(root/'launch.json');runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container']]))
    assert runtime['State']['Status']=='exited' and runtime['State']['ExitCode']==0 and runtime['Image']==launch['image']
    assert runtime['HostConfig']['NetworkMode']=='host' and runtime['Config']['Healthcheck']['Test']==['NONE']
    binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
    assert next(m for m in binds if m['RW'])['Source']==str(root.resolve())
    for item in read(root/'readonly-mount-freeze.json'):
        m,=[m for m in binds if m['Destination']==item['destination']]
        assert not m['RW'] and m['Source']==item['source']
        if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    for name,h in read(attempt/'prestart-freeze.json').items():
        p=Path(name)
        if str(p).startswith('/workspace/'):p=Path.cwd()/p.relative_to('/workspace')
        assert sha(p)==h
        try:rel=p.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    complete=read(attempt/'completion.json');replayed=read(ra/'completion.json')
    assert complete['status']=='completed_related_report_revision_diagnostic' and complete['frozen_inputs_unchanged']
    assert replayed['fresh_calls']==0 and replayed['status']==complete['status'] and replayed['frozen_inputs_unchanged']
    for key in ['logical_calls','results','revision','scientific_outcome_independently_assessed','independent_correction_credit']:
        assert complete[key]==replayed[key],key
    calls=read(attempt/'calls.json');rcalls=read(ra/'calls.json');assert len(calls)==len(rcalls)==complete['fresh_calls']<=9
    usage=collections.Counter()
    for i,(row,rrow) in enumerate(zip(calls,rcalls)):
        assert row['index']==i and row['status']=='returned' and row['origin']=='fresh_model' and row['response_metadata']['finish_reason']=='stop'
        assert rrow['origin']=='strict_replay'
        for key in ['stage','case_index','artifact_id','prompt_sha256','response_sha256']:assert row[key]==rrow[key]
        for kind in ['prompt','response']:
            assert sha(attempt/f'call-{i:02d}-{kind}.txt')==row[f'{kind}_sha256']==sha(ra/f'call-{i:02d}-{kind}.txt')
        usage.update({k:v for k,v in row['response_metadata']['token_usage'].items()if type(v)is int})
    assert sha(attempt/'candidate-report.txt')==sha(ra/'candidate-report.txt')
    out=R/'related-report-revision-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
    write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=binds,network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=len(calls),replay_fresh_calls=0,usage=dict(usage),
        same_prompts_responses_decisions_changes_and_candidate=True,model_confirmed_edits=len(complete['revision']['changes']),
        report_readbacks=len(complete['results']),scientific_outcome_independently_assessed=False,independent_correction_credit=0))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(audit=read(out/'audit.json'),manifests={str(p):seal(p)for p in [R/'related-report-revision-preflight-20261115-v1',root,replay,out]})))

if __name__=='__main__':main()
