"""Four bounded native confirmations: actual adverse proposal plus counterfactual calibration; no quality credit."""
import argparse,copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from scripts.run_source_view_native_pair_20261115 import prepare
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from research_verify.evidence_flow import confirm_repairs, _review_material, required_sources, document_structure_spans
from research_verify.synthesis_trace import DISABLED
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def jobs():
 case,sources,reports,groups,inputs=prepare();docs=native_documents(sources)
 old=R/'source-view-native-model-20261115-v1/attempt/actual_view_scope';chain=R/'source-view-native-coordinator-handoff-20261115-v1/source9-repair-evidence-chain.json'
 data=read(chain);material=data['first_review_prompt']['actual_supplied_source_material'];report=(old/'original-report.md').read_text()
 issue,=read(old/'result.json')['native_applied'];original_issue=copy.deepcopy(issue)
 group,=[g for g in groups['actual_view_scope'] if issue['claim_id'] in g]
 section='\n'.join(c['text'] for c in group.values());reserve=min(8000,len(json.dumps(document_structure_spans(report),ensure_ascii=False)))
 material,_=_review_material(docs,case['query']+'\n'+section,group,required_sources(section,sources),60000-reserve)
 assert str(material)==data['first_review_prompt']['actual_supplied_source_material']
 line,=[line for line in report.splitlines() if line.startswith('- **FACS分选**：门控为')]
 assert 'CCR3⁺' in line
 wrong=line.replace('CCR3⁺','CCR3⁻');assert wrong!=line
 calibration_report=report.replace(line,wrong);assert calibration_report.count(wrong)==1
 calibration_issue=dict(statement=wrong,replacement=line,source_id=9,status='contradiction',evidence_quote=issue['evidence_quote'])
 cases=[dict(case='observed_proposal',report=report,issue=issue,origin='Actual frozen Writer report and actual harmful native proposal; known diagnostic, not heldout'),
        dict(case='counterfactual_calibration',report=calibration_report,issue=calibration_issue,origin='Evaluator-generated one-marker sign inversion of same report FACS bullet; not original feedback, never counts as report correction')]
 result=[]
 for example in cases:
  for arm in ['selected_context','complete_acquired_context']:
   settings={'citation.confirmation_acquired_context':arm=='complete_acquired_context','citation.confirmation_prompt_chars':60000}
   prompts=[]
   handler=SimpleNamespace(get_setting=lambda k,d=None:settings.get(k,d),_invoke_text=lambda p,**kw:prompts.append(p) or '{"decisions":[]}')
   confirm_repairs(handler,example['report'],[example['issue']],material,case['query'],DISABLED,documents=docs)
   assert len(prompts)==1
   if example['case']=='observed_proposal' and arm=='selected_context':assert prompts[0]==(old/'call-003-prompt.txt').read_text(), ''.join(__import__('difflib').unified_diff((old/'call-003-prompt.txt').read_text().splitlines(True),prompts[0].splitlines(True)))[-2500:]
   result.append(dict(**example,arm=arm,settings=settings,prompt=prompts[0]))
 assert original_issue==issue
 return case,sources,material,result,[*inputs,chain,old/'original-report.md',old/'result.json',old/'call-003-prompt.txt']

