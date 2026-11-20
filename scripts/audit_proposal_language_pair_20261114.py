"""Source-blind rendering/confirmation provenance audit, not semantic acceptance."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.proposal_language import proposal_render_prompt,parse_rendered_proposals
from research_verify.evidence_flow import confirm_repairs


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    completion=json.loads((a.attempt/'completion.json').read_text());assert completion['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd()
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace') if path.is_relative_to('/workspace') else (path.relative_to(root) if path.is_absolute() else path)
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==completion['calls']<=6
    paths={}
    for call in calls:
        found=list(a.attempt.glob(f"**/call-{call['call_id']:03d}-prompt.txt"));assert len(found)==1
        path=found[0];paths[call['call_id']]=path;assert sha(path)==call['prompt_sha256']
        assert call['status']=='returned' and sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    rows=[]
    for job in plan['jobs']:
        folder=a.attempt/job['name'];selected=[x for x in calls if x['job']==job['name']]
        call=next(x for x in selected if x['stage']=='source_blind_rendering');path=paths[call['call_id']]
        assert path.read_text()==proposal_render_prompt(job['issues'])
        rendered=parse_rendered_proposals(path.with_name(path.name.replace('-prompt','-response')).read_text(),job['issues'])
        assert {str(k):v for k,v in rendered.items()}==json.loads((folder/'renderings.json').read_text())
        original=(folder/'original-report.txt').read_text();assert sha(folder/'original-report.txt')==job['original_report_sha256']
        for arm in plan['arms']:
            issues=job['issues'] if arm=='direct_proposal' else [{**i,'replacement':rendered[i['claim_id']]['text']} for i in job['issues']]
            captured=[]
            handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d),
                '_invoke_text':staticmethod(lambda prompt,**kw:captured.append(prompt) or '{"decisions":[]}')})()
            trace=type('Trace',(),{'record':staticmethod(lambda *args,**kw:None)})()
            confirm_repairs(handler,original,issues,job['material'],job['query'],trace)
            actual=[paths[x['call_id']].read_text() for x in selected if x['arm']==arm and x['stage']=='repair_validation']
            assert captured==actual
            r=json.loads((folder/arm/'result.json').read_text());report=(folder/arm/'report.txt').read_text()
            assert sha(folder/arm/'report.txt')==r['report_sha256'];restored=report
            for issue in reversed(r['native_applied']):
                assert restored.count(issue['replacement'])==1;restored=restored.replace(issue['replacement'],issue['statement'],1)
            assert restored==original
            rows.append(dict(job=job['name'],arm=arm,native_applied=r['native_applied'],native_unresolved=r['native_unresolved'],
                report_sha256=r['report_sha256'],report_chars=len(report),same_native_confirmation_replayed=True,
                only_recorded_replacements=True))
    audit=dict(scope=plan['scope'],exit_code=0,verified_launch_startup_completion_hashes=True,calls=len(calls),
        source_blind_rendering_request_verified=True,rows=rows,quality_claim=None,newly_credited_corrections=0,
        limits=['No independent linguistic fidelity gold','No complete report review','No independent primary-source corrections/retention/new-error assessment'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),rows=[dict(job=r['job'],arm=r['arm'],applied=len(r['native_applied'])) for r in rows])))


if __name__=='__main__':main()
