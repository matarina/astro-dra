"""Exact offline quote-selection and independent confirmation replay; no quality score."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from types import SimpleNamespace
from scripts.run_quote_reselection_pair_20261114 import prepare
from research_verify.quote_reselection import quotation_prompt,parse_quote_updates
from research_verify.evidence_flow import confirm_repairs


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    h=json.loads((a.attempt.parent/'execution-handle.json').read_text());state=json.loads(subprocess.check_output(['docker','inspect',h['container']]))[0]
    assert state['Id']==h['container_id']and state['State']['Status']=='exited'and state['State']['ExitCode']==0
    freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd()
    for n,digest in freeze.items():
        path=Path(n);rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path;snapshot=a.attempt/'code'/rel
        assert sha(snapshot if snapshot.exists()else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text());assert all(freeze.get('/workspace/'+n,freeze.get(n))==v for n,v in launch.items())
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged']is True;calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']
    issues,material,original,query,inputs=prepare();replayed=[]
    def invoke(prompt,**kw):
        call=calls[len(replayed)];assert call['stage']==kw['stage'];folder=a.attempt/call['folder'];pp=folder/f"call-{call['call_id']:03d}-prompt.txt";rp=pp.with_name(pp.name.replace('-prompt','-response'))
        assert prompt==pp.read_text()and sha(pp)==call['prompt_sha256'];replayed.append(call)
        assert call['status']=='returned'and sha(rp)==call['response_sha256'];return rp.read_text()
    handler=SimpleNamespace(get_setting=lambda k,d=None:True if k in {'citation.attribute_confirmation_review','citation.confirmation_consistency_review'}else d,_invoke_text=invoke)
    trace=SimpleNamespace(record=lambda *a:None)
    report,applied,pending=confirm_repairs(handler,original,issues,material,query,trace)
    baseline=json.loads((a.attempt/'baseline/result.json').read_text());assert not replayed and report==original and not applied and pending==baseline['native_unresolved']
    updated,receipts=parse_quote_updates(invoke(quotation_prompt(issues,material),stage='quote_reselection'),issues,material)
    allowed={'source_id','source_ids','evidence_sources','evidence_quote'}
    for before,after in zip(issues,updated,strict=True):assert {k:v for k,v in before.items()if k not in allowed}=={k:v for k,v in after.items()if k not in allowed}
    report,applied,pending=confirm_repairs(handler,original,updated,material,query,trace)
    result=json.loads((a.attempt/'reselected/result.json').read_text());assert updated==result['issues']and receipts==result['quote_receipts']and applied==result['native_applied']and pending==result['native_unresolved']
    assert report==(a.attempt/'reselected/report.txt').read_text()and sha(a.attempt/'reselected/report.txt')==result['report_sha256']
    recovered=report
    for edit in reversed(applied):assert recovered.count(edit['replacement'])==1;recovered=recovered.replace(edit['replacement'],edit['statement'],1)
    assert recovered==original and len(replayed)==len(calls)
    audit=dict(exit_code=0,verified_launch_start_completion_hashes=True,calls=len(calls),baseline_confirmation_calls=0,
        fixed_statements_replacements_and_statuses=True,quotes_validated_in_own_source=True,exact_confirmation_replay=True,inverse_only_recorded_edit_reconstruction=True,
        applied=len(applied),report_sha256=result['report_sha256'],quality_claim=None,newly_credited_corrections=0,
        limits=['Fixed proposal only, not integrated whole-report path','Matches previously produced local report; not a new correction','Original source-language/time eligibility and independent retention/new-error adjudication unresolved'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes());print(json.dumps(audit))


if __name__=='__main__':main()
