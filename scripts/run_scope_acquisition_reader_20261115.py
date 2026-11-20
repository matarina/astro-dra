"""Source-only acquisition comparison on one known paper; no report scoring.

Same original query, paper identity, scope instruction and span-ID reader.
Only additional identity-bound original article text differs. No old report,
native verdict or expected biological answer enters either model prompt.
"""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.source_span_answers import answer_prompt, parse_answers, span_registry
from research_verify.fact_document import clean_json
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--replay-attempt',type=Path)
    p.add_argument('--prior-prefix',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay_attempt);a.out_dir.mkdir(exist_ok=False)
    spec=json.loads(a.inputs.read_text());assert len(spec['cases'])==2
    files=[a.inputs,Path(__file__).resolve().relative_to(Path.cwd()),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    prefix=json.loads((a.prior_prefix/'calls.json').read_text())if a.prior_prefix else []
    if a.prior_prefix:
        files.extend([a.prior_prefix/'calls.json',a.prior_prefix/'completion.json'])
        for row in prefix:
            files.extend([a.prior_prefix/f"call-{row['index']:02d}-prompt.txt",a.prior_prefix/f"call-{row['index']:02d}-response.txt"])
    for c in spec['cases']:files.append(Path(c['views_path']))
    linked=a.inputs.parent/'input-freeze.json'
    assert linked.is_file()
    bound=json.loads(linked.read_text());assert all(sha(Path(f))==h for f,h in bound.items())
    files.extend([linked,*map(Path,bound)])
    frozen={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',frozen)
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    settings={'llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,'llm.max_retries':0}
    plan=dict(scope='One known immune paper/source-only acquisition diagnostic. Same original question, source ID/PMID/DOI, scope instructions, reader algorithm and model settings; new arm appends identity-bound original article text to the unchanged original abstract. No old report, native judgement, expected answer or feedback label in prompts. No complete report, independent correction, retention/new-error assessment or unseen-task generalization.',maximum_fresh_calls=2,maximum_prompt_chars=60000,max_facts_per_source=4,max_fact_chars=600,max_quote_references=3,span_max_chars=900,settings=settings,source_acquisition=False,new_independent_correction_credit=0)
    plan.update(strict_prefix_cached_calls=len(prefix),maximum_new_fresh_calls=2-len(prefix))
    write(a.out_dir/'plan.json',plan);model=None;calls=[];results=[]
    prior=json.loads((a.replay_attempt/'calls.json').read_text())if a.replay_attempt else None
    for case in spec['cases']:
        assert sha(Path(case['views_path']))==case['views_sha256']
        views=json.loads(Path(case['views_path']).read_text());records,spans=span_registry(views)
        folder=a.out_dir/case['case_id'];folder.mkdir();write(folder/'supplied-passages.json',records)
        for mode in ['span_ids']:
            prompt=answer_prompt(case['query'],views,transport=mode);assert len(prompt)<=60000
            i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
            row=dict(index=i,case_id=case['case_id'],transport=mode,status='started',prompt_sha256=sha(pp),prompt_chars=len(prompt));calls.append(row);write(a.out_dir/'calls.json',calls)
            try:
                if prior is not None:
                    old=prior[i];rp=a.replay_attempt/f'call-{i:02d}-response.txt';op=a.replay_attempt/f'call-{i:02d}-prompt.txt'
                    assert (old['case_id'],old['transport'],op.read_text())==(case['case_id'],mode,prompt)
                    assert sha(op)==old['prompt_sha256']and sha(rp)==old['response_sha256']
                    raw,metadata=rp.read_text(),old['response_metadata'];row['origin']='saved_response_replay'
                elif i < len(prefix):
                    old=prefix[i];rp=a.prior_prefix/f'call-{i:02d}-response.txt';op=a.prior_prefix/f'call-{i:02d}-prompt.txt'
                    assert (old['case_id'],old['transport'],op.read_text())==(case['case_id'],mode,prompt)
                    assert sha(op)==old['prompt_sha256']and sha(rp)==old['response_sha256']and old['status']=='returned'
                    raw,metadata=rp.read_text(),old['response_metadata'];row.update(origin='strict_prefix_cache',cached_from=str(rp))
                elif a.execute:
                    row['origin']='fresh_model';write(a.out_dir/'calls.json',calls)
                    if model is None:
                        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                        from local_deep_research.config.thread_settings import settings_context
                        from local_deep_research.config.llm_config import get_llm
                        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
                        effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
                        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                    response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
                else:
                    raw=json.dumps({'sources':[dict(source_id=v['source_id'],facts=[])for v in views]});metadata={};row['origin']='preflight_placeholder'
                rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw)
                row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata)
                parsed=parse_answers(raw,views,transport=mode);write(folder/(mode+'-parsed.json'),parsed)
                if prior is not None:assert parsed==json.loads((a.replay_attempt/case['case_id']/(mode+'-parsed.json')).read_text())
                result=dict(case_id=case['case_id'],transport=mode,status='parsed',source_records=len(views),raw_facts=sum(len(r.get('facts',[]))for r in clean_json(raw)['sources']if isinstance(r,dict)and isinstance(r.get('facts'),list)),bound_facts=len(parsed['registry']),unbound_facts=len(parsed['unbound_facts']),invalid_question_bindings=len(parsed['invalid_question_bindings']),model_unaddressed_question_ids=parsed['model_unaddressed_question_ids'],semantic_support_verified=False)
                for fact in parsed['registry'].values():
                    source=next(v for v in views if str(v['source_id'])==fact['source_id'])
                    assert hashlib.sha256(source['text'].encode()).hexdigest()==fact['source_view_sha256']
                    assert all(source['text'][q['start']:q['end']]==q['text']for q in fact['quotes'])
            except Exception as exc:
                row.setdefault('failure',error_receipt(exc));result=dict(case_id=case['case_id'],transport=mode,status='unavailable',failure=error_receipt(exc))
            write(a.out_dir/'calls.json',calls);results.append(result);write(a.out_dir/'results.json',results)
    if prior is not None:
        assert len(calls)==len(prior) and results==json.loads((a.replay_attempt/'results.json').read_text())
    completion=dict(results=results,logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),strict_prefix_cached_calls=sum(c.get('origin')=='strict_prefix_cache'for c in calls),prior_prefix=str(a.prior_prefix)if a.prior_prefix else None,all_planned_observations_recorded=len(results)==2,parse_or_call_failures=sum(r['status']=='unavailable'for r in results),replay_exact=True if prior is not None else None,frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in frozen.items()),retrieval_network_reads=0,complete_report_evaluated=False,semantic_verdict=None,new_independent_correction_credit=0)
    write(a.out_dir/'completion.json',completion);print(json.dumps({k:v for k,v in completion.items()if k!='results'}))
    if completion['parse_or_call_failures'] or not completion['frozen_inputs_unchanged']:
        raise SystemExit(2)


if __name__=='__main__':main()
