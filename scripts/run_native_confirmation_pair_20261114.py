"""Matched native confirmation on frozen real proposals, not independent scoring."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from research_verify.evidence_flow import (
    _review_material, required_sources, document_structure_spans, confirm_repairs,
    ATTRIBUTE_CONFIRMATION_INSTRUCTIONS,
)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--before-attempt',type=Path,required=True)
    p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    prior=json.loads((a.before_attempt/'plan.json').read_text())
    previous=json.loads((a.before_attempt/'unit_boundaries/result.json').read_text())
    assert json.loads((a.before_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    case=json.loads(a.case_manifest.read_text())['cases'][0];source=Path(case['source']);original=Path(case['draft'])
    assert sha(source)==prior['source_pack_sha256']==case['source_sha256']
    assert sha(original)==prior['report_sha256']==case['draft_sha256']
    report=original.read_text();sources=json.loads(source.read_text());docs=native_documents(sources)
    assert case['query']==prior['query'] and hashlib.sha256(case['query'].encode()).hexdigest()==case['query_sha256']
    reserve=min(8000,len(json.dumps(document_structure_spans(report),ensure_ascii=False)))
    calls=json.loads((a.before_attempt/'unit_boundaries/calls.json').read_text())
    frozen_prompts={}
    inputs=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),
        Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
        Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py'),
        a.case_manifest,source,original,a.before_attempt/'plan.json',a.before_attempt/'completion.json',
        a.before_attempt/'unit_boundaries/result.json',a.before_attempt/'unit_boundaries/calls.json']
    for call in calls:
        if call['stage']!='repair_validation':continue
        path=a.before_attempt/f"unit_boundaries/call-{call['call_id']:03d}-prompt.txt"
        assert sha(path)==call['prompt_sha256'];inputs.append(path)
        prompt=path.read_text();candidates=json.loads(prompt.split('Candidates:\n',1)[1])
        frozen_prompts[tuple(c['original'] for c in candidates)]=prompt
    jobs=[]
    for group in prior['groups']:
        claims={int(k):v for k,v in group.items()}
        issues=[{**i,'status':i['issue_type']} for i in previous['native_unresolved']
                if i.get('status')=='repair_not_confirmed' and i.get('claim_id') in claims]
        if not issues:continue
        section='\n'.join(c['text'] for c in claims.values())
        material,_=_review_material(docs,case['query']+'\n'+section,claims,required_sources(section,sources),max(2000,60000-reserve))
        frozen=frozen_prompts[tuple(i['statement'] for i in issues)]
        jobs.append(dict(issues=issues,material=material,frozen_prompt=frozen))
    assert len(jobs)==2 and sum(len(j['issues']) for j in jobs)==3
    # Verify the exact existing native request BEFORE any model invocation.
    for job in jobs:
        prompts=[]
        handler=type('Handler',(),{'_invoke_text':staticmethod(lambda prompt,**kw:prompts.append(prompt) or '{"decisions":[]}')})()
        confirm_repairs(handler,report,job['issues'],job['material'],case['query'],Trace(a.out_dir/'preflight.jsonl'))
        assert prompts==[job['frozen_prompt']]
    root=Path.cwd();freeze={str(f):sha(f) for f in inputs}
    for f in inputs:
        rel=f.relative_to(root) if f.is_absolute() else f
        if str(rel).startswith(('scripts/','local_deep_research/')):
            target=a.out_dir/'code'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    protocol=dict(scope='Matched post-review confirmation, SAME real proposals and original source views; not writer/first-check evaluation',
        query=case['query'],query_sha256=case['query_sha256'],original_report_sha256=sha(original),source_pack_sha256=sha(source),
        jobs=[dict(issues=j['issues'],material_sha256=hashlib.sha256(str(j['material']).encode()).hexdigest(),
                   baseline_prompt_sha256=hashlib.sha256(j['frozen_prompt'].encode()).hexdigest()) for j in jobs],
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,planned_calls=4,
        candidate_delta='Only appended attribute-by-attribute confirmation instructions; approval conditions unchanged',
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'original-report.txt').write_text(report)
    if not a.execute:print(json.dumps(dict(planned_calls=4,proposals=3)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})
    snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,
        'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    summaries=[]
    for arm in ['baseline','attribute_confirmation']:
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');returned=[];revised=report;applied=[];pending=[]
        for index,job in enumerate(jobs):
            expected=job['frozen_prompt']+ ('\n\n'+ATTRIBUTE_CONFIRMATION_INSTRUCTIONS if arm=='attribute_confirmation' else '')
            class Handler:
                def get_setting(self,key,default=None):return arm=='attribute_confirmation' if key=='citation.attribute_confirmation_review' else default
                def _invoke_text(self,prompt,**kwargs):
                    assert prompt==expected
                    (folder/f'call-{index:03d}-prompt.txt').write_text(prompt)
                    entry=dict(call_id=index,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),status='attempted');returned.append(entry)
                    try:
                        raw=model.invoke(prompt);text=str(getattr(raw,'content',raw));(folder/f'call-{index:03d}-response.txt').write_text(text)
                        entry.update(status='returned',response_sha256=hashlib.sha256(text.encode()).hexdigest());return text
                    except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__);raise
                    finally:(folder/'calls.json').write_text(json.dumps(returned,indent=2)+'\n')
            handler=Handler()
            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
                model=get_llm(settings_snapshot=snap)
                revised,fixes,unresolved=confirm_repairs(handler,revised,job['issues'],job['material'],case['query'],trace)
            applied.extend(fixes);pending.extend(unresolved)
        (folder/'report.txt').write_text(revised)
        result=dict(arm=arm,model_calls=len(returned),native_applied=applied,native_unresolved=pending,report_chars=len(revised),
            report_sha256=sha(folder/'report.txt'),quality_claim=None,newly_credited_corrections=0)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');summaries.append(result)
    completion=dict(arms=summaries,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=sum(r['model_calls'] for r in summaries),native_applied=[len(r['native_applied']) for r in summaries],frozen_inputs_unchanged=completion['frozen_inputs_unchanged'])))


if __name__=='__main__':main()
