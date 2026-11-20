"""Separate faithful claim translation from entailment on exposed groups.

No report changes, source retrieval or independent correctness scoring.
"""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.claim_language import translation_prompt,parse_translations
from research_verify.evidence_flow import literal_assertion_spans,parse_review
from research_verify.source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


PRESENTATION_NOTE='These units are a diagnostic presentation of report assertions. Their presentation language does not change the original report language or establish article language/eligibility. Assess factual meaning against the supplied sources; no report is being rewritten.'


def main():
    p=argparse.ArgumentParser();p.add_argument('--before-attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    assert json.loads((a.before_attempt/'completion.json').read_text())['frozen_inputs_unchanged'] is True
    a.out_dir.mkdir(parents=True,exist_ok=False);prior=json.loads((a.before_attempt/'plan.json').read_text())
    inputs=[Path(__file__),*Path('local_deep_research/research_verify').glob('*.py'),a.before_attempt/'plan.json',a.before_attempt/'completion.json'];jobs=[]
    for job in prior['jobs']:
        path=a.before_attempt/job['name']/'native-prompt.txt';inputs.append(path);base=path.read_text();assert sha(path)==job['native_prompt_sha256']
        claims={int(k):v for k,v in job['claims'].items()};folder=a.out_dir/job['name'];folder.mkdir()
        (folder/'translation-prompt.txt').write_text(translation_prompt(claims));(folder/'base-native-prompt.txt').write_text(base)
        jobs.append(dict(name=job['name'],claims=claims,base=base,folder=folder))
    root=Path.cwd();freeze={str(p):sha(p) for p in inputs}
    for path in inputs:
        rel=path.relative_to(root) if path.is_absolute() else path
        if str(rel).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    protocol=dict(scope='Two exposed historical groups: translation/comprehension diagnosis, not semantic fidelity gold or report correction',
        jobs=[dict(name=j['name'],claims=j['claims']) for j in jobs],planned_calls=6,model='deepseek-v4-flash',temperature=0,max_tokens=6000,
        comparison='Original versus source-blind English-rendered claim text/spans; source text, IDs, context and common concept/presentation instructions unchanged',
        report_changes=False,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(dict(planned_calls=6)));return
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
            index=len(calls);entry=dict(call_id=index,job=folder.name,stage=stage,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest());calls.append(entry)
            (folder/f'call-{index:03d}-prompt.txt').write_text(prompt)
            try:
                response=model.invoke(prompt);text=str(getattr(response,'content',response));(folder/f'call-{index:03d}-response.txt').write_text(text)
                entry.update(status='returned',response_sha256=hashlib.sha256(text.encode()).hexdigest());return text
            except Exception as exc:entry.update(status='unavailable',error_type=type(exc).__name__);raise
            finally:(a.out_dir/'calls.json').write_text(json.dumps(calls,indent=2)+'\n')
        for n,j in enumerate(jobs):
            try:translated=parse_translations(invoke(translation_prompt(j['claims']),j['folder'],'translation'),j['claims'])
            except Exception as exc:results.append(dict(job=j['name'],status='translation_unavailable',error_type=type(exc).__name__));continue
            (j['folder']/'translations.json').write_text(json.dumps(translated,ensure_ascii=False,indent=2)+'\n')
            prefix,tail=j['base'].split('\nFINAL ANSWER:\n',1);payload,suffix=tail.split('\n\nSUPPLIED SOURCES:',1)
            original=json.loads(payload);english=[{**c,'text':translated[c['claim_id']]['text'],
                'literal_assertion_spans':literal_assertion_spans(translated[c['claim_id']]['text'])} for c in original]
            prompts=dict(original=j['base'],english=prefix+'\nFINAL ANSWER:\n'+json.dumps(english,ensure_ascii=False)+'\n\nSUPPLIED SOURCES:'+suffix)
            for arm in (['original','english'] if n%2==0 else ['english','original']):
                prompt=prompts[arm]+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS+'\n\n'+PRESENTATION_NOTE
                assert prompt.split('\n\nSUPPLIED SOURCES:',1)[1]==(j['base']+'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS+'\n\n'+PRESENTATION_NOTE).split('\n\nSUPPLIED SOURCES:',1)[1]
                row=dict(job=j['name'],arm=arm)
                try:
                    if len(prompt)>60000:raise ValueError('Prompt exceeds budget')
                    raw=invoke(prompt,j['folder'],arm+'_native_check')
                    check_claims=j['claims'] if arm=='original' else {k:{**c,'text':translated[k]['text']} for k,c in j['claims'].items()}
                    issues,checked=parse_review(raw,check_claims,include_checked=True);row.update(status='parsed',issues=issues,checked=checked)
                except Exception as exc:row.update(status='unavailable',error_type=type(exc).__name__)
                results.append(row);(a.out_dir/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'completion.json').write_text(json.dumps(dict(calls=len(calls),results=results,
        frozen_inputs_unchanged=all(sha(Path(p))==h for p,h in freeze.items()),quality_claim=None,newly_credited_corrections=0),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=len(calls),results=len(results))))


if __name__=='__main__':main()
