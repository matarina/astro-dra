"""Installed-adapter metadata comparison; no LLM, network, or scientific scoring."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, arm):
    from local_deep_research.web_search_engines.engines import search_engine_europepmc as epmc
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.evidence_cards import build_source_card
    from research_verify.generation import format_source_documents, GROUNDING_INSTRUCTIONS
    from research_verify.source_identity import classify_source
    protocol = json.loads((root/"protocol.json").read_text())
    if digest(root/"records.json") != protocol["records_sha256"] or digest(root/"contracts.json") != protocol["contracts_sha256"]:
        raise ValueError("Frozen inputs changed")
    packet = json.loads((root/"records.json").read_text())
    # Exercise the installed native adapter against exact archived HTTP JSON.
    class Response:
        def json(self):
            return deepcopy(packet)
    calls = []
    def frozen_get(*args, **kwargs):
        calls.append({"query": kwargs.get("params", {}).get("query")})
        return Response()
    epmc.service_get = frozen_get
    epmc._search_proxy_kwargs = lambda: {}
    engine = epmc.EuropePMCSearchEngine.__new__(epmc.EuropePMCSearchEngine)
    engine.max_results = 50
    start = time.monotonic()
    previews = engine._get_previews("frozen-metadata-records")
    handler = StandardCitationHandler(None)
    real = []
    for index, source in enumerate(previews, 1):
        source["index"] = index
        docs = handler._create_documents([source])
        material = format_source_documents(docs, "Supplied source metadata", max_chars=60000, required_ids={index})
        real.append({"id": source["id"], "source": source, "classified": classify_source(source),
                     "card": build_source_card(source), "document_metadata": docs[0].metadata,
                     "document_text": docs[0].page_content, "material": material})
    synthetic = []
    for case in json.loads((root/"contracts.json").read_text()):
        source = deepcopy(case["source"])
        docs = handler._create_documents([source])
        synthetic.append({"case_id": case["case_id"], "classified": classify_source(source),
                          "card": build_source_card(source, case["requested_fields"]),
                          "document_metadata": docs[0].metadata,
                          "material": format_source_documents(docs, "Supplied source metadata", max_chars=60000,
                                                               required_ids={source["index"]})})
    result = {"arm": arm, "status": "completed_component_replay", "real": real, "synthetic": synthetic,
              "source_requests_replayed": calls, "network_calls": 0, "model_calls": 0,
              "component_seconds": time.monotonic()-start,
              "grounding_instructions_sha256": hashlib.sha256(GROUNDING_INSTRUCTIONS.encode()).hexdigest()}
    (root/(arm+"-result.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"arm": arm, "status": result["status"], "real": len(real),
                      "synthetic": len(synthetic), "model_calls": 0, "network_calls": 0}))


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
