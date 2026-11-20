"""Bounded source-only reading/comparison on two exposed historical groups.

Not held-out validation or complete report checking. Uses the existing native
parser/semantic confirmation and preserves complete experimental report copies.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from research_verify.evidence_flow import (_review_material,required_sources,document_structure_spans,
    visible_texts,visible_headers,parse_review,confirm_repairs)
from research_verify.independent_verification import SourcePassage,VerificationAnswer
from research_verify.source_fact_review import (source_fact_prompt,parse_source_facts,comparison_notes,
    CONCEPT_COMPARISON_INSTRUCTIONS)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--execute',action='store_true');a=ap.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113');jobs=[]
    inputs=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
        Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    specs=[('neuropathy','native-attribute-confirmation-neuropathy-pair-20261114-v1','baseline','native-original-neuropathy-inputs-20261114-v1'),
           ('xenium','native-unit-boundary-xenium-pair-20261114-v1','unit_boundaries','native-original-xenium-inputs-20261114-v1')]
    for name,prior_name,prior_arm,manifest_dir in specs:
        prior=base/prior_name/'attempt';manifest=base/manifest_dir/'case-manifest.json'
        case=json.loads(manifest.read_text())['cases'][0];sources=json.loads(Path(case['source']).read_text());report=Path(case['draft']).read_text()
        assert sha(Path(case['source']))==case['source_sha256'] and sha(Path(case['draft']))==case['draft_sha256']
        plan=json.loads((prior/'plan.json').read_text());claims={int(k):v for k,v in plan['groups'][1].items()}
        section='\n'.join(c['text'] for c in claims.values());reserve=min(8000,len(json.dumps(document_structure_spans(report),ensure_ascii=False)))
        docs=native_documents(sources);material,_=_review_material(docs,case['query']+'\n'+section,claims,required_sources(section,sources),max(2000,60000-reserve))
        trace_path=prior/prior_arm/'trace.jsonl';calls_path=prior/prior_arm/'calls.json'
        requests=[json.loads(l)['data'] for l in trace_path.read_text().splitlines() if json.loads(l)['stage']=='native_check_request']
        calls=[c for c in json.loads(calls_path.read_text()) if c['stage']=='native_check'];n=next(i for i,r in enumerate(requests) if r['review_group']==2)
        prompt_path=prior/prior_arm/f"call-{calls[n]['call_id']:03d}-prompt.txt";prompt=prompt_path.read_text();assert sha(prompt_path)==calls[n]['prompt_sha256']
        assert prompt.split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]==str(material)
        texts=visible_texts(material);headers=visible_headers(material);titles={int(d.metadata['index']):d.metadata.get('title','') for d in docs}
        passages=[SourcePassage(source_id=i,title=titles.get(i,''),text=headers.get(i,'')+'\n'+texts.get(i,''),
            field='supplied_view',basis='supplied_metadata_and_source_text',scope_note='Same view as native check; not necessarily full paper') for i in sorted(set(texts)|set(headers))]
        batches=[passages[i:i+3] for i in range(0,len(passages),3)]
        folder=a.out_dir/name;folder.mkdir();(folder/'original-report.txt').write_text(report);(folder/'native-prompt.txt').write_text(prompt)
        for i,batch in enumerate(batches):(folder/f'reader-{i:02d}-prompt.txt').write_text(source_fact_prompt(batch,case['query']))
        jobs.append(dict(name=name,query=case['query'],report=report,claims=claims,material=material,prompt=prompt,batches=batches,folder=folder))
        inputs.extend([manifest,Path(case['source']),Path(case['draft']),prior/'plan.json',trace_path,calls_path,prompt_path])
    frozen={str(p):sha(p) for p in inputs};root=Path.cwd()
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    protocol=dict(scope='Two pre-exposed historical groups; not full report coverage or semantic generalization',
        jobs=[dict(name=j['name'],claims=j['claims'],source_ids=[p.source_id for b in j['batches'] for p in b],reader_batches=len(j['batches']),
            original_report_sha256=hashlib.sha256(j['report'].encode()).hexdigest(),native_prompt_sha256=hashlib.sha256(j['prompt'].encode()).hexdigest()) for j in jobs],
        arms=['native','concept_instruction','source_notes'],model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        planned_reader_calls=sum(len(j['batches']) for j in jobs),planned_native_calls=6,maximum_confirmation_calls=6,
        changes=dict(concept_instruction='Append only generic concept/relation comparison instructions',
            source_notes='Same concept instructions plus fallible source-only notes; original source view unchanged'),
        semantic_confirmation='Same existing approval conditions and attribute confirmation ON in every arm',quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(protocol,ensure_ascii=False));return
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
            i=len(calls);entry=dict(call_id=i,job=folder.name,stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{i:03d}-prompt.txt').write_text(prompt)
            try:
                raw=model.invoke(prompt);text=str(getattr(raw,'content',raw));(folder/f'call-{i:03d}-response.txt').write_text(text)
                entry.update(status='returned',response_sha256=hashlib.sha256(text.encode()).hexdigest());return text
            except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__);raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        for job_no,j in enumerate(jobs):
            answers=[]
            for i,batch in enumerate(j['batches']):
                try:answers.extend(parse_source_facts(invoke(source_fact_prompt(batch,j['query']),j['folder'],'source_facts'),batch,j['query']))
                except Exception as exc:answers.extend(VerificationAnswer(question_id=f'source-facts-{p.source_id}',status='unknown',unknowns=(type(exc).__name__,)) for p in batch)
            (j['folder']/'reader-answers.json').write_text(json.dumps([asdict(x) for x in answers],ensure_ascii=False,indent=2)+'\n')
            notes=comparison_notes(answers)
            for arm in (protocol['arms'] if job_no%2==0 else list(reversed(protocol['arms']))):
                folder=j['folder']/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
                prompt=j['prompt']+ ('\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS if arm!='native' else '')
                if arm=='source_notes':prompt+='\n\n'+notes
                result=dict(job=j['name'],arm=arm,quality_claim=None,newly_credited_corrections=0)
                revised=j['report'];applied=[];unresolved=[]
                try:
                    if len(prompt)>60000:raise ValueError('Diagnostic native prompt exceeds declared budget')
                    raw=invoke(prompt,folder,'native_check');issues,checked=parse_review(raw,j['claims'],include_checked=True)
                    handler=type('Handler',(),{'get_setting':staticmethod(lambda key,default=None:True if key=='citation.attribute_confirmation_review' else default),
                        '_invoke_text':staticmethod(lambda prompt,**kw:invoke(prompt,folder,'repair_validation'))})()
                    revised,applied,unresolved=confirm_repairs(handler,revised,issues,j['material'],j['query'],trace)
                    result.update(status='parsed',issues=issues,checked=checked)
                except Exception as exc:result.update(status='unavailable',error_type=type(exc).__name__)
                (folder/'report.txt').write_text(revised);result.update(native_applied=applied,native_unresolved=unresolved,report_sha256=sha(folder/'report.txt'),report_chars=len(revised))
                (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');results.append(result)
    completion=dict(calls=len(calls),results=results,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(calls=len(calls),frozen_inputs_unchanged=completion['frozen_inputs_unchanged'])))


if __name__=='__main__':main()
