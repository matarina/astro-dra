"""Finite report-blind source reading before complete-report omission comparison.

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
    p.add_argument('--canonical-source-units',action='store_true');a=p.parse_args()
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
    minimum_gap_chars=len(unit_gap_prompt(case['query'],report,shown,[],anchors,[],units))if a.canonical_source_units else None
    if minimum_gap_chars is not None and minimum_gap_chars>a.prompt_budget_chars:
        raise ValueError('Canonical complete-report prompt cannot fit even before reading notes')
    a.out_dir.mkdir(parents=True,exist_ok=False)
    files=[a.case_manifest,case['draft'],case['source'],Path(__file__),
        *[Path('scripts')/n for n in ['prepare_source_detail_material_20261114.py',
          'run_native_original_report_pair_20261114.py','run_hallucination_next_phase_experiment_20261113.py','experiment_error_receipt.py']],
        Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),
        *[Path('local_deep_research/overlay')/n for n in ['engine_registry.py','module_whitelist.py','search_engine_europepmc.py']]]
    freeze={str(path):sha(path)for path in files};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in files:
        rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'original-report.txt').write_text(report)
    (a.out_dir/'anchors.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2)+'\n')
    if a.canonical_source_units:(a.out_dir/'source-units.json').write_text(json.dumps(units,ensure_ascii=False,indent=2)+'\n')
    protocol=dict(scope='Report-blind source fields then complete original report additions; unassessed scientific outcome',
        case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],manifest_sha256=sha(a.case_manifest),
        original_report_sha256=sha(case['draft']),source_pack_sha256=sha(case['source']),original_report_chars=len(report),
        initial_material_chars=len(shown),registered_sources=len(sources),unregistered_report_citations=sorted(required-registered),
        anchor_count=len(anchors),source_reader_batches=len(batches),maximum_model_calls=len(batches)+3,
        maximum_prompt_chars=a.prompt_budget_chars,source_budget_chars=a.source_budget_chars,
        report_blind_reading_ids=sorted(reading_ids),maximum_fields_per_source=a.maximum_fields_per_source,
        canonical_source_units=a.canonical_source_units,canonical_maximum_fields_per_source=12 if a.canonical_source_units else None,
        minimum_comparison_prompt_chars=minimum_gap_chars,
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
            response=model.invoke(prompt);raw=str(response.content)
            reply=a.out_dir/f'call-{index:02d}-response.txt';reply.write_text(raw)
            entry.update(status='returned',response_sha256=sha(reply),response_metadata=response.response_metadata);return raw
        except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2,default=str)+'\n')
    answer=report;requirements=[];notes=[];gap=None;insertions=[];decisions=[];failure=None
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
            if a.canonical_source_units:
                gap=parse_unit_gaps(invoke(unit_gap_prompt(case['query'],report,shown,requirements,anchors,notes,units),
                    'canonical_request_gap_review'),report,shown,requirements,anchors,reading_ids)
            else:
                gap=parse_gaps(invoke(gap_prompt(case['query'],report,shown,requirements,anchors=anchors,field_notes=notes),
                    'positioned_request_gap_review'),report,shown,requirements,anchors=anchors)
            trace.record('request_gap_review',gap)
            if gap['eligible']:
                answer,insertions,decisions=apply_confirmed_additions(invoke(
                    confirmation_prompt(case['query'],report,shown,requirements,gap['eligible']),
                    'request_addition_confirmation'),report,gap['eligible'])
    except Exception as exc:failure=error_receipt(exc)
    (a.out_dir/'candidate-report.txt').write_text(answer)
    completion=dict(status='unavailable'if failure else'completed',failure=failure,calls=len(calls),requirements=requirements,
        field_notes=notes,final_gap=gap,insertions=insertions,decisions=decisions,
        report_chars=len(answer),report_sha256=sha(a.out_dir/'candidate-report.txt'),original_report_sha256=sha(a.out_dir/'original-report.txt'),
        original_preserved_as_insertions=True,source_records_unchanged=sha(case['source'])==protocol['source_pack_sha256'],
        article_requests_not_executed=gap.get('needs_articles',[])if gap else[],
        frozen_inputs_unchanged=all(sha(Path(path))==digest for path,digest in freeze.items()),
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=completion['status'],calls=len(calls),insertions=len(insertions),report_chars=len(answer),failure=failure),ensure_ascii=False))


if __name__=='__main__':main()
