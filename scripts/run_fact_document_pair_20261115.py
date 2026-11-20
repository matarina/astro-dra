"""Complete native synthesis with source-only scientific answer copying.

Exact cached baseline and shared reading, source-only answer calls and one fresh candidate Writer followed
by normal native checks. No live retrieval, repairs by this runner, publication
or production activation. Raw JSON remains separate from rendered model output.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from research_verify import evidence_flow
from research_verify.fact_document import instructions, render, answer_prompt, parse_answers
from research_verify.generation import format_source_documents
from research_verify.evidence_flow import cited_indices
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior-attempt',type=Path,required=True)
    p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    prior=json.loads((a.prior_attempt/'plan.json').read_text())
    previous=[c for c in json.loads((a.prior_attempt/'calls.json').read_text())if c['arm']=='inherited']
    assert len(previous)==6  # reader, writer, four native checks
    cases=_manifest_cases(a.case_manifest);assert len(cases)==1;case=cases[0]
    original=case['draft'].read_text();sources=json.loads(case['source'].read_text())
    assert sha(case['source'])==prior['source_pack_sha256'] and sha(case['draft'])==prior['original_report_sha256']
    assert case['query']==prior['query']
    paths=[Path(__file__).resolve().relative_to(Path.cwd().resolve()),
           Path('scripts/run_complete_draft_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),
           Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
           a.case_manifest,case['draft'],case['source'],a.prior_attempt/'plan.json',a.prior_attempt/'calls.json',
           a.prior_attempt/'inherited/result.json',a.prior_attempt/'inherited/report.txt',
           *Path('local_deep_research/research_verify').glob('*.py')]
    for c in previous:paths.extend([a.prior_attempt/f"call-{c['index']:02d}-prompt.txt",a.prior_attempt/f"call-{c['index']:02d}-response.txt"])
    freeze={str(path):sha(path)for path in paths}
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in paths:
        relative=path.resolve().relative_to(Path.cwd().resolve())
        if str(relative).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    material=format_source_documents(native_documents(sources),case['query'],max_chars=200000,required_ids=cited_indices(original))
    assert str(material) in (a.prior_attempt/'call-01-prompt.txt').read_text()
    (a.out_dir/'source-material.txt').write_text(str(material))
    byid={str(s['index']):s for s in sources};batches=[];batch=[];used=0
    for sid,view in material.views.items():
        record=dict(source_id=int(sid),title=byid[str(sid)].get('title'),metadata=view['metadata'],text=view['text'],scope=view['scope'])
        size=len(json.dumps(record,ensure_ascii=False))
        assert size<85000
        if batch and (used+size>85000 or len(batch)>=12):batches.append(batch);batch=[];used=0
        batch.append(record);used+=size
    if batch:batches.append(batch)
    assert len(batches)<=5
    (a.out_dir/'source-answer-batches.json').write_text(json.dumps(batches,ensure_ascii=False,indent=2)+'\n')
    clock=datetime.fromisoformat(prior['fixed_writer_clock'])
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock
    settings=prior['settings'];calls=[];results=[];model=None
    plan=dict(scope='Same original query/nonempty draft/38-source material/clock/shared native reader; candidate adds source-only answer calls, explicit fact/identity registries and direct fact-node rendering during NEW generation. Extra compute and expanded rendered output are declared, not cost parity. Native checks unchanged. No independent scoring/generalization claim.',
              prior_attempt=str(a.prior_attempt),query=case['query'],query_sha256=case['query_sha256'],
              source_pack_sha256=sha(case['source']),original_report_sha256=sha(case['draft']),
              settings=settings,maximum_candidate_calls=len(batches)+7,maximum_source_answer_calls=len(batches),maximum_fresh_writer_calls=1,
              maximum_prompt_chars=330000,original_source_count=len(sources),newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')

    def get_model():
        nonlocal model
        if model is None:
            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
            from local_deep_research.config.thread_settings import settings_context
            from local_deep_research.config.llm_config import get_llm
            defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
            effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
        return model

    for arm in ['baseline','fact_document']:
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
        arm_sources=copy.deepcopy(sources);fetch=FixedSources();cache_index=0;fresh=0;registry={}
        class Handler:
            stream_callback=None
            settings_snapshot=settings
            evidence_fetcher=fetch
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def is_fact_checking_enabled(self):return True
            def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _no_sources_response(self,q):raise ValueError('No actual source material')
            def _invoke_text(self,prompt,trace=None,stage='model'):
                nonlocal cache_index,fresh
                i=len(calls);row=dict(index=i,arm=arm,stage=stage)
                use_cache=arm=='baseline'or stage=='source_reading'
                if use_cache:
                    c=previous[cache_index]if arm=='baseline'else previous[0]
                    assert stage==c['stage']
                    oldp=a.prior_attempt/f"call-{c['index']:02d}-prompt.txt";oldr=a.prior_attempt/f"call-{c['index']:02d}-response.txt"
                    assert prompt==oldp.read_text()and sha(oldp)==c['prompt_sha256']and sha(oldr)==c['response_sha256']
                    raw=oldr.read_text();metadata=c['response_metadata'];row.update(origin='strict_cache',cached_from=str(oldr))
                    if arm=='baseline':cache_index+=1
                else:
                    if stage=='writer':
                        # The entire old native prompt remains a byte-identical prefix.
                        oldp=a.prior_attempt/'call-01-prompt.txt';assert prompt==oldp.read_text()
                        for batch_index,batch in enumerate(batches):
                            aux=answer_prompt(case['query'],batch);assert len(aux)<90000
                            k=len(calls);ap=a.out_dir/f'call-{k:02d}-prompt.txt';ap.write_text(aux)
                            ar=dict(index=k,arm=arm,stage='source_answers',origin='fresh_model'if a.execute else'preflight_placeholder',prompt_sha256=sha(ap),prompt_chars=len(aux))
                            calls.append(ar);fresh+=1
                            (a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
                            if a.execute:
                                response=get_model().invoke(aux);auxraw=str(getattr(response,'content',response));auxmeta=getattr(response,'response_metadata',{})
                            else:
                                auxraw=json.dumps({'sources':[dict(source_id=v['source_id'],facts=[])for v in batch]});auxmeta={}
                            rp=a.out_dir/f'call-{k:02d}-response.txt';rp.write_text(auxraw)
                            ar.update(status='returned',response_sha256=sha(rp),response_metadata=auxmeta)
                            (a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2,default=str)+'\n')
                            parsed=parse_answers(auxraw,batch)
                            assert not set(registry)&set(parsed['registry'])
                            registry.update(parsed['registry'])
                            (folder/f'source-answers-{batch_index:02d}.json').write_text(json.dumps(parsed,ensure_ascii=False,indent=2)+'\n')
                        (folder/'fact-registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
                        prompt+=instructions(arm_sources,registry)
                        i=len(calls);row=dict(index=i,arm=arm,stage=stage)
                    fresh+=1
                    if fresh>len(batches)+7 or len(prompt)>330000:raise ValueError('Finite candidate call budget')
                    row['origin']='fresh_model'if a.execute else'preflight_placeholder'
                    # Persist the real request before invocation, including failures.
                    (a.out_dir/f'call-{i:02d}-prompt.txt').write_text(prompt)
                    calls.append(row)
                    (a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
                    if a.execute:
                        response=get_model().invoke(prompt);raw=str(getattr(response,'content',response));metadata=getattr(response,'response_metadata',{})
                    else:
                        raw=json.dumps({'nodes':[{'kind':'text','text':original}]},ensure_ascii=False)if stage=='writer'else'{"issues":[]}'
                        metadata={}
                pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
                rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw)
                row.update(prompt_sha256=sha(pp),response_sha256=sha(rp),response_metadata=metadata,status='returned')
                if use_cache:calls.append(row)
                (a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2,default=str)+'\n')
                if arm=='fact_document'and stage=='writer':
                    rendered,receipts=render(raw,arm_sources,registry)
                    (folder/'writer-rendered.txt').write_text(rendered)
                    (folder/'fact-rendering.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
                    row['rendered_sha256']=sha(folder/'writer-rendered.txt')
                    (a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2,default=str)+'\n')
                    return rendered
                return raw
        try:
            result=evidence_flow.synthesize(Handler(),case['query'],arm_sources,original,trace)
            answer=result['content'];(folder/'report.txt').write_text(answer)
            row=dict(arm=arm,status='completed',report_chars=len(answer),report_sha256=sha(folder/'report.txt'),native_review=result['evidence_review'],sources=arm_sources,supplement_requests=fetch.events)
            if arm=='baseline':
                old=json.loads((a.prior_attempt/'inherited/result.json').read_text())
                assert cache_index==len(previous)and answer==(a.prior_attempt/'inherited/report.txt').read_text()
                assert row['native_review']==old['native_review']
        except Exception as exc:
            row=dict(arm=arm,status='unavailable',failure_type=type(exc).__name__)
        (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str)+'\n');results.append({k:v for k,v in row.items()if k!='sources'})
        if arm=='baseline'and row['status']!='completed':break
    completion=dict(arms=results,logical_calls=len(calls),fresh_model_requests=sum(c['origin']=='fresh_model'for c in calls),strict_cached_calls=sum(c['origin']=='strict_cache'for c in calls),
                    frozen_inputs_unchanged=all(sha(Path(k))==v for k,v in freeze.items()),network_retrieval_reads=0,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps({k:v for k,v in completion.items()if k!='arms'}))


if __name__=='__main__':main()
