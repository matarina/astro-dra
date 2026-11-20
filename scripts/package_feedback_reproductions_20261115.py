"""Static manual inspection pages and evidence sealing; no scientific adjudication."""
from pathlib import Path
import argparse,collections,datetime,gzip,hashlib,html,json,os,re,tarfile,time,subprocess,importlib.util,shutil
CSS='''body{font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif;color:#24384d;background:#f3f6fa;margin:0}main{max-width:1400px;margin:auto;padding:28px}header,section,.card{background:white;border:1px solid #dbe4ed;border-radius:12px;padding:22px;margin-bottom:20px}h1{margin:0 0 12px;font-size:28px}h2{font-size:20px;margin:0 0 10px}h3{margin:10px 0}a{color:#246899;text-decoration:none}a:hover{text-decoration:underline}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 ui-monospace,monospace;background:#f4f7fa;border-radius:6px;padding:14px;max-height:900px;overflow:auto}details{border-top:1px solid #dce6ed;margin-top:10px;padding-top:10px}summary{cursor:pointer;color:#2c597d}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e1e9f0;text-align:left;padding:9px;vertical-align:top}th{background:#edf3f9}small,.muted{color:#62778b}.scroll{overflow:auto}.pill{padding:3px 8px;border-radius:10px;background:#eaf3f8;color:#27516c;font-size:12px}input{font:inherit;padding:8px;border:1px solid #bfcfdf;border-radius:6px;min-width:260px}code{background:#edf3f8;padding:2px 5px}nav{display:flex;gap:18px;flex-wrap:wrap} .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}.prompt{white-space:pre-wrap;background:#f3f7fb;padding:13px;border-left:3px solid #548bb3}.note{color:#526b80} @media(max-width:650px){main{padding:12px}header,section,.card{padding:15px}h1{font-size:23px}table{min-width:650px}}'''
TITLES={'immune':'免疫细胞分选与单细胞实验','rna-qc':'RNA 质检与测序决策','tumor-20':'肿瘤单细胞与空间组学文献','diabetes':'糖尿病神经病变中文文献','adipose':'脂肪样本空间转录组','xenium':'Xenium 文献'}
STAGES={'main_agent':'主 Agent','subtask_agent':'子研究 Agent','relevance_filter':'相关性筛选','source_selection':'写作选材','source_reading':'写作前原文阅读','writer':'Writer 成文','native_check':'原生核查','repair_confirmation':'修订确认','repair':'局部修订','confirmation':'确认','revision':'修订','model_other':'其他模型调用'}
def escape(v):return html.escape(str(v))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p,default=None):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default

