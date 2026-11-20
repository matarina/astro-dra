"""Prepare/run six unchanged feedback questions in disposable deployed-code containers."""
from pathlib import Path
import argparse,concurrent.futures,datetime,hashlib,html,json,os,re,shutil,subprocess,tempfile,time,gzip
REPO=Path(__file__).resolve().parents[1]
INVENTORY=REPO/'evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json'
PRIOR=REPO/'evaluation/frontier-strategy-20261113/feedback-neuropathy-original-prompt-reproduction-20261115T054349Z'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def inspect_container(name):return json.loads(subprocess.check_output(['docker','inspect',name]))[0]
def prepare():
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');root=REPO/'evaluation/frontier-strategy-20261113'/('all-feedback-original-prompts-'+stamp);root.mkdir()
 ref=inspect_container('local_deep_research-local-deep-research-1');expected=json.loads((PRIOR/'production-source-freeze.json').read_text())
 # Read only installed package files in the existing production process namespace.
 code="from pathlib import Path;import hashlib,json;root=Path('/install/.venv/lib/python3.14/site-packages');d={};\nfor pkg in ['local_deep_research','research_verify']:\n for p in (root/pkg).rglob('*'):\n  if p.is_file()and '__pycache__'not in p.parts and p.suffix!='.pyc':d['runtime-source/'+str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()\nprint(json.dumps(d))"
 live=json.loads(subprocess.check_output(['docker','exec',ref['Id'],'/install/.venv/bin/python','-c',code]))
 assert live==expected,'Production package snapshot changed; copy a new snapshot before launch'
 shutil.copytree(PRIOR/'runtime-source',root/'runtime-source',copy_function=os.link)
 write(root/'production-source-freeze.json',expected);write(root/'production-baseline.json',{'image':ref['Image'],'reference_container_id':ref['Id'],'network':ref['HostConfig']['NetworkMode'],'extra_hosts':ref['HostConfig'].get('ExtraHosts')or[],'installed_package_hashes_match_prior_snapshot':True,'runtime_files':len(expected),'read_only_packages':True,'production_volumes_mounted':False,'deployment_or_restart':False})
 shutil.copyfile(REPO/'scripts/feedback_reproduction_observer_20261115.py',root/'observer.py')
 shutil.copyfile(Path(__file__),root/'coordinator.py')
 inv=json.loads(INVENTORY.read_text());write(root/'feedback-inventory-copy.json',inv)
 settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','general.enable_fact_checking':True,'verify.enable_citation_qc':False,'search.tool':'searxng','search.search_strategy':'langgraph-agent','langgraph_agent.max_unique_sources':500}
 runner=(PRIOR/'run_model_research.py').read_text().replace('    logger.remove()','    # Logging is configured by the isolated observation bootstrap.')
 runner=runner.replace("    snapshot.update(config.get('settings') or {})", "    snapshot.update(config.get('settings') or {})\n    from observer import CURRENT_RECORDER\n    CURRENT_RECORDER.write(Path('/attempt/effective-settings-redacted.json'),snapshot)")
 bootstrap='''from pathlib import Path
import argparse,hashlib,json,os,runpy,sys,time
ROOT=Path('/attempt');os.umask(0o077)
os.environ['LDR_DATA_DIR']='/attempt/results/data'
os.environ['LDR_RESEARCH_TRACE_ENABLED']='true'
os.environ['LDR_RESEARCH_TRACE_DIR']='/attempt/results/traces'
sys.path.insert(0,'/batch')
import observer
r=observer.Recorder(ROOT);observer.CURRENT_RECORDER=r;r.logging();r.install()
p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');args=p.parse_args()
if args.preflight:
 import openai
 from research_verify.synthesis_trace import SynthesisTrace
 with SynthesisTrace('isolated-preflight','observation-self-check')as t:t.record('self_check',{'prompt':'preflight placeholder','reasoning_content':'synthetic observation check; not an evaluation','api_key':'DO_NOT_PERSIST'})
 fake=openai.types.chat.ChatCompletion.model_validate({'id':'preflight-only','object':'chat.completion','created':0,'model':'no-model-called','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'preflight only','reasoning_content':'synthetic field preservation check'}}]})
 folder=r.begin({'model':'no-model-called','messages':[{'role':'user','content':'preflight placeholder'}]});r.returned(folder,fake)
 assert json.loads((folder/'response.json').read_text())['choices'][0]['message']['reasoning_content']=='synthetic field preservation check'
 assert 'DO_NOT_PERSIST'not in ''.join(gzipfile.read_text(errors='ignore')for gzipfile in ROOT.rglob('*.json'))
 r.write(ROOT/'preflight.json',{'status':'passed','fresh_model_calls':0,'fresh_retrieval_calls':0,'sdk_response_identity_unchanged':True,'unknown_reasoning_field_preserved':True,'full_trace_hook_active':True,'search_and_collection_hooks_installed':True,'sensitive_field_redacted':True})
 raise SystemExit(0)
config=json.loads((ROOT/'input.json').read_text());question=(ROOT/'question.txt').read_text()
assert config['question']==question and hashlib.sha256(question.encode()).hexdigest()==config['question_sha256']
try:runpy.run_path('/attempt/run_model_research.py',run_name='__main__',init_globals={'CONFIG':config})
finally:r.write(ROOT/'runner-returned.json',{'at':time.time(),'note':'Runner finally reached; process may still have library cleanup threads.'})
'''
 tasks=[];labels=['immune','rna-qc','tumor-20','diabetes','adipose','xenium']
 for n,(task,label)in enumerate(zip(inv['tasks'],labels),1):
  prompt=task['original_prompt'];assert hashlib.sha256(prompt.encode()).hexdigest()==task['original_prompt_sha256']
  name=f'{n:02d}-{label}-{task["task_id"]}';case=root/name;case.mkdir();(case/'question.txt').write_text(prompt);(case/'run_model_research.py').write_text(runner);(case/'boot.py').write_text(bootstrap)
  config={'environment':{},'question':prompt,'question_sha256':task['original_prompt_sha256'],'task_id':('feedback-'+stamp+'-'+label).replace('_','-'),'settings':settings}
  write(case/'input.json',config);write(case/'original-feedback.json',{'task':task,'issues':[x for x in inv['issues']if x['task_id']==task['task_id']],'scope':'Original allegations are mixed factual, identity, scope, omission, duplicate and unresolved types; no correction verdict assigned.'})
  write(case/'prestart-hash-freeze.json',{'input_files':{f:sha(case/f)for f in ['question.txt','run_model_research.py','boot.py','input.json','original-feedback.json']},'batch_observer_sha256':sha(root/'observer.py'),'runtime_manifest_sha256':sha(root/'production-source-freeze.json'),'inventory_sha256':sha(INVENTORY),'purpose':'Same original user question, fresh full deployed-pipeline execution with observation hooks; no topic rules or changed selection budgets'})
  tasks.append({'case':name,'task_id':task['task_id'],'label':label,'question_sha256':task['original_prompt_sha256']})
 pre=root/'preflight';pre.mkdir();(pre/'boot.py').write_text(bootstrap)
 write(root/'batch-plan.json',{'created_utc':stamp,'cases':tasks,'case_count':6,'max_concurrent_cases':2,'baseline':'Current deployed packages, not new main patches or experimental repair candidate','original_user_prompts_unchanged':True,'fresh_retrieval':True,'latent_reasoning_not_observable':True,'provider_returned_reasoning_preserved':True,'server_gateway_logs_not_in_scope':True,'original_v23_untouched':True,'independent_adjudication':False,'correction_credit':0,'broad_goal_remains_paused':True,'limits':['Current date, live retrieval and generation differ from historical runs','Historical per-user settings snapshot unavailable','Model endpoint label does not freeze actual checkpoint','Observation logs omit credentials; model-returned reasoning is not a causal trace of hidden computation']})
 write(root/'prestart-batch-freeze.json',{'files':{f:sha(root/f)for f in ['observer.py','coordinator.py','batch-plan.json','production-source-freeze.json','production-baseline.json','feedback-inventory-copy.json']},'case_freezes':{t['case']:sha(root/t['case']/'prestart-hash-freeze.json')for t in tasks}})
 print(str(root),flush=True);return root

