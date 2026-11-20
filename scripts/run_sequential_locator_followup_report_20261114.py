"""Complete report: fresh or exact cached native phase, then attribute followup."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.run_native_original_report_pair_20261114 import Trace,FixedSources
from scripts.experiment_error_receipt import error_receipt
from research_verify.evidence_flow import review_answer,review_claim_groups
from research_verify.sequential_review import sequential_english_review
from research_verify.evidence_fetch import EvidenceFetcher


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--native-call-budget',type=int,default=32);p.add_argument('--extra-call-budget',type=int,default=64)
    p.add_argument('--native-cache-attempt',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not 1<=a.native_call_budget<=64 or not 1<=a.extra_call_budget<=64:raise ValueError('Budget outside experimental limit')
    cases=_manifest_cases(a.case_manifest)
    if len(cases)!=1 or cases[0]['draft'] is None:raise ValueError('Exactly one original report required')
    case=cases[0];a.out_dir.mkdir(parents=True,exist_ok=False);report=case['draft'].read_text();sources=json.loads(case['source'].read_text())
    groups=review_claim_groups(report,native_documents(copy.deepcopy(sources)),sources,case['query'],60000)
    cache=[];cache_inputs=[]
    if a.native_cache_attempt:
        cache=json.loads((a.native_cache_attempt/'calls.json').read_text());cache=[c for c in cache if c['phase']=='native']
        assert json.loads((a.native_cache_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
        cache_inputs=[a.native_cache_attempt/'calls.json',a.native_cache_attempt/'completion.json']
        for c in cache:
            q=a.native_cache_attempt/'baseline'/f"call-{c['call_id']:03d}-prompt.txt"
            assert sha(q)==c['prompt_sha256'] and sha(q.with_name(q.name.replace('-prompt','-response')))==c['response_sha256']
            cache_inputs.extend([q,q.with_name(q.name.replace('-prompt','-response'))])
    files=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),a.case_manifest,case['source'],case['draft'],*cache_inputs,
        *[Path('local_deep_research/overlay')/f for f in ['engine_registry.py','module_whitelist.py','search_engine_europepmc.py']]]
    freeze={str(x):sha(x) for x in files};root=Path.cwd()
    for path in files:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');(a.out_dir/'original-report.txt').write_text(report)
    protocol=dict(scope='Complete archived-report post-writer comparison, original native review shared; not fresh retrieval/writer or independent outcome evaluation',
        case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],manifest_sha256=sha(a.case_manifest),
        original_report_sha256=sha(case['draft']),source_pack_sha256=sha(case['source']),source_count=len(sources),native_groups=len(groups),
        source_scope='Newly acquired original-namespace metadata/abstracts; not historical writer exposure or complete paper evidence',
        native_call_budget=a.native_call_budget,extra_call_budget=a.extra_call_budget,context_budget=60000,
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        common_native_settings=dict(identity_attributes=True,attribute_confirmation=True,confirmation_consistency=True),
        candidate_delta='Extra English review with bounded original-reference PDF followup and literal quote reselection; native baseline shared',
        candidate_flags=dict(original_reference_pdf_followup=True,literal_quote_reselection=True),
        native_cache_attempt=str(a.native_cache_attempt)if a.native_cache_attempt else None,native_cached_calls=len(cache),runtime_overlay_files=['engine_registry.py','module_whitelist.py','search_engine_europepmc.py'],runtime_host_alias='host.docker.internal:127.0.0.1',
        evidence_followup=dict(requests=16,seconds=90,rounds_per_group=2,web_search=False),
        budget_comparison='Additional verification has extra calls; no matched-cost or efficiency gain claimed',
        live_search=False,writer_generation=False,publication=False,save_time_citation_qc=False,
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(native_groups=len(groups),maximum_calls=a.native_call_budget+a.extra_call_budget)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1,
        'citation.identity_attribute_review':True,'citation.attribute_confirmation_review':True,'citation.confirmation_consistency_review':True})
    calls=[];phase='native';folder=a.out_dir/'baseline';folder.mkdir();trace=Trace(folder/'trace.jsonl');fetcher=FixedSources();working_sources=copy.deepcopy(sources)
    class Handler:
        settings_snapshot=snap
        def get_setting(self,k,d=None):return snap.get(k,d)
        def _create_documents(self,records):return native_documents(records)
        def _invoke_text(self,prompt,**kw):
            n=len(calls);entry=dict(call_id=n,phase=phase,stage=kw.get('stage'),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            try:
                if phase=='native' and a.native_cache_attempt:
                    c=cache[n];q=a.native_cache_attempt/'baseline'/f"call-{c['call_id']:03d}-prompt.txt"
                    assert c['stage']==kw.get('stage') and prompt==q.read_text()
                    raw=q.with_name(q.name.replace('-prompt','-response')).read_text();entry['origin']='cached_native'
                else:
                    response=self.model.invoke(prompt);raw=str(getattr(response,'content',response));entry['origin']='fresh'
                (folder/f'call-{n:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
    handler=Handler();native_budget=dict(remaining=a.native_call_budget)
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(handler.get_setting)})()):
        handler.model=get_llm(settings_snapshot=snap)
        baseline,docs,native_applied,native_pending,shown=review_answer(handler,case['query'],report,native_documents(working_sources),
            working_sources,trace,None,1,60000,dict(fetcher=fetcher),native_budget)
        (folder/'report.txt').write_text(baseline)
        if a.native_cache_attempt:assert len(calls)==len(cache)
        native_calls=len(calls);base_result=dict(report_sha256=sha(folder/'report.txt'),report_chars=len(baseline),model_calls=native_calls,
            native_applied=native_applied,native_unresolved=native_pending,remaining_calls=native_budget['remaining'],shown_source_ids=sorted(shown),
            supplement_requests=fetcher.events,quality_claim=None,newly_credited_corrections=0)
        (folder/'result.json').write_text(json.dumps(base_result,ensure_ascii=False,indent=2)+'\n')
        snap['citation.confirmation_evidence_followup']=True
        snap['citation.confirmation_attribute_evidence_followup']=True
        snap['citation.literal_quote_reselection']=True
        snap['citation.original_reference_pdf_followup']=True
        phase='sequential';folder=a.out_dir/'candidate';folder.mkdir();trace=Trace(folder/'trace.jsonl');(folder/'start-report.txt').write_text(baseline)
        acquisitions=[];transport=[]
        class RecordedFetcher(EvidenceFetcher):
            def read_bytes(self,url,**kw):
                n=len(transport);entry=dict(index=n,url=url,params=kw.get('params'),format='raw_bytes');transport.append(entry)
                try:
                    raw=super().read_bytes(url,**kw);path=a.out_dir/f'primary-response-{n:03d}.bin';path.write_bytes(raw)
                    entry.update(status='retrieved',sha256=sha(path),bytes=len(raw),file=path.name);return raw
                except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
                finally:(a.out_dir/'primary-transport.json').write_text(json.dumps(transport,indent=2)+'\n')
            def article(self,source):
                n=len(acquisitions);entry=dict(index=n,source_index=source.get('index'),source_before=copy.deepcopy(source));acquisitions.append(entry)
                try:
                    text=super().article(source)
                    if text:
                        path=a.out_dir/f'primary-article-{n:03d}.txt';path.write_text(text)
                        entry.update(status='acquired',sha256=sha(path),chars=len(text),file=path.name)
                    else:entry.update(status='unavailable')
                    return text
                except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
                finally:(a.out_dir/'primary-acquisitions.json').write_text(json.dumps(acquisitions,ensure_ascii=False,indent=2)+'\n')
            def web(self,*args,**kwargs):
                self.events.append(dict(status='web_not_exercised_in_primary_acquisition_experiment'));return []
        primary_fetcher=RecordedFetcher(snap,seconds=90,requests=16)
        extra_budget=dict(remaining=a.extra_call_budget)
        candidate,extra_applied,extra_pending,receipts=sequential_english_review(handler,case['query'],baseline,docs,working_sources,trace,extra_budget,network_state=dict(fetcher=primary_fetcher))
        (folder/'report.txt').write_text(candidate)
        result=dict(start_report_sha256=sha(folder/'start-report.txt'),report_sha256=sha(folder/'report.txt'),report_chars=len(candidate),
            additional_model_calls=len(calls)-native_calls,remaining_calls=extra_budget['remaining'],extra_applied=extra_applied,
            extra_unresolved=extra_pending,group_receipts=receipts,common_native_result=base_result,
            quality_claim=None,newly_credited_corrections=0)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'final-source-records.json').write_text(json.dumps(working_sources,ensure_ascii=False,indent=2)+'\n')
    completion=dict(fresh_model_calls=sum(c.get('origin')=='fresh'for c in calls),cached_native_calls=sum(c.get('origin')=='cached_native'for c in calls),primary_acquisitions=acquisitions,primary_transport=transport,calls=len(calls),baseline=base_result,candidate=result,shared_native_report_sha256=base_result['report_sha256'],
        working_source_records_unchanged=working_sources==sources,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),baseline_chars=len(baseline),candidate_chars=len(candidate),newly_credited_corrections=0)))


if __name__=='__main__':main()
