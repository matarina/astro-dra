"""Exact frozen-prompt alternate-model comparison; no new reading or report edits."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.source_fact_ledger import attribute_comparison_prompt,parse_attribute_comparisons
from research_verify.comparison_accounting import attribute_label_accounting
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--prior-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--reference-ledger',action='store_true');a=p.parse_args()
    prior=json.loads((a.prior_attempt/'completion.json').read_text());oldplan=json.loads((a.prior_attempt/'plan.json').read_text());inputs=Path(oldplan['inputs']);data=json.loads(inputs.read_text());oldcalls=json.loads((a.prior_attempt/'calls.json').read_text());catalog=json.loads(a.catalog.read_text())
    assert prior['status']=='completed'and prior['frozen_inputs_unchanged']
    alt='qwen3-vl-235b-a22b-instruct-fp8';assert alt in catalog['rows'][0]['model_ids']
    jobs=[];paths=[Path(__file__),Path('scripts/experiment_error_receipt.py'),a.catalog,inputs,a.prior_attempt/'completion.json',a.prior_attempt/'calls.json',a.prior_attempt/'plan.json',*Path('local_deep_research/research_verify').glob('*.py')]
    for name,stage in [('if','if:attribute_comparison:1'),('neuropathy','neuropathy:attribute_comparison:0')]:
        call=next(c for c in oldcalls if c['stage']==stage);pp=a.prior_attempt/f"call-{call['index']:02d}-prompt.txt";rp=a.prior_attempt/f"call-{call['index']:02d}-response.txt"
        assert call['status']=='returned'and sha(pp)==call['prompt_sha256']and sha(rp)==call['response_sha256']
        prompt=pp.read_text();extract=json.loads(prompt.split('ORIGINAL REPORT CLAIMS:\n',1)[1].split('\nFALLIBLE SOURCE-ONLY NOTES:',1)[0]);case=next(c for c in data['cases']if c['case_id']==name);ledger=next(r for r in prior['results']if r['case_id']==name)['ledger']
        assert attribute_comparison_prompt(case['query'],extract,ledger,case['source_units'])==prompt
        if a.reference_ledger:prompt=attribute_comparison_prompt(case['query'],extract,ledger,case['source_units'],references_only=True)
        jobs.append(dict(case_id=name,stage=stage,prompt=prompt,extracted=extract,units=case['source_units'],prior_response=str(rp),prior_metadata=call['response_metadata']));paths.extend([pp,rp])
    a.out_dir.mkdir(parents=True,exist_ok=False);freeze={str(p):sha(p)for p in paths}
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='Two exposed original-language frozen attribute prompts, comparator alias only; not complete report repair/independent quality/generalization',models=['deepseek-v4-flash',alt],reference_ledger=a.reference_ledger,maximum_fresh_calls=4 if a.reference_ledger else 2,temperature=0,max_tokens=4000,max_retries=0,prompt_char_limit=70000,model_identity='Endpoint aliases/fingerprints only; checkpoint not verified',jobs=jobs,newly_credited_corrections=0,report_changes=False)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(jobs=len(jobs),maximum_fresh_calls=plan['maximum_fresh_calls'])));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    base=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});base.update({'llm.provider':'openai_endpoint','llm.temperature':0,'llm.max_tokens':4000,'llm.request_timeout':180,'llm.max_retries':0,'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];results=[]
    for n,job in enumerate(jobs):
        for model_name in ([alt,'deepseek-v4-flash']if n==0 else['deepseek-v4-flash',alt]):
            i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(job['prompt']);entry=dict(index=i,case_id=job['case_id'],model=model_name,prompt_sha256=sha(pp),prompt_chars=len(job['prompt']));calls.append(entry);result=dict(case_id=job['case_id'],model=model_name)
            try:
                if model_name=='deepseek-v4-flash'and not a.reference_ledger:
                    raw=Path(job['prior_response']).read_text();metadata=job['prior_metadata'];entry.update(origin='strict_cache',cached_from=job['prior_response'])
                else:
                    snap={**base,'llm.model':model_name}
                    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):response=get_llm(settings_snapshot=snap).invoke(job['prompt'])
                    raw=str(response.content);metadata=response.response_metadata;entry['origin']='fresh'
                rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);entry.update(status='returned',response_sha256=sha(rp),response_metadata=metadata)
                parsed=parse_attribute_comparisons(raw,job['extracted'],job['units']);result.update(status='parsed',parsed=parsed,accounting=[attribute_label_accounting(c)for c in parsed['comparisons']])
            except Exception as exc:
                diagnostic=error_receipt(exc);result.update(status='unavailable',**diagnostic)
                if entry.get('status')!='returned':entry.update(status='unavailable',**diagnostic)
            results.append(result);(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    complete=dict(calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh'for c in calls),cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0,report_modifications=0)
    (a.out_dir/'completion.json').write_text(json.dumps(complete,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls),parsed=sum(r['status']=='parsed'for r in results))))


if __name__=='__main__':main()
