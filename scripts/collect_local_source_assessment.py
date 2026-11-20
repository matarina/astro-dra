"""Summarize auxiliary local-judge labels without turning them into gold."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean


def collect(root, original):
    protocol = json.loads((root / "protocol.json").read_text())
    for relative, expected in protocol["drafts_sha256"].items():
        if hashlib.sha256((original / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Preserved draft changed after assessment protocol freeze")
    for name, field in (("sources.json", "source_pool_sha256"),
                        ("experiment.json", "experiment_sha256")):
        if hashlib.sha256((original / name).read_bytes()).hexdigest() != protocol[field]:
            raise ValueError("Source pool or task configuration changed")
    totals = {}
    rows = []
    matches = disagreements = 0
    for key in protocol["order"]:
        arm, caseid = key.split("/")
        filename = arm + "-" + caseid + ".json"
        path = root / filename
        if not path.exists():
            rows.append({"arm": arm, "case_id": caseid, "status": "missing"})
            continue
        ann = json.loads(path.read_text())
        row = {"arm": arm, "case_id": caseid, "status": ann["status"],
               "latency_seconds": ann["latency_seconds"], "usage": ann.get("usage")}
        if ann["status"] == "annotated_model_assisted":
            claims = ann["claims"]
            row.update(claims=len(claims), grounding=dict(Counter(c["grounding"] for c in claims)),
                       raw_grounding=dict(Counter(c.get("assessor_grounding", c["grounding"]) for c in claims)),
                       entailment_true=sum(c.get("citation_entails") is True for c in claims),
                       entailment_false=sum(c.get("citation_entails") is False for c in claims),
                       entailment_missing=sum(c.get("citation_entails") is None for c in claims),
                       usefulness=ann.get("usefulness"))
            old_path = original / "assessment" / filename
            if old_path.exists():
                old = json.loads(old_path.read_text())
                # Exact identical substrings only. Different decompositions
                # cannot be counted as matched semantic claim units.
                old_claims = {c["text"]: c for c in old.get("claims", [])}
                row["exact_text_matches"] = []
                for c in claims:
                    if c["text"] in old_claims:
                        o = old_claims[c["text"]]
                        a = o.get("assessor_grounding", o["grounding"])
                        b = c.get("assessor_grounding", c["grounding"])
                        row["exact_text_matches"].append({"text": c["text"],
                            "original_raw_label": a, "local_raw_label": b,
                            "labels_disagree": a != b})
                        matches += 1
                        disagreements += a != b
        rows.append(row)
    for arm in ("baseline", "candidate"):
        valid = [r for r in rows if r["arm"] == arm and r["status"] == "annotated_model_assisted"]
        counts = Counter()
        raw_counts = Counter()
        for row in valid:
            counts.update(row["grounding"])
            raw_counts.update(row["raw_grounding"])
        totals[arm] = {"scheduled": sum(r["arm"] == arm for r in rows),
                      "valid_annotations": len(valid), "claims": sum(counts.values()),
                      "grounding_after_quote_validation": dict(counts),
                      "raw_assessor_grounding": dict(raw_counts),
                      "entailment": {k: sum(r["entailment_" + k] for r in valid)
                                      for k in ("true", "false", "missing")},
                      "usefulness_values": [r["usefulness"] for r in valid],
                      "mean_latency_seconds": mean(r["latency_seconds"] for r in valid) if valid else None,
                      "prompt_tokens": sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in valid),
                      "completion_tokens": sum((r.get("usage") or {}).get("completion_tokens", 0) for r in valid)}
    paths = [root / "protocol.json"] + [root / (k.replace("/", "-") + ".json")
                                       for k in protocol["order"]]
    return {"status": "auxiliary_assessment_not_effectiveness_validation",
            "independence": protocol["independence"], "arms": totals, "reports": rows,
            "exact_text_matched_units": matches, "raw_label_disagreements_on_exact_matches": disagreements,
            "limitations": ["Three direct task families only; no representative or sealed held-out sample.",
                            "Fresh claim decomposition differs by assessor; aggregate label counts are not claim-level agreement.",
                            "Exact quote existence is a structural check, not semantic entailment.",
                            "No independent expert adjudication; zero adverse model labels is not zero hallucination.",
                            "Local judge latency under shared-GPU contention is not report-generation latency."],
            "files_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths if p.exists()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.assessment, args.experiment)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result["arms"], indent=2))


if __name__ == "__main__":
    main()
