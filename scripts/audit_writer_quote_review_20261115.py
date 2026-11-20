"""Terminal/raw-response/parser-recovery audit; no scientific score."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from research_verify.fact_document import clean_json
from research_verify.evidence_flow import parse_review
from scripts.audit_material_exposure_20261115 import extracted_review_material
from scripts.isolated_network import assert_network_matches


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['run','recovery','reconstructed-runner','out-dir']:
        p.add_argument('--'+key, type=Path, required=True)
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    launch=json.loads((a.run/'launch.json').read_text())
    inspect=lambda cid:json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    info,ref=inspect(launch['container_id']),inspect(launch['network_reference_container'])
    assert info['State']['Status']=='exited' and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id']
    assert info['Config']['Healthcheck']['Test']==['NONE']
    assert info['Config']['Entrypoint']==['/install/.venv/bin/python']
    assert_network_matches(ref,info)
    overlays=lambda x:sorted((m['Source'],m['Destination'],m['RW'])for m in x['Mounts']if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(ref) and len(overlays(info))==3 and all(not m[2]for m in overlays(info))
    assert next(m for m in info['Mounts']if m['Destination']=='/workspace')['RW']is False
    attempt=a.run/'attempt';original=json.loads((attempt/'completion.json').read_text())
    assert original['fresh_calls']==5 and original['frozen_inputs_unchanged']
    freeze=json.loads((attempt/'prestart-freeze.json').read_text())
    changed=[]
    for filename, expected in freeze.items():
        f=Path(filename)
        if f.is_relative_to('/workspace'):
            f=Path.cwd()/f.relative_to('/workspace')
        if sha(f)!=expected:
            assert str(f.relative_to(Path.cwd())if f.is_absolute()else f)=='scripts/run_writer_quote_review_20261115.py'
            changed.append(dict(path=str(f), frozen_sha256=expected, current_sha256=sha(f)))
        if str(filename).startswith(('scripts/','local_deep_research/')):
            assert sha(attempt/'code'/filename)==expected
    assert len(changed)==1
    expected_runner=next(h for f,h in freeze.items()if f.endswith('/scripts/run_writer_quote_review_20261115.py')or f=='scripts/run_writer_quote_review_20261115.py')
    assert sha(a.reconstructed_runner)==expected_runner
    assert 'checked_claim_ids=sorted(checked)' in a.reconstructed_runner.read_text()
    launch_freeze=json.loads((a.run/'launch-freeze.json').read_text())
    for filename, expected in launch_freeze.items():
        f=Path(filename)
        if f.name=='run_writer_quote_review_20261115.py':
            assert sha(a.reconstructed_runner)==expected
        else:
            assert sha(f)==expected
    recovery=json.loads((a.recovery/'completion.json').read_text())
    assert recovery['fresh_calls']==0 and recovery['replay_exact']
    strict=a.out_dir/'strict-saved-response-replay'
    subprocess.run([sys.executable,'scripts/run_writer_quote_review_20261115.py',
                    '--out-dir',str(strict),'--replay-attempt',str(a.recovery)],check=True)
    assert json.loads((strict/'completion.json').read_text())['replay_exact']
    plan=json.loads((attempt/'plan.json').read_text())
    observations=[];metadata=[]
    for pair in plan['pairs']:
        key=pair['key'];folder=attempt/key;restored=a.recovery/key;replayed=strict/key
        old=json.loads((folder/'result.json').read_text())
        new=json.loads((restored/'result.json').read_text())
        assert old['status']=='unavailable' and old['failure']['error_type']=='TypeError'
        assert new['status']=='parsed' and new['prior_parse_failure']==old['failure']
        for name in ['prompt.txt','response.txt','baseline-response.txt','quotation-receipt.json']:
            assert (folder/name).read_bytes()==(restored/name).read_bytes()==(replayed/name).read_bytes()
        assert sha(folder/'prompt.txt')==old['prompt_sha256']==pair['prompt_sha256']
        assert sha(folder/'response.txt')==old['response_sha256']
        assert sha(folder/'baseline-response.txt')==pair['baseline_response_sha256']
        assert old['response_metadata']==new['response_metadata']
        metadata.append(old['response_metadata'])
        prompt=(folder/'prompt.txt').read_text()
        claims=json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
        receipt=json.loads((folder/'quotation-receipt.json').read_text())
        material=extracted_review_material(prompt, sorted({r['source_id']for r in receipt['quote_bindings']}
             | {int(m)for m in re.findall(r'^\[(\d+)\]\nTitle:',prompt,re.M)}))
        # The serialized source-ID set above is independently matched by the parser.
        attached=[r for r in receipt['quote_bindings']if r['status']=='window_attached']
        assert all(r['quote']in material.views[r['source_id']]['text']for r in attached)
        ids=sorted({i for r in attached for i in r['claim_ids']})
        summaries={}
        for name in ['baseline-response.txt','response.txt']:
            raw=clean_json((folder/name).read_text())
            issues,checked=parse_review((folder/name).read_text(),{c['claim_id']:c for c in claims},include_checked=True)
            summaries[name]=dict(affected_claim_entries=[x for x in raw['issues']if x.get('claim_id')in ids],
                                 native_issues=issues,native_checked=checked)
        assert summaries['response.txt']['native_issues']==new['native_issues']
        assert summaries['response.txt']['native_checked']==new['native_checked']
        observations.append(dict(key=key, restored_quote_bindings=len(attached),
                                 source_windows=len(receipt['additions']),affected_claim_ids=ids,
                                 prompt_chars=len(prompt), native_results=summaries))
    write(a.out_dir/'native-observations.json',observations)
    receipt=dict(scope='Five native-check-stage observations across TWO KNOWN reports; not independent semantic adjudication',
                 terminal_exit_code=0, model_calls=5, all_finish_reasons=[m.get('finish_reason')for m in metadata],
                 token_usage={k:sum(m.get('token_usage',{}).get(k,0)for m in metadata)
                              for k in ['prompt_tokens','completion_tokens','total_tokens']},
                 parser_failures_preserved=5, post_terminal_parser_fix=changed,
                 immutable_code_copies_verified=True, immutable_input_artifact_hashes_verified=True,
                 original_runner_snapshot_method='Original self-file was hash-frozen but not copied; reconstructed by reversing exact parser-fix edits, matching original freeze SHA256',
                 original_runner_sha256=expected_runner,
                 raw_prompt_reply_quotation_receipt_replay_exact=True, native_parser_recovery_exact=True,
                 strict_saved_response_replay_exact=True, audit_new_model_calls=0,audit_new_retrieval_calls=0,
                 source_quote_bindings_restored=sum(x['restored_quote_bindings']for x in observations),
                 exact_noop_first_round_controls=len(plan['controls']), all_prompts_within_60000=True,
                 complete_reports_rewritten=0, scientific_quality_assessed=False,new_independent_correction_credit=0)
    assert all(x['prompt_chars']<=60000 for x in observations)
    write(a.out_dir/'audit.json',receipt)
    files=[*attempt.rglob('*'),*a.out_dir.rglob('*'),*a.recovery.rglob('*'),Path(__file__),
           a.run/'launch.json',a.run/'launch-freeze.json',a.reconstructed_runner]
    manifest={str(f):sha(f)for f in files if f.is_file()}
    write(a.out_dir/'MANIFEST.json',manifest)
    assert all(sha(Path(f))==h for f,h in manifest.items())
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
