"""Finite native-prompt diagnostic. No report edits or independent verdicts."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from research_verify.evidence_flow import (
    review_units,review_claim_groups,_review_material,required_sources,
    review_prompt,document_structure_spans,parse_review,
)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113')
    assembly_path=base/'archive-identity-sourcepacks-20261114-v3/assembly-audit.json'
    inventory_path=Path('evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json')
    tasks={t['task_id']:t['original_prompt'] for t in json.loads(inventory_path.read_text())['tasks']}
    # Evaluation linkage of the five archive files, never a production filter.
    task_ids=['task-47c54edcc0eb','task-6e8e8d113e76','task-6ac5d65ed736','task-90ad0dce1609','task-a9b2517baf83']
    extraction_paths=[base/'report-unbound-identity-extraction-20261114-v1/attempt/extraction.json',
        *[base/f'report-identity-extraction-cross-archive-20261114-v1/report-{i:02d}/extraction.json' for i in [1,2,3]],
        base/'report-identity-extraction-model-20261114-v2/attempt/extraction.json']
    reports=json.loads(assembly_path.read_text())['reports'];jobs=[];plans=[]
    inputs=[assembly_path,inventory_path,Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
            Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    for report_index,(row,task_id,extraction_path) in enumerate(zip(reports,task_ids,extraction_paths,strict=True)):
        path=Path(row['report_path']);pack=Path(row['source_pack_path']);inputs.extend([path,pack,extraction_path])
        report=path.read_text();sources=json.loads(pack.read_text());documents=native_documents(sources)
        query=tasks[task_id];units=review_units(report);groups=review_claim_groups(report,documents,sources,query,60000)
        extraction=json.loads(extraction_path.read_text())
        assert extraction['report_sha256']==sha(path) if 'report_sha256' in extraction else True
        observations=[*extraction['mentions'],*[r for r in extraction['unresolved'] if r.get('field_positions')]]
        positions=[(start,end) for m in observations for start,end in m.get('field_positions',{}).values()]
        identity_groups=[i for i,g in enumerate(groups) if any(
            units[cid].report_start<=start<end<=units[cid].report_end for cid in g for start,end in positions)]
        selected=sorted({identity_groups[i] for i in [0,len(identity_groups)//2,len(identity_groups)-1]}) if identity_groups else []
        structures=document_structure_spans(report)
        reserve=min(8000,len(json.dumps(structures,ensure_ascii=False)))
        plan=dict(report_path=str(path),task_id=task_id,report_sha256=sha(path),units=len(units),groups=len(groups),
            identity_detected_groups=identity_groups,selected_group_indices=selected,
            optimistic_identity_groups_in_first_six=[i for i in identity_groups if i<6],
            note='First-six is an optimistic diagnostic bound for six review calls; retries/confirmation can consume calls, and actual configured budgets differ.')
        plans.append(plan)
        for group_index in selected:
            claims=groups[group_index];section='\n'.join(c['text'] for c in claims.values())
            name=f'report-{report_index:02d}-group-{group_index:03d}';d=a.out_dir/name;d.mkdir()
            job=dict(name=name,report_index=report_index,group_index=group_index,claims=claims)
            try:
                material,prompt_claims=_review_material(documents,query+'\n'+section,claims,required_sources(section,sources),max(2000,60000-reserve))
                context=query+'\nExisting report headings (destinations must use these exact headings):\n'+'\n'.join(
                    __import__('re').findall(r'^#{1,6} .+',report,__import__('re').M))
                prompt=review_prompt(context,section,material,claims=prompt_claims,structure_spans=structures,prompt_budget=60000)
                (d/'prompt.txt').write_text(prompt);(d/'material.txt').write_text(str(material))
                job.update(status='prepared',prompt_chars=len(prompt),material_chars=len(material),
                    prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    material_sha256=hashlib.sha256(str(material).encode()).hexdigest(),
                    visible_ids=sorted(getattr(material,'views',{})),prompt_claims=prompt_claims)
            except Exception as exc:job.update(status='material_unavailable',error_type=type(exc).__name__,error=str(exc)[:200])
            (d/'input.json').write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n');jobs.append(job)
    frozen={str(p):sha(p) for p in inputs}
    for path in inputs:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'plan.json').write_text(json.dumps(dict(scope='Native identity-check input exposure and comprehension diagnostic, not correction/adjudication',sampling='First/middle/last native groups containing report-only extracted identity fields; no feedback or expected labels in prompts',reports=plans,jobs=jobs),ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(prepared=len(jobs),unavailable=sum(j['status']!='prepared' for j in jobs))));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})
    snapshot.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,
                     'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    calls=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:snapshot.get(k,d))})()):
        model=get_llm(settings_snapshot=snapshot)
        for job in jobs:
            if job['status']!='prepared':continue
            d=a.out_dir/job['name'];prompt=(d/'prompt.txt').read_text();entry=dict(name=job['name'])
            assert hashlib.sha256(prompt.encode()).hexdigest()==job['prompt_sha256']
            try:
                raw=model.invoke(prompt);raw=str(getattr(raw,'content',raw));(d/'response.txt').write_text(raw)
                claims={int(k):v for k,v in job['claims'].items()};issues,checked=parse_review(raw,claims,include_checked=True)
                entry.update(status='parsed',issues=issues,checked=checked,response_sha256=hashlib.sha256(raw.encode()).hexdigest())
            except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__,error=str(exc)[:200])
            calls.append(entry);(a.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'completion.json').write_text(json.dumps(dict(scope='Same native review prompt/model, diagnostic only; no report edits or independent quality verdict',calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls),frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),quality_claim=None),indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),unavailable=sum(c['status']!='parsed' for c in calls))))


if __name__=='__main__':main()
