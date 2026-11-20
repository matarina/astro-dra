"""Exact offline replay of literal report extraction and located comparisons."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from research_verify.literal_occurrences import extraction_prompt,parse_extraction,comparison_prompt,parse_comparison,parse_extraction_partial
from research_verify.citation_field_scope import citation_report_scope
from research_verify.request_fields import original_anchors
from research_verify.canonical_fields import source_units
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    plan=json.loads((a.attempt/'plan.json').read_text());complete=json.loads((a.attempt/'completion.json').read_text());data=json.loads(a.inputs.read_text());calls=json.loads((a.attempt/'calls.json').read_text());cursor=0
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());container=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
    assert container['State']['Status']=='exited'and container['State']['ExitCode']==0 and container['Image']==handle['image']
    assert next(m for m in container['Mounts']if m['Destination']=='/workspace')['RW']is False
    for fn in [a.attempt/'prestart-freeze.json',a.attempt.parent/'launch-code-freeze.json']:
        for path,digest in json.loads(fn.read_text()).items():
            actual=Path(path)
            if actual.is_relative_to('/workspace'):actual=Path.cwd()/actual.relative_to('/workspace')
            assert sha(actual)==digest
    for row in data['input_files']:assert sha(Path(row['path']))==row['sha256']
    for case in data['cases']:
        sid=case['source_units'][0]['source_id'];report=Path(case['report_path']).read_text()
        assert sha(Path(case['report_path']))==case['report_sha256']
        assert citation_report_scope(report,sid,original_anchors(report))['report_units']==case['report_units']
        # Locate the sourcepack by the input manifest, not a regenerated model quotation.
        matching=[]
        for row in data['input_files']:
            path=Path(row['path'])
            if path.name=='case-manifest.json':
                m=json.loads(path.read_text())['cases'][0]
                if m['original_task_id']==case['original_task_id']:matching.append(m)
        assert len(matching)==1
        sources=json.loads(Path(matching[0]['source']).read_text());selected=[s for s in sources if int(s['index'])==sid]
        material=format_source_documents(native_documents(selected),case['query'],max_chars=240000,required_ids={sid})
        registry=source_units(material,{sid});ids={u['unit_id']for u in case['source_units']}
        assert [u for u in registry if u['unit_id']in ids]==case['source_units']
    def invoke(prompt,stage):
        nonlocal cursor
        i=cursor;cursor+=1;call=calls[i];pp=a.attempt/f'call-{i:02d}-prompt.txt';rp=a.attempt/f'call-{i:02d}-response.txt'
        assert call['stage']==stage and prompt==pp.read_text()and sha(pp)==call['prompt_sha256']and len(prompt)==call['prompt_chars']and len(prompt)<=70000
        assert call['status']=='returned'and sha(rp)==call['response_sha256']
        if call.get('origin')=='strict_cache':
            old=Path(call['cached_from']);assert sha(old)==call['response_sha256']
            assert old.with_name(old.name.replace('-response.txt','-prompt.txt')).read_text()==prompt
            assert ':extract:'in stage
        return rp.read_text()
    results=[]
    for case in data['cases']:
        extraction=[];comparisons=[];batch=[];batches=[];size=0
        for unit in case['report_units']:
            if batch and size+len(unit['text'])>2200:batches.append(batch);batch=[];size=0
            batch.append(unit);size+=len(unit['text'])
        if batch:batches.append(batch)
        for i,b in enumerate(batches):
            raw=invoke(extraction_prompt(case['query'],b),case['case_id']+':extract:'+str(i))
            try:extraction.extend((parse_extraction_partial if plan.get('partial_literal_bindings')else parse_extraction)(raw,b))
            except(ValueError,KeyError,TypeError)as exc:
                extraction.extend(dict(report_unit_id=u['report_unit_id'],claims=[],status='unassessed',limit='Unusable extraction: '+type(exc).__name__)for u in b)
        claims=[dict(report_unit_id=x['report_unit_id'],claims=[claim])for x in extraction for claim in x['claims']]
        for i,start in enumerate(range(0,len(claims),12)):
            b=claims[start:start+12];raw=invoke(comparison_prompt(case['query'],b,case['source_units']),case['case_id']+':compare:'+str(i))
            try:comparisons.extend(parse_comparison(raw,b,case['source_units']))
            except(ValueError,KeyError,TypeError)as exc:
                comparisons.extend(dict(claim_id=x['claims'][0]['claim_id'],relation=None,status='unassessed',reason='Unusable comparison: '+type(exc).__name__,evidence=[])for x in b)
        results.append(dict(case_id=case['case_id'],extraction=extraction,comparisons=comparisons))
    assert complete['status']=='completed'and results==complete['results']and cursor==len(calls)==complete['calls']and cursor<=12 and complete['frozen_inputs_unchanged']
    audit=dict(scope='Exact parser/provenance replay, not scientific adjudication',exit_code=0,input_native_material_verified=True,launch_start_end_hashes_match=True,calls=cursor,fresh_calls=sum(c.get('origin','fresh')=='fresh'for c in calls),cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),report_modifications=0,quality_claim=None,newly_credited_corrections=0,cases=[dict(case_id=r['case_id'],extraction_units=len(r['extraction']),extracted_claims=sum(len(x['claims'])for x in r['extraction']),unassessed_extraction_units=sum(x['status']=='unassessed'for x in r['extraction']),unlocated_claims=sum(len(x.get('unlocated_claims',[]))for x in r['extraction']),whitespace_recovered=sum(c.get('binding')=='whitespace_only_original_span'for x in r['extraction']for c in x['claims']),comparisons=len(r['comparisons']),unassessed_comparisons=sum(x['status']=='unassessed'for x in r['comparisons']))for r in results])
    a.out_dir.mkdir(exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':main()
