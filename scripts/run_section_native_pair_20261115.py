"""Complete native pair: frozen flat baseline and cached new section Writer.

No repeated reading/Writer model calls. Only the new section draft's native
checks may invoke the model, with the same16call budget as the saved baseline.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from research_verify import evidence_flow
from research_verify.fact_document import instructions as flat_instructions,render as flat_render
from research_verify.section_document import instructions,render
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prior-attempt',type=Path,required=True);p.add_argument('--writer-attempt',type=Path,required=True);p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--replay-attempt',type=Path);p.add_argument('--writer-exposure-context',action='store_true',help='Opt-in section-arm native exposure context; flat cache remains unchanged');p.add_argument('--native-response-cache-dir',type=Path);p.add_argument('--uncited-source-discovery',action='store_true');p.add_argument('--writer-quote-evidence',action='store_true');p.add_argument('--native-cache-attempt',type=Path);p.add_argument('--quote-cache-dir',type=Path);a=p.parse_args();assert not(a.execute and a.replay_attempt);assert not(a.execute and a.native_cache_attempt);a.out_dir.mkdir(exist_ok=False)
    cases=_manifest_cases(a.case_manifest);assert len(cases)==1;case=cases[0];draft=case['draft'].read_text();sources=json.loads(case['source'].read_text());oldplan=json.loads((a.prior_attempt/'plan.json').read_text());oldall=json.loads((a.prior_attempt/'calls.json').read_text());previous=[c for c in oldall if c['arm']=='candidate'and c['stage']not in('source_questions','source_answers')];assert len(previous)==18
    assert oldplan['query']==case['query']and oldplan['original_report_sha256']==sha(case['draft'])and oldplan['source_pack_sha256']==sha(case['source'])
    registry=json.loads((a.prior_attempt/'candidate/fact-registry.json').read_text());wr=json.loads((a.writer_attempt/'result.json').read_text());assert wr['status']=='draft_generated'and wr['frozen_inputs_unchanged']
    assert sha(a.writer_attempt/'response.txt')==wr['response_sha256']and sha(a.writer_attempt/'prompt.txt')==wr['prompt_sha256']
    assert sha(a.writer_attempt/'fact-registry.json')==sha(a.prior_attempt/'candidate/fact-registry.json')
    settings=oldplan['settings'];assert settings['general.enable_fact_checking']and not settings['verify.enable_citation_qc']and settings['citation.max_review_calls']==16
    clock=datetime.fromisoformat(oldplan['fixed_writer_clock'])
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock;evidence_flow.SOURCE_CONTEXT_CHARS=300000
    files=[Path(__file__).resolve().relative_to(Path.cwd()),a.case_manifest,case['draft'],case['source'],a.prior_attempt/'plan.json',a.prior_attempt/'calls.json',a.prior_attempt/'candidate/result.json',a.prior_attempt/'candidate/report.txt',a.prior_attempt/'candidate/fact-registry.json',*[a.writer_attempt/name for name in ['plan.json','result.json','prompt.txt','response.txt','candidate-draft.txt','rendering.json','fact-registry.json','native-writer-prefix.txt']],Path('scripts/run_complete_draft_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    for c in previous:files.extend([a.prior_attempt/f"call-{c['index']:02d}-prompt.txt",a.prior_attempt/f"call-{c['index']:02d}-response.txt"])
    pool={}
    if a.native_cache_attempt:
        cp=a.native_cache_attempt/'calls.json';files.append(cp)
        for c in json.loads(cp.read_text()):
            if c['arm']!='section' or c['stage'] in ('source_reading','writer'):continue
            op=a.native_cache_attempt/f"call-{c['index']:02d}-prompt.txt";rp=a.native_cache_attempt/f"call-{c['index']:02d}-response.txt"
            assert sha(op)==c['prompt_sha256'] and sha(rp)==c['response_sha256']
            pool[(c['stage'],sha(op))]=(op,rp,c['response_metadata']);files.extend([op,rp])
    if a.quote_cache_dir:
        assert a.native_cache_attempt and a.writer_quote_evidence
        for folder in sorted(a.quote_cache_dir.glob('immune-group-*')):
            result=folder/'result.json';c=json.loads(result.read_text());op=folder/'prompt.txt';rp=folder/'response.txt'
            assert c['status']=='parsed' and sha(op)==c['prompt_sha256'] and sha(rp)==c['response_sha256']
            key=('native_check',sha(op));assert key not in pool
            pool[key]=(op,rp,c['response_metadata']);files.extend([result,op,rp])
    if a.native_response_cache_dir:
        assert a.native_cache_attempt and not a.execute
        files.extend([a.native_response_cache_dir/'plan.json',a.native_response_cache_dir/'completion.json'])
        for folder in sorted(a.native_response_cache_dir.glob('group-*')):
            result=folder/'result.json';c=json.loads(result.read_text());op=folder/'prompt.txt';rp=folder/'response.txt'
            assert c['status']=='parsed' and sha(op)==c['prompt_sha256'] and sha(rp)==c['response_sha256']
            key=('native_check',sha(op));assert key not in pool
            pool[key]=(op,rp,c['response_metadata']);files.extend([result,op,rp])
    if a.replay_attempt:
        files.extend([a.replay_attempt/'calls.json',a.replay_attempt/'completion.json'])
        for c in json.loads((a.replay_attempt/'calls.json').read_text()):
            files.extend([a.replay_attempt/f"call-{c['index']:02d}-prompt.txt",a.replay_attempt/f"call-{c['index']:02d}-response.txt"])
        files.extend(a.replay_attempt/arm/'result.json' for arm in ['flat','section'])
    freeze={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',freeze)
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    plan=dict(scope='Complete actual native synthesis; exact cached flat baseline and exact cached new paper-block Writer draft. Same original question/nonempty report/material/source reader/fact registry/native16call budgets/fixed clock. Only section candidate native calls fresh. No retrieval, production changes, independent semantic judgement or generalization claim.',prior_attempt=str(a.prior_attempt),writer_attempt=str(a.writer_attempt),query=case['query'],query_sha256=case['query_sha256'],original_report_sha256=sha(case['draft']),source_pack_sha256=sha(case['source']),settings=settings,fixed_writer_clock=clock.isoformat(),isolated_source_cap_override=300000,maximum_fresh_calls=16,maximum_prompt_chars=500000,new_independent_correction_credit=0)
    plan['section_writer_exposure_context']=a.writer_exposure_context
    plan['section_writer_quote_evidence']=a.writer_quote_evidence
    plan['section_uncited_source_discovery']=a.uncited_source_discovery
    plan['strict_native_cache_only']=bool(a.native_cache_attempt)
    plan['cache_miss_policy']='Preserve unmatched prompt and unresolved failure; no fresh model or placeholder response.'
    if a.native_cache_attempt:plan['maximum_fresh_calls']=0
    plan['historical_budget_limit']='Unchanged historical native prompts may exceed declared60000; no new calls authorized. Newly augmented prompts bounded to60000.'
    plan['exposure_context_budget_tradeoff']='When enabled, reserve6000chars inside existing native60000budget; reviewer source excerpts may change. Not a label-only contrast.'
    write(a.out_dir/'plan.json',plan);calls=[];results=[];model=None;replay=json.loads((a.replay_attempt/'calls.json').read_text())if a.replay_attempt else None
    for arm in ['flat','section']:
        folder=a.out_dir/arm;folder.mkdir();fetch=FixedSources();trace=Trace(folder/'trace.jsonl');arm_sources=copy.deepcopy(sources);cache_index=0;fresh=0
        arm_settings=(settings|{'citation.include_writer_exposure_context':True}
                      if arm=='section'and a.writer_exposure_context else settings)
        if arm=='section' and a.writer_quote_evidence:arm_settings=arm_settings|{'citation.preserve_writer_quote_evidence':True}
        if arm=='section' and a.uncited_source_discovery:arm_settings=arm_settings|{'citation.discover_uncited_source_context':True}
        class Handler:
            stream_callback=None;settings_snapshot=arm_settings;evidence_fetcher=fetch
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def is_fact_checking_enabled(self):return True
            def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _no_sources_response(self,q):raise ValueError('No actual material')
            def _invoke_text(self,prompt,trace=None,stage='model'):
                nonlocal cache_index,fresh,model
                if stage=='writer':
                    assert prompt==(a.writer_attempt/'native-writer-prefix.txt').read_text()
                    prompt+=(flat_instructions if arm=='flat'else instructions)(arm_sources,registry)
                assert len(prompt)<500000
                i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,arm=arm,stage=stage,status='started',prompt_sha256=sha(pp),prompt_chars=len(prompt));calls.append(row);write(a.out_dir/'calls.json',calls)
                try:
                    if replay is not None:
                        old=replay[i];op=a.replay_attempt/f'call-{i:02d}-prompt.txt';rp=a.replay_attempt/f'call-{i:02d}-response.txt';assert(old['arm'],old['stage'],op.read_text())==(arm,stage,prompt);assert sha(op)==old['prompt_sha256']and sha(rp)==old['response_sha256'];raw,meta=rp.read_text(),old['response_metadata'];row.update(origin='saved_response_replay',replay_origin=old['origin'])
                    elif arm=='flat'or stage=='source_reading':
                        c=previous[cache_index]if arm=='flat'else previous[0];op=a.prior_attempt/f"call-{c['index']:02d}-prompt.txt";rp=a.prior_attempt/f"call-{c['index']:02d}-response.txt";assert c['stage']==stage and prompt==op.read_text()and sha(op)==c['prompt_sha256']and sha(rp)==c['response_sha256'];raw,meta=rp.read_text(),c['response_metadata'];row.update(origin='strict_prior_cache',cached_from=str(rp));cache_index+=int(arm=='flat')
                    elif stage=='writer':
                        assert prompt==(a.writer_attempt/'prompt.txt').read_text();raw=(a.writer_attempt/'response.txt').read_text();meta=wr['response_metadata'];row.update(origin='strict_writer_cache',cached_from=str(a.writer_attempt/'response.txt'))
                    elif a.native_cache_attempt:
                        match=pool.get((stage,sha(pp)))
                        if match is None:
                            row['origin']='strict_cache_miss'
                            raise LookupError('No exact saved response for stage/prompt SHA; fresh calls disabled')
                        op,rp,meta=match;assert op.read_text()==prompt
                        raw=rp.read_text();row.update(origin='strict_native_prompt_cache',cached_from=str(rp))
                    else:
                        fresh+=1;assert fresh<=16
                        row['origin']='fresh_model'if a.execute else'preflight_placeholder';write(a.out_dir/'calls.json',calls)
                        if a.execute:
                            if model is None:
                                from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                                from local_deep_research.config.thread_settings import settings_context
                                from local_deep_research.config.llm_config import get_llm
                                defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
                                with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                            response=model.invoke(prompt);raw,meta=str(response.content),response.response_metadata
                        else:raw,meta='{"issues":[]}',{}
                    rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=meta)
                    if stage=='writer':
                        answer,receipt=(flat_render if arm=='flat'else render)(raw,arm_sources,registry);(folder/'writer-rendered.txt').write_text(answer);write(folder/'rendering.json',receipt)
                        self.writer_quote_registry=registry;self.writer_quote_rendering=receipt
                        if arm=='section':assert answer==(a.writer_attempt/'candidate-draft.txt').read_text()
                        return answer
                    return raw
                except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
                finally:write(a.out_dir/'calls.json',calls)
        try:
            result=evidence_flow.synthesize(Handler(),case['query'],arm_sources,draft,trace);(folder/'report.txt').write_text(result['content']);row=dict(arm=arm,status='completed',report_chars=len(result['content']),report_sha256=sha(folder/'report.txt'),native_review=result['evidence_review'],sources=arm_sources,supplement_requests=fetch.events)
            if arm=='flat':
                old=json.loads((a.prior_attempt/'candidate/result.json').read_text());assert result['content']==(a.prior_attempt/'candidate/report.txt').read_text()and row['native_review']==old['native_review']and row['supplement_requests']==old['supplement_requests'];assert replay is not None or cache_index==len(previous)
        except Exception as exc:row=dict(arm=arm,status='unavailable',failure=error_receipt(exc))
        write(folder/'result.json',row);results.append({k:v for k,v in row.items()if k!='sources'})
        if row['status']=='unavailable':break
    if replay is not None:
        assert len(calls)==len(replay)
        for row in results:assert row=={k:v for k,v in json.loads((a.replay_attempt/row['arm']/'result.json').read_text()).items()if k!='sources'}
    completion=dict(arms=results,logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),strict_cached_calls=sum(c.get('origin')in('strict_prior_cache','strict_writer_cache','strict_native_prompt_cache')for c in calls),frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in freeze.items()),replay_exact=True if replay is not None else None,retrieval_network_reads=0,new_independent_correction_credit=0,unavailable_calls=sum(c.get('status')=='unavailable'for c in calls));write(a.out_dir/'completion.json',completion);print(json.dumps({k:v for k,v in completion.items()if k!='arms'}))
    if any(r['status']=='unavailable'for r in results) or completion['unavailable_calls']:raise SystemExit(2)


if __name__=='__main__':main()
