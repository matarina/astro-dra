"""Offline exact replay of per-field comparison/model-confirmed editing evidence."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from research_verify.field_comparison import compare_and_edit

from research_verify.request_fields import (atomic_request_prompt,original_anchors,
    source_field_prompt,parse_source_fields)
from research_verify.canonical_fields import (source_units,unit_field_prompt,parse_unit_fields,
    unit_gap_prompt,parse_unit_gaps)
from research_verify.request_additions import (parse_request_plan,gap_prompt,parse_gaps,
    confirmation_prompt,apply_confirmed_additions)
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    plan=json.loads((a.attempt/'plan.json').read_text());complete=json.loads((a.attempt/'completion.json').read_text())
    assert complete['status']in {'completed','unavailable'}and complete['frozen_inputs_unchanged']and complete['source_records_unchanged']
    root=Path.cwd();manifest=None;freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists()else root/rel)==digest
        assert sha(root/rel)==digest
        if path.name=='case-manifest.json':manifest=root/rel
    assert manifest and sha(manifest)==plan['manifest_sha256']
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']]))[0]
    assert state['Id']==handle['container_id']and state['Image']==handle['image_id']
    assert not state['State']['Running']and state['State']['ExitCode']==0
    assert state['HostConfig']['ExtraHosts']==['host.docker.internal:127.0.0.1']
    assert any(m['Destination']=='/workspace'and not m['RW']for m in state['Mounts'])
    for target in ['web_search_engines/engine_registry.py','security/module_whitelist.py','web_search_engines/engines/search_engine_europepmc.py']:
        assert any(m['Destination']=='/install/.venv/lib/python3.14/site-packages/local_deep_research/'+target and not m['RW']for m in state['Mounts'])
    case=_manifest_cases(manifest)[0];sources=json.loads(case['source'].read_text());report=case['draft'].read_text()
    assert sha(case['source'])==plan['source_pack_sha256']and sha(case['draft'])==plan['original_report_sha256']
    assert report==(a.attempt/'original-report.txt').read_text()
    anchors=original_anchors(report);assert anchors==json.loads((a.attempt/'anchors.json').read_text())
    assert len(anchors)==plan['anchor_count']
    calls=json.loads((a.attempt/'calls.json').read_text());cursor=0
    def invoke(prompt,stage):
        nonlocal cursor
        event=calls[cursor];path=a.attempt/f'call-{cursor:02d}-prompt.txt'
        assert prompt==path.read_text()and sha(path)==event['prompt_sha256']and stage==event['stage']
        assert len(prompt)==event['prompt_chars']and len(prompt)<=plan['maximum_prompt_chars']
        if event.get('origin')=='strict_cache':
            cached=Path(event['cached_from']);assert sha(cached)==event['response_sha256']
            assert cursor<2 and prompt==cached.with_name(f'call-{cursor:02d}-prompt.txt').read_text()
        else:assert event.get('origin')=='fresh'
        reply=a.attempt/f'call-{cursor:02d}-response.txt';cursor+=1
        assert event['status']=='returned'and sha(reply)==event['response_sha256'];return reply.read_text()
    requirements=parse_request_plan(invoke(atomic_request_prompt(case['query']),'atomic_request_plan'),case['query'])
    assert requirements==complete['requirements']
    notes=[];seen=[];reading_ids=plan.get('report_blind_reading_ids',[int(s['index'])for s in sources])
    reading_sources=[s for s in sources if int(s['index'])in reading_ids]
    maximum_fields=plan.get('maximum_fields_per_source',3)
    canonical=plan.get('canonical_source_units',False)
    for batch_no,start in enumerate(range(0,len(reading_sources),24)):
        batch=reading_sources[start:start+24];ids={int(s['index'])for s in batch};seen.extend(sorted(ids))
        shown=format_source_documents(native_documents(batch),case['query'],max_chars=plan['source_budget_chars'],required_ids=ids)
        if canonical:
            fields=parse_unit_fields(invoke(unit_field_prompt(case['query'],requirements,source_units(shown,ids)),
                'report_blind_canonical_fields'),requirements,source_units(shown,ids))
        else:
            fields=parse_source_fields(invoke(source_field_prompt(case['query'],requirements,shown,maximum_fields=maximum_fields),
                'report_blind_source_fields'),requirements,shown,maximum_fields=maximum_fields)
        notes.append(dict(batch=batch_no,**fields))
    assert sorted(seen)==sorted(reading_ids)and len(seen)==len(set(seen))
    assert notes==complete['field_notes']
    material=format_source_documents(native_documents(sources),case['query'],max_chars=plan['source_budget_chars'],required_ids={int(s['index'])for s in sources})
    units=source_units(material,reading_ids);assert units==json.loads((a.attempt/'source-units.json').read_text())
    answer=report;result=None;failure_replayed=None
    try:
        answer,result=compare_and_edit(case['query'],report,material,requirements,anchors,notes,set(reading_ids),invoke,
            SimpleNamespace(record=lambda *args,**kwargs:None))
    except json.JSONDecodeError as exc:
        assert complete['status']=='unavailable'and complete['failure']['error_type']==type(exc).__name__
        failure_replayed=type(exc).__name__
    assert (failure_replayed is None)==(complete['status']=='completed')
    assert result==complete['field_result']
    assert cursor==len(calls)==complete['calls']and cursor<=plan['maximum_model_calls']
    assert answer==(a.attempt/'candidate-report.txt').read_text()and sha(a.attempt/'candidate-report.txt')==complete['report_sha256']
    changes=result['changes']if result else[]
    old_cursor=new_cursor=0;restored=[]
    for change in sorted(changes,key=lambda c:c['start']):
        outside=report[old_cursor:change['start']]
        assert answer[new_cursor:new_cursor+len(outside)]==outside
        restored.append(outside);new_cursor+=len(outside)
        assert answer[new_cursor:new_cursor+len(change['replacement'])]==change['replacement']
        assert report[change['start']:change['end']]==change['original_text']
        restored.append(change['original_text']);new_cursor+=len(change['replacement']);old_cursor=change['end']
    assert answer[new_cursor:]==report[old_cursor:];restored.append(answer[new_cursor:]);assert ''.join(restored)==report
    fresh=sum(c.get('origin')=='fresh'for c in calls);cached=sum(c.get('origin')=='strict_cache'for c in calls)
    assert fresh==complete['fresh_calls']and cached==complete['cached_calls']
    audit=dict(scope='Exact source/field-comparison/proposal/confirmation/application replay; not independent scientific assessment',
        exit_code=0,workflow_status=complete['status'],failure_replayed=failure_replayed,
        launch_start_end_hashes_verified=True,complete_protocol_replay=True,calls=len(calls),fresh_calls=fresh,strict_cached_calls=cached,
        registered_sources=len(sources),source_blind_reading_ids=reading_ids,source_units=len(units),
        observations=len(result['observations'])if result else None,
        comparisons=result['comparisons']if result else None,
        eligible_proposals=len(result['edit_proposals']['eligible'])if result else None,
        changes=len(changes),original_preserved_outside_changed_spans=True,source_records_unchanged=True,
        original_report_sha256=complete['original_report_sha256'],candidate_report_sha256=complete['report_sha256'],
        quality_claim=None,newly_credited_corrections=0,
        limits=['Model source/comparison/edit/confirmation judgments remain fallible',
                'No new acquisition inside this runner; input pack contains separately acquired source5fulltext',
                'No full writer/native checker rerun or matched-cost superiority proof',
                'Correct content INSIDE replacements and full-report new errors/usefulness require independent adjudication'])
    a.out_dir.mkdir(parents=True,exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes());print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
