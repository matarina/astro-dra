"""Matched complete native synthesis, real inherited draft vs existing fresh flag.

Shared source-reading response requires exact prompt bytes. No live retrieval,
publication, independent adjudication or production configuration changes.
"""
import argparse,copy,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt
from research_verify import evidence_flow


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class FixedSources:
    def __init__(self):self.events=[]
    def record(self,*args,**kwargs):return None
    def pmc_identifiers(self,*args,**kwargs):return {}
    def article(self,source):
        self.events.append(dict(kind='article',source_id=source.get('index'),status='fixed_source_unavailable'));return None
    def web(self,*args,**kwargs):
        self.events.append(dict(kind='web',status='fixed_source_unavailable'));return []


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    cases=_manifest_cases(a.case_manifest);assert len(cases)==1;case=cases[0]
    original=case['draft'].read_text();assert original.strip();sources=json.loads(case['source'].read_text());a.out_dir.mkdir(exist_ok=False)
    files=[a.case_manifest,case['draft'],case['source'],Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    freeze={str(f):sha(f)for f in files};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    clock=datetime.now(timezone.utc)
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock
    settings={'general.enable_fact_checking':True,'verify.enable_citation_qc':False,'citation.enable_source_reading':True,'citation.enable_source_reading_roles':False,'citation.fresh_evidence_synthesis':False,'citation.source_context_chars':200000,'citation.max_review_calls':6,'citation.fetch_cited_source_bodies_before_writing':False,'citation.claim_directed_source_context':False,'citation.identity_attribute_review':False,'citation.semantic_passage_ranking':False,'llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,'llm.max_retries':0}
    plan=dict(scope='Complete actual native synthesis using original request and nonempty archived report; candidate ONLY existing fresh_evidence_synthesis flag, shared exact source-reading prompt/reply; no retrieval/publication/independent scoring',case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],source_pack_sha256=sha(case['source']),source_count=len(sources),original_report_sha256=sha(case['draft']),original_report_chars=len(original),settings=settings,fixed_writer_clock=clock.isoformat(),maximum_calls=16,maximum_prompt_chars=300000,maximum_native_calls_per_arm=6,arms=['inherited','fresh'],quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    model=None
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        from local_deep_research.config.thread_settings import settings_context
        from local_deep_research.config.llm_config import get_llm
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:settings.get(k,d))})()):model=get_llm(settings_snapshot=settings)
    calls=[];shared={};results=[];writer_prompts={};reader_prompts={}
    for arm in plan['arms']:
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');arm_sources=copy.deepcopy(sources);fetch=FixedSources()
        class Handler:
            stream_callback=None
            settings_snapshot=settings|{'citation.fresh_evidence_synthesis':arm=='fresh'}
            evidence_fetcher=fetch
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def is_fact_checking_enabled(self):return True
            def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _no_sources_response(self,q):raise ValueError('No actual source material')
            def _invoke_text(self,prompt,trace=None,stage='model'):
                if len(calls)>=16 or len(prompt)>300000:raise ValueError('Finite complete-pair call bound')
                i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,arm=arm,stage=stage,prompt_sha256=sha(pp),prompt_chars=len(prompt));calls.append(row)
                if stage=='writer':writer_prompts[arm]=prompt
                if stage=='source_reading':reader_prompts[arm]=prompt
                try:
                    if stage=='source_reading'and arm=='fresh':
                        if prompt not in shared:raise ValueError('Paired source-reading input differs')
                        raw,metadata=shared[prompt];row['origin']='strict_shared_source_reading'
                    elif not a.execute:
                        raw=original if stage=='writer'else('{"readings":[]}'if stage=='source_reading'else'{"issues":[]}');metadata={};row['origin']='preflight_placeholder'
                    else:
                        response=model.invoke(prompt);raw=str(getattr(response,'content',response));metadata=getattr(response,'response_metadata',{});row['origin']='fresh_model'
                    if stage=='source_reading':shared[prompt]=(raw,metadata)
                    rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);return raw
                except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
                finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2,default=str)+'\n')
        try:
            result=evidence_flow.synthesize(Handler(),case['query'],arm_sources,original,trace)
            answer=result['content'];(folder/'report.txt').write_text(answer)
            row=dict(arm=arm,status='completed',report_chars=len(answer),report_sha256=sha(folder/'report.txt'),native_review=result['evidence_review'],sources=arm_sources,supplement_requests=fetch.events)
        except Exception as exc:row=dict(arm=arm,status='unavailable',failure=error_receipt(exc))
        (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str)+'\n');results.append(row)
    matched=dict(both_writer_requests=all(x in writer_prompts for x in plan['arms']),shared_reading_requests=reader_prompts.get('inherited')==reader_prompts.get('fresh')and bool(reader_prompts),same_source_material_notes_scope_and_time=False,nonempty_draft_in_inherited=False,draft_withheld_in_fresh=False)
    if matched['both_writer_requests']:
        matched.update(same_source_material_notes_scope_and_time=writer_prompts['inherited'].split('New Sources:\n',1)[1]==writer_prompts['fresh'].split('New Sources:\n',1)[1],nonempty_draft_in_inherited=original in writer_prompts['inherited'],draft_withheld_in_fresh=original not in writer_prompts['fresh'])
        assert all(matched.values()),matched
    completion=dict(arms=[{k:v for k,v in x.items()if k!='sources'}for x in results],pair_invariance=matched,frozen_inputs_unchanged=all(sha(Path(f))==h for f,h in freeze.items()),logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),shared_reading_calls=sum(c.get('origin')=='strict_shared_source_reading'for c in calls),live_network_retrieval_reads=0,scientific_status='not_independently_assessed',newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps(completion,ensure_ascii=False,default=str))


if __name__=='__main__':main()
