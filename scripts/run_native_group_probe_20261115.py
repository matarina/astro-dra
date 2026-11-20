"""One exact changed native-check prompt, preserving the baseline/report.

Group selection is an explicit diagnostic coordinate, not a scientific rule.
No repairs or report generation; parse/labels do not establish correctness.
"""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.evidence_flow import parse_review
from scripts.experiment_error_receipt import error_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')


def requests(folder):
    return [row['data'] for row in map(json.loads,(folder/'trace.jsonl').read_text().splitlines()) if row.get('stage')=='native_check_request']


def claims(prompt):
    return json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['preflight-attempt','baseline-attempt','out-dir']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--group',type=int,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--replay-attempt',type=Path)
    args=parser.parse_args();assert not(args.execute and args.replay_attempt)
    args.out_dir.mkdir(exist_ok=False)
    current=[row for row in requests(args.preflight_attempt) if row['review_group']==args.group and row['round']==1]
    previous=[row for row in requests(args.baseline_attempt) if row['review_group']==args.group and row['round']==1]
    assert len(current)==len(previous)==1
    prompt=current[0]['prompt'];old_prompt=previous[0]['prompt']
    payload=claims(prompt);assert payload==claims(old_prompt) and len(prompt)<=60000
    new_call,=[row for row in read(args.preflight_attempt/'calls.json') if row['stage']=='native_check' and row['prompt_sha256']==hashlib.sha256(prompt.encode()).hexdigest()]
    old_call,=[row for row in read(args.baseline_attempt/'calls.json') if row['stage']=='native_check' and row['prompt_sha256']==hashlib.sha256(old_prompt.encode()).hexdigest()]
    assert old_call['status']=='returned'
    current_prompt=args.preflight_attempt/f"call-{new_call['index']:02d}-prompt.txt"
    baseline_prompt=args.baseline_attempt/f"call-{old_call['index']:02d}-prompt.txt"
    baseline_reply=args.baseline_attempt/f"call-{old_call['index']:02d}-response.txt"
    assert sha(current_prompt)==new_call['prompt_sha256'] and sha(baseline_prompt)==old_call['prompt_sha256'] and sha(baseline_reply)==old_call['response_sha256']
    inputs=[Path(__file__).resolve(),current_prompt,baseline_prompt,baseline_reply]
    for folder in [args.preflight_attempt,args.baseline_attempt]:
        inputs.extend(folder/name for name in ['calls.json','plan.json','completion.json','trace.jsonl','prestart-freeze.json'])
    bound=read(args.preflight_attempt/'prestart-freeze.json')
    assert all(sha(Path(path))==value for path,value in bound.items())
    inputs.extend(Path(path) for path in bound)
    if args.replay_attempt:
        inputs.extend(args.replay_attempt/name for name in ['result.json','prompt.txt','response.txt','baseline-response.txt'])
    frozen={str(path):sha(path) for path in inputs}
    write(args.out_dir/'prestart-freeze.json',frozen)
    for path in inputs:
        resolved=path.resolve()
        root=next(parent for parent in resolved.parents if parent.samefile(Path.cwd()))
        relative=resolved.relative_to(root)
        if str(relative).startswith(('scripts/','local_deep_research/')):
            target=args.out_dir/'code'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    settings=read(args.preflight_attempt/'plan.json')['settings']
    write(args.out_dir/'plan.json',dict(scope='One known-task native group diagnostic: same exact claim payload/citations/report/model settings, changed actual source selection. No expected source answer or coordinator diagnosis injected. No report repair, quality/adoption/generalization conclusion.',group=args.group,prompt_path=str(current_prompt),prompt_sha256=sha(current_prompt),baseline_prompt_path=str(baseline_prompt),baseline_response_path=str(baseline_reply),maximum_fresh_calls=1,maximum_prompt_chars=60000,settings=settings,source_acquisition=False,new_independent_correction_credit=0))
    (args.out_dir/'prompt.txt').write_text(prompt)
    (args.out_dir/'baseline-response.txt').write_bytes(baseline_reply.read_bytes())
    result=dict(status='started',prompt_sha256=sha(args.out_dir/'prompt.txt'));write(args.out_dir/'result.json',result)
    try:
        if args.replay_attempt:
            old=read(args.replay_attempt/'result.json')
            assert (args.replay_attempt/'prompt.txt').read_text()==prompt
            assert sha(args.replay_attempt/'response.txt')==old['response_sha256']
            raw=(args.replay_attempt/'response.txt').read_text();metadata=old['response_metadata'];result['origin']='strict_saved_response_replay'
        elif args.execute:
            result['origin']='fresh_model';write(args.out_dir/'result.json',result)
            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
            from local_deep_research.config.thread_settings import settings_context
            from local_deep_research.config.llm_config import get_llm
            defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
            effective=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint','llm.request_timeout':180,'llm.max_retries':0}
            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):
                model=get_llm(settings_snapshot=effective)
            response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
        else:
            raw=baseline_reply.read_text();metadata=old_call['response_metadata'];result['origin']='preflight_baseline_reply_not_candidate_observation'
        reply=args.out_dir/'response.txt';reply.write_text(raw)
        result.update(response_sha256=sha(reply),response_metadata=metadata);write(args.out_dir/'result.json',result)
        issues,checked=parse_review(raw,{row['claim_id']:row for row in payload},include_checked=True)
        result.update(status='parsed',native_issues=issues,native_checked=checked)
        if args.replay_attempt:assert (issues,checked)==(old['native_issues'],old['native_checked'])
    except Exception as error:result.update(status='unavailable',failure=error_receipt(error))
    write(args.out_dir/'result.json',result)
    done=dict(status=result['status'],fresh_model_calls=int(result.get('origin')=='fresh_model'),frozen_inputs_unchanged=all(sha(Path(path))==value for path,value in frozen.items()),report_rewrites=0,independent_assessment_complete=False,new_independent_correction_credit=0)
    write(args.out_dir/'completion.json',done);print(json.dumps(done))
    if result['status']!='parsed' or not done['frozen_inputs_unchanged']:raise SystemExit(2)


if __name__=='__main__':main()
