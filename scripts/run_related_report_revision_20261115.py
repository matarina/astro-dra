"""Bounded field-only questions, all citation-linked readback, then source5 model edits/confirmation; no independent score."""
import argparse,json
from dataclasses import asdict,replace
from pathlib import Path
from scripts.run_fact_question_readback_20261115 import prepare,passage,answer_receipts,navigation_regions,read,write,sha,R,TOKENIZER
from research_verify.independent_verification import VerificationQuestion,parse_verification_response
from research_verify.retention_inventory import (report_readback_prompt,citation_related_regions,field_question_prompt,
    parse_field_questions,project_report_regions)
from research_verify.field_comparison import edit_prompt,parse_edits,edit_confirmation_prompt,apply_confirmed_edits
from research_verify.dimension_comparison import preview_confirmation_prompt
from research_verify.request_fields import original_anchors
from scripts.experiment_error_receipt import error_receipt

def inputs():
    cases,claims,groups,paths=prepare();prior=R/'fact-question-readback-model-20261115-v1/attempt/question-plans.json'
    plans=read(prior);old=[tuple(VerificationQuestion(**q)for q in p['questions'])for p in plans]
    regions=navigation_regions(cases,groups);paths.append(prior)
    links=[{l['question_id']:l['claim_id']for l in p['links']}for p in plans]
    return cases,groups,old,regions,links,paths

