"""Replay saved review responses through current local-repair validation.

CONFIG is supplied on stdin by the caller. This does not rerun the writer,
review model or search. Only independent repair confirmations call the real API.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace


def main(config):
    from loguru import logger
    logger.remove()
    os.umask(0o077)
    os.environ.update(config['environment'])
    import local_deep_research
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.evidence_flow import parse_review, version_candidates, confirm_repairs
    from research_verify.synthesis_trace import text_digest

    defaults=Path(local_deep_research.__file__).parent/'defaults/default_settings.json'
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in json.loads(defaults.read_text()).items()})
    snapshot.update({'llm.request_timeout':90,'llm.max_retries':0})
    output=Path('/tmp/evidence-repair-replay');output.mkdir(mode=0o700)
    summaries=[]
    with settings_context(SimpleNamespace(username=None,get_setting=lambda key,default=None:snapshot.get(key,default))):
        model=get_llm(settings_snapshot=snapshot)
        for run in config['runs']:
            events=[]
            class Trace:
                def record(self,stage,payload):events.append({'stage':stage,**payload})
            class Counted:
                calls=0
                def invoke(self,prompt):
                    if self.calls>=32:raise TimeoutError('Confirmation replay call budget exhausted')
                    self.calls+=1
                    return model.invoke(prompt)
            counted=Counted();handler=StandardCitationHandler(counted,snapshot)
            body=run['body'];applied=[];unresolved=[]
            for saved in run['reviews']:
                prompt=saved['request']['prompt']
                claims={c['claim_id']:c for c in json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\nSUPPLIED SOURCES:',1)[0])}
                material=prompt.split('\nSUPPLIED SOURCES:\n',1)[1]
                issues=parse_review(saved['response'],claims)
                versions=version_candidates(claims,run['sources'],material)
                issues.extend(v for v in versions if not any(i.get('statement')==v['statement']
                    and i.get('status')=='version_update' for i in issues))
                body,fixes,pending=confirm_repairs(handler,body,issues,material,run['question'],Trace())
                applied.extend(fixes);unresolved.extend(pending)
            summary={'mode':run['mode'],'real_confirmation_calls':counted.calls,'applied':len(applied),
                'unresolved':len(unresolved),'input_sha256':text_digest(run['body']),
                'output_sha256':text_digest(body),'scope':'Frozen review responses; real independent confirmations only'}
            result={'summary':summary,'applied':applied,'unresolved':unresolved,'events':events}
            (output/(run['mode']+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            (output/(run['mode']+'-body.md')).write_text(body)
            summaries.append(summary)
            (output/'summary.json').write_text(json.dumps(summaries,indent=2))
            print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main(CONFIG)
