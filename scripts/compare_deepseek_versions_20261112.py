"""Frozen writer and evidence-comprehension comparison; credentials stay external."""
import argparse, concurrent.futures, gzip, hashlib, json, time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/deepseek-version-comparison-20261112'
CREDENTIALS=Path('/data1/maxw/.local/state/dra-model-comparison/credentials-20261112.json')

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def prepare():
    inputs=OUT/'inputs'; inputs.mkdir(parents=True,exist_ok=True)
    base=ROOT/'evaluation/archive-prompt-method-candidate-20261112/results'
    tasks=[]
    for name,suffix in [('immune','47c54edcc0eb'),('adipose','a9b2517baf83'),('xenium','6e8e8d113e76')]:
        files=sorted(base.glob('*'+suffix+'/traces/**/*writer_request.json.gz'))
        if len(files)!=1: raise ValueError((name,len(files)))
        prompt=json.loads(gzip.decompress(files[0].read_bytes()))['prompt']
        (inputs/(name+'.txt')).write_text(prompt)
        tasks.append({'id':name,'kind':'historical_writer_prompt','source':str(files[0].relative_to(ROOT)), 'input_sha256':digest(prompt),'chars':len(prompt)})
    sources=json.loads((ROOT/'evaluation/fixed-source-role-20261112/case2-sources.json').read_text())
    lookup={str(s['index']):s for s in sources}
    questions=[
      ('D1','35','这篇材料中的PBG I–IV是否均已被形态学确认是嗜碱性粒细胞？哪些群体在IgE交联或IL-3刺激后CD203c增加？说明检测方法和供体数。'),
      ('D2','40','CD16阴性选择能否完整保留这里研究的抑制性嗜酸性粒细胞？中和galectin-10是否完全消除了抑制作用？给出依据。'),
      ('D3','43','文中是谁的T细胞增殖支持能力下降、谁上调Bcl2？这些观察属于人还是小鼠，能否当成人细胞已验证的结果？'),
      ('D4','54','IL-5缺失/中和对嗜酸性粒细胞成熟有什么影响？IRF8在文中是否被证明是嗜酸性粒细胞生成的内在必要条件？区分扩增与成熟。'),
      ('D5','81','该研究使用哪种单细胞方法？是否通过无偏聚类识别了明确亚群？CPA3 mRNA在所有细胞高表达能否证明CPA3蛋白也在所有细胞高表达？'),
      ('D6','31','这篇研究的受试者、样本量和检测方法是什么？能否称其为10x平台单细胞RNA测序研究，并把体外CD4/CD8效应推广为体内效果？'),
      ('D7','36','仅依据这份摘要，列出组织来源、起始组织量、获得细胞数量、纯度和活力（若未给出则标缺失），并给出具体FACS分选抗体面板。不要用外部知识补足。'),
      ('D8','33','列出这份材料实际涉及的物种和组织。它是否直接证明同一方案可用于人类四种免疫细胞的单细胞转录组？提供其具体抗体面板，若材料未给出应明确说明。'),
    ]
    items=[]
    for ident,index,q in questions:
        s=lookup[index]
        items.append({'id':ident,'question':q,'source':{'source_id':index,'title':s.get('title'),'pmid':s.get('pmid'),'doi':s.get('doi'),'reading_scope':'complete supplied abstract; full paper not supplied','text':s.get('abstract') or ''}})
    save(inputs/'diagnostic-sources.json',items)
    prompt='''Use ONLY the supplied abstract for each question. Answer in Chinese and keep the source's species, subjects, conditions and uncertainty. Do not infer absent methods from general knowledge. For each item return its id, a concise answer, and an exact English source quotation supporting the answer; if evidence is absent, state that explicitly. Missing evidence in an abstract does not mean the full paper lacks it. Return one JSON object with an "answers" array. Do not omit an item.\n\n'''+json.dumps(items,ensure_ascii=False)
    (inputs/'diagnostic.txt').write_text(prompt)
    tasks.append({'id':'diagnostic','kind':'eight_source_grounded_questions','source':'evaluation/fixed-source-role-20261112/case2-sources.json','input_sha256':digest(prompt),'chars':len(prompt)})
    manifest={'scope':'Current third-party deepseek-v4-flash deployment versus official deepseek-flash. Gateway underlying checkpoint not independently verified. Frozen writer-stage replay, not a full DRA run. Diagnostic questions based on archived real abstracts; exploratory, not held-out medical benchmark.','assessment_plan':'Review eight predefined diagnostic answers against supplied original abstracts; separately inspect the three historical writer replays for evidence errors and omissions. Do not infer whole-report hallucination rate from selected claims, structural counts or this small sample. Repeat diagnostic pair if differences or ambiguity warrant it.','controls':{'temperature':0,'max_tokens':6000,'thinking':{'type':'disabled'},'messages':'one identical user message per task','live_retrieval':False,'native_review':False,'writer_input_equal':True,'task_timeout_s':480,'automatic_retry':False},'tasks':tasks,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(OUT/'manifest.json',manifest)
    return tasks

def run_task(task,provider,repeat='1',max_tokens=6000):
    config=json.loads(CREDENTIALS.read_text())[provider]
    ident=task['id']; prompt=(OUT/'inputs'/(ident+'.txt')).read_text()
    assert digest(prompt)==task['input_sha256']
    directory=OUT/'responses'/provider/(ident+'-'+repeat);directory.mkdir(parents=True,exist_ok=True)
    if (directory/'summary.json').exists(): raise FileExistsError(directory)
    payload={'model':config['model'],'messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':max_tokens,'thinking':{'type':'disabled'}}
    row={'task':ident,'provider':provider,'repeat':repeat,'input_sha256':digest(prompt),'requested_model':config['model'],'request_controls':{'temperature':0,'max_tokens':max_tokens,'thinking':{'type':'disabled'}},'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'running'}
    save(directory/'summary.json',row);started=time.monotonic()
    try:
        r=requests.post(config['base_url'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+config['api_key']},json=payload,timeout=(20,480),allow_redirects=False)
        row['http_status']=r.status_code
        if r.status_code!=200:
            row['status']='http_error'
            try:row['error_type']=(r.json().get('error') or {}).get('type')
            except (ValueError,AttributeError):pass
        else:
            data=r.json();choice=(data.get('choices') or [{}])[0];msg=choice.get('message') or {}
            content=msg.get('content') or ''
            # Keep response fields needed for audit; never serialize request headers/configuration.
            receipt={k:data.get(k) for k in ['id','created','model','system_fingerprint','usage','choices']}
            save(directory/'response.json',receipt);(directory/'report.md').write_text(content)
            row.update(status='completed' if choice.get('finish_reason')=='stop' and content.strip() else 'incomplete',response_model=data.get('model'),system_fingerprint=data.get('system_fingerprint'),finish_reason=choice.get('finish_reason'),usage=data.get('usage'),output_chars=len(content),has_reasoning_content=bool(msg.get('reasoning_content')),output_sha256=digest(content))
    except Exception as e:row.update(status='error',error_type=type(e).__name__)
    row['elapsed_s']=round(time.monotonic()-started,3);save(directory/'summary.json',row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--tasks',nargs='+');ap.add_argument('--repeat',default='1');ap.add_argument('--max-tokens',type=int,default=6000);args=ap.parse_args()
    tasks=prepare() if args.prepare else json.loads((OUT/'manifest.json').read_text())['tasks']
    if args.prepare and not args.tasks:
        print(json.dumps(tasks,ensure_ascii=False));return
    tasks=[t for t in tasks if not args.tasks or t['id'] in args.tasks]
    # Two concurrent calls; cap demand on shared inference service.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run_task,t,p,args.repeat,args.max_tokens) for t in tasks for p in ('current','official')]
        for f in concurrent.futures.as_completed(futures): f.result()

if __name__=='__main__': main()
