"""Preserve truncated terminal response and literal COMPLETE prefix objects for forensic reading only."""
import json,subprocess,hashlib
from pathlib import Path
from scripts.run_related_report_revision_20261115 import R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.report_occurrences import parse_comparisons

def main():
 root=R/'report-occurrence-comparison-model-20261115-v1';a=root/'attempt';rt,=json.loads(subprocess.check_output(['docker','inspect',read(root/'launch.json')['container']]))
 assert rt['State']['Status']=='exited'and rt['State']['ExitCode']==2
 complete=read(a/'completion.json');assert complete['status']=='unavailable'and complete['fresh_calls']==1 and complete['frozen_inputs_unchanged']
 row,=read(a/'calls.json');assert row['response_metadata']['finish_reason']=='length'and row['status']=='unavailable'
 for kind in ['prompt','response']:assert sha(a/f'call-00-{kind}.txt')==row[kind+'_sha256']
 for name,h in read(a/'prestart-freeze.json').items():
  p=Path(name)
  if str(p).startswith('/workspace/'):p=Path.cwd()/p.relative_to('/workspace')
  assert sha(p)==h
  try:rel=p.resolve().relative_to(Path.cwd())
  except ValueError:continue
  if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(a/'code'/rel)==h
 raw=(a/'call-00-response.txt').read_text();cursor=raw.index('[',raw.index('"comparisons"'))+1;decoder=json.JSONDecoder();objects=[];end_reason=None
 while cursor<len(raw):
  while cursor<len(raw)and raw[cursor].isspace():cursor+=1
  if cursor<len(raw)and raw[cursor]==',':cursor+=1;continue
  if cursor<len(raw)and raw[cursor]==']':end_reason='array_end';break
  start=cursor
  try:obj,cursor=decoder.raw_decode(raw,cursor)
  except json.JSONDecodeError:end_reason='incomplete_json_object';break
  literal=raw[start:cursor]
  try:bound=parse_comparisons(json.dumps(dict(comparisons=[obj])),complete['inventories'])['comparisons'][0];error=None
  except (ValueError,TypeError,KeyError)as exc:bound=None;error=type(exc).__name__
  objects.append(dict(response_start=start,response_end=cursor,literal_sha256=hashlib.sha256(literal.encode()).hexdigest(),raw_object=obj,bound=bound,binding_error=error))
 out=R/'report-occurrence-comparison-failure-audit-20261115-v1';out.mkdir(exist_ok=False)
 write(out/'complete-prefix-objects.json',dict(scope='Forensic complete JSON objects ONLY, NOT a complete accepted comparison result. No closing syntax invented or original attempt relabelled.',objects=objects,end_reason=end_reason,independent_correction_credit=0))
 write(out/'audit.json',dict(scope=__doc__,state=rt['State'],fresh_calls=1,replay_fresh_calls=0,finish_reason='length',usage=row['response_metadata']['token_usage'],
  frozen_inputs_and_codecopies_verified=True,complete_prefix_objects=len(objects),bound_prefix_objects=sum(o['bound']is not None for o in objects),end_reason=end_reason,
  accepted_complete_semantic_result=False,independent_correction_credit=0))
 (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
 print(json.dumps(dict(audit=read(out/'audit.json'),manifests={str(p):seal(p)for p in [R/'report-occurrence-comparison-preflight-20261115-v1',root,out]})))
 for o in objects:
  if o['bound']and o['bound']['relationship']=='conflict':print(json.dumps(dict(refs=o['bound']['fact_refs'],reason=o['bound']['reason']),ensure_ascii=False))
if __name__=='__main__':main()