def launch(root,case,preflight=False):
 ref=inspect_container('local_deep_research-local-deep-research-1');base=json.loads((root/'production-baseline.json').read_text());assert ref['Image']==base['image']
 prefixes=('LDR_','OPENAI_','SEARXNG_','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')
 env=[s for s in ref['Config']['Env']if s.split('=',1)[0].startswith(prefixes)]
 fd,ep=tempfile.mkstemp(prefix='astro-feedback-env-');os.fchmod(fd,0o600)
 stamp=root.name.rsplit('-',1)[-1].lower();name='astro-six-feedback-'+stamp+'-'+('preflight'if preflight else case.name.split('-')[0])
 try:
  with os.fdopen(fd,'w')as f:f.write('\n'.join(env)+'\n')
  cmd=['docker','run','-d','--name',name,'--user',str(os.getuid())+':'+str(os.getgid()),'--network','none'if preflight else base['network'],'--no-healthcheck','--env-file',ep,'--entrypoint','/install/.venv/bin/python','-e','XDG_CONFIG_HOME=/attempt/runtime-config','-e','XDG_CACHE_HOME=/attempt/runtime-cache','-e','PYTHONDONTWRITEBYTECODE=1','-v',str(case)+':/attempt:rw','-v',str(root)+':/batch:ro']
  if not preflight:
   for h in base['extra_hosts']:cmd+=['--add-host',h]
  for pkg in ['local_deep_research','research_verify']:cmd+=['-v',str(root/'runtime-source'/pkg)+':/install/.venv/lib/python3.14/site-packages/'+pkg+':ro']
  cmd += [base['image'],'/attempt/boot.py']+(['--preflight']if preflight else[])
  cid=subprocess.check_output(cmd,text=True).strip();write(case/'launch.json',{'container':cid,'name':name,'started_unix':time.time(),'image':base['image'],'network':'none'if preflight else base['network'],'production_volumes_mounted':False,'preflight':preflight,'case_freeze_sha256':sha(case/'prestart-hash-freeze.json')if not preflight else None});return cid
 finally:os.unlink(ep)

