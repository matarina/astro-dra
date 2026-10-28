"""Matched-material model comparison using installed writing/review interfaces.

CONFIG arrives on stdin. Search/document acquisition is frozen and identical;
only inference calls use the network. Fresh search is tested separately.
"""
import copy
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


def main(config):
    from loguru import logger
    logger.remove()
    os.umask(0o077)
    os.environ.update(config['environment'])
    output=Path('/tmp/model-comparison');output.mkdir(mode=0o700)
    os.environ.update({'LDR_DATA_DIR':str(output/'data'),'LDR_RESEARCH_TRACE_ENABLED':'true',
                       'LDR_RESEARCH_TRACE_DIR':str(output/'traces')})
    import local_deep_research
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.evidence_flow import review_answer
    from research_verify.synthesis_trace import trace_context,start_trace,text_digest,source_snapshot
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig

    defaults=Path(local_deep_research.__file__).parent/'defaults/default_settings.json'
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in json.loads(defaults.read_text()).items()})
    snapshot.update({'llm.request_timeout':120,'llm.max_retries':0})
    (output/'manifest.json').write_text(json.dumps({'model':snapshot['llm.model'],
        'provider':snapshot['llm.provider'],'temperature':snapshot.get('llm.temperature'),
        'max_tokens':snapshot.get('llm.max_tokens'),'writer_prompt_sha256':text_digest(config['writer_prompt']),
        'thinking_request':config.get('thinking','server_default'),
        'frozen_body_sha256':text_digest(config['body']),
        'source_snapshot_sha256':text_digest(json.dumps(config['sources'],ensure_ascii=False,sort_keys=True)),
        'production_flow_sha256':hashlib.sha256(Path(__import__('research_verify.evidence_flow',fromlist=['x']).__file__).read_bytes()).hexdigest(),
        'scope':'Same material and caller; inference model/service changes. All document retrieval frozen; no production state changes.'},indent=2))

    with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:snapshot.get(k,d))):
        raw_model=get_llm(settings_snapshot=snapshot)
        class Counted:
            calls=0
            def invoke(self,prompt):
                self.calls+=1;started=time.monotonic()
                try:
                    options={'extra_body':{'thinking':{'type':config['thinking']}}} if config.get('thinking') else {}
                    result=raw_model.invoke(prompt,**options)
                    meta=getattr(result,'response_metadata',{}) or {}
                    usage=meta.get('token_usage') or {}
                    row={'call':self.calls,'elapsed_s':round(time.monotonic()-started,3),
                        'prompt_sha256':text_digest(prompt),'response_model':meta.get('model_name') or meta.get('model'),
                        'finish_reason':meta.get('finish_reason'),'completion_tokens':usage.get('completion_tokens'),
                        'reasoning_tokens':(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')}
                    return result
                except Exception as exc:
                    row={'call':self.calls,'elapsed_s':round(time.monotonic()-started,3),'error_type':type(exc).__name__}
                    raise
                finally:
                    with (output/'calls.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        model=Counted();summaries=[]

        def run(label,question,body,supplied,write=False):
            started=time.monotonic();begin=model.calls;task='compare-'+label.replace('_','-')+'-'+uuid4().hex
            sources=copy.deepcopy(supplied)
            handler=StandardCitationHandler(model,snapshot)
            class FrozenFetch:
                events=[]
                def article(self,source):
                    return source.get('fetched_content') or (source.get('full_content') if source.get('content_type') in {'full_text','fulltext'} else None)
                def web(self,*args):
                    self.events.append({'status':'frozen_primary_document_not_supplied'})
                    return []
            with trace_context(task),start_trace('model_benchmark') as trace:
                trace.record('input_sources',{'sources':source_snapshot(sources)})
                if write:
                    trace.record('writer_request',{'prompt':config['writer_prompt']})
                    body=handler._invoke_text(config['writer_prompt'],trace=trace,stage='writer')
                trace.record('review_input',{'text':body,'text_sha256':text_digest(body)})
                documents=handler._create_documents(sources)
                final,documents,applied,pending,shown=review_answer(handler,question,body,documents,sources,
                    trace,None,1,200000,{'fetcher':FrozenFetch()},{'remaining':32})
                trace.record('final_response',{'text':final,'text_sha256':text_digest(final)})
                publication=publish_report(final,sources,cfg=VerifyConfig(enable_citation_qc=False))
            directory=output/label;directory.mkdir(mode=0o700)
            (directory/'input.md').write_text(body);(directory/'body.md').write_text(final)
            (directory/'report.md').write_text(publication.content+'\n\n## Sources\n\n'+'\n\n'.join(
                f'[{s.index}] {s.title}\n   URL: {s.url}' for s in publication.sources)+'\n')
            (directory/'review.json').write_text(json.dumps({'applied':applied,'unresolved':pending},ensure_ascii=False,indent=2))
            summary={'label':label,'task_id':task,'model':snapshot['llm.model'],'model_calls':model.calls-begin,
                'completed':True,
                'elapsed_s':round(time.monotonic()-started,3),'applied':len(applied),'unresolved':len(pending),
                'input_sha256':text_digest(body),'output_sha256':text_digest(final),'shown_sources':len(shown)}
            summaries.append(summary)
            (output/'summary.json').write_text(json.dumps(summaries,indent=2));print(json.dumps(summary),flush=True)

        def safe_run(label,*args,**kwargs):
            try:run(label,*args,**kwargs)
            except Exception as exc:
                summary={'label':label,'model':snapshot['llm.model'],'completed':False,'error_type':type(exc).__name__}
                summaries.append(summary)
                (output/'summary.json').write_text(json.dumps(summaries,indent=2));print(json.dumps(summary),flush=True)

        if config.get('run_frozen_report',True):
            safe_run('frozen_report',config['question'],config['body'],config['sources'])
        for case in config['cases']:
            safe_run('case_'+case['id'],case['question'],case['body'],case['sources'])
        if config.get('run_writer',True):
            safe_run('same_prompt_writer',config['question'],'',config['sources'],write=True)


if __name__=='__main__':
    main(CONFIG)
