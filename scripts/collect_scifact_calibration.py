"""Source-relative expert-label calibration, with all scheduled cases counted.

Collection does not change predictions, repair failed responses or tune prompts.
This is not a report-generation or retrieval effectiveness measurement.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

from evidence_eval_metrics import _bootstrap, _rate


GOLD_LABELS = ("SUPPORT", "CONTRADICT", "NEI")
PREDICTIONS = GOLD_LABELS + ("PARTIAL", "MISSING")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def classification(rows, gold, key):
    matrix = {label: {prediction: 0 for prediction in PREDICTIONS} for label in GOLD_LABELS}
    correct, families = [], []
    for case_id, target in gold.items():
        predicted = rows.get(case_id, {}).get(key, "MISSING")
        if predicted not in PREDICTIONS:
            raise ValueError("Unrecognized prediction")
        matrix[target["expected"]][predicted] += 1
        correct.append(int(predicted == target["expected"]))
        families.append(target["task_family"])
    n = len(gold)
    predicted_support = sum(row["SUPPORT"] for row in matrix.values())
    non_support = sum(sum(matrix[label].values()) for label in ("CONTRADICT", "NEI"))
    labelled = sum(matrix[label][p] for label in GOLD_LABELS for p in GOLD_LABELS)
    interval = _bootstrap(correct, families)
    interval["mean_accuracy"] = interval.pop("mean_delta")
    return {
        "confusion_gold_rows_prediction_columns": matrix,
        "all_scheduled_accuracy": _rate(sum(correct), n),
        "accuracy_document_cluster_bootstrap": interval,
        "three_class_prediction_coverage": _rate(labelled, n),
        "support_precision": _rate(matrix["SUPPORT"]["SUPPORT"], predicted_support),
        "recall_by_gold_label": {label: _rate(matrix[label][label], sum(matrix[label].values()))
                                 for label in GOLD_LABELS},
        "false_support_on_non_support": _rate(
            matrix["CONTRADICT"]["SUPPORT"] + matrix["NEI"]["SUPPORT"], non_support),
        "missing": sum(row["MISSING"] for row in matrix.values()),
        "partial_unmapped": sum(row["PARTIAL"] for row in matrix.values()),
    }


def validate_inputs(root, freeze):
    checks = {"protocol_sha256": "protocol.json", "code_manifest_sha256": "code-hashes.json",
              "cases_sha256": "cases.jsonl", "gold_sha256": "gold.jsonl"}
    for key, name in checks.items():
        if sha(root/name) != freeze[key]:
            raise ValueError("Frozen file mismatch: " + name)
    protocol = json.loads((root/"protocol.json").read_text())
    for key, name in (("cases_sha256", "cases.jsonl"), ("gold_sha256", "gold.jsonl"),
                      ("rubric_sha256", "rubric.txt")):
        if sha(root/name) != protocol[key]:
            raise ValueError("Protocol hash mismatch: " + name)
    for key, name in (("archive_sha256", "data.tar.gz"), ("claims_file_sha256", "claims_dev.jsonl"),
                      ("corpus_sha256", "corpus.jsonl")):
        if sha(root/name) != protocol["dataset"][key]:
            raise ValueError("Dataset hash mismatch: " + name)
    for manifest, directory in (("code-hashes.json", "code"), ("runner-hashes.json", "runner")):
        for name, expected in json.loads((root/manifest).read_text()).items():
            if sha(root/directory/name) != expected:
                raise ValueError("Frozen code mismatch: " + name)
    cases = {row["case_id"]: row for row in jsonl(root/"cases.jsonl")}
    gold_rows = jsonl(root/"gold.jsonl")
    gold = {row["case_id"]: row for row in gold_rows}
    if len(cases) != protocol["case_count"] or len(gold) != len(gold_rows) or cases.keys() != gold.keys():
        raise ValueError("Missing or duplicate case/gold IDs")
    original = {row["id"]: row for row in jsonl(root/"claims_dev.jsonl")}
    corpus = {str(row["doc_id"]): row for row in jsonl(root/"corpus.jsonl")}
    for case_id, target in gold.items():
        claim = original[target["original_claim_id"]]
        doc_id = str(target["doc_id"])
        source = corpus[doc_id]
        case = cases[case_id]
        if case["claim"] != claim["claim"] or len(case["sources"]) != 1:
            raise ValueError("Original claim/source count changed")
        given = case["sources"][0]
        if given["abstract"] != " ".join(source["abstract"]) or given["title"] != source["title"]:
            raise ValueError("Original abstract/title changed")
        if target["expected"] == "NEI":
            if claim["evidence"] or [str(x) for x in claim["cited_doc_ids"]] != [doc_id]:
                raise ValueError("NEI lacks annotated single cited-document provenance")
        else:
            rationales = claim["evidence"][doc_id]
            if {r["label"] for r in rationales} != {target["expected"]}:
                raise ValueError("Label differs from expert annotation")
            if target["rationales"] != rationales:
                raise ValueError("Gold rationales changed")
    if dict(Counter(r["expected"] for r in gold.values())) != protocol["label_counts"]:
        raise ValueError("Stratum counts changed")
    return protocol, cases, gold


def collect(root, freeze):
    protocol, cases, gold = validate_inputs(root, freeze)
    settings = [json.loads((root/("settings-"+str(i)+".json")).read_text()) for i in (0, 1)]
    if settings[0] != settings[1]:
        raise ValueError("Shards have unmatched model settings")
    public = settings[0].copy()
    digest = public.pop("settings_sha256")
    if hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest() != digest:
        raise ValueError("Settings digest mismatch")
    expected_paths = {arm+"-"+case_id+".json" for arm in protocol["arms"] for case_id in cases}
    actual = {p.name for p in (root/"outputs").glob("*.json")}
    if actual-expected_paths:
        raise ValueError("Unexpected output files")
    arms, by_arm, artifact_hashes = {}, {}, {}
    native_reconciliation = {"raw_to_parsed_status_counts": Counter(), "changed_cases": []}
    for arm in protocol["arms"]:
        rows = {}
        for case_id in cases:
            path = root/"outputs"/(arm+"-"+case_id+".json")
            if not path.exists():
                continue
            row = json.loads(path.read_text())
            if row["case_id"] != case_id or row["arm"] != arm or row["settings_sha256"] != digest:
                raise ValueError("Result identity/settings mismatch")
            base = path.with_suffix("")
            prompt = Path(str(base)+".prompt.txt")
            if sha(prompt) != row["prompt_sha256"]:
                raise ValueError("Prompt hash mismatch")
            if cases[case_id]["sources"][0]["abstract"] not in prompt.read_text():
                # Assessor serializes newlines etc. through JSON, native emits plain text.
                escaped = json.dumps(cases[case_id]["sources"][0]["abstract"], ensure_ascii=False)[1:-1]
                if escaped not in prompt.read_text():
                    raise ValueError("Complete source absent from prompt")
            for artifact in (path, prompt, Path(str(base)+".response.txt")):
                if artifact.exists():
                    artifact_hashes[str(artifact.relative_to(root))] = sha(artifact)
            if arm == "native_review_first_pass" and row["status"] == "completed_component_assessment":
                raw = Path(str(base)+".response.txt").read_text()
                obj = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I))
                entries = [u for u in obj["issues"] if u.get("claim_id") == 0]
                if len(entries) != 1:
                    raise ValueError("Native raw status cannot be localized")
                before, after = entries[0].get("status"), row.get("native_status")
                native_reconciliation["raw_to_parsed_status_counts"][str(before)+" -> "+str(after)] += 1
                if before != after:
                    native_reconciliation["changed_cases"].append({"case_id": case_id, "raw_status": before,
                        "parsed_status": after, "gold": gold[case_id]["expected"]})
            rows[case_id] = row
        by_arm[arm] = rows
        valid = [r for r in rows.values() if r["status"] == "completed_component_assessment"]
        times = sorted(r["latency_seconds"] for r in rows.values())
        usage = [r["usage"] for r in rows.values() if isinstance(r.get("usage"), dict)]
        arms[arm] = {
            "scheduled": len(cases), "result_files": len(rows), "component_parse_completed": len(valid),
            "invalid_or_failed": len(rows)-len(valid), "absent_output_files": len(cases)-len(rows),
            "errors": dict(Counter(r.get("error_type") for r in rows.values() if r.get("error_type"))),
            "raw": classification(rows, gold, "raw_prediction"),
            "quote_checked": classification(rows, gold, "prediction"),
            "fully_covered_claims": sum(r.get("claim_text_fully_covered") is True for r in rows.values()) if arm == "existing_report_assessor" else None,
            "decomposed_units_with_exact_quotes": sum(r.get("units_with_exact_quote", 0) for r in rows.values()) if arm == "existing_report_assessor" else None,
            "decomposed_unit_quote_denominator": sum(r.get("exact_quote_denominator", 0) for r in rows.values()) if arm == "existing_report_assessor" else None,
            "native_claims_with_exact_quotes": sum(r.get("exact_quote_valid") is True for r in rows.values()) if arm == "native_review_first_pass" else None,
            "native_statuses": dict(Counter(r.get("native_status") for r in rows.values())) if arm == "native_review_first_pass" else None,
            "model_calls_attempted": len(rows), "recorded_usage_calls": len(usage),
            "tokens": {k: sum(u.get(k, 0) for u in usage) for k in ("input_tokens", "output_tokens", "total_tokens")},
            "latency_seconds": {"n": len(times), "mean": statistics.mean(times) if times else None,
                                "p50": statistics.median(times) if times else None,
                                "p95_nearest_rank": times[max(0, (95*len(times)+99)//100-1)] if times else None},
        }
    a, b = protocol["arms"]
    paired = {}
    for key in ("raw_prediction", "prediction"):
        # Includes missing/partial as incorrect, including absent result files.
        deltas = [int(by_arm[b].get(cid, {}).get(key) == g["expected"]) -
                  int(by_arm[a].get(cid, {}).get(key) == g["expected"]) for cid, g in gold.items()]
        paired[key] = {"direction": b+" minus "+a,
                       **_bootstrap(deltas, [g["task_family"] for g in gold.values()])}
    disagreements = {arm: [{"case_id": cid, "expected": gold[cid]["expected"],
                           "raw": row["raw_prediction"], "quote_checked": row["prediction"]}
                          for cid, row in by_arm[arm].items()
                          if row["raw_prediction"] != gold[cid]["expected"] or row["prediction"] != gold[cid]["expected"]]
                     for arm in protocol["arms"]}
    return {
        "status": "complete_component_calibration" if actual == expected_paths else "incomplete_component_calibration",
        "root": str(root), "freeze": freeze, "settings": settings[0], "case_count": len(cases),
        "source_document_clusters": len({g["task_family"] for g in gold.values()}),
        "gold_counts": dict(Counter(g["expected"] for g in gold.values())),
        "verified_frozen_code_files": len(json.loads((root/"code-hashes.json").read_text())),
        "arms": arms, "paired_accuracy_differences": paired, "disagreements": disagreements,
        "native_status_reconciliation": native_reconciliation,
        "artifact_sha256": artifact_hashes,
        "assessment_provenance": "Independent previously published expert labels; no new independent human assessment of model disagreements.",
        "limitations": protocol["limitations"] + [
            "The two components use different prompts and output formats; neither is an agent baseline/candidate comparison.",
            "Exact quotes establish localization, not entailment. Quote guards are offline diagnostics, not production publication gates.",
            "A missing native root evidence quote may coexist with atom-level evidence; raw and quote-checked verdicts are reported separately.",
            "Native parse_review applies its existing atom/status reconciliation; no new claim extraction or revision is tested.",
            "Confidence intervals describe this public balanced sample. Document clusters do not model shared topic dependence or training contamination.",
            "No retrieval/source recall, long-form usefulness, generation coverage or cross-domain robustness endpoint is measured here.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text())
    result = collect(Path(freeze["root"]), freeze)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n")
    print(json.dumps({"status": result["status"], "cases": result["case_count"],
                      "arms": {a: {"raw_accuracy": r["raw"]["all_scheduled_accuracy"],
                                    "quote_checked_accuracy": r["quote_checked"]["all_scheduled_accuracy"]}
                               for a, r in result["arms"].items()}}, indent=2))


if __name__ == "__main__":
    main()
