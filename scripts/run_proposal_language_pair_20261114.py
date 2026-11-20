"""Fixed English proposals: direct versus source-blind original-language rendering."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.evidence_flow import parse_review,confirm_repairs
from research_verify.proposal_language import proposal_render_prompt,parse_rendered_proposals
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--language-attempt',type=Path,required=True)
    p.add_argument('--source-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    for parent in [a.language_attempt,a.source_attempt]:assert json.loads((parent/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    plan=json.loads((a.language_attempt/'plan.json').read_text());sources=json.loads((a.source_attempt/'plan.json').read_text())
    results=json.loads((a.language_attempt/'results.json').read_text());calls=json.loads((a.language_attempt/'calls.json').read_text())
    inputs=[Path(__file__),Path('scripts/experiment_error_receipt.py'),Path('scripts/run_native_original_report_pair_20261114.py'),
        *Path('local_deep_research/research_verify').glob('*.py')];jobs=[]
    for parent in [a.language_attempt,a.source_attempt]:inputs.extend([parent/'plan.json',parent/'completion.json'])
    inputs.extend([a.language_attempt/'results.json',a.language_attempt/'calls.json'])
    for j in plan['jobs']:
        name=j['name'];claims={int(k):v for k,v in j['claims'].items()}
        readings=json.loads((a.language_attempt/name/'translations.json').read_text())
        call=next(x for x in calls if x['job']==name and x['stage']=='english_native_check')
        raw=a.language_attempt/name/f"call-{call['call_id']:03d}-response.txt";assert sha(raw)==call['response_sha256']
        issues,checked=parse_review(raw.read_text(),{k:{**c,'text':readings[str(k)]['text']} for k,c in claims.items()},include_checked=True)
        old=next(r for r in results if r['job']==name and r['arm']=='english');assert issues==old['issues'] and checked==old['checked']
        proposals=[{**i,'statement':claims[i['claim_id']]['text']} for i in issues if i['status']=='contradiction' and i.get('replacement')]
        base=a.language_attempt/name/'base-native-prompt.txt';original=a.source_attempt/name/'original-report.txt'
        src=next(x for x in sources['jobs'] if x['name']==name)
        assert sha(base)==src['native_prompt_sha256'] and sha(original)==src['original_report_sha256']
        text=base.read_text();material=text.split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
        query=text.split('Question: ',1)[1].split('\n',1)[0];folder=a.out_dir/name;folder.mkdir();(folder/'original-report.txt').write_bytes(original.read_bytes())
        inputs.extend([raw,base,original,a.language_attempt/name/'translations.json'])
        jobs.append(dict(name=name,issues=proposals,material=material,query=query,report=original.read_text(),folder=folder))
    freeze={str(x):sha(x) for x in inputs};root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Fixed real English proposals from two exposed groups; post-proposal language stage only, NOT production baseline or whole-report review',
        arms=['direct_proposal','rendered_proposal'],planned_render_calls=2,maximum_confirmation_calls=4,
        upstream_cost='Six-call translation/check diagnostic reused; additional upstream retrieval and source preparation excluded from this stage cost',
        jobs=[dict(name=j['name'],issues=j['issues'],query=j['query'],material=j['material'],original_report_sha256=hashlib.sha256(j['report'].encode()).hexdigest()) for j in jobs],
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,confirmation='Same unchanged native attribute confirmation ON in both arms',
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(proposals=sum(len(j['issues']) for j in jobs),maximum_calls=6)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[];rows=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        def invoke(prompt,folder,stage):
            assert len(prompt)<=60000
            n=len(calls);entry=dict(call_id=n,job=folder.relative_to(a.out_dir).parts[0],arm=folder.name,stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            try:
                response=model.invoke(prompt);raw=str(getattr(response,'content',response));(folder/f'call-{n:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        for n,j in enumerate(jobs):
            try:
                rendered=parse_rendered_proposals(invoke(proposal_render_prompt(j['issues']),j['folder'],'source_blind_rendering'),j['issues'])
                (j['folder']/'renderings.json').write_text(json.dumps(rendered,ensure_ascii=False,indent=2)+'\n')
            except Exception as exc:
                rows.append(dict(job=j['name'],status='rendering_unavailable',**error_receipt(exc)));continue
            for arm in (protocol['arms'] if n%2==0 else list(reversed(protocol['arms']))):
                folder=j['folder']/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');issues=j['issues']
                if arm=='rendered_proposal':issues=[{**i,'replacement':rendered[i['claim_id']]['text']} for i in issues]
                handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k=='citation.attribute_confirmation_review' else d),
                    '_invoke_text':staticmethod(lambda prompt,**kw:invoke(prompt,folder,'repair_validation'))})()
                report,applied,unresolved=confirm_repairs(handler,j['report'],issues,j['material'],j['query'],trace)
                (folder/'report.txt').write_text(report);row=dict(job=j['name'],arm=arm,native_applied=applied,native_unresolved=unresolved,
                    report_sha256=sha(folder/'report.txt'),report_chars=len(report),quality_claim=None,newly_credited_corrections=0)
                (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');rows.append(row)
    completion=dict(calls=len(calls),results=rows,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls))))


if __name__=='__main__':main()
