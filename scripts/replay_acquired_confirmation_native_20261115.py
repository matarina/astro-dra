"""Composed strict native replay using historical exact checks and new fresh confirmation; zero fresh calls."""
import copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from scripts.run_source_view_native_pair_20261115 import prepare
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace,FixedSources
from research_verify.evidence_flow import review_answer
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def main():
 out=R/'acquired-confirmation-native-replay-20261115-v1';out.mkdir(exist_ok=False)
 case,sources,reports,groups,inputs=prepare();old=R/'source-view-native-model-20261115-v1/attempt/actual_view_scope';fresh=R/'acquired-confirmation-model-20261115-v1/attempt/job-01';cache={};paths=[]
 for row in read(old/'calls.json'):
  assert row['status']=='returned';prompt=old/f'call-{row["index"]:03d}-prompt.txt';response=old/f'call-{row["index"]:03d}-response.txt'
  assert sha(prompt)==row['prompt_sha256'] and sha(response)==row['response_sha256'];key=(row['stage'],sha(prompt));assert key not in cache
  cache[key]=dict(prompt=prompt,response=response,origin='historical_native_same_report');paths.extend([prompt,response])
 fp=fresh/'prompt.txt';fr=fresh/'response.txt';row=read(fresh.parent/'calls.json')[1];assert sha(fp)==row['prompt_sha256'] and sha(fr)==row['response_sha256']
 cache[('repair_validation',sha(fp))]=dict(prompt=fp,response=fr,origin='fresh_confirmation_complete_acquired_context');paths.extend([fp,fr])
 code=[Path(__file__),Path('scripts/run_source_view_native_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
 frozen={str(p):sha(p) for p in [*inputs,*paths,*code]};write(out/'prestart-freeze.json',frozen)
 for p in code:
  target=out/'code'/p.resolve().relative_to(Path.cwd());target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
 results=[]
 for arm in ['selected_context','complete_acquired_context']:
  folder=out/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');calls=[];fetcher=FixedSources()
  def invoke(prompt,**kw):
   key=(kw['stage'],hashlib.sha256(prompt.encode()).hexdigest());assert key in cache,('unfrozen_prompt',key)
   item=cache[key];assert prompt==item['prompt'].read_text();index=len(calls)
   (folder/f'call-{index:03d}-prompt.txt').write_text(prompt);(folder/f'call-{index:03d}-response.txt').write_bytes(item['response'].read_bytes())
   calls.append(dict(stage=kw['stage'],prompt_sha256=key[1],response_sha256=sha(item['response']),cached_prompt=str(item['prompt']),cached_response=str(item['response']),origin=item['origin']));write(folder/'calls.json',calls)
   return item['response'].read_text()
  settings={'citation.confirmation_acquired_context':arm=='complete_acquired_context','citation.confirmation_prompt_chars':60000}
  handler=SimpleNamespace(get_setting=lambda k,d=None:settings.get(k,d),_invoke_text=invoke,_create_documents=native_documents)
  arm_sources=copy.deepcopy(sources);report=reports['actual_view_scope'].read_text();budget={'remaining':32}
  revised,docs,applied,unresolved,shown=review_answer(handler,case['query'],report,native_documents(arm_sources),arm_sources,trace,None,1,60000,{'fetcher':fetcher},budget)
  (folder/'native-report.md').write_text(revised)
  if arm=='selected_context':assert revised==(old/'native-report.md').read_text()
  result=dict(arm=arm,scope=__doc__,logical_calls=len(calls),fresh_calls=0,applied=applied,unresolved=unresolved,report_sha256=sha(folder/'native-report.md'),original_report_sha256=sha(reports['actual_view_scope']),retained_exact_original=revised==report,independent_correction_credit=0)
  write(folder/'result.json',result);results.append(result)
 unchanged=all(sha(Path(p))==h for p,h in frozen.items());assert unchanged
 write(out/'completion.json',dict(scope=__doc__,results=results,frozen_inputs_unchanged=unchanged,fresh_calls=0,full_fresh_end_to_end=False,independent_correction_credit=0))
 print(json.dumps([dict(arm=r['arm'],logical_calls=r['logical_calls'],applied=len(r['applied']),unresolved=len(r['unresolved']),retained_exact_original=r['retained_exact_original']) for r in results]))
if __name__=='__main__':main()
