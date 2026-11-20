"""Audit actual matched Writer stage; never call it full native/semantic success."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from research_verify.evidence_flow import cited_indices


def read(p):return json.loads(p.read_text())
def resolve(p):return Path.cwd()/p.relative_to('/workspace')if str(p).startswith('/workspace/')else p
def sha(p):return hashlib.sha256(resolve(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--reader-run',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    launch=read(a.run/'launch.json');info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    assert info['State']['Status']=='exited'and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id']and info['HostConfig']['NetworkMode']=='host'
    assert info['Config']['Entrypoint']==['/install/.venv/bin/python']and info['Config']['Healthcheck']['Test']==['NONE']
    for dest in ['/workspace',str(Path.cwd())]:assert not next(m for m in info['Mounts']if m['Destination']==dest)['RW']
    ref=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    overlays=lambda x:sorted((m['Source'],m['Destination'],m['RW'])for m in x['Mounts']if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(ref)and len(overlays(info))==3 and all(not m[2]for m in overlays(info))
    attempt=a.run/'attempt';done=read(attempt/'completion.json');plan=read(attempt/'plan.json');calls=read(attempt/'calls.json')
    assert done['status']=='completed_writer_stage'and done['fresh_model_calls']==1 and done['strict_reader_cached_calls']==4 and done['reader_batches_completed']==4
    assert plan['query_sha256']=='47c54edcc0eba1729bd5a70d759588b116eae37810bcecd2a3b8953176283338'
    for freeze in [read(a.run/'launch-freeze.json'),read(attempt/'prestart-freeze.json')]:assert all(sha(Path(k))==h for k,h in freeze.items())
    for f in (attempt/'code').rglob('*'):
        if f.is_file():assert f.read_bytes()==resolve(Path(f.relative_to(attempt/'code'))).read_bytes()
    usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)
    for c in calls:
        i=c['index'];assert c['origin']==('fresh_model'if c['stage']=='writer'else'strict_reader_cache')and c['status']=='returned'and c['response_metadata']['finish_reason']=='stop'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==c['prompt_sha256']and sha(attempt/f'call-{i:02d}-response.txt')==c['response_sha256']
        assert c['prompt_chars']<=(360000 if c['stage']=='writer' else 140000)
        if c['origin']=='fresh_model':
            for k in usage:usage[k]+=c['response_metadata']['token_usage'][k]
    prefix=Path('evaluation/frontier-strategy-20261113/section-writer-model-20261115-v1/attempt/native-writer-prefix.txt').read_text()
    writer=(attempt/'call-04-prompt.txt').read_text();assert writer.startswith(prefix+'\nADDITIONAL FALLIBLE SOURCE-ONLY FIELD NOTES:\n')
    observations=read(attempt/'observations.json');ids={r['source_id']for r in observations}
    assert ids.issubset(set(range(1,21)))
    for o in observations:
        assert hashlib.sha256(o['quote'].encode()).hexdigest()==o['unit_sha256']
    reader=read(a.reader_run/'launch.json');ri=json.loads(subprocess.check_output(['docker','inspect',reader['container_id']]))[0]
    assert ri['State']['Status']=='exited'and ri['State']['ExitCode']==2
    prior=a.reader_run/'attempt';pd=read(prior/'completion.json');assert pd['fresh_model_calls']==4 and pd['reader_batches_completed']==4 and not(prior/'candidate-report.md').exists()
    for freeze in [read(a.reader_run/'launch-freeze.json'),read(prior/'prestart-freeze.json')]:assert all(sha(Path(k))==h for k,h in freeze.items())
    pc=read(prior/'calls.json');assert len(pc)==4
    for old,new in zip(pc,calls[:4]):
        i=old['index'];assert old['origin']=='fresh_model'and old['response_metadata']['finish_reason']=='stop'
        for kind in ['prompt','response']:
            pp=prior/f'call-{i:02d}-{kind}.txt';np=attempt/f'call-{i:02d}-{kind}.txt'
            assert pp.read_bytes()==np.read_bytes()and sha(pp)==old[kind+'_sha256']
        for k in usage:usage[k]+=old['response_metadata']['token_usage'][k]
    replay=a.out_dir/'strict-replay'
    proc=subprocess.run([sys.executable,'scripts/run_canonical_immune_writer_compact_20261115.py','--out-dir',str(replay),'--replay-attempt',str(attempt),'--reader-cache',str(prior)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (a.out_dir/'strict-replay-output.txt').write_text(proc.stdout);assert proc.returncode==0
    rd=read(replay/'completion.json');assert rd['fresh_model_calls']==0 and rd['exact_report_replay']
    for i in range(5):
        for kind in ['prompt','response']:assert(attempt/f'call-{i:02d}-{kind}.txt').read_bytes()==(replay/f'call-{i:02d}-{kind}.txt').read_bytes()
    report=(attempt/'candidate-report.md').read_text();cited=set(cited_indices(report))
    write(a.out_dir/'audit.json',dict(execution_provenance_audit_passed=True,actual_model_usage=usage,actual_writer_prompt_chars=len(writer),original_prefix_chars=len(prefix),report_chars=len(report),report_sha256=sha(attempt/'candidate-report.md'),actual_fresh_reader_calls=4,actual_fresh_writer_calls=1,original_oversize_attempt_preserved=True,field_observations=len(observations),source_ids_with_field_notes=sorted(ids),source_ids_without_field_notes=sorted(set(range(1,21))-ids),cited_source_ids=sorted(cited),foreign_citation_ids=sorted(cited-set(range(1,21))),strict_replay_fresh_calls=0,full_native_pipeline_complete=False,independent_source_assessment_complete=False,useful_retention_and_new_error_clearance=False,new_independent_correction_credit=0,limits='One known task; same source packet/draft/native prefix/clock but additional field reading compute and notes, max12000tokens rather than older8000generation. Not cost parity or unseen-task generalization. No semantic adoption inferred. Previous acquisition test failures remain unresolved.'))
    files=[*[f for f in a.reader_run.rglob('*')if f.is_file()],*[f for f in a.run.rglob('*')if f.is_file()],*[f for f in a.out_dir.rglob('*')if f.is_file()],Path(__file__)]
    manifest={str(f):sha(f)for f in files};write(a.out_dir/'MANIFEST.json',manifest);assert all(sha(Path(k))==h for k,h in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest),manifest_sha256=sha(a.out_dir/'MANIFEST.json'),audit=read(a.out_dir/'audit.json'))))


if __name__=='__main__':main()
