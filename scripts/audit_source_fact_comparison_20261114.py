"""Terminal exposure, call and text-change audit, not semantic adjudication."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd()
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace') if path.is_relative_to('/workspace') else (path.relative_to(root) if path.is_absolute() else path)
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']
    for call in calls:
        paths=list(a.attempt.glob(f"**/call-{call['call_id']:03d}-prompt.txt"));assert len(paths)==1
        path=paths[0];assert sha(path)==call['prompt_sha256']
        if call.get('response_sha256'):assert sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    a.out_dir.mkdir(parents=True,exist_ok=False);rows=[];readers=[]
    for job in plan['jobs']:
        folder=a.attempt/job['name'];original=(folder/'original-report.txt').read_text();assert sha(folder/'original-report.txt')==job['original_report_sha256']
        base=(folder/'native-prompt.txt').read_text();assert sha(folder/'native-prompt.txt')==job['native_prompt_sha256']
        reader_calls=[call for call in calls if call['stage']=='source_facts' and call['job']==job['name']]
        prepared=sorted(folder.glob('reader-*-prompt.txt'));assert len(reader_calls)==len(prepared)==job['reader_batches']
        for path,call in zip(prepared,reader_calls):assert sha(path)==call['prompt_sha256']
        answers=json.loads((folder/'reader-answers.json').read_text())
        assert sorted(x['question_id'] for x in answers)==sorted(f'source-facts-{i}' for i in job['source_ids'])
        readers.append(dict(job=job['name'],source_ids=job['source_ids'],reader_calls=len(reader_calls),answers=len(answers),
            unknown_answers=sum(x['status']=='unknown' for x in answers),
            evidence_quotes=sum(len(x['evidence']) for x in answers),located_quotes=sum(e['quote_valid'] for x in answers for e in x['evidence'])))
        for arm in plan['arms']:
            result=json.loads((folder/arm/'result.json').read_text());native_call=next(call for call in calls if call['stage']=='native_check'
                and list(a.attempt.glob(f"**/call-{call['call_id']:03d}-prompt.txt"))[0].parent==folder/arm)
            prompt=(folder/arm/f"call-{native_call['call_id']:03d}-prompt.txt").read_text()
            if arm=='native':assert prompt==base
            elif arm=='concept_instruction':assert prompt==base+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS
            else:assert prompt.startswith(base+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS+'\n\nFALLIBLE SOURCE-ONLY READING NOTES')
            assert len(prompt)<=60000
            report=(folder/arm/'report.txt').read_text();assert sha(folder/arm/'report.txt')==result['report_sha256']
            restored=report
            for issue in reversed(result['native_applied']):
                assert restored.count(issue['replacement'])==1;restored=restored.replace(issue['replacement'],issue['statement'],1)
            assert restored==original
            rows.append(dict(job=job['name'],arm=arm,status=result['status'],native_applied=len(result['native_applied']),
                report_sha256=result['report_sha256'],report_chars=len(report),native_prompt_chars=len(prompt),
                only_recorded_native_replacements=True))
    audit=dict(scope='Two exposed groups, source-only request construction and real native revisions; no full report/held-out semantic validation',
        exit_code=state['State']['ExitCode'],verified_launch_startup_completion_hashes=True,calls=len(calls),readers=readers,rows=rows,
        all_arms_same_report_by_job={j['name']:len({r['report_sha256'] for r in rows if r['job']==j['name']})==1 for j in plan['jobs']},
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
