"""Replay installed adapters/validator/publication over frozen API packets.

No live requests, model calls or scientific assessment. New receipts are tested
as adapter metadata; their absence is not a scientific-error metric.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.web_search_engines.engines import search_engine_europepmc as epmc
    from local_deep_research.web_search_engines.engines import search_engine_pubmed as pubmed
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.source_identity import classify_source
    from research_verify.doi_validator import DoiValidator, badge_for
    from research_verify.http_client import HttpResult
    from research_verify.config import VerifyConfig
    from research_verify.generation import format_source_documents, GROUNDING_INSTRUCTIONS
    from research_verify.publication import publish_report
    from research_verify.claims import extract_report_claims
    from research_verify.evidence_cards import build_source_card
    root, arm = Path(sys.argv[1]), sys.argv[2]
    protocol = json.loads((root/"case-protocol.json").read_text())
    for name, expected in protocol["sha256"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen input changed: "+name)
    xml_manifest = json.loads((root/"supplemental-xml-fixture.json").read_text())
    if hashlib.sha256((root/"efetch.xml").read_bytes()).hexdigest() != xml_manifest["sha256"]:
        raise ValueError("Supplemental frozen XML changed")
    handler = StandardCitationHandler(None)
    def view(source, index):
        item = deepcopy(source)
        item["index"] = index
        original = deepcopy(item)
        classified = classify_source(item)
        docs = handler._create_documents([item])
        material = format_source_documents(docs, "Supplied source metadata", max_chars=60000, required_ids={index})
        publication = publish_report("Routing placeholder ["+str(index)+"].\n\n## Sources\n", [item], cfg=VerifyConfig(enable_citation_qc=False))
        if item != original:
            raise ValueError("Source modified during identity/publication processing")
        return {"source": original, "classified": classified, "card": build_source_card(item), "native_metadata": docs[0].metadata,
                "native_text": docs[0].page_content, "material": material,
                "publication": publication.metadata(), "publication_content": publication.content,
                "prose_candidates_after_publication": [{"text": c.text, "start": c.report_start, "end": c.report_end}
                                                       for c in extract_report_claims(publication.content)],
                "bibliography_start": publication.content.index("\n\n## Sources\n")}
    epmc_packet = json.loads((root/"epmc-records.json").read_text())
    adapter_calls = []
    def epmc_get(*args, **kwargs):
        adapter_calls.append({"adapter": "europepmc", "endpoint": args[0]})
        return SimpleNamespace(json=lambda: deepcopy(epmc_packet))
    epmc.service_get, epmc._search_proxy_kwargs = epmc_get, lambda: {}
    engine = epmc.EuropePMCSearchEngine.__new__(epmc.EuropePMCSearchEngine)
    engine.max_results = 50
    epmc_rows = [view(source, i) for i, source in enumerate(engine._get_previews("frozen-record-packet"), 1)]

    summary = json.loads((root/"pubmed-summary.response").read_text())
    xml = (root/"efetch.xml").read_text()
    def pubmed_get(url, **kwargs):
        adapter_calls.append({"adapter": "pubmed", "endpoint": url})
        return SimpleNamespace(json=lambda: deepcopy(summary), text=xml, status_code=200, raise_for_status=lambda: None)
    pubmed.safe_get, pubmed._search_proxy_kwargs = pubmed_get, lambda: {}
    engine = pubmed.PubMedSearchEngine.__new__(pubmed.PubMedSearchEngine)
    engine.api_key, engine.engine_type = None, "pubmed"
    engine.summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    engine.fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    engine.rate_tracker = SimpleNamespace(apply_rate_limit=lambda _: 0)
    engine._scrub_error = lambda value: str(value)
    engine._optimize_query_for_pubmed = lambda query: query
    engine._adaptive_search = lambda query: (summary["result"]["uids"], "frozen")
    for flag in ("publication_type", "authors", "journal", "full_date", "year", "citation", "language", "pmid", "doi"):
        setattr(engine, "include_"+flag+"_in_context", True)
    pubmed_rows = [view(source, i) for i, source in enumerate(engine._get_previews("frozen-record-packet"), 1)]
    states = [{"case_id": case["id"], **view(case["source"], i)}
              for i, case in enumerate(json.loads((root/"state-cases.json").read_text()), 1)]

    class HTTP:
        def __init__(self, result):
            self.result, self.calls = result, []
        async def get(self, url, **kwargs):
            self.calls.append(url)
            return self.result
    async def checks():
        rows = []
        inputs = json.loads((root/"http-cases.json").read_text())
        crossref = json.loads((root/"crossref-numpy.response").read_text())
        inputs += [{"id": "actual_crossref_numpy", "source": {"doi": crossref["message"]["DOI"],
                    "title": crossref["message"]["title"][0]}, "status": 200, "json": crossref},
                   {"id": "actual_pubmed_summary", "source": {"pmid": "32678530", "title": summary["result"]["32678530"]["title"]},
                    "status": 200, "json": summary}]
        for i, case in enumerate(inputs, 1):
            http = HTTP(HttpResult(case["status"], deepcopy(case["json"]), ""))
            check = await DoiValidator(http, VerifyConfig()).verify(case["source"])
            item = {**case["source"], "_verify": check.model_dump()}
            rows.append({"case_id": case["id"], "check": check.model_dump(), "badge": badge_for(check),
                         "request_count": len(http.calls), **view(item, i)})
        return rows
    rows = asyncio.run(checks())
    output = {"arm": arm, "status": "completed_installed_identity_probe",
              "scope": "source metadata/identity processing only", "epmc": epmc_rows, "pubmed": pubmed_rows,
              "state_cases": states, "validator_cases": rows, "adapter_calls": adapter_calls,
              "network_calls": 0, "model_calls": 0,
              "grounding_instructions_sha256": hashlib.sha256(GROUNDING_INSTRUCTIONS.encode()).hexdigest()}
    modules = {
        "local_deep_research/overlay/search_engine_europepmc.py": epmc,
        "local_deep_research/search_engine_pubmed.py": pubmed,
        **{"local_deep_research/research_verify/"+name+".py": sys.modules["research_verify."+name]
           for name in ("source_identity", "doi_validator", "models", "generation", "publication", "citation_display", "textutil", "evidence_cards")},
        "local_deep_research/overlay/base_citation_handler.py": sys.modules["local_deep_research.citation_handlers.base_citation_handler"],
    }
    if "research_verify.record_identity" in sys.modules:
        modules["local_deep_research/research_verify/record_identity.py"] = sys.modules["research_verify.record_identity"]
    output["installed_module_sha256"] = {name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                        for name, module in modules.items()}
    (root/(arm+"-probe.json")).write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"arm": arm, "status": output["status"], "epmc": len(epmc_rows), "pubmed": len(pubmed_rows),
                      "states": len(states), "validator_checks": len(rows), "adapter_requests": len(adapter_calls)}))


if __name__ == "__main__":
    main()
