"""Fallible bilingual readings into original-language native repair, exposed groups only."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.claim_language import parse_translations, fidelity_prompt, parse_fidelity, bilingual_notes, original_language_comparison_notes
from research_verify.source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS
from research_verify.comparison_reconciliation import reconciliation_notes
from research_verify.evidence_flow import confirm_repairs, parse_review
from scripts.run_native_original_report_pair_20261114 import Trace


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--language-attempt',type=Path,required=True)
    p.add_argument('--source-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--english-review-attempt',type=Path)
    p.add_argument('--fidelity-attempt',type=Path)
    p.add_argument('--original-review-attempt',type=Path)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    for path in [a.language_attempt,a.source_attempt]:
        assert json.loads((path/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    language=json.loads((a.language_attempt/'plan.json').read_text());source=json.loads((a.source_attempt/'plan.json').read_text())
    jobs=[];inputs=[Path(__file__),Path('scripts/run_native_original_report_pair_20261114.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    for parent in [a.language_attempt,a.source_attempt]:inputs.extend([parent/'completion.json',parent/'plan.json'])
    for job in language['jobs']:
        name=job['name'];claims={int(k):v for k,v in job['claims'].items()};folder=a.out_dir/name;folder.mkdir()
        base=a.language_attempt/name/'base-native-prompt.txt';translated=a.language_attempt/name/'translations.json'
        original=a.source_attempt/name/'original-report.txt'
        prior=next(j for j in source['jobs'] if j['name']==name)
        assert sha(base)==prior['native_prompt_sha256'] and sha(original)==prior['original_report_sha256']
        assert job['claims']==prior['claims']
        # Re-parse the ORIGINAL raw translation response, not a hand-edited reading.
        calls=json.loads((a.language_attempt/'calls.json').read_text())
        call=next(c for c in calls if c['job']==name and c['stage']=='translation')
        raw=a.language_attempt/name/f"call-{call['call_id']:03d}-response.txt"
        assert sha(raw)==call['response_sha256'];readings=parse_translations(raw.read_text(),claims)
        assert {str(k):v for k,v in readings.items()}==json.loads(translated.read_text())
        prompt=base.read_text();material=prompt.split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
        query=prompt.split('Question: ',1)[1].split('\n',1)[0]
        inputs.extend([base,translated,original,raw,a.language_attempt/'calls.json'])
        (folder/'original-report.txt').write_text(original.read_text())
        jobs.append(dict(name=name,folder=folder,claims=claims,readings=readings,prompt=prompt,
            material=material,query=query,report=original.read_text()))
    if a.english_review_attempt:
        # Reuse the existing English checker output as fallible observations, never gold.
        assert a.english_review_attempt.resolve()==a.language_attempt.resolve()
        review_path=a.english_review_attempt/'results.json';inputs.append(review_path)
        reviews=json.loads(review_path.read_text())
        for j in jobs:
            r=next(x for x in reviews if x['job']==j['name'] and x['arm']=='english');assert r['status']=='parsed'
            call=next(c for c in json.loads((a.language_attempt/'calls.json').read_text()) if c['job']==j['name'] and c['stage']=='english_native_check')
            raw=a.language_attempt/j['name']/f"call-{call['call_id']:03d}-response.txt";assert sha(raw)==call['response_sha256'];inputs.append(raw)
            english_claims={k:{**c,'text':j['readings'][k]['text']} for k,c in j['claims'].items()}
            issues,checked=parse_review(raw.read_text(),english_claims,include_checked=True)
            assert issues==r['issues'] and checked==r['checked']
            j['english_review']=dict(issues=issues,checked=checked)
    if a.fidelity_attempt:
        assert json.loads((a.fidelity_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
        fp=a.fidelity_attempt/'plan.json';inputs.extend([fp,a.fidelity_attempt/'completion.json',a.fidelity_attempt/'calls.json'])
        old=json.loads(fp.read_text());old_calls=json.loads((a.fidelity_attempt/'calls.json').read_text())
        for j in jobs:
            oldj=next(x for x in old['jobs'] if x['name']==j['name'])
            assert oldj['claims']=={str(k):v for k,v in j['claims'].items()} and oldj['readings']=={str(k):v for k,v in j['readings'].items()}
            call=next(x for x in old_calls if x['job']==j['name'] and x['stage']=='linguistic_fidelity')
            prompt=a.fidelity_attempt/j['name']/f"call-{call['call_id']:03d}-prompt.txt";raw=prompt.with_name(prompt.name.replace('-prompt','-response'))
            assert sha(prompt)==call['prompt_sha256'] and sha(raw)==call['response_sha256']
            assert prompt.read_text()==fidelity_prompt(j['claims'],j['readings']);inputs.extend([prompt,raw])
            j['cached_fidelity']=parse_fidelity(raw.read_text(),j['claims'])
    if a.original_review_attempt:
        assert a.english_review_attempt and a.fidelity_attempt
        old=a.original_review_attempt
        assert json.loads((old/'completion.json').read_text())['frozen_inputs_unchanged'] is True
        inputs.extend([old/'completion.json',old/'calls.json',old/'plan.json'])
        old_calls=json.loads((old/'calls.json').read_text())
        for j in jobs:
            result=old/j['name']/'original/result.json';r=json.loads(result.read_text());assert r['status']=='parsed'
            call=next(x for x in old_calls if x['job']==j['name'] and x['arm']=='original' and x['stage']=='native_check')
            prompt=old/j['name']/'original'/f"call-{call['call_id']:03d}-prompt.txt";raw=prompt.with_name(prompt.name.replace('-prompt','-response'))
            assert sha(prompt)==call['prompt_sha256'] and sha(raw)==call['response_sha256']
            assert prompt.read_text()==j['prompt']+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS
            issues,checked=parse_review(raw.read_text(),j['claims'],include_checked=True)
            assert issues==r['issues'] and checked==r['checked'];j['original_review']=dict(issues=issues,checked=checked)
            inputs.extend([result,prompt,raw])
    freeze={str(path):sha(path) for path in inputs};root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Two exposed eight-unit groups, complete original report copies but NOT whole-report checking',
        jobs=[dict(name=j['name'],query=j['query'],claims=j['claims'],readings=j['readings'],
            english_review=j.get('english_review'),
            original_review=j.get('original_review'),
            native_prompt_sha256=hashlib.sha256(j['prompt'].encode()).hexdigest(),
            material_sha256=hashlib.sha256(j['material'].encode()).hexdigest(),
            original_report_sha256=hashlib.sha256(j['report'].encode()).hexdigest()) for j in jobs],
        arms=['english_observations','dual_observations'] if a.original_review_attempt else ['original','bilingual'],
        reconcile_observations=bool(a.original_review_attempt),
        planned_fidelity_calls=0 if a.fidelity_attempt else 2,planned_native_calls=4,maximum_confirmation_calls=4,
        delta=('Both arms omit prior replacements; candidate additionally receives separate original-language review observations' if a.original_review_attempt else
            'Append source-blind readings, separate fallible linguistic review'+(' and fixed English checker observations' if a.english_review_attempt else '')+' to original native request; unchanged native approval rules'),
        confirmation='Same native attribute confirmation ON in both arms; no bilingual appendix or forced approval',
        fixed_english_observations=bool(a.english_review_attempt),cached_fidelity=bool(a.fidelity_attempt),
        cached_fidelity_attempt=str(a.fidelity_attempt) if a.fidelity_attempt else None,
        upstream_cost='Reuses six-call translation/English-check diagnostic and two linguistic fidelity calls; not a fresh whole pipeline comparison',
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(planned_calls=4+protocol['planned_fidelity_calls'],maximum_calls=8+protocol['planned_fidelity_calls'])));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[];results=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        def invoke(prompt,folder,stage):
            assert len(prompt)<=60000
            n=len(calls);entry=dict(call_id=n,job=folder.relative_to(a.out_dir).parts[0],arm=folder.name,
                stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            try:
                response=model.invoke(prompt);raw=str(getattr(response,'content',response));(folder/f'call-{n:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__);raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        for n,j in enumerate(jobs):
            try:fidelity=j['cached_fidelity'] if 'cached_fidelity' in j else parse_fidelity(invoke(fidelity_prompt(j['claims'],j['readings']),j['folder'],'linguistic_fidelity'),j['claims'])
            except Exception as exc:fidelity={k:dict(status='unknown',reason=type(exc).__name__) for k in j['claims']}
            (j['folder']/'fidelity.json').write_text(json.dumps(fidelity,ensure_ascii=False,indent=2)+'\n')
            for arm in (protocol['arms'] if n%2==0 else list(reversed(protocol['arms']))):
                folder=j['folder']/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
                prompt=j['prompt']+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS
                if a.original_review_attempt:
                    prompt+='\n\n'+reconciliation_notes(j['claims'],j['readings'],fidelity,j['english_review'],
                        j['original_review'] if arm=='dual_observations' else None)
                if arm=='bilingual':prompt+='\n\n'+(original_language_comparison_notes(j['readings'],fidelity,j['english_review'])
                    if 'english_review' in j else bilingual_notes(j['readings'],fidelity))
                revised=j['report'];applied=[];unresolved=[];row=dict(job=j['name'],arm=arm)
                try:
                    raw=invoke(prompt,folder,'native_check');issues,checked=parse_review(raw,j['claims'],include_checked=True)
                    handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d),
                        '_invoke_text':staticmethod(lambda prompt,**kw:invoke(prompt,folder,'repair_validation'))})()
                    revised,applied,unresolved=confirm_repairs(handler,revised,issues,j['material'],j['query'],trace)
                    row.update(status='parsed',issues=issues,checked=checked)
                except Exception as exc:row.update(status='unavailable',error_type=type(exc).__name__)
                (folder/'report.txt').write_text(revised);row.update(native_applied=applied,native_unresolved=unresolved,
                    report_sha256=sha(folder/'report.txt'),report_chars=len(revised),quality_claim=None,newly_credited_corrections=0)
                (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');results.append(row)
    completion=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),frozen_inputs_unchanged=completion['frozen_inputs_unchanged'])))


if __name__=='__main__':main()