def page(path,title,content):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>'+CSS+'</style><main>'+content+'</main></html>')
def pre(v):return '<pre>'+escape(v if isinstance(v,str)else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
def link(p,label):return '<a href="'+escape(p)+'">'+escape(label)+'</a>'
def has_reasoning_text(v):
 if isinstance(v,str):return bool(v.strip())
 if isinstance(v,list):return any(has_reasoning_text(x)for x in v)
 if isinstance(v,dict):return any(has_reasoning_text(x)for k,x in v.items()if k in ['content','text','summary','reasoning','reasoning_content','thinking'])
 return False

def reasoning_fields(v,path=''):
 rows=[]
 if isinstance(v,dict):
  for k,x in v.items():
   if any(t in k.lower()for t in ['reasoning','thinking']):rows.append({'field':path+'/'+k,'nonempty':has_reasoning_text(x),'value':x})
   rows+=reasoning_fields(x,path+'/'+k)
 elif isinstance(v,list):
  for i,x in enumerate(v):rows+=reasoning_fields(x,path+'/'+str(i))
 return rows

def stage_of(receipt):
 fs=receipt.get('call_stack',[])
 for f in fs:
  if f.get('stage')in ['source_selection','source_reading','writer','native_check','repair_confirmation','repair','confirmation','revision']:return f['stage']
 if any(f['function']=='_run_batch'for f in fs):return 'relevance_filter'
 if any(f['function']=='run_subtask'for f in fs):return 'subtask_agent'
 if any(f['function']=='analyze_topic'for f in fs):return 'main_agent'
 return next((str(f['stage'])for f in fs if f.get('stage')),'model_other')

def package_case(root,t,seal):
 case=root/t['case']
 if seal:
  launch=read(case/'launch.json',{})
  if launch.get('container'):
   spec=importlib.util.spec_from_file_location('batch_redactor',root/'observer.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);redactor=module.Recorder(case)
   config=json.loads(subprocess.check_output(['docker','inspect',launch['container']]))[0]['Config']
   redactor.secrets += [v.split('=',1)[1]for v in config['Env']if '='in v and module.SENSITIVE.search(v.split('=',1)[0])and len(v.split('=',1)[1])>=8]
   logs=subprocess.run(['docker','logs',launch['container']],capture_output=True,text=True)
   (case/'container-stdout.log').write_text(redactor.clean(logs.stdout));(case/'container-stderr.log').write_text(redactor.clean(logs.stderr))
 summary=read(case/'results/summary.json',{});feedback=read(case/'original-feedback.json');question=(case/'question.txt').read_text();events=[];calls=[];rcount=0;nonempty=0;stages=collections.Counter();obs=case/'observer-errors.jsonl';observer_errors=len(obs.read_text().splitlines())if obs.exists()else 0
 for reqpath in sorted((case/'provider-io').glob('*/request.json')):
  folder=reqpath.parent;request=read(reqpath,{});receipt=read(folder/'receipt.json',{});response=read(folder/'response.json',read(folder/'response-chunks.json',None));reasoning=reasoning_fields(response);nonempty+=sum(x['nonempty']for x in reasoning);rcount+=response is not None;stage=stage_of(receipt);stages[stage]+=1
  title='模型调用 '+folder.name+' · '+STAGES.get(stage,stage)+' / '+stage
  body='<header>'+link('../../timeline.html','← 返回本题时间线')+'<h1>'+escape(title)+'</h1><p>时间：'+escape(datetime.datetime.fromtimestamp(receipt.get('started_unix',0),datetime.timezone.utc).isoformat())+' · 状态：'+escape(receipt.get('status'))+' · 线程：'+escape(receipt.get('thread'))+'</p><nav>'+link('request.json','实际 SDK 请求 JSON')+' '+(link('response.json','实际 SDK 返回 JSON')if(folder/'response.json').exists()else link('response-chunks.json','流式返回 chunks')if(folder/'response-chunks.json').exists()else link('exception.json','SDK 调用异常')if(folder/'exception.json').exists()else '尚无返回对象')+' '+link('receipt.json','调用阶段与栈回执')+'</nav></header>'
  body+='<section><h2>模型返回文本 / 工具调用</h2>'
  choices=response.get('choices',[])if isinstance(response,dict)else[]
  if choices:
   for choice in choices:
    msg=choice.get('message',choice.get('delta',{}));body+='<h3>content</h3>'+pre(msg.get('content'))
    if msg.get('tool_calls'):body+='<h3>tool_calls</h3>'+pre(msg['tool_calls'])
  elif response is not None:body+=pre(response)
  else:body+='<p>尚无 SDK 返回对象；查看调用状态。</p>'+pre(read(folder/'exception.json',{}))
  body+='</section><section><h2>服务端经 SDK 返回的 reasoning / thinking 字段</h2><p class="note">仅展示实际返回字段；空值表示本次边界未取得推理文本，不表示模型没有内部计算。显式返回文本也不是隐藏内部计算的完整因果记录。</p>'+pre(reasoning if reasoning else 'SDK 返回对象未包含 reasoning / thinking 字段')+'</section>'
  body+='<section><h2>实际请求消息</h2>'
  for i,m in enumerate(request.get('messages',[])):
   content=m.get('content');body+='<details><summary>'+escape(str(i)+' · '+m.get('role','?')+' · '+str(len(content)if isinstance(content,str)else 0)+' 字符')+'</summary>'+pre(m)+'</details>'
  other={k:v for k,v in request.items()if k!='messages'};body+='<details><summary>工具定义、采样及其余请求参数</summary>'+pre(other)+'</details></section><section><h2>原始返回全部字段</h2><details><summary>展开 SDK response 全部字段</summary>'+pre(response)+'</details></section>'
  page(folder/'inspect.html',title,body)
  events.append({'at':receipt.get('started_unix',0),'kind':'模型 / '+STAGES.get(stage,stage)+' / '+stage,'label':'调用 '+folder.name+' · '+receipt.get('status','unknown'),'href':str((folder/'inspect.html').relative_to(case)),'json':str(reqpath.relative_to(case))});calls.append({'id':folder.name,'stage':stage,'receipt':str((folder/'receipt.json').relative_to(case)),'status':receipt.get('status'),'request_sha256':sha(reqpath),'response_present':response is not None,'reasoning_fields':[{k:x[k]for k in ['field','nonempty']}for x in reasoning]})
 for kind in ['full-trace','search-io','collection-io']:
  for folder in sorted((case/kind).glob('*')):
   if not folder.is_dir():continue
   receipt=read(folder/'receipt.json',{});inp=read(folder/'input.json',{});at=receipt.get('at',inp.get('started_unix',0));stage=receipt.get('stage',inp.get('engine',kind));parts=[]
   for f in sorted(folder.iterdir()):
    if f.name=='inspect.html':continue
    if f.suffix=='.gz':
     try:d=json.loads(gzip.decompress(f.read_bytes()));out=folder/(f.stem);out.write_text(json.dumps(d,ensure_ascii=False,indent=2));continue
     except Exception:continue
   # Enumeration occurs after decompression so plain JSON is directly inspectable.
   for f in sorted(folder.glob('*.json')):
    d=read(f,{});parts.append('<details'+(' open'if f.name in ['receipt.json','input.json','finish.json']else'')+'><summary>'+escape(f.name)+'</summary>'+pre(d)+'</details>')
    if kind=='collection-io'and f.name=='before.json':at=d.get('at',at)
   body='<header>'+link('../../timeline.html','← 返回本题时间线')+'<h1>'+escape(kind+' / '+folder.name+' / '+stage)+'</h1><p>原始数据按边界分别保存，可查看输入、输出与来源编号。</p></header><section>'+''.join(parts)+'</section>'
   page(folder/'inspect.html',kind+' '+folder.name,body)
   events.append({'at':at,'kind':kind,'label':str(stage)+' · '+folder.name,'href':str((folder/'inspect.html').relative_to(case))})
 events.sort(key=lambda x:x['at']);rows=''.join('<tr><td>'+escape(datetime.datetime.fromtimestamp(e['at'],datetime.timezone.utc).strftime('%H:%M:%S.%f')[:-3]if e['at']else'—')+'</td><td>'+escape(e['kind'])+'</td><td>'+link(e['href'],e['label'])+'</td></tr>'for e in events)
 findings=feedback['issues'];issuebody=''.join('<details><summary>'+escape(x['issue_id']+' · '+x.get('category',''))+'</summary>'+pre(x)+'</details>'for x in findings)
 logs=[]
 for p in sorted(case.rglob('*')):
  if p.is_file()and(p.suffix=='.log'or p.name in ['python-logging.jsonl','observer-errors.jsonl','effective-settings-redacted.json','container-exit.json','process-cleanup-receipt.json']):logs.append(link(str(p.relative_to(case)),str(p.relative_to(case))))
 header='<header>'+link('../index.html','← 六题总索引')+'<h1>'+escape(TITLES[t['label']]+' · 原题复现检查')+'</h1><div class="prompt">'+escape(question)+'</div><p>任务：'+escape(t['task_id'])+' · prompt SHA256：<code>'+escape(t['question_sha256'])+'</code></p><nav>'+link('results/report.md','最终报告')+' '+link('results/sources.json','完整来源池')+' '+link('original-feedback.json','原始反馈及条目')+' '+link('prestart-hash-freeze.json','启动冻结')+' '+link('case-audit.json','完成审计')+'</nav></header>'
 reviewnote='<section><h2>建议检查顺序</h2><p>先对照原始反馈和最终报告，再沿时间线回查：检索候选 → 相关性筛选 / 数量截断 → 来源登记前后 → 主 Agent 的实际 tool 消息 → 草稿 → Writer 实际材料 / 阅读索引 → Writer 返回 → 核查及修订 → 最终正文。</p><p class="note">只依据文本实际出现的位置判断阶段。候选出现、编号被选择、登记成功、进入模型请求和进入报告是不同状态。原始反馈包含不同证据类型，本页不自动判断是否复现、纠正或产生新错误。</p></section>'
 body=header+reviewnote+'<section><h2>执行状态与日志覆盖</h2>'+pre({'summary':summary,'captured_provider_requests':len(calls),'captured_provider_responses':rcount,'nonempty_returned_reasoning_fields':nonempty,'stages':dict(stages),'observer_error_count':observer_errors})+'</section><section><h2>运行日志与配置</h2><nav>'+' · '.join(logs)+'</nav></section><section><h2>原始反馈条目</h2>'+issuebody+'</section><section><h2>按时间排列的模型调用与处理边界</h2><p><input id="filter" placeholder="筛选：writer / main_agent / search…" aria-label="筛选时间线"></p><div class="scroll"><table id="timeline"><thead><tr><th>UTC 时间</th><th>阶段</th><th>记录</th></tr></thead><tbody>'+rows+'</tbody></table></div></section><script>document.getElementById("filter").oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#timeline tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))}</script>'
 page(case/'timeline.html',t['label']+' 原题复现检查',body)
 audit={'case':t['case'],'question_matches_inventory':question==feedback['task']['original_prompt'],'question_sha256_matches':sha(case/'question.txt')==t['question_sha256'],'summary':summary,'provider_request_count':len(calls),'provider_response_count':rcount,'nonempty_returned_reasoning_field_count':nonempty,'observer_error_count':observer_errors,'model_calls':calls,'stage_counts':dict(stages),'source_search_count':len(list((case/'search-io').glob('*/input.json'))),'uncapped_full_trace_count':len(list((case/'full-trace').glob('*/receipt.json'))),'collection_boundary_count':len(list((case/'collection-io').glob('*/before.json'))),'correction_credit':0,'independent_adjudication_performed':False,'logging_limits':['No hidden internal thoughts beyond provider-returned fields','No upstream gateway/inference-server logs','Credentials redacted','Recorded execution is not an accuracy verdict']}
 original_events=[]
 for eventfile in (case/'results/traces').rglob('events.jsonl'):
  original_events += [json.loads(line)for line in eventfile.read_text().splitlines()if line.strip()]
 audit['application_trace_event_count']=len(original_events)
 audit['application_trace_size_omissions']=sum(x.get('status')=='omitted_size_limit'for x in original_events)
 audit['uncapped_copy_count_matches_application_events']=audit['uncapped_full_trace_count']==len(original_events)
 audit['model_request_terminal_statuses']=dict(collections.Counter(x['status']for x in calls))
 if seal:
  assert audit['uncapped_copy_count_matches_application_events'],'Uncapped trace copy/event count mismatch'
  freeze=read(case/'prestart-hash-freeze.json');audit['frozen_input_hash_mismatches']=[n for n,h in freeze['input_files'].items()if sha(case/n)!=h];audit['observer_matches_freeze']=sha(root/'observer.py')==freeze['batch_observer_sha256'];assert not audit['frozen_input_hash_mismatches']and audit['observer_matches_freeze'];assert audit['question_matches_inventory']and audit['question_sha256_matches']
  actualfirst=read(next(iter(sorted((case/'provider-io').glob('*/request.json')))),{})if calls else{};audit['first_model_request_has_exact_original_user_message']=any(x.get('content')==question for x in actualfirst.get('messages',[]))
 write= lambda p,x:p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');write(case/'case-audit.json',audit)
 if seal:
  manifest={str(p.relative_to(case)):sha(p)for p in sorted(case.rglob('*'))if p.is_file()and not any(x in p.relative_to(case).parts for x in ['runtime-config','runtime-cache'])and p.name!='completion-hash-manifest.json'};write(case/'completion-hash-manifest.json',{'files':manifest,'created_unix':time.time()})
 return audit

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--seal',action='store_true');p.add_argument('--archive',action='store_true');args=p.parse_args();root=args.root.resolve()
 if args.seal:
  shutil.copyfile(Path(__file__),root/'review-packager.py')
  shutil.copyfile(Path(__file__).with_name('find_feedback_reproduction_text_20261115.py'),root/'find_text.py')
 plan=read(root/'batch-plan.json');audits=[package_case(root,t,args.seal)for t in plan['cases']];cards=[]
 for t,a in zip(plan['cases'],audits):
  status='已完成研究流程'if a['summary'].get('completed')and not a['summary'].get('research_error')else('执行返回错误'if a['summary']else'执行中 / 待执行')
  cards.append('<div class="card"><h2>'+escape(TITLES[t['label']])+' <span class="pill">'+status+'</span></h2><p>'+escape(read(root/t['case']/'original-feedback.json')['task']['original_prompt'])+'</p><p>'+str(a['provider_request_count'])+' 次模型请求 · '+str(a['provider_response_count'])+' 份返回 · '+str(a['summary'].get('source_pool','—'))+' 个来源 · '+str(a['summary'].get('references','—'))+' 条参考文献</p><nav>'+link(t['case']+'/timeline.html','打开完整检查时间线')+' '+link(t['case']+'/results/report.md','最终报告')+'</nav></div>')
 archive_link=('<p>'+link('../'+root.name+'-manual-review.tar.gz','下载完整检查包 tar.gz')+' · '+link('../'+root.name+'-manual-review.tar.gz.sha256','压缩包 SHA256')+'</p>')if args.archive else''
 body='<header>'+archive_link+'<h1>六道反馈原题 · 完整流程检查包</h1><p>批次：'+escape(root.name)+'</p><p>当前部署代码的隔离复现，保留六条原始用户 prompt，重新实时检索。使用程序化研究入口，报告本地保存，未经过生产登录与账号数据库。原生一致性检查开启，保存前逐引用 QC 关闭；检索及写作预算沿用当前配置。</p><p class="note">历史日期、检索材料、账号设置和模型底层版本不保证相同；本次使用独立配置与缓存，没有复制生产账号数据库或缓存。推理栏仅包含经 SDK 返回的显式 reasoning / thinking 字段；未返回的隐藏内部推理无法补录。上游网关/推理服务器日志不在本包范围。反馈条目与本轮报告的正确性需人工按原始来源检查，本包没有自动裁决。</p><nav>'+link('batch-plan.json','执行计划及限制')+' '+link('batch-audit.json','批次完成审计')+' '+link('production-source-freeze.json','部署代码哈希')+' '+link('prestart-batch-freeze.json','启动冻结')+' '+link('README.md','检查说明')+'</nav></header><div class="cards">'+''.join(cards)+'</div>'
 page(root/'index.html','六题原始 prompt 复现检查包',body)
 readme='''# 六道反馈原题复现检查包

打开 index.html，再进入各题 timeline.html。页面离线可用，模型调用及处理边界都链接到独立 inspect.html 和原始 JSON。

需要跨阶段查找某个词时，在本目录运行 `python find_text.py "待查词" --case "任务目录的一部分"`。它只检索已保存的实际文本并给出上下文与检查页面路径，不调用模型，也不判定事实正确性。`--max-files` 可调整显示数量。

检查路径：原始反馈 → 最终报告 → 检索预览 / 筛选输入输出 → 来源登记前后 → 实际主 Agent 请求中的 tool 消息 → 草稿 → Writer 材料与返回 → 原生核查 / 补证 / 修订 → 最终正文 / Publication。

provider-io 保存实际 SDK 请求、完整 SDK 返回及调用栈；包括服务端显式返回的 reasoning 字段（如有）。full-trace 为额外无大小截断的处理事件副本；results/traces 为应用原生 trace。search-io 和 collection-io 分别记录候选/过滤/内容获取及登记前后。runtime.log、stdout.log、stderr.log 和 python-logging.jsonl 记录可获取的本进程日志。请求中的鉴权字段及已知凭据被脱敏；未读取上游检索服务器、网关或推理服务器内部日志。

preflight/ 仅为断网的日志自检，含明确标记的模拟字段，不属于六题真实模型执行，也不计入模型调用或 reasoning 统计。人工批注建议另存 manual-notes.md，不修改原始证据文件。

本次使用程序化研究入口和当前已部署包的只读快照，报告保存在本地，不经过生产登录与账号数据库；不是 GitHub 最初原版，也不是未部署修复候选。保持原题，没有添加争议术语、答案提示或题目专用规则。实时检索、时间、历史账号设置和模型底层版本可能不同；隔离任务使用独立配置和缓存，不复制生产账号数据库或缓存，因此不是历史请求逐字重放。运行库缓存不打入检查压缩包；实际检索返回、来源材料和模型阅读输入均单独保存。

completion-hash-manifest.json / batch-completion-hashes.json 为完成时 SHA256。原始反馈保持混合证据类别；没有进行本轮独立原始来源裁决、有用内容保留或新增错误评估，纠正计数为0。运行结束不代表幻觉问题已解决。
''';(root/'README.md').write_text(readme)
 batch={'cases':audits,'execution_completed_without_research_error':sum(bool(a['summary'].get('completed'))and not a['summary'].get('research_error')for a in audits),'provider_requests':sum(a['provider_request_count']for a in audits),'provider_responses':sum(a['provider_response_count']for a in audits),'nonempty_returned_reasoning_fields':sum(a['nonempty_returned_reasoning_field_count']for a in audits),'observer_errors':sum(a['observer_error_count']for a in audits),'correction_credit':0,'independent_adjudication':False}
 if args.seal:
  expected=read(root/'production-source-freeze.json');batch['runtime_hash_mismatches']=[n for n,h in expected.items()if sha(root/n)!=h];freeze=read(root/'prestart-batch-freeze.json');batch['batch_input_hash_mismatches']=[n for n,h in freeze['files'].items()if sha(root/n)!=h];batch['case_freeze_hash_mismatches']=[n for n,h in freeze['case_freezes'].items()if sha(root/n/'prestart-hash-freeze.json')!=h];assert not any(batch[k]for k in ['runtime_hash_mismatches','batch_input_hash_mismatches','case_freeze_hash_mismatches'])
 (root/'batch-audit.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
 if args.seal:
  hashes={str(p.relative_to(root)):sha(p)for p in sorted(root.rglob('*'))if p.is_file()and not any(x in p.relative_to(root).parts for x in ['runtime-config','runtime-cache'])and p.name!='batch-completion-hashes.json'};(root/'batch-completion-hashes.json').write_text(json.dumps({'files':hashes,'created_unix':time.time()},indent=2)+'\n')
 if args.archive:
  out=root.with_name(root.name+'-manual-review.tar.gz')
  with tarfile.open(out,'w:gz',compresslevel=5)as tar:
   def fil(info):return None if any(x in Path(info.name).parts for x in ['runtime-config','runtime-cache'])else info
   tar.add(root,arcname=root.name,filter=fil)
  out.with_suffix(out.suffix+'.sha256').write_text(sha(out)+'  '+out.name+'\n')
 print(json.dumps({'index':str(root/'index.html'),'complete':batch['execution_completed_without_research_error'],'calls':batch['provider_requests'],'responses':batch['provider_responses'],'nonempty_reasoning_fields':batch['nonempty_returned_reasoning_fields'],'observer_errors':batch['observer_errors']},ensure_ascii=False))
if __name__=='__main__':main()
