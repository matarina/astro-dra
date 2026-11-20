"""One draft-question generation diagnostic; no source reader or report writer."""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.source_questions import inventory,question_prompt,parse_questions
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    case=_manifest_cases(a.case_manifest)[0];report=case['draft'].read_text();claims=inventory(report)
    paths=[Path(__file__).resolve().relative_to(Path.cwd().resolve()),a.case_manifest,case['draft'],case['source'],
           Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
           *Path('local_deep_research/research_verify').glob('*.py')]
    frozen={str(p):sha(p)for p in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (a.out_dir/'inventory.json').write_text(json.dumps(claims,ensure_ascii=False,indent=2)+'\n')
    prompt=question_prompt(case['query'],claims);assert len(prompt)<35000
    (a.out_dir/'prompt.txt').write_text(prompt)
    receipt=dict(scope='One known original report, untrusted draft-derived question feasibility only',
                 query=case['query'],report_sha256=sha(case['draft']),claims=len(claims),
                 maximum_calls=1,max_tokens=8000,temperature=0,max_retries=0,
                 source_evidence_shown=False,report_edits=0,newly_credited_corrections=0)
    if a.execute:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        from local_deep_research.config.thread_settings import settings_context
        from local_deep_research.config.llm_config import get_llm
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
        settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|{'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,'llm.max_retries':0,'llm.request_timeout':180}
        try:
            with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:settings.get(k,d))})()):
                response=get_llm(settings_snapshot=settings).invoke(prompt)
            raw=str(response.content);(a.out_dir/'response.txt').write_text(raw)
            receipt['response_metadata']=response.response_metadata
            parsed=parse_questions(raw,claims);(a.out_dir/'questions.json').write_text(json.dumps(parsed,ensure_ascii=False,indent=2)+'\n')
            receipt.update(status='returned',questions=len(parsed['questions']),unbound=len(parsed['unbound_rows']),missing_claims=parsed['claims_without_questions'])
        except Exception as exc:receipt.update(status='unavailable',failure_type=type(exc).__name__)
    else:receipt['status']='preflight_no_model'
    receipt['frozen_inputs_unchanged']=all(sha(Path(k))==v for k,v in frozen.items())
    (a.out_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
