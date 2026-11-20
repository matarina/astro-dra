"""Replay the exact cached and fresh responses through native confirmation."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from research_verify.evidence_flow import confirm_repairs,confirmation_conflicts


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
    fresh=json.loads((a.attempt/'calls.json').read_text());assert len(fresh)==c['new_calls']==plan['maximum_new_calls']==1
    cached=json.loads((a.attempt/'cached-responses.json').read_text());assert len(cached)==c['cached_responses']==plan['cached_first_responses']==20
    for call in fresh:
        path=a.attempt/call['folder']/f"call-{call['call_id']:03d}-prompt.txt";assert sha(path)==call['prompt_sha256']
        assert call['status']=='returned' and sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    rows=[]
    for j in plan['jobs']:
        folder=a.attempt/j['case_id'];original=(folder/'original-report.txt').read_text();assert sha(folder/'original-report.txt')==j['original_report_sha256']
        for arm in plan['arms']:
            out=folder/arm;r=json.loads((out/'result.json').read_text());cached_row=next(x for x in cached if x['case_id']==j['case_id'] and x['arm']==arm)
            assert sha(out/'cached-prompt.txt')==cached_row['prompt_sha256'] and sha(out/'cached-response.txt')==cached_row['response_sha256']
            assert (out/'cached-prompt.txt').read_text()==j['initial_prompt'] and (out/'cached-response.txt').read_text()==j['initial_response']
            fresh_for=[x for x in fresh if x['folder']==j['case_id']+'/'+arm];observed=[]
            def invoke(prompt,**kw):
                actual=prompt+('\n\n'+j['notes'] if j['notes'] else '')
                if kw['stage']=='repair_validation':assert actual==j['initial_prompt'];return j['initial_response']
                call=fresh_for[len(observed)];path=out/f"call-{call['call_id']:03d}-prompt.txt";assert actual==path.read_text();observed.append(call)
                return path.with_name(path.name.replace('-prompt','-response')).read_text()
            handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else (arm=='clarification' if k=='citation.confirmation_consistency_review' else d))})()
            events=[];trace=type('Trace',(),{'record':staticmethod(lambda stage,data:events.append(dict(stage=stage,data=data)))})()
            report,applied,pending=confirm_repairs(handler,original,[j['issue']],j['material'],j['query'],trace,invoke=invoke)
            assert len(observed)==len(fresh_for) and report==(out/'report.txt').read_text() and sha(out/'report.txt')==r['report_sha256']
            assert applied==r['native_applied'] and pending==r['native_unresolved']
            restored=report
            for issue in reversed(applied):assert restored.count(issue['replacement'])==1;restored=restored.replace(issue['replacement'],issue['statement'],1)
            assert restored==original
            final_conflicts=[]
            if fresh_for:
                call=fresh_for[-1];path=out/f"call-{call['call_id']:03d}-response.txt"
                obj=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',path.read_text().strip(),flags=re.I));final_conflicts=confirmation_conflicts(obj['decisions'])
            rows.append(dict(case_id=j['case_id'],arm=arm,native_applied=len(applied),report_sha256=r['report_sha256'],new_calls=len(fresh_for),
                final_protocol_conflicts=final_conflicts,invalid_response_events=[x for x in events if x['stage']=='repair_validation_invalid'],
                exact_native_replay=True,only_recorded_replacements=True))
    audit=dict(scope=plan['scope'],exit_code=0,verified_launch_startup_completion_hashes=True,cached_responses=20,new_calls=1,rows=rows,
        quality_claim=None,newly_credited_corrections=0,limits=['Rejecting contradictory approval is not correction of the unchanged original','Missing or incorrect attribute checks can remain internally consistent','No independent full-report correction/retention/new-error adjudication'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(cached_responses=20,new_calls=1,changed_cases=[j['case_id'] for j in plan['jobs'] if len({x['report_sha256'] for x in rows if x['case_id']==j['case_id']})>1])))


if __name__=='__main__':main()
