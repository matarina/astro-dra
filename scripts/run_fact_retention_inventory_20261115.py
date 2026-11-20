"""Six bounded inventory/retention diagnostic calls on actual IF/immune edits; no report approvals."""
import argparse,json
from pathlib import Path
from scripts.run_dimension_report_boundary_20261115 import prepare as source_cases,R,read,write,sha,TOKENIZER
from research_verify.canonical_fields import source_units
from research_verify.retention_inventory import inventory_prompt,parse_inventory,retention_prompt,parse_retention
from scripts.experiment_error_receipt import error_receipt

def prepare():
    cases,inputs=source_cases()
    current=R/'dimension-report-boundary-model-20261115-v2/attempt/case-00/edit-result.json'
    earlier=R/'associated-field-report-model-20261115-v1/attempt/arm-00/result.json'
    immune=R/'source-view-native-model-20261115-v1/attempt/actual_view_scope/result.json'
    a,b=read(current)['proposals']['eligible'];old,=[p for p in read(earlier)['edit_proposals']['eligible']if p['anchor_id']==206]
    issue,=read(immune)['native_applied']
    assert a['anchor']==old['anchor']and a['anchor_start']==old['anchor_start']
    assert issue['statement']in cases[1]['report']
    texts0={'t17':a['anchor'],'t23':b['anchor'],'t04':a['addition'],'t08':b['addition'],'t66':old['addition']}
    texts1={'t41':issue['statement'],'t55':issue['statement'],'t77':issue['replacement']}
    pairs0=[dict(pair_id='p31',original='t17',candidate='t04'),dict(pair_id='p12',original='t23',candidate='t08'),dict(pair_id='p76',original='t17',candidate='t66')]
    pairs1=[dict(pair_id='p54',original='t41',candidate='t55'),dict(pair_id='p28',original='t41',candidate='t77')]
    prepared=[]
    for i,(c,texts,pairs,groups)in enumerate(zip(cases,[texts0,texts1],[pairs0,pairs1],[['t17 t23','t04 t08 t66'],['t41','t55 t77']])):
        c['texts']=texts;c['pairs']=pairs;c['units']=source_units(c['material'],c['source_ids']);c['inventory_groups']=[]
        for names in groups:
            selected={k:texts[k]for k in names.split()};c['inventory_groups'].append(selected)
            prepared.append(dict(case_index=i,texts=selected,prompt=inventory_prompt(c['question'],selected)))
    return cases,prepared,[*inputs,current,earlier,immune]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--replay',type=Path)
    a=p.parse_args();assert not(a.execute and a.replay);cases,prepared,inputs=prepare()
    from tokenizers import Tokenizer
    assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
    tok=Tokenizer.from_file(str(TOKENIZER));tokens=lambda s:len(tok.encode(s,add_special_tokens=False).ids)
    for j in prepared:assert int(tokens(j['prompt'])*1.1)+6000+8192<=131072
    # Source registry already contains ALL acquired text; no selected passage truncation.
    estimates=[tokens(retention_prompt(c['question'],c['pairs'],[],c['texts'],c['units']))for c in cases]
    assert all(int(n*1.1)+12000+6000+8192<=131072 for n in estimates)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    code=[Path(__file__),Path('scripts/run_dimension_report_boundary_20261115.py'),Path('scripts/run_associated_field_report_pair_20261115.py'),
          Path('scripts/prepare_source_detail_material_20261114.py'),Path('scripts/run_native_original_report_pair_20261114.py'),
          Path('scripts/experiment_error_receipt.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    if a.execute:
        assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
        assert all(sha(Path(n))==h for n,h in read(a.preflight/'prestart-freeze.json').items())
        inputs.extend(a.preflight/n for n in ['prestart-freeze.json','completion.json','plan.json'])
    if a.replay:inputs.extend(p for p in a.replay.rglob('*')if p.is_file()and 'code'not in p.parts)
    freeze={str(p):sha(p)for p in [*inputs,*code]};write(a.out_dir/'prestart-freeze.json',freeze)
    for path in code:
        dest=a.out_dir/'code'/path.resolve().relative_to(Path.cwd());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.max_retries':0,
        'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    write(a.out_dir/'plan.json',dict(scope=__doc__,maximum_fresh_calls=6,settings=settings,source_only_estimated_comparison_tokens=estimates,
        protocol='Read original and candidate spans in separate fresh contexts with no source, prior verdict or before/after role labels. Candidates grouped within task, so version similarity may be visible. Then compare all original and candidate facts against complete actual source units under original question. Four inventory calls plus2source-scoped comparisons. No whole-report context, original Reader verdicts, expected facts/counts or feedback labels in model input; no approvals/edits/native/Writer/search/publication.',
        control_provenance='Actual historical IF retained/loss model proposals; actual immune adverse native MACS-to-FACS replacement; immune unchanged identity calibration copied original statement, never counts as new correction. Known used examples, not heldout or majority/generalization evidence.',
        tokenizer_endpoint_identity='unverified;10percentmargin+6000output+8192reserve',independent_correction_credit=0))
    for i,j in enumerate(prepared):(a.out_dir/f'prepared-{i:02d}-prompt.txt').write_text(j['prompt'])
    for i,c in enumerate(cases):write(a.out_dir/f'case-{i:02d}-inputs.json',dict(question=c['question'],texts=c['texts'],pairs=c['pairs'],units=c['units']))
    calls=[];inventories=[[],[]];results=[];model=None;failure=None
    def invoke(prompt,stage,case_index):
        nonlocal model
        assert len(calls)<6 and int(tokens(prompt)*1.1)+6000+8192<=131072
        n=len(calls);pp=a.out_dir/f'call-{n:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=n,stage=stage,case_index=case_index,prompt_sha256=sha(pp),prompt_chars=len(prompt),estimated_tokens=tokens(prompt),status='started')
        calls.append(row);write(a.out_dir/'calls.json',calls)
        try:
            if a.replay:
                old=read(a.replay/'calls.json')[n];assert old['status']=='returned'and old['stage']==stage and old['case_index']==case_index and old['prompt_sha256']==row['prompt_sha256']
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
            for i,j in enumerate(prepared):
                if a.preflight:assert j['prompt']==(a.preflight/f'prepared-{i:02d}-prompt.txt').read_text()
                inventories[j['case_index']].extend(parse_inventory(invoke(j['prompt'],'independent_span_inventory',j['case_index']),j['texts']))
            write(a.out_dir/'inventories.json',inventories)
            for i,c in enumerate(cases):
                prompt=retention_prompt(c['question'],c['pairs'],inventories[i],c['texts'],c['units'])
                parsed=parse_retention(invoke(prompt,'source_scoped_retention_comparison',i),c['pairs'],inventories[i],c['units'])
                results.append(dict(case_index=i,pairs=parsed))
        except Exception as exc:failure=error_receipt(exc)
    write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('preflight_only'if not(a.execute or a.replay)else'completed_retention_diagnostic'),
        failure=failure,logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),inventories=inventories,results=results,
        frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),report_changes=0,independent_correction_credit=0))
    print(json.dumps(dict(failure=failure,logical_calls=len(calls),comparison_cases=len(results),independent_correction_credit=0)))
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
