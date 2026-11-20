"""Isolated native-writer pilot with frozen sources; no production data or search.

Run only inside a disposable image after overlays are installed. Configuration
comes from a frozen JSON; endpoint secrets stay in the container environment.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace


def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handler import CitationHandler
    import local_deep_research
    from research_verify.synthesis_trace import trace_context
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    class FrozenEvidence:
        def record(self, *args, **kwargs): return None
        def pmc_identifiers(self, *args, **kwargs): return {}
        def article(self, *args, **kwargs): return ''
        def web(self, *args, **kwargs): return []
    root=Path('/experiment');config=json.loads((root/'experiment.json').read_text())
    sources=json.loads((root/'sources.json').read_text())
    arm=os.environ['PILOT_ARM'];out=root/arm;out.mkdir(exist_ok=True)
    os.environ['LDR_DATA_DIR']=str(out/'data')
    os.environ['LDR_RESEARCH_TRACE_ENABLED']='true';os.environ['LDR_RESEARCH_TRACE_DIR']=str(out/'traces')
    defaults=Path(local_deep_research.__file__).parent/'defaults/default_settings.json'
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in json.loads(defaults.read_text()).items()})
    snapshot.update(config['settings'])
    # Secret-bearing connection configuration is intentionally excluded.
    public={k:snapshot.get(k) for k in config['record_setting_keys']}
    setting_hash=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    (out/'settings.json').write_text(json.dumps(public,indent=2))
    with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:snapshot.get(k,d))):
        model=get_llm(settings_snapshot=snapshot)
        for case in config['cases']:
            target=out/(case['case_id']+'.json')
            if target.exists():continue
            started=time.monotonic()
            row={**case,'model':snapshot['llm.model'],'temperature':snapshot.get('llm.temperature'),'settings_sha256':setting_hash,'source_pack_sha256':config['source_pack_sha256'],'system':arm}
            try:
                handler=CitationHandler(model,handler_type='standard',settings_snapshot=snapshot)
                # Adapter exposes the underlying native handler. Both arms
                # use the same closed evidence pool, with native checks on.
                target_handler=getattr(handler,'_handler',handler)
                target_handler.evidence_fetcher=FrozenEvidence()
                with trace_context('pilot-'+arm+'-'+case['case_id']):
                    result=handler.analyze_followup(case['query'],copy.deepcopy(sources),'',0)
                    body=result.get('content') or result.get('response') or ''
                    pub=publish_report(body,sources,cfg=VerifyConfig(enable_citation_qc=False))
                row.update(status='completed',body=body,publication=pub.metadata(),claims=[],assessment_status='not_annotated')
            except Exception as exc:
                row.update(status='failed',error_type=type(exc).__name__,claims=[])
            row['latency_seconds']=round(time.monotonic()-started,3)
            target.write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str))
            print(json.dumps({k:row.get(k) for k in ('case_id','system','status','error_type','latency_seconds')}),flush=True)


if __name__=='__main__':main()
