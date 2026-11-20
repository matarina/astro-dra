"""Replay cached native, fresh attribute followup and raw primary-to-view chain."""
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.run_native_original_report_pair_20261114 import FixedSources
from research_verify.evidence_flow import review_answer
from research_verify.sequential_review import sequential_english_review


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd();manifest=None
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace') if path.is_relative_to('/workspace') else (path.relative_to(root) if path.is_absolute() else path)
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists() else root/rel)==digest
        if path.name=='case-manifest.json':manifest=root/rel
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text());assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    assert manifest and sha(manifest)==plan['manifest_sha256'];case=_manifest_cases(manifest)[0]
    assert sha(case['draft'])==plan['original_report_sha256'] and sha(case['source'])==plan['source_pack_sha256']
    original=(a.attempt/'original-report.txt').read_text();assert original==case['draft'].read_text()
    sources=json.loads(case['source'].read_text());working=copy.deepcopy(sources)
    baseline=(a.attempt/'baseline/report.txt').read_text();start=(a.attempt/'candidate/start-report.txt').read_text();assert baseline==start
    assert sha(a.attempt/'baseline/report.txt')==c['baseline']['report_sha256']==c['candidate']['start_report_sha256']==c['shared_native_report_sha256']
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls'];replayed=[];phase='native';followup=False
    for call in calls:
        folder='baseline' if call['phase']=='native' else 'candidate'
        path=a.attempt/folder/f"call-{call['call_id']:03d}-prompt.txt";assert sha(path)==call['prompt_sha256']
        if call.get('response_sha256'):assert sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    class Handler:
        settings_snapshot={}
        def get_setting(self,k,d=None):return followup if k in {'citation.confirmation_evidence_followup','citation.confirmation_attribute_evidence_followup','citation.literal_quote_reselection'} else (True if k in {'citation.identity_attribute_review','citation.attribute_confirmation_review','citation.confirmation_consistency_review'} else d)
        def _create_documents(self,records):return native_documents(records)
        def _invoke_text(self,prompt,**kw):
            call=calls[len(replayed)];assert call['phase']==phase and call['stage']==kw.get('stage')
            folder='baseline' if phase=='native' else 'candidate';path=a.attempt/folder/f"call-{call['call_id']:03d}-prompt.txt"
            assert prompt==path.read_text();replayed.append(call)
            if call['status']!='returned':raise RuntimeError('Frozen model call unavailable')
            return path.with_name(path.name.replace('-prompt','-response')).read_text()
    handler=Handler();trace=type('Trace',(),{'record':staticmethod(lambda *args,**kw:None)})();fetcher=FixedSources();budget=dict(remaining=plan['native_call_budget'])
    b,docs,applied,pending,shown=review_answer(handler,case['query'],original,native_documents(working),working,trace,None,1,60000,dict(fetcher=fetcher),budget)
    assert b==baseline and applied==c['baseline']['native_applied'] and pending==c['baseline']['native_unresolved']
    assert budget['remaining']==c['baseline']['remaining_calls'] and len(replayed)==c['baseline']['model_calls']
    assert c['cached_native_calls']==sum(x.get('origin')=='cached_native'for x in calls)
    assert c['fresh_model_calls']==sum(x.get('origin')=='fresh'for x in calls)
    assert c['cached_sequential_calls']==sum(x.get('origin')=='cached_sequential'for x in calls)
    assert c['all_prior_calls_replayed']is True
    cache_path=Path(plan['full_cache_attempt']);cache_path=root/cache_path.relative_to('/workspace')if cache_path.is_relative_to('/workspace')else cache_path
    original_calls=json.loads((cache_path/'calls.json').read_text());used_cache=[]
    for call in calls:
        if call['origin'].startswith('cached_'):
            old=original_calls[call['cache_call_id']];assert call['phase']==old['phase']and call['stage']==old['stage']
            assert call['prompt_sha256']==old['prompt_sha256']and call['response_sha256']==old['response_sha256']
            used_cache.append(call['cache_call_id'])
    assert used_cache==[x['call_id']for x in original_calls]
    assert state['HostConfig']['ExtraHosts']==['host.docker.internal:127.0.0.1']
    expected={'web_search_engines/engine_registry.py','security/module_whitelist.py','web_search_engines/engines/search_engine_europepmc.py'}
    assert all(any(m['Destination']=='/install/.venv/lib/python3.14/site-packages/local_deep_research/'+target and not m['RW']for m in state['Mounts'])for target in expected)
    # Re-derive acquired article bytes from frozen raw core metadata/XML.
    from research_verify.pmc_identity import article_text
    records={};reparsed=set()
    for event in c['primary_transport']:
        if event.get('status')!='retrieved':continue
        path=a.attempt/f"primary-response-{event['index']:03d}.txt";raw=path.read_text()
        if event['url'].endswith('/search'):
            for record in json.loads(raw).get('resultList',{}).get('result',[]):
                if record.get('pmcid'):records[record['pmcid']]=record
        elif event['url'].endswith('/fullTextXML'):
            pmcid=event['url'].split('/')[-2];record=records[pmcid]
            parsed=article_text(raw,record,pmid=record.get('pmid')or record.get('id'))
            if parsed:reparsed.add(hashlib.sha256(parsed[:500_000].encode()).hexdigest())
    acquisitions=c['primary_acquisitions'];used=[]
    assert all(e['sha256']in reparsed for e in acquisitions if e.get('status')=='acquired')
    for event in c['primary_transport']:
        if event.get('status')=='retrieved':assert sha(a.attempt/f"primary-response-{event['index']:03d}.txt")==event['sha256']
    class ReplayFetcher:
        events=[]
        def article(self,source):
            event=acquisitions[len(used)];assert source==event['source_before'];used.append(event)
            if event['status']=='acquired':
                path=a.attempt/event['file'];assert sha(path)==event['sha256'];return path.read_text()
            if event.get('error_type'):raise RuntimeError('Recorded primary acquisition unavailable')
            return None
        def web(self,*args,**kw):return []
    phase='sequential';followup=True;extra_budget=dict(remaining=plan['extra_call_budget'])
    candidate,extra_applied,extra_pending,receipts=sequential_english_review(handler,case['query'],b,docs,working,trace,extra_budget,network_state=dict(fetcher=ReplayFetcher()))
    assert candidate==(a.attempt/'candidate/report.txt').read_text() and sha(a.attempt/'candidate/report.txt')==c['candidate']['report_sha256']
    assert extra_applied==c['candidate']['extra_applied'] and extra_pending==c['candidate']['extra_unresolved'] and receipts==c['candidate']['group_receipts']
    assert extra_budget['remaining']==c['candidate']['remaining_calls'] and len(replayed)==len(calls)
    assert (working==sources)==c['working_source_records_unchanged']
    assert len(used)==len(acquisitions) and working==json.loads((a.attempt/'final-source-records.json').read_text())
    audit=dict(cached_sequential_calls=c['cached_sequential_calls'],all_prior_calls_replayed_in_order=True,cached_native_calls=c['cached_native_calls'],fresh_model_calls=c['fresh_model_calls'],raw_primary_to_extracted_text_reparsed=True,standard_runtime_overlays_and_host_alias_verified=True,primary_requests=len(acquisitions),primary_acquired=sum(e.get('status')=='acquired'for e in acquisitions),primary_events=acquisitions,scope=plan['scope'],exit_code=0,verified_launch_startup_completion_hashes=True,calls=len(calls),
        native_calls=c['baseline']['model_calls'],additional_calls=c['candidate']['additional_model_calls'],
        native_applied=len(applied),extra_applied=len(extra_applied),native_unresolved=len(pending),extra_unresolved=len(extra_pending),
        complete_native_and_sequential_replay=True,shared_native_start_verified=True,
        source_records_unchanged=c['working_source_records_unchanged'],group_receipts=receipts,
        baseline_sha256=c['baseline']['report_sha256'],candidate_sha256=c['candidate']['report_sha256'],
        quality_claim=None,newly_credited_corrections=0,
        limits=['Additional verification has extra model calls','Translation and native supported labels are not independent gold','Prior34 responses fixed and replayed; new quote/confirmation calls not a fresh full-report replication','No independent correction/retention/new-error assessment','New metadata/abstracts do not establish complete article or original historical evidence'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),native_applied=len(applied),extra_applied=len(extra_applied),groups_checked=sum(r['status']=='checked' for r in receipts))))


if __name__=='__main__':main()
