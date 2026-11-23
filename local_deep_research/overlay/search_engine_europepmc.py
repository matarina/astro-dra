"""Europe PMC search: one core response for identity and abstract text."""
from typing import Any, Dict, List
import os

from research_verify.retrieval import (
    academic_snippet,
    html_text,
    service_get,
)
from research_verify.source_relations import epmc_relations
from ..search_engine_base import BaseSearchEngine, Exposure, Sensitivity


def _search_proxy_kwargs() -> dict:
    """Use the operator-provided search proxy without changing LLM routing."""
    proxy = (os.environ.get("LDR_SEARCH_PROXY_URL") or
             os.environ.get("LDR_SEARCH_HTTP_PROXY") or "").strip()
    return {"proxies": {"http": proxy, "https": proxy}} if proxy else {}


class EuropePMCSearchEngine(BaseSearchEngine):
    is_public = True
    is_scientific = True
    is_lexical = True
    needs_llm_relevance_filter = True
    egress_sensitivity = Sensitivity.NON_SENSITIVE
    egress_exposure = Exposure.EXPOSING

    def __init__(self, max_results=12, llm=None, max_filtered_results=6,
                 settings_snapshot=None, programmatic_mode=False,
                 search_snippets_only=False):
        super().__init__(llm=llm, max_results=max_results,
                         max_filtered_results=max_filtered_results,
                         settings_snapshot=settings_snapshot,
                         programmatic_mode=programmatic_mode,
                         search_snippets_only=search_snippets_only)

    def _get_previews(self, query: str) -> List[Dict[str, Any]]:
        from research_verify.record_identity import make_record_provenance
        endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {"query": query, "format": "json", "resultType": "core",
                  "pageSize": max(1, min(1000, int(self.max_results)))}
        response = service_get(endpoint, service="europepmc", interval=0.35,
                               params=params, **_search_proxy_kwargs())
        data = response.json()
        records = data.get("resultList", {}).get("result")
        if records is None and data.get("hitCount") == 0:
            return []
        if not isinstance(records, list):
            raise ValueError("Europe PMC returned no valid result list")
        results = []
        for record in records:
            identifier, source = str(record.get("id") or ""), str(record.get("source") or "")
            if not identifier or not source:
                continue
            abstract = html_text(record.get("abstractText"))
            journal = record.get("journalInfo") or {}
            title = html_text(record.get("title"))
            item = {
                "id": identifier, "title": title,
                "authors": [a["fullName"] for a in (record.get("authorList") or {}).get("author", [])
                            if a.get("fullName")] or ([record["authorString"]] if record.get("authorString") else []),
                "link": f"https://europepmc.org/article/{source}/{identifier}",
                "doi": record.get("doi") or "", "pmid": record.get("pmid") or (identifier if source == "MED" else ""),
                "pmcid": record.get("pmcid") or (identifier if source == "PMC" else ""), "source": "Europe PMC",
                "journal": (journal.get("journal") or {}).get("title") or "",
                "journal_ref": (journal.get("journal") or {}).get("title") or None,
                "pubdate": record.get("firstPublicationDate") or record.get("pubYear") or "",
                "language": record.get("language") or record.get("languageOfFullText") or "",
                "publication_types": (record.get("pubTypeList") or {}).get("pubType") or [],
                "abstract": abstract, "content_type": "abstract" if abstract else "metadata",
                "related_articles": epmc_relations(record),
                "record_provenance": make_record_provenance("europepmc", record),
            }
            item["snippet"] = academic_snippet(item, abstract)
            if abstract:
                item["full_content"] = abstract
                item["content"] = abstract
            results.append({**item, "_full_result": item})
        return results
