"""Installed syntax/routing/publication replay, with no scientific/model verdict."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


def main():
    from loguru import logger
    logger.remove()
    from research_verify.claims import extract_report_claims
    from research_verify.citation_display import cited_indices
    from research_verify.source_collection import sources_for_draft
    from research_verify.evidence_flow import review_units
    from research_verify.publication import publish_report, validate_publication
    from research_verify.config import VerifyConfig
    root,arm=Path(sys.argv[1]),sys.argv[2]
    import research_verify
    package=Path(research_verify.__file__).parent
    cases=json.loads((root/"cases.json").read_text())
    sources=json.loads((root/"sources.json").read_text())
    result={"arm":arm,"network_calls":0,"model_calls":0,"cases":[],"legacy_validation":[],
        "installed_module_sha256":{str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in package.glob("*.py")}}
    for case in cases:
        draft=case["draft"]
        units=extract_report_claims(draft)
        current=deepcopy(sources[:1]);archive=deepcopy(sources)
        original=deepcopy((current,archive))
        selected,state=sources_for_draft(current,archive,draft)
        publication=publish_report(draft,sources,cfg=VerifyConfig(enable_citation_qc=False))
        validate_publication(publication.content,publication.metadata())
        result["cases"].append({"case_id":case["case_id"],"draft":draft,
            "citation_ids":cited_indices(draft),"units":[{"text":u.text,"kind":u.kind,"start":u.report_start,"end":u.report_end,"citations":u.citations} for u in units],
            "raw_coordinates_valid":all(draft[u.report_start:u.report_end]==u.text for u in units),
            "review_units":[{"text":u.text,"kind":u.kind,"citations":u.citations} for u in review_units(draft)],
            "routing":state,"selected_ids":[s["index"] for s in selected],
            "collector_archive_unchanged":(current,archive)==original,
            "publication":publication.metadata(),"published_text":publication.content})
    if arm=="candidate":
        baseline=json.loads((root/"baseline-probe.json").read_text())
        for row in baseline["cases"]:
            before=deepcopy(row["publication"])
            validate_publication(row["published_text"],row["publication"])
            result["legacy_validation"].append({"case_id":row["case_id"],"validated_without_mutation":before==row["publication"]})
    (root/(arm+"-probe.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"arm":arm,"cases":len(cases),"citation_contracts_matching":sum(r["citation_ids"]==c["expected_prose_citation_ids"] for r,c in zip(result["cases"],cases)),"legacy_reports":len(result["legacy_validation"])}))


if __name__=="__main__":main()
