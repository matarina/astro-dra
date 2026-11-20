"""Two-arm known-paper Writer mechanism probe, not a full report evaluation."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.revisable_section_document import instructions, render
from research_verify.fact_document import clean_json
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--replay-attempt',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay_attempt);a.out_dir.mkdir(exist_ok=False)
    root=Path('evaluation/frontier-strategy-20261113')
    views_path=root/'native-scope-acquisition-inputs-20261115-v1/acquired-views.json'
    notes_path=root/'scope-acquisition-reader-model-20261115-v1/attempt/acquired/span_ids-parsed.json'
    cases_path=root/'native-scope-acquisition-inputs-20261115-v1/cases.json'
    sources_path=root/'immune-questioned-fact-inputs-20261115-v1/sources.json'
    files=[Path(__file__),Path('scripts/experiment_error_receipt.py'),views_path,notes_path,cases_path,sources_path,
        root/'scope-acquisition-reader-model-20261115-v1/attempt/call-01-response.txt',
        root/'scope-acquisition-reader-model-20261115-v1/attempt/calls.json',
        root/'scope-acquisition-reader-model-20261115-v1/attempt/completion.json',
        *Path('local_deep_research/research_verify').glob('*.py'),
        Path('local_deep_research/tests/test_revisable_section_document.py')]
    frozen={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',frozen)
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    views=read(views_path);registry=read(notes_path)['registry'];query=read(cases_path)['cases'][1]['query']
    ids={str(v['source_id'])for v in views};sources=[s for s in read(sources_path)if str(s['index'])in ids]
    assert len(views)==len(sources)==1 and len(registry)==4
    assert read(root/'scope-acquisition-reader-model-20261115-v1/attempt/completion.json')['fresh_model_calls']==2
    for fact in registry.values():assert fact['source_view_sha256']==hashlib.sha256(views[0]['text'].encode()).hexdigest()
    settings={'llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,'llm.max_retries':0}
    write(a.out_dir/'plan.json',dict(scope='One known source, complete paper-specific answer only. Both arms receive the same original query, all four fallible acquired-body notes, original source passages, identity and settings. Only selected-note revision permission differs. No old report, expected answer, native judgement or feedback label. Neither a complete multi-paper matched-report assessment nor independent correction/generalization evidence.',arms=['immutable','revisable'],maximum_fresh_calls=2,maximum_prompt_chars=60000,settings=settings,source_acquisition=False,new_independent_correction_credit=0))
    calls=[];results=[];model=None
    for i,mode in enumerate(['immutable','revisable']):
        folder=a.out_dir/mode;folder.mkdir()
        prompt=('ORIGINAL REQUEST:\n'+query+'\nDIAGNOSTIC OUTPUT SCOPE:\n'
            'Answer only for the supplied paper, with all useful paper-specific '
            'methods relevant to the original request. Do not fabricate a '
            'multi-paper review from a one-paper packet.\n'+instructions(sources,registry,views,allow_revisions=mode=='revisable'))
        assert len(prompt)<=60000
        pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=i,arm=mode,prompt_sha256=sha(pp),prompt_chars=len(prompt),status='started');calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay_attempt:
                old=read(a.replay_attempt/'calls.json')[i];rp=a.replay_attempt/f'call-{i:02d}-response.txt'
                assert (a.replay_attempt/f'call-{i:02d}-prompt.txt').read_text()==prompt
                assert old['prompt_sha256']==sha(pp)and old['response_sha256']==sha(rp)
                raw=rp.read_text();metadata=old['response_metadata'];row['origin']='saved_response_replay'
            elif a.execute:
                row['origin']='fresh_model';write(a.out_dir/'calls.json',calls)
                if model is None:
                    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                    from local_deep_research.config.thread_settings import settings_context
                    from local_deep_research.config.llm_config import get_llm
                    defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                    effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
                    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
            else:
                raw=json.dumps(dict(title='Preflight only',sections=[]));metadata={};row['origin']='preflight_placeholder'
            rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw)
            row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata)
            report,receipt=render(raw,sources,registry,views)
            if mode=='immutable':assert not receipt['writer_revisions']
            (folder/'report.md').write_text(report);write(folder/'rendering.json',receipt)
            if a.replay_attempt:
                assert report==(a.replay_attempt/mode/'report.md').read_text()
                assert receipt==read(a.replay_attempt/mode/'rendering.json')
            result=dict(arm=mode,status='rendered',report_chars=len(report),selected_fact_ids=receipt['selected_fact_ids'],unselected_fact_ids=receipt['unselected_fact_ids'],revisions=len(receipt['writer_revisions']),semantic_verdict=None)
        except Exception as exc:
            row['failure']=error_receipt(exc);result=dict(arm=mode,status='unavailable',failure=error_receipt(exc))
        results.append(result);write(a.out_dir/'calls.json',calls);write(a.out_dir/'results.json',results)
    done=dict(results=results,fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),failures=sum(r['status']=='unavailable'for r in results),frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in frozen.items()),replay_exact=True if a.replay_attempt else None,complete_report_evaluated=False,new_independent_correction_credit=0)
    write(a.out_dir/'completion.json',done);print(json.dumps(done))
    if done['failures'] or not done['frozen_inputs_unchanged']:raise SystemExit(2)


if __name__=='__main__':main()
