"""Exact one-group replay/provenance and provisional own-view quote audit."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.audit_material_exposure_20261115 import extracted_review_material
from scripts.prepare_native_scope_acquisition_20261115 import display_candidate
from research_verify.evidence_flow import parse_review


def read(path):return json.loads(path.read_text())
def resolve(path):return Path.cwd()/path.relative_to('/workspace') if str(path).startswith('/workspace/') else path
def sha(path):return hashlib.sha256(resolve(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(exist_ok=False)
    launch=read(args.run/'launch.json');info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    assert info['State']['Status']=='exited' and info['State']['ExitCode']==0 and info['Image']==launch['image_id']
    assert info['HostConfig']['NetworkMode']=='host' and info['Config']['Entrypoint']==['/install/.venv/bin/python']
    assert info['Config']['Healthcheck']['Test']==['NONE']
    for dest in ['/workspace',str(Path.cwd())]:assert not next(m for m in info['Mounts'] if m['Destination']==dest)['RW']
    ref=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    overlays=lambda item:sorted((m['Source'],m['Destination'],m['RW']) for m in item['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(ref) and len(overlays(info))==3 and all(not row[2] for row in overlays(info))
    attempt=args.run/'attempt';plan=read(attempt/'plan.json');result=read(attempt/'result.json');done=read(attempt/'completion.json')
    assert result['status']=='parsed' and result['origin']=='fresh_model' and done['fresh_model_calls']==1
    assert result['response_metadata']['finish_reason']=='stop' and plan['maximum_fresh_calls']==1
    for frozen in [read(args.run/'launch-freeze.json'),read(attempt/'prestart-freeze.json')]:assert all(sha(Path(p))==h for p,h in frozen.items())
    assert sha(attempt/'prompt.txt')==result['prompt_sha256'] and sha(attempt/'response.txt')==result['response_sha256']
    command=info['Config']['Cmd']
    getarg=lambda name:command[command.index(name)+1]
    replay=args.out_dir/'strict-replay'
    process=subprocess.run([sys.executable,'scripts/run_native_group_probe_20261115.py','--preflight-attempt',getarg('--preflight-attempt'),'--baseline-attempt',getarg('--baseline-attempt'),'--group',getarg('--group'),'--out-dir',str(replay),'--replay-attempt',str(attempt)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (args.out_dir/'replay-output.txt').write_text(process.stdout);assert process.returncode==0 and read(replay/'completion.json')['fresh_model_calls']==0
    assert read(replay/'result.json')['native_checked']==result['native_checked'] and read(replay/'result.json')['native_issues']==result['native_issues']
    for name in ['prompt.txt','response.txt','baseline-response.txt']:assert (attempt/name).read_bytes()==(replay/name).read_bytes()
    prompt=(attempt/'prompt.txt').read_text();old_prompt=Path(plan['baseline_prompt_path']).read_text()
    payload=json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
    old_payload=json.loads(old_prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0]);assert payload==old_payload
    old_issues,old_checked=parse_review((attempt/'baseline-response.txt').read_text(),{r['claim_id']:r for r in payload},include_checked=True)
    actual=extracted_review_material(prompt,[9,10,11,12]);before=extracted_review_material(old_prompt,[9,10,11,12])
    assert actual.views[11]['text']==before.views[11]['text'] and 'Mcpt8' not in actual.views[11]['text'] and 'GFP' not in actual.views[11]['text']
    rows=[]
    for check in result['native_checked']+result['native_issues']:
        sid=int(check['source_id']);view=actual.views[sid]['text'];quotes=[]
        for q in check.get('evidence_quote',[]):quotes.append(dict(role='claim',text=q))
        for atom in check.get('atom_checks',[]):
            q=atom.get('evidence_quote')
            if isinstance(q,str) and q:quotes.append(dict(role=atom.get('attribute'),text=q))
        for q in quotes:
            q['literal_in_own_supplied_view']=q['text'] in view
            q['display_location']=display_candidate(q['text'],view) if not q['literal_in_own_supplied_view'] else None
        rows.append(dict(claim_id=check['claim_id'],source_id=sid,native_status=check['status'],quotes=quotes,semantic_support_verified=False))
    write(args.out_dir/'own-view-quote-bindings.json',rows)
    write(args.out_dir/'observations.json',dict(scope='Coordinator source-view diagnosis, not independent scientific outcome assessment.',baseline_issues=old_issues,baseline_checked=old_checked,new_issues=result['native_issues'],new_checked=result['native_checked'],same_claims=True,same_source11_bytes=True,
        source9='Restored original acquired MACS paragraph supports the stated antibodies/beads/magnetic separation. New native label changes from contradiction to supported; no report edit and no original-allegation correction credit.',
        source11='Same supplied abstract contains neither Mcpt8 nor GFP. New supported atom quotes Mcpt8^GFP transgenic mice despite absence from its own supplied view. Do not equate old-view absence with paper-level falsity; newly acquired original body investigation is separate.',
        source12='Selected view contains neither CD14 nor CD117-high, but native approves combined marker panel using noncontinuous expression/yield phrases. Full acquired body has separate assay contexts; its availability elsewhere is not selected-quote support.',
        decision='Do not promote full focused native rerun merely to obtain all-supported labels. Whole-report original-source useful-retention/new-error clearance and independent review remain incomplete.',report_rewrites=0,new_independent_correction_credit=0))
    write(args.out_dir/'audit.json',dict(terminal_exit=0,fresh_calls=1,strict_replay_fresh_calls=0,prompt_chars=len(prompt),actual_usage=result['response_metadata']['token_usage'],native_issue_count=len(result['native_issues']),native_checked_count=len(result['native_checked']),scientific_quality_pass=False,new_independent_correction_credit=0))
    files=[*[p for p in args.run.rglob('*') if p.is_file()],*[p for p in args.out_dir.rglob('*') if p.is_file()],Path(__file__)]
    manifest={str(p):sha(p) for p in files};write(args.out_dir/'MANIFEST.json',manifest);assert all(sha(Path(p))==h for p,h in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest),manifest_sha256=sha(args.out_dir/'MANIFEST.json'),fresh_calls=1,issue_count=len(result['native_issues']),checked_count=len(result['native_checked']),quality_pass=False)))


if __name__=='__main__':main()
