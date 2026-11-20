"""Compare actual source exposure/binding; never score scientific correctness."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, freeze, cases_freeze):
    for key, filename in (("protocol_sha256", "protocol.json"), ("baseline_manifest_sha256", "baseline-code-hashes.json")):
        if sha(root/filename) != freeze[key]:
            raise ValueError("Baseline freeze changed")
    for key, filename in (("case_protocol_sha256", "case-protocol.json"), ("cases_sha256", "cases.json"), ("settings_sha256", "settings.json")):
        if sha(root/filename) != cases_freeze[key]:
            raise ValueError("Case/settings freeze changed")
    manifests = {arm: json.loads((root/(arm+"-code-hashes.json")).read_text()) for arm in ("baseline", "candidate")}
    for arm, manifest in manifests.items():
        for filename, expected in manifest.items():
            if sha(root/(arm+"-code")/filename) != expected:
                raise ValueError("Frozen code changed: "+arm+" "+filename)
    # Original corrected fixtures are identical between the two test runs.
    fixture_manifest = json.loads((root/"fixture-corrected-code-hashes.json").read_text())
    for filename, expected in fixture_manifest.items():
        if sha(root/"test-code"/filename) != expected:
            raise ValueError("Corrected fixture snapshot changed")
    cases = {c["case_id"]: c for c in json.loads((root/"cases.json").read_text())}
    runs = {arm: json.loads((root/(arm+"-probe.json")).read_text()) for arm in manifests}
    if runs["baseline"]["grounding_instructions_sha256"] != runs["candidate"]["grounding_instructions_sha256"]:
        raise ValueError("Synthesis instructions changed")
    summary, details = {}, {}
    for arm, run in runs.items():
        rows = {r["case_id"]: r for r in run["cases"]}
        if rows.keys() != cases.keys() or len(rows) != len(run["cases"]):
            raise ValueError("Missing/duplicate probe results")
        if run["model_calls"] or run["network_calls"]:
            raise ValueError("Unexpected model/network call")
        counts = Counter()
        per_domain = {}
        arm_details = []
        for case_id, case in cases.items():
            row = rows[case_id]
            if row["status"] != "completed_component_probe":
                raise ValueError("Incomplete component probe")
            counts["cases"] += 1
            selected_ids = [int(s["index"]) for s in row["selected_sources"]]
            current_preserved = all(s in row["selected_sources"] for s in case["current_sources"])
            counts["nonempty_current_cases"] += bool(case["current_sources"])
            counts["current_preserved"] += current_preserved
            if not current_preserved or not row["archive_unchanged"] or not row["current_collector_unchanged"] or not row["output_draft_unchanged"]:
                raise ValueError("Current/archive/draft preservation failed")
            counts["expected_source_ids_match"] += selected_ids == case["expected_source_ids"]
            state = row["source_recovery"]
            if arm == "candidate":
                for key in ("recovered_ids", "missing_ids", "ambiguous_ids"):
                    if state[key] != case["expected_"+key]:
                        raise ValueError("Candidate lookup-state contract failed")
                counts["candidate_lookup_state_matches"] += 1
            if not case["expected_recovered_ids"]:
                counts["control_cases"] += 1
                counts["controls_without_archive_expansion"] += selected_ids == case["expected_source_ids"]
            counts["handler_calls"] += len(row["handler_calls"])
            publication = row["publication"]["claim_publication"]
            if publication["audit_status"] != "disabled" or publication["status"] != "unverified":
                raise ValueError("Publication audit/state unexpectedly changed")
            mapped = {old: s for s in publication["sources"] for old in s["original_indices"]}
            for unresolved in case["expected_missing_ids"] + case["expected_ambiguous_ids"]:
                counts["unresolved_label_observations"] += 1
                retained = unresolved not in mapped and ("["+str(unresolved)+"]") in row["publication_content"]
                counts["unresolved_retained_without_guessed_url"] += retained
                if not retained:
                    raise ValueError("Unresolved label remapped or deleted")
            expected_lookup = {int(s["index"]): s for s in case["archive_sources"]}
            exposed, linked = [], []
            for target in case["expected_recovered_ids"]:
                original = expected_lookup[target]
                counts["expected_prior_source_observations"] += 1
                evidence_exposed = any(any(s == original for s in call["sources"]) and
                    original["abstract"] in call["material"] for call in row["handler_calls"])
                binding = mapped.get(target)
                correct_link = bool(binding and binding["url"] == original["link"])
                counts["prior_source_exposed"] += evidence_exposed
                counts["prior_source_publication_binding"] += correct_link
                exposed.append(evidence_exposed); linked.append(correct_link)
                domain = per_domain.setdefault(case["domain"], {"observations": 0, "source_exposed": 0, "publication_binding": 0})
                domain["observations"] += 1; domain["source_exposed"] += evidence_exposed; domain["publication_binding"] += correct_link
            arm_details.append({"case_id": case_id, "selected_ids": selected_ids,
                "prior_source_exposed": exposed, "prior_source_linked": linked,
                "source_recovery": state, "handler_calls": len(row["handler_calls"])})
        if arm == "candidate" and counts["expected_source_ids_match"] != len(cases):
            raise ValueError("Candidate added/dropped an unexpected source")
        refetch = run["actual_installed_refetch"]
        if refetch["archive_count"] != 1 or refetch["returned_index"] != 1 or not refetch["original_abstract_preserved"] or not refetch["fetched_text_preserved"]:
            raise ValueError("Installed refetch ID/text preservation failed")
        summary[arm] = {"counts": dict(counts), "by_domain": per_domain,
            "actual_installed_refetch": {"returned_index": refetch["returned_index"],
                "current_source_count": len(refetch["current_sources"]), "current_url_count": len(refetch["current_urls"]),
                "archive_count": refetch["archive_count"], "original_and_fetched_text_preserved": True},
            "component_seconds_mean": statistics.mean(r["seconds"] for r in rows.values()),
            "model_calls": 0, "network_calls": 0}
        details[arm] = arm_details
    tests = {}
    for arm, filename in (("baseline", "baseline-corrected-fixture-tests.log"), ("candidate", "candidate-tests.log")):
        text = (root/filename).read_text()
        passed = re.search(r"(\d+) passed", text)
        failed = re.search(r"(\d+) failed", text)
        tests[arm] = {"passed": int(passed[1]) if passed else 0, "failed": int(failed[1]) if failed else 0,
                      "log_sha256": sha(root/filename),
                      "failed_test_names": [line.split("::",1)[1] for line in text.splitlines() if line.startswith("FAILED ") and "::" in line]}
    return {"status": "completed_installed_source_routing_comparison", "root": str(root),
        "scope": "Frozen development source-routing cases with original archived abstracts and synthetic drafts; no scientific assessment.",
        "freeze": freeze, "case_freeze": cases_freeze, "case_count": len(cases),
        "arms": summary, "case_details": details, "tests": tests,
        "test_scope": "78 shared corrected-fixture checks: baseline 76 pass/2 fail. Candidate additionally runs 8 new routing tests and 4 existing collector tests (90 total).",
        "runtime_changed_files": [name for name in manifests["baseline"] if "/tests/" not in name and manifests["baseline"][name] != manifests["candidate"][name]],
        "new_test_files": sorted(manifests["candidate"].keys()-manifests["baseline"].keys()),
        "grounding_instructions_sha256": runs["baseline"]["grounding_instructions_sha256"],
        "artifacts_sha256": {name: sha(root/name) for name in ["protocol.json", "case-protocol.json", "cases.json", "settings.json", "baseline-code-hashes.json", "candidate-code-hashes.json", "fixture-corrected-code-hashes.json", "baseline-probe.json", "candidate-probe.json", "baseline-probe-before-publication.json", "candidate-probe-before-publication.json", "test-wheel-hashes.json"]},
        "scientific_assessment": "not_performed",
        "unmeasured_endpoints": ["unsupported/contradicted scientific claims", "citation entailment", "report usefulness and obligation coverage", "fresh retrieval relevance/recall", "real-model latency/tokens", "representative cross-domain robustness"],
        "limitations": [
            "Exposed/linked source counts are routing contracts, not evidence that a draft claim is supported.",
            "Sources were previously inspected; frozen case variants cannot be called independent heldout generalization evidence.",
            "Recording writer uses actual native document construction/formatting but preserves draft verbatim. Native source reading/consistency/model generation are not exercised.",
            "Baseline missing new recovery metadata is unreported, never scored as semantic failure. Exposure is measured from actual source/text inputs.",
            "Candidate can activate an existing synthesis path on calls previously skipped; additional real-model cost/latency is unmeasured.",
            "Ambiguous index records remain unresolved, while current records are preserved. No title/keyword identity inference, source deletion or publication gate is added.",
            "Earlier 16-pair report results do not include this runtime change. Overall reliability improvement remains unproven.",
        ]}


if __name__ == "__main__":
    freeze = json.loads(Path("evaluation/source-recovery-freeze-20261111.json").read_text())
    cases_freeze = json.loads(Path("evaluation/source-recovery-cases-freeze-20261111.json").read_text())
    result = collect(Path(freeze["root"]), freeze, cases_freeze)
    Path("evaluation/source-recovery-results-20261111.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"status": result["status"], "arms": result["arms"], "tests": result["tests"]}, indent=2))
