"""Collect metadata/identity replay evidence with explicit unmeasured endpoints."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_log(path):
    text = path.read_text()
    summary = re.search(r"(\d+) failed, (\d+) passed", text)
    if not summary:
        raise ValueError("Missing completed pytest summary")
    return {"failed": int(summary[1]), "passed": int(summary[2]), "log_sha256": sha(path),
        "failures": [line.split("::", 1)[1] for line in text.splitlines()
                     if line.startswith("FAILED ") and "::" in line]}


def collect(root, freeze, cases_freeze):
    for key, name in (("protocol_sha256", "protocol.json"), ("baseline_manifest_sha256", "baseline-code-hashes.json"),
                      ("epmc_records_sha256", "epmc-records.json")):
        if sha(root/name) != freeze[key]:
            raise ValueError("Baseline/source freeze changed")
    if sha(root/"case-protocol.json") != cases_freeze["case_protocol_sha256"]:
        raise ValueError("Case protocol changed")
    case_protocol = json.loads((root/"case-protocol.json").read_text())
    for name, expected in case_protocol["sha256"].items():
        if sha(root/name) != expected:
            raise ValueError("Frozen packet/case changed: "+name)
    if sha(root/"efetch.xml") != json.loads((root/"supplemental-xml-fixture.json").read_text())["sha256"]:
        raise ValueError("Supplemental earlier XML changed")
    manifests = {arm: json.loads((root/(arm+"-code-hashes.json")).read_text()) for arm in ("baseline", "candidate")}
    runs = {arm: json.loads((root/(arm+"-probe.json")).read_text()) for arm in manifests}
    for arm, manifest in manifests.items():
        for name, expected in manifest.items():
            if sha(root/(arm+"-code")/name) != expected:
                raise ValueError("Frozen code mismatch: "+name)
        run = runs[arm]
        if run["status"] != "completed_installed_identity_probe" or run["network_calls"] or run["model_calls"]:
            raise ValueError("Incomplete or nonisolated probe")
        for name, expected in run["installed_module_sha256"].items():
            if expected != manifest[name]:
                raise ValueError("Installed module does not match frozen source: "+name)
    if runs["baseline"]["grounding_instructions_sha256"] != runs["candidate"]["grounding_instructions_sha256"]:
        raise ValueError("Generation instructions changed")
    arms, preservation = {}, {}
    for arm, run in runs.items():
        arms[arm] = {
            "api_adapter_requests": len(run["adapter_calls"]),
            "adapter_rows": {engine: {"n": len(run[engine]),
                "identity_states": dict(Counter(x["classified"]["identity_status"] for x in run[engine])),
                "publication_states": dict(Counter(x["classified"]["publication_state"] for x in run[engine])),
                "bibliography_statuses": dict(Counter(x["classified"]["publication_status"] for x in run[engine])),
                "document_types": dict(Counter(x["classified"]["document_type"] for x in run[engine])),
                "peer_review_states": dict(Counter(x["classified"]["peer_review_status"] for x in run[engine]))}
                for engine in ("epmc", "pubmed")},
            "state_cases": [{"case_id": x["case_id"], "identity": x["classified"]["identity_status"],
                             "publication": x["classified"]["publication_state"],
                             "bibliography_status": x["classified"]["publication_status"]} for x in run["state_cases"]],
            "validator_cases": [{"case_id": x["case_id"], "verified": x["check"]["verified"],
                "lookup_status": x["check"].get("lookup_status", "unreported"), "badge": x["badge"],
                "identity": x["classified"]["identity_status"], "requests": x["request_count"]} for x in run["validator_cases"]],
            "installed_module_hashes_verified": len(run["installed_module_sha256"]),
            "network_calls_during_probe": 0, "model_calls": 0,
        }
        all_rows = [row for key in ("epmc", "pubmed", "state_cases", "validator_cases") for row in run[key]]
        if not all(row["publication"]["claim_publication"]["audit_status"] == "disabled" and
                   row["publication"]["claim_publication"]["status"] == "unverified" for row in all_rows):
            raise ValueError("Audit/publication status changed")
        arms[arm]["publication_rows"] = len(all_rows)
        arms[arm]["prose_only_routing_candidate_count"] = dict(Counter(len(row["prose_candidates_after_publication"]) for row in all_rows))
        leaked = sum(any(c["start"] >= row["bibliography_start"] for c in row["prose_candidates_after_publication"])
                     for row in all_rows)
        arms[arm]["bibliography_rows_reopened_as_prose"] = {"numerator": leaked, "denominator": len(all_rows)}
        if arm == "candidate" and leaked:
            raise ValueError("Candidate bibliography reopened prose extraction")
        if any(row["request_count"] != 1 for row in run["validator_cases"]):
            raise ValueError("Lookup added unplanned requests")
    unique_records = set()
    for engine in ("epmc", "pubmed"):
        b, c = runs["baseline"][engine], runs["candidate"][engine]
        if len(b) != len(c):
            raise ValueError("Adapter dropped records")
        counts = Counter()
        for old, new in zip(b, c):
            x, y = old["source"], new["source"]
            if x["id"] != y["id"] or x["link"] != y["link"]:
                raise ValueError("IDs/order/URLs changed")
            if x["abstract"] != y["abstract"] or old["native_text"] != new["native_text"]:
                raise ValueError("Source/native text changed")
            if not all(row["source"]["abstract"] in row["material"] for row in (old, new)):
                raise ValueError("Complete supplied abstract absent from material")
            publication = new["publication"]["claim_publication"]
            if len(publication["sources"]) != 1 or publication["sources"][0]["url"] != y["link"]:
                raise ValueError("Source citation lost or rebound")
            if new["card"]["identity"]["identity_status"] != new["classified"]["identity_status"]:
                raise ValueError("Card identity differs")
            if not publication["sources"][0].get("identity_provenance"):
                raise ValueError("Publication provenance lost")
            counts["ids_order_urls_preserved"] += 1
            counts["abstract_native_text_and_material_preserved"] += 1
            counts["citation_url_and_provenance_preserved"] += 1
            unique_records.add(("MED", x.get("_pmid") or x.get("pmid") or x["id"]) if engine == "pubmed" or "/MED/" in x["link"] else ("PPR", x["id"]))
        preservation[engine] = {"denominator": len(b), **dict(counts)}
    expected = {x["id"]: x for x in json.loads((root/"state-cases.json").read_text())}
    for row in runs["candidate"]["state_cases"]:
        case = expected[row["case_id"]]
        if row["classified"]["identity_status"] != case["expected_identity"] or row["classified"]["publication_state"] != case["expected_publication_state"]:
            raise ValueError("Candidate state contract failed")
    http_cases = {x["id"]: x for x in json.loads((root/"http-cases.json").read_text())}
    for row in runs["candidate"]["validator_cases"]:
        if row["case_id"] in http_cases and row["check"]["verified"] is not http_cases[row["case_id"]]["expected_verified"]:
            raise ValueError("Candidate HTTP uncertainty contract failed")
    registry_fetch = {row["name"]: row for row in json.loads((root/"registry-scope-fetch.json").read_text())}
    datacite = json.loads((root/"datacite-zenodo.response").read_text())
    if registry_fetch["crossref-zenodo"]["status"] != 404 or registry_fetch["datacite-zenodo"]["status"] != 200 or datacite["data"]["id"].casefold() != "10.5281/zenodo.4663312":
        raise ValueError("Cross-registry counterexample not corroborated")
    tests = {"baseline": test_log(root/"baseline-final-tests.log"),
             "candidate": test_log(root/"candidate-current-tests.log")}
    tests["same_legacy_failure_names"] = set(tests["baseline"]["failures"]) == set(tests["candidate"]["failures"])
    return {"status": "completed_identity_component_comparison_with_unresolved_legacy_tests", "root": str(root),
        "freeze": freeze, "case_freeze": cases_freeze, "arms": arms, "source_preservation": preservation,
        "adapter_record_observations": sum(len(runs["candidate"][e]) for e in ("epmc", "pubmed")),
        "distinct_underlying_adapter_records": len(unique_records),
        "registry_counterexample": {"doi": datacite["data"]["id"], "crossref_http": 404, "datacite_http": 200,
            "scope": "Engineering-only corroboration; no production DataCite backend or search-pool change."},
        "tests": tests, "runtime_changed_files": [n for n in manifests["candidate"] if n.endswith(".py") and "/tests/" not in n and manifests["candidate"].get(n) != manifests["baseline"].get(n)],
        "scientific_assessment": "not_performed", "new_prompt_rules": 0,
        "grounding_instructions_sha256": runs["baseline"]["grounding_instructions_sha256"],
        "artifacts_sha256": {name: sha(root/name) for name in ["protocol.json", "case-protocol.json", "state-cases.json", "http-cases.json", "baseline-code-hashes.json", "candidate-code-hashes.json", "baseline-probe.json", "candidate-probe.json", "fetch.json", "registry-scope-fetch.json", "supplemental-xml-fixture.json", "test-wheel-hashes.json"]},
        "limitations": [
            "Seventeen adapter observations describe nine underlying previously inspected source records, not seventeen independent papers or a sealed heldout evaluation.",
            "State expectations are constrained metadata contracts, not independent scientific gold. Baseline field absence is not a scientific error count.",
            "Receipts document trusted adapter processing/metadata binding, not cryptographic source authentication or all local-field accuracy. Caller-supplied receipts can be forged.",
            "Title comparison is a normalized bibliographic comparison with explicit matching IDs, not scientific equivalence or title-only identity merging. Metadata/version/role differences may need further resolution.",
            "Identity and registry/index metadata do not establish peer review, source truth, source-text provenance, claim entailment or usefulness.",
            "Malformed/registry-missing lookups remain unknown without adding another agency lookup. This sacrifices some validation coverage rather than asserting global absence.",
            "The supplemental NCBI XML was copied from an earlier preserved fixture after edits; it is not prospectively heldout evidence.",
            "Twenty-five shared legacy citation-audit failures remain unresolved. Same failures are not evidence those behaviors work; no save-time audits are restored to satisfy them.",
            "An initial collector wrongly required one syntactic candidate per placeholder. It is preserved; final checks use source-section offsets. URL-aware sentence splitting remains an open, pre-existing issue.",
            "No model/report-generation latency, hallucination rate, retrieval recall, useful synthesis or representative domain-regression endpoint is measured. Prior report pilots contain older code.",
        ]}


if __name__ == "__main__":
    freeze = json.loads(Path("evaluation/identity-provenance-freeze-20261111.json").read_text())
    cases_freeze = json.loads(Path("evaluation/identity-provenance-cases-freeze-20261111.json").read_text())
    result = collect(Path(freeze["root"]), freeze, cases_freeze)
    Path("evaluation/identity-provenance-results-20261111.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"status": result["status"], "source_preservation": result["source_preservation"],
        "unique_records": result["distinct_underlying_adapter_records"], "tests": {k: {"passed": v["passed"], "failed": v["failed"]} for k, v in result["tests"].items() if isinstance(v, dict)}}, indent=2))
