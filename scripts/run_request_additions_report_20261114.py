"""Complete archived report plus source-confirmed requested-field additions.

No writer regeneration, production hook or independent quality adjudication.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from research_verify.request_additions import (request_plan_prompt,parse_request_plan,gap_prompt,
    parse_gaps,confirmation_prompt,apply_confirmed_additions)
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.evidence_flow import supplement,required_sources
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    cases=_manifest_cases(a.case_manifest);assert len(cases)==1
    case=cases[0];report=case['draft'].read_text();sources=json.loads(case['source'].read_text());working=copy.deepcopy(sources)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    files=[a.case_manifest,case['draft'],case['source'],Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
        Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),
        *[Path('local_deep_research/overlay')/n for n in ['engine_registry.py','module_whitelist.py','search_engine_europepmc.py']]]
    freeze={str(path):sha(path)for path in files};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in files:
        if str(path).startswith(('scripts/','local_deep_research/'))or str(path).startswith('/workspace/scripts/'):
            rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'original-report.txt').write_text(report)
    registered={int(s['index'])for s in sources};required=required_sources(report,sources)
    def material():
        return format_source_documents(native_documents(working),case['query'],max_chars=120000,required_ids=required&registered)
    shown=material()
    protocol=dict(scope='Complete original archived-report request-led addition candidate; no independent outcome evaluation',
        case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],manifest_sha256=sha(a.case_manifest),
        original_report_sha256=sha(case['draft']),source_pack_sha256=sha(case['source']),original_report_chars=len(report),
        initial_material_chars=len(shown),registered_sources=len(sources),unregistered_report_citations=sorted(required-registered),
        maximum_model_calls=4,maximum_prompt_chars=220000,source_budget_chars=120000,
        fetch_budget=dict(logical_requests=6,seconds=60,maximum_requested_ids=4),
        native_complete_report_check_rerun=False,writer_generation=False,live_search=False,publication=False,
        native_consistency_setting=True,save_time_citation_qc=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(protocol,ensure_ascii=False));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,
        'llm.request_timeout':180,'llm.max_retries':1,'citation.original_reference_document_followup':True,
        'general.enable_fact_checking':True,'verify.enable_citation_qc':False})
    calls=[];transport=[];articles=[];trace=Trace(a.out_dir/'trace.jsonl')
    class Recorded(EvidenceFetcher):
        def read_bytes(self,url,**kw):
            event=dict(index=len(transport),url=url,params=kw.get('params'));transport.append(event)
            try:
                raw=super().read_bytes(url,**kw);path=a.out_dir/f"response-{event['index']:02d}.bin";path.write_bytes(raw)
                event.update(status='retrieved',file=path.name,sha256=sha(path),bytes=len(raw));return raw
            except Exception as exc:event.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'transport.json').write_text(json.dumps(transport,indent=2)+'\n')
        def article(self,source):
            event=dict(source_before=copy.deepcopy(source));articles.append(event)
            try:
                text=super().article(source)
                if text:
                    path=a.out_dir/f'article-{len(articles):02d}.txt';path.write_text(text)
                    event.update(status='acquired',file=path.name,sha256=sha(path),chars=len(text))
                else:event['status']='unavailable'
                return text
            except Exception as exc:event.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'articles.json').write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n')
    fetch=Recorded(snap,requests=6,seconds=60)
    def invoke(prompt,stage):
        if len(calls)>=4 or len(prompt)>220000:raise ValueError('Request addition invocation bound')
        index=len(calls);entry=dict(index=index,stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
        path=a.out_dir/f'call-{index:02d}-prompt.txt';path.write_text(prompt)
        try:
            raw=str(model.invoke(prompt).content);reply=a.out_dir/f'call-{index:02d}-response.txt';reply.write_text(raw)
            entry.update(status='returned',response_sha256=sha(reply));return raw
        except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
        finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
    answer=report;requirements=[];gap=None;insertions=[];decisions=[];failure=None
    try:
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
            model=get_llm(settings_snapshot=snap)
            requirements=parse_request_plan(invoke(request_plan_prompt(case['query']),'request_plan'),case['query'])
            for round_no in range(2):
                shown=material();trace.record('request_gap_input',dict(round=round_no,material=str(shown),views=shown.views,requirements=requirements))
                gap=parse_gaps(invoke(gap_prompt(case['query'],report,shown,requirements),'request_gap_review'),report,shown,requirements)
                trace.record('request_gap_review',dict(round=round_no,**gap))
                if round_no or not gap['needs_articles']:break
                needed=[i for i in gap['needs_articles']if i in registered]
                acquired=supplement([dict(status='insufficient_evidence',source_id=i,request={'kind':'article'})for i in needed],working,fetch,register=None,trace=trace)
                if not acquired:break
            if gap['eligible']:
                prompt=confirmation_prompt(case['query'],report,shown,requirements,gap['eligible'])
                answer,insertions,decisions=apply_confirmed_additions(invoke(prompt,'request_addition_confirmation'),report,gap['eligible'])
    except Exception as exc:failure=error_receipt(exc)
    (a.out_dir/'candidate-report.txt').write_text(answer)
    (a.out_dir/'source-records.json').write_text(json.dumps(working,ensure_ascii=False,indent=2)+'\n')
    completion=dict(status='unavailable'if failure else'completed',failure=failure,calls=len(calls),requirements=requirements,
        final_gap=gap,insertions=insertions,decisions=decisions,report_chars=len(answer),report_sha256=sha(a.out_dir/'candidate-report.txt'),
        original_report_sha256=sha(a.out_dir/'original-report.txt'),original_preserved_as_insertions=True,
        source_identity_metadata_unchanged=all(s=={k:v for k,v in t.items()if k!='fetched_content'}for s,t in zip(sources,working,strict=True)),
        transport=transport,articles=articles,frozen_inputs_unchanged=all(sha(Path(path))==digest for path,digest in freeze.items()),
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=completion['status'],calls=len(calls),insertions=len(insertions),report_chars=len(answer),failure=failure),ensure_ascii=False))


if __name__=='__main__':main()
