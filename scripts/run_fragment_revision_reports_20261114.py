"""Finite complete-report literal-fragment proposal/confirmation, never deployment."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.fragment_revision import revision_anchors,revision_prompt,parse_proposals,apply_proposals,confirmation_prompt,confirmation_decisions
from research_verify.canonical_fields import source_units
from research_verify.generation import format_source_documents,writer_source_query
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--cache-unchanged-attempt',type=Path)
    p.add_argument('--source-budget-chars',type=int,choices=[200000,240000],default=240000)
    p.add_argument('--material-query-mode',choices=['question','draft','protected'],default='question')
    p.add_argument('--index-preview-chars',type=int,choices=[24,100],default=100);a=p.parse_args()
    cases=_manifest_cases(a.case_manifest);assert len(cases)==2
    a.out_dir.mkdir(parents=True,exist_ok=False);paths=[a.case_manifest,Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')];jobs=[]
    for case in cases:
        preview_chars=case.get('index_preview_chars',a.index_preview_chars);report=case['draft'].read_text();sources=json.loads(case['source'].read_text());ids={int(s['index'])for s in sources}
        material_query=writer_source_query(case['query'],report,claim_directed=a.material_query_mode!='question');selection_receipts=[]
        material=format_source_documents(native_documents(sources),material_query,max_chars=a.source_budget_chars,required_ids=ids,protected_query=case['query']if a.material_query_mode=='protected'else None,selection_receipts=selection_receipts);units=source_units(material,ids);anchors=revision_anchors(report);prompt=revision_prompt(case['query'],report,material,anchors,units,index_preview_chars=preview_chars)
        if len(prompt)>400000:raise ValueError('Finite complete-report proposal context')
        folder=a.out_dir/case['case_id'];folder.mkdir();(folder/'original-report.txt').write_text(report);(folder/'source-material.txt').write_text(str(material));(folder/'source-units.json').write_text(json.dumps(units,ensure_ascii=False,indent=2)+'\n');(folder/'anchors.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2)+'\n')
        (folder/'selection-receipts.json').write_text(json.dumps(selection_receipts,ensure_ascii=False,indent=2)+'\n')
        jobs.append(dict(case=case,report=report,material=material,units=units,anchors=anchors,prompt=prompt,folder=folder,index_preview_chars=preview_chars));paths.extend([case['draft'],case['source']])
    if a.cache_unchanged_attempt:paths.extend([a.cache_unchanged_attempt/'calls.json',*a.cache_unchanged_attempt.glob('call-*-*.txt')])
    frozen={str(p):sha(p)for p in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    for path in paths:
        rel=path.relative_to(Path.cwd())if path.is_absolute()else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='Two complete original archived reports, minimal semantic model revisions then separate confirmation; no retrieval/writer regeneration/deployment or independent scoring',cases=[dict(case_id=j['case']['case_id'],index_preview_chars=j['index_preview_chars'],query=j['case']['query'],query_sha256=j['case']['query_sha256'],original_report_sha256=sha(j['case']['draft']),source_pack_sha256=sha(j['case']['source']),report_chars=len(j['report']),material_chars=len(j['material']),sources=len(j['material'].views),source_units=len(j['units']),anchors=len(j['anchors']),proposal_prompt_chars=len(j['prompt']))for j in jobs],cache_unchanged_attempt=str(a.cache_unchanged_attempt)if a.cache_unchanged_attempt else None,maximum_calls=4,maximum_prompt_chars=400000,source_budget_chars=a.source_budget_chars,material_query_mode=a.material_query_mode,index_preview_chars=a.index_preview_chars,max_tokens=6000,max_retries=0,temperature=0,atomic_batch=True,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan,ensure_ascii=False));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':180,'llm.max_retries':0,'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];results=[]
    def invoke(prompt,stage):
        if len(calls)>=4 or len(prompt)>400000:raise ValueError('Finite fragment revision invocation bound')
        i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,stage=stage,prompt_chars=len(prompt),prompt_sha256=sha(pp));calls.append(row)
        try:
            cached=None
            if a.cache_unchanged_attempt:
                matches=[c for c in json.loads((a.cache_unchanged_attempt/'calls.json').read_text())if c['stage']==stage]
                if len(matches)==1:
                    c=matches[0];old=a.cache_unchanged_attempt/f"call-{c['index']:02d}-prompt.txt"
                    if c['status']=='returned'and prompt==old.read_text()and sha(old)==c['prompt_sha256']:cached=c
            if cached is not None:
                old=a.cache_unchanged_attempt/f"call-{cached['index']:02d}-response.txt";assert sha(old)==cached['response_sha256']
                raw=old.read_text();metadata=cached['response_metadata'];row.update(origin='strict_cache',cached_from=str(old))
            else:
                response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata;row['origin']='fresh'
            rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);return raw
        except Exception as exc:row.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        for job in jobs:
            case=job['case'];answer=job['report'];result=dict(case_id=case['case_id'],status='prepared',parsed=None,confirmation=None,changes=[])
            try:
                parsed=parse_proposals(invoke(job['prompt'],case['case_id']+':propose'),job['report'],job['anchors'],job['units']);result['parsed']=parsed
                proposed=apply_proposals(job['report'],parsed['proposals']);(job['folder']/'proposal-report.txt').write_text(proposed)
                if parsed['proposals']:
                    decision=confirmation_decisions(invoke(confirmation_prompt(case['query'],proposed,job['material'],job['anchors'],job['units'],parsed['proposals'],index_preview_chars=job['index_preview_chars']),case['case_id']+':confirm'),parsed['proposals']);result['confirmation']=decision
                    if decision['batch_approved']:answer=proposed;result['changes']=parsed['proposals']
                result['status']='completed'
            except Exception as exc:result.update(status='unavailable',failure=error_receipt(exc))
            (job['folder']/'candidate-report.txt').write_text(answer);result.update(report_sha256=sha(job['folder']/'candidate-report.txt'),report_chars=len(answer),original_report_sha256=sha(job['folder']/'original-report.txt'));results.append(result)
    complete=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),quality_claim=None,newly_credited_corrections=0,production_changes=False)
    (a.out_dir/'completion.json').write_text(json.dumps(complete,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls),results=[dict(case_id=r['case_id'],status=r['status'],changes=len(r['changes']))for r in results])))


if __name__=='__main__':main()
