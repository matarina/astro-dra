"""Six-call maximum: matched comparisons on two known tasks, then isolated IF edit+preview-confirmation. No quality score."""
import argparse,json,hashlib
from pathlib import Path
from research_verify.dimension_comparison import dimension_comparison_prompt,parse_dimension_comparisons,preview_confirmation_prompt
from research_verify.field_comparison import (observations_from_notes,comparison_prompt,parse_comparisons,
    edit_prompt,parse_edits,edit_confirmation_prompt,apply_confirmed_edits)
from research_verify.generation import SourceMaterial
from research_verify.canonical_fields import source_units
from research_verify.request_fields import original_anchors
from scripts.run_associated_field_report_pair_20261115 import prepare as if_inputs,read,sha,write,R,TOKENIZER
from scripts.experiment_error_receipt import error_receipt

def prepare():
    case,report,material,requirements,anchors,jobs,inputs=if_inputs()
    obs=observations_from_notes(jobs[1]['notes'],requirements)
    cases=[dict(case_id='original_IF_source5',question=case['query'],report=report,material=material,
        requirements=requirements,anchors=anchors,observations=obs,source_ids={5})]
    base=R/'canonical-immune-writer-model-20261115-v1/attempt'
    cp=R/'immune-questioned-fact-inputs-20261115-v1/case-manifest.json'
    immune,=read(cp)['cases'];vp=R/'immune-questioned-fact-model-20261115-v1/attempt/source-views.json'
    view=read(vp)['9'];mat=view['block']
    units=source_units(mat,{9});assert units==[u for u in read(base/'source-units.json')if u['source_id']==9]
    notes=[];notepaths=sorted(base.glob('field-notes-*.json'))
    for path in notepaths:
        row=read(path);selected=[s for s in row['sources']if s['source_id']==9]
        if selected:notes.append(dict(sources=selected))
    reqs=read(base/'requirements.json');observations=observations_from_notes(notes,reqs)
    registry={(u['unit_id'],u['text_sha256']):u for u in units}
    assert observations and all(registry[o['unit_id'],o['unit_sha256']]['text']==o['quote']for o in observations)
    rp=R/'source-view-native-model-20261115-v1/attempt/actual_view_scope/original-report.md'
    original=rp.read_text();assert len(original)==7435
    cases.append(dict(case_id='original_immune_source9_known_writer',question=immune['query'],report=original,
        material=mat,requirements=reqs,anchors=original_anchors(original),observations=observations,source_ids={9}))
    inputs.extend([cp,vp,rp,*notepaths,base/'requirements.json',base/'source-units.json'])
    for c in cases:assert hashlib.sha256(c['question'].encode()).hexdigest()in {case['query_sha256'],immune['query_sha256']}
    return cases,inputs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--replay',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay)
    cases,inputs=prepare()
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tokenizer=Tokenizer.from_file(str(TOKENIZER));tokens=lambda s:len(tokenizer.encode(s,add_special_tokens=False).ids)
    prepared=[]
    for case in cases:
        values=[case[k]for k in ['question','report','material','requirements','anchors','observations']]
        for arm,fn in [('existing_comparison',comparison_prompt),('dimension_comparison',dimension_comparison_prompt)]:
            prompt=fn(*values);assert int(tokens(prompt)*1.1)+12000+8192<=131072
            prepared.append(dict(case_id=case['case_id'],arm=arm,prompt=prompt,estimated_tokens=tokens(prompt)))
    # Baseline IF input is byte-exact last turn's plural-reading comparison.
    old=R/'associated-field-report-model-20261115-v1/attempt/call-03-prompt.txt'
    assert prepared[0]['prompt']==old.read_text();inputs.append(old)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),Path('scripts/run_associated_field_report_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),
          Path('scripts/experiment_error_receipt.py'),Path('scripts/run_native_original_report_pair_20261114.py'),
          Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    if a.execute:
        assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
        assert all(sha(Path(n))==h for n,h in read(a.preflight/'prestart-freeze.json').items())
        inputs.extend(a.preflight/n for n in ['prestart-freeze.json','plan.json','completion.json'])
    if a.replay:inputs.extend(p for p in a.replay.rglob('*')if p.is_file()and 'code'not in p.parts)
    freeze={str(p):sha(p)for p in [*inputs,*code]};write(a.out_dir/'prestart-freeze.json',freeze)
    for path in code:
        dest=a.out_dir/'code'/path.resolve().relative_to(Path.cwd());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,'llm.max_retries':0,
        'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=6,settings=settings,
        protocol='Fresh baseline/candidate comparisons on identical within-task source observations/question/full report/material. IF=source5complete acquired text and complete original archive report; immune=source9complete45k acquired view and complete prior known7435char Writer report under original question, NOT original feedback report. Historical known cases, not heldout/generalization proof. Candidate adds per-dimension/whole-report literal occurrence judgments. Only IF candidate continues minimal proposal and confirmation with hypothetical whole-report preview; no baseline edit rerun. Thus report outcomes are not an isolated component comparison. No live retrieval/native/Writer/production.',
        jobs=[{k:v for k,v in j.items()if k!='prompt'}for j in prepared],
        independent_correction_credit=0,tokenizer_endpoint_match='unverified;10percent estimate+12000output+8192reserve'))
    for i,j in enumerate(prepared):(a.out_dir/f'prepared-{i:02d}-prompt.txt').write_text(j['prompt'])
    for i,c in enumerate(cases):
        folder=a.out_dir/f'case-{i:02d}';folder.mkdir();(folder/'original-report.txt').write_text(c['report'])
        write(folder/'input.json',dict(question=c['question'],requirements=c['requirements'],anchors=c['anchors'],observations=c['observations'],material=str(c['material']),views=getattr(c['material'],'views',None)))
    calls=[];results=[];model=None;failure=None
    def invoke(prompt,case_id,stage):
        nonlocal model
        assert len(calls)<6 and int(tokens(prompt)*1.1)+12000+8192<=131072
        n=len(calls);pp=a.out_dir/f'call-{n:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=n,case_id=case_id,stage=stage,prompt_sha256=sha(pp),estimated_tokens=tokens(prompt),prompt_chars=len(prompt),status='started')
        calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay:
                old=read(a.replay/'calls.json')[n];assert old['status']=='returned'and old['stage']==stage and old['case_id']==case_id and old['prompt_sha256']==row['prompt_sha256']
                rp=a.replay/f'call-{n:02d}-response.txt';assert sha(rp)==old['response_sha256'];raw=rp.read_text();meta=old['response_metadata'];row['origin']='strict_replay'
            else:
                if model is None:
                    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                    from local_deep_research.config.thread_settings import settings_context
                    from local_deep_research.config.llm_config import get_llm
                    defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                    effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings
                    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
                row['origin']='fresh_model';response=model.invoke(prompt);raw=str(response.content);meta=response.response_metadata
            rp=a.out_dir/f'call-{n:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=meta)
            assert meta.get('finish_reason')=='stop';return raw
        except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
        finally:write(a.out_dir/'calls.json',calls)
    if a.execute or a.replay:
        try:
            for i,job in enumerate(prepared):
                if a.preflight:assert job['prompt']==(a.preflight/f'prepared-{i:02d}-prompt.txt').read_text()
                c=cases[i//2];raw=invoke(job['prompt'],job['case_id'],job['arm'])
                if job['arm']=='existing_comparison':parsed=parse_comparisons(raw,c['question'],c['anchors'],c['observations'])
                else:parsed=parse_dimension_comparisons(raw,c['question'],c['material'],c['anchors'],c['observations'])
                results.append(dict(case_id=job['case_id'],arm=job['arm'],comparisons=parsed))
            c=cases[0];values=[c[k]for k in ['question','report','material','requirements','anchors','observations']];comparisons=results[1]['comparisons']
            raw=invoke(edit_prompt(*values,comparisons),c['case_id'],'dimension_edit_proposals')
            edits=parse_edits(raw,c['report'],c['material'],c['requirements'],c['anchors'],c['source_ids'],c['observations'])
            answer=c['report'];changes=[];decisions=[];preview=None
            if edits['eligible']:
                prompt=preview_confirmation_prompt(edit_confirmation_prompt(*values,comparisons,edits['eligible']),c['report'],edits['eligible'])
                raw=invoke(prompt,c['case_id'],'dimension_preview_confirmation')
                answer,changes,decisions=apply_confirmed_edits(raw,c['report'],edits['eligible'])
            (a.out_dir/'case-00/candidate-report.txt').write_text(answer)
            write(a.out_dir/'case-00/edit-result.json',dict(proposals=edits,decisions=decisions,changes=changes,report_sha256=sha(a.out_dir/'case-00/candidate-report.txt'),
                final_report_independently_assessed=False,final_subset_rechecked=False,independent_correction_credit=0))
        except Exception as exc:failure=error_receipt(exc)
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('preflight_only'if not(a.execute or a.replay)else'completed_dimension_diagnostic'),
        failure=failure,logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),results=results,
        frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,logical_calls=len(calls),comparisons=len(results),independent_correction_credit=0)))
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
