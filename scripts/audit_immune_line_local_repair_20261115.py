"""Terminal, byte-preservation and zero-call replay audit; no independent scientific assessment."""
import json,subprocess,collections
from pathlib import Path
from scripts.run_immune_line_local_repair_20261115 import prepare_cases,R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
    root=R/'immune-line-local-repair-model-20261115-v1';attempt=root/'attempt';rr=R/'immune-line-local-repair-replay-20261115-v1';replay=rr/'attempt'
    run,=json.loads(subprocess.check_output(['docker','inspect',read(root/'launch.json')['container']]))
    rep,=json.loads(subprocess.check_output(['docker','inspect',read(rr/'launch.json')['container']]))
    for runtime,folder in [(run,root),(rep,rr)]:
        assert runtime['State']['Status']=='exited'and runtime['State']['ExitCode']==0
        assert runtime['Image']==read(folder/'launch.json')['image']and runtime['Config']['Healthcheck']['Test']==['NONE']
        binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
        assert next(m for m in binds if m['RW'])['Source']==str(folder.resolve())
        for item in read(folder/'readonly-mount-freeze.json'):
            m,=[m for m in binds if m['Destination']==item['destination']];assert not m['RW']and m['Source']==item['source']
            if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    assert rep['HostConfig']['NetworkMode']=='none'
    for name,h in read(attempt/'prestart-freeze.json').items():
        p=Path(name)
        if str(p).startswith('/workspace/'):p=Path.cwd()/p.relative_to('/workspace')
        assert sha(p)==h
        try:rel=p.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    complete=read(attempt/'completion.json');rc=read(replay/'completion.json')
    assert complete['status']==rc['status']=='completed_immune_line_local_repair_diagnostic'
    assert complete['frozen_inputs_unchanged']and rc['frozen_inputs_unchanged']and rc['fresh_calls']==0
    for k in ['results','logical_calls','independent_correction_credit']:assert complete[k]==rc[k]
    calls=read(attempt/'calls.json');rcalls=read(replay/'calls.json');assert len(calls)==len(rcalls)==complete['fresh_calls']<=3
    usage=collections.Counter()
    for i,(c,r)in enumerate(zip(calls,rcalls)):
        assert c['index']==i and c['status']=='returned'and c['origin']=='fresh_model'and c['response_metadata']['finish_reason']=='stop'
        assert r['origin']=='strict_replay'
        for k in ['stage','case_index','prompt_sha256','response_sha256']:assert c[k]==r[k]
        for kind in ['prompt','response']:assert sha(attempt/f'call-{i:02d}-{kind}.txt')==c[f'{kind}_sha256']==sha(replay/f'call-{i:02d}-{kind}.txt')
        usage.update({k:v for k,v in c['response_metadata']['token_usage'].items()if type(v)is int})
    allcases,_=prepare_cases();cases=[allcases[1]];witnesses=[]
    for result,c in zip(complete['results'],cases):
        i=result['case_index'];assert (attempt/f'original-report-{i}.txt').read_text()==c['report']
        candidate=(attempt/f'candidate-report-{i}.txt').read_text();assert candidate==(replay/f'candidate-report-{i}.txt').read_text()
        edits=[]
        for change in result['changes']:
            p=result['proposals']['eligible'][change['candidate_index']]
            if p['action']=='replace':
                for b in p['token_span_bindings']:
                    assert c['report'][b['start']:b['end']]==b['original_text']
                    assert '\n'not in b['original_text']and '\r'not in b['original_text']
                    edits.append(dict(start=b['start'],end=b['end'],text=b['replacement']))
            else:edits.append(dict(start=p['anchor_end'],end=p['anchor_end'],text='\n\n'+p['addition']+'\n'))
        expected=c['report']
        for e in sorted(edits,key=lambda x:x['start'],reverse=True):expected=expected[:e['start']]+e['text']+expected[e['end']:]
        assert candidate==expected
        witnesses.append(dict(case_index=i,applied_model_edits=len(edits),actual_subspan_changes=edits,all_bytes_outside_selected_subspans_preserved=True,
            original_chars=len(c['report']),candidate_chars=len(candidate),semantic_assessment='UNASSESSED'))
    out=R/'immune-line-local-repair-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=len(calls),replay_fresh_calls=0,usage=dict(usage),witnesses=witnesses,independent_correction_credit=0))
    write(out/'runtime.json',dict(model=dict(state=run['State'],image=run['Image'],mounts=run['Mounts'],network=run['HostConfig']['NetworkMode']),replay=dict(state=rep['State'],image=rep['Image'],network=rep['HostConfig']['NetworkMode'])))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    manifests={str(p):seal(p)for p in [R/'immune-line-local-repair-preflight-20261115-v1',root,rr,out]}
    hand=R/'immune-line-local-repair-coordinator-handoff-20261115-v1';hand.mkdir(exist_ok=False);neutral=hand/'assessment-input';neutral.mkdir()
    for i,c in enumerate(cases):
        folder=neutral/f'case-{i}';folder.mkdir()
        for name in ['original-report','candidate-report','original-question']:(folder/f'{name}.txt').write_bytes((attempt/f'{name}-{i}.txt').read_bytes())
        write(folder/'complete-source-units.json',c['units'])
        xml=R/'acquired-confirmation-coordinator-handoff-20261115-v2/assessment-input/primary-source-9.xml'
        (folder/'primary-source.xml').write_bytes(xml.read_bytes())
    write(neutral/'status.json',dict(status='UNASSESSED',case_origins=['Actual known adverse experimental immune native output, not original archive output'],
        limits='Known controls, single source per task; not complete6task or20paper research/generic quality validation',independent_correction_credit=0))
    write(hand/'fallible-model-decisions.json',complete['results']);write(hand/'fallible-field-comparisons.json',read(attempt/'field-comparisons.json'));write(hand/'execution-evidence.json',dict(manifests=manifests,audit=read(out/'audit.json')))
    (hand/'README.md').write_text('Goal ACTIVE; new independent correction credit0. Full original questions, primary sources and actual original/candidate reports are neutral UNASSESSED inputs. Model decisions outside neutral inputs. Literal outside-subspan preservation does not prove correct selection, source entailment, no new errors or global consistency. No independent review requested, production deployment or other-session writes.\n')
    manifests[str(hand)]=seal(hand);print(json.dumps(dict(audit=read(out/'audit.json'),manifests=manifests)))
if __name__=='__main__':main()
