"""Finite source-only ledger then attribute comparison; never edits reports."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.source_fact_ledger import ledger_prompt,parse_ledger,attribute_comparison_prompt,parse_attribute_comparisons,parse_ledger_partial
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--extraction-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--partial-ledger',action='store_true');p.add_argument('--cache-first-source',type=Path);a=p.parse_args()
    data=json.loads(a.inputs.read_text());prior=json.loads((a.extraction_attempt/'completion.json').read_text());assert prior['status']=='completed'
    extracted={r['case_id']:r['extraction']for r in prior['results']}
    paths=[a.inputs,a.extraction_attempt/'completion.json',a.extraction_attempt/'calls.json',*a.extraction_attempt.glob('call-*-*.txt'),Path(__file__),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py'),*[Path(x['path'])for x in data['input_files']]]
    if a.cache_first_source:paths.extend([a.cache_first_source/'calls.json',a.cache_first_source/'call-00-prompt.txt',a.cache_first_source/'call-00-response.txt'])
    for c in data['cases']:
        report=Path(c['report_path']).read_text();assert sha(Path(c['report_path']))==c['report_sha256']
        for u in extracted[c['case_id']]:
            for claim in u['claims']:assert report[claim['report_start']:claim['report_end']]==claim['quote']
    a.out_dir.mkdir(parents=True,exist_ok=False);frozen={str(p):sha(p)for p in paths}
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='Previously exposed two-task diagnostic: source-only reading then per-attribute comparison, no report edits or independent scoring',inputs=str(a.inputs),extraction_attempt=str(a.extraction_attempt),partial_ledger=a.partial_ledger,cache_first_source=str(a.cache_first_source)if a.cache_first_source else None,maximum_calls=8,maximum_prompt_chars=70000,maximum_output_tokens=4000,comparison_batch_claims=12,writer=False,publication=False,live_fetch=False,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':4000,'llm.request_timeout':180,'llm.max_retries':1,'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];results=[];failure=None
    def invoke(prompt,stage):
        if len(calls)>=8 or len(prompt)>70000:raise ValueError('Finite ledger invocation bound')
        i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,stage=stage,prompt_chars=len(prompt),prompt_sha256=sha(pp));calls.append(row)
        try:
            if a.cache_first_source and i==0:
                old=json.loads((a.cache_first_source/'calls.json').read_text())[0];assert old['stage']==stage and old['status']=='returned'
                pp_old=a.cache_first_source/'call-00-prompt.txt';rp_old=a.cache_first_source/'call-00-response.txt'
                assert prompt==pp_old.read_text()and sha(pp_old)==old['prompt_sha256']and sha(rp_old)==old['response_sha256']
                raw=rp_old.read_text();metadata=old['response_metadata'];row.update(origin='strict_cache',cached_from=str(rp_old))
            else:
                response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata;row['origin']='fresh'
            rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);return raw
        except Exception as exc:row.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    try:
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
            model=get_llm(settings_snapshot=snap)
            for case in data['cases']:
                ledger=(parse_ledger_partial if a.partial_ledger else parse_ledger)(invoke(ledger_prompt(case['query'],case['source_units']),case['case_id']+':source_ledger'),case['source_units'])
                comparisons=[];r=dict(case_id=case['case_id'],ledger=ledger,batches=comparisons);results.append(r)
                claims=[dict(report_unit_id=x['report_unit_id'],claims=[c])for x in extracted[case['case_id']]for c in x['claims']]
                for i,start in enumerate(range(0,len(claims),12)):
                    b=claims[start:start+12];raw=invoke(attribute_comparison_prompt(case['query'],b,ledger,case['source_units']),case['case_id']+':attribute_comparison:'+str(i))
                    comparisons.append(parse_attribute_comparisons(raw,b,case['source_units']))
                (a.out_dir/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    except Exception as exc:failure=error_receipt(exc)
    complete=dict(status='unavailable'if failure else'completed',failure=failure,calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),report_modifications=0,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(complete,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(status=complete['status'],calls=len(calls),failure=failure)))


if __name__=='__main__':main()
