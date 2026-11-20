"""Inspect bound record state separately from transport in the installed app."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path


def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from research_verify.source_identity import classify_source
    from research_verify.evidence_cards import build_source_card
    from research_verify.generation import format_source_documents, GROUNDING_INSTRUCTIONS
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    root, arm = Path("/experiment"), os.environ["PILOT_ARM"]
    handler = StandardCitationHandler(None)
    rows = []
    for position, case in enumerate(json.loads((root / "cases.json").read_text()), 1):
        source = {**deepcopy(case["source"]), "index": position}
        original = deepcopy(source)
        classified = classify_source(source)
        documents = handler._create_documents([source])
        material = format_source_documents(documents, "Supplied material", max_chars=200000)
        draft = "Preserved routing prose [" + str(position) + "]."
        publication = publish_report(draft, [source], cfg=VerifyConfig(enable_citation_qc=False))
        wanted = case["expected"]
        rows.append({"case_id": case["case_id"], "expected": wanted,
                     "classified": classified, "card": build_source_card(source),
                     "native_metadata": documents[0].metadata, "native_text": documents[0].page_content,
                     "material": material, "source_unchanged": source == original,
                     "metadata_contract": all(classified.get(k) == v for k, v in wanted.items()),
                     "draft_preserved": publication.report_body == draft,
                     "publication": publication.metadata(), "rendered": publication.content})
    result = {"arm": arm, "cases": rows, "network_requests": 0, "model_calls": 0,
              "grounding_instructions_sha256": hashlib.sha256(GROUNDING_INSTRUCTIONS.encode()).hexdigest(),
              "scope": "Metadata/transport and material-preservation contracts, not scientific accuracy"}
    (root / (arm + "-probe.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"arm": arm, "cases": len(rows), "metadata_contract": sum(r["metadata_contract"] for r in rows),
                      "source_unchanged": sum(r["source_unchanged"] for r in rows),
                      "draft_preserved": sum(r["draft_preserved"] for r in rows)}))


if __name__ == "__main__":
    main()
