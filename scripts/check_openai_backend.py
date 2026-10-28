"""Smoke-test the configured OpenAI-compatible backend inside the LDR image.

Pass environment overrides through stdin as JSON for an isolated candidate test,
otherwise use the container's existing environment. Never emits credentials.
"""
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit


def main():
    if '--stdin-env' in sys.argv:
        os.environ.update(json.load(sys.stdin))
    from loguru import logger
    logger.remove()
    secrets = [v for k, v in os.environ.items() if k.endswith('_API_KEY') and v]
    def safe(value):
        text = str(value)
        for secret in secrets:
            text = text.replace(secret, '[redacted]')
        return text
    from langchain_core.messages import HumanMessage, ToolMessage
    import local_deep_research
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.llm.providers.implementations.custom_openai_endpoint import CustomOpenAIEndpointProvider
    from local_deep_research.llm.providers.implementations.deepseek import DeepseekProvider
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.web_search_engines.relevance_filter import filter_previews_for_relevance

    pkg = Path(local_deep_research.__file__).parent
    defaults = json.loads((pkg / 'defaults/default_settings.json').read_text())
    snapshot = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()})
    context = SimpleNamespace(username=None, get_setting=lambda key, default=None: snapshot.get(key, default))
    expected = os.environ['LDR_LLM_MODEL']
    checks, timings = [], {}
    started = time.monotonic()
    result = {'model': expected, 'provider': snapshot.get('llm.provider'), 'checks_passed': False}
    try:
        with settings_context(context):
            assert snapshot['llm.model'] == expected
            provider = {'openai_endpoint': CustomOpenAIEndpointProvider, 'deepseek': DeepseekProvider}[snapshot['llm.provider']]
            assert provider.is_available(snapshot)
            checks.append('environment_default_and_native_provider')
            t0 = time.monotonic()
            llm = get_llm(settings_snapshot=snapshot)
            reply = llm.invoke('请只回复四个字：连接成功')
            assert '连接成功' in str(reply.content), 'Chinese completion missing expected response'
            checks.append('ldr_get_llm_chinese_completion')
            timings['completion_s'] = round(time.monotonic() - t0, 3)
            t0 = time.monotonic()
            streamed = ''.join(chunk.content for chunk in llm.stream('Reply with exactly BACKEND_STREAM_OK.')
                               if isinstance(chunk.content, str))
            assert 'BACKEND_STREAM_OK' in streamed, f'Streaming missing expected response: {streamed[:300]!r}'
            checks.append('streaming')
            timings['stream_s'] = round(time.monotonic() - t0, 3)
            tool = {'type': 'function', 'function': {
                'name': 'add_numbers', 'description': 'Add two integers. Use this tool for addition.',
                'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}},
                               'required': ['a', 'b']}}}
            bound = llm.bind_tools([tool])
            messages = [HumanMessage(content='Use the add_numbers tool to calculate 2 plus 3. You must call the tool.')]
            t0 = time.monotonic()
            response = bound.invoke(messages)
            assert response.tool_calls, 'No structured tool call'
            call = response.tool_calls[0]
            assert call['name'] == 'add_numbers' and call['args'] == {'a': 2, 'b': 3}, 'Unexpected tool arguments'
            final = bound.invoke(messages + [response, ToolMessage(content='5', tool_call_id=call['id'])])
            assert '5' in str(final.content), 'Tool result roundtrip failed'
            checks.extend(['structured_tool_call', 'tool_result_roundtrip'])
            timings['tool_roundtrip_s'] = round(time.monotonic() - t0, 3)
            t0 = time.monotonic()
            candidates = [{'title': 'Microscopy image analysis', 'abstract': 'A microscope image segmentation method.', 'index': 1},
                          {'title': 'Basketball scores', 'abstract': 'Scores from a basketball game.', 'index': 2}]
            relevant = filter_previews_for_relevance(llm, candidates, 'microscopy image segmentation', engine_name='smoke')
            assert [r['index'] for r in relevant] == [1], 'Search relevance smoke decision failed'
            checks.append('relevance_filter')
            timings['relevance_s'] = round(time.monotonic() - t0, 3)
            t0 = time.monotonic()
            writer = StandardCitationHandler(llm, snapshot)
            source = {'index': 7, 'title': 'Synthetic backend smoke fixture', 'link': 'https://example.org/smoke',
                      'abstract': 'In a validation dataset, method A reduced measurement error from 10 to 5. No clinical benefit was evaluated.',
                      'content_type': 'abstract'}
            answer = writer.analyze_followup('用一句中文说明方法A的测量误差结果，保留来源引用。', [source], '', 0)
            assert re.search(r'\[7\]', answer['content']), 'Writer did not preserve the supplied citation ID'
            checks.append('native_consistency_and_final_writer')
            timings['writer_s'] = round(time.monotonic() - t0, 3)
            result.update({'checks_passed': True, 'temperature': snapshot.get('llm.temperature'),
                           'max_tokens_setting': snapshot.get('llm.max_tokens'),
                           'consistency_enabled': snapshot.get('general.enable_fact_checking'),
                           'configured_host': urlsplit(snapshot.get('llm.openai_endpoint.url', '') if provider is CustomOpenAIEndpointProvider else provider.default_base_url).hostname})
    except Exception as exc:
        result.update({'error_type': type(exc).__name__, 'error': safe(exc)[:1600]})
    result.update({'checks': checks, 'timings': timings, 'elapsed_s': round(time.monotonic() - started, 3),
                   'scope': 'Backend integration smoke; no full research or account changes.'})
    if '--output' in sys.argv:
        Path(sys.argv[sys.argv.index('--output') + 1]).write_text(safe(json.dumps(result, ensure_ascii=False, indent=2)) + '\n')
    print('RESULT ' + safe(json.dumps(result, ensure_ascii=False)), flush=True)
    raise SystemExit(0 if result['checks_passed'] else 1)


if __name__ == '__main__':
    main()
