"""Finite post-writer native check pair; cached exact baseline vs retrieval options."""
import argparse,copy,hashlib,json
from pathlib import Path
from research_verify.evidence_flow import review_answer
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--prior-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    old=a.prior_attempt;prior=json.loads((old/'plan.json').read_text());old_result=json.loads((old/'inherited/result.json').read_text());report=(old/'inherited/report.txt').read_text();sources=old_result['sources'];settings=prior['settings'];calls=[];results=[]
    previous=[c for c in json.loads((old/'calls.json').read_text())if c['arm']=='inherited'and c['stage']=='native_check'];assert len(previous)==4
    paths=[Path(__file__),Path('scripts/run_complete_draft_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py'),old/'plan.json',old/'calls.json',old/'inherited/report.txt',old/'inherited/result.json']
    for row in previous:paths.extend([old/f"call-{row['index']:02d}-prompt.txt",old/f"call-{row['index']:02d}-response.txt"])
    freeze={str(p):sha(p)for p in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for p in paths:
        if str(p).startswith(('scripts/','local_deep_research/')):
            d=a.out_dir/'code'/p;d.parent.mkdir(parents=True,exist_ok=True);d.write_bytes(p.read_bytes())
    plan=dict(scope='Same COMPLETE previously generated inherited report and actual native sources; no Writer/regeneration/retrieval/publication. Cached baseline requires identical native prompt and response bytes; candidate ONLY source-scoped query and hyphen component retrieval hints. No independent scoring.',query=prior['query'],query_sha256=prior['query_sha256'],report_sha256=sha(old/'inherited/report.txt'),report_chars=len(report),settings=settings,maximum_native_calls_per_arm=6,maximum_logical_calls=12,maximum_prompt_chars=300000,arms=['baseline','retrieval'],quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');model=None
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        from local_deep_research.config.thread_settings import settings_context
        from local_deep_research.config.llm_config import get_llm
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:settings.get(k,d))})()):model=get_llm(settings_snapshot=settings)
    for arm in plan['arms']:
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');arm_sources=copy.deepcopy(sources);fetch=FixedSources();baseline_index=0
        class Handler:
            settings_snapshot=settings|{'citation.review_source_scoped_queries':arm=='retrieval','citation.review_compound_terms':arm=='retrieval'}
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _invoke_text(self,prompt,trace=None,stage='model'):
                nonlocal baseline_index
                if len(calls)>=12 or len(prompt)>300000:raise ValueError('Finite native pair invocation bound')
                i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,arm=arm,stage=stage,prompt_sha256=sha(pp),prompt_chars=len(prompt));calls.append(row)
                try:
                    if arm=='baseline':
                        c=previous[baseline_index];baseline_index+=1;assert stage==c['stage']
                        op=old/f"call-{c['index']:02d}-prompt.txt";rp=old/f"call-{c['index']:02d}-response.txt";assert sha(op)==c['prompt_sha256']and prompt==op.read_text()and sha(rp)==c['response_sha256'];raw=rp.read_text();metadata=c['response_metadata'];row.update(origin='strict_cache',cached_from=str(rp))
                    elif not a.execute:raw='{"issues":[]}';metadata={};row['origin']='preflight_placeholder'
                    else:
                        response=model.invoke(prompt);raw=str(getattr(response,'content',response));metadata=getattr(response,'response_metadata',{});row['origin']='fresh_model'
                    rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);return raw
                except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
                finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2,default=str)+'\n')
        try:
            revised,docs,applied,unresolved,shown=review_answer(Handler(),prior['query'],report,native_documents(arm_sources),arm_sources,trace,None,1,200000,dict(fetcher=fetch),dict(remaining=6))
            (folder/'report.txt').write_text(revised);result=dict(arm=arm,status='completed',report_sha256=sha(folder/'report.txt'),report_chars=len(revised),report_changed=revised!=report,applied=applied,unresolved=unresolved,shown_source_ids=sorted(shown),supplement_requests=fetch.events,sources=arm_sources)
            if arm=='baseline':assert revised==report and baseline_index==len(previous)and applied==old_result['native_review']['parts'][0]['applied']and unresolved==old_result['native_review']['parts'][0]['unresolved']
        except Exception as exc:result=dict(arm=arm,status='unavailable',failure=error_receipt(exc))
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n');results.append({k:v for k,v in result.items()if k!='sources'})
    completion=dict(arms=results,logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),strict_cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),network_retrieval_reads=0,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps({k:v for k,v in completion.items()if k!='arms'},ensure_ascii=False))


if __name__=='__main__':main()
