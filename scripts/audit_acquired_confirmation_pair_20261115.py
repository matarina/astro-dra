"""Verify terminal/runtime/frozen code, actual full-context payload and zero-call replay."""
import hashlib,json,subprocess,sys
from pathlib import Path
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def main():
 model=R/'acquired-confirmation-model-20261115-v1';attempt=model/'attempt';launch=read(model/'launch.json');runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
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
 assert sha(R/'confirmation-context-baseline-code-20261115-v1/evidence_flow.py')==sha(R/'source-view-native-model-20261115-v1/attempt/code/local_deep_research/research_verify/evidence_flow.py')
 completion=read(attempt/'completion.json');assert completion['status']=='confirmation_diagnostic_complete' and completion['frozen_inputs_unchanged']
 calls=read(attempt/'calls.json');assert len(calls)==4;usage={};summaries=[]
 for row in calls:
  folder=attempt/f'job-{row["index"]:02d}';assert row['status']=='returned' and row['origin']=='fresh_model'
  assert sha(folder/'prompt.txt')==row['prompt_sha256'] and sha(folder/'response.txt')==row['response_sha256']
  assert (folder/'prompt.txt').read_bytes()==(R/f'acquired-confirmation-preflight-20261115-v1/job-{row["index"]:02d}/prompt.txt').read_bytes()
  assert row['response_metadata']['finish_reason']=='stop'
  for k,v in row['response_metadata'].get('token_usage',{}).items():
   if isinstance(v,int):usage[k]=usage.get(k,0)+v
  if row['arm']=='complete_acquired_context':
   payload=json.loads((folder/'prompt.txt').read_text().split('\nCandidates:\n',1)[1]);registry=payload['source_context_registry'];assert set(registry)=={'9'}
   text=registry['9']['context'];assert len(text)==45562 and 'Cy7' in text and 'Generation of the Donors C and D Datasets' in text
   for c in payload['candidates']:assert c['source_context']['context_ref']=='9'
  result=read(folder/'result.json');assert sha(folder/'native-report.md')==result['report_sha256'];summaries.append({k:result[k] for k in ['case','arm','report_changed','report_sha256']})
 out=R/'acquired-confirmation-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
 write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
 subprocess.run([sys.executable,'scripts/run_acquired_confirmation_pair_20261115.py','--out-dir',str(out/'strict-replay'),'--replay',str(attempt)],check=True)
 write(out/'audit.json',dict(scope=__doc__,fresh_calls=4,strict_replay_fresh_calls=0,model_usage=usage,results=summaries,independent_correction_credit=0,limitations='Known one-source proposal plus generated calibration. Complete context and lossless shared serialization jointly differ; single pair does not isolate their effects or prove robust generalization.'))
 (out/'audit-code.py').write_bytes(Path(__file__).read_bytes());print(json.dumps(dict(calls=4,usage=usage,independent_correction_credit=0)))
if __name__=='__main__':main()
