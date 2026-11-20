"""Observation-only hooks for isolated feedback reproductions; no production install."""
from pathlib import Path
import asyncio,contextvars,gzip,hashlib,inspect,json,logging,os,re,sys,threading,time,traceback
SENSITIVE=re.compile(r'api[_-]?key|authorization|password|secret|credential|access[_-]?token|refresh[_-]?token|cookie',re.I)
class Recorder:
 def __init__(self,root):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.counts={};self.local=threading.local()
  self.secrets=[v for k,v in os.environ.items()if SENSITIVE.search(k)and len(v)>=8]
 def clean(self,v):
  if isinstance(v,dict):return {str(k):'<REDACTED>'if SENSITIVE.search(str(k))else self.clean(x)for k,x in v.items()}
  if isinstance(v,(list,tuple)):return [self.clean(x)for x in v]
  if isinstance(v,str):
   for x in self.secrets:v=v.replace(x,'<REDACTED>')
   v=re.sub(r'\bsk-[A-Za-z0-9_-]{16,}','<REDACTED>',v)
   v=re.sub(r'''(?i)(bearer\s+|api[_-]?key=|access_token=)[^\s&"']+''',r'\1<REDACTED>',v)
   return re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@',r'\1<REDACTED>@',v)
  if v is None or isinstance(v,(bool,int,float)):return v
  if hasattr(v,'model_dump'):return self.clean(v.model_dump(mode='json'))
  return '<unsupported '+type(v).__name__+'>'
 def write(self,p,data):
  p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
  raw=json.dumps(self.clean(data),ensure_ascii=False,indent=2,default=str).encode();tmp=p.with_name(p.name+'.tmp-'+str(threading.get_ident()));tmp.write_bytes(raw);tmp.replace(p)
 def error(self,where):
  try:
   with self.lock:
    with (self.root/'observer-errors.jsonl').open('a')as f:f.write(json.dumps(self.clean({'where':where,'at':time.time(),'traceback':traceback.format_exc()}),ensure_ascii=False)+'\n')
  except Exception:pass
 def folder(self,kind):
  with self.lock:n=self.counts.get(kind,0);self.counts[kind]=n+1
  p=self.root/kind/f'{n:05d}';p.mkdir(parents=True,exist_ok=False);return p
 def frames(self):
  frames=[];f=sys._getframe(2)
  while f and len(frames)<45:
   file=f.f_code.co_filename
   if any(x in file for x in ['/local_deep_research/','/research_verify/','run_model_research.py']):
    row={'file':file,'function':f.f_code.co_name,'line':f.f_lineno}
    for k in ['stage','batch','number','group_no','round_no','query','topic']:
     v=f.f_locals.get(k)
     if isinstance(v,(str,int,float,bool)):row[k]=v
    frames.append(row)
   f=f.f_back
  return frames
 def begin(self,options,kind='provider-io'):
  p=self.folder(kind);self.write(p/'request.json',{k:v for k,v in options.items()if k not in {'extra_headers','timeout'}and type(v).__name__ not in {'Omit','NotGiven'}})
  self.write(p/'receipt.json',{'status':'started','started_unix':time.time(),'thread':threading.current_thread().name,'model':options.get('model'),'stream':options.get('stream',False),'call_stack':self.frames()});return p
 def returned(self,p,value):
  if hasattr(value,'model_dump'):
   self.write(p/'response.json',value.model_dump(mode='json'));self.finish(p,'returned')
  else:self.write(p/'response-type.json',{'type':type(value).__name__})
 def finish(self,p,status,**kw):
  r=json.loads((p/'receipt.json').read_text());r.update(status=status,ended_unix=time.time(),**kw);self.write(p/'receipt.json',r)
 def install(self):
  import openai
  original=openai.resources.chat.completions.Completions.create;rec=self
  def create(client,*args,**options):
   p=None
   try:p=rec.begin(options)
   except Exception:rec.error('provider_begin')
   try:result=original(client,*args,**options)
   except BaseException:
    if p:
     try:rec.write(p/'exception.json',{'traceback':traceback.format_exc()});rec.finish(p,'raised')
     except Exception:rec.error('provider_exception')
    raise
   if p:
    try:
     value=result.parse()if not hasattr(result,'model_dump')and hasattr(result,'parse')else result
     if hasattr(value,'model_dump'):rec.returned(p,value)
     else:setattr(value,'_dra_capture_folder',p)
    except Exception:rec.error('provider_response')
   return result
  openai.resources.chat.completions.Completions.create=create
  original_async=openai.resources.chat.completions.AsyncCompletions.create
  async def acreate(client,*args,**options):
   p=None
   try:p=rec.begin(options)
   except Exception:rec.error('async_provider_begin')
   try:result=await original_async(client,*args,**options)
   except BaseException:
    if p:
     try:rec.write(p/'exception.json',{'traceback':traceback.format_exc()});rec.finish(p,'raised')
     except Exception:rec.error('async_provider_exception')
    raise
   if p:
    try:
     value=result.parse()if not hasattr(result,'model_dump')and hasattr(result,'parse')else result
     if inspect.isawaitable(value):value=await value
     if hasattr(value,'model_dump'):rec.returned(p,value)
     else:setattr(value,'_dra_capture_folder',p)
    except Exception:rec.error('async_provider_response')
   return result
  openai.resources.chat.completions.AsyncCompletions.create=acreate
  stream_iter=openai.Stream.__iter__
  def iterator(stream):
   p=getattr(stream,'_dra_capture_folder',None);chunks=[]
   try:
    for chunk in stream_iter(stream):
     if p:chunks.append(rec.clean(chunk))
     yield chunk
   finally:
    if p:
     try:rec.write(p/'response-chunks.json',chunks);rec.finish(p,'stream_finished',chunks=len(chunks))
     except Exception:rec.error('stream_response')
  openai.Stream.__iter__=iterator
  astream_iter=openai.AsyncStream.__aiter__
  async def aiterator(stream):
   p=getattr(stream,'_dra_capture_folder',None);chunks=[]
   try:
    async for chunk in astream_iter(stream):
     if p:chunks.append(rec.clean(chunk))
     yield chunk
   finally:
    if p:
     try:rec.write(p/'response-chunks.json',chunks);rec.finish(p,'stream_finished',chunks=len(chunks))
     except Exception:rec.error('async_stream_response')
  openai.AsyncStream.__aiter__=aiterator
  from research_verify.synthesis_trace import SynthesisTrace
  original_record=SynthesisTrace.record
  def trace_record(trace,stage,data):
   try:
    with rec.lock:
     p=rec.folder('full-trace');raw=json.dumps(rec.clean(data),ensure_ascii=False,default=str).encode();(p/'data.json.gz').write_bytes(gzip.compress(raw,mtime=0));rec.write(p/'receipt.json',{'at':time.time(),'research_id':trace.research_id,'trace_id':trace.trace_id,'kind':trace.path.name.split('-')[0],'stage':stage,'thread':threading.current_thread().name,'uncompressed_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
   except Exception:rec.error('full_trace')
   return original_record(trace,stage,data)
  SynthesisTrace.record=trace_record
  from local_deep_research.web_search_engines.search_engine_base import BaseSearchEngine
  original_run=BaseSearchEngine.run
  def run(engine,query,*a,**kw):
   p=None;overrides={}
   try:
    p=rec.folder('search-io');rec.write(p/'input.json',{'query':query,'engine':type(engine).__name__,'max_results':getattr(engine,'max_results',None),'max_filtered_results':getattr(engine,'max_filtered_results',None),'batch_size':getattr(engine,'relevance_filter_batch_size',None),'started_unix':time.time(),'call_stack':rec.frames()})
    for method in ['_get_previews','_filter_for_relevance','_get_full_content']:
     orig=getattr(engine,method);overrides[method]=(method in engine.__dict__,orig)
     def wrapped(*args,__orig=orig,__method=method,**kwargs):
      try:rec.write(p/(__method+'-input.json'),{'args':args,'kwargs':kwargs})
      except Exception:rec.error('search_stage_input')
      value=__orig(*args,**kwargs)
      try:rec.write(p/(__method+'-output.json'),value)
      except Exception:rec.error('search_stage_output')
      return value
     setattr(engine,method,wrapped)
   except Exception:rec.error('search_begin')
   try:
    result=original_run(engine,query,*a,**kw)
    if p:
     try:rec.write(p/'output.json',result);rec.write(p/'finish.json',{'ended_unix':time.time(),'count':len(result)if isinstance(result,list)else None})
     except Exception:rec.error('search_output')
    return result
   finally:
    for method,(owned,orig)in overrides.items():
     if owned:setattr(engine,method,orig)
     else:delattr(engine,method)
  BaseSearchEngine.run=run
  from research_verify.source_collection import SourceCollectionMixin
  original_add=SourceCollectionMixin.add_results
  def add(collector,results,engine_name='web'):
   p=None
   try:p=rec.folder('collection-io');rec.write(p/'before.json',{'engine':engine_name,'results':results,'at':time.time()})
   except Exception:rec.error('collection_begin')
   value=original_add(collector,results,engine_name)
   if p:
    try:rec.write(p/'after.json',{'results':results,'added':getattr(value,'added',None),'reused':getattr(value,'reused',None),'excluded':getattr(value,'excluded',None),'unregistered':getattr(value,'unregistered',None),'limit':getattr(value,'limit',None),'at':time.time()})
    except Exception:rec.error('collection_output')
   return value
  SourceCollectionMixin.add_results=add
  return self
 def logging(self):
  rec=self
  class SafeWriter:
   def __init__(self,path):self.f=path.open('a',buffering=1);self.lock=threading.Lock()
   def write(self,s):
    with self.lock:self.f.write(rec.clean(s))
    return len(s)
   def flush(self):self.f.flush()
   def isatty(self):return False
  sys.stdout=SafeWriter(self.root/'stdout.log');sys.stderr=SafeWriter(self.root/'stderr.log')
  from loguru import logger
  logger.remove()
  def sink(message):
   with rec.lock:
    with (rec.root/'runtime.log').open('a')as f:f.write(rec.clean(str(message)))
  logger.add(sink,level='DEBUG',backtrace=False,diagnose=False)
  class SafeHandler(logging.Handler):
   def emit(self,record):
    try:
     with rec.lock:
      with (rec.root/'python-logging.jsonl').open('a')as f:f.write(json.dumps(rec.clean({'at':record.created,'logger':record.name,'level':record.levelname,'message':record.getMessage()}),ensure_ascii=False)+'\n')
    except Exception:rec.error('stdlib_log')
  logging.getLogger().addHandler(SafeHandler());logging.getLogger().setLevel(logging.INFO)
