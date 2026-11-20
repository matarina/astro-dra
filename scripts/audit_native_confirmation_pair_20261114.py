"""Verify a completed paired confirmation and stage blinded report evidence."""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True);a=ap.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    root=Path.cwd()
    for name,digest in freeze.items():
        p=Path(name);rel=p.relative_to('/workspace') if p.is_relative_to('/workspace') else (p.relative_to(root) if p.is_absolute() else p)
        saved=a.attempt/'code'/rel;assert sha(saved if saved.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+name,freeze.get(name))==h for name,h in launch.items())
    original=(a.attempt/'original-report.txt').read_text();assert sha(a.attempt/'original-report.txt')==plan['original_report_sha256']
    a.out_dir.mkdir(parents=True,exist_ok=False);rows=[];atoms=[]
    for result in c['arms']:
        arm=result['arm'];folder=a.attempt/arm;report=(folder/'report.txt').read_text()
        assert sha(folder/'report.txt')==result['report_sha256']
        calls=json.loads((folder/'calls.json').read_text());assert len(calls)==2
        for call in calls:
            i=call['call_id'];prompt=(folder/f'call-{i:03d}-prompt.txt').read_text()
            assert sha(folder/f'call-{i:03d}-prompt.txt')==call['prompt_sha256']
            assert call['status']=='returned' and sha(folder/f'call-{i:03d}-response.txt')==call['response_sha256']
            baseline=(a.attempt/'baseline'/f'call-{i:03d}-prompt.txt').read_text()
            if arm!='baseline':assert prompt.startswith(baseline+'\n\n')
            assert hashlib.sha256(baseline.encode()).hexdigest()==plan['jobs'][i]['baseline_prompt_sha256']
            candidates=json.JSONDecoder().raw_decode(prompt.split('Candidates:\n',1)[1])[0]
            raw=(folder/f'call-{i:03d}-response.txt').read_text();reply=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip(),flags=re.I))
            for decision in reply['decisions']:
                candidate=candidates[decision['candidate_index']]
                for key in ['original_attribute_checks','replacement_attribute_checks']:
                    for check in decision.get(key,[]):
                        texts=[x['metadata']+'\n'+x['context'] for x in candidate['source_contexts'] if x['source_id']==check.get('source_id')]
                        quote=check.get('evidence_quote');normalize=lambda s:' '.join(s.split())
                        atoms.append(dict(arm=arm,call_id=i,candidate_index=decision['candidate_index'],side=key,check=check,
                            quote_located_in_stated_source=isinstance(quote,str) and bool(quote.strip()) and any(normalize(quote) in normalize(t) for t in texts)))
        reconstructed=report
        for issue in reversed(result['native_applied']):
            assert reconstructed.count(issue['replacement'])==1
            reconstructed=reconstructed.replace(issue['replacement'],issue['statement'],1)
        assert reconstructed==original,'Report contains edits outside recorded native replacements'
        (a.out_dir/(arm+'-changes.diff')).write_text(''.join(difflib.unified_diff(original.splitlines(keepends=True),report.splitlines(keepends=True),fromfile='original',tofile=arm)))
        rows.append(dict(arm=arm,model_calls=len(calls),native_applied=len(result['native_applied']),
            report_chars=len(report),report_sha256=result['report_sha256'],only_recorded_native_replacements=True))
    audit=dict(scope='Matched confirmation execution and literal quote/change provenance; NOT independent correction/retention/new-error assessment',
        exit_code=state['State']['ExitCode'],verified_launch_startup_completion_hashes=True,rows=rows,attribute_checks=atoms,
        quote_checks=len(atoms),unlocated_quotes=sum(not x['quote_located_in_stated_source'] for x in atoms),
        quality_claim=None,newly_credited_corrections=0,
        limits=['Two local edits are not two denominator units; feedback identity/year clauses may belong to the same allegation.',
                'Generic Date metadata and model decisions do not settle online/issue/preprint date scopes.',
                'Fixed proposals isolate confirmation; first-pass proposal generation and cross-task generalization are not evaluated.'])
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    packet=a.out_dir/'independent-review-inputs';packet.mkdir()
    for label,arm in [('report-a','attribute_confirmation'),('report-b','baseline')]:
        (packet/(label+'.txt')).write_bytes((a.attempt/arm/'report.txt').read_bytes())
    (packet/'original-report.txt').write_bytes((a.attempt/'original-report.txt').read_bytes())
    (packet/'original-question.txt').write_text(plan['query'])
    name=next(n for n in freeze if n.endswith('/case-manifest.json'))
    manifest_path=root/Path(name).relative_to('/workspace') if name.startswith('/workspace/') else Path(name)
    case=json.loads(manifest_path.read_text())['cases'][0];sources=Path(case['source']);assert sha(sources)==plan['source_pack_sha256']
    (packet/'sources.json').write_bytes(sources.read_bytes())
    (packet/'README.txt').write_text('Assess original-source correctness, versions/date scopes, useful content retention and new errors for both reports. '
        'This is a matched post-review confirmation experiment using identical frozen proposals and source views, not new writer generation. '
        'Supplied material is newly acquired metadata/abstracts with unresolved records; consult original primary sources as needed. '
        'Do not equate edits, model labels or source-quote location with corrections, or count edits as denominator units.\n')
    (a.out_dir/'coordinator-only-blind-map.json').write_text(json.dumps(dict(report_a='attribute_confirmation',report_b='baseline'),indent=2)+'\n')
    (a.out_dir/'review-input-hashes.json').write_text(json.dumps({p.name:sha(p) for p in packet.iterdir()},indent=2)+'\n')
    print(json.dumps(dict(rows=rows,quote_checks=len(atoms),unlocated_quotes=audit['unlocated_quotes'],newly_credited_corrections=0)))


if __name__=='__main__':main()
