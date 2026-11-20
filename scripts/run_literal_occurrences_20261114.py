"""Finite frozen literal report extraction/comparison diagnostic. Never edits reports."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.literal_occurrences import extraction_prompt,parse_extraction,comparison_prompt,parse_comparison,parse_extraction_partial
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--partial-literal-bindings',action='store_true');p.add_argument('--cache-extractions',type=Path);a=p.parse_args()
    data=json.loads(a.inputs.read_text());assert len(data['cases'])==2
    a.out_dir.mkdir(parents=True,exist_ok=False)
    paths=[a.inputs,Path(__file__),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    paths.extend(Path(x['path'])for x in data['input_files'])
    if a.cache_extractions:
        paths.extend([a.cache_extractions/'calls.json',*[p for p in a.cache_extractions.glob('call-*-*.txt')]])
    frozen={str(p):sha(p)for p in paths}
    for x in data['input_files']:assert sha(Path(x['path']))==x['sha256']
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='Source-blind literal report extraction then located source comparison; no edits or independent scoring',cases=[dict(case_id=c['case_id'],query_sha256=hashlib.sha256(c['query'].encode()).hexdigest(),report_units=len(c['report_units']),source_units=len(c['source_units']))for c in data['cases']],partial_literal_bindings=a.partial_literal_bindings,cache_extractions=str(a.cache_extractions)if a.cache_extractions else None,maximum_calls=12,maximum_prompt_chars=70000,maximum_output_tokens=4000,extraction_batch_chars=2200,comparison_batch_claims=12,writer=False,publication=False,live_fetch=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':4000,'llm.request_timeout':180,'llm.max_retries':1,'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];results=[];failure=None
    def invoke(prompt,stage):
        if len(calls)>=12 or len(prompt)>70000:raise ValueError('Finite diagnostic call/prompt bound')
        i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=i,stage=stage,prompt_sha256=sha(pp),prompt_chars=len(prompt));calls.append(row)
        try:
            cached=None
            if a.cache_extractions and ':extract:'in stage:
                matches=[c for c in json.loads((a.cache_extractions/'calls.json').read_text())if c['stage']==stage]
                assert len(matches)==1;cached=matches[0];old=a.cache_extractions/f"call-{cached['index']:02d}-prompt.txt"
                assert cached['status']=='returned'and prompt==old.read_text()and sha(old)==cached['prompt_sha256']
                old_reply=a.cache_extractions/f"call-{cached['index']:02d}-response.txt";assert sha(old_reply)==cached['response_sha256']
                raw=old_reply.read_text();metadata=cached['response_metadata'];row.update(origin='strict_cache',cached_from=str(old_reply))
            else:
                response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata;row['origin']='fresh'
            rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw)
            row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);return raw
        except Exception as exc:row.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    try:
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
            model=get_llm(settings_snapshot=snap)
            for case in data['cases']:
                extraction=[];comparisons=[];batch=[];batches=[];size=0
                for unit in case['report_units']:
                    if batch and size+len(unit['text'])>2200:batches.append(batch);batch=[];size=0
                    batch.append(unit);size+=len(unit['text'])
                if batch:batches.append(batch)
                r=dict(case_id=case['case_id'],extraction=extraction,comparisons=comparisons);results.append(r)
                for i,b in enumerate(batches):
                    raw=invoke(extraction_prompt(case['query'],b),case['case_id']+':extract:'+str(i))
                    try:extraction.extend((parse_extraction_partial if a.partial_literal_bindings else parse_extraction)(raw,b))
                    except(ValueError,KeyError,TypeError)as exc:
                        extraction.extend(dict(report_unit_id=u['report_unit_id'],claims=[],status='unassessed',limit='Unusable extraction: '+type(exc).__name__)for u in b)
                claims=[dict(report_unit_id=x['report_unit_id'],claims=[claim])for x in extraction for claim in x['claims']]
                for i,start in enumerate(range(0,len(claims),12)):
                    b=claims[start:start+12];raw=invoke(comparison_prompt(case['query'],b,case['source_units']),case['case_id']+':compare:'+str(i))
                    try:comparisons.extend(parse_comparison(raw,b,case['source_units']))
                    except(ValueError,KeyError,TypeError)as exc:
                        comparisons.extend(dict(claim_id=x['claims'][0]['claim_id'],relation=None,status='unassessed',reason='Unusable comparison: '+type(exc).__name__,evidence=[])for x in b)
                (a.out_dir/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    except Exception as exc:failure=error_receipt(exc)
    completion=dict(status='unavailable'if failure else'completed',failure=failure,calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(status=completion['status'],calls=len(calls),failure=failure)))


if __name__=='__main__':main()
