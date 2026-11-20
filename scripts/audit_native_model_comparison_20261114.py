"""Audit same-prompt model comparison; no independent semantic score."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.evidence_flow import parse_review


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
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==completion['calls']==plan['planned_calls']==4
    rows=[]
    for job in plan['jobs']:
        folder=a.attempt/job['name'];claims={int(k):v for k,v in job['claims'].items()}
        assert sha(folder/'native-prompt.txt')==job['prompt_sha256']
        for model in plan['models']:
            call=next(c for c in calls if c['job']==job['name'] and c['model']==model)
            prompt=folder/model/f"call-{call['call_id']:03d}-prompt.txt"
            assert sha(prompt)==call['prompt_sha256']==job['prompt_sha256']
            row=json.loads((folder/model/'result.json').read_text())
            if call['status']=='returned':
                response=prompt.with_name(prompt.name.replace('-prompt','-response'));assert sha(response)==call['response_sha256']
                if row['status']=='parsed':
                    issues,checked=parse_review(response.read_text(),claims,include_checked=True)
                    assert issues==row['issues'] and checked==row['checked']
                    for entry in issues+checked:assert entry['statement']==claims[entry['claim_id']]['text']
            rows.append(row)
    audit=dict(scope=plan['scope'],verified_launch_startup_completion_hashes=True,calls=4,
        byte_identical_prompts_sources_by_job=True,rows=rows,model_identity=plan['model_identity'],
        report_changes=False,quality_claim=None,newly_credited_corrections=0)
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=4,parsed=sum(r['status']=='parsed' for r in rows))))


if __name__=='__main__':main()
