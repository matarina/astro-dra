"""Installed Agent stream and synthesis smoke with simulated tools/models.

No requests, user databases, or changes to application settings. Run with the
installed application's Python. Trace root can be supplied via the environment.
"""
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


def main():
    from loguru import logger
    logger.remove()
    import langchain.agents
    from langchain_core.messages import AIMessage, ToolMessage
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.config import VerifyConfig
    from research_verify.publication import publish_report
    from research_verify.synthesis_trace import trace_context

    os.umask(0o077)
    os.environ['LDR_RESEARCH_TRACE_ENABLED'] = 'true'
    os.environ.setdefault('LDR_RESEARCH_TRACE_DIR', '/tmp/generic-source-checks')
    task = 'diagnostic-generic-' + uuid4().hex
    snapshot = {'general.enable_fact_checking': True, 'search.tool': 'pubmed'}
    class Model:
        calls = 0
        def invoke(self, prompt):
            assert 'BEGIN RELATED PUBLICATION NOTICE' in prompt
            self.calls += 1
            return AIMessage(content='Reported result [1].' if self.calls == 1 else '{"issues":[{"claim_id":0,"status":"supported"}]}')
    model = Model()
    strategy = LangGraphAgentStrategy(model=model, search=None,
        citation_handler=StandardCitationHandler(model, snapshot),
        settings_snapshot=snapshot, programmatic_mode=True)
    strategy._build_tools = lambda **kwargs: [SimpleNamespace(name='web_search')]
    strategy._build_egress_context = lambda: None
    strategy.check_termination = lambda *args: None
    strategy._observation_event = lambda message: None
    events = []
    strategy._update_progress = lambda *args, **kwargs: events.append(str(args))
    class Agent:
        def stream(self, *args, **kwargs):
            strategy.collector.add_results([
                {'pmid': '100', 'abstract': 'Reported result.',
                 'related_articles': [{'relation_type': 'erratum_in', 'pmid': '200'}]},
                {'pmid': '200', 'snippet': 'Notice metadata only.'}], 'simulated')
            yield {'model': {'messages': [AIMessage(content='', tool_calls=[
                {'id':'call-probe', 'name':'web_search', 'args':{'query':'test'}}])]}}
            yield {'tools': {'messages': [ToolMessage(content='PRIVATE_TOOL_PAYLOAD', tool_call_id='call-probe')]}}
            yield {'model': {'messages': [AIMessage(content='Reported result [1].')]}}
    langchain.agents.create_agent = lambda **kwargs: Agent()
    with trace_context(task):
        result = strategy.analyze_topic('General research question')
        pub = publish_report(result['current_knowledge'], result['search_results'],
                             cfg=VerifyConfig(enable_verify=False))
    assert model.calls == 2 and len(pub.sources) == 1
    assert 'PRIVATE_TOOL_PAYLOAD' not in json.dumps(result, default=str)
    assert all('PRIVATE_TOOL_PAYLOAD' not in e for e in events)
    root = Path(os.environ['LDR_RESEARCH_TRACE_DIR']) / task
    stages = {}
    for p in root.rglob('*.json.gz'):
        stage = p.name.split('-',1)[1][:-8]
        stages.setdefault(stage, []).append(json.loads(gzip.decompress(p.read_bytes())))
    assert stages['tool_messages'][0]['messages'][0]['content'] == 'PRIVATE_TOOL_PAYLOAD'
    assert stages['tool_messages'][0]['messages'][0]['tool_call_id'] == 'call-probe'
    assert stages['source_material_views']
    assert 'BEGIN RELATED PUBLICATION NOTICE' in stages['writer_sources'][0]['text']
    assert stages['publication_output'][0]['text'] == pub.content
    assert all((p.stat().st_mode & 0o777) == (0o700 if p.is_dir() else 0o600)
               for p in [root, *root.rglob('*')])
    print(json.dumps({'checks_passed':True,'research_id':task,'real_model_calls':0,
        'simulated_synthesis_calls':model.calls,'tool_result_private':True,
        'notice_in_review_and_writer':True,'trace_permissions_checked':True,
        'trace_stage_counts':{k:len(v) for k,v in stages.items()}}))


if __name__ == '__main__':
    main()
