"""Terminal/hash/strict-replay and literal source-view audit; no semantic quality score."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def main():
 model=ROOT/'source-view-native-model-20261115-v1';attempt=model/'attempt'
 launch=read(model/'launch.json');runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
 assert runtime['State']['Status']=='exited' and runtime['State']['ExitCode']==0
 assert runtime['Image']==launch['image_id']
 assert runtime['Config']['Healthcheck']['Test']==['NONE']
 assert runtime['HostConfig']['NetworkMode']=='host'
 binds=[m for m in runtime['Mounts'] if m['Type']=='bind'];assert sum(m['RW'] for m in binds)==1
 assert next(m for m in binds if m['RW'])['Source']==str(model.resolve())
 for row in read(model/'readonly-mount-freeze.json'):
  m,=[m for m in binds if m['Destination']==row['destination']];assert not m['RW'] and m['Source']==row['source']
  if row['sha256']:assert sha(Path(row['source']))==row['sha256']
 frozen=read(attempt/'prestart-freeze.json')
 for p,h in frozen.items():
  path=Path(p)
  if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
  assert sha(path)==h
  rel=path.resolve().relative_to(Path.cwd())
  if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
 completion=read(attempt/'completion.json');assert completion['status']=='native_check_complete' and completion['frozen_inputs_unchanged']
 out=ROOT/'source-view-native-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
 write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
 rows=[];total_usage={};exposure=[]
 sourcepack=read(attempt/'actual-source-pack.json');original3=next(s for s in sourcepack if str(s['index'])=='3')['fetched_content']
 # Evaluator-only textual diagnostics. Never enter model prompts or application decisions.
 paragraphs=[p for p in original3.split('\n\n') if ('greater than 10' in p or 'up to 10' in p) and '2 g' in p]
 assert len(paragraphs)==3
 for arm in ['record_scope','actual_view_scope']:
  folder=attempt/arm;calls=read(folder/'calls.json');result=read(folder/'result.json');assert len(calls)==result['model_calls']<=32
  assert sha(folder/'native-report.md')==result['native_report_sha256']
  for c in calls:
   assert c['origin']=='fresh_model' and c['status']=='returned';i=c['index'];prompt=folder/f'call-{i:03d}-prompt.txt';response=folder/f'call-{i:03d}-response.txt'
   assert sha(prompt)==c['prompt_sha256'] and sha(response)==c['response_sha256']
   meta=c['response_metadata'];assert meta['finish_reason']=='stop'
   for k,v in meta.get('token_usage',{}).items():
    if isinstance(v,int):total_usage[k]=total_usage.get(k,0)+v
   rows.append(dict(arm=arm,index=i,stage=c['stage'],prompt_sha256=sha(prompt),response_sha256=sha(response)))
   t=prompt.read_text()
   if c['stage']=='native_check' and 'SUPPLIED SOURCES:\n' in t:
    material=t.split('SUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
    blocks=list(re.finditer(r'^\[(\d+)\]\nTitle:.*?\nBEGIN SOURCE TEXT\n(.*?)\nEND SOURCE TEXT',material,re.M|re.S))
    for m in blocks:
     if m[1]=='3':exposure.append(dict(arm=arm,call_index=i,source_id=3,source_view_sha256=hashlib.sha256(m[2].encode()).hexdigest(),source_view_chars=len(m[2]),quantity_paragraph_exposure=[dict(paragraph_sha256=hashlib.sha256(p.encode()).hexdigest(),exact=p in m[2]) for p in paragraphs],source_excerpt=m[2]))
 subprocess.run([sys.executable,'scripts/run_source_view_native_pair_20261115.py','--out-dir',str(out/'strict-replay'),'--replay',str(attempt)],check=True)
 write(out/'literal-source3-exposure.json',dict(scope='Literal exposure to actual native checks, not entailment/quality adjudication',original_quantity_paragraphs=paragraphs,views=exposure))
 write(out/'audit.json',dict(scope=__doc__,fresh_model_calls=len(rows),model_usage=total_usage,strict_replay_fresh_calls=0,call_hashes=rows,independent_correction_credit=0,original_complete_reports_not_overwritten=True,source3_quantity_conflict_amendment='source3-quantity-scope-amendment-20261115-v2'))
 (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
 print(json.dumps(dict(calls=len(rows),usage=total_usage,source3_views=len(exposure),independent_correction_credit=0)))
if __name__=='__main__':main()
