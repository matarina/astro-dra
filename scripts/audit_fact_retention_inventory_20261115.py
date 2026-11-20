"""Terminal/source and zero-fresh exact inventory replay; no semantic adjudication."""
import json,subprocess,collections
from pathlib import Path
from scripts.run_fact_retention_inventory_20261115 import prepare,read,write,sha,R
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.retention_inventory import inventory_prompt,parse_inventory,retention_prompt,parse_retention

def main():
    root=R/'fact-retention-inventory-model-20261115-v1';attempt=root/'attempt';launch=read(root/'launch.json')
    runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
    assert runtime['State']['Status']=='exited'and runtime['State']['ExitCode']==0 and runtime['Image']==launch['image_id']
    assert runtime['Config']['Healthcheck']['Test']==['NONE']and runtime['HostConfig']['NetworkMode']=='host'
    binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
    assert next(m for m in binds if m['RW'])['Source']==str(root.resolve())
    for item in read(root/'readonly-mount-freeze.json'):
        m,=[m for m in binds if m['Destination']==item['destination']];assert not m['RW']and m['Source']==item['source']
        if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    for name,h in read(attempt/'prestart-freeze.json').items():
        path=Path(name)
        if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
        assert sha(path)==h
        try:rel=path.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    complete=read(attempt/'completion.json');assert complete['status']=='completed_retention_diagnostic'and complete['frozen_inputs_unchanged']
    calls=read(attempt/'calls.json');assert len(calls)==6 and complete['fresh_calls']==6
    usage=collections.Counter()
    for i,row in enumerate(calls):
        assert row['index']==i and row['status']=='returned'and row['origin']=='fresh_model'and row['response_metadata']['finish_reason']=='stop'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==row['prompt_sha256']and sha(attempt/f'call-{i:02d}-response.txt')==row['response_sha256']
        usage.update({k:v for k,v in row['response_metadata']['token_usage'].items()if type(v)is int})
    cases,prepared,_=prepare();inventories=[[],[]];results=[];statistics=[]
    for i,j in enumerate(prepared):
        prompt=inventory_prompt(cases[j['case_index']]['question'],j['texts'])
        assert prompt==j['prompt']==(attempt/f'call-{i:02d}-prompt.txt').read_text()
        assert prompt==(R/'fact-retention-inventory-preflight-20261115-v1/attempt'/f'prepared-{i:02d}-prompt.txt').read_text()
        assert calls[i]['stage']=='independent_span_inventory'and calls[i]['case_index']==j['case_index']
        inventories[j['case_index']].extend(parse_inventory((attempt/f'call-{i:02d}-response.txt').read_text(),j['texts']))
    assert inventories==complete['inventories']==read(attempt/'inventories.json')
    for i,c in enumerate(cases):
        n=i+4;prompt=retention_prompt(c['question'],c['pairs'],inventories[i],c['texts'],c['units'])
        assert prompt==(attempt/f'call-{n:02d}-prompt.txt').read_text()
        assert calls[n]['stage']=='source_scoped_retention_comparison'and calls[n]['case_index']==i
        units=json.loads(prompt.split('\nCOMPLETE ACTUAL SOURCE UNITS:\n',1)[1]);assert units==c['units']
        parsed=parse_retention((attempt/f'call-{n:02d}-response.txt').read_text(),c['pairs'],inventories[i],c['units'])
        results.append(dict(case_index=i,pairs=parsed))
        for pair in parsed:
            statistics.append(dict(case_index=i,pair_id=pair['pair_id'],
                retention_states=dict(collections.Counter(f.get('retention',f.get('status'))for f in pair.get('original_facts',[]))),
                original_support_states=dict(collections.Counter(f.get('source_support',f.get('status'))for f in pair.get('original_facts',[]))),
                candidate_support_states=dict(collections.Counter(f.get('source_support',f.get('status'))for f in pair.get('candidate_facts',[])))))
    assert results==complete['results']
    out=R/'fact-retention-inventory-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
    write(out/'strict-replay-inventories.json',inventories);write(out/'strict-replay-results.json',results)
    write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=6,strict_replay_fresh_calls=0,usage=dict(usage),statistics=statistics,
        inventory_fact_counts=[{r['text_id']:len(r['facts'])for r in group}for group in inventories],
        report_changes=0,whole_report_consistency_assessed=False,independent_correction_credit=0))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=6,usage=dict(usage),statistics=statistics,
        manifests={str(p):seal(p)for p in [R/'fact-retention-inventory-preflight-20261115-v1',root,out]}),ensure_ascii=False))

if __name__=='__main__':main()
