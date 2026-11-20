"""Audit terminal execution, literal full-report transport and strict zero-call replay; no scientific verdict."""
import collections,json,subprocess,hashlib
from pathlib import Path
from scripts.run_associated_field_report_pair_20261115 import prepare,read,sha,write,R
from scripts.run_native_original_report_pair_20261114 import Trace
from research_verify.field_comparison import compare_and_edit

def seal(root):
    files={str(p.relative_to(root)):sha(p)for p in sorted(root.rglob('*'))if p.is_file()and p.name!='MANIFEST.json'}
    write(root/'MANIFEST.json',dict(scope='Integrity only; no quality or semantic success',files=files))
    assert all(sha(root/p)==h for p,h in files.items())
    return sha(root/'MANIFEST.json')

def main():
    root=R/'associated-field-report-model-20261115-v1';attempt=root/'attempt'
    launch=read(root/'launch.json');runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
    assert runtime['State']['Status']=='exited'and runtime['State']['ExitCode']==0
    assert runtime['Image']==launch['image_id']and runtime['Config']['Healthcheck']['Test']==['NONE']and runtime['HostConfig']['NetworkMode']=='host'
    binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
    assert next(m for m in binds if m['RW'])['Source']==str(root.resolve())
    for item in read(root/'readonly-mount-freeze.json'):
        m,=[m for m in binds if m['Destination']==item['destination']]
        assert not m['RW']and m['Source']==item['source']
        if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    for name,h in read(attempt/'prestart-freeze.json').items():
        path=Path(name)
        if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
        assert sha(path)==h
        try:rel=path.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    complete=read(attempt/'completion.json');assert complete['status']=='complete_report_source_targeted_diagnostic'and complete['frozen_inputs_unchanged']
    calls=read(attempt/'calls.json');assert 4<=len(calls)<=6 and complete['fresh_calls']==len(calls)
    usage=collections.Counter()
    for i,row in enumerate(calls):
        assert row['index']==i and row['status']=='returned'and row['origin']=='fresh_model'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==row['prompt_sha256']and sha(attempt/f'call-{i:02d}-response.txt')==row['response_sha256']
        assert row['response_metadata']['finish_reason']=='stop'
        usage.update({k:v for k,v in row['response_metadata'].get('token_usage',{}).items()if type(v)is int})
    case,report,material,requirements,anchors,jobs,inputs=prepare()
    assert (attempt/'original-report.txt').read_text()==report
    assert read(attempt/'source-material.json')==dict(text=str(material),views={str(k):v for k,v in material.views.items()})
    out=R/'associated-field-report-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
    cursor=0;stats=[]
    for index,job in enumerate(jobs):
        dest=out/f'strict-replay-arm-{index:02d}';dest.mkdir();trace=Trace(dest/'trace.jsonl')
        def invoke(prompt,stage):
            nonlocal cursor
            row=calls[cursor];assert row['arm']==job['arm']and row['stage']==stage
            assert prompt==(attempt/f'call-{cursor:02d}-prompt.txt').read_text()
            assert report in prompt and str(material)in prompt
            if stage=='per_field_comparison':
                pre=R/'associated-field-report-preflight-20261115-v1/attempt'/f'comparison-{index:02d}-prompt.txt'
                assert prompt==pre.read_text()
            raw=(attempt/f'call-{cursor:02d}-response.txt').read_text();cursor+=1;return raw
        answer,result=compare_and_edit(case['query'],report,material,requirements,anchors,job['notes'],{5},invoke,trace)
        assert result==read(attempt/f'arm-{index:02d}/result.json')
        assert answer==(attempt/f'arm-{index:02d}/candidate-report.txt').read_text()
        assert hashlib.sha256(answer.encode()).hexdigest()==complete['results'][index]['report_sha256']
        write(dest/'result.json',result);(dest/'candidate-report.txt').write_text(answer)
        stats.append(dict(arm=job['arm'],observations=len(result['observations']),
            comparison_states=dict(collections.Counter(c['state']for c in result['comparisons'])),
            structurally_eligible_proposals=len(result['edit_proposals']['eligible']),
            structurally_unresolved_proposals=len(result['edit_proposals']['unresolved']),
            model_confirmed_edits=len(result['changes']),model_decisions=result['decisions'],
            changed_characters_original=sum(len(c['original_text'])for c in result['changes']),
            report_chars=len(answer),original_report_chars=len(report),
            semantic_assessment='UNASSESSED; model confirmation is fallible, all other source/report claims unassessed'))
    assert cursor==len(calls)
    write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=len(calls),strict_replay_fresh_calls=0,usage=dict(usage),statistics=stats,
        complete_original_report_and_source_in_every_call=True,independent_assessment_complete=False,independent_correction_credit=0))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    seals={str(folder):seal(folder)for folder in [R/'associated-field-report-preflight-20261115-v1',root,out]}
    print(json.dumps(dict(fresh_calls=len(calls),usage=dict(usage),statistics=[{k:v for k,v in s.items()if k!='model_decisions'}for s in stats],manifests=seals),ensure_ascii=False))

if __name__=='__main__':main()
