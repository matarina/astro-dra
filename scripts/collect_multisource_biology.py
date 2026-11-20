"""Collect fixed-panel observations without converting them into efficacy claims."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def writer_prompts(root, arm, case):
    identifier = hashlib.sha256(("multisource-biology-" + arm + "-" + case).encode()).hexdigest()[:32]
    prompts = []
    folder = root / arm / "traces" / identifier
    folder.stat()  # Fail on missing/inaccessible traces instead of reporting zero exposure.
    for path in folder.rglob("events.jsonl"):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event.get("status") != "recorded":
                continue
            raw = gzip.open(path.parent / event["file"], "rb").read()
            if len(raw) != event["bytes"] or hashlib.sha256(raw).hexdigest() != event["sha256"]:
                raise ValueError("Trace changed")
            if event["stage"] == "writer_request":
                prompts.append(json.loads(raw)["prompt"])
    if not prompts:
        raise ValueError("Actual writer prompt missing or inaccessible: " + str(folder))
    return prompts


def collect(root):
    cfg = json.loads((root / "experiment.json").read_text())
    for freeze in ["freeze.json", "generation-artifacts-freeze.json", "trace-artifacts-freeze.json"]:
        for name, expected in json.loads((root / freeze).read_text())["sha256"].items():
            if sha(root / name) != expected:
                raise ValueError("Frozen bytes changed: " + name)
    observations = []
    for case in cfg["cases"]:
        pack = json.loads((root / case["source_pack"]).read_text())
        pair = []
        for arm in ["baseline", "candidate"]:
            path = root / arm / (case["case_id"] + ".json")
            row = json.loads(path.read_text())
            calls = json.loads((root / arm / (case["case_id"] + ".calls.json")).read_text())
            prompts = writer_prompts(root, arm, case["case_id"])
            actual = row.get("sources", [])
            fields_preserved = len(actual) == len(pack) and all(
                all(a.get(k) == v for k, v in b.items()) for a, b in zip(actual, pack))
            observed = {"case_id": case["case_id"], "family": case["task_family"], "domain": case["domain"],
                        "variant": case["variant"], "arm": arm, "status": row["status"],
                        "settings_sha256": row["settings_sha256"], "source_pack_sha256": row["source_pack_sha256"],
                        "sources_preserved_recomputed": fields_preserved, "source_contexts": len(pack),
                        "distinct_source_urls": len({s["link"] for s in pack}),
                        "exact_contexts_in_writer": sum(bool(s["content"]) and any(s["content"] in p for p in prompts) for s in pack),
                        "stripped_contexts_in_writer": sum(bool(s["content"].strip()) and any(s["content"].strip() in p for p in prompts) for s in pack),
                        "writer_calls": len(prompts), "logical_calls": len(calls), "latency_seconds": row["latency_seconds"],
                        "returned_total_tokens": sum((c.get("usage") or {}).get("total_tokens", 0) for c in calls),
                        "calls_missing_token_usage": sum(not isinstance(c.get("usage"), dict) or "total_tokens" not in c["usage"] for c in calls),
                        "publication_status": row.get("publication", {}).get("claim_publication", {}).get("status"),
                        "audit_status": row.get("publication", {}).get("claim_publication", {}).get("audit_status"),
                        "word_count_posthoc": len(row.get("body", "").split()),
                        "all_claim_unsupported_or_contradicted": "unestablished; bounded targets only",
                        "retrieval_recall": "not measured; frozen author-provided context pool"}
            assess_path = root / "assessment" / (arm + "-" + case["case_id"] + ".json")
            if assess_path.exists():
                assessment = json.loads(assess_path.read_text())
                observed["assessment_status"] = assessment["status"]
                targets = assessment.get("targets", [])
                observed["scheduled_scientific_targets"] = 2
                observed["raw_target_coverage"] = dict(Counter(t["coverage"] for t in targets))
                observed["localized_complete_targets"] = sum(t["coverage"] == "complete" and t["draft_quote_localized"] for t in targets)
                observed["quote_eligible_entailed_targets"] = sum(t["grounding"] == "entailed" and t["mechanical_support_eligible"] for t in targets)
                observed["raw_target_grounding"] = dict(Counter(t["grounding"] for t in targets))
                observed["bound_assisted_positive_citations"] = sum(t.get("citation_entails") == "yes" and t["mechanical_citation_eligible"] for t in targets)
                observed["invalid_annotation_items"] = len(assessment.get("invalid", []))
                rating = assessment.get("raw_annotation", {}).get("usefulness", {}).get("rating")
                observed["assisted_usefulness"] = rating if type(rating) is int and 1 <= rating <= 5 else None
            else:
                observed["assessment_status"] = "not_assessed"
            pair.append(observed)
            observations.append(observed)
        if pair[0]["settings_sha256"] != pair[1]["settings_sha256"] or pair[0]["source_pack_sha256"] != pair[1]["source_pack_sha256"]:
            raise ValueError("Unmatched pair")
    groups = defaultdict(list)
    for row in observations:
        groups[(row["domain"], row["arm"])].append(row)
    summaries = []
    for (domain, arm), rows in sorted(groups.items()):
        ratings = [r["assisted_usefulness"] for r in rows if r.get("assisted_usefulness") is not None]
        summaries.append({"domain": domain, "arm": arm, "scheduled_reports": len(rows),
                          "families": len({r["family"] for r in rows}), "completed": sum(r["status"] == "completed" for r in rows),
                          "source_contexts": sum(r["source_contexts"] for r in rows),
                          "exact_contexts_in_writer": sum(r["exact_contexts_in_writer"] for r in rows),
                          "stripped_contexts_in_writer": sum(r["stripped_contexts_in_writer"] for r in rows),
                          "source_fields_preserved_reports": sum(r["sources_preserved_recomputed"] for r in rows),
                          "mean_latency_seconds": statistics.mean(r["latency_seconds"] for r in rows),
                          "returned_total_tokens": sum(r["returned_total_tokens"] for r in rows),
                          "logical_calls": sum(r["logical_calls"] for r in rows),
                          "assessment_statuses": dict(Counter(r["assessment_status"] for r in rows)),
                          "scheduled_targets": len(rows) * 2,
                          "localized_complete_targets": sum(r.get("localized_complete_targets", 0) for r in rows),
                          "quote_eligible_entailed_targets": sum(r.get("quote_eligible_entailed_targets", 0) for r in rows),
                          "bound_assisted_positive_citations": sum(r.get("bound_assisted_positive_citations", 0) for r in rows),
                          "invalid_annotation_items": sum(r.get("invalid_annotation_items", 0) for r in rows),
                          "assisted_usefulness_denominator": len(ratings),
                          "mean_assisted_usefulness": statistics.mean(ratings) if ratings else None})
    cost_path = root / "assessment-cost.json"
    result = {"status": "fixed_source_purposive_public_panel_not_overall_effectiveness", "observations": observations,
              "domain_summaries": summaries, "paired_cases": len(cfg["cases"]), "family_count": 6,
              "assessment_overhead": json.loads(cost_path.read_text()) if cost_path.exists() else None,
              "limits": ["Same-backbone assisted labels are not independent expert judgments. Quotation localization and citation ID binding do not prove entailment.",
                         "Only two provisional scientific targets per family; other unsupported/contradicted claims remain unmeasured.",
                         "Author context provenance can be summarized; no actual full-paper truth or retrieval recall established.",
                         "Single shared-load trial, fixed model alias not frozen remote weights, returned usage not billable/wire calls.",
                         "One sequencing-adjacent question; general bioinformatics robustness unproven. One family in most domains; no precise population confidence interval justified.",
                         "Comparison is cumulative127-vs170 code, excluding the later draft-preservation change. No individual patch attribution."]}
    (root / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"paired_cases": result["paired_cases"], "domain_summaries": summaries}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    collect(parser.parse_args().root)
