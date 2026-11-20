"""Terminal integrity and report-change evidence; no semantic correction score."""
import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True);a=ap.parse_args()
    # Check terminal state before creating audit/delivery artifacts.
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    completion=json.loads((a.attempt/'completion.json').read_text());assert completion['frozen_inputs_unchanged'] is True
    a.out_dir.mkdir(parents=True,exist_ok=False)
    root=Path.cwd();freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    for name,digest in freeze.items():
        p=Path(name);rel=p.relative_to('/workspace') if p.is_relative_to('/workspace') else (p.relative_to(root) if p.is_absolute() else p)
        saved=a.attempt/'code'/rel
        assert sha(saved if saved.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+name,freeze.get(name))==digest for name,digest in launch.items())
    plan=json.loads((a.attempt/'plan.json').read_text());original=(a.attempt/'original-report.txt').read_text()
    assert sha(a.attempt/'original-report.txt')==plan['report_sha256']
    rows=[];materials={};diffs=[]
    for result in completion['arms']:
        arm=result['arm'];folder=a.attempt/arm;report=(folder/'report.txt').read_text()
        assert sha(folder/'report.txt')==result['report_sha256']
        calls=json.loads((folder/'calls.json').read_text());assert len(calls)==result['model_calls']
        for call in calls:
            prefix=folder/f"call-{call['call_id']:03d}"
            assert sha(Path(str(prefix)+'-prompt.txt'))==call['prompt_sha256']
            if call.get('response_sha256'):assert sha(Path(str(prefix)+'-response.txt'))==call['response_sha256']
        events=[json.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
        snapshots=[e['data'] for e in events if e['stage']=='review_snapshot']
        assert len(snapshots)==1 and snapshots[0]['text']==original
        requests=[e['data'] for e in events if e['stage']=='native_check_request']
        prepared={}
        for r in requests:
            assert r['report_text_sha256']==plan['report_sha256']
            material=r['prompt'].split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
            prepared[str((r['review_group'],r['round']))]=dict(material_sha256=hashlib.sha256(material.encode()).hexdigest(),
                claim_ids=r['claim_ids'],source_ids=r['source_ids'],review_text=r['review_text'])
        materials[arm]=prepared
        blocks=[]
        for tag,i,j,k,l in difflib.SequenceMatcher(None,original,report,autojunk=False).get_opcodes():
            if tag!='equal':blocks.append(dict(operation=tag,original_start=i,original_end=j,report_start=k,report_end=l,
                                               original_text=original[i:j],revised_text=report[k:l]))
        diff=''.join(difflib.unified_diff(original.splitlines(keepends=True),report.splitlines(keepends=True),fromfile='original',tofile=arm))
        (a.out_dir/(arm+'-changes.diff')).write_text(diff)
        (a.out_dir/(arm+'-change-spans.json')).write_text(json.dumps(blocks,ensure_ascii=False,indent=2)+'\n')
        rows.append(dict(arm=arm,model_calls=len(calls),native_applied=len(result['native_applied']),
            native_unresolved=len(result['native_unresolved']),changed=report!=original,change_blocks=len(blocks),
            original_chars=len(original),report_chars=len(report),
            invalid_native_replies=sum(e['stage']=='native_check_invalid' for e in events),
            report_sha256=result['report_sha256'],native_request_count=len(requests),
            max_native_prompt_chars=max((len(r['prompt']) for r in requests),default=0),
            native_prompt_over_budget=sum(len(r['prompt'])>r['prompt_budget'] for r in requests),
            supplementary_requests=result['supplement_requests']))
    same_group_material=materials['baseline']==materials[plan['arms'][1]]
    if plan.get('comparison')!='review_unit_boundaries':
        assert same_group_material,'Matched native group source exposure differs'
    audit=dict(scope='Execution/input matching and literal report changes only; not independent source adjudication',
        container_id=state['Id'],image_id=state['Image'],exit_code=state['State']['ExitCode'],
        verified_launch_startup_completion_hashes=True,matched_original_report_and_source_pool=True,
        matched_group_source_material=same_group_material,comparison=plan.get('comparison'),
        native_groups_per_arm={arm:len(value) for arm,value in materials.items()},
        rows=rows,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    # New coordinator-owned review packet, separate from the reviewer's artifacts.
    packet=a.out_dir/'independent-review-inputs';packet.mkdir()
    mapping=dict(report_a=plan['arms'][1],report_b='baseline')
    for label,arm in mapping.items():(packet/(label+'.txt')).write_bytes((a.attempt/arm/'report.txt').read_bytes())
    (packet/'original-report.txt').write_bytes((a.attempt/'original-report.txt').read_bytes())
    (packet/'original-question.txt').write_text(plan['query'])
    manifest_name=next(name for name in freeze if name.endswith('/case-manifest.json'))
    manifest_path=root/Path(manifest_name).relative_to('/workspace') if manifest_name.startswith('/workspace/') else Path(manifest_name)
    manifest=json.loads(manifest_path.read_text());source_path=root/manifest['cases'][0]['source']
    assert sha(source_path)==plan['source_pack_sha256'];(packet/'sources.json').write_bytes(source_path.read_bytes())
    (packet/'README.txt').write_text('Compare both reports with the unchanged original and original request using primary sources. '
        'Supplied sources are newly acquired metadata/abstracts; unresolved records remain unknown. '
        'Assess factual/identity/scope corrections, useful content retention, omissions and new errors separately. '
        'Model verdicts are not adjudication. This single-task post-writer experiment cannot establish a six-task majority or generalization.\n')
    (a.out_dir/'coordinator-only-blind-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
    (a.out_dir/'review-input-hashes.json').write_text(json.dumps({p.name:sha(p) for p in packet.iterdir()},indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
