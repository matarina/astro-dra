"""One fresh complete Writer draft with paper blocks, exact cached flat baseline.

Actual original question, nonempty draft, evidence/reader notes,35fallible facts
and native Writer prefix are unchanged. No new source reading/retrieval/native
checks here; the candidate is a Writer-stage draft, never a final checked report.
"""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.fact_document import instructions as flat_instructions,render as flat_render
from research_verify.section_document import instructions,render
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prior-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--replay-attempt',type=Path);a=p.parse_args();assert not(a.execute and a.replay_attempt);a.out_dir.mkdir(exist_ok=False)
    oldplan=json.loads((a.prior_attempt/'plan.json').read_text());oldcalls=json.loads((a.prior_attempt/'calls.json').read_text());writer=next(c for c in oldcalls if c['arm']=='candidate'and c['stage']=='writer');oldp=a.prior_attempt/f"call-{writer['index']:02d}-prompt.txt";oldr=a.prior_attempt/f"call-{writer['index']:02d}-response.txt";assert sha(oldp)==writer['prompt_sha256']and sha(oldr)==writer['response_sha256']
    registry=json.loads((a.prior_attempt/'candidate/fact-registry.json').read_text());oldresult=json.loads((a.prior_attempt/'candidate/result.json').read_text());sources=oldresult['sources']
    suffix=flat_instructions(sources,registry);flat_prompt=oldp.read_text();assert flat_prompt.endswith(suffix);prefix=flat_prompt[:-len(suffix)];assert prefix==(a.prior_attempt/'call-01-prompt.txt').read_text()
    baseline,flat_receipt=flat_render(oldr.read_text(),sources,registry);assert baseline==(a.prior_attempt/'candidate/report.txt').read_text()
    files=[Path(__file__).resolve().relative_to(Path.cwd()),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py'),a.prior_attempt/'plan.json',a.prior_attempt/'calls.json',oldp,oldr,a.prior_attempt/'candidate/fact-registry.json',a.prior_attempt/'candidate/result.json',a.prior_attempt/'candidate/report.txt',a.prior_attempt/'call-01-prompt.txt']
    frozen={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',frozen)
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    (a.out_dir/'baseline.txt').write_text(baseline);write(a.out_dir/'baseline-rendering.json',flat_receipt);write(a.out_dir/'sources.json',sources);write(a.out_dir/'fact-registry.json',registry);(a.out_dir/'native-writer-prefix.txt').write_text(prefix)
    prompt=prefix+instructions(sources,registry);assert len(prompt)<500000;(a.out_dir/'prompt.txt').write_text(prompt)
    plan=dict(scope='Complete Writer-stage draft comparison only; exact saved flat baseline, same full native Writer prefix/source evidence/reader notes/35fallible facts. Candidate ONLY changes composition instruction/interface and rendering into section/paper/analysis blocks. Additional prose is explicitly fallible; no automatic deduplication or semantic verdict. No new acquisition, report-blind adjudication or native-check execution.',query=oldplan['query'],query_sha256=oldplan['query_sha256'],original_report_sha256=oldplan['original_report_sha256'],source_pack_sha256=oldplan['source_pack_sha256'],prior_attempt=str(a.prior_attempt),native_writer_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),fact_registry_sha256=sha(a.out_dir/'fact-registry.json'),maximum_fresh_calls=1,settings=oldplan['settings'],model_max_tokens=8000,native_consistency_configured=True,native_check_executed=False,new_independent_correction_credit=0)
    write(a.out_dir/'plan.json',plan)
    result=dict(status='started',prompt_sha256=sha(a.out_dir/'prompt.txt'),native_check_executed=False,new_independent_correction_credit=0);write(a.out_dir/'result.json',result)
    try:
        if a.replay_attempt:
            previous=json.loads((a.replay_attempt/'result.json').read_text());assert prompt==(a.replay_attempt/'prompt.txt').read_text()and sha(a.replay_attempt/'prompt.txt')==previous['prompt_sha256']
            raw=(a.replay_attempt/'response.txt').read_text();metadata=previous['response_metadata'];assert sha(a.replay_attempt/'response.txt')==previous['response_sha256'];origin='saved_response_replay'
        elif a.execute:
            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
            from local_deep_research.config.thread_settings import settings_context
            from local_deep_research.config.llm_config import get_llm
            defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|plan['settings']|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:settings.get(k,d))})()):model=get_llm(settings_snapshot=settings)
            response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata;origin='fresh_model'
        else:
            raw=json.dumps(dict(title='预检占位',sections=[dict(heading='占位原稿',blocks=[dict(kind='analysis',purpose='limitation',text=baseline,source_ids=[])])]),ensure_ascii=False);metadata={};origin='preflight_placeholder'
        (a.out_dir/'response.txt').write_text(raw);result.update(response_sha256=sha(a.out_dir/'response.txt'),response_metadata=metadata,origin=origin)
        write(a.out_dir/'result.json',result)
        draft,receipts=render(raw,sources,registry);(a.out_dir/'candidate-draft.txt').write_text(draft);write(a.out_dir/'rendering.json',receipts)
        if a.replay_attempt:
            assert draft==(a.replay_attempt/'candidate-draft.txt').read_text()and receipts==json.loads((a.replay_attempt/'rendering.json').read_text())
        result.update(status='draft_generated',draft_chars=len(draft),draft_sha256=sha(a.out_dir/'candidate-draft.txt'),selected_fact_nodes=len(receipts['facts']),identity_blocks=len(receipts['identities']),generated_prose_chars=sum(len(x['text'])for x in receipts['generated_prose']),replay_exact=True if a.replay_attempt else None)
    except Exception as exc:result.update(status='unavailable',failure=error_receipt(exc))
    result['frozen_inputs_unchanged']=all(sha(Path(k))==h for k,h in frozen.items());write(a.out_dir/'result.json',result);print(json.dumps({k:v for k,v in result.items()if k!='response_metadata'}))
    if result['status']=='unavailable':raise SystemExit(2)


if __name__=='__main__':main()
