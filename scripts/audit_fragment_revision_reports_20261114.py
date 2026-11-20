"""Exact complete-report fragment revision replay; not independent scientific scoring."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from research_verify.fragment_revision import revision_anchors,revision_prompt,parse_proposals,apply_proposals,confirmation_prompt,confirmation_decisions
from research_verify.canonical_fields import source_units
from research_verify.generation import format_source_documents,writer_source_query
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class RecordedInvocationFailure(Exception):pass


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    cases=_manifest_cases(a.case_manifest);complete=json.loads((a.attempt/'completion.json').read_text());plan=json.loads((a.attempt/'plan.json').read_text());calls=json.loads((a.attempt/'calls.json').read_text());handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());cursor=0;summary=[]
    container=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
    assert container['State']['Status']=='exited'and container['State']['ExitCode']==0 and container['Image']==handle['image']
    assert next(m for m in container['Mounts']if m['Destination']=='/workspace')['RW']is False
    for fn in [a.attempt/'prestart-freeze.json',a.attempt.parent/'launch-code-freeze.json']:
        for path,digest in json.loads(fn.read_text()).items():
            actual=Path(path)
            if actual.is_relative_to('/workspace'):actual=Path.cwd()/actual.relative_to('/workspace')
            assert sha(actual)==digest
    def invoke(prompt,stage):
        nonlocal cursor
        i=cursor;cursor+=1;c=calls[i];pp=a.attempt/f'call-{i:02d}-prompt.txt'
        assert stage==c['stage']and pp.read_text()==prompt and sha(pp)==c['prompt_sha256']and len(prompt)==c['prompt_chars']and len(prompt)<=400000
        if c['status']=='unavailable':raise RecordedInvocationFailure(c['error_type'])
        rp=a.attempt/f'call-{i:02d}-response.txt';assert c['status']=='returned'and sha(rp)==c['response_sha256']
        if c.get('origin')=='strict_cache':
            old=Path(c['cached_from']);assert sha(old)==c['response_sha256']and old.with_name(old.name.replace('-response.txt','-prompt.txt')).read_text()==prompt
        return rp.read_text()
    for case,record in zip(cases,complete['results']):
        report=case['draft'].read_text();sources=json.loads(case['source'].read_text());ids={int(s['index'])for s in sources};mode=plan.get('material_query_mode','question');selection_receipts=[]
        material_query=writer_source_query(case['query'],report,claim_directed=mode!='question')
        material=format_source_documents(native_documents(sources),material_query,max_chars=plan['source_budget_chars'],required_ids=ids,protected_query=case['query']if mode=='protected'else None,selection_receipts=selection_receipts);units=source_units(material,ids);anchors=revision_anchors(report);folder=a.attempt/case['case_id']
        if (folder/'selection-receipts.json').exists():assert json.loads((folder/'selection-receipts.json').read_text())==selection_receipts
        assert case['case_id']==record['case_id']and (folder/'original-report.txt').read_text()==report and (folder/'source-material.txt').read_text()==str(material)
        assert json.loads((folder/'source-units.json').read_text())==units and json.loads((folder/'anchors.json').read_text())==anchors
        answer=report;parsed=None;confirmation=None;changes=[];failure=None
        try:
            parsed=parse_proposals(invoke(revision_prompt(case['query'],report,material,anchors,units,index_preview_chars=case.get('index_preview_chars',plan.get('index_preview_chars',100))),case['case_id']+':propose'),report,anchors,units)
            proposed=apply_proposals(report,parsed['proposals']);assert proposed==(folder/'proposal-report.txt').read_text()
            if parsed['proposals']:
                confirmation=confirmation_decisions(invoke(confirmation_prompt(case['query'],proposed,material,anchors,units,parsed['proposals'],index_preview_chars=case.get('index_preview_chars',plan.get('index_preview_chars',100))),case['case_id']+':confirm'),parsed['proposals'])
                if confirmation['batch_approved']:answer=proposed;changes=parsed['proposals']
        except (ValueError,KeyError,TypeError,RecordedInvocationFailure)as exc:
            failure=type(exc).__name__
            assert record['status']=='unavailable'
            if isinstance(exc,RecordedInvocationFailure):assert str(exc)==record['failure']['error_type']
            else:assert type(exc).__name__==record['failure']['error_type']
        assert (failure is None)==(record['status']=='completed')and parsed==record['parsed']and confirmation==record['confirmation']and changes==record['changes']
        assert answer==(folder/'candidate-report.txt').read_text()and sha(folder/'candidate-report.txt')==record['report_sha256']and sha(case['draft'])==record['original_report_sha256']
        # Verify byte identity outside all actual applied intervals by reverse construction.
        old_cursor=new_cursor=0;restored=[]
        for change in sorted(changes,key=lambda c:c['start']):
            outside=report[old_cursor:change['start']];assert answer[new_cursor:new_cursor+len(outside)]==outside;restored.append(outside);new_cursor+=len(outside)
            assert answer[new_cursor:new_cursor+len(change['replacement'])]==change['replacement'];new_cursor+=len(change['replacement']);restored.append(change['original_text']);old_cursor=change['end']
        assert answer[new_cursor:]==report[old_cursor:];restored.append(answer[new_cursor:]);assert ''.join(restored)==report
        summary.append(dict(case_id=case['case_id'],status=record['status'],failure_replayed=failure,sources=len(ids),anchors=len(anchors),located_proposals=len(parsed['proposals'])if parsed else 0,unlocated_proposals=len(parsed['unlocated_proposals'])if parsed else None,applied_changes=len(changes),outside_applied_spans_byte_identical=True,candidate_report_sha256=record['report_sha256']))
    assert cursor==len(calls)==complete['calls']<=4 and complete['frozen_inputs_unchanged']
    audit=dict(scope='Exact native source/prompt/parser/confirmation/application replay; not independent scientific adjudication',exit_code=0,launch_start_end_hashes_match=True,calls=cursor,fresh_calls=sum(c.get('origin','fresh')=='fresh'for c in calls),cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),cases=summary,quality_claim=None,newly_credited_corrections=0)
    a.out_dir.mkdir(exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':main()
