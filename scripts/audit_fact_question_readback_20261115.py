"""Terminal and exact existing-planner/QA replay; report-wording answers are NOT primary evidence."""
import json,subprocess,collections,argparse
from dataclasses import replace,asdict
from pathlib import Path
from scripts.run_fact_question_readback_20261115 import prepare,passage,answer_receipts,navigation_regions,read,write,sha,R
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.independent_verification import QuestionPlanningResult,VerificationQuestion,plan_verification_questions,parse_verification_response
from research_verify.retention_inventory import report_readback_prompt

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--navigation',action='store_true');args=parser.parse_args()
    version='v2'if args.navigation else'v1';expected=5 if args.navigation else 7
    root=R/f'fact-question-readback-model-20261115-{version}';attempt=root/'attempt';launch=read(root/'launch.json')
    runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
    assert runtime['State']['Status']=='exited'and runtime['State']['ExitCode']==0 and runtime['Image']==launch['image_id']
    assert runtime['Config']['Healthcheck']['Test']==['NONE']and runtime['HostConfig']['NetworkMode']=='host'
    binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
    assert next(m for m in binds if m['RW'])['Source']==str(root.resolve())
    for item in read(root/'readonly-mount-freeze.json'):
        m,=[m for m in binds if m['Destination']==item['destination']];assert not m['RW']and m['Source']==item['source']
        if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    for name,h in read(attempt/'prestart-freeze.json').items():
        path=Path(name)
        if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
        assert sha(path)==h
        try:rel=path.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    complete=read(attempt/'completion.json');assert complete['status']=='completed_report_readback_diagnostic'and complete['frozen_inputs_unchanged']
    calls=read(attempt/'calls.json');assert len(calls)==expected and complete['fresh_calls']==expected
    usage=collections.Counter()
    for i,row in enumerate(calls):
        assert row['index']==i and row['status']=='returned'and row['origin']=='fresh_model'and row['response_metadata']['finish_reason']=='stop'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==row['prompt_sha256']and sha(attempt/f'call-{i:02d}-response.txt')==row['response_sha256']
        usage.update({k:v for k,v in row['response_metadata']['token_usage'].items()if type(v)is int})
    cases,claims,groups,_=prepare();plans=[];cursor=0;results=[];stats=[]
    def invoke(prompt,stage,case_index,artifact_id=None):
        nonlocal cursor
        row=calls[cursor];assert row['stage']==stage and row['case_index']==case_index and row['artifact_id']==artifact_id
        assert prompt==(attempt/f'call-{cursor:02d}-prompt.txt').read_text()
        raw=(attempt/f'call-{cursor:02d}-response.txt').read_text();cursor+=1;return raw
    for i,group in enumerate(claims):
        if args.navigation:
            row=read(R/'fact-question-readback-model-20261115-v1/attempt/question-plans.json')[i]
            plans.append(QuestionPlanningResult(**{**row,'questions':tuple(VerificationQuestion(**q)for q in row['questions'])}));continue
        def planner(prompt):
            assert prompt==(R/'fact-question-readback-preflight-20261115-v1/attempt'/f'planner-{i:02d}-prompt.txt').read_text()
            return invoke(prompt,'existing_neutral_question_planner',i)
        plans.append(plan_verification_questions(planner,group))
    # JSON roundtrip normalizes tuple/list representation only.
    assert json.loads(json.dumps([asdict(p)for p in plans]))==read(attempt/'question-plans.json')
    region_map=navigation_regions(cases,groups)if args.navigation else None
    for i,group in enumerate(groups):
        for sid,text,origin in group:
            questions=tuple(replace(q,source_ids=(sid,))for q in plans[i].questions);ps=[passage(sid,text)]
            nav=None
            if region_map:
                links={link['question_id']:link['claim_id']for link in plans[i].links}
                nav={q.question_id:[dict(artifact_id=sid,**region_map[sid][links[q.question_id].split(':')[0]])]for q in questions}
            prompt=report_readback_prompt(questions,ps,navigation=nav);assert text in prompt
            if nav:
                assert prompt==(attempt/f'readback-{sid}-prompt.txt').read_text()
                assert prompt==(R/f'fact-question-readback-preflight-20261115-{version}/attempt'/f'readback-{sid}-prompt.txt').read_text()
            assert (attempt/f'report-{sid}.txt').read_text()==text
            answers=parse_verification_response(invoke(prompt,'complete_report_text_readback',i,sid),questions,ps)
            receipts=answer_receipts(answers)
            results.append(dict(case_index=i,artifact_id=sid,questions=[asdict(q)for q in questions],answers=receipts,
                semantic_evidence_kind='report_wording_only',scientific_support_assessed=False))
            stats.append(dict(case_index=i,artifact_id=sid,report_chars=len(text),questions=len(questions),
                statuses=dict(collections.Counter(a.status for a in answers)),
                evidence_statuses=dict(collections.Counter(a.evidence_status for a in answers)),
                parse_warnings=[dict(question_id=a.question_id,warnings=a.parse_warnings)for a in answers if a.parse_warnings]))
    assert cursor==expected and json.loads(json.dumps(results))==complete['results']
    out=R/f'fact-question-readback-terminal-audit-20261115-{version}';out.mkdir(exist_ok=False)
    write(out/'strict-replay-plans.json',[asdict(p)for p in plans]);write(out/'strict-replay-results.json',results)
    write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=expected,strict_replay_fresh_calls=0,usage=dict(usage),statistics=stats,
        questions_per_case=[len(p.questions)for p in plans],uncovered_claims=[p.uncovered_claim_ids for p in plans],
        report_artifact_namespace=[sid for g in groups for sid,text,origin in g],all_five_complete_reports_supplied=True,
        report_changes=0,scientific_support_assessed=False,independent_correction_credit=0))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=expected,usage=dict(usage),statistics=stats,manifests={str(p):seal(p)for p in [R/f'fact-question-readback-preflight-20261115-{version}',root,out]}),ensure_ascii=False))

if __name__=='__main__':main()
