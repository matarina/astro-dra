"""Probe installed finalization source exposure; no scientific report generation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time


def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy, SearchResultsCollector
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.generation import format_source_documents, GROUNDING_INSTRUCTIONS
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    root, arm = Path(sys.argv[1]), sys.argv[2]
    protocol = json.loads((root/"case-protocol.json").read_text())
    for filename, key in (("cases.json", "cases_sha256"), ("settings.json", "settings_sha256")):
        if hashlib.sha256((root/filename).read_bytes()).hexdigest() != protocol[key]:
            raise ValueError("Frozen probe input changed")
    cases = json.loads((root/"cases.json").read_text())
    output = []
    native = StandardCitationHandler(None)
    for case in cases:
        calls = []
        class CaptureWriter:
            def analyze_followup(self, question, sources, previous_knowledge="", nr_of_links=0):
                records = deepcopy(sources)
                docs = native._create_documents(records)
                material = format_source_documents(docs, question+"\n"+previous_knowledge,
                    max_chars=60000, required_ids={int(s["index"]) for s in records})
                calls.append({"query": question, "sources": records,
                              "material": material, "draft": previous_knowledge})
                return {"content": previous_knowledge, "documents": docs}
        strategy = LangGraphAgentStrategy.__new__(LangGraphAgentStrategy)
        strategy.collector = SearchResultsCollector()
        strategy.collector._results = deepcopy(case["current_sources"])
        strategy.collector._sources = [s["link"] for s in case["current_sources"]]
        strategy.collector._all_links = deepcopy(case["archive_sources"])
        strategy.all_links_of_system = strategy.collector._all_links
        strategy.get_setting = lambda key, default=None: default
        strategy.settings_snapshot = {}
        strategy.citation_handler = CaptureWriter()
        strategy._update_progress = lambda *args, **kwargs: None
        strategy._attach_doi_verification = lambda sources: None
        strategy._attach_constraint_match = lambda query, sources: None
        strategy._attach_keyword_coverage = lambda query, sources: None
        strategy._attach_citation_qc = lambda content, sources: (content, [])
        strategy._format_citations = lambda content, sources: content
        start = time.monotonic()
        result = strategy._finalize(case["query"], case["draft"], 1, 0, [])
        publication = publish_report(result["current_knowledge"], result["search_results"],
                                     cfg=VerifyConfig(enable_citation_qc=False))
        output.append({"case_id": case["case_id"], "domain": case["domain"], "variant": case["variant"],
            "status": "completed_component_probe", "seconds": time.monotonic()-start,
            "handler_calls": calls, "selected_sources": result["search_results"],
            "returned_urls": result["sources"], "source_recovery": result["final_report"].get("source_recovery"),
            "publication": publication.metadata(), "publication_content": publication.content,
            "output_draft_unchanged": result["current_knowledge"] == case["draft"],
            "current_collector_unchanged": strategy.collector.results == case["current_sources"],
            "archive_unchanged": strategy.collector._all_links == case["archive_sources"]})
    # Exercise the actual installed collector too, not only its AST test seam.
    original = deepcopy(cases[0]["archive_sources"][0])
    original.pop("index", None)
    collector = SearchResultsCollector()
    collector.add_results([original], "europepmc")
    collector.reset()
    index = collector.find_or_add_result({"link": original["link"], "fetched_content": original["abstract"]}, "fetch")
    refetch = {"returned_index": index, "current_sources": collector.results,
               "current_urls": collector.sources, "archive_count": len(collector._all_links),
               "original_abstract_preserved": collector._all_links[0]["abstract"] == original["abstract"],
               "fetched_text_preserved": collector._all_links[0]["fetched_content"] == original["abstract"]}
    row = {"arm": arm, "scope": "installed source-exposure component; writer records inputs and preserves draft",
           "model_calls": 0, "network_calls": 0,
           "grounding_instructions_sha256": hashlib.sha256(GROUNDING_INSTRUCTIONS.encode()).hexdigest(),
           "cases": output, "actual_installed_refetch": refetch}
    (root/(arm+"-probe.json")).write_text(json.dumps(row, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"arm": arm, "cases": len(output), "model_calls": 0,
                      "handler_calls": sum(len(r["handler_calls"]) for r in output)}))


if __name__ == "__main__":
    main()
