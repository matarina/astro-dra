"""Blinded model-assisted annotation; not independent human ground truth."""
import hashlib
import json
import random
import re
import time
import os
from pathlib import Path
from types import SimpleNamespace




def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    import local_deep_research
    root=Path('/experiment');cfg=json.loads((root/'experiment.json').read_text());rubric=(root/'assessment-rubric.txt').read_text()
    defaults=Path(local_deep_research.__file__).parent/'defaults/default_settings.json'
    settings=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in json.loads(defaults.read_text()).items()});settings.update(cfg['settings'])
    queue=[(arm,case['case_id']) for arm in ['baseline','candidate'] for case in cfg['cases']]
    random.Random(20261110).shuffle(queue)
    output=root/'assessment';output.mkdir(exist_ok=True)
    with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:settings.get(k,d))):
        model=get_llm(settings_snapshot=settings)
        for position,(arm,caseid) in enumerate(queue):
            if position % 2 != int(os.environ.get('ASSESS_SHARD','0')): continue
            dest=output/(arm+'-'+caseid+'.json')
            if dest.exists(): continue
            path=root/arm/(caseid+'.json')
            if not path.exists():continue
            row=json.loads(path.read_text())
            if row.get('status')!='completed':continue
            sources=json.loads((root/row['source_pack']).read_text())
            corpus={int(s['index']):s['abstract'] for s in sources}
            prompt=rubric+'\nINPUT DATA:\n'+json.dumps({'question':row['query'],'explicit_report_settings':row['report_settings'],'obligations':row['obligations'],'draft':row['body'],'sources':sources},ensure_ascii=False)
            start=time.monotonic();response=model.invoke(prompt);raw=response.content
            (output/(arm+'-'+caseid+'.response.txt')).write_text(raw)
            try:
                clean=re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip())
                ann=json.loads(clean);assert isinstance(ann.get('claims'),list)
                for claim in ann['claims']:
                    if claim.get('grounding') not in {'supported','partial','unsupported','contradicted','unverifiable'}:raise ValueError('invalid verdict')
                    if not claim.get('text') or claim['text'] not in row['body']:raise ValueError('claim text not in draft')
                    quote_ok=bool(claim.get('evidence')) and all(e.get('quote') and e['quote'] in corpus.get(e.get('source_id'),'') for e in claim.get('evidence',[]))
                    claim['quoted_span_exists']=quote_ok
                    if claim['grounding'] in {'supported','partial','contradicted'} and not quote_ok:
                        claim['assessor_grounding']=claim['grounding'];claim['grounding']='unverifiable'
                    if claim.get('citation_entails') is True:
                        cited=claim.get('citations',[])
                        cited_quote=quote_ok and all(e.get('source_id') in cited for e in claim.get('evidence',[]))
                        if not cited_quote:claim['citation_entails']=None
                ann.update(status='annotated_model_assisted',assessor_model=settings['llm.model'],independence='separate_blinded_request_same_model_family_not_independent_human',rubric_sha256=hashlib.sha256(rubric.encode()).hexdigest(),latency_seconds=time.monotonic()-start)
            except (ValueError,AssertionError,TypeError,KeyError):
                ann={'status':'annotation_invalid','latency_seconds':time.monotonic()-start}
            dest.write_text(json.dumps(ann,ensure_ascii=False,indent=2));print(json.dumps({'case_id':caseid,'annotation_status':ann['status']}),flush=True)


if __name__=='__main__':main()
