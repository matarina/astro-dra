"""Run the installed default research pipeline in an isolated diagnostic container.

The caller supplies CONFIG on stdin. No user account or production database is
opened. Source snapshots use the application's normal private trace recorder.
"""
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace


def main(config):
    from loguru import logger
    logger.remove()
    os.umask(0o077)
    os.environ.update(config['environment'])
    output=Path('/tmp/model-research');output.mkdir(mode=0o700)
    os.environ['LDR_DATA_DIR']=str(output/'data')
    os.environ['LDR_RESEARCH_TRACE_ENABLED']='true'
    os.environ['LDR_RESEARCH_TRACE_DIR']=str(output/'traces')
    import local_deep_research
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.search_config import get_search
    from local_deep_research.search_system import AdvancedSearchSystem
    from local_deep_research.web.services.research_service import _extract_synthesized_answer
    from research_verify.synthesis_trace import trace_context,source_snapshot
    from research_verify.publication import publish_report,collect_publication_sources
    from research_verify.config import VerifyConfig

    defaults=Path(local_deep_research.__file__).parent/'defaults/default_settings.json'
    snapshot=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in json.loads(defaults.read_text()).items()})
    snapshot.update(config.get('settings') or {})
    public_keys=['llm.model','llm.provider','llm.temperature','llm.max_tokens','search.tool',
        'search.search_strategy','search.iterations','search.questions_per_iteration',
        'langgraph_agent.max_unique_sources','search.engine.web.pubmed.default_params.get_full_text',
        'general.enable_fact_checking','search.fetch.mode']
    (output/'manifest.json').write_text(json.dumps({'query':config['question'],
        'settings':{k:snapshot.get(k) for k in public_keys},'task_id':config['task_id'],
        'scope':'Fresh full research with installed defaults; programmatic mode, no per-user overrides'},ensure_ascii=False,indent=2))
    started=time.monotonic()
    def progress(message,percent,metadata):
        row={'elapsed_s':round(time.monotonic()-started,3),'percent':percent,
            'phase':metadata.get('phase'),'message':str(message)[:300]}
        with (output/'progress.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        (output/'status.json').write_text(json.dumps(row,ensure_ascii=False))
    system=None
    try:
        with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:snapshot.get(k,d))):
            model=get_llm(settings_snapshot=snapshot)
            search=get_search(search_tool=snapshot['search.tool'],llm_instance=model,
                settings_snapshot=snapshot,programmatic_mode=True)
            system=AdvancedSearchSystem(llm=model,search=search,strategy_name=snapshot['search.search_strategy'],
                max_iterations=snapshot['search.iterations'],questions_per_iteration=snapshot['search.questions_per_iteration'],
                settings_snapshot=snapshot,programmatic_mode=True)
            if 'include_sub_research' in config and hasattr(system.strategy, 'include_sub_research'):
                system.strategy.include_sub_research = bool(config['include_sub_research'])
            system.set_progress_callback(progress)
            with trace_context(config['task_id']):
                result=system.analyze_topic(config['question'])
                body=_extract_synthesized_answer(result) or result.get('formatted_findings') or ''
                sources=collect_publication_sources(system,system.all_links_of_system)
                publication=publish_report(body,sources,cfg=VerifyConfig(enable_citation_qc=False))
            (output/'sources.json').write_text(json.dumps(source_snapshot(sources),ensure_ascii=False,indent=2))
            (output/'result.json').write_text(json.dumps({'body':body,'error':result.get('error'),
                'iterations':result.get('iterations'),'metadata':publication.metadata()},ensure_ascii=False,default=str,indent=2))
            byid={int(s['index']):s for s in sources}
            bibliography=[]
            for source in publication.sources:
                record=byid.get(source.original_indices[0],{})
                bibliography.append(f'[{source.index}] {source.title}\n   URL: {source.url}\n   DOI: {record.get("doi","")}')
            report=publication.content+'\n\n## Sources\n\n'+'\n\n'.join(bibliography)+'\n'
            (output/'report.md').write_text(report)
            summary={'completed':True,'model':snapshot['llm.model'],'provider':snapshot['llm.provider'],
                'strategy':snapshot['search.search_strategy'],'effective_iterations':system.strategy.max_iterations,
                'elapsed_s':round(time.monotonic()-started,3),'source_pool':len(sources),
                'references':len(publication.sources),'report_chars':len(report),'research_error':result.get('error')}
            (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
    except Exception as exc:
        failure={'completed':False,'error_type':type(exc).__name__,'elapsed_s':round(time.monotonic()-started,3)}
        (output/'summary.json').write_text(json.dumps(failure));print(json.dumps(failure),flush=True)
        raise SystemExit(1)
    finally:
        if system is not None:system.close()


if __name__=='__main__':
    main(CONFIG)
