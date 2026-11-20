"""Reuse existing neutral planning/QA on five complete REPORT artifacts; no primary-source verdict or report repair."""
import argparse,hashlib,json
from dataclasses import asdict,replace
from pathlib import Path
from scripts.run_fact_retention_inventory_20261115 import prepare as retention_cases,R,read,write,sha,TOKENIZER
from research_verify.independent_verification import (ClaimPlanningInput,VerificationQuestion,SourcePassage,
    QuestionPlanningResult,plan_verification_questions,parse_verification_response)
from research_verify.retention_inventory import report_readback_prompt,project_report_regions
from research_verify.dimension_comparison import hypothetical_report
from scripts.experiment_error_receipt import error_receipt

def prepare():
    cases,_,inputs=retention_cases();prior=R/'fact-retention-inventory-model-20261115-v1/attempt/completion.json'
    inv=read(prior)['inventories'];editpath=R/'dimension-report-boundary-model-20261115-v2/attempt/case-00/edit-result.json'
    oldpath=R/'associated-field-report-model-20261115-v1/attempt/arm-00/result.json'
    nativepath=R/'source-view-native-model-20261115-v1/attempt/actual_view_scope/native-report.md'
    edits=read(editpath)['proposals']['eligible'];short,=[p for p in read(oldpath)['edit_proposals']['eligible']if p['anchor_id']==206]
    native=nativepath.read_text();assert len(native)==7451
    originals=[100001,100004];artifactgroups=[
        [(100001,cases[0]['report'],'original'),(100002,hypothetical_report(cases[0]['report'],edits),'actual_model_proposals_hypothetical'),
         (100003,hypothetical_report(cases[0]['report'],[short]),'historical_shorter_proposal_hypothetical')],
        [(100004,cases[1]['report'],'original_known_writer'),(100005,native,'actual_historical_native_revision')]]
    claims=[]
    for i,c in enumerate(cases):
        bytext={r['text_id']:r for r in inv[i]};rows=[]
        for tid in dict.fromkeys(p['original']for p in c['pairs']):
            for fact in bytext[tid]['facts']:
                rows.append(ClaimPlanningInput(claim_id=f'{tid}:{fact["fact_id"]}',text=fact['statement'],
                    source_ids=(originals[i],),kind='report_assertion_not_primary_evidence',
                    context='ORIGINAL USER QUESTION: '+c['question']+'\nActual report span context: '+c['texts'][tid]))
        assert 0<len(rows)<=12;claims.append(rows)
    inputs.extend([prior,editpath,oldpath,nativepath])
    return cases,claims,artifactgroups,inputs

def passage(sid,text):
    return SourcePassage(source_id=sid,title='Report text artifact',text=text,field='report_text',
        basis='report_text_only_not_primary_evidence',identity={'artifact_sha256':hashlib.sha256(text.encode()).hexdigest()},
        scope_note='Only what this complete report states; no primary article or scientific truth established')


def navigation_regions(cases,groups):
    result={};base=[]
    for c in cases:
        regions={}
        for tid in dict.fromkeys(p['original']for p in c['pairs']):
            text=c['texts'][tid];assert c['report'].count(text)==1
            start=c['report'].index(text);regions[tid]=dict(start=start,end=start+len(text))
        base.append(regions)
    edits=read(R/'dimension-report-boundary-model-20261115-v2/attempt/case-00/edit-result.json')['proposals']['eligible']
    old,=[p for p in read(R/'associated-field-report-model-20261115-v1/attempt/arm-00/result.json')['edit_proposals']['eligible']if p['anchor_id']==206]
    result[100001]=base[0]
    for sid,proposals in [(100002,edits),(100003,[old])]:
        report,regions=project_report_regions(cases[0]['report'],base[0],proposals)
        assert report==next(text for g in groups for aid,text,origin in g if aid==sid);result[sid]=regions
    issue,=read(R/'source-view-native-model-20261115-v1/attempt/actual_view_scope/result.json')['native_applied']
    result[100004]=base[1];start=base[1]['t41']['start']
    p=dict(action='replace',anchor_start=start,anchor_end=start+len(issue['statement']),anchor=issue['statement'],addition=issue['replacement'])
    report,result[100005]=project_report_regions(cases[1]['report'],base[1],[p]);assert report==groups[1][1][1]
    return result

