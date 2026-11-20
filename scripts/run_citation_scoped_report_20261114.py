"""Finite citation-scoped per-observation comparisons and separately confirmed edits.

No production caller, new retrieval, writer regeneration or independent scoring.
"""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.request_fields import (atomic_request_prompt,original_anchors,
    source_field_prompt,parse_source_fields)
from research_verify.canonical_fields import (source_units,unit_field_prompt,parse_unit_fields,
    unit_gap_prompt,parse_unit_gaps)
from research_verify.request_additions import (parse_request_plan,gap_prompt,parse_gaps,
    confirmation_prompt,apply_confirmed_additions)
from research_verify.citation_field_scope import compare_and_edit,citation_report_scope
from research_verify.evidence_flow import required_sources
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--read-source-ids',nargs='+',type=int,help='Read these registered sources blind; ALL sources still enter report comparison')
    p.add_argument('--source-budget-chars',type=int,default=120000)
    p.add_argument('--prompt-budget-chars',type=int,default=280000)
    p.add_argument('--maximum-fields-per-source',type=int,default=3)
    p.add_argument('--canonical-source-units',action='store_true')
    p.add_argument('--cache-first-stages',type=Path)
    p.add_argument('--maximum-observations',type=int,default=12);a=p.parse_args()
    if not 1<=a.maximum_observations<=12:raise ValueError('Finite observation call bound')
    if not a.canonical_source_units:raise ValueError('Field comparison requires canonical source units')
    if not 120000<=a.source_budget_chars<=300000 or not 280000<=a.prompt_budget_chars<=400000:
        raise ValueError('Finite context budget')
    if not 1<=a.maximum_fields_per_source<=8:raise ValueError('Finite field bound')
    cases=_manifest_cases(a.case_manifest);assert len(cases)==1
    case=cases[0];report=case['draft'].read_text();sources=json.loads(case['source'].read_text())
    if not 1<=len(sources)<=48:raise ValueError('Finite source-reader batch bound')
    anchors=original_anchors(report);registered={int(s['index'])for s in sources};required=required_sources(report,sources)
    shown=format_source_documents(native_documents(sources),case['query'],max_chars=a.source_budget_chars,required_ids=registered)
    reading_ids=set(a.read_source_ids)if a.read_source_ids else registered
    if not reading_ids<=registered:raise ValueError('Unregistered source reading ID')
    reading_sources=[s for s in sources if int(s['index'])in reading_ids]
    batches=[reading_sources[i:i+24]for i in range(0,len(reading_sources),24)]
    units=source_units(shown,reading_ids)if a.canonical_source_units else[]
    minimum_gap_chars=None
    scope_receipts=[]
    for sid in sorted(reading_ids):
        scoped=citation_report_scope(report,sid,anchors)
        scope_receipts.append(dict(source_id=sid,report_units=len(scoped['report_units']),
            report_text_chars=sum(len(r['text'])for r in scoped['report_units']),
            unassigned_units_outside_scope=len(scoped['unassigned_outside_scope'])))
    if minimum_gap_chars is not None and minimum_gap_chars>a.prompt_budget_chars:
        raise ValueError('Canonical complete-report prompt cannot fit even before reading notes')
    a.out_dir.mkdir(parents=True,exist_ok=False)
    files=[a.case_manifest,case['draft'],case['source'],Path(__file__),
        *[Path('scripts')/n for n in ['prepare_source_detail_material_20261114.py',
          'run_native_original_report_pair_20261114.py','run_hallucination_next_phase_experiment_20261113.py','experiment_error_receipt.py']],
        Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),
        *[Path('local_deep_research/overlay')/n for n in ['engine_registry.py','module_whitelist.py','search_engine_europepmc.py']]]
    if a.cache_first_stages:
        files.extend([a.cache_first_stages/'calls.json',a.cache_first_stages/'plan.json',
            *[a.cache_first_stages/f'call-{i:02d}-{kind}.txt'for i in range(2)for kind in ['prompt','response']]])
    freeze={str(path):sha(path)for path in files};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in files:
        rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'original-report.txt').write_text(report)
    (a.out_dir/'anchors.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2)+'\n')
    if a.canonical_source_units:(a.out_dir/'source-units.json').write_text(json.dumps(units,ensure_ascii=False,indent=2)+'\n')
    protocol=dict(scope='Citation-scoped per-observation comparison then complete-report model-confirmed editing; unassessed scientific outcome',
        case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],manifest_sha256=sha(a.case_manifest),
        original_report_sha256=sha(case['draft']),source_pack_sha256=sha(case['source']),original_report_chars=len(report),
        initial_material_chars=len(shown),registered_sources=len(sources),unregistered_report_citations=sorted(required-registered),
        anchor_count=len(anchors),source_reader_batches=len(batches),maximum_model_calls=len(batches)+3+a.maximum_observations,
        maximum_prompt_chars=a.prompt_budget_chars,source_budget_chars=a.source_budget_chars,
        report_blind_reading_ids=sorted(reading_ids),maximum_fields_per_source=a.maximum_fields_per_source,
        canonical_source_units=a.canonical_source_units,canonical_maximum_fields_per_source=12 if a.canonical_source_units else None,
        minimum_comparison_prompt_chars=minimum_gap_chars,citation_scope_receipts=scope_receipts,maximum_observations=a.maximum_observations,
        scoped_prompt_char_bound=48000,comparison_max_tokens=1200,editor_confirmation_max_tokens=4000,strict_cache_first_two_stages=str(a.cache_first_stages)if a.cache_first_stages else None,
        native_complete_report_check_rerun=False,writer_generation=False,live_search=False,live_article_fetch=False,
        publication=False,native_consistency_setting=True,save_time_citation_qc=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(protocol,ensure_ascii=False));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,
        'llm.request_timeout':180,'llm.max_retries':1,'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];trace=Trace(a.out_dir/'trace.jsonl')
    def invoke(prompt,stage):
        if len(calls)>=protocol['maximum_model_calls']or len(prompt)>protocol['maximum_prompt_chars']:
            raise ValueError('Source-field invocation bound')
        index=len(calls);entry=dict(index=index,stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),prompt_chars=len(prompt));calls.append(entry)
        path=a.out_dir/f'call-{index:02d}-prompt.txt';path.write_text(prompt)
        try:
            if a.cache_first_stages and index<2:
                prior=json.loads((a.cache_first_stages/'calls.json').read_text())[index]
                assert prior['stage']==stage and prior['status']=='returned'
                assert prompt==(a.cache_first_stages/f'call-{index:02d}-prompt.txt').read_text()
                cached=a.cache_first_stages/f'call-{index:02d}-response.txt';assert sha(cached)==prior['response_sha256']
                raw=cached.read_text();entry.update(origin='strict_cache',cached_from=str(cached))
                metadata=prior.get('response_metadata',{})
            else:
                entry['request_max_tokens']=1200 if stage.startswith('citation_field_comparison_')else 4000
                response=model.bind(max_tokens=entry['request_max_tokens']).invoke(prompt);raw=str(response.content);metadata=response.response_metadata;entry['origin']='fresh'
            reply=a.out_dir/f'call-{index:02d}-response.txt';reply.write_text(raw)
            entry.update(status='returned',response_sha256=sha(reply),response_metadata=metadata);return raw
        except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    answer=report;requirements=[];notes=[];result=None;failure=None
    try:
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
            model=get_llm(settings_snapshot=snap)
            requirements=parse_request_plan(invoke(atomic_request_prompt(case['query']),'atomic_request_plan'),case['query'])
            for batch_no,batch in enumerate(batches):
                batch_material=format_source_documents(native_documents(batch),case['query'],max_chars=a.source_budget_chars,
                    required_ids={int(s['index'])for s in batch})
                trace.record('report_blind_field_input',dict(batch=batch_no,material=str(batch_material),views=batch_material.views))
                if a.canonical_source_units:
                    batch_units=source_units(batch_material,{int(s['index'])for s in batch})
                    assert batch_units==[u for u in units if u['source_id']in {int(s['index'])for s in batch}]
                    fields=parse_unit_fields(invoke(unit_field_prompt(case['query'],requirements,batch_units),
                        'report_blind_canonical_fields'),requirements,batch_units)
                else:
                    fields=parse_source_fields(invoke(source_field_prompt(case['query'],requirements,batch_material,
                        maximum_fields=a.maximum_fields_per_source),'report_blind_source_fields'),requirements,batch_material,
                        maximum_fields=a.maximum_fields_per_source)
                notes.append(dict(batch=batch_no,**fields));trace.record('report_blind_field_result',notes[-1])
            trace.record('request_gap_input',dict(material=str(shown),views=shown.views,requirements=requirements))
            answer,result=compare_and_edit(case['query'],report,shown,requirements,anchors,notes,reading_ids,invoke,trace,maximum_observations=a.maximum_observations)
    except Exception as exc:failure=error_receipt(exc)
    (a.out_dir/'candidate-report.txt').write_text(answer)
    completion=dict(status='unavailable'if failure else'completed',failure=failure,calls=len(calls),requirements=requirements,
        field_notes=notes,field_result=result,
        report_chars=len(answer),report_sha256=sha(a.out_dir/'candidate-report.txt'),original_report_sha256=sha(a.out_dir/'original-report.txt'),
        original_preserved_outside_model_confirmed_spans=True,source_records_unchanged=sha(case['source'])==protocol['source_pack_sha256'],
        live_article_fetch=False,fresh_calls=sum(c.get('origin')=='fresh'for c in calls),cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),
        frozen_inputs_unchanged=all(sha(Path(path))==digest for path,digest in freeze.items()),
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=completion['status'],calls=len(calls),changes=len(result['changes'])if result else 0,report_chars=len(answer),failure=failure),ensure_ascii=False))


if __name__=='__main__':main()
