"""Two known-task full-report token-index repair diagnostic; no independent correction score."""
import argparse,json
from pathlib import Path
from scripts.run_related_report_revision_20261115 import inputs,R,TOKENIZER,read,write,sha
from scripts.experiment_error_receipt import error_receipt
from research_verify.token_span_edits import token_edit_prompt,parse_token_edits
from research_verify.field_comparison import edit_confirmation_prompt,apply_confirmed_edits
from research_verify.dimension_comparison import preview_confirmation_prompt
from research_verify.request_fields import original_anchors

def prepare_cases():
    cases,groups,_,_,_,paths=inputs()
    cases[1]=dict(cases[1],report=groups[1][1][1],anchors=original_anchors(groups[1][1][1]))
    return cases,paths

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out-dir',type=Path,required=True);ap.add_argument('--execute',action='store_true');ap.add_argument('--preflight',type=Path);ap.add_argument('--replay',type=Path);a=ap.parse_args()
    assert not(a.execute and a.replay);cases,paths=prepare_cases()
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tok=Tokenizer.from_file(str(TOKENIZER));tokens=lambda p:len(tok.encode(p,add_special_tokens=False).ids)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),*Path('local_deep_research/research_verify').glob('*.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
        *[Path('scripts')/n for n in ['run_related_report_revision_20261115.py','run_fact_question_readback_20261115.py','run_fact_retention_inventory_20261115.py',
        'run_dimension_report_boundary_20261115.py','run_associated_field_report_pair_20261115.py','prepare_source_detail_material_20261114.py','run_native_original_report_pair_20261114.py','experiment_error_receipt.py']]]
    if a.execute:
        assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
        assert all(sha(Path(n))==h for n,h in read(a.preflight/'prestart-freeze.json').items())
        paths.extend(a.preflight/n for n in ['prestart-freeze.json','completion.json','plan.json'])
    if a.replay:paths.extend(p for p in a.replay.rglob('*')if p.is_file()and 'code'not in p.parts)
    freeze={str(p):sha(p)for p in [*paths,*code]};write(a.out_dir/'prestart-freeze.json',freeze)
    for p in code:
        q=a.out_dir/'code'/p.resolve().relative_to(Path.cwd());q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,'llm.max_retries':0,'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=4,settings=settings,
        cases=['Verbatim archived IFquestion/original full58404char report/source5complete material','Verbatim original immunequestion/actual historical adverse native7451char report/source9complete material'],
        limits=['Known controls, not unused generalization','Not a full20paper or6task evaluation','Subspan preserves outside bytes only; source support/whole-report retention/new errors not independently adjudicated','No forced approval/deployment/production modification'],independent_correction_credit=0))
    prompts=[]
    for i,c in enumerate(cases):
        (a.out_dir/f'original-report-{i}.txt').write_text(c['report']);(a.out_dir/f'original-question-{i}.txt').write_text(c['question']);write(a.out_dir/f'complete-source-units-{i}.json',c['units'])
        values=[c[k]for k in ['question','report','material','requirements','anchors','observations']]
        prompt=token_edit_prompt(*values,[],c['source_ids']);assert int(tokens(prompt)*1.1)+12000+8192<=131072
        (a.out_dir/f'proposal-prompt-{i}.txt').write_text(prompt);prompts.append(prompt)
    calls=[];results=[];failure=None;model=None
    def invoke(prompt,stage,case_index):
        nonlocal model
        assert len(calls)<4 and int(tokens(prompt)*1.1)+12000+8192<=131072
        n=len(calls);pp=a.out_dir/f'call-{n:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=n,stage=stage,case_index=case_index,prompt_sha256=sha(pp),estimated_tokens=tokens(prompt),status='started');calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay:
                prev=read(a.replay/'calls.json')[n];assert all(prev[k]==row[k]for k in ['stage','case_index','prompt_sha256'])and prev['status']=='returned'
                rp=a.replay/f'call-{n:02d}-response.txt';assert sha(rp)==prev['response_sha256'];raw=rp.read_text();meta=prev['response_metadata'];row['origin']='strict_replay'
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
            for i,c in enumerate(cases):
                if a.preflight:assert prompts[i]==(a.preflight/f'proposal-prompt-{i}.txt').read_text()
                values=[c[k]for k in ['question','report','material','requirements','anchors','observations']]
                edits=parse_token_edits(invoke(prompts[i],'source_grounded_token_index_proposals',i),c['report'],c['material'],c['requirements'],c['anchors'],c['source_ids'],c['observations'])
                answer=c['report'];changes=[];decisions=[]
                if edits['eligible']:
                    prompt=preview_confirmation_prompt(edit_confirmation_prompt(*values,[],edits['eligible']),c['report'],edits['eligible'])
                    answer,changes,decisions=apply_confirmed_edits(invoke(prompt,'separate_full_report_preview_confirmation',i),c['report'],edits['eligible'])
                (a.out_dir/f'candidate-report-{i}.txt').write_text(answer)
                result=dict(case_index=i,proposals=edits,changes=changes,decisions=decisions,report_chars=len(answer),sha256=sha(a.out_dir/f'candidate-report-{i}.txt'),independent_correction_credit=0)
                results.append(result);write(a.out_dir/'results.json',results)
        except Exception as exc:failure=error_receipt(exc)
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('completed_token_index_repair_diagnostic'if a.execute or a.replay else'preflight_only'),failure=failure,
        logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),results=results,frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,calls=len(calls),applied=[len(r['changes'])for r in results],independent_correction_credit=0)))
    if failure:raise SystemExit(2)
if __name__=='__main__':main()
