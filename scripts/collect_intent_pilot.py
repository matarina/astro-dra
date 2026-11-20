"""Paired fixed-source finalization evidence, with explicit missing labels."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from evidence_eval_metrics import paired


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    cfg = json.loads((root / "experiment.json").read_text())
    runs = {}
    integrity = {}
    obligations = {}
    token_usage = {}
    annotation_coverage = {}
    for arm in ("baseline", "candidate"):
        rows = []
        checks = []
        obligation_counts = Counter()
        for case in cfg["cases"]:
            path = root / arm / (case["case_id"] + ".json")
            if not path.exists():
                rows.append({**case, "status":"missing", "claims":[]})
                continue
            row = json.loads(path.read_text())
            sources = json.loads((root / case["source_pack"]).read_text())
            if sha(root / case["source_pack"]) != case["source_pack_sha256"]:
                raise ValueError("Source pack changed")
            ap = root / "assessment" / (arm + "-" + case["case_id"] + ".json")
            ann = json.loads(ap.read_text()) if ap.exists() else {"status":"annotation_missing"}
            valid = ann.get("status") == "annotated_model_assisted"
            row.update(claims=ann.get("claims",[]) if valid else [],
                       assessment_status=ann["status"], usefulness=ann.get("usefulness") if valid else None)
            by_name = {o.get("name"):o for o in ann.get("obligations",[]) if isinstance(o,dict)} if valid else {}
            row["obligation_assessments"] = []
            for name in case["obligations"]:
                covered = by_name.get(name,{}).get("covered")
                key = "covered" if covered is True else "not_covered" if covered is False else "missing"
                obligation_counts[key] += 1
                row["obligation_assessments"].append({"name":name,"covered":covered if isinstance(covered,bool) else None})
            rows.append(row)
            identifier = hashlib.sha256(("intent-" + arm + "-" + case["case_id"]).encode()).hexdigest()[:32]
            folder = root / arm / "traces" / identifier
            counts = Counter()
            snapshots = []
            payloads = 0
            for events in folder.rglob("events.jsonl"):
                for line in events.read_text().splitlines():
                    event = json.loads(line)
                    counts[event["stage"]] += 1
                    if event.get("status") != "recorded": continue
                    raw = gzip.open(events.parent / event["file"],"rb").read()
                    if len(raw) != event["bytes"] or hashlib.sha256(raw).hexdigest() != event["sha256"]:
                        raise ValueError("Trace byte/hash mismatch")
                    payloads += 1
                    if event["stage"] == "input_sources":
                        supplied = json.loads(raw)["sources"]
                        snapshots.append(len(supplied) == len(sources) and all(
                            a.get("abstract") == b.get("abstract") and a.get("pmid") == b.get("pmid")
                            for a,b in zip(supplied,sources)))
            checks.append({"case_id":case["case_id"],"trace_payloads_validated":payloads,
                           "input_source_snapshots":len(snapshots),
                           "source_snapshots_preserved":bool(snapshots) and all(snapshots),
                           "native_check_requests":counts["native_check_request"],
                           "stage_counts":dict(counts)})
        runs[arm] = {"system":arm,"cases":rows,"assessment":{
            "independence":"blinded_requests_same_model_family_not_independent_human",
            "statuses":dict(Counter(x.get("assessment_status","missing") for x in rows))}}
        integrity[arm] = checks
        obligations[arm] = dict(obligation_counts)
        valid_reports = sum(x.get("assessment_status") == "annotated_model_assisted" for x in rows)
        annotation_coverage[arm] = {"valid_reports":valid_reports,"scheduled_reports":len(cfg["cases"]),
                                   "invalid_or_missing_reports":len(cfg["cases"])-valid_reports,
                                   "claim_units_in_invalid_reports":"unknown; excluded from claim-rate denominators"}
        tokens = Counter()
        known = 0
        for path in (root / arm).glob("*.calls.json"):
            for call in json.loads(path.read_text()):
                usage = call.get("usage")
                if isinstance(usage,dict):
                    known += 1
                    for key in ("input_tokens","output_tokens","total_tokens"):
                        value = usage.get(key)
                        if isinstance(value,int) and not isinstance(value,bool):tokens[key] += value
        token_usage[arm] = {"calls_with_usage":known,**dict(tokens)}
        (root / (arm + "-annotated.json")).write_text(json.dumps(runs[arm],ensure_ascii=False,indent=2))
    result = paired(runs["baseline"],runs["candidate"])
    result.update(effectiveness="unproven", trace_integrity=integrity,
                  task_obligations=obligations,
                  report_annotation_coverage=annotation_coverage,
                  generation_token_usage=token_usage,
                  generation_statuses={a:dict(Counter(x["status"] for x in runs[a]["cases"])) for a in runs},
                  source_preservation={a:{"preserved":sum(x.get("sources_preserved") is True for x in runs[a]["cases"]),
                                          "scheduled":len(cfg["cases"])} for a in runs},
                  model_calls={a:sum(x.get("model_calls",0) for x in runs[a]["cases"]) for a in runs},
                  per_variant={variant:paired(
                      {**runs["baseline"],"cases":[x for x in runs["baseline"]["cases"] if x["variant"]==variant]},
                      {**runs["candidate"],"cases":[x for x in runs["candidate"]["cases"] if x["variant"]==variant]})
                      for variant in sorted({c["variant"] for c in cfg["cases"]})},
                  limitations_additional=[
                      "Four real-source task families, one nonmedical control; not representative or sealed held-out.",
                      "Structured positive controls are programmatic and separate from natural-language tasks.",
                      "One generation per arm; family bootstrap has only four clusters and one per domain.",
                      "Source preservation is not retrieval recall; retrieval measured in a separate prior experiment.",
                      "Frozen ordinary finalization candidate; detailed adapter correction separately integration-tested.",
                      "Exact quote validation is structural and source-relative absence claims may be misclassified."])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path("/experiment"))
    p.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    result = collect(args.root)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ("status","matched_cases","generation_statuses","source_preservation","model_calls","task_obligations")},indent=2))


if __name__ == "__main__": main()