def readback(c,text,sid,questions,regions,links):
    qs=tuple(replace(q,source_ids=(sid,))for q in questions)
    nav={q.question_id:[dict(artifact_id=sid,**regions[links[q.question_id].split(':')[0]])]for q in qs}
    related=citation_related_regions(text,sid,c['source_ids'])
    return qs,report_readback_prompt(qs,[passage(sid,text)],navigation=nav,related_regions=related)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--replay',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay);cases,groups,old,regions,links,paths=inputs()
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tok=Tokenizer.from_file(str(TOKENIZER));tokens=lambda s:len(tok.encode(s,add_special_tokens=False).ids)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),*[Path('scripts')/n for n in ['run_fact_question_readback_20261115.py','run_fact_retention_inventory_20261115.py',
        'run_dimension_report_boundary_20261115.py','run_associated_field_report_pair_20261115.py','prepare_source_detail_material_20261114.py',
        'run_native_original_report_pair_20261114.py','experiment_error_receipt.py']],Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    if a.execute:
        assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
        assert all(sha(Path(n))==h for n,h in read(a.preflight/'prestart-freeze.json').items())
        paths.extend(a.preflight/n for n in ['prestart-freeze.json','plan.json','completion.json'])
    if a.replay:paths.extend(p for p in a.replay.rglob('*')if p.is_file()and 'code'not in p.parts)
    freeze={str(p):sha(p)for p in [*paths,*code]};write(a.out_dir/'prestart-freeze.json',freeze)
    for path in code:
        dest=a.out_dir/'code'/path.resolve().relative_to(Path.cwd());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,'llm.max_retries':0,
        'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=9,settings=settings,
        protocol='One field-only wording call(no old question/assertion/source/report values); five full-report readbacks with primary target and all same-citation regions. Then source5complete acquired material/full original IF report request a maximum3source-supported minimal edits, separate confirmation with complete hypothetical report, and final readback if edits applied. No primary truth inferred from report-only QA. Original questions/source namespaces unchanged. Related citations are syntactic, not semantic scope proof. Known two tasks/single target-source IF revision, not20paper/full6task evaluation. No Writer/search/native/production deployment.',
        prior_uncovered_IF_claim_ids=['t23:0','t23:4'],all_question_neutrality_verified=False,independent_correction_credit=0))
    for group in groups:
        for sid,text,origin in group:(a.out_dir/f'input-report-{sid}.txt').write_text(text)
    all_old=tuple(q for group in old for q in group);wording_prompt=field_question_prompt(all_old)
    (a.out_dir/'wording-prompt.txt').write_text(wording_prompt)
    estimates=[]
    for i,group in enumerate(groups):
        for sid,text,origin in group:
            qs,prompt=readback(cases[i],text,sid,old[i],regions[sid],links[i]);n=tokens(prompt)
            assert int(n*1.1)+12000+8192<=131072
            estimates.append(dict(artifact_id=sid,prompt_tokens=n,report_chars=len(text),related_regions=len(citation_related_regions(text,sid,cases[i]['source_ids']))))
    write(a.out_dir/'preflight-estimates.json',estimates)
    calls=[];results=[];new_questions=[];model=None;failure=None;revision=None
    def invoke(prompt,stage,case_index=None,artifact_id=None):
        nonlocal model
        assert len(calls)<9 and int(tokens(prompt)*1.1)+12000+8192<=131072
        n=len(calls);pp=a.out_dir/f'call-{n:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=n,stage=stage,case_index=case_index,artifact_id=artifact_id,prompt_sha256=sha(pp),estimated_tokens=tokens(prompt),prompt_chars=len(prompt),status='started')
        calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay:
                prior=read(a.replay/'calls.json')[n];assert all(prior[k]==row[k]for k in ['stage','case_index','artifact_id','prompt_sha256'])and prior['status']=='returned'
                rp=a.replay/f'call-{n:02d}-response.txt';assert sha(rp)==prior['response_sha256'];raw=rp.read_text();meta=prior['response_metadata'];row['origin']='strict_replay'
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
            if a.preflight:assert wording_prompt==(a.preflight/'wording-prompt.txt').read_text()
            new_questions=parse_field_questions(invoke(wording_prompt,'field_only_question_wording'),all_old)
            write(a.out_dir/'field-only-questions.json',[asdict(q)for q in new_questions]);byid={q.question_id:q for q in new_questions}
            case_qs=[tuple(byid[q.question_id]for q in group)for group in old]
            for i,group in enumerate(groups):
                for sid,text,origin in group:
                    qs,prompt=readback(cases[i],text,sid,case_qs[i],regions[sid],links[i])
                    parsed=parse_verification_response(invoke(prompt,'related_complete_report_readback',i,sid),qs,[passage(sid,text)])
                    results.append(dict(case_index=i,artifact_id=sid,questions=[asdict(q)for q in qs],answers=answer_receipts(parsed)))
            c=cases[0];values=[c[k]for k in ['question','report','material','requirements','anchors','observations']]
            aids=[r['anchor_id']for r in c['anchors']if set(r['citation_ids'])&c['source_ids']]
            scope=('\nRELATED ORIGINAL REPORT ANCHOR IDS (same citation, not identical scientific scope):\n'+json.dumps(aids)
                +'\nRecheck ALL same-study/method occurrences. Repair source-supported requested information while retaining correct content/identifiers/table context. '
                'Do not leave the same error elsewhere by fixing only one occurrence. Unknown abstract scope is not a whole-paper contradiction. '
                'No unnecessary expansion beyond the original user request. Report-only answers below are fallible navigation, NEVER primary evidence.\n')
            raw=invoke(scope+json.dumps(results[0]['answers'],ensure_ascii=False)+'\n'+edit_prompt(*values,[]),'source_grounded_minimal_edits',0,100001)
            edits=parse_edits(raw,c['report'],c['material'],c['requirements'],c['anchors'],c['source_ids'],c['observations'])
            answer=c['report'];changes=[];decisions=[]
            if edits['eligible']:
                prompt=scope+preview_confirmation_prompt(edit_confirmation_prompt(*values,[],edits['eligible']),c['report'],edits['eligible'])
                answer,changes,decisions=apply_confirmed_edits(invoke(prompt,'source_grounded_preview_confirmation',0,100001),c['report'],edits['eligible'])
            (a.out_dir/'candidate-report.txt').write_text(answer)
            revision=dict(proposals=edits,changes=changes,decisions=decisions,report_chars=len(answer),report_sha256=sha(a.out_dir/'candidate-report.txt'),independent_correction_credit=0)
            write(a.out_dir/'revision.json',revision)
            if changes:
                approved=[p for j,p in enumerate(edits['eligible'])if any(ch['candidate_index']==j for ch in changes)]
                after,newregions=project_report_regions(c['report'],regions[100001],approved);assert after==answer
                qs,prompt=readback(c,answer,100006,case_qs[0],newregions,links[0])
                parsed=parse_verification_response(invoke(prompt,'final_candidate_related_readback',0,100006),qs,[passage(100006,answer)])
                results.append(dict(case_index=0,artifact_id=100006,questions=[asdict(q)for q in qs],answers=answer_receipts(parsed)))
        except Exception as exc:failure=error_receipt(exc)
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('preflight_only'if not(a.execute or a.replay)else'completed_related_report_revision_diagnostic'),
        failure=failure,logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),results=results,revision=revision,
        frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),scientific_outcome_independently_assessed=False,independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,logical_calls=len(calls),model_confirmed_edits=len(revision['changes'])if revision else None,independent_correction_credit=0)))
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
