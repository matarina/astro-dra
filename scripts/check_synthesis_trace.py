"""Focused installed-pipeline check; stdin supplies env and public source fixtures.

Enters Agent finalization with a supplied draft, not a full research run.
Does not open user databases or print credentials, prompts, or source text.
"""
import gzip
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def main():
    os.umask(0o077)
    config = json.load(sys.stdin)
    os.environ.update(config['environment'])
    from loguru import logger
    logger.remove()
    import local_deep_research
    from langchain_core.messages import HumanMessage, AIMessage
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.utilities.thread_context import set_search_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    from research_verify.synthesis_trace import text_digest

    pkg = Path(local_deep_research.__file__).parent
    defaults = json.loads((pkg / 'defaults/default_settings.json').read_text())
    snapshot = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()})
    # Bounded probe only; application request settings are not changed.
    snapshot.update({'llm.request_timeout': 60, 'llm.max_retries': 0})
    context = SimpleNamespace(username=None, get_setting=lambda key, default=None: snapshot.get(key, default))
    # Same lookup used by web workers, without credentials or user DB access.
    set_search_context({'research_id': config['research_id']})
    started = time.monotonic()
    with settings_context(context):
        base = get_llm(settings_snapshot=snapshot)
        class Counted:
            calls = 0
            def invoke(self, *args, **kwargs):
                self.calls += 1
                return base.invoke(*args, **kwargs)
        model = Counted()
        strategy = LangGraphAgentStrategy(model=model, search=None,
                    citation_handler=StandardCitationHandler(model, snapshot),
                    settings_snapshot=snapshot, programmatic_mode=True)
        strategy.collector.add_results(config['sources'], 'probe')
        result = strategy._finalize(config['question'], config['draft'], 1, 0,
                    [HumanMessage(content=config['question']), AIMessage(content=config['draft'])])
        body = result['current_knowledge']
        publication = publish_report(body, strategy.collector.results,
                    cfg=VerifyConfig(enable_citation_qc=False))
    root = Path(os.environ['LDR_RESEARCH_TRACE_DIR'])
    task = root / config['research_id']
    artifacts = {}
    for path in task.rglob('*.json.gz'):
        stage = path.name.split('-', 1)[1][:-8]
        artifacts.setdefault(stage, []).append(json.loads(gzip.decompress(path.read_bytes())))
    for name in ['agent_draft', 'agent_messages', 'collector_sources', 'input_sources',
                 'writer_sources', 'native_check_request', 'native_check_response',
                 'writer_request', 'writer_response', 'publication_input', 'publication_output']:
        assert artifacts.get(name), 'Missing required trace stage: ' + name
    evidence = artifacts['writer_sources'][0]['text']
    assert artifacts['native_check_request'][0]['source_ids']
    assert all(request['report_text_sha256']==artifacts['writer_response'][0]['text_sha256']
               for request in artifacts['native_check_request'])
    assert evidence in artifacts['writer_request'][0]['prompt']
    assert config['question'] in artifacts['native_check_request'][0]['prompt']
    feedback = artifacts['native_check_response'][0]['text_used']
    assert artifacts['writer_response'][0]['text_sha256'] == artifacts['review_snapshot'][0]['text_sha256']
    assert artifacts['final_response'][0]['text_sha256'] == artifacts['publication_input'][0]['text_sha256']
    assert text_digest(body) == artifacts['publication_input'][0]['text_sha256']
    assert artifacts['publication_output'][0]['text'] == publication.content
    assert 2 <= model.calls <= 33, 'Unexpected unbounded synthesis/review calls'
    (root / 'focused-report.md').write_text(publication.content)
    summary = {'checks_passed': True, 'model': snapshot['llm.model'],
               'provider': snapshot['llm.provider'], 'model_calls': model.calls,
               'research_id': config['research_id'], 'trace_stage_counts': {k: len(v) for k, v in artifacts.items()},
               'review_chars': len(feedback), 'report_chars': len(body),
               'elapsed_s': round(time.monotonic() - started, 3),
               'scope': 'Actual Agent finalization/review/writer/publication with supplied draft; no full search or account changes.'}
    (root / 'check-result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Provider exception messages can echo authentication material.
        print(json.dumps({'checks_passed': False, 'error_type': type(exc).__name__}), flush=True)
        raise SystemExit(1)
