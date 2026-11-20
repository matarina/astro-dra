"""Audit a negative/failed two-arm writer probe without converting it to success."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def read(p):return json.loads(p.read_text())
def source_path(p):
    return Path.cwd()/p.relative_to('/workspace') if str(p).startswith('/workspace/') else p


def sha(p):return hashlib.sha256(source_path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    launch=read(a.run/'launch.json');info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    state=info['State'];assert state['Status']=='exited'and state['ExitCode']==2
    assert info['Image']==launch['image_id']and info['HostConfig']['NetworkMode']=='host'
    assert info['Config']['Entrypoint']==['/install/.venv/bin/python']and info['Config']['Healthcheck']['Test']==['NONE']
    for dest in ['/workspace',str(Path.cwd())]:assert not next(m for m in info['Mounts']if m['Destination']==dest)['RW']
    ref=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    overlays=lambda x:sorted((m['Source'],m['Destination'],m['RW'])for m in x['Mounts']if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(ref)and len(overlays(info))==3 and all(not r[2]for r in overlays(info))
    attempt=a.run/'attempt'
    for freeze in [read(a.run/'launch-freeze.json'),read(attempt/'prestart-freeze.json')]:
        assert all(sha(Path(k))==v for k,v in freeze.items())
    for f in (attempt/'code').rglob('*'):
        if f.is_file():assert f.read_bytes()==source_path(Path(f.relative_to(attempt/'code'))).read_bytes()
    calls=read(attempt/'calls.json');done=read(attempt/'completion.json');assert len(calls)==2 and done['fresh_model_calls']==2 and done['failures']==1
    usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)
    for c in calls:
        i=c['index'];assert c['origin']=='fresh_model'and c['status']=='returned'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==c['prompt_sha256']
        assert sha(attempt/f'call-{i:02d}-response.txt')==c['response_sha256']
        assert c['response_metadata']['finish_reason']=='stop'and c['prompt_chars']<=60000
        for k in usage:usage[k]+=c['response_metadata']['token_usage'][k]
    replay=a.out_dir/'strict-replay'
    command=[sys.executable,'scripts/run_revisable_writer_pair_20261115.py','--out-dir',str(replay),'--replay-attempt',str(attempt)]
    proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (a.out_dir/'strict-replay-output.txt').write_text(proc.stdout);assert proc.returncode==2
    rd=read(replay/'completion.json');assert rd['fresh_model_calls']==0 and rd['failures']==1 and rd['replay_exact']and rd['results']==done['results']
    for i in range(2):
        for kind in ['prompt','response']:assert (attempt/f'call-{i:02d}-{kind}.txt').read_bytes()==(replay/f'call-{i:02d}-{kind}.txt').read_bytes()
    assert (attempt/'immutable/report.md').read_bytes()==(replay/'immutable/report.md').read_bytes()
    assert not(attempt/'revisable/report.md').exists()
    root=Path('evaluation/frontier-strategy-20261113')
    views=read(root/'native-scope-acquisition-inputs-20261115-v1/acquired-views.json');source=views[0]['text']
    notes=read(root/'scope-acquisition-reader-model-20261115-v1/attempt/acquired/span_ids-parsed.json')['registry']
    receipt=read(attempt/'immutable/rendering.json');report=(attempt/'immutable/report.md').read_text()
    assert receipt['selected_fact_ids']==list(notes)and not receipt['writer_revisions']
    for r in receipt['facts']+receipt['identities']+receipt['generated_prose']:assert report[r['start']:r['end']]==r['rendered']
    assert all(report.count(n['text'])>=1 for n in notes.values())
    raw=(attempt/'call-01-response.txt').read_text()
    try:
        from research_verify.fact_document import clean_json
        clean_json(raw)
    except json.JSONDecodeError as exc:
        syntax=dict(type='JSONDecodeError',line=exc.lineno,column=exc.colno,offset=exc.pos,message=exc.msg)
    else:raise AssertionError('Expected actual parse failure')
    lexical=re.findall(r'"revisions"\s*:\s*(\[[^\]]*\])',raw)
    write(a.out_dir/'writer-boundary-observations.json',dict(
        scope='Coordinator provisional observations, not independent scientific adjudication.',
        immutable=dict(selected_fact_ids=receipt['selected_fact_ids'],note_text_occurrences={k:report.count(v['text'])for k,v in notes.items()},all_four_original_notes_copied=True,known_relation_concern_copied=notes['19:0']['text'],unassessed_generated_prose=receipt['generated_prose']),
        revisable=dict(usable_report=False,syntax_failure=syntax,raw_response_sha256=sha(attempt/'call-01-response.txt'),lexical_revision_arrays=lexical,lexical_nonempty_revision_arrays=sum(s.strip()!='[]'for s in lexical),semantic_inference_from_malformed_response=False),
        conclusion='This execution does not support adopting optional note revisions as a semantic fix. No retry, permissive JSON repair, scientific edit, report success or independent correction is credited.',
        useful_retention_new_error_assessment='Incomplete. Immutable output retains all four note texts but duplicates three; source-specific additional prose and recommendations remain unadjudicated. No usable revisable report exists.',new_independent_correction_credit=0))
    # Original-source evidence, kept OUT of model prompts and production logic.
    excerpts=[]
    for start,end in [(source.index('scRNA-seq data of total immune cells'),source.index('The shared transcript count matrices'))]:
        excerpts.append(dict(start=start,end=end,text=source[start:end]))
    for heading,next_heading in [('10X data filtering','10X data normalization'),('Smart-seq2 data filtering','Smart-seq2 data normalization'),('10X and Smart-seq2 integrated data','Technical Validation')]:
        start=source.index(heading);end=source.index(next_heading,start);excerpts.append(dict(start=start,end=end,text=source[start:end]))
    assert all(source[e['start']:e['end']]==e['text']for e in excerpts)
    write(a.out_dir/'source-relationship-review.json',dict(source_id=19,source_view_sha256=hashlib.sha256(source.encode()).hexdigest(),original_excerpts=excerpts,population_counts=[55825,1963,32773,96631],population_sum=187192,platform_counts=[186123,1069],platform_sum=187192,
        provisional_concern='The reader note and immutable writer allocate all population counts to10X, although the original presents population categories across10X or Smart-seq2. Separate platform filtering totals corroborate distinct measurement axes. This is coordinator evidence, not an independent complete-report correction.',
        unresolved='Exact per-population platform allocation not inferred from totals. Raw-data records and supplements have not been evaluated here. New paper-specific or proposal text in both replies has not passed complete original-source review.',new_independent_correction_credit=0))
    tests=subprocess.run([sys.executable,'-m','pytest','-q','local_deep_research/tests/test_revisable_section_document.py','local_deep_research/tests/test_section_document.py','local_deep_research/tests/test_source_span_answers.py'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (a.out_dir/'dependency-test-output.txt').write_text(tests.stdout);assert tests.returncode==0
    write(a.out_dir/'audit.json',dict(execution_status='terminal_exit2_preserved',cause='Second fresh reply has invalid JSON; both model calls finish stop.',provenance_checks_passed=True,candidate_semantic_fix_demonstrated=False,strict_replay=dict(fresh_model_calls=0,expected_exit=2,exact_results_and_raw_replies=True),actual_model_usage=usage,production_deployment=False,complete_report_evaluated=False,new_independent_correction_credit=0,broader_previous_acquisition_test_failures='Five failures recorded in scope-acquisition-reader-terminal-audit-20261115-v1 remain unresolved; this focused test run does not override them.'))
    files=[* [f for f in a.run.rglob('*')if f.is_file()],* [f for f in a.out_dir.rglob('*')if f.is_file()],Path(__file__)]
    manifest={str(f):sha(f)for f in files};write(a.out_dir/'MANIFEST.json',manifest)
    assert all(sha(Path(k))==h for k,h in manifest.items())
    print(json.dumps(dict(payloads_verified=len(manifest),manifest_sha256=sha(a.out_dir/'MANIFEST.json'),execution_exit=2,model_calls=2,candidate_fix_demonstrated=False)))


if __name__=='__main__':main()
