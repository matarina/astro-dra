"""Fixed real proposals: isolate newly acquired primary body evidence, no writer."""
import argparse
import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from research_verify.evidence_flow import confirm_repairs
from research_verify.generation import SourceMaterial
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    root=Path('evaluation/frontier-strategy-20261113')
    old=root/'sequential-native-xenium-model-20261114-v1/attempt'
    xml=root/'coordinator-xenium-methods-acquisition-20261114-v1/PMC12449477.xml'
    receipt=xml.with_name('receipt.json');assert sha(xml)==json.loads(receipt.read_text())['sha256']
    article=ET.fromstring(xml.read_bytes());ids={n.get('pub-id-type'):''.join(n.itertext()) for n in article.findall('./front/article-meta/article-id')}
    assert ids['doi']=='10.1038/s41416-025-03088-0' and ids['pmid']=='40670667'
    # Entire body, all paragraphs/headings in document order; no claim-keyword selection.
    body=article.find('body');fulltext='\n\n'.join(''.join(e.itertext()) for e in body.iter() if e.tag in {'title','p'})
    rows=[json.loads(l) for l in (old/'candidate/trace.jsonl').read_text().splitlines()]
    group=next(r['data'] for r in rows if r['stage']=='sequential_group_input' and r['data']['group']==3)
    proposals=next(r['data']['issues'] for r in rows if r['stage']=='sequential_group_proposals' and r['data']['group']==3)
    views={int(k):v for k,v in group['material_views'].items()}
    assert all('10.1038/s41416-025-03088-0' in views[i]['metadata'] for i in [14,15])
    material=SourceMaterial(group['material'],views)
    updated=copy.deepcopy(views);updated[15]['text']=fulltext
    updated[15]['metadata']+='\nEvidence type: newly acquired primary XML full-text body (all body paragraphs/headings); figures/tables/references outside these elements not fully represented.\n'
    # Confirmation uses registry text/metadata. Underlying prior rendered string is
    # provenance only; no assertion that it already contains this newly acquired body.
    expanded=SourceMaterial(group['material'],updated)
    plan=json.loads((old/'plan.json').read_text());report=(old/'baseline/report.txt').read_text()
    jobs=[]
    for issue in proposals:
        # Both actual proposals, including supported-control. No label enters prompts.
        for arm in ['abstract_union','primary_body']:
            jobs.append(dict(issue=issue,arm=arm,material=material if arm=='abstract_union' else expanded,
                             report=report,query=plan['query']))
    inputs=[old/'candidate/trace.jsonl',old/'baseline/report.txt',old/'plan.json',xml,receipt,
            Path(__file__),Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),
            *Path('local_deep_research/research_verify').glob('*.py')]
    return jobs,inputs,fulltext,ids


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    jobs,inputs,fulltext,ids=prepare();a.out_dir.mkdir(parents=True,exist_ok=False)
    freeze={str(f):sha(f) for f in inputs};root=Path.cwd()
    for f in inputs:
        rel=f.relative_to(root) if f.is_absolute() else f
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    (a.out_dir/'primary-body.txt').write_text(fulltext)
    protocol=dict(scope='Two fixed actual proposals, separate native confirmations only; no full-report pipeline or independent outcome scoring',
        original_attempt='sequential-native-xenium-model-20261114-v1/attempt',primary_article_ids=ids,
        primary_body_sha256=sha(a.out_dir/'primary-body.txt'),primary_body_chars=len(fulltext),
        delta='Only source15 context/metadata gains newly acquired full body; same current citation union/approval/attribute/consistency handling',
        maximum_calls=8,context_budget=80000,model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        upstream_cost='Excludes prior25-call whole-report run and primary acquisition; fixed proposals reuse prior reviewer outputs',
        jobs=[dict(claim_id=j['issue']['claim_id'],arm=j['arm'],issue=j['issue']) for j in jobs],
        quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    calls=[];results=[]
    def handler_for(job,folder,model=None):
        def invoke(prompt,**kw):
            assert len(prompt)<=80000 and len(calls)<8
            n=len(calls);entry=dict(call_id=n,claim_id=job['issue']['claim_id'],arm=job['arm'],stage=kw.get('stage'),
                prompt_chars=len(prompt),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),folder=str(folder.relative_to(a.out_dir)))
            calls.append(entry);(folder/f'call-{n:03d}-prompt.txt').write_text(prompt)
            if model is None:return '{"decisions":[]}'
            try:
                raw=str(model.invoke(prompt).content);(folder/f'call-{n:03d}-response.txt').write_text(raw)
                entry.update(status='returned',response_sha256=hashlib.sha256(raw.encode()).hexdigest());return raw
            except Exception as exc:entry.update(status='unavailable',**error_receipt(exc));raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        return type('Handler',(),{'get_setting':staticmethod(lambda k,d=None:True if k in {'citation.attribute_confirmation_review','citation.confirmation_consistency_review'} else d),
                                 '_invoke_text':staticmethod(invoke)})()
    def run_jobs(model=None):
        for j in jobs:
            folder=a.out_dir/f"claim-{j['issue']['claim_id']}"/j['arm'];folder.mkdir(parents=True)
            report,applied,pending=confirm_repairs(handler_for(j,folder,model),j['report'],[j['issue']],j['material'],j['query'],Trace(folder/'trace.jsonl'))
            (folder/'report.txt').write_text(report);r=dict(claim_id=j['issue']['claim_id'],arm=j['arm'],native_applied=applied,native_unresolved=pending,
                report_sha256=sha(folder/'report.txt'),report_chars=len(report),quality_claim=None,newly_credited_corrections=0)
            (folder/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');results.append(r)
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        from local_deep_research.config.thread_settings import settings_context
        from local_deep_research.config.llm_config import get_llm
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
        snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
            'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):run_jobs(get_llm(settings_snapshot=snap))
    else:run_jobs()
    if not a.execute:assert len(calls)==len(jobs), "Incomplete preflight prompts"
    complete=dict(preflight_only=not a.execute,calls=len(calls),results=results,
        frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(complete,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(preflight_only=not a.execute,calls=len(calls),prompt_chars=[c['prompt_chars']for c in calls])))


if __name__=='__main__':main()
