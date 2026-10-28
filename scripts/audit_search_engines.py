#!/usr/bin/env python3
"""Read-only live adapter audit; credentials stay inside the selected container.

Run with the host Python. No user databases, engine switches, or research jobs
are modified. The snapshot uses installed defaults plus container environment;
per-user encrypted settings are deliberately outside this audit's scope.
"""
import argparse
import concurrent.futures
import json
import pathlib
import subprocess
import time


WORKER = r'''
import ast, contextlib, importlib, inspect, io, json, os, pathlib, re, signal, socket, sys, time
from urllib.parse import urlsplit
start = time.monotonic()
mode, engine_name, query, budget = sys.argv[1:5]
budget = int(budget)
result = {'engine':engine_name, 'query':query, 'http':[], 'warnings':[]}
if len(sys.argv)>5 and sys.argv[5]:
    for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:os.environ[key]=sys.argv[5]
    result['temporary_process_proxy']=sys.argv[5]
secrets = [v for k,v in os.environ.items() if any(w in k.upper() for w in ['API_KEY','TOKEN','PASSWORD','SECRET']) and len(v)>3]
def clean(value):
    text = str(value)
    for secret in secrets: text = text.replace(secret, '<redacted>')
    text = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?<redacted>', text)
    return text[:700]
class BudgetExpired(BaseException): pass
def alarm(*args): raise BudgetExpired()
signal.signal(signal.SIGALRM, alarm)
signal.alarm(budget)
socket.setdefaulttimeout(18)
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
  try:
    import local_deep_research
    root = pathlib.Path(local_deep_research.__file__).parent
    snapshot = {}
    for f in sorted((root/'defaults').rglob('*.json')):
      try: data=json.loads(f.read_text())
      except (ValueError,OSError): continue
      if isinstance(data,dict):
        for k,v in data.items():
          if isinstance(v,dict) and 'value' in v: snapshot[k]=v['value']
    # Apply only actual settings keys, respecting the value type.
    for k,old in list(snapshot.items()):
      env='LDR_'+k.upper().replace('.','_')
      if env in os.environ:
        raw=os.environ[env]
        try:
          if isinstance(old,bool): val=raw.lower() in ('true','1','yes','on')
          elif isinstance(old,(int,float,list,dict)) or old is None: val=json.loads(raw)
          else: val=raw
        except ValueError: val=raw
        snapshot[k]=val
    from local_deep_research.web_search_engines.engine_registry import ENGINE_REGISTRY
    from loguru import logger
    logger.remove()
    logger.enable('local_deep_research')
    logger.add(lambda msg: result['warnings'].append(clean(msg.record['message'])) if msg.record['level'].no >=30 and len(result['warnings'])<12 else None, level='WARNING')
    if mode=='inventory':
      rows=[]
      for name,entry in ENGINE_REGISTRY.items():
        prefix='search.engine.web.'+name+'.'
        config={k[len(prefix):]:v for k,v in snapshot.items() if k.startswith(prefix)}
        sensitive=lambda k:any(w in k for w in ['api_key','token','password','secret'])
        rows.append({'engine':name,'class':entry.class_name,'configured_in_defaults':bool(config),
          'agent_enabled':os.getenv('LDR_SEARCH_ENGINE_WEB_'+name.upper()+'_AGENT_ENABLED',config.get('agent_enabled')),
          'auto_enabled':os.getenv('LDR_SEARCH_ENGINE_WEB_'+name.upper()+'_USE_IN_AUTO_SEARCH',config.get('use_in_auto_search')),
          'requires_key':config.get('requires_api_key',False),
          'key_present':bool(os.getenv('LDR_SEARCH_ENGINE_WEB_'+name.upper()+'_API_KEY',config.get('api_key',''))),
          'params':{k:('<configured>' if v else '<empty>') if sensitive(k) else v for k,v in config.items() if k.startswith('default_params.')},
          'description':config.get('description','')})
      result={'engines':rows,'root':str(root),'snapshot_source':'installed defaults plus environment; no per-user database', 'proxy_configured':bool(os.getenv('HTTPS_PROXY') or os.getenv('https_proxy'))}
    else:
      import requests
      oldsend=requests.sessions.Session.send
      def send(self,request,**kwargs):
        timeout=kwargs.get('timeout')
        if timeout is None: kwargs['timeout']=18
        elif isinstance(timeout,(float,int)): kwargs['timeout']=min(timeout,18)
        target=urlsplit(request.url)
        event={'host':target.hostname,'path':target.path,'method':request.method}
        t=time.monotonic()
        try:
          response=oldsend(self,request,**kwargs)
          event['status']=response.status_code
          event['content_type']=response.headers.get('content-type','').split(';')[0]
          if target.path=='/search' and response.status_code==200 and 'json' in event['content_type']:
            try:
              data=response.json()
              event['result_count']=len(data.get('results',[]))
              event['unresponsive_engines']=data.get('unresponsive_engines',[])
            except (ValueError,AttributeError): pass
          if response.status_code>=400:
            try:
              body=response.json()
              if isinstance(body,dict): event['detail']=clean({k:v for k,v in body.items() if k in ['error','message','detail','errors','status','statusCode']})
            except (ValueError,TypeError): event['detail']=clean(re.sub('<[^>]+>',' ',response.text[:600]))
          return response
        except Exception as exc:
          event['exception']=type(exc).__name__;event['detail']=clean(exc)
          raise
        finally:
          event['seconds']=round(time.monotonic()-t,3)
          if len(result['http'])<60:result['http'].append(event)
      requests.sessions.Session.send=send
      try:
        import httpx
        old_httpx_send=httpx.Client.send
        def httpx_send(self,request,**kwargs):
          target=urlsplit(str(request.url));t=time.monotonic()
          event={'host':target.hostname,'path':target.path,'method':request.method,'transport':'httpx'}
          try:
            resp=old_httpx_send(self,request,**kwargs);event['status']=resp.status_code
            if resp.status_code>=400:
              try:event['detail']=clean(resp.json())
              except Exception:pass
            return resp
          except Exception as exc:event['exception']=type(exc).__name__;event['detail']=clean(exc);raise
          finally:
            event['seconds']=round(time.monotonic()-t,3)
            if len(result['http'])<60:result['http'].append(event)
        httpx.Client.send=httpx_send
      except ImportError:pass
      snapshot['search.engine.library.enabled']=False
      snapshot['search.tool']=engine_name
      snapshot['search.snippets_only']= mode != 'full'
      snapshot['search.skip_relevance_filter']=True
      from local_deep_research.web_search_engines.search_engine_factory import create_search_engine
      kwargs={'max_results':2,'max_filtered_results':2,'optimize_queries':False,'max_retries':1,'include_full_content':mode=='full','get_full_text':False,'include_full_text':False}
      if engine_name=='pubmed': kwargs['days_limit']=0
      result['stage']='factory'
      if mode=='direct':
        entry=ENGINE_REGISTRY[engine_name]
        module=importlib.import_module('local_deep_research.web_search_engines'+entry.module_path)
        cls=getattr(module,entry.class_name)
        kwargs={k:v for k,v in kwargs.items() if k in inspect.signature(cls.__init__).parameters}
        engine=cls(settings_snapshot=snapshot,**kwargs)
        engine._configure_programmatic_mode(True)
        result['diagnostic_direct_adapter']=True
      else:
        engine=create_search_engine(engine_name,settings_snapshot=snapshot,programmatic_mode=True,**kwargs)
      if engine is None: result['status']='constructor_unavailable'
      else:
        result['stage']='preview'
        previews=engine.run(query) if mode=='pipeline' else engine._get_previews(query)
        result['count']=len(previews or [])
        result['samples']=[{'title':clean(x.get('title',''))[:220],'url':str(x.get('link',x.get('url',''))).split('?')[0][:300], 'snippet_chars':len(str(x.get('snippet','')))} for x in (previews or [])[:2]]
        result['status']='search_ok' if previews else 'empty'
        if mode=='full' and previews:
          result['stage']='full_content'
          items=engine._get_full_content(previews[:1])
          result['content']=[{'title':clean(x.get('title',''))[:150], 'content_type':x.get('content_type'), 'full_content_chars':len(str(x.get('full_content',''))),'content_chars':len(str(x.get('content',''))),'abstract_chars':len(str(x.get('abstract',''))),'text_chars':len(str(x.get('text',''))),'snippet_chars':len(str(x.get('snippet',''))),'keys':list(x)} for x in (items or [])[:1]]
          result['full_search_helper_initialized']=hasattr(engine,'full_search')
          result['llm_supplied']=False
          result['status']='search_and_content_checked'
  except BudgetExpired: result['status']='budget_timeout'
  except Exception as exc: result.update(status='error',exception=type(exc).__name__,detail=clean(exc))
  finally: signal.alarm(0)
result['elapsed_seconds']=round(time.monotonic()-start,3)
print(json.dumps(result,ensure_ascii=False))
'''