def main():
 p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--replay',type=Path);p.add_argument('--preflight',type=Path);a=p.parse_args();assert not(a.execute and a.replay)
 case,sources,material,prepared,inputs=jobs();a.out_dir.mkdir(parents=True,exist_ok=False)
 code=[Path(__file__),Path('scripts/run_source_view_native_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
 frozen={str(p):sha(p) for p in [*inputs,*code]};write(a.out_dir/'prestart-freeze.json',frozen)
 for f in code:
  target=a.out_dir/'code'/f.resolve().relative_to(Path.cwd());target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
 settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':4000,'llm.max_retries':0,'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
 write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=4,settings=settings,confirmation_prompt_chars=60000,
  cases=[{k:v for k,v in j.items() if k not in ['prompt','report','issue']} for j in prepared],
  independent_correction_credit=0,production_deployment=False,writer=False,retrieval=False,full_native_pipeline=False,
  expected_outcomes='Evaluator-only: preserve source-supported original in observed proposal; correct controlled sign inversion in calibration. These expectations are not put into model inputs. Model verdicts remain provisional; counterfactual never counts in denominator.'))
 calls=[];results=[];model=None;failure=None
 for index,job in enumerate(prepared):
  folder=a.out_dir/f'job-{index:02d}';folder.mkdir();trace=Trace(folder/'trace.jsonl');(folder/'original-report.md').write_text(job['report']);write(folder/'issue.json',job['issue'])
  def invoke(prompt,**kwargs):
   nonlocal model
   (folder/'prompt.txt').write_text(prompt);assert prompt==job['prompt'];assert len(prompt)+4000+8192<=131072
   if a.preflight:assert (a.preflight/f'job-{index:02d}/prompt.txt').read_text()==prompt
   row=dict(index=index,case=job['case'],arm=job['arm'],prompt_sha256=sha(folder/'prompt.txt'),status='started');calls.append(row);write(a.out_dir/'calls.json',calls)
   try:
    if a.replay:
     old=a.replay/f'job-{index:02d}';entry=read(a.replay/'calls.json')[index];assert entry['prompt_sha256']==row['prompt_sha256'] and entry['status']=='returned'
     raw=(old/'response.txt').read_text();assert sha(old/'response.txt')==entry['response_sha256'];meta=entry['response_metadata'];row['origin']='strict_replay'
    elif a.execute:
     if model is None:
      from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
      from local_deep_research.config.thread_settings import settings_context
      from local_deep_research.config.llm_config import get_llm
      defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'));effective=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})|settings
      with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
     response=model.invoke(prompt);raw=str(response.content);meta=response.response_metadata;row['origin']='fresh_model'
    else:raw='{"decisions":[]}';meta={};row['origin']='preflight_placeholder'
    (folder/'response.txt').write_text(raw);row.update(status='returned',response_sha256=sha(folder/'response.txt'),response_metadata=meta)
    if a.execute or a.replay:assert meta.get('finish_reason')=='stop'
    return raw
   except Exception as exc:row.update(status='unavailable',error_type=type(exc).__name__);raise
   finally:write(a.out_dir/'calls.json',calls)
  handler=SimpleNamespace(get_setting=lambda k,d=None:job['settings'].get(k,d),_invoke_text=invoke)
  report,applied,unresolved=confirm_repairs(handler,job['report'],[job['issue']],material,case['query'],trace,documents=native_documents(copy.deepcopy(sources)))
  (folder/'native-report.md').write_text(report)
  result=dict(case=job['case'],arm=job['arm'],report_sha256=sha(folder/'native-report.md'),original_report_sha256=sha(folder/'original-report.md'),applied=applied,unresolved=unresolved,report_changed=report!=job['report'],independent_correction_credit=0)
  write(folder/'result.json',result);results.append(result)
  if a.replay:assert result==read(a.replay/f'job-{index:02d}/result.json')
  if calls[-1]['status']!='returned':failure=dict(index=index,status=calls[-1]['status']);break
 unchanged=all(sha(Path(p))==h for p,h in frozen.items())
 write(a.out_dir/'completion.json',dict(status='unavailable' if failure else ('preflight_only' if not(a.execute or a.replay) else 'confirmation_diagnostic_complete'),failure=failure,frozen_inputs_unchanged=unchanged,results=results,independent_correction_credit=0))
 print(json.dumps(dict(calls=len(calls),results=[dict(case=r['case'],arm=r['arm'],report_changed=r['report_changed']) for r in results],failure=failure,frozen_inputs_unchanged=unchanged)))
 if failure or not unchanged:raise SystemExit(2)
if __name__=='__main__':main()
