"""Collect a frozen metadata replay without claiming scientific effectiveness."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, freeze):
    for key, name in (("protocol_sha256", "protocol.json"), ("baseline_manifest_sha256", "baseline-code-hashes.json"),
                      ("records_sha256", "records.json"), ("contracts_sha256", "contracts.json")):
        if sha(root/name) != freeze[key]:
            raise ValueError("Frozen input mismatch: "+name)
    manifests = {arm: json.loads((root/(arm+"-code-hashes.json")).read_text()) for arm in ("baseline", "candidate")}
    for arm, manifest in manifests.items():
        for name, expected in manifest.items():
            if sha(root/(arm+"-code")/name) != expected:
                raise ValueError("Frozen code mismatch: "+arm+" "+name)
    if manifests["baseline"].keys() != manifests["candidate"].keys():
        raise ValueError("Source trees have unmatched file sets")
    protocol = json.loads((root/"protocol.json").read_text())
    for origin in protocol["records"]:
        if sha(root/origin["raw_path"]) != origin["sha256"]:
            raise ValueError("Archived official record changed")
    runs = {arm: json.loads((root/(arm+"-result.json")).read_text()) for arm in manifests}
    baseline, candidate = runs["baseline"], runs["candidate"]
    n = len(protocol["records"])
    for arm, run in runs.items():
        if run["status"] != "completed_component_replay" or len(run["real"]) != n:
            raise ValueError("Incomplete installed replay")
        if run["model_calls"] or run["network_calls"]:
            raise ValueError("Unexpected external call")
    if baseline["grounding_instructions_sha256"] != candidate["grounding_instructions_sha256"]:
        raise ValueError("Synthesis instructions changed")
    if [r["id"] for r in baseline["real"]] != [r["id"] for r in candidate["real"]]:
        raise ValueError("Record IDs/order changed")
    changed_states = []
    statuses = {}
    source_equal = text_equal = complete_abstracts = provided_localized = provided_count = 0
    for b, c in zip(baseline["real"], candidate["real"]):
        source_equal += b["source"] == c["source"]
        text_equal += b["document_text"] == c["document_text"]
        complete_abstracts += bool(c["source"].get("abstract")) and all(c["source"]["abstract"] in r["material"] for r in (b, c))
        for f in c["card"]["fields"].values():
            if f["status"] == "provided_metadata":
                provided_count += 1
                provided_localized += f["source_key"] in c["source"] and c["source"][f["source_key"]] == f["value"]
        before, after = b["classified"]["peer_review_status"], c["classified"]["peer_review_status"]
        if before != after:
            changed_states.append({"id": b["id"], "before": before, "after": after})
    for arm, run in runs.items():
        statuses[arm] = {
            "peer_review_statuses": dict(Counter(r["classified"]["peer_review_status"] for r in run["real"])),
            "card_field_statuses": dict(Counter(f["status"] for r in run["real"] for f in r["card"]["fields"].values())),
            "requested_default_field_statuses": dict(Counter(r["card"]["fields"][key]["status"] for r in run["real"]
                for key in ("title", "authors", "journal", "year", "language", "study_type", "platform", "technology", "population", "sample_size", "groups", "outcome"))),
            "material_chars": sum(len(r["material"]) for r in run["real"]),
            "component_seconds_single_replay": run["component_seconds"],
        }
    synthetic = {arm: {r["case_id"]: r for r in run["synthetic"]} for arm, run in runs.items()}
    contracts = json.loads((root/"contracts.json").read_text())
    syn = {}
    for case in contracts:
        key, source = case["case_id"], case["source"]
        b, c = synthetic["baseline"][key], synthetic["candidate"][key]
        syn[key] = {"before_peer_review": b["classified"]["peer_review_status"],
                    "after_peer_review": c["classified"]["peer_review_status"],
                    "before_fields": b["card"]["fields"], "after_fields": c["card"]["fields"],
                    "before_document_metadata": b["document_metadata"], "after_document_metadata": c["document_metadata"],
                    "before_material_chars": len(b["material"]), "after_material_chars": len(c["material"])}
        if key == "synthetic_aliases":
            for field in case["requested_fields"]:
                if c["card"]["fields"][field]["status"] != "unknown":
                    raise ValueError("Candidate inferred an unstated canonical field")
            for field, value in source.items():
                if field != "index" and c["card"]["fields"][field]["value"] != value:
                    raise ValueError("Supplied original metadata lost")
            for field in ("population", "groups", "sample_size", "platform", "technology"):
                if c["document_metadata"][field] is not None:
                    raise ValueError("Native reader still infers canonical scientific fields")
            for field in ("species", "cohort", "n", "instrument", "method"):
                if c["document_metadata"]["additional_source_metadata"][field] != source[field]:
                    raise ValueError("Original metadata absent from native document")
                if json.dumps(field)+": "+json.dumps(source[field]) not in c["material"]:
                    raise ValueError("Original metadata absent from native material")
        if key == "synthetic_zero":
            if c["document_metadata"]["sample_size"] != 0 or c["document_metadata"]["groups"] is not False:
                raise ValueError("Zero/false value lost in native document")
            if "Sample-size metadata: 0" not in c["material"] or "Groups metadata: False" not in c["material"]:
                raise ValueError("Zero/false value lost in material")
    if source_equal != n or text_equal != n or complete_abstracts != n or provided_localized != provided_count:
        raise ValueError("Source preservation/localization contract failed")
    preservation = json.loads((root/"v1-preservation.json").read_text())
    for name, expected in preservation["sha256"].items():
        if sha(root/name) != expected:
            raise ValueError("Preserved first candidate artifact changed")
    first = json.loads((root/"comparison-v1.json").read_text())
    return {"status": "completed_installed_component_comparison", "freeze": freeze,
            "scope": "Metadata handling only; no independent scientific gold or report-quality endpoint.",
            "real_records": n, "previously_inspected_real_records": 8, "synthetic_contracts": len(contracts),
            "source_payloads_identical": {"numerator": source_equal, "denominator": n},
            "native_document_text_identical": {"numerator": text_equal, "denominator": n},
            "complete_supplied_abstract_in_both_materials": {"numerator": complete_abstracts, "denominator": n},
            "provided_candidate_card_values_trace_to_source_keys": {"numerator": provided_localized, "denominator": provided_count},
            "arms": statuses, "peer_review_state_changes": changed_states, "synthetic_diagnostics": syn,
            "code_files_verified_per_arm": len(manifests["baseline"]),
            "changed_snapshot_files": [name for name in manifests["baseline"] if manifests["baseline"][name] != manifests["candidate"][name]],
            "unchanged_synthesis_instructions_sha256": baseline["grounding_instructions_sha256"],
            "first_candidate_preserved": {"artifacts": preservation,
                "material_chars": first["arms"]["candidate"]["material_chars"],
                "final_material_chars": statuses["candidate"]["material_chars"],
                "change": "Remove exact duplicate bibliographic data and redundant unknown-state provenance headers; differing values remain visible. No semantic or report-output tuning."},
            "network_calls_during_replay": 0, "model_calls": 0,
            "artifacts_sha256": {name: sha(root/name) for name in ["protocol.json", "baseline-code-hashes.json", "candidate-code-hashes.json", "records.json", "contracts.json", "baseline-result.json", "candidate-result.json"]},
            "limitations": protocol["limits"] + [
                "Metadata contract correction is not report effectiveness. Independent source/claim assessment remains necessary.",
                "Unmodified record IDs and acquired text do not establish retrieval recall, evidence selection or usefulness.",
                "Original metadata is exposed under separate keys. The model may still misinterpret it; downstream usefulness and context-budget regressions are unmeasured.",
                "Original-key headers can increase source-material length on sources with additional fields. Component timings exclude install/import and do not measure model latency.",
                "Explicit peer_reviewed booleans are supplied assertions with provenance, not independently verified peer-review evidence.",
            ]}


if __name__ == "__main__":
    freeze = json.loads(Path("evaluation/metadata-unknowns-freeze-20261110.json").read_text())
    result = collect(Path(freeze["root"]), freeze)
    Path("evaluation/metadata-unknowns-results-20261110.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: result[k] for k in ("status", "real_records", "arms", "peer_review_state_changes")}, indent=2))
