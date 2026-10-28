"""Standard source-based synthesis with evidence continuity and final-text review."""
from typing import Any, Dict, List, Union
from research_verify.synthesis_trace import start_trace, text_digest
from .base_citation_handler import BaseCitationHandler


class StandardCitationHandler(BaseCitationHandler):
    def _synthesize(self, question, search_results, previous_knowledge, nr_of_links, kind):
        from research_verify.evidence_flow import synthesize
        with start_trace(kind) as trace:
            trace.record("agent_draft", {"question": question, "text": previous_knowledge,
                         "text_sha256": text_digest(previous_knowledge)})
            return synthesize(self, question, search_results, previous_knowledge, trace, nr_of_links)

    def analyze_initial(self, query: str, search_results: Union[str, List[Dict]]) -> Dict[str, Any]:
        return self._synthesize(query, search_results, "", 0, "initial_synthesis")

    def analyze_followup(self, question: str, search_results: Union[str, List[Dict]],
                         previous_knowledge: str, nr_of_links: int) -> Dict[str, Any]:
        return self._synthesize(question, search_results, previous_knowledge, nr_of_links, "synthesis")
