"""Offline exact protocol/application replay of a complete request-addition run."""
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from research_verify.request_additions import (request_plan_prompt,parse_request_plan,gap_prompt,
    parse_gaps,confirmation_prompt,apply_confirmed_additions)
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.evidence_flow import supplement,required_sources
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    plan=json.loads((a.attempt/'plan.json').read_text());complete=json.loads((a.attempt/'completion.json').read_text())
    assert complete['status']=='completed'and complete['frozen_inputs_unchanged']
    root=Path.cwd();manifest=None
    freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists()else root/rel)==digest
        if path.name=='case-manifest.json':manifest=root/rel
    assert manifest and sha(manifest)==plan['manifest_sha256']
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+name,freeze.get(name))==digest for name,digest in launch.items())
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']]))[0]
    assert state['Id']==handle['container_id']and state['Image']==handle['image_id']
    assert not state['State']['Running']and state['State']['ExitCode']==0
    assert state['HostConfig']['ExtraHosts']==['host.docker.internal:127.0.0.1']
    targets={'web_search_engines/engine_registry.py','security/module_whitelist.py','web_search_engines/engines/search_engine_europepmc.py'}
    assert all(any(m['Destination']=='/install/.venv/lib/python3.14/site-packages/local_deep_research/'+target and not m['RW']for m in state['Mounts'])for target in targets)
    case=_manifest_cases(manifest)[0];assert sha(case['source'])==plan['source_pack_sha256']and sha(case['draft'])==plan['original_report_sha256']
    original=case['draft'].read_text();assert original==(a.attempt/'original-report.txt').read_text()
    sources=json.loads(case['source'].read_text());working=copy.deepcopy(sources);registered={int(s['index'])for s in sources};required=required_sources(original,sources)
    calls=json.loads((a.attempt/'calls.json').read_text());cursor=0
    def invoke(prompt,stage):
        nonlocal cursor
        event=calls[cursor];path=a.attempt/f'call-{cursor:02d}-prompt.txt';assert prompt==path.read_text()and sha(path)==event['prompt_sha256']and event['stage']==stage
        cursor+=1;reply=a.attempt/f"call-{event['index']:02d}-response.txt";assert event['status']=='returned'and sha(reply)==event['response_sha256'];return reply.read_text()
    transport=complete['transport'];articles=complete['articles'];transport_cursor=0;article_cursor=0
    def get(url,**kwargs):
        nonlocal transport_cursor
        event=transport[transport_cursor];transport_cursor+=1
        assert event['url']==url and event.get('params')==kwargs.get('params')
        if event['status']!='retrieved':raise RuntimeError('Recorded unavailable transport')
        path=a.attempt/event['file'];assert sha(path)==event['sha256']and path.stat().st_size==event['bytes'];raw=path.read_bytes()
        return SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[raw],close=lambda:None)
    class Replay(EvidenceFetcher):
        def article(self,source):
            nonlocal article_cursor
            event=articles[article_cursor];article_cursor+=1;assert source==event['source_before']
            text=super().article(source)
            if event['status']=='acquired':
                path=a.attempt/event['file'];assert sha(path)==event['sha256']and text==path.read_text()
            else:assert not text
            return text
    fetch=Replay({'citation.original_reference_document_followup':True},get=get,requests=100,seconds=10000)
    trace=SimpleNamespace(record=lambda *args,**kw:None)
    requirements=parse_request_plan(invoke(request_plan_prompt(case['query']),'request_plan'),case['query']);assert requirements==complete['requirements']
    for round_no in range(2):
        material=format_source_documents(native_documents(working),case['query'],max_chars=plan['source_budget_chars'],required_ids=required&registered)
        gap=parse_gaps(invoke(gap_prompt(case['query'],original,material,requirements),'request_gap_review'),original,material,requirements)
        if round_no or not gap['needs_articles']:break
        needed=[i for i in gap['needs_articles']if i in registered]
        acquired=supplement([dict(status='insufficient_evidence',source_id=i,request={'kind':'article'})for i in needed],working,fetch,register=None,trace=trace)
        if not acquired:break
    assert gap==complete['final_gap']
    answer=original;insertions=[];decisions=[]
    if gap['eligible']:
        prompt=confirmation_prompt(case['query'],original,material,requirements,gap['eligible'])
        answer,insertions,decisions=apply_confirmed_additions(invoke(prompt,'request_addition_confirmation'),original,gap['eligible'])
    assert answer==(a.attempt/'candidate-report.txt').read_text()and sha(a.attempt/'candidate-report.txt')==complete['report_sha256']
    assert insertions==complete['insertions']and decisions==complete['decisions']
    assert cursor==len(calls)==complete['calls']and transport_cursor==len(transport)and article_cursor==len(articles)
    assert working==json.loads((a.attempt/'source-records.json').read_text())
    assert all(before=={k:v for k,v in after.items()if k!='fetched_content'}for before,after in zip(sources,working,strict=True))
    audit=dict(scope='Exact request/addition protocol and full-report application replay; not independent assessment',
        exit_code=0,launch_start_end_hashes_verified=True,complete_protocol_replay=True,calls=len(calls),
        raw_transports_replayed=transport_cursor,article_requests_replayed=article_cursor,
        requirements=len(requirements),eligible_proposals=len(gap['eligible']),unresolved_proposals=len(gap['unresolved']),
        insertions=len(insertions),source_metadata_unchanged=True,original_report_sha256=complete['original_report_sha256'],
        candidate_report_sha256=complete['report_sha256'],quality_claim=None,newly_credited_corrections=0,
        limits=['Model requirement/coverage/confirmation outputs are fallible','No fresh writer or complete native checker replay','Report scope and all original allegations remain independently unassessed'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes());print(json.dumps(audit))


if __name__=='__main__':main()
