"""Fixed actual proposals: native confirmation with/without source-blind inventory."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.assertion_inventory import inventory_prompt,parse_inventory,confirmation_inventory_notes
from research_verify.evidence_flow import confirm_repairs
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=False);base=Path('evaluation/frontier-strategy-20261113')
    source_attempt=base/'source-blind-proposal-rendering-model-20261114-v1/attempt'
    source_plan=json.loads((source_attempt/'plan.json').read_text())
    specs=[('source-blind-proposal-rendering-model-20261114-v1','neuropathy','rendered_proposal'),
           ('dual-observation-reconciliation-model-20261114-v1','neuropathy','dual_observations'),
           ('source-blind-proposal-rendering-model-20261114-v1','xenium','rendered_proposal'),
           ('original-language-repair-model-20261114-v1','xenium','original')]
    inputs=[Path(__file__),Path('scripts/experiment_error_receipt.py'),Path('scripts/run_native_original_report_pair_20261114.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),source_attempt/'plan.json',source_attempt/'completion.json']
    jobs=[];units={}
    for attempt_name,name,arm in specs:
        old=base/attempt_name/'attempt';assert json.loads((old/'completion.json').read_text())['frozen_inputs_unchanged'] is True
        result=old/name/arm/'result.json';r=json.loads(result.read_text());prior=json.loads((old/'plan.json').read_text())
        source=next(j for j in source_plan['jobs'] if j['name']==name);original=source_attempt/name/'original-report.txt'
        oldj=next(j for j in prior['jobs'] if j['name']==name)
        assert sha(original)==source['original_report_sha256']==oldj['original_report_sha256']
        material=source['material']
        if oldj.get('material_sha256'):assert hashlib.sha256(material.encode()).hexdigest()==oldj['material_sha256']
        else:assert material==oldj['material']
        inputs.extend([old/'plan.json',old/'completion.json',result,original])
        for issue in r['native_applied']:
            key=f'p{len(jobs):02d}';folder=a.out_dir/key;folder.mkdir();report=original.read_text();assert report.count(issue['statement'])==1
            units[key+'-original']=issue['statement'];units[key+'-replacement']=issue['replacement']
            (folder/'original-report.txt').write_text(report)
            jobs.append(dict(case_id=key,issue=issue,report=report,material=material,query=source['query'],folder=folder,
                provenance=dict(attempt=attempt_name,job=name,arm=arm,claim_id=issue['claim_id'])))
    root=Path.cwd();freeze={str(x):sha(x) for x in inputs}
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Five fixed actual proposals from exposed groups, original and replacement tested separately; not full-report quality or production baseline',
        jobs=[dict(case_id=j['case_id'],issue=j['issue'],query=j['query'],material=j['material'],provenance=j['provenance'],
            original_report_sha256=hashlib.sha256(j['report'].encode()).hexdigest()) for j in jobs],
        units=units,arms=['native','inventory'],planned_inventory_calls=1,maximum_confirmation_calls=2*len(jobs),
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        delta='Candidate appends source-blind literal inventories; same native attribute confirmation and approval conditions',
        upstream_cost='Reuses actual completed proposals, reports and source acquisition; this stage cost excludes all upstream calls',
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(proposals=len(jobs),maximum_calls=1+2*len(jobs))));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[];results=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        def invoke(prompt,folder,stage):
            assert len(prompt)<=60000
            n=len(calls);entry=dict(call_id=n,folder=str(folder.relative_to(a.out_dir)),stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            try:
                response=model.invoke(prompt);raw=str(getattr(response,'content',response));(folder/f'call-{n:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        try:inventory=parse_inventory(invoke(inventory_prompt(units),a.out_dir,'source_blind_inventory'),units)
        except Exception as exc:inventory={key:dict(model_status='unknown',spans=[],reason=type(exc).__name__) for key in units}
        (a.out_dir/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
        for n,j in enumerate(jobs):
            for arm in (protocol['arms'] if n%2==0 else list(reversed(protocol['arms']))):
                folder=j['folder']/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
                notes=confirmation_inventory_notes(inventory[j['case_id']+'-original'],inventory[j['case_id']+'-replacement'])
                def confirm_invoke(prompt,**kw):
                    actual=prompt+('\n\n'+notes if arm=='inventory' else '')
                    return invoke(actual,folder,'repair_validation')
                handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d)})()
                report,applied,unresolved=confirm_repairs(handler,j['report'],[j['issue']],j['material'],j['query'],trace,invoke=confirm_invoke)
                (folder/'report.txt').write_text(report);r=dict(case_id=j['case_id'],arm=arm,native_applied=applied,native_unresolved=unresolved,
                    report_sha256=sha(folder/'report.txt'),report_chars=len(report),quality_claim=None,newly_credited_corrections=0)
                (folder/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');results.append(r)
    completion=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls))))


if __name__=='__main__':main()
