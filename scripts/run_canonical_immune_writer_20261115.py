"""Matched original immune Writer with existing source-blind canonical fields.

No new scientific schema or production caller. Entire original native Writer
prefix, sources, old draft and clock are preserved. Added fallible source-unit
notes are interpretations, not forced report text or semantic approval.
"""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.canonical_fields import source_units,unit_field_prompt,parse_unit_fields
from research_verify.field_comparison import observations_from_notes
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')


def prepare():
    root=Path('evaluation/frontier-strategy-20261113')
    paths=dict(case=root/'immune-questioned-fact-inputs-20261115-v1/case-manifest.json',
        views=root/'immune-questioned-fact-model-20261115-v1/attempt/source-views.json',
        material=root/'immune-questioned-fact-model-20261115-v1/attempt/source-material.txt',
        prefix=root/'section-writer-model-20261115-v1/attempt/native-writer-prefix.txt')
    case=read(paths['case'])['cases'][0]
    for k in ['source','draft']:
        paths[k]=Path(case[k]);assert sha(paths[k])==case[k+'_sha256']
    assert hashlib.sha256(case['query'].encode()).hexdigest()==case['query_sha256']
    prefix=paths['prefix'].read_text();material=paths['material'].read_text()
    assert material in prefix and case['query']in prefix and paths['draft'].read_text()in prefix
    ids={int(k)for k in read(paths['views'])};assert len(ids)==20
    units=source_units(material,ids)
    # Request decomposition only: the four cell names are copied from the user
    # question. No feedback-proposed marker, quantity, platform or gold enters.
    requirements=[dict(requirement_id=i,request_quote=name,
        description=name+'：提取文献报告的分选、富集及后续单细胞实验方案和平台；保留原文适用对象与条件。')
        for i,name in enumerate(['嗜酸性粒细胞','嗜碱性粒细胞','肥大细胞','T细胞'])]
    assert all(r['request_quote']in case['query']for r in requirements)
    batches=[];batch=[]
    for sid in sorted(ids):
        selected=[u for u in units if u['source_id']==sid]
        if batch and len(unit_field_prompt(case['query'],requirements,batch+selected))>140000:
            batches.append(batch);batch=[]
        batch.extend(selected)
        assert len(unit_field_prompt(case['query'],requirements,batch))<=140000
    if batch:batches.append(batch)
    assert len(batches)<=5
    return paths,case,requirements,units,batches,prefix


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--replay-attempt',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay_attempt);a.out_dir.mkdir(exist_ok=False)
    paths,case,requirements,units,batches,prefix=prepare()
    files=[*paths.values(),Path(__file__).resolve(),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    frozen={str(f):sha(f)for f in files};write(a.out_dir/'prestart-freeze.json',frozen)
    for f in files:
        rel=f.resolve().relative_to(Path.cwd().resolve())
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    write(a.out_dir/'requirements.json',requirements);write(a.out_dir/'source-units.json',units)
    settings={'llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,'llm.max_retries':0}
    write(a.out_dir/'plan.json',dict(scope='One matched original immune task, full original20-source Writer packet/draft/query/clock retained as exact native prefix. Existing canonical-field source-blind reader adds fallible scope-specific notes. No expected answer, old draft or native judgement in reader prompts. No forced fact text or claim-specific correction. Original prefix contains its original draft and native reading; this is NOT an ablation removing old-draft exposure. Extra reader compute and appendix declared, not cost parity.',query_sha256=case['query_sha256'],source_pack_sha256=sha(paths['source']),original_report_sha256=sha(paths['draft']),native_writer_prefix_sha256=sha(paths['prefix']),source_records=20,source_units=len(units),reader_batches=len(batches),maximum_fresh_calls=len(batches)+1,reader_prompt_budget=140000,writer_prompt_budget=360000,settings=settings,native_consistency_setting_unchanged=True,native_complete_report_checks_in_this_stage=False,save_time_citation_qc=False,publication=False,new_independent_correction_credit=0))
    calls=[];notes=[];model=None;failure=None
    def invoke(prompt,stage):
        nonlocal model
        budget=360000 if stage=='writer' else 140000
        assert len(prompt)<=budget and len(calls)<len(batches)+1
        i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=i,stage=stage,status='started',prompt_chars=len(prompt),prompt_sha256=sha(pp));calls.append(row);write(a.out_dir/'calls.json',calls)
        if a.replay_attempt:
            old=read(a.replay_attempt/'calls.json')[i];rp=a.replay_attempt/f'call-{i:02d}-response.txt'
            assert old['stage']==stage and (a.replay_attempt/f'call-{i:02d}-prompt.txt').read_text()==prompt
            assert old['prompt_sha256']==sha(pp)and old['response_sha256']==sha(rp)
            raw=rp.read_text();metadata=old['response_metadata'];row['origin']='saved_response_replay'
        elif a.execute:
            row['origin']='fresh_model';write(a.out_dir/'calls.json',calls)
            if model is None:
                from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                from local_deep_research.config.thread_settings import settings_context
                from local_deep_research.config.llm_config import get_llm
                defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180}
                with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
            response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
        else:
            row['origin']='preflight_placeholder';metadata={}
            raw='Preflight only; not a candidate report.'if stage=='writer'else json.dumps(dict(sources=[dict(source_id=sid,fields=[],unresolved_requirements=list(range(4)))for sid in sorted({u['source_id']for u in batches[i]})]))
        rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);write(a.out_dir/'calls.json',calls)
        if a.execute and metadata.get('finish_reason')!='stop':raise ValueError('Model did not finish normally; no retry')
        return raw
    try:
        for i,batch in enumerate(batches):
            parsed=parse_unit_fields(invoke(unit_field_prompt(case['query'],requirements,batch),'report_blind_canonical_fields'),requirements,batch)
            assert not parsed['rejected_fields']
            notes.append(dict(batch=i,**parsed));write(a.out_dir/f'field-notes-{i:02d}.json',notes[-1])
        observations=observations_from_notes(notes);write(a.out_dir/'observations.json',observations)
        prompt=prefix+'\nADDITIONAL FALLIBLE SOURCE-ONLY FIELD NOTES:\n'+json.dumps(observations,ensure_ascii=False)+(
            '\nThese are fallible interpretations tied to original source units, not '
            'verified findings or text to copy. Use supplied original source text '
            'to resolve study/population/method scope and qualifiers before '
            'writing. Produce ONE complete useful Chinese report answering the '
            'original request. Preserve supported specific sorting/enrichment '
            'methods and actual single-cell platforms, with study attribution. '
            'An excerpt or abstract boundary is not whole-paper absence. The '
            'old draft is navigation, never evidence. Revise inaccurate draft '
            'interpretations from original material, without replacing useful '
            'requested details with generic uncertainty. Distinguish published '
            'experiments from proposals. Do not repeat a paper merely to append '
            'notes. Ordinary Markdown with actual numeric source citations; '
            'no JSON, audit table, implementation labels or outside knowledge. '
            'Do not invent a bibliography or sources.\n')
        raw=invoke(prompt,'writer');assert raw.strip();(a.out_dir/'candidate-report.md').write_text(raw)
    except Exception as exc:
        failure=error_receipt(exc);write(a.out_dir/'failure.json',failure)
    done=dict(status='unavailable'if failure else('preflight_only'if not a.execute and not a.replay_attempt else'completed_writer_stage'),failure=failure,logical_calls=len(calls),fresh_model_calls=sum(c.get('origin')=='fresh_model'for c in calls),reader_batches_completed=len(notes),frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in frozen.items()),full_native_pipeline_complete=False,independent_assessment_complete=False,new_independent_correction_credit=0)
    if a.replay_attempt and not failure:
        assert (a.out_dir/'candidate-report.md').read_bytes()==(a.replay_attempt/'candidate-report.md').read_bytes();done['exact_report_replay']=True
    write(a.out_dir/'completion.json',done);print(json.dumps(done))
    if failure or not done['frozen_inputs_unchanged']:raise SystemExit(2)


if __name__=='__main__':main()
