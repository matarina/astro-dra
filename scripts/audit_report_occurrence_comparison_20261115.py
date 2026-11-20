"""Audit exact report-only replay/integrity; semantic opinions remain unadjudicated."""
import json,subprocess,collections
from pathlib import Path
from scripts.run_related_report_revision_20261115 import R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
 root=R/'report-occurrence-comparison-model-20261115-v1';a=root/'attempt';rr=R/'report-occurrence-comparison-replay-20261115-v1';ra=rr/'attempt'
 runtimes=[]
 for folder in [root,rr]:
  launch=read(folder/'launch.json');rt,=json.loads(subprocess.check_output(['docker','inspect',launch['container']]))
  assert rt['State']['Status']=='exited'and rt['State']['ExitCode']==0 and rt['Image']==launch['image']
  assert rt['Config']['Healthcheck']['Test']==['NONE'];binds=[m for m in rt['Mounts']if m['Type']=='bind']
  assert sum(m['RW']for m in binds)==1 and next(m for m in binds if m['RW'])['Source']==str(folder.resolve())
  for item in read(folder/'readonly-mount-freeze.json'):
   m,=[m for m in binds if m['Destination']==item['destination']];assert not m['RW']and m['Source']==item['source']
   if item['sha256']:assert sha(Path(item['source']))==item['sha256']
  runtimes.append(dict(state=rt['State'],image=rt['Image'],mounts=binds,network=rt['HostConfig']['NetworkMode']))
 assert runtimes[1]['network']=='none'
 for name,h in read(a/'prestart-freeze.json').items():
  p=Path(name)
  if str(p).startswith('/workspace/'):p=Path.cwd()/p.relative_to('/workspace')
  assert sha(p)==h
  try:rel=p.resolve().relative_to(Path.cwd())
  except ValueError:continue
  if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(a/'code'/rel)==h
 c=read(a/'completion.json');rc=read(ra/'completion.json');assert c['status']==rc['status']=='completed_report_occurrences_diagnostic'
 assert c['frozen_inputs_unchanged']and rc['frozen_inputs_unchanged']and c['fresh_calls']==1 and rc['fresh_calls']==0
 for k in ['logical_calls','inventories','comparisons','independent_correction_credit']:assert c[k]==rc[k]
 calls=read(a/'calls.json');replay=read(ra/'calls.json');usage=collections.Counter();assert len(calls)==len(replay)==1
 for i,(row,rrow)in enumerate(zip(calls,replay)):
  assert row['status']=='returned'and row['origin']=='fresh_model'and row['response_metadata']['finish_reason']=='stop'and rrow['origin']=='strict_replay'
  for k in ['stage','prompt_sha256','response_sha256']:assert row[k]==rrow[k]
  for kind in ['prompt','response']:assert sha(a/f'call-{i:02d}-{kind}.txt')==row[f'{kind}_sha256']==sha(ra/f'call-{i:02d}-{kind}.txt')
  usage.update({k:v for k,v in row['response_metadata']['token_usage'].items()if type(v)is int})
 out=R/'report-occurrence-comparison-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
 write(out/'runtime.json',runtimes)
 stats=dict(scope=__doc__,fresh_calls=1,replay_fresh_calls=0,usage=dict(usage),occurrences=len(c['inventories']),
  extracted_facts=sum(len(r['facts'])for r in c['inventories']),rejected_facts=sum(len(r.get('rejected_facts',[]))for r in c['inventories']),unassessed_occurrences=c['comparisons']['unassessed_occurrences'],
  compared_relationships=dict(collections.Counter(r['relationship']for r in c['comparisons']['comparisons'])),
  uncompared_facts=len(c['comparisons']['uncompared_facts']),scientific_outcome_assessed=False,independent_correction_credit=0)
 write(out/'audit.json',stats);(out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
 manifests={str(f):seal(f)for f in [R/'report-occurrence-comparison-preflight-20261115-v1',root,rr,out]}
 hand=R/'report-occurrence-comparison-coordinator-handoff-20261115-v1';hand.mkdir(exist_ok=False);neutral=hand/'assessment-input';neutral.mkdir()
 for name in ['report.txt','question.txt','occurrences.json']:(neutral/name).write_bytes((a/name).read_bytes())
 base=R/'token-index-report-repair-coordinator-handoff-20261115-v1/assessment-input/case-0'
 for name in ['original-report.txt','primary-source.xml','complete-source-units.json']:(neutral/name).write_bytes((base/name).read_bytes())
 write(neutral/'status.json',dict(status='UNASSESSED',report_origin='Actual experimental token-index IF candidate58481chars, original archived58404char report preserved separately',
  model_inputs='Primary source units/XML included ONLY for future review, not used by report-only diagnostic',independent_correction_credit=0))
 write(hand/'fallible-inventories.json',c['inventories']);write(hand/'fallible-consistency-opinions.json',c['comparisons']);write(hand/'execution-evidence.json',dict(manifests=manifests,audit=stats))
 (hand/'README.md').write_text('Goal ACTIVE; new independent correction credit0. Per-occurrence report readings and consistency opinions are not primary truth, useful-retention or new-error adjudication. Known single-source IFcandidate only; uncited occurrences not guaranteed. Neutral original/candidate reports/question/source preserved separately from model opinions. No independent review requested or other-session artifacts modified.\n')
 manifests[str(hand)]=seal(hand);print(json.dumps(dict(audit=stats,manifests=manifests)))
if __name__=='__main__':main()
