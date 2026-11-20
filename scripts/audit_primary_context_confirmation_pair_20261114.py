"""Verify frozen inputs, source-only prompt delta and exact decision/application replay."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.run_primary_context_confirmation_pair_20261114 import prepare
from research_verify.evidence_flow import confirm_repairs


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());state=json.loads(subprocess.check_output(['docker','inspect',handle['container']]))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text());root=Path.cwd()
    for n,h in freeze.items():
        original=Path(n);rel=original.relative_to('/workspace') if original.is_relative_to('/workspace') else original
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists()else root/rel)==h
    assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True and c['preflight_only'] is False
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']
    jobs,inputs,body,ids=prepare();assert (a.attempt/'primary-body.txt').read_text()==body
    replayed=[];results=[]
    def invoke(prompt,**kw):
        call=calls[len(replayed)];assert call['stage']==kw['stage'];folder=a.attempt/call['folder'];pp=folder/f"call-{call['call_id']:03d}-prompt.txt"
        assert prompt==pp.read_text() and sha(pp)==call['prompt_sha256'];replayed.append(call)
        rp=pp.with_name(pp.name.replace('-prompt','-response'))
        if call['status']!='returned':raise RuntimeError('Recorded unavailable call')
        assert sha(rp)==call['response_sha256'];return rp.read_text()
    handler=SimpleNamespace(get_setting=lambda k,d=None:True if k in {'citation.attribute_confirmation_review','citation.confirmation_consistency_review'}else d,_invoke_text=invoke)
    for job in jobs:
        report,applied,pending=confirm_repairs(handler,job['report'],[job['issue']],job['material'],job['query'],SimpleNamespace(record=lambda *args:None))
        folder=a.attempt/f"claim-{job['issue']['claim_id']}"/job['arm'];r=json.loads((folder/'result.json').read_text())
        assert report==(folder/'report.txt').read_text() and sha(folder/'report.txt')==r['report_sha256']
        assert applied==r['native_applied'] and pending==r['native_unresolved']
        recovered=report
        for change in reversed(applied):
            assert recovered.count(change['replacement'])==1
            recovered=recovered.replace(change['replacement'],change['statement'],1)
        assert recovered==job['report']
        results.append(dict(claim_id=r['claim_id'],arm=r['arm'],applied=len(applied),unresolved=len(pending),report_sha256=r['report_sha256']))
    assert len(replayed)==len(calls)
    prompts={}
    for call in calls:
        if call['stage']=='repair_validation':prompts[(call['claim_id'],call['arm'])]=(a.attempt/call['folder']/f"call-{call['call_id']:03d}-prompt.txt").read_text()
    assert prompts[18,'abstract_union']==prompts[18,'primary_body']
    decoder=json.JSONDecoder();before,after=prompts[19,'abstract_union'].split('\nCandidates:\n',1);full_before,full_after=prompts[19,'primary_body'].split('\nCandidates:\n',1)
    old,oe=decoder.raw_decode(after);new,ne=decoder.raw_decode(full_after)
    assert before==full_before and after[oe:]==full_after[ne:] and len(old)==len(new)==1
    oc=old[0].pop('source_contexts');nc=new[0].pop('source_contexts');assert old==new and len(oc)==len(nc)==2
    assert oc[0]==nc[0] and oc[1]['source_id']==nc[1]['source_id']==15
    assert nc[1]['context']==body and nc[1]['metadata'].startswith(oc[1]['metadata'])
    assert all(x in body for x in ['302 genes','11 groups','22 groups'])
    a.out_dir.mkdir(parents=True,exist_ok=False)
    audit=dict(verified_launch_startup_completion_hashes=True,exit_code=0,calls=len(calls),exact_prompt_response_and_application_replay=True,
        unchanged_control_prompt=True,only_source15_context_and_scope_metadata_changed=True,
        entire_primary_body_supplied=True,primary_article_ids=ids,results=results,
        quality_claim=None,newly_credited_corrections=0,
        limits=['Fixed actual proposals only; not end-to-end discovery or new writer','Prior whole-report25 calls and acquisition excluded from stage cost',
                'Context budget80000 versus prior60000; first full-text request62023chars',
                'Full-text body extraction does not include every table/reference/supplement',
                'No independent original-source correction/retention/new-error adjudication or generalization'])
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),results=results)))


if __name__=='__main__':main()
