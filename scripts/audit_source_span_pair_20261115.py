"""Audit actual quote transport, including retained parse failure; no quality score."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from scripts.isolated_network import assert_network_matches
from research_verify.source_span_answers import span_registry


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    inspect=lambda c:json.loads(subprocess.check_output(['docker','inspect',c]))[0]
    launch=json.loads((a.run/'launch.json').read_text());info=inspect(launch['container_id']);ref=inspect(launch['network_reference_container'])
    assert info['State']['Status']=='exited'and info['State']['ExitCode']==0 and info['Image']==launch['image_id'];assert_network_matches(ref,info)
    assert info['Config']['Healthcheck']['Test']==['NONE']and info['Config']['Entrypoint']==['/install/.venv/bin/python']
    assert next(m for m in info['Mounts']if m['Destination']=='/workspace')['RW']is False
    overlays=lambda x:sorted((m['Source'],m['Destination'],m['RW'])for m in x['Mounts']if m['Destination'].startswith('/install/'))
    assert overlays(info)==overlays(ref) and len(overlays(info))==3 and all(not row[2]for row in overlays(info))
    attempt=a.run/'attempt';freeze=json.loads((a.run/'launch-freeze.json').read_text());inner=json.loads((attempt/'prestart-freeze.json').read_text())
    assert all(sha(Path(k))==v for k,v in freeze.items())and all(sha(Path(k))==v for k,v in inner.items())
    for path,digest in inner.items():
        if path.startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/path)==digest
    calls=json.loads((attempt/'calls.json').read_text());assert len(calls)==6 and[c['index']for c in calls]==list(range(6))
    assert all(c['status']=='returned'for c in calls)
    for c in calls:
        assert sha(attempt/f"call-{c['index']:02d}-prompt.txt")==c['prompt_sha256']and sha(attempt/f"call-{c['index']:02d}-response.txt")==c['response_sha256']
    completion=json.loads((attempt/'completion.json').read_text());prior=Path(completion['prior_prefix']);prior_run=prior.parent
    old_launch=json.loads((prior_run/'launch.json').read_text());old=inspect(old_launch['container_id']);assert old['State']['Status']=='exited'and old['State']['ExitCode']==2
    old_calls=json.loads((prior/'calls.json').read_text());assert len(old_calls)==1 and calls[0]['origin']=='strict_prefix_cache'
    assert old_calls[0]['prompt_sha256']==calls[0]['prompt_sha256'] and old_calls[0]['response_sha256']==calls[0]['response_sha256']
    assert (prior/'call-00-response.txt').read_bytes()==(attempt/'call-00-response.txt').read_bytes()
    old_freeze=json.loads((prior/'prestart-freeze.json').read_text())
    for path,digest in old_freeze.items():
        file=prior/'code'/path if path.startswith(('scripts/','local_deep_research/'))else Path(path)
        assert sha(file)==digest
    cases=json.loads(a.inputs.read_text())['cases'];total_spans=0
    for i,case in enumerate(cases):
        pp=[(attempt/f'call-{2*i+j:02d}-prompt.txt').read_text()for j in [0,1]]
        assert pp[0].split('QUOTE TRANSPORT:',1)[0]==pp[1].split('QUOTE TRANSPORT:',1)[0]
        assert pp[0].split('ORIGINAL REQUEST:\n',1)[1]==pp[1].split('ORIGINAL REQUEST:\n',1)[1]
        assert sha(Path(case['views_path']))==case['views_sha256']
        views=json.loads(Path(case['views_path']).read_text());records,spans=span_registry(views);total_spans+=len(spans)
        assert records==json.loads((attempt/case['case_id']/'supplied-passages.json').read_text())
        for view,record in zip(views,records):
            assert ''.join(s['text']for s in record['passages'])==view['text']
            assert all(view['text'][s['start']:s['end']]==s['text']for s in record['passages'])
    subprocess.run([sys.executable,'scripts/run_source_span_pair_20261115.py','--inputs',str(a.inputs),'--out-dir',str(a.out_dir/'replay'),'--replay-attempt',str(attempt)],check=True)
    replay=json.loads((a.out_dir/'replay/completion.json').read_text());assert replay['replay_exact'] and replay['fresh_model_calls']==0 and replay['parse_or_call_failures']==1
    fresh_usage=[c['response_metadata']['token_usage']for c in calls]
    audit=dict(terminal_exit=0,initial_prefix_terminal_exit=2,initial_json_failure_preserved=True,network_matches_reference=True,repo_read_only=True,standard_read_only_overlays=3,healthcheck_disabled=True,launch_frozen_files=len(freeze),prestart_frozen_files=len(inner),frozen_hashes_unchanged=True,actual_calls=6,new_calls_this_attempt=5,strict_prefix_cached_calls=1,overall_fresh_calls_including_initial_attempt=6,all_finish_reasons=[c['response_metadata'].get('finish_reason')for c in calls],common_instructions_and_source_data_identical_within_pairs=True,source_views=8,known_original_tasks=2,exact_source_spans=total_spans,source_characters_and_selected_coordinates_preserved=True,complete_saved_response_replay_exact=True,audit_model_calls=0,audit_retrieval_calls=0,token_usage={k:sum(u.get(k,0)for u in fresh_usage)for k in ['prompt_tokens','completion_tokens','total_tokens']},complete_report_evaluated=False,scientific_accuracy_assessed=False,new_independent_correction_credit=0)
    write(a.out_dir/'audit.json',audit);print(json.dumps(audit))


if __name__=='__main__':main()
