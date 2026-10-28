"""Installed-module smoke check, intended for a disposable offline container."""
import importlib
import json
from types import SimpleNamespace

from loguru import logger
logger.remove()

from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import SearchResultsCollector, LangGraphAgentStrategy
from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
from research_verify.config import VerifyConfig
from research_verify.publication import publish_report, validate_publication

fetch = importlib.import_module("local_deep_research.advanced_search_system.tools.fetch")
raw = "Opening context. " * 50 + "The experimental endpoint did not improve."
collector = SearchResultsCollector()
collector.add_results([{"title": "Original source", "link": "https://example.com/a", "snippet": "Search preview."}])
collector.reset()
original = fetch._fetch_raw_content
fetch._fetch_raw_content = lambda *args, **kwargs: (
    {"status": "success", "title": "Original source", "content": raw}, "https://example.com/a", None,
)
try:
    model = SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content="Model summary claims an improvement."))
    tool = fetch.build_fetch_tool("summary_focus_query", collector, model=model, overall_query="endpoint")
    observation = tool.invoke({"url": "https://example.com/a", "focus": "experimental endpoint"})
finally:
    fetch._fetch_raw_content = original
assert observation.startswith("[1]") and len(collector._all_links) == len(collector.results) == 1
assert collector.find_by_index(1)["fetched_content"] == raw

prompts = []
def write(prompt):
    prompts.append(prompt)
    return SimpleNamespace(content="The experimental endpoint did not improve [1].")
writer = StandardCitationHandler(SimpleNamespace(invoke=write), settings_snapshot={})
# Clear the per-call list to exercise a later section reusing the cited source.
collector.reset()
runner = SimpleNamespace(
    collector=collector, all_links_of_system=collector._all_links, citation_handler=writer,
    _update_progress=lambda *args: None, _format_citations=lambda body, sources: body,
)
result = LangGraphAgentStrategy._finalize(runner, "experimental endpoint", "Working draft cites [1].", 1, 1, [])
assert raw in prompts[0] and "Model summary claims an improvement." not in prompts[0]
publication = publish_report(result["current_knowledge"], collector._all_links, cfg=VerifyConfig(enable_verify=False))
validate_publication(publication.content, publication.metadata())
assert publication.content.endswith("[[1]](https://example.com/a).")
print("RESULT " + json.dumps({"checks_passed": True, "raw_chars": len(raw),
    "stable_fetch_index": 1, "draft_source_restored": True,
    "real_fetch_tool_and_writer_imported": True, "generated_summary_used_as_evidence": False}))
