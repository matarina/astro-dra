"""Installed evidence-flow validation with fixtures supplied through CONFIG.

Normal mode performs real selection/writing/review. Saved-writer mode supplies
a frozen prior answer and exercises real post-writing review/confirmation.
No live research tools, user accounts, or report database are opened.
"""
import copy
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import time


def main(config):
    from loguru import logger
    logger.remove()
    import local_deep_research
    from langchain_core.messages import AIMessage
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import SearchResultsCollector
    from research_verify.synthesis_trace import trace_context
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    from research_verify.evidence_fetch import EvidenceFetcher

    os.umask(0o077)
    output=Path('/tmp/evidence-flow-validation');output.mkdir(mode=0o700)
    os.environ.update(config['environment'])
    os.environ['LDR_RESEARCH_TRACE_ENABLED']='true'
    os.environ['LDR_RESEARCH_TRACE_DIR']=str(output/'traces')
    os.environ['LDR_DATA_DIR']=str(output/'data')
    defaults=json.loads((Path(local_deep_research.__file__).parent/'defaults/default_settings.json').read_text())
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})
    snapshot.update({'llm.request_timeout':120,'llm.max_retries':0})
    context=SimpleNamespace(username=None,get_setting=lambda key,default=None:snapshot.get(key,default))
    with settings_context(context):
        model=get_llm(settings_snapshot=snapshot)
        if config.get('primary_document_probe'):
            probe=config['primary_document_probe']
            fetch=EvidenceFetcher(snapshot,seconds=20,requests=4)
            try:
                records=fetch.web(probe['query'],probe.get('domain',''),probe.get('url',''))
                probe_result={'records':len(records),'events':fetch.events}
                (output/'primary-document-records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
            except Exception as exc:
                probe_result={'error_type':type(exc).__name__,'events':fetch.events}
            (output/'primary-document-probe.json').write_text(json.dumps(probe_result,indent=2))
            print(json.dumps({'primary_document_probe':probe_result}),flush=True)
        summaries=[]
        for mode in config.get('modes',['normal','saved_writer']):
            started=time.monotonic()
            task='diagnostic-flow-'+mode.replace('_','-')+'-'+uuid4().hex
            collector=SearchResultsCollector([],max_results=500)
            sources=copy.deepcopy(config['sources'])
            collector._all_links.extend(sources)
            collector._results.extend(sources)
            for source in sources:
                for key in collector._identity_keys(source):collector._identity_map[key]=source
            class Counted:
                real_calls=0
                simulated_writer=False
                def invoke(self,prompt):
                    if mode=='saved_writer' and not self.simulated_writer and 'Previous Knowledge:' in prompt:
                        self.simulated_writer=True
                        return AIMessage(content=config['saved_writer'])
                    self.real_calls+=1
                    return model.invoke(prompt)
            counted=Counted()
            handler=StandardCitationHandler(counted,snapshot)
            handler.source_registrar=collector.find_or_add_result
            with trace_context(task):
                result=handler.analyze_followup(config['question'],sources,config['draft'],0)
                publication=publish_report(result['content'],sources,cfg=VerifyConfig(enable_citation_qc=False))
            artifacts={}
            for p in (output/'traces'/task).rglob('*.json.gz'):
                stage=p.name.split('-',1)[1][:-8]
                artifacts.setdefault(stage,[]).append(json.loads(gzip.decompress(p.read_bytes())))
            # The review must contain the actual answer, never only the Agent draft.
            assert artifacts.get('native_check_request') and artifacts.get('final_response')
            for writer in artifacts['writer_response']:
                assert any(writer['text_sha256']==s['text_sha256'] for s in artifacts['review_snapshot'])
                assert any(writer['text_sha256']==r['report_text_sha256'] for r in artifacts['native_check_request'])
            required=set()
            shown=set()
            for item in artifacts['evidence_plan']:required.update(item['required_ids'])
            for item in artifacts['writer_sources']:shown.update(item['source_ids'])
            known={int(s['index']) for s in sources}
            assert required & known <= shown
            assert artifacts['final_response'][0]['text']==result['content']
            assert artifacts['publication_input'][0]['text']==result['content']
            summary={'mode':mode,'research_id':task,'model':snapshot['llm.model'],
                'real_model_calls':counted.real_calls,'elapsed_s':round(time.monotonic()-started,3),
                'required_sources':len(required),'shown_sources':len(shown),
                'parts':len(artifacts['writer_sources']),
                'review_status':result['evidence_review']['status'],
                'applied_repairs':sum(len(r['applied']) for r in artifacts.get('grounded_repairs',[])),
                'unresolved_issues':sum(len(r['unresolved']) for r in artifacts.get('grounded_repairs',[])),
                'version_records':len(artifacts.get('publication_version',[])),
                'linked_publications':[{'index':s['index'],'pmid':s.get('pmid'),'doi':s.get('doi')}
                    for s in sources if s.get('pmid') in config.get('expected_publication_pmids',[])],
                'invalid_reviews':len(artifacts.get('native_check_invalid',[])),
                'material_contract_passed':True}
            (output/(mode+'-report.md')).write_text(publication.content)
            (output/(mode+'-body.md')).write_text(result['content'])
            (output/(mode+'-sources.json')).write_text(json.dumps(sources,ensure_ascii=False,indent=2))
            summaries.append(summary)
            (output/'summary.json').write_text(json.dumps({'results':summaries},indent=2))
            print(json.dumps(summary),flush=True)
    return output


if __name__=='__main__':
    main(CONFIG)