def public_status(case):
 try:
  s=json.loads((case/'results/status.json').read_text());return {k:s.get(k)for k in ['elapsed_s','percent','phase','message']}
 except (FileNotFoundError,json.JSONDecodeError):return {'phase':'initializing'}
def run_case(root,t):
 case=root/t['case'];cid=launch(root,case);print(json.dumps({'event':'started','case':t['label'],'container':cid[:12]},ensure_ascii=False),flush=True);last=None;done_at=None
 while True:
  state=inspect_container(cid)['State'];status=public_status(case);receipts=list((case/'provider-io').glob('*/receipt.json'));returned=0
  for f in receipts:
   try:returned+=json.loads(f.read_text()).get('status')in ['returned','raised','stream_finished']
   except (FileNotFoundError,json.JSONDecodeError):pass
  row={'event':'progress','case':t['label'],'calls':len(receipts),'returned':returned,**status}
  signature=(len(receipts),returned,status.get('phase'),status.get('percent'))
  if signature!=last:print(json.dumps(row,ensure_ascii=False),flush=True);last=signature
  summary=case/'results/summary.json'
  if summary.exists()and(case/'runner-returned.json').exists()and returned==len(receipts):
   if done_at is None:done_at=time.time()
   if state['Status']=='running'and time.time()-done_at>8:
    files={str(f.relative_to(case)):sha(f)for f in (case/'results').iterdir()if f.is_file()};subprocess.run(['docker','stop','--time','5',cid],check=True,capture_output=True);assert all(sha(case/n)==h for n,h in files.items());write(case/'process-cleanup-receipt.json',{'stop_requested_only_after_runner_returned_and_all_model_calls_terminal':True,'core_results_hashes_unchanged':True,'hashes':files,'at':time.time()})
  if state['Status']!='running':
   write(case/'container-exit.json',{k:state[k]for k in ['Status','ExitCode','OOMKilled','StartedAt','FinishedAt']});print(json.dumps({'event':'finished','case':t['label'],'state':state['Status'],'exit':state['ExitCode'],'summary':json.loads(summary.read_text())if summary.exists()else None},ensure_ascii=False),flush=True);return
  time.sleep(12)

def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--run',type=Path);a=p.parse_args()
 if a.prepare:prepare();return
 root=(a.preflight or a.run).resolve()
 if a.preflight:
  case=root/'preflight';cid=launch(root,case,True)
  result=subprocess.check_output(['docker','wait',cid],text=True).strip();print(json.dumps({'preflight_exit':result,'receipt':json.loads((case/'preflight.json').read_text())if(case/'preflight.json').exists()else None}));return
 plan=json.loads((root/'batch-plan.json').read_text());assert json.loads((root/'preflight/preflight.json').read_text())['status']=='passed'
 for t in plan['cases']:
  case=root/t['case'];freeze=json.loads((case/'prestart-hash-freeze.json').read_text());assert all(sha(case/n)==h for n,h in freeze['input_files'].items())
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
  futures=[pool.submit(run_case,root,t)for t in plan['cases']]
  for f in concurrent.futures.as_completed(futures):f.result()
 write(root/'batch-execution-finished.json',{'at':time.time(),'cases':plan['cases'],'note':'Execution receipts only; manual adjudication remains separate.'})
if __name__=='__main__':main()