def answer_receipts(answers):
    return [{**asdict(a),'evidence_status':a.evidence_status,'effective_status':a.effective_status,
        'evidence_kind':'report_text_only_not_primary_evidence','independent_assessment':'UNASSESSED'}for a in answers]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--replay',type=Path)
    p.add_argument('--navigation-plan-from',type=Path,help='Reuse frozen prior neutral questions and add actual report-region navigation; five fresh readbacks only')
    a=p.parse_args();assert not(a.execute and a.replay);cases,claims,groups,inputs=prepare()
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tok=Tokenizer.from_file(str(TOKENIZER));tokens=lambda s:len(tok.encode(s,add_special_tokens=False).ids)
    region_map=navigation_regions(cases,groups)if a.navigation_plan_from else None
    if a.navigation_plan_from:inputs.extend(a.navigation_plan_from/n for n in ['question-plans.json','calls.json','completion.json'])
    estimates=[]
    for group in groups:
        for sid,text,origin in group:
            prompt=report_readback_prompt([VerificationQuestion('preflight','What information does this report explicitly state?',(sid,))],[passage(sid,text)])
            n=tokens(prompt);assert int(n*1.1)+12000+12000+8192<=131072
            estimates.append(dict(artifact_id=sid,chars=len(text),minimum_estimated_tokens=n))
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),Path('scripts/run_fact_retention_inventory_20261115.py'),Path('scripts/run_dimension_report_boundary_20261115.py'),
          Path('scripts/run_associated_field_report_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),
          Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),
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
    maximum=5 if a.navigation_plan_from else 7
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=maximum,settings=settings,artifact_estimates=estimates,
        navigation_question_plan_from=str(a.navigation_plan_from)if a.navigation_plan_from else None,
        neutral_planner_fresh_calls=0 if a.navigation_plan_from else 2,
        navigation_limit='Actual current report ranges projected through declared edits; no new paper facts or expected answers. Previously generated questions still vague/count-leaking and uncovered questions stay uncovered. Variation and added navigation confound a causal improvement claim.'if region_map else None,
        protocol='Two existing plan_verification_questions calls over all original11IF/3immune fallible inventory items. Same generated neutral questions routed unchanged to five full report artifact IDs in separate fresh contexts. Reuse existing build_verification_prompt and parse_verification_response via explicit report-only adapter. All statuses mean report answer presence, NEVER primary support. No primary source text or old answer/verdict in readback input. No scientific correction/approval/new-error clearance. Question neutrality/coverage unverified; known used tasks; not heldout or majority/generalization proof.',
        scientific_source_namespace=False,new_report_generation=False,production_deployment=False,independent_correction_credit=0))
    write(a.out_dir/'planning-claims.json',[[asdict(c)for c in group]for group in claims])
    for group in groups:
        for sid,text,origin in group:
            (a.out_dir/f'report-{sid}.txt').write_text(text)
    write(a.out_dir/'coordinator-artifact-map.json',[dict(case_index=i,artifact_id=sid,origin=origin,report_sha256=sha(a.out_dir/f'report-{sid}.txt'))for i,group in enumerate(groups)for sid,text,origin in group])
    calls=[];plans=[];results=[];model=None;failure=None
    def invoke(prompt,stage,case_index,artifact_id=None):
        nonlocal model
        assert len(calls)<maximum and int(tokens(prompt)*1.1)+12000+8192<=131072
        n=len(calls);pp=a.out_dir/f'call-{n:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=n,stage=stage,case_index=case_index,artifact_id=artifact_id,prompt_sha256=sha(pp),prompt_chars=len(prompt),estimated_tokens=tokens(prompt),status='started')
        calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay:
                old=read(a.replay/'calls.json')[n];assert all(old[k]==row[k]for k in ['stage','case_index','artifact_id','prompt_sha256'])and old['status']=='returned'
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
    try:
        for i,group in enumerate(claims):
            if a.navigation_plan_from:
                row=read(a.navigation_plan_from/'question-plans.json')[i]
                plans.append(QuestionPlanningResult(**{**row,'questions':tuple(VerificationQuestion(**q)for q in row['questions'])}))
                continue
            if not(a.execute or a.replay):
                def preflight(prompt):
                    (a.out_dir/f'planner-{i:02d}-prompt.txt').write_text(prompt)
                    return json.dumps(dict(plans=[dict(claim_id=c.claim_id,questions=[])for c in group]))
                result=plan_verification_questions(preflight,group)
            else:
                def planner(prompt):
                    if a.preflight:assert prompt==(a.preflight/f'planner-{i:02d}-prompt.txt').read_text()
                    return invoke(prompt,'existing_neutral_question_planner',i)
                result=plan_verification_questions(planner,group)
            plans.append(result)
        write(a.out_dir/'question-plans.json',[asdict(p)for p in plans])
        if a.execute or a.replay or a.navigation_plan_from:
            for i,group in enumerate(groups):
                plan=plans[i];assert plan.questions,'No usable neutral questions; stop, do not substitute handwritten questions'
                original_id=group[0][0];assert all(q.source_ids==(original_id,)for q in plan.questions)
                for sid,text,origin in group:
                    questions=tuple(replace(q,source_ids=(sid,))for q in plan.questions);ps=[passage(sid,text)]
                    nav=None
                    if region_map:
                        links={link['question_id']:link['claim_id']for link in plan.links}
                        nav={q.question_id:[dict(artifact_id=sid,**region_map[sid][links[q.question_id].split(':')[0]])]for q in questions}
                    prompt=report_readback_prompt(questions,ps,navigation=nav)
                    if region_map:
                        assert int(tokens(prompt)*1.1)+12000+8192<=131072
                        (a.out_dir/f'readback-{sid}-prompt.txt').write_text(prompt)
                        if a.preflight:assert prompt==(a.preflight/f'readback-{sid}-prompt.txt').read_text()
                    if not(a.execute or a.replay):continue
                    parsed=parse_verification_response(invoke(prompt,'complete_report_text_readback',i,sid),questions,ps)
                    results.append(dict(case_index=i,artifact_id=sid,questions=[asdict(q)for q in questions],answers=answer_receipts(parsed),
                        semantic_evidence_kind='report_wording_only',scientific_support_assessed=False))
    except Exception as exc:failure=error_receipt(exc)
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('preflight_only'if not(a.execute or a.replay)else'completed_report_readback_diagnostic'),
        failure=failure,logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),results=results,
        frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),report_changes=0,independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,logical_calls=len(calls),reports_read_back=len(results),independent_correction_credit=0)))
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
