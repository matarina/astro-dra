"""Replay fixed real approvals; only contradictory responses get a fresh clarification."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from research_verify.assertion_inventory import confirmation_inventory_notes
from research_verify.evidence_flow import confirm_repairs,confirmation_conflicts
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--before-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    assert json.loads((a.before_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    plan=json.loads((a.before_attempt/'plan.json').read_text());calls=json.loads((a.before_attempt/'calls.json').read_text())
    inventory=json.loads((a.before_attempt/'inventory.json').read_text());inputs=[Path(__file__),Path('scripts/experiment_error_receipt.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),*Path('local_deep_research/research_verify').glob('*.py'),
        a.before_attempt/'plan.json',a.before_attempt/'calls.json',a.before_attempt/'completion.json',a.before_attempt/'inventory.json'];jobs=[]
    for j in plan['jobs']:
        original=a.before_attempt/j['case_id']/'original-report.txt';assert sha(original)==j['original_report_sha256'];inputs.append(original)
        for side in plan['arms']:
            call=next(x for x in calls if x['folder']==j['case_id']+'/'+side)
            prompt=a.before_attempt/call['folder']/f"call-{call['call_id']:03d}-prompt.txt";raw=prompt.with_name(prompt.name.replace('-prompt','-response'))
            assert sha(prompt)==call['prompt_sha256'] and sha(raw)==call['response_sha256'];inputs.extend([prompt,raw])
            obj=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.read_text().strip(),flags=re.I))
            notes=confirmation_inventory_notes(inventory[j['case_id']+'-original'],inventory[j['case_id']+'-replacement']) if side=='inventory' else ''
            key=j['case_id']+'-'+side;folder=a.out_dir/key;folder.mkdir();(folder/'original-report.txt').write_bytes(original.read_bytes())
            jobs.append(dict(case_id=key,issue=j['issue'],query=j['query'],material=j['material'],report=original.read_text(),notes=notes,
                initial_prompt=prompt.read_text(),initial_response=raw.read_text(),conflicts=confirmation_conflicts(obj['decisions']),folder=folder))
    inputs=list(dict.fromkeys(inputs));freeze={str(x):sha(x) for x in inputs};root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Fixed real decision replay plus bounded semantic clarification; no fresh first-pass comparison or independent quality score',
        jobs=[{k:v for k,v in j.items() if k not in {'folder','report'}}|dict(original_report_sha256=hashlib.sha256(j['report'].encode()).hexdigest()) for j in jobs],
        arms=['cached_native','clarification'],cached_first_responses=2*len(jobs),maximum_new_calls=sum(bool(j['conflicts']) for j in jobs),
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        delta='Default-OFF consistency review asks once for semantic clarification only for a self-contradictory verdict; same source evidence and native approval fields',
        upstream_cost='Reuses prior eleven-call inventory/confirmation experiment and all upstream report/source preparation',quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(cached_responses=2*len(jobs),maximum_new_calls=protocol['maximum_new_calls'])));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    fresh=[];cached=[];results=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        for n,j in enumerate(jobs):
            for arm in (protocol['arms'] if n%2==0 else list(reversed(protocol['arms']))):
                folder=j['folder']/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
                def invoke(prompt,**kw):
                    actual=prompt+('\n\n'+j['notes'] if j['notes'] else '')
                    if kw['stage']=='repair_validation':
                        assert actual==j['initial_prompt'];(folder/'cached-prompt.txt').write_text(actual);(folder/'cached-response.txt').write_text(j['initial_response'])
                        cached.append(dict(case_id=j['case_id'],arm=arm,prompt_sha256=hashlib.sha256(actual.encode()).hexdigest(),response_sha256=hashlib.sha256(j['initial_response'].encode()).hexdigest()))
                        return j['initial_response']
                    assert arm=='clarification' and kw['stage']=='repair_validation_clarification' and len(actual)<=60000
                    i=len(fresh);entry=dict(call_id=i,folder=str(folder.relative_to(a.out_dir)),stage=kw['stage'],prompt_sha256=hashlib.sha256(actual.encode()).hexdigest());fresh.append(entry)
                    (folder/f'call-{i:03d}-prompt.txt').write_text(actual)
                    try:
                        response=model.invoke(actual);raw=str(getattr(response,'content',response));(folder/f'call-{i:03d}-response.txt').write_text(raw)
                        entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
                    except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
                    finally:(a.out_dir/'calls.json').write_text(json.dumps(fresh,indent=2)+'\n')
                handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else (arm=='clarification' if k=='citation.confirmation_consistency_review' else d))})()
                report,applied,pending=confirm_repairs(handler,j['report'],[j['issue']],j['material'],j['query'],trace,invoke=invoke)
                (folder/'report.txt').write_text(report);row=dict(case_id=j['case_id'],arm=arm,native_applied=applied,native_unresolved=pending,
                    report_sha256=sha(folder/'report.txt'),report_chars=len(report),quality_claim=None,newly_credited_corrections=0)
                (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');results.append(row)
    (a.out_dir/'cached-responses.json').write_text(json.dumps(cached,indent=2)+'\n')
    completion=dict(new_calls=len(fresh),cached_responses=len(cached),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(new_calls=len(fresh),cached_responses=len(cached))))


if __name__=='__main__':main()
