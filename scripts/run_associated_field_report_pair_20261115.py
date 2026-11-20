"""Bounded full-original-report/source5 experiment, not whole-task or independent adjudication."""
import argparse, hashlib, json
from pathlib import Path

from research_verify.canonical_fields import source_units
from research_verify.field_comparison import compare_and_edit, comparison_prompt, observations_from_notes
from research_verify.generation import format_source_documents
from research_verify.request_fields import original_anchors
from research_verify.request_additions import parse_request_plan
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt

R=Path('evaluation/frontier-strategy-20261113')
TOKENIZER=Path('/data1/maxw/.cache/uv/archive-v0/4uK_3d65AxUtkUBO/litellm/litellm_core_utils/tokenizers/deepseek_tokenizer.json')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def prepare():
    casepath=R/'source-span-if-original-inputs-20261115-v1/case-manifest.json'
    case,=read(casepath)['cases'];reportpath=Path(case['draft']);pack=Path(case['source'])
    assert sha(reportpath)==case['draft_sha256'] and sha(pack)==case['source_sha256']
    report=reportpath.read_text();assert len(report)==58404
    record,=[s for s in read(pack) if str(s['index'])=='5']
    material=format_source_documents(native_documents([record]),case['query'],max_chars=120000,required_ids={5})
    prior=R/'request-canonical-if-model-20261114-v1/attempt'
    units=source_units(material,{5});assert units==read(prior/'source-units.json')
    assert material.views[5]['text']==record['fetched_content']
    requirements=parse_request_plan((prior/'call-00-response.txt').read_text(),case['query'])
    notespath=R/'multi-requirement-if-model-20261115-v1/attempt/completion.json'
    readings=read(notespath);assert readings['status']=='completed_reading_diagnostic'
    anchors=original_anchors(report)
    jobs=[dict(arm=row['arm'],notes=[row['parsed']]) for row in readings['results']]
    assert [j['arm']for j in jobs]==['single_requirement','multiple_requirements']
    inputs=[casepath,reportpath,pack,notespath,prior/'source-units.json',prior/'call-00-response.txt',TOKENIZER]
    return case,report,material,requirements,anchors,jobs,inputs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path)
    p.add_argument('--replay',type=Path);a=p.parse_args();assert not(a.execute and a.replay)
    case,report,material,requirements,anchors,jobs,inputs=prepare()
    # The frozen bundled tokenizer is a budget estimate, not a verified endpoint tokenizer.
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tokenizer=Tokenizer.from_file(str(TOKENIZER))
    def tokens(text):return len(tokenizer.encode(text,add_special_tokens=False).ids)
    initial=[]
    for job in jobs:
        obs=observations_from_notes(job['notes'],requirements)
        prompt=comparison_prompt(case['query'],report,material,requirements,anchors,obs)
        estimate=tokens(prompt)
        assert estimate+12000+12000+8192<=131072, 'Comparison plus bounded dynamic/output/reserve cannot fit'
        initial.append(dict(arm=job['arm'],prompt=prompt,prompt_chars=len(prompt),estimated_tokens=estimate,observations=obs))
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),Path('scripts/experiment_error_receipt.py'),Path('scripts/prepare_source_detail_material_20261114.py'),
          Path('scripts/run_native_original_report_pair_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
          *Path('local_deep_research/research_verify').glob('*.py')]
    if a.execute:
        assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
        for path,h in read(a.preflight/'prestart-freeze.json').items():assert sha(Path(path))==h
        inputs.extend(a.preflight/n for n in ['completion.json','prestart-freeze.json','plan.json'])
    if a.replay:inputs.extend(p for p in a.replay.rglob('*') if p.is_file() and 'code'not in p.parts)
    frozen={str(p):sha(p)for p in [*inputs,*code]};write(a.out_dir/'prestart-freeze.json',frozen)
    for path in code:
        dest=a.out_dir/'code'/path.resolve().relative_to(Path.cwd());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,
              'llm.max_retries':0,'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=6,settings=settings,
        original_question=case['query'],original_report_sha256=case['draft_sha256'],source_pack_sha256=case['source_sha256'],
        protocol='Two prior fresh fallible readings, same full original report/question and complete acquired source5. Compare every distinct observation, propose at most3 minimal edits, separately confirm using the same source/full report. No new Reader/search/Writer/native run. Different earlier sampled readings confound association-schema attribution. Only source5 is supplied, NOT all42sources or20eligiblepapers. Other report claims remain unassessed. No hidden expected edits/counts/gold.',
        source_ids=[5],complete_original_report_chars=len(report),actual_source_chars=len(material.views[5]['text']),
        complete_source_unit_count=len(source_units(material,{5})),
        preflight_inputs=[{k:v for k,v in row.items()if k not in {'prompt','observations'}} for row in initial],
        tokenizer_sha256=sha(TOKENIZER),token_budget=131072,output_budget=12000,input_reserve=8192,
        tokenizer_matches_endpoint='unverified; input estimate enlarged by10percent at invocation',
        independent_correction_credit=0,production_deployment=False,independent_assessment_complete=False))
    for i,row in enumerate(initial):
        (a.out_dir/f'comparison-{i:02d}-prompt.txt').write_text(row['prompt'])
        write(a.out_dir/f'observations-{i:02d}.json',row['observations'])
    (a.out_dir/'original-report.txt').write_text(report);write(a.out_dir/'source-material.json',dict(text=str(material),views=material.views))
    write(a.out_dir/'anchors.json',anchors);write(a.out_dir/'requirements.json',requirements)
    calls=[];results=[];model=None;failure=None
    if a.execute or a.replay:
        for index,job in enumerate(jobs):
            folder=a.out_dir/f'arm-{index:02d}';folder.mkdir();trace=Trace(folder/'trace.jsonl')
            local_calls=[]
            def invoke(prompt,stage):
                nonlocal model
                assert len(local_calls)<3 and len(calls)<6
                estimate=tokens(prompt);assert int(estimate*1.1)+12000+8192<=131072,'Dynamic complete prompt exceeds finite budget'
                n=len(calls);path=a.out_dir/f'call-{n:02d}-prompt.txt';path.write_text(prompt)
                row=dict(index=n,arm=job['arm'],stage=stage,status='started',prompt_sha256=sha(path),prompt_chars=len(prompt),estimated_tokens=estimate)
                calls.append(row);local_calls.append(row);write(a.out_dir/'calls.json',calls)
                try:
                    if stage=='per_field_comparison':
                        assert prompt==initial[index]['prompt']
                        if a.preflight:assert path.read_text()==(a.preflight/f'comparison-{index:02d}-prompt.txt').read_text()
                    if a.replay:
                        old=read(a.replay/'calls.json')[n];assert old['stage']==stage and old['arm']==row['arm'] and old['prompt_sha256']==row['prompt_sha256'] and old['status']=='returned'
                        responsepath=a.replay/f'call-{n:02d}-response.txt';assert sha(responsepath)==old['response_sha256']
                        raw=responsepath.read_text();meta=old['response_metadata'];row['origin']='strict_replay'
                    else:
                        if model is None:
                            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                            from local_deep_research.config.thread_settings import settings_context
                            from local_deep_research.config.llm_config import get_llm
                            defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                            effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings
                            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                        row['origin']='fresh_model';response=model.invoke(prompt);raw=str(response.content);meta=response.response_metadata
                    responsepath=a.out_dir/f'call-{n:02d}-response.txt';responsepath.write_text(raw)
                    row.update(status='returned',response_sha256=sha(responsepath),response_metadata=meta)
                    assert meta.get('finish_reason')=='stop'
                    return raw
                except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
                finally:write(a.out_dir/'calls.json',calls)
            try:
                answer,result=compare_and_edit(case['query'],report,material,requirements,anchors,job['notes'],{5},invoke,trace)
                (folder/'candidate-report.txt').write_text(answer);write(folder/'result.json',result)
                results.append(dict(arm=job['arm'],result=result,report_sha256=sha(folder/'candidate-report.txt'),report_chars=len(answer)))
                if a.replay:assert read(a.replay/f'arm-{index:02d}/result.json')==result
            except Exception as exc:failure=error_receipt(exc);break
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('preflight_only'if not(a.execute or a.replay)else'complete_report_source_targeted_diagnostic'),
        failure=failure,fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),logical_calls=len(calls),results=results,
        frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),independent_assessment_complete=False,independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,logical_calls=len(calls),arms=[dict(arm=r['arm'],changes=len(r['result']['changes']))for r in results])))
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