QUERIES = {
    'arxiv':'all:"graph neural networks"', 'brave':'PubMed cancer immunotherapy',
    'exa':'cancer immunotherapy clinical trial', 'github':'local-deep-research',
    'google_pse':'cancer immunotherapy', 'mojeek':'cancer immunotherapy',
    'pubmed':'cancer immunotherapy', 'searxng':'cancer immunotherapy clinical trial',
    'serpapi':'cancer immunotherapy', 'tavily':'cancer immunotherapy',
    'tinyfish':'cancer immunotherapy', 'wayback':'https://www.wikipedia.org/',
    'wikinews':'election', 'wikipedia':'Cancer immunotherapy',
    'elasticsearch':'research', 'paperless':'research', 'scaleserp':'cancer immunotherapy',
    'serper':'cancer immunotherapy', 'sofya':'cancer immunotherapy',
    'nasa_ads':'black hole', 'openalex':'cancer immunotherapy',
    'semantic_scholar':'cancer immunotherapy', 'gutenberg':'Pride and Prejudice',
    'openlibrary':'Pride and Prejudice', 'pubchem':'aspirin',
    'stackexchange':'python list comprehension', 'zenodo':'cancer',
    'ddg':'cancer immunotherapy', 'guardian':'cancer',
}


def call(container, mode, engine, query, budget, proxy=''):
    proc = subprocess.run(
        ['docker','exec','-i',container,'/install/.venv/bin/python','-',mode,engine,query,str(budget),proxy],
        input=WORKER,text=True,capture_output=True,timeout=budget+20,
    )
    for line in reversed(proc.stdout.splitlines()):
        try:
            result=json.loads(line)
            result['container']=container
            return result
        except ValueError:
            continue
    return {'container':container,'engine':engine,'status':'worker_failed','exit_code':proc.returncode}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container',required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    parser.add_argument('--engines',nargs='*')
    parser.add_argument('--budget',type=int,default=65)
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--mode',choices=['inventory','preview','full','direct','pipeline'],default='preview')
    parser.add_argument('--query',help='Override the per-engine smoke query')
    parser.add_argument('--proxy',default='',help='Diagnostic override for this worker process only')
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Refusing to overwrite existing evidence: '+str(args.output))
    data={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'container':args.container,'mode':args.mode,'budget_per_engine_seconds':args.budget,'scope':'Installed defaults + container environment; no encrypted account settings; no LLM supplied; real adapter calls in the selected mode; two requested results (some adapters override this from settings). Full mode checks content fields and does not by itself assert article full text.', 'results':[]}
    inventory=call(args.container,'inventory','','',args.budget)
    data['inventory']=inventory
    def save(): args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    save()
    if args.mode=='inventory': return
    names=args.engines or [x['engine'] for x in inventory['engines']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(call,args.container,args.mode,name,args.query or QUERIES[name],args.budget,args.proxy):name for name in names}
        for future in concurrent.futures.as_completed(futures):
            name=futures[future]
            try:result=future.result()
            except Exception as exc:result={'engine':name,'status':'orchestration_error','exception':type(exc).__name__}
            data['results'].append(result)
            save()
            print(json.dumps({k:result[k] for k in ['engine','status','count','elapsed_seconds','exception'] if k in result}),flush=True)
    data['completed_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    save()


if __name__=='__main__': main()
