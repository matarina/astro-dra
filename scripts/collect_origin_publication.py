"""Collect metadata contracts and native regression costs without efficacy claims."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    for name, digest in json.loads((root / "freeze.json").read_text())["sha256"].items():
        if sha(root / name) != digest:
            raise ValueError("Frozen input changed: " + name)
    generation_freeze = root / "generation-artifacts-freeze.json"
    if generation_freeze.exists():
        for name, digest in json.loads(generation_freeze.read_text())["sha256"].items():
            if sha(root / name) != digest:
                raise ValueError("Generation artifact changed: " + name)
    cfg = json.loads((root / "experiment.json").read_text())
    probes = {arm: json.loads((root / (arm + "-probe.json")).read_text()) for arm in cfg["arms"]}
    if (root / "reason-probe.json").exists():
        probes["reason_followup_not_model_tested"] = json.loads((root / "reason-probe.json").read_text())
    metrics = {}
    reference = probes["baseline"]["cases"]
    for arm, probe in probes.items():
        rows = probe["cases"]
        metrics[arm] = {"cases": len(rows), "metadata_contract": sum(r["metadata_contract"] for r in rows),
                        "sources_unchanged": sum(r["source_unchanged"] for r in rows),
                        "drafts_preserved": sum(r["draft_preserved"] for r in rows),
                        "native_text_same_as_baseline": sum(a["native_text"] == b["native_text"] for a, b in zip(rows, reference)),
                        "identity_state_same_as_baseline": sum(a["classified"]["identity_status"] == b["classified"]["identity_status"] for a, b in zip(rows, reference)),
                        "publication_state_same_as_baseline": sum(a["classified"]["publication_state"] == b["classified"]["publication_state"] for a, b in zip(rows, reference)),
                        "grounding_instructions_sha256": probe["grounding_instructions_sha256"]}
    observations = []
    for case in cfg["cases"]:
        sources = json.loads((root / case["source_pack"]).read_text())
        setting_hashes = set()
        for arm in cfg["arms"]:
            row = json.loads((root / arm / (case["case_id"] + ".json")).read_text())
            calls = json.loads((root / arm / (case["case_id"] + ".calls.json")).read_text())
            setting_hashes.add(row["settings_sha256"])
            if row["source_pack_sha256"] != case["source_pack_sha256"]:
                raise ValueError("Source mismatch")
            identifier = hashlib.sha256(("origin-publication-" + arm + "-" + case["case_id"]).encode()).hexdigest()[:32]
            folder = root / arm / "traces" / identifier
            folder.stat()
            prompts = []
            for log in folder.rglob("events.jsonl"):
                for line in log.read_text().splitlines():
                    event = json.loads(line)
                    if event.get("status") != "recorded":
                        continue
                    raw = gzip.open(log.parent / event["file"], "rb").read()
                    if len(raw) != event["bytes"] or hashlib.sha256(raw).hexdigest() != event["sha256"]:
                        raise ValueError("Trace payload changed")
                    if event["stage"] == "writer_request":
                        prompts.append(json.loads(raw)["prompt"])
            if not prompts:
                raise ValueError("Missing actual writer prompt")
            actual = row.get("sources", [])
            publication = row.get("publication", {}).get("claim_publication", {})
            observations.append({"arm": arm, "case_id": case["case_id"], "family": case["task_family"],
                "domain": case["domain"], "status": row["status"],
                "sources_preserved_recomputed": len(actual) == len(sources) and all(all(a.get(k) == v for k, v in b.items()) for a, b in zip(actual, sources)),
                "source_contexts": len(sources),
                "exact_contexts_in_writer": sum(bool(s.get("content")) and any(s["content"] in p for p in prompts) for s in sources),
                "timed_finalization_seconds": row["latency_seconds"], "logical_calls": len(calls),
                "returned_total_tokens": sum((c.get("usage") or {}).get("total_tokens", 0) for c in calls),
                "calls_missing_usage": sum("total_tokens" not in (c.get("usage") or {}) for c in calls),
                "publication_status": publication.get("status"), "audit_status": publication.get("audit_status"),
                "settings_sha256": row["settings_sha256"], "source_pack_sha256": row["source_pack_sha256"],
                "scientific_error_rate": "not established; this collection does not label scientific meaning"})
        if len(setting_hashes) != 1:
            raise ValueError("Unmatched settings")
    totals = []
    for arm in cfg["arms"]:
        rows = [r for r in observations if r["arm"] == arm]
        totals.append({"arm": arm, "scheduled_reports": len(rows),
                       "completed": sum(r["status"] == "completed" for r in rows),
                       "source_contexts": sum(r["source_contexts"] for r in rows),
                       "exact_contexts_in_writer": sum(r["exact_contexts_in_writer"] for r in rows),
                       "sources_preserved_reports": sum(r["sources_preserved_recomputed"] for r in rows),
                       "mean_timed_finalization_seconds": statistics.mean(r["timed_finalization_seconds"] for r in rows),
                       "returned_total_tokens": sum(r["returned_total_tokens"] for r in rows),
                       "logical_calls": sum(r["logical_calls"] for r in rows),
                       "publication_statuses": dict(Counter(r["publication_status"] for r in rows)),
                       "audit_statuses": dict(Counter(r["audit_status"] for r in rows))})
    reviews = None
    if (root / "blind-review.json").exists():
        review = json.loads((root / "blind-review.json").read_text())
        mapping = {m["blind_id"]: m for m in json.loads((root / "blind-review-map.json").read_text())}
        lookup = {r["blind_id"]: r for r in json.loads((root / "blind-review-input.json").read_text())}
        for r in review["reviews"]:
            body = lookup[r["blind_id"]]["body"]
            for field in ["scientific_concerns", "publication_metadata_assertions", "application_scope_concerns"]:
                for item in r.get(field, []):
                    if item["draft_quote"] not in body:
                        raise ValueError("Review quote not located: " + r["blind_id"])
        reviews = {"status": "Implementing-AI arm-blinded reading, not independent human expertise or comprehensive scientific claim annotation",
                   "reviewed_reports": len(review["reviews"]), "arms": []}
        for arm in cfg["arms"]:
            rows = [r for r in review["reviews"] if mapping[r["blind_id"]]["arm"] == arm]
            labels = Counter(i["label"] for r in rows for i in r.get("publication_metadata_assertions", []))
            reviews["arms"].append({"arm": arm, "reports": len(rows),
                "useful_core_synthesis_present": sum(r["useful_synthesis_present"] for r in rows),
                "scheduled_previously_frozen_core_targets": len(rows) * 2,
                "reviewed_complete_core_targets": sum(v == "complete" for r in rows for v in r["core_target_coverage"]),
                "selected_publication_assertion_labels": dict(labels)})
    reasons = []
    for arm in ["candidate", "reason"]:
        path = root / (arm + "-reason-controls.json")
        if path.exists():
            rows = json.loads(path.read_text())["cases"]
            reasons.append({"arm": arm, "cases": len(rows), "matches": sum(r["matched"] for r in rows),
                            "native_text_preserved": sum(r["native_text_preserved"] for r in rows),
                            "complete_text_in_material": sum(r["content_in_material"] for r in rows)})
    result = {"status": "metadata_contract_and_archived_case_regression_not_overall_effectiveness",
              "probe_metrics": metrics, "report_totals": totals, "reports": observations,
              "bounded_implementer_review": reviews,
              "reason_followup_contracts_not_model_tested": reasons,
              "tests": json.loads((root / "test-results.json").read_text()) if (root / "test-results.json").exists() else None,
              "limits": ["Previously inspected nine API records and transformed controls, not new independent scientific gold.",
                         "Six known source/question families, one original variant per arm, single shared-load trial; no fresh heldout effectiveness result.",
                         "Separate identity, artifact/document type, publication and peer review states; a bound API receipt does not bind page contents or establish scientific support.",
                         "No live retrieval, overall unsupported/contradicted rate or independent expert assessment established. Returned usage is not billed wire calls."]}
    (root / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"probe_metrics": metrics, "report_totals": totals}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    collect(parser.parse_args().root)
