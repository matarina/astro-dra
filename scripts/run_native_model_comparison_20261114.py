"""Exact-prompt first-pass comprehension comparison on two exposed groups only."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.evidence_flow import parse_review
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--language-attempt',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(a.catalog.read_text());models=['deepseek-v4-flash','Qwen3.8-27B']
    assert all(m in catalog['model_ids'] for m in models)
    assert json.loads((a.language_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    plan=json.loads((a.language_attempt/'plan.json').read_text());oldcalls=json.loads((a.language_attempt/'calls.json').read_text())
    inputs=[Path(__file__),Path('scripts/experiment_error_receipt.py'),a.catalog,a.language_attempt/'plan.json',a.language_attempt/'calls.json',a.language_attempt/'completion.json',
        *Path('local_deep_research/research_verify').glob('*.py')];jobs=[]
    for job in plan['jobs']:
        name=job['name'];claims={int(k):v for k,v in job['claims'].items()}
        call=next(x for x in oldcalls if x['job']==name and x['stage']=='original_native_check')
        prompt=a.language_attempt/name/f"call-{call['call_id']:03d}-prompt.txt"
        assert sha(prompt)==call['prompt_sha256'];inputs.append(prompt)
        folder=a.out_dir/name;folder.mkdir();(folder/'native-prompt.txt').write_bytes(prompt.read_bytes())
        jobs.append(dict(name=name,claims=claims,prompt=prompt.read_text(),folder=folder))
    freeze={str(path):sha(path) for path in inputs};root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Two exposed original-language first-pass groups; no report generation, repair, independent quality or held-out evaluation',
        models=models,model_identity='Endpoint aliases only; checkpoint and backend identity not verified',temperature=0,max_tokens=6000,planned_calls=4,
        jobs=[dict(name=j['name'],claims=j['claims'],prompt_sha256=hashlib.sha256(j['prompt'].encode()).hexdigest()) for j in jobs],
        delta='Only requested model alias; exact same prompts, sources, IDs and native parser',report_changes=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(planned_calls=4)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    base=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});base.update({
        'llm.provider':'openai_endpoint','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[];results=[]
    for n,j in enumerate(jobs):
        for model_name in (models if n%2==0 else list(reversed(models))):
            snap={**base,'llm.model':model_name};folder=j['folder']/model_name;folder.mkdir()
            i=len(calls);entry=dict(call_id=i,job=j['name'],model=model_name,prompt_sha256=hashlib.sha256(j['prompt'].encode()).hexdigest());calls.append(entry)
            (folder/f'call-{i:03d}-prompt.txt').write_text(j['prompt']);row=dict(job=j['name'],model=model_name)
            try:
                with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
                    model=get_llm(settings_snapshot=snap);response=model.invoke(j['prompt'])
                raw=str(getattr(response,'content',response));(folder/f'call-{i:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest())
                issues,checked=parse_review(raw,j['claims'],include_checked=True);row.update(status='parsed',issues=issues,checked=checked)
            except Exception as exc:
                diagnostic=error_receipt(exc);row.update(status='unavailable',**diagnostic)
                if entry.get('status')!='returned':entry.update(status='unavailable',**diagnostic)
            (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');results.append(row)
            (a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
    completion=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),
        report_changes=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),parsed=sum(r['status']=='parsed' for r in results))))


if __name__=='__main__':main()
