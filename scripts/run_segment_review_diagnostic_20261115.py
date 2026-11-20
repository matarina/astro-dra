"""Three saved-case segment reviews; no writer, repair, retrieval or publication."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from research_verify.segment_review import review_prompt, parse_review, segments
from research_verify.claims import extract_report_claims


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    base = Path('evaluation/frontier-strategy-20261113')
    rna = Path('evaluation/archive-prompt-reviewed-20261112/results/reviewed-20261112-archive-41d13d68b84e')
    paths = [Path(__file__).resolve().relative_to(Path.cwd().resolve()), Path('local_deep_research/research_verify/segment_review.py'),
             Path('local_deep_research/research_verify/claims.py'),
             Path('local_deep_research/research_verify/report_syntax.py'),
             rna/'manifest.json',
             base/'review-source-query-engineering-packet-20261115-v1/diagnosis.json',
             base/'complete-draft-pair-model-20261115-v1/attempt/inherited/report.txt']
    request_path = next(rna.rglob('0035-native_check_request.json.gz'))
    response_path = next(rna.rglob('0036-native_check_response.json.gz'))
    writer_path = next(rna.rglob('0032-writer_response.json.gz'))
    paths += [request_path,response_path,writer_path]
    load_gz = lambda path: json.loads(gzip.decompress(path.read_bytes()))
    req = load_gz(request_path)
    writer = load_gz(writer_path)['text_used']
    # Preserve the actual entire writer paragraph, including final citation scope.
    paragraphs = writer.split('\n\n')
    text = next(t for t in paragraphs if '若该峰确为低水平的细菌等外源RNA污染' in t)
    evidence = req['prompt'].split('SUPPLIED SOURCES:\n',1)[1]
    diagnosis = json.loads(paths[5].read_text())
    x = diagnosis['incomplete_attribute_control']
    report = paths[6].read_text()
    positive = next(c.text for c in extract_report_claims(report) if '248' in c.text and 'C57BL' in c.text)
    cases = [dict(case_id='s0',question=json.loads((rna/'manifest.json').read_text())['query'],
                  parent=text,evidence=evidence,source_scope='Exact whole native first-check supplied material; paragraph from actual Writer'),
             dict(case_id='s1',question='10X Xenium发表了哪些文献？',parent=x['claim']['text'],
                  evidence='[2]\n'+x['source2_supplied_text']+'\n[9]\n'+x['source9_supplied_text'],
                  source_scope='Exact source2/9 abstract text from prior paired diagnosis; duplicate IDs remain distinct'),
             dict(case_id='s2',question='10X Xenium发表了哪些文献？',parent=positive,
                  evidence='[1]\n'+diagnosis['positive_control']['actual_primary_paragraph'],
                  source_scope='Known correct-detail retention control, exact Methods paragraph; not new heldout material')]
    freeze = {str(path):sha(path) for path in paths}
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in paths[:4]:
        dest = a.out_dir/'code'/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(path.read_bytes())
    settings = {'llm.model':'deepseek-v4-flash','llm.provider':'openai_endpoint',
                'llm.temperature':0,'llm.max_tokens':6000,'llm.max_retries':0,'llm.request_timeout':180,
                'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
    plan = dict(scope='Three source-scope mechanism diagnostics, NOT complete-report matched outcome evaluation or an algorithm-quality pair',
                cases=cases, settings=settings,maximum_model_calls=3,maximum_prompt_chars=60000,
                expected_semantic_labels=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    prompts = [review_prompt(c['question'],c['parent'],c['evidence']) for c in cases]
    for c,prompt in zip(cases,prompts):
        assert len(prompt)<=60000
        (a.out_dir/(c['case_id']+'-prompt.txt')).write_text(prompt)
    model=None
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        from local_deep_research.config.thread_settings import settings_context
        from local_deep_research.config.llm_config import get_llm
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
        effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):
            model=get_llm(settings_snapshot=effective)
    results=[]
    for case,prompt in zip(cases,prompts):
        row=dict(case_id=case['case_id'],prompt_sha256=sha(a.out_dir/(case['case_id']+'-prompt.txt')),
                 segment_count=len(segments(case['parent'])))
        if model is not None:
            try:
                response=model.invoke(prompt)
                raw=str(getattr(response,'content',response))
                path=a.out_dir/(case['case_id']+'-response.txt');path.write_text(raw)
                row.update(execution='returned',response_sha256=sha(path),metadata=getattr(response,'response_metadata',{}))
                try:row['parsed']=parse_review(raw,case['parent'],case['evidence'])
                except(ValueError,TypeError,KeyError)as exc:row.update(parse_status='unavailable',parse_error=type(exc).__name__)
            except Exception as exc:
                # Never serialize request headers, endpoint URLs or exception bodies.
                row.update(execution='unavailable',error_type=type(exc).__name__)
        else:row['execution']='preflight_no_model'
        results.append(row)
        (a.out_dir/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str)+'\n')
    completion=dict(model_requests=len(cases)if a.execute else 0,results=len(results),
                    frozen_inputs_unchanged=all(sha(Path(k))==v for k,v in freeze.items()),
                    network_retrieval_reads=0,report_modifications=0,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,indent=2)+'\n')
    print(json.dumps(completion))


if __name__=='__main__':main()
