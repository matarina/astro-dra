"""One fixed actual whole-report proposal: literal reselection then native confirmation."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.quote_reselection import quotation_prompt,parse_quote_updates
from research_verify.evidence_flow import confirm_repairs
from research_verify.generation import SourceMaterial
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    base=Path('evaluation/frontier-strategy-20261113');old=base/'sequential-attribute-neuropathy-model-20261114-v1/attempt'
    rows=[json.loads(l)for l in (old/'candidate/trace.jsonl').read_text().splitlines()]
    group=next(r['data']for r in rows if r['stage']=='sequential_group_input'and r['data']['group']==2)
    issues=next(r['data']['issues']for r in rows if r['stage']=='sequential_group_proposals'and r['data']['group']==2)
    material=SourceMaterial(group['material'],{int(k):v for k,v in group['material_views'].items()})
    report=(old/'baseline/report.txt').read_text();plan=json.loads((old/'plan.json').read_text())
    assert all(report.count(i['statement'])==1 for i in issues)
    inputs=[Path(__file__),Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),
        *Path('local_deep_research/research_verify').glob('*.py'),old/'candidate/trace.jsonl',old/'baseline/report.txt',old/'plan.json',old/'completion.json']
    return issues,material,report,plan['query'],inputs


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    issues,material,original,query,inputs=prepare();a.out_dir.mkdir(parents=True,exist_ok=False)
    freeze={str(f):sha(f)for f in inputs};root=Path.cwd()
    for f in inputs:
        rel=f.relative_to(root)if f.is_absolute()else f
        if str(rel).startswith(('scripts/','local_deep_research/')):
            target=a.out_dir/'code'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    (a.out_dir/'original-report.txt').write_text(original)
    plan=dict(scope='Fixed actual rendered proposal from exposed complete-report diagnostic; quote transport only, not a fresh whole pipeline or independent outcome',
        query=query,issues=issues,material=str(material),material_views=material.views,original_report_sha256=sha(a.out_dir/'original-report.txt'),
        maximum_fresh_calls=3,model='deepseek-v4-flash',temperature=0,max_tokens=6000,context_budget=60000,
        upstream_cost='Excludes prior34fresh complete-report calls and source acquisition',quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(proposals=len(issues),quote_prompt_chars=len(quotation_prompt(issues,material)),maximum_fresh_calls=3)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[];results=[];folder=a.out_dir/'baseline';folder.mkdir()
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        def invoke(prompt,**kw):
            assert len(prompt)<=60000 and len(calls)<3
            n=len(calls);entry=dict(call_id=n,stage=kw.get('stage'),folder=folder.name,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            try:
                raw=str(model.invoke(prompt).content);(folder/f'call-{n:03d}-response.txt').write_text(raw);entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        handler=type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k in {'citation.attribute_confirmation_review','citation.confirmation_consistency_review'}else d),'_invoke_text':staticmethod(invoke)})()
        for arm in ['baseline','reselected']:
            folder=a.out_dir/arm;folder.mkdir(exist_ok=True);selected=issues;receipts=[]
            if arm=='reselected':
                try:selected,receipts=parse_quote_updates(invoke(quotation_prompt(issues,material),stage='quote_reselection'),issues,material)
                except Exception as exc:receipts=[dict(status='unavailable',**error_receipt(exc))]
            report,applied,pending=confirm_repairs(handler,original,selected,material,query,Trace(folder/'trace.jsonl'))
            (folder/'report.txt').write_text(report);result=dict(arm=arm,issues=selected,quote_receipts=receipts,native_applied=applied,native_unresolved=pending,
                report_sha256=sha(folder/'report.txt'),report_chars=len(report),quality_claim=None,newly_credited_corrections=0)
            (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');results.append(result)
    completion=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(f))==h for f,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls),applied=[len(r['native_applied'])for r in results])))


if __name__=='__main__':main()
