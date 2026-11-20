"""Existing native post-Writer check of two frozen complete reports, not adjudication."""
import argparse, copy, hashlib, json
from pathlib import Path
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace, FixedSources
from research_verify.evidence_flow import review_answer, review_claim_groups

ROOT=Path('evaluation/frontier-strategy-20261113')
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def prepare():
    cp=ROOT/'immune-questioned-fact-inputs-20261115-v1/case-manifest.json'
    case,=read(cp)['cases']; sp=Path(case['source']); assert sha(sp)==case['source_sha256']
    mp=ROOT/'source-view-scope-writer-coordinator-handoff-20261115-v1/assessment-input/generation-source-material.json'
    materials=read(mp); sources=copy.deepcopy(read(sp)); grouped={}
    for row in materials: grouped.setdefault(str(row['source_id']),[]).append(row['text'])
    assert set(grouped)=={str(s['index']) for s in sources}
    joined={sid:'\n\nADDITIONAL WRITER-SUPPLIED SOURCE TEXT:\n'.join(parts) for sid,parts in grouped.items()}
    for s in sources:
        s['fetched_content']=joined[str(s['index'])]
    docs=native_documents(sources)
    for doc in docs:
        assert doc.page_content==joined[str(doc.metadata['index'])],doc.metadata['index']
    reports={arm:ROOT/f'source-view-scope-writer-model-20261115-v1/attempt/{arm}-report.md'
             for arm in ['record_scope','actual_view_scope']}
    groups={arm:review_claim_groups(p.read_text(),docs,sources,case['query'],60000) for arm,p in reports.items()}
    return case,sources,reports,groups,[cp,sp,mp,*reports.values()]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--replay',type=Path)
    a=p.parse_args(); assert not(a.execute and a.replay)
    case,sources,reports,groups,inputs=prepare();a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
          Path('scripts/run_native_original_report_pair_20261114.py'),
          Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
          Path('local_deep_research/overlay/base_citation_handler.py'),
          *Path('local_deep_research/research_verify').glob('*.py')]
    frozen={str(f):sha(f) for f in [*inputs,*code]}
    for f in code:
        rel=f.resolve().relative_to(Path.cwd());target=a.out_dir/'code'/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    write(a.out_dir/'prestart-freeze.json',frozen)
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,
              'llm.max_tokens':8000,'llm.request_timeout':180,'llm.max_retries':0,
              'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    # No experimental native feature flags; existing default native code in both arms.
    plan=dict(scope=__doc__,settings=settings,source_count=len(sources),question=case['query'],
        source_scope='Identical actual complete Writer-supplied source texts plus additional source text; original source identities preserved. No newly acquired text.',
        native_groups={k:len(v) for k,v in groups.items()},groups=groups,
        maximum_native_calls_per_arm=32,maximum_total_fresh_calls=64,source_context_chars=60000,
        live_search=False,writer=False,production_deployment=False,independent_correction_credit=0,
        limitations='Two different complete reports, not matched report intervention; native verdicts/repairs are fallible. No independent source/retention/new-error or generalization verdict. Existing native semantic-confirmation revisions on experimental copies only.')
    write(a.out_dir/'plan.json',plan);write(a.out_dir/'actual-source-pack.json',sources)
    if not(a.execute or a.replay):
        write(a.out_dir/'completion.json',dict(status='preflight_only',fresh_calls=0,native_groups=plan['native_groups']))
        print(json.dumps(dict(fresh_calls=0,groups=plan['native_groups'])));return
    snap=dict(settings)
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
        snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})|settings
    all_results=[];failure=None
    for arm,path in reports.items():
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');fetcher=FixedSources();calls=[]
        source_copy=copy.deepcopy(sources);report=path.read_text();(folder/'original-report.md').write_text(report)
        class Handler:
            settings_snapshot=snap;model=None
            def get_setting(self,k,default=None):return self.settings_snapshot.get(k,default)
            def _create_documents(self,s):return native_documents(s)
            def _invoke_text(self,prompt,**kw):
                index=len(calls);pp=folder/f'call-{index:03d}-prompt.txt';pp.write_text(prompt)
                row=dict(index=index,stage=kw.get('stage'),prompt_sha256=sha(pp),prompt_chars=len(prompt),status='started')
                calls.append(row);write(folder/'calls.json',calls)
                try:
                    # Conservative character upper bound; no silent source/prompt truncation.
                    assert len(prompt)+8000+8192<=131072,'conservative_prompt_context_bound'
                    if a.replay:
                        oldfolder=a.replay/arm;old=read(oldfolder/'calls.json')[index]
                        assert old['status']=='returned' and old['prompt_sha256']==row['prompt_sha256']
                        rp=oldfolder/f'call-{index:03d}-response.txt';assert sha(rp)==old['response_sha256']
                        raw=rp.read_text();metadata=old['response_metadata'];row['origin']='strict_replay'
                    else:
                        if self.model is None:
                            from local_deep_research.config.thread_settings import settings_context
                            from local_deep_research.config.llm_config import get_llm
                            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(self.get_setting)})()):
                                self.model=get_llm(settings_snapshot=self.settings_snapshot)
                        response=self.model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
                        row['origin']='fresh_model'
                    rp=folder/f'call-{index:03d}-response.txt';rp.write_text(raw)
                    row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata)
                    assert metadata.get('finish_reason')=='stop','non_stop_finish'
                    return raw
                except Exception as exc:
                    row.update(status='unavailable',error_type=type(exc).__name__);raise
                finally:write(folder/'calls.json',calls)
        handler=Handler();budget={'remaining':32}
        try:
            revised,docs,applied,unresolved,shown=review_answer(handler,case['query'],report,
                native_documents(source_copy),source_copy,trace,None,1,60000,{'fetcher':fetcher},budget)
            (folder/'native-report.md').write_text(revised)
            result=dict(arm=arm,original_report_sha256=sha(path),native_report_sha256=sha(folder/'native-report.md'),
                original_chars=len(report),native_chars=len(revised),model_calls=len(calls),remaining_calls=budget['remaining'],
                native_applied=applied,native_unresolved=unresolved,shown_source_ids=sorted(shown),
                supplement_requests=fetcher.events,independent_correction_credit=0)
            if a.replay:
                assert len(calls)==len(read(a.replay/arm/'calls.json'))
                assert result==read(a.replay/arm/'result.json')
            write(folder/'result.json',result);all_results.append(result)
        except Exception as exc:
            failure=dict(arm=arm,error_type=type(exc).__name__)
            break
    unchanged=all(sha(Path(p))==h for p,h in frozen.items())
    write(a.out_dir/'completion.json',dict(status='failed' if failure else 'native_check_complete',failure=failure,
        frozen_inputs_unchanged=unchanged,results=all_results,independent_correction_credit=0))
    print(json.dumps(dict(results=len(all_results),failure=failure,frozen_inputs_unchanged=unchanged)))
    if failure or not unchanged:raise SystemExit(2)
if __name__=='__main__':main()
