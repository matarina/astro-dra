"""Matched post-writer native review; no writer, live search, or publication.

Both arms start from the same archived report and newly acquired source pack.
Only existing native semantic confirmation can revise the experimental copy.
Outputs require independent source/retention/new-error review before scoring.
"""
import argparse
import ast
import copy
from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path

from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from research_verify.evidence_flow import review_answer, review_claim_groups
from research_verify import evidence_flow
from research_verify.claims import extract_report_claims


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class Trace:
    def __init__(self,path):self.path=path;self.events=[]
    def record(self,stage,data):
        row=dict(stage=stage,data=data);self.events.append(row)
        with self.path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')


class FixedSources:
    """Keep source scope identical and explicitly log unmet supplement requests."""
    def __init__(self):self.events=[]
    def article(self,source):
        self.events.append(dict(kind='article',source_id=source.get('index'),status='fixed_source_unavailable'))
        return None
    def web(self,query,domain='',url=''):
        self.events.append(dict(kind='web',query=query,domain=domain,url=url,status='live_search_disabled'))
        return []


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--baseline-review-units-code',type=Path,
                   help='Frozen previous review_units code; compare boundaries with identity checking ON in both arms')
    p.add_argument('--attribute-confirmation',action='store_true',
                   help='Compare confirmation instructions only; same identity first-check and units in both arms')
    a=p.parse_args();cases=_manifest_cases(a.case_manifest)
    if a.attribute_confirmation and a.baseline_review_units_code:raise ValueError('Choose one candidate mechanism')
    if len(cases)!=1 or cases[0]['draft'] is None:raise ValueError('Exactly one original report case required')
    case=cases[0];a.out_dir.mkdir(parents=True,exist_ok=False)
    report=case['draft'].read_text();sources=json.loads(case['source'].read_text())
    if not isinstance(sources,list):raise ValueError('Expected original-namespace source list')
    groups=review_claim_groups(report,native_documents(copy.deepcopy(sources)),sources,case['query'],60000)
    current_units=evidence_flow.review_units;baseline_units=current_units
    if a.baseline_review_units_code:
        tree=ast.parse(a.baseline_review_units_code.read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='review_units')
        scope=dict(re=re,replace=replace,extract_report_claims=extract_report_claims)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(a.baseline_review_units_code),'exec'),scope)
        baseline_units=scope['review_units']
    try:
        evidence_flow.review_units=baseline_units
        baseline_groups=review_claim_groups(report,native_documents(copy.deepcopy(sources)),sources,case['query'],60000)
    finally:evidence_flow.review_units=current_units
    files=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
           Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
           Path('local_deep_research/overlay/base_citation_handler.py'),
           *Path('local_deep_research/research_verify').glob('*.py'),a.case_manifest,case['source'],case['draft']]
    if a.baseline_review_units_code:files.append(a.baseline_review_units_code)
    frozen={str(f):sha(f) for f in files}
    root=Path.cwd()
    for f in files:
        rel=f.relative_to(root) if f.is_absolute() else f
        if str(rel).startswith(('scripts/','local_deep_research/')):
            target=a.out_dir/'code'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'original-report.txt').write_text(report)
    protocol=dict(scope='Matched post-writer native semantic check of one unchanged original report; not writer generation or full objective validation',
        case_id=case['case_id'],query=case['query'],query_sha256=case['query_sha256'],report_sha256=sha(case['draft']),
        source_pack_sha256=sha(case['source']),manifest_sha256=sha(a.case_manifest),source_count=len(sources),
        source_scope='Newly acquired original-namespace metadata/abstracts, not historical production writer material',
        native_groups=len(groups),groups=groups,baseline_groups=baseline_groups,
        arms=['baseline','attribute_confirmation' if a.attribute_confirmation else ('unit_boundaries' if a.baseline_review_units_code else 'identity_attributes')],
        comparison='attribute_confirmation' if a.attribute_confirmation else ('review_unit_boundaries' if a.baseline_review_units_code else 'identity_attributes'),
        candidate_delta=('Only review-unit serialization boundaries; identity checking ON in both arms, same source pool and native code otherwise'
                         if a.baseline_review_units_code else ('Only appended confirmation attribute instructions; first-check identity and unit preparation identical'
                         if a.attribute_confirmation else 'Identity attribute instructions plus literal assertion/citation annotations; same shared parser and author transport')),
        model='deepseek-v4-flash',temperature=0,max_tokens=6000,native_call_budget_per_arm=16,source_context_chars=60000,
        live_search=False,writer_generation=False,save_time_citation_qc=False,
        report_revision='Existing native semantic quote/location eligibility and separate confirmation only; no new application rules',
        independent_correction_retention_new_error_review='required, not performed by this runner',quality_claim=None)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(groups=len(groups),model_calls=0)));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})
    snap.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,
                 'llm.max_tokens':6000,'llm.request_timeout':120,'llm.max_retries':1})
    summaries=[]
    for arm in protocol['arms']:
        evidence_flow.review_units=baseline_units if arm=='baseline' else current_units
        folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl');calls=[]
        arm_sources=copy.deepcopy(sources);fetcher=FixedSources()
        class Handler:
            settings_snapshot={**snap,'citation.identity_attribute_review':bool(a.baseline_review_units_code) or a.attribute_confirmation or arm=='identity_attributes',
                               'citation.attribute_confirmation_review':arm=='attribute_confirmation'}
            def get_setting(self,key,default=None):return self.settings_snapshot.get(key,default)
            def _create_documents(self,sources):return native_documents(sources)
            def _invoke_text(self,prompt,**kwargs):
                call_id=len(calls);entry=dict(call_id=call_id,stage=kwargs.get('stage'),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
                (folder/f'call-{call_id:03d}-prompt.txt').write_text(prompt)
                try:
                    raw=self.model.invoke(prompt);text=str(getattr(raw,'content',raw))
                    (folder/f'call-{call_id:03d}-response.txt').write_text(text)
                    entry.update(status='returned',response_sha256=hashlib.sha256(text.encode()).hexdigest())
                    return text
                except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__);raise
                finally:
                    calls.append(entry);(folder/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        handler=Handler();budget=dict(remaining=protocol['native_call_budget_per_arm'])
        with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(handler.get_setting)})()):
            handler.model=get_llm(settings_snapshot=handler.settings_snapshot)
            try:
                revised,docs,applied,unresolved,shown=review_answer(handler,case['query'],report,
                    native_documents(arm_sources),arm_sources,trace,None,1,60000,dict(fetcher=fetcher),budget)
            finally:evidence_flow.review_units=current_units
        (folder/'report.txt').write_text(revised)
        result=dict(arm=arm,report_sha256=sha(folder/'report.txt'),original_report_sha256=protocol['report_sha256'],
            original_chars=len(report),report_chars=len(revised),model_calls=len(calls),remaining_native_calls=budget['remaining'],
            native_applied=applied,native_unresolved=unresolved,shown_source_ids=sorted(shown),
            supplement_requests=fetcher.events,quality_claim=None,newly_credited_corrections=0)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');summaries.append(result)
    completion=dict(arms=summaries,frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in frozen.items()),
                    quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(arms=len(summaries),model_calls=sum(r['model_calls'] for r in summaries),
                         frozen_inputs_unchanged=completion['frozen_inputs_unchanged'],newly_credited_corrections=0)))


if __name__=='__main__':main()
