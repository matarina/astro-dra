"""Collect syntax and routing evidence, explicitly outside scientific efficacy."""
import hashlib
import json
from pathlib import Path
import re


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    protocol=json.loads((root/"protocol.json").read_text())
    for name,h in protocol["sha256"].items():
        if sha(root/name)!=h:raise ValueError("Pre-edit freeze changed")
    manifests={a:json.loads((root/(a+"-code-hashes.json")).read_text()) for a in ["baseline","candidate"]}
    cases=json.loads((root/"cases.json").read_text())
    arms={}
    failures={}
    for arm,manifest in manifests.items():
        for name,h in manifest.items():
            if sha(root/(arm+"-code")/name)!=h:raise ValueError("Frozen code changed")
        run=json.loads((root/(arm+"-probe.json")).read_text())
        if run["network_calls"] or run["model_calls"]:raise ValueError("Nonisolated replay")
        for name,h in run["installed_module_sha256"].items():
            if h!=manifest["local_deep_research/research_verify/"+name]:raise ValueError("Installed hash mismatch")
        if len(run["cases"])!=len(cases):raise ValueError("Missing cases")
        rows=run["cases"]
        for row,case in zip(rows,cases):
            if row["case_id"]!=case["case_id"] or row["draft"]!=case["draft"]:raise ValueError("Case mismatch")
            if not row["raw_coordinates_valid"] or not row["collector_archive_unchanged"]:raise ValueError("Text/collector mutation")
            p=row["publication"]["claim_publication"]
            if p["audit_status"]!="disabled" or p["status"]!="unverified" or p["report_body"]!=case["draft"]:
                raise ValueError("Report/audit state changed")
        text=(root/(arm+"-tests.log")).read_text()
        summary=re.search(r"(\d+) failed, (\d+) passed",text)
        if not summary:raise ValueError("Incomplete test run")
        failures[arm]=[line.split("::",1)[1] for line in text.splitlines() if line.startswith("FAILED ")]
        arms[arm]={"syntax_contract_matches":sum(r["citation_ids"]==c["expected_prose_citation_ids"] for r,c in zip(rows,cases)),
            "case_denominator":len(cases),"coordinates_and_archive_preserved":len(rows),
            "native_review_candidate_count":sum(len(r["review_units"]) for r in rows),
            "schema_versions":sorted({r["publication"]["claim_publication"]["schema_version"] for r in rows}),
            "legacy_reports_validated_unchanged":sum(x["validated_without_mutation"] for x in run["legacy_validation"]),
            "tests":{"passed":int(summary[2]),"failed":int(summary[1]),"log_sha256":sha(root/(arm+"-tests.log"))},
            "cases":[{"case_id":r["case_id"],"citation_ids":r["citation_ids"],"routing":r["routing"]} for r in rows]}
    if arms["candidate"]["syntax_contract_matches"]!=len(cases):raise ValueError("Candidate syntax regression")
    if arms["candidate"]["legacy_reports_validated_unchanged"]!=len(cases):raise ValueError("Legacy mutation/validation loss")
    return {"status":"completed_installed_syntax_routing_comparison","root":str(root),"arms":arms,
        "same_remaining_failure_names":set(failures["baseline"])==set(failures["candidate"]),
        "remaining_failures":failures["candidate"],"overall_effectiveness":"unproven","scientific_assessment":"not_performed",
        "runtime_changed_files":[n for n in manifests["candidate"] if n.endswith(".py") and "/tests/" not in n and manifests["candidate"][n]!=manifests["baseline"].get(n)],
        "artifacts_sha256":{n:sha(root/n) for n in ["protocol.json","cases.json","sources.json","baseline-code-hashes.json","candidate-code-hashes.json","baseline-probe.json","candidate-probe.json","test-policy-correction.json"]},
        "limitations":["24 implementing-agent syntax contracts, not heldout scientific cases or hallucination accuracy.",
            "Two real previously inspected abstracts are routing fixtures, selected after the initial syntax freeze; no fresh source-recall or usefulness gold.",
            "Additional questions/headings/advice remain unknown candidates; reviewer work and errors may increase. No native model-quality/latency comparison here.",
            "37 shared selected-test failures remain red. The separate storage/export check also fails in both arms because Quarto bibliography omits URLs; later export stages are not proved.",
            "New2.2 report serialization requires the candidate reader. Compatibility was checked on24 pre-round2.1 fixtures and existing2.0 read-only tests, not by migrating production data.",
            "Original bibliography wording/unmapped entries are retained; supplied duplicate or incorrect bibliography metadata is not scientifically validated.",
            "Installed MarkdownIt4.2.0 supplies syntax parsing, not scientific meaning; supported explicit numeric citations and conventional bibliography labels are a constrained grammar."]}


if __name__=="__main__":
    index=json.loads(Path("evaluation/markdown-citations-freeze-20261111.json").read_text());root=Path(index["root"])
    if sha(root/"protocol.json")!=index["protocol_sha256"]:raise ValueError("Protocol hash changed")
    result=collect(root);Path("evaluation/markdown-citations-results-20261111.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({a:{k:v for k,v in d.items() if k!="cases"} for a,d in result["arms"].items()},indent=2))
