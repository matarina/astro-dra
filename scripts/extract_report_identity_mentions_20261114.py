"""Report-only identity extraction diagnostic, no sources/judge labels supplied."""
import argparse,dataclasses,hashlib,json
from pathlib import Path
from research_verify.identity_mentions import identity_units,identity_prompt,parse_identity_mentions


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True)
    p.add_argument('--max-units',type=int,default=12)
    p.add_argument('--cited-only',action='store_true')
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    if a.max_units < 1:p.error('--max-units must be positive')
    report=a.report.read_text();units=identity_units(report,include_unbound=not a.cited_only);batches=[];batch=[]
    for unit in units:
        if batch and (len(batch)>=a.max_units or len(json.dumps([*batch,unit],ensure_ascii=False))>12000):
            batches.append(batch);batch=[]
        batch.append(unit)
    if batch:batches.append(batch)
    freeze={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.report,Path(__file__),
             *[Path('local_deep_research/research_verify')/name for name in
               ['identity_mentions.py','identity_audit.py','claims.py','report_syntax.py']]]}
    for path in freeze:
        if path.startswith(('local_deep_research/','scripts/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(Path(path).read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    values=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in values.items()})
    snapshot.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,
                     'llm.max_tokens':2000,'llm.request_timeout':120,'llm.max_retries':1})
    def setting(k,d=None):return snapshot.get(k,d)
    calls=[];mentions=[];unresolved=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(setting)})()):
        model=get_llm(settings_snapshot=snapshot)
        for i,batch in enumerate(batches):
            prompt=identity_prompt(batch);entry=dict(batch=i,prompt=prompt)
            try:
                raw=model.invoke(prompt);raw=str(getattr(raw,'content',raw));entry['response']=raw
                clean=raw.strip()
                if clean.startswith('```'):clean=clean.split('\n',1)[1].rsplit('```',1)[0].strip()
                accepted,unknown=parse_identity_mentions(clean,report,batch)
                for row in accepted:
                    value=dataclasses.asdict(row['mention']);value['mention_id']=f'b{i}-'+value['mention_id']
                    mentions.append(dict(**value,unit_id=row['unit_id'],field_positions=row['field_positions']))
                unresolved.extend(unknown);entry.update(status='completed',accepted=len(accepted),unresolved=len(unknown))
            except Exception as exc:entry.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:200])
            calls.append(entry)
            (a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n')
    out=dict(scope='Report-only model extraction and coordinate integrity; no identity truth/correction score',
             max_units_per_batch=a.max_units,report_sha256=freeze[str(a.report)],
             include_unbound=not a.cited_only,
             report_units=len(units),calls=len(calls),failed=sum(c['status']=='failed' for c in calls),
             mentions=mentions,unresolved=unresolved,quality_claim=None,
             frozen_inputs_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in freeze.items()))
    (a.out_dir/'extraction.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(units=len(units),calls=len(calls),mentions=len(mentions),failed=out['failed'])))


if __name__=='__main__':main()
