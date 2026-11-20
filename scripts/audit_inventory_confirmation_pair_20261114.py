"""Literal inventory/confirmation experiment audit, not independent quality scoring."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.assertion_inventory import inventory_prompt,parse_inventory,confirmation_inventory_notes
from research_verify.evidence_flow import confirm_repairs


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd()
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace') if path.is_relative_to('/workspace') else (path.relative_to(root) if path.is_absolute() else path)
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text());assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']<=1+plan['maximum_confirmation_calls'];paths={}
    for call in calls:
        path=a.attempt/call['folder']/f"call-{call['call_id']:03d}-prompt.txt";paths[call['call_id']]=path;assert sha(path)==call['prompt_sha256']
        assert call['status']=='returned' and sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    invcall=next(x for x in calls if x['stage']=='source_blind_inventory');path=paths[invcall['call_id']]
    assert path.read_text()==inventory_prompt(plan['units'])
    inventory=parse_inventory(path.with_name(path.name.replace('-prompt','-response')).read_text(),plan['units'])
    assert inventory==json.loads((a.attempt/'inventory.json').read_text())
    for key,row in inventory.items():
        for span in row['spans']:assert plan['units'][key][span['start']:span['end']]==span['quote']
    rows=[]
    for job in plan['jobs']:
        folder=a.attempt/job['case_id'];original=(folder/'original-report.txt').read_text();assert sha(folder/'original-report.txt')==job['original_report_sha256']
        notes=confirmation_inventory_notes(inventory[job['case_id']+'-original'],inventory[job['case_id']+'-replacement'])
        for arm in plan['arms']:
            captured=[]
            handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d)})()
            trace=type('Trace',(),{'record':staticmethod(lambda *args,**kw:None)})()
            confirm_repairs(handler,original,[job['issue']],job['material'],job['query'],trace,
                invoke=lambda prompt,**kw:captured.append(prompt+('\n\n'+notes if arm=='inventory' else '')) or '{"decisions":[]}')
            actual=[paths[x['call_id']].read_text() for x in calls if x['folder']==job['case_id']+'/'+arm]
            assert captured==actual
            r=json.loads((folder/arm/'result.json').read_text());report=(folder/arm/'report.txt').read_text();assert sha(folder/arm/'report.txt')==r['report_sha256']
            restored=report
            for issue in reversed(r['native_applied']):
                assert restored.count(issue['replacement'])==1;restored=restored.replace(issue['replacement'],issue['statement'],1)
            assert restored==original
            events=[json.loads(x) for x in (folder/arm/'trace.jsonl').read_text().splitlines()]
            decisions=[e['data'] for e in events if e['stage']=='repair_validation_decisions']
            rows.append(dict(case_id=job['case_id'],arm=arm,native_applied=len(r['native_applied']),report_sha256=r['report_sha256'],decisions=decisions,
                source_and_native_prompt_replayed=True,only_recorded_replacements=True))
    audit=dict(scope=plan['scope'],exit_code=0,verified_launch_startup_completion_hashes=True,calls=len(calls),rows=rows,
        located_spans=sum(len(r['spans']) for r in inventory.values()),unlocated_assertions=sum(len(r['unlocated']) for r in inventory.values()),
        quality_claim=None,newly_credited_corrections=0,limits=['Inventory locations do not prove semantic completeness or truth','No independent full-report corrections/retention/new-error assessment'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),decisions=[(r['case_id'],r['arm'],r['native_applied']) for r in rows])))


if __name__=='__main__':main()
