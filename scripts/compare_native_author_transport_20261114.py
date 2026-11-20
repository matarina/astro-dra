"""Compare frozen native prompts after author transport repair, no report edits."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from scripts.prepare_source_detail_material_20261114 import native_documents
from research_verify.evidence_flow import _review_material,required_sources,document_structure_spans,review_prompt,parse_review


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--before-dir',type=Path,required=True)
    p.add_argument('--report-index',type=int,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113');plan_path=a.before_dir/'plan.json'
    before=json.loads(plan_path.read_text());assembly_path=base/'archive-identity-sourcepacks-20261114-v3/assembly-audit.json'
    assembly=json.loads(assembly_path.read_text());row=assembly['reports'][a.report_index]
    report_path=Path(row['report_path']);report=report_path.read_text();pack_path=Path(row['source_pack_path'])
    sources=json.loads(pack_path.read_text());docs=native_documents(sources)
    inventory_path=Path('evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json')
    tasks={t['task_id']:t['original_prompt'] for t in json.loads(inventory_path.read_text())['tasks']}
    query=tasks[before['reports'][a.report_index]['task_id']]
    structures=document_structure_spans(report);reserve=min(8000,len(json.dumps(structures,ensure_ascii=False)))
    jobs=[];inputs=[Path(__file__),plan_path,assembly_path,report_path,pack_path,inventory_path,
        Path('scripts/prepare_source_detail_material_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    for old in before['jobs']:
        if old['report_index']!=a.report_index or old['status']!='prepared':continue
        claims={int(k):v for k,v in old['claims'].items()};section='\n'.join(c['text'] for c in claims.values())
        material,prompt_claims=_review_material(docs,query+'\n'+section,claims,required_sources(section,sources),max(2000,60000-reserve))
        context=query+'\nExisting report headings (destinations must use these exact headings):\n'+'\n'.join(re.findall(r'^#{1,6} .+',report,re.M))
        prompt=review_prompt(context,section,material,claims=prompt_claims,structure_spans=structures,prompt_budget=60000)
        prior=a.before_dir/old['name']/'prompt.txt';prior_material=a.before_dir/old['name']/'material.txt';inputs.extend([prior,prior_material])
        old_prompt=prior.read_text();assert 'Authors (supplied metadata): ' not in old_prompt
        remove=lambda value:re.sub(r'(?m)^Authors \(supplied metadata\): [^\n]*\n','',value)
        if remove(prompt)!=old_prompt or remove(str(material))!=prior_material.read_text():
            raise ValueError('Prompt changed beyond added author metadata; refuse a claimed transport-only comparison')
        d=a.out_dir/old['name'];d.mkdir();(d/'prompt.txt').write_text(prompt);(d/'material.txt').write_text(str(material))
        jobs.append(dict(name=old['name'],claims=claims,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            before_prompt_sha256=sha(prior),only_added_author_metadata=True,prompt_chars=len(prompt)))
    freeze={str(p):sha(p) for p in inputs}
    for path in inputs:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'plan.json').write_text(json.dumps(dict(scope='Matched native prompt comparison, author fields only; no independent correction verdict',jobs=jobs),ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(jobs=len(jobs),only_author_metadata_changed=True)));return
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
        for job in jobs:
            d=a.out_dir/job['name'];entry=dict(name=job['name'])
            try:
                raw=model.invoke((d/'prompt.txt').read_text());raw=str(getattr(raw,'content',raw));(d/'response.txt').write_text(raw)
                issues,checked=parse_review(raw,job['claims'],include_checked=True)
                entry.update(status='parsed',issues=issues,checked=checked,response_sha256=hashlib.sha256(raw.encode()).hexdigest())
            except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__,error=str(exc)[:200])
            calls.append(entry);(a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'completion.json').write_text(json.dumps(dict(calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls),
        frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None),indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls))))


if __name__=='__main__':main()
