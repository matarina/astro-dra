"""Terminal and literal-field transport audit; source binding is not semantic adjudication."""
import hashlib,json,subprocess,sys,collections
from pathlib import Path
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def main():
 model=R/'multi-requirement-if-model-20261115-v1';attempt=model/'attempt';launch=read(model/'launch.json');runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
 assert runtime['State']['Status']=='exited' and runtime['State']['ExitCode']==0 and runtime['Image']==launch['image_id']
 assert runtime['Config']['Healthcheck']['Test']==['NONE'] and runtime['HostConfig']['NetworkMode']=='host'
 binds=[m for m in runtime['Mounts'] if m['Type']=='bind'];assert sum(m['RW'] for m in binds)==1
 assert next(m for m in binds if m['RW'])['Source']==str(model.resolve())
 for row in read(model/'readonly-mount-freeze.json'):
  m,=[m for m in binds if m['Destination']==row['destination']];assert not m['RW'] and m['Source']==row['source']
  if row['sha256']:assert sha(Path(row['source']))==row['sha256']
 for p,h in read(attempt/'prestart-freeze.json').items():
  path=Path(p)
  if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
  assert sha(path)==h
  rel=path.resolve().relative_to(Path.cwd())
  if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
 completion=read(attempt/'completion.json');assert completion['status']=='completed_reading_diagnostic' and completion['frozen_inputs_unchanged']
 calls=read(attempt/'calls.json');assert len(calls)==2;usage={};stats=[]
 units=read(R/'request-canonical-if-model-20261114-v1/attempt/source-units.json')
 for index,row in enumerate(calls):
  assert row['status']=='returned' and row['origin']=='fresh_model'
  pp=attempt/f'call-{index:02d}-prompt.txt';rp=attempt/f'call-{index:02d}-response.txt'
  assert sha(pp)==row['prompt_sha256'] and sha(rp)==row['response_sha256']
  assert pp.read_bytes()==(R/f'multi-requirement-if-preflight-20261115-v1/call-{index:02d}-prompt.txt').read_bytes()
  actual_units,consumed=json.JSONDecoder().raw_decode(pp.read_text().split('\nACTUAL SOURCE UNITS:\n',1)[1]);assert actual_units==units
  assert row['response_metadata']['finish_reason']=='stop'
  for k,v in row['response_metadata'].get('token_usage',{}).items():
   if isinstance(v,int):usage[k]=usage.get(k,0)+v
  parsed=completion['results'][index]['parsed'];assert not parsed['rejected_fields']
  fields=parsed['sources'][0]['fields'];keys=[tuple(f[k] for k in ['study','modality','group','quantity_unit','value','unit_id']) for f in fields]
  stats.append(dict(arm=row['arm'],field_rows=len(fields),distinct_exact_observation_records=len(set(keys)),duplicated_exact_records=len(fields)-len(set(keys)),semantic_support='unassessed',fields=fields,unresolved_requirements=parsed['sources'][0]['unresolved_requirements']))
 out=R/'multi-requirement-if-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
 write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
 subprocess.run([sys.executable,'scripts/run_multi_requirement_if_pair_20261115.py','--out-dir',str(out/'strict-replay'),'--replay-attempt',str(attempt)],check=True)
 replay=read(out/'strict-replay/completion.json');assert replay['results']==completion['results']
 write(out/'audit.json',dict(scope=__doc__,fresh_calls=2,strict_replay_fresh_calls=0,model_usage=usage,statistics=stats,independent_correction_credit=0))
 (out/'audit-code.py').write_bytes(Path(__file__).read_bytes());print(json.dumps(dict(calls=2,usage=usage,statistics=[{k:v for k,v in s.items() if k not in ['fields','unresolved_requirements']} for s in stats])))
if __name__=='__main__':main()
