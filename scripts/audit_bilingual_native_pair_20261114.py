"""Audit literal exposure and native revisions, without semantic scoring."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.claim_language import fidelity_prompt, parse_fidelity, bilingual_notes, original_language_comparison_notes
from research_verify.source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS
from research_verify.comparison_reconciliation import reconciliation_notes
from research_verify.evidence_flow import confirm_repairs


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
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']<=10
    paths={}
    for call in calls:
        found=list(a.attempt.glob(f"**/call-{call['call_id']:03d}-prompt.txt"));assert len(found)==1
        path=found[0];paths[call['call_id']]=path;assert sha(path)==call['prompt_sha256']
        assert call['status']=='returned' and sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    rows=[];linguistic=[]
    for job in plan['jobs']:
        folder=a.attempt/job['name'];claims={int(k):v for k,v in job['claims'].items()};readings={int(k):v for k,v in job['readings'].items()}
        selected=[x for x in calls if x['job']==job['name']]
        if plan.get('cached_fidelity'):
            prior=Path(plan['cached_fidelity_attempt'])
            if prior.is_relative_to('/workspace'):prior=root/prior.relative_to('/workspace')
            prior_calls=json.loads((prior/'calls.json').read_text())
            fcall=next(x for x in prior_calls if x['job']==job['name'] and x['stage']=='linguistic_fidelity')
            fp=prior/job['name']/f"call-{fcall['call_id']:03d}-prompt.txt"
            assert sha(fp)==fcall['prompt_sha256'] and sha(fp.with_name(fp.name.replace('-prompt','-response')))==fcall['response_sha256']
        else:
            fcall=next(x for x in selected if x['stage']=='linguistic_fidelity');fp=paths[fcall['call_id']]
        assert fp.read_text()==fidelity_prompt(claims,readings)
        fidelity=parse_fidelity(fp.with_name(fp.name.replace('-prompt','-response')).read_text(),claims)
        assert {str(k):v for k,v in fidelity.items()}==json.loads((folder/'fidelity.json').read_text())
        linguistic.append(dict(job=job['name'],reviews=fidelity,scope='Fallible source-blind linguistic review, not independent semantic gold'))
        original=(folder/'original-report.txt').read_text();assert sha(folder/'original-report.txt')==job['original_report_sha256']
        for arm in plan['arms']:
            r=json.loads((folder/arm/'result.json').read_text());nc=next(x for x in selected if x['arm']==arm and x['stage']=='native_check')
            prompt=paths[nc['call_id']].read_text();suffix='\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS
            if plan.get('reconcile_observations'):
                suffix+='\n\n'+reconciliation_notes(claims,readings,fidelity,job['english_review'],
                    job['original_review'] if arm=='dual_observations' else None)
            if arm=='bilingual':suffix+='\n\n'+(original_language_comparison_notes(readings,fidelity,job['english_review'])
                if plan.get('fixed_english_observations') else bilingual_notes(readings,fidelity))
            assert prompt.endswith(suffix);base=prompt[:-len(suffix)];assert hashlib.sha256(base.encode()).hexdigest()==job['native_prompt_sha256']
            material=base.split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
            assert hashlib.sha256(material.encode()).hexdigest()==job['material_sha256']
            # Reconstruct the native confirmation request without making a model call.
            captured=[]
            handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d),
                '_invoke_text':staticmethod(lambda prompt,**kw:captured.append(prompt) or '{"decisions":[]}')})()
            trace=type('Trace',(),{'record':staticmethod(lambda *args,**kw:None)})()
            confirm_repairs(handler,original,r['issues'],material,job['query'],trace)
            actual=[paths[x['call_id']].read_text() for x in selected if x['arm']==arm and x['stage']=='repair_validation']
            assert captured==actual
            for issue in r['issues']:
                assert issue['statement']==claims[issue['claim_id']]['text']
            report=(folder/arm/'report.txt').read_text();assert sha(folder/arm/'report.txt')==r['report_sha256']
            restored=report
            for issue in reversed(r['native_applied']):
                assert restored.count(issue['replacement'])==1;restored=restored.replace(issue['replacement'],issue['statement'],1)
            assert restored==original
            rows.append(dict(job=job['name'],arm=arm,status=r['status'],native_applied=r['native_applied'],
                report_sha256=r['report_sha256'],report_chars=len(report),original_language_statements=True,
                same_native_confirmation_request_replayed=True,only_recorded_native_replacements=True))
    audit=dict(scope='Two exposed groups, not whole-report coverage or independent correction/retention/new-error assessment',
        exit_code=0,verified_launch_startup_completion_hashes=True,calls=len(calls),linguistic_reviews=linguistic,rows=rows,
        quality_claim=None,newly_credited_corrections=0)
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),rows=[dict(job=r['job'],arm=r['arm'],applied=len(r['native_applied'])) for r in rows])))


if __name__=='__main__':main()
