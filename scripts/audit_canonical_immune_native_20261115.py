"""Inspect terminal native run and actual prompt/source boundaries; no scoring."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.audit_material_exposure_20261115 import extracted_review_material


def read(path):
    return json.loads(path.read_text())


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def resolve(path):
    return Path.cwd()/path.relative_to('/workspace') if str(path).startswith('/workspace/') else path


def sha(path):
    return hashlib.sha256(resolve(path).read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def requests(folder):
    return [row['data'] for row in map(json.loads,(folder/'trace.jsonl').read_text().splitlines()) if row.get('stage')=='native_check_request']


def claims(prompt):
    return json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(exist_ok=False)
    launch=read(args.run/'launch.json')
    info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    assert info['State']['Status']=='exited' and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id'] and info['HostConfig']['NetworkMode']=='host'
    assert info['Config']['Entrypoint']==['/install/.venv/bin/python'] and info['Config']['Healthcheck']['Test']==['NONE']
    for destination in ['/workspace',str(Path.cwd())]:
        assert not next(m for m in info['Mounts'] if m['Destination']==destination)['RW']
    reference=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    def overlays(value):
        return sorted((m['Source'],m['Destination'],m['RW']) for m in value['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(reference) and len(overlays(info))==3
    assert all(not row[2] for row in overlays(info))
    attempt=args.run/'attempt'
    for frozen in [read(args.run/'launch-freeze.json'),read(attempt/'prestart-freeze.json')]:
        assert all(sha(Path(path))==value for path,value in frozen.items())
    for path in (attempt/'code').rglob('*'):
        if path.is_file():assert path.read_bytes()==resolve(Path(path.relative_to(attempt/'code'))).read_bytes()
    plan=read(attempt/'plan.json');done=read(attempt/'completion.json')
    assert plan['settings']['general.enable_fact_checking'] and not plan['settings']['verify.enable_citation_qc']
    assert plan['settings']['citation.bound_complete_review_prompt'] and plan['maximum_fresh_native_calls']==16
    assert done['status']=='native_pipeline_executed' and done['fresh_model_calls']<=16
    usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)
    calls=read(attempt/'calls.json');unavailable=[];nonstop=[]
    for call in calls:
        index=call['index'];prompt=attempt/f'call-{index:02d}-prompt.txt'
        assert sha(prompt)==call['prompt_sha256']
        if call.get('origin')=='fresh_model':assert len(prompt.read_text())<=60000
        if call['status']!='returned':
            unavailable.append(call);continue
        assert sha(attempt/f'call-{index:02d}-response.txt')==call['response_sha256']
        if call.get('origin')=='fresh_model':
            if call['response_metadata'].get('finish_reason')!='stop':nonstop.append(index)
            for key in usage:usage[key]+=call['response_metadata']['token_usage'][key]
    root=Path('evaluation/frontier-strategy-20261113')
    names=['canonical-immune-native-default-preflight-20261115-v2','canonical-immune-native-bounded-preflight-20261115-v1','canonical-immune-native-bounded-preflight-20261115-v2']
    versions={name:requests(root/name) for name in names}
    original=versions[names[0]];compact=versions[names[1]];split=versions[names[2]]
    def index_claims(rows):
        found={}
        for row in rows:
            for claim in claims(row['prompt']):
                key=claim['claim_id'];assert key not in found;found[key]=claim
        return found
    assert index_claims(original)==index_claims(split)
    before=extracted_review_material(original[0]['prompt'],original[0]['source_ids'])
    compressed=extracted_review_material(compact[0]['prompt'],compact[0]['source_ids'])
    after=[extracted_review_material(row['prompt'],row['source_ids']) for row in split[:3]]
    assert len(before.views[3]['text'])==46145 and len(compressed.views[3]['text'])==5260
    assert all(view.views[3]['text']==before.views[3]['text'] for view in after)
    actual=requests(attempt);source_boundaries=[]
    for row in actual:
        material=extracted_review_material(row['prompt'],row['source_ids'])
        source_boundaries.append(dict(group=row['review_group'],round=row['round'],claim_ids=row['claim_ids'],prompt_chars=row['prompt_chars'],sources=[dict(source_id=sid,chars=len(view['text']),sha256=digest(view['text'])) for sid,view in material.views.items()]))
    writer=Path(plan['writer_attempt'])/'candidate-report.md'
    final=attempt/'report.md';review=read(attempt/'native-review.json')
    write(args.out_dir/'budget-boundary-audit.json',dict(default_off_overflow_chars=original[0]['prompt_chars'],first_material_repack_prompt_chars=compact[0]['prompt_chars'],first_material_repack_source3_chars=5260,split_first_three_prompt_chars=[row['prompt_chars'] for row in split[:3]],split_source3_chars=46145,claim_ids_and_payloads_preserved=True,original_groups=len(original),split_groups=len(split),native_call_limit_unchanged=16,actual_source_boundaries=source_boundaries,semantic_support_verified=False))
    write(args.out_dir/'audit.json',dict(execution_provenance_passed=True,terminal_exit=0,actual_fresh_native_calls=done['fresh_model_calls'],actual_native_usage=usage,unavailable_calls=unavailable,nonstop_model_calls=nonstop,writer_chars=len(writer.read_text()),writer_sha256=sha(writer),final_chars=len(final.read_text()),final_sha256=sha(final),writer_unchanged_by_native=writer.read_bytes()==final.read_bytes(),native_review=review,independent_scientific_assessment_complete=False,useful_retention_and_new_error_clearance=False,new_independent_correction_credit=0,limits='Native labels and repairs are fallible model output, not independent original-source adjudication. Known task only. Prompt grouping/source exposure changed in this native arm and extra reading/generation compute is declared. No full native saved-response replay or model repeat claimed. Earlier generation audit captured code before review-budget changes; its frozen copies remain authoritative for that stage.'))
    paths=[*[path for path in args.run.rglob('*') if path.is_file()],*[path for path in args.out_dir.rglob('*') if path.is_file()],Path(__file__),Path('local_deep_research/tests/test_complete_review_prompt_budget.py')]
    manifest={str(path):sha(path) for path in paths}
    write(args.out_dir/'MANIFEST.json',manifest)
    assert all(sha(Path(path))==value for path,value in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest),manifest_sha256=sha(args.out_dir/'MANIFEST.json'),fresh_native_calls=done['fresh_model_calls'],final_chars=len(final.read_text()),writer_unchanged=writer.read_bytes()==final.read_bytes(),new_independent_correction_credit=0)))


if __name__=='__main__':main()
