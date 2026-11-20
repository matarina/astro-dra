"""Measure original evidence exposure with the installed formatter, no model."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    from loguru import logger
    logger.remove()
    from local_deep_research.citation_handlers.base_citation_handler import BaseCitationHandler
    from research_verify.generation import format_source_documents
    import research_verify
    root, arm = Path(sys.argv[1]), sys.argv[2]
    freeze = json.loads((root / "inputs-freeze.json").read_text())
    for name, expected in freeze["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Input freeze changed")
    gold = {x["family"]: x for x in json.loads((root / "reference-gold.json").read_text())}
    rows = []
    for case in json.loads((root / "cases.json").read_text()):
        sources = json.loads((root / case["source_pack"]).read_text())
        original = deepcopy(sources)
        documents = BaseCitationHandler._create_documents(SimpleNamespace(), sources)
        original_documents = deepcopy(documents)
        views, calls = [], []
        output = format_source_documents(documents, case["query"], reading_scope=views,
                                         selector=lambda prompt: calls.append(prompt) or "[1]")
        reference = gold[case["task_family"]]
        snippets = []
        if reference["dataset"].startswith("Evidence Inference"):
            for annotation in reference["annotations"]:
                derived = annotation["derived_localization"]
                snippets.append({"annotation_index": annotation["annotation_index"],
                                 "source_localized": derived["status"] == "unique_exact",
                                 "entire_quote_in_view": derived["status"] == "unique_exact" and derived["decoded_annotation"] in output})
        else:
            for answer_index, answer in enumerate(reference["original_reference"]["answers"]):
                for index, text in enumerate(answer["answer"].get("evidence") or []):
                    snippets.append({"answer_index": answer_index, "evidence_index": index,
                                     "source_localized": any(text in d.page_content for d in documents),
                                     "entire_quote_in_view": bool(text) and text in output})
        rows.append({"case_id": case["case_id"], "family": case["task_family"], "domain": case["domain"],
                     "split": case["split"], "source_count": len(sources), "formatted_chars": len(output),
                     "original_fields_preserved": all(all(s.get(k) == value for k, value in before.items())
                                                       for s, before in zip(sources, original)),
                     "documents_unchanged": documents == original_documents,
                     "source_texts_complete_in_view": sum(d.page_content in output for d in documents),
                     "supplied_abstracts_complete_in_view": all(not d.metadata.get("abstract") or d.metadata["abstract"] in output for d in documents),
                     "selector_calls": len(calls), "views": views, "reference_exposure": snippets})
    package = Path(research_verify.__file__).parent
    result = {"status": "completed_formatter_exposure_only", "arm": arm, "model_calls": 0,
              "installed_module_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob("*.py")},
              "rows": rows, "scientific_effectiveness": "unproven"}
    (root / (arm + "-exposure.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"arm": arm, "cases": len(rows), "complete_views": sum(x["source_texts_complete_in_view"] for x in rows),
                      "full_reference_spans_in_view": sum(y["entire_quote_in_view"] for x in rows for y in x["reference_exposure"])}))


if __name__ == "__main__":
    main()
