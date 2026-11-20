"""Cached actual canonical-field Writer through enabled native consistency.

Preflight uses labelled placeholders, never semantic approval. New checks are
allowed only after an exact current preflight proves all prompts fit60000chars.
No reader/Writer resampling or live evidence fetch.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from research_verify import evidence_flow
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--preflight-attempt',type=Path);p.add_argument('--complete-prompt-budget',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    root=Path('evaluation/frontier-strategy-20261113')
    writer=root/'canonical-immune-writer-compact-model-20261115-v1/attempt'
    prior=root/'immune-questioned-fact-model-20261115-v1/attempt'
    casepath=root/'immune-questioned-fact-inputs-20261115-v1/case-manifest.json';case=read(casepath)['cases'][0]
    old=read(prior/'plan.json');settings=dict(old['settings']);
    if a.complete_prompt_budget:settings['citation.bound_complete_review_prompt']=True
    assert settings['general.enable_fact_checking']and not settings['verify.enable_citation_qc']and settings['citation.max_review_calls']==16
    assert read(writer/'completion.json')['status']=='completed_writer_stage'
    sourcepath=Path(case['source']);draftpath=Path(case['draft']);assert sha(sourcepath)==case['source_sha256']and sha(draftpath)==case['draft_sha256']
    sources=read(sourcepath);draft=draftpath.read_text()
    wc=read(writer/'calls.json')[-1];assert wc['stage']=='writer'and wc['origin']=='fresh_model'
    wp=writer/f"call-{wc['index']:02d}-prompt.txt";wr=writer/f"call-{wc['index']:02d}-response.txt"
    assert sha(wp)==wc['prompt_sha256']and sha(wr)==wc['response_sha256']and wr.read_bytes()==(writer/'candidate-report.md').read_bytes()
    prefix=root/'section-writer-model-20261115-v1/attempt/native-writer-prefix.txt'
    first=next(c for c in read(prior/'calls.json')if c['arm']=='candidate'and c['stage']=='source_reading')
    rp=prior/f"call-{first['index']:02d}-prompt.txt";rr=prior/f"call-{first['index']:02d}-response.txt"
    assert sha(rp)==first['prompt_sha256']and sha(rr)==first['response_sha256']
    files=[Path(__file__).resolve(),casepath,sourcepath,draftpath,prior/'plan.json',prior/'calls.json',rp,rr,prefix,writer/'calls.json',writer/'completion.json',wp,wr,writer/'candidate-report.md',writer/'writer-field-transport.json',*Path('local_deep_research/research_verify').glob('*.py'),*[Path(s)for s in ['scripts/run_complete_draft_pair_20261115.py','scripts/prepare_source_detail_material_20261114.py','scripts/run_native_original_report_pair_20261114.py','scripts/experiment_error_receipt.py']]]
    freeze={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',freeze)
    for f in files:
        rel=f.resolve().relative_to(Path.cwd().resolve())
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    if a.execute:
        assert a.preflight_attempt is not None
        pf=read(a.preflight_attempt/'completion.json');assert pf['status']=='preflight_only'and pf['oversize_native_prompts']==0 and pf['fresh_model_calls']==0
        oldfreeze=read(a.preflight_attempt/'prestart-freeze.json');assert all(sha(Path(k))==v for k,v in oldfreeze.items())
    clock=datetime.fromisoformat(old['fixed_writer_clock'])
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock;evidence_flow.SOURCE_CONTEXT_CHARS=300000
    write(a.out_dir/'plan.json',dict(scope='Exact cached native source reader and actual matched canonical-field Writer; native consistency ON, save-time citationQC OFF. Preflight only unless explicitly executed after all actual preflight prompts fit. No independent scientific verdict.',maximum_fresh_native_calls=16,maximum_native_prompt_chars=60000,source_cap=300000,fixed_writer_clock=clock.isoformat(),settings=settings,actual_cached_writer_settings=read(writer/'plan.json')['settings'],writer_attempt=str(writer),live_source_acquisition=False,new_independent_correction_credit=0))
    calls=[];model=None;fetch=FixedSources();trace=Trace(a.out_dir/'trace.jsonl')
    class Handler:
        stream_callback=None;settings_snapshot=settings;evidence_fetcher=fetch
        def get_setting(self,k,d=None):return settings.get(k,d)
        def is_fact_checking_enabled(self):return True
        def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
        def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
        def _no_sources_response(self,q):raise ValueError('No actual source material')
        def _invoke_text(self,prompt,trace=None,stage='model'):
            nonlocal model
            if stage=='writer':
                assert prompt==prefix.read_text()
                assert wp.read_text().startswith(prompt+'\nADDITIONAL FALLIBLE SOURCE-ONLY FIELD NOTES:\n')
                prompt=wp.read_text()
            i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
            row=dict(index=i,stage=stage,prompt_sha256=sha(pp),prompt_chars=len(prompt),status='started');calls.append(row);write(a.out_dir/'calls.json',calls)
            try:
                if stage=='source_reading':
                    assert prompt==rp.read_text();raw=rr.read_text();meta=first['response_metadata'];row['origin']='strict_source_reader_cache'
                elif stage=='writer':
                    raw=wr.read_text();meta=wc['response_metadata'];row['origin']='strict_actual_writer_cache'
                else:
                    assert sum(c.get('origin')=='fresh_model'for c in calls)<16
                    row['over_prompt_budget']=len(prompt)>60000
                    if a.execute:
                        assert len(prompt)<=60000;row['origin']='fresh_model';write(a.out_dir/'calls.json',calls)
                        if model is None:
                            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                            from local_deep_research.config.thread_settings import settings_context
                            from local_deep_research.config.llm_config import get_llm
                            defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                            effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
                            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                        response=model.invoke(prompt);raw=str(response.content);meta=response.response_metadata
                    else:raw='{"issues":[]}';meta={};row['origin']='preflight_placeholder_not_semantic_review'
                responsepath=a.out_dir/f'call-{i:02d}-response.txt';responsepath.write_text(raw);row.update(status='returned',response_sha256=sha(responsepath),response_metadata=meta);return raw
            except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
            finally:write(a.out_dir/'calls.json',calls)
    failure=None;review=None
    try:
        result=evidence_flow.synthesize(Handler(),case['query'],copy.deepcopy(sources),draft,trace)
        (a.out_dir/'report.md').write_text(result['content']);review=result['evidence_review'];write(a.out_dir/'native-review.json',review)
    except Exception as exc:failure=error_receipt(exc)
    done=dict(status='unavailable'if failure else('native_pipeline_executed'if a.execute else'preflight_only'),failure=failure,logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),native_prompt_chars=[c['prompt_chars']for c in calls if c['stage']not in ['source_reading','writer']],oversize_native_prompts=sum(c.get('over_prompt_budget',False)for c in calls),frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in freeze.items()),placeholder_review_not_quality_evidence=not a.execute,independent_assessment_complete=False,new_independent_correction_credit=0)
    write(a.out_dir/'completion.json',done);print(json.dumps(done))
    if failure or not done['frozen_inputs_unchanged']:raise SystemExit(2)


if __name__=='__main__':main()
