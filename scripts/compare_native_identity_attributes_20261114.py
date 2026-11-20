"""Paired native-review diagnostic; no report edits or independent verdicts."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from scripts.prepare_source_detail_material_20261114 import native_documents
from research_verify.evidence_flow import (
    _review_material,required_sources,document_structure_spans,review_prompt,parse_review,
    IDENTITY_ATTRIBUTE_INSTRUCTIONS,
    literal_assertion_spans,
)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--before-plan-dir',type=Path,required=True)
    p.add_argument('--report-index',type=int,action='append',required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113');assembly_path=base/'archive-identity-sourcepacks-20261114-v3/assembly-audit.json'
    inventory_path=Path('evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json')
    plan_path=a.before_plan_dir/'plan.json';prior=json.loads(plan_path.read_text())
    assembly=json.loads(assembly_path.read_text());tasks={t['task_id']:t['original_prompt'] for t in json.loads(inventory_path.read_text())['tasks']}
    jobs=[];inputs=[Path(__file__),plan_path,assembly_path,inventory_path,
        Path('scripts/prepare_source_detail_material_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    for report_index in a.report_index:
        row=assembly['reports'][report_index];path=Path(row['report_path']);pack=Path(row['source_pack_path']);inputs.extend([path,pack])
        report=path.read_text();sources=json.loads(pack.read_text());docs=native_documents(sources)
        query=tasks[prior['reports'][report_index]['task_id']];structures=document_structure_spans(report)
        reserve=min(8000,len(json.dumps(structures,ensure_ascii=False)))
        for old in prior['jobs']:
            if old['report_index']!=report_index or old['status']!='prepared':continue
            claims={int(k):v for k,v in old['claims'].items()};section='\n'.join(c['text'] for c in claims.values())
            material,prompt_claims=_review_material(docs,query+'\n'+section,claims,required_sources(section,sources),max(2000,60000-reserve))
            context=query+'\nExisting report headings (destinations must use these exact headings):\n'+'\n'.join(re.findall(r'^#{1,6} .+',report,re.M))
            kwargs=dict(claims=prompt_claims,structure_spans=structures,prompt_budget=60000)
            control=review_prompt(context,section,material,**kwargs)
            treatment=review_prompt(context,section,material,identity_attributes=True,**kwargs)
            frozen_prompt=a.before_plan_dir/old['name']/'prompt.txt';inputs.append(frozen_prompt)
            assert control==frozen_prompt.read_text(),'Disabled native prompt differs from frozen author-enabled baseline'
            annotated_claims={k:{**c,'literal_assertion_spans':literal_assertion_spans(c['text'])}
                              for k,c in prompt_claims.items()}
            expected=review_prompt(context,section,material,**{**kwargs,'claims':annotated_claims})
            assert treatment==expected+'\n\n'+IDENTITY_ATTRIBUTE_INSTRUCTIONS
            d=a.out_dir/old['name'];d.mkdir();(d/'material.txt').write_text(str(material))
            for arm,prompt in [('control',control),('identity_attributes',treatment)]:
                (d/(arm+'-prompt.txt')).write_text(prompt)
            jobs.append(dict(name=old['name'],report_index=report_index,claims=claims,
                material_sha256=hashlib.sha256(str(material).encode()).hexdigest(),
                prompt_hashes={arm:hashlib.sha256(prompt.encode()).hexdigest() for arm,prompt in [('control',control),('identity_attributes',treatment)]},
                only_appended_identity_instructions=False,
                candidate_changes=['literal sentence/citation annotations in unchanged parent claims',
                                   'explicit identity attribute instructions'],
                annotated_claims=annotated_claims))
    freeze={str(path):sha(path) for path in inputs}
    root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    protocol=dict(scope='Matched native comprehension diagnostic, no full report edits or independent correction/retention/new-error verdict',
        jobs=jobs,model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        order='alternate arm order per job; each invoke receives no conversation history',quality_claim=None)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(jobs=len(jobs),planned_calls=2*len(jobs))));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()});snap.update({
        'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':6000,
        'llm.request_timeout':120,'llm.max_retries':1})
    calls=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snap.get(k,d))})()):
        model=get_llm(settings_snapshot=snap)
        for i,job in enumerate(jobs):
            arms=['control','identity_attributes'] if i%2==0 else ['identity_attributes','control']
            d=a.out_dir/job['name']
            for arm in arms:
                prompt=(d/(arm+'-prompt.txt')).read_text();assert hashlib.sha256(prompt.encode()).hexdigest()==job['prompt_hashes'][arm]
                entry=dict(name=job['name'],arm=arm)
                try:
                    raw=model.invoke(prompt);raw=str(getattr(raw,'content',raw));(d/(arm+'-response.txt')).write_text(raw)
                    issues,checked=parse_review(raw,job['claims'],include_checked=True)
                    entry.update(status='parsed',issues=issues,checked=checked,response_sha256=hashlib.sha256(raw.encode()).hexdigest())
                except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__,error=str(exc)[:200])
                calls.append(entry);(a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'completion.json').write_text(json.dumps(dict(calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls),
        frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None),indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls))))


if __name__=='__main__':main()
