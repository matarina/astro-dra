"""Validate sealed reserved review packets and report paired source-relative outcomes."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from collect_fulltext_budget import interval
from prepare_reserved_report_review import ARMS, digest, read, verify_files


GROUNDING = {"supported", "partial", "unsupported", "contradicted", "unassessable"}
CITATION = {"entails", "partial", "unsupported", "contradicts", "unassessable", "context_only"}
COVERAGE = {"covered", "partial", "omitted", "conflicting", "unassessable"}


def exact_span(text, span):
    if not 0 <= span["start"] < span["end"] <= len(text) or text[span["start"]:span["end"]] != span["quote"]:
        raise ValueError("Recorded passage does not match original coordinates")


def keyed(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return result


def count_annotations(report, annotation, sources, family_criteria, availability, dimensions):
    body = report["body"]
    sampled = keyed(report["sampled_units"], "unit_id")
    reviewed = keyed(annotation["sampled_units"], "unit_id")
    if (sampled.keys() != reviewed.keys() or annotation["source_pack_sha256"] != report["source_pack_sha256"]
            or annotation["coverage"].keys() != family_criteria or annotation["usefulness"].keys() != dimensions):
        raise ValueError("Annotation differs from the frozen report sample or criteria")

    roles, labels, citations = Counter(), Counter(), Counter()
    explicit_without_verdict = 0
    for unit_id, original in sampled.items():
        unit = reviewed[unit_id]
        span = unit["span"]
        exact_span(body, span)
        if (span["start"], span["end"], unit["explicit_citations"]) != (
                original["report_start"], original["report_end"], original["citations"]):
            raise ValueError("Reviewed span or citation numbering differs from frozen sample")
        roles[unit["role"]] += 1
        verdict_ids = set()
        for claim in unit["empirical_assertions"]:
            exact_span(body, claim["span"])
            if (claim["grounding"] not in GROUNDING or claim["span"]["start"] < span["start"]
                    or claim["span"]["end"] > span["end"]):
                raise ValueError("Unexpected claim label or scope")
            labels[claim["grounding"]] += 1
            relationships = {}
            for evidence in claim["source_evidence"]:
                index = evidence["index"]
                exact_span(sources[index][evidence["field"]], evidence)
                explicit = index in original["citations"]
                relationship = evidence["relationship"]
                if explicit != evidence["explicit_unit_citation"] or relationship not in CITATION:
                    raise ValueError("Invalid citation verdict")
                if explicit:
                    if relationship == "context_only" or relationships.setdefault(index, relationship) != relationship:
                        raise ValueError("Conflicting verdicts for one claim–citation pair")
            verdict_ids.update(relationships)
            citations.update(relationships.values())
        if unit["empirical_assertions"]:
            explicit_without_verdict += len(set(original["citations"]) - verdict_ids)

    coverage = defaultdict(Counter)
    for key, judgment in annotation["coverage"].items():
        status = judgment["status"]
        if status not in COVERAGE:
            raise ValueError("Unknown coverage label")
        if judgment["draft_span"] is not None:
            exact_span(body, judgment["draft_span"])
        elif status in {"covered", "partial", "conflicting"}:
            raise ValueError("Coverage verdict requires a passage")
        coverage[availability[key]][status] += 1
    usefulness = {}
    for key, judgment in annotation["usefulness"].items():
        score = judgment["score"]
        if score != "unknown" and (type(score) is not int or score not in {0, 1, 2}):
            raise ValueError("Usefulness verdict differs from frozen ordinal scale")
        if judgment["draft_span"] is not None:
            exact_span(body, judgment["draft_span"])
        elif score in {1, 2}:
            raise ValueError("Positive usefulness verdict requires a passage")
        usefulness[key] = score
    return {"roles": dict(roles), "grounding": dict(labels), "citation_pairs": dict(citations),
            "empirical_unit_citations_without_verdict": explicit_without_verdict,
            "coverage_by_evidence_availability": dict(coverage), "usefulness": usefulness}


def load_reviews(batches, reports, bindings, protocol_sha):
    annotations = {}
    for batch in batches:
        path = batch / "receipt.json"
        receipt = read(path)
        verify_files(batch, receipt["sha256"])
        if receipt["protocol_sha256"] != protocol_sha:
            raise ValueError("Intermediate packet used a different protocol")
        for row in read(batch / "reports.json"):
            if row != reports[row["report_id"]]:
                raise ValueError("Intermediate report or sample differs from terminal packet")
        for annotation_path in sorted(batch.glob("*.review.json")):
            review = read(annotation_path)
            if review["packet_receipt_sha256"] != digest(path.read_bytes()) or review["protocol_sha256"] != protocol_sha:
                raise ValueError("Annotation packet hash mismatch")
            for item in review["reports"]:
                report_id = item["report_id"]
                if report_id in annotations or bindings[report_id]["family"] != review["family"]:
                    raise ValueError("Duplicate review or family mismatch")
                annotations[report_id] = (item, review["reviewer"])
    return annotations


def rate(counts, key):
    total = sum(counts.values())
    return counts.get(key, 0) / total if total else None


def row_metrics(row):
    labels = row.get("grounding", {})
    coverage = row.get("coverage_by_evidence_availability", {})
    metrics = {"latency_seconds": row.get("latency_seconds"), "model_calls": row.get("model_calls"),
               "total_reported_tokens": row.get("total_reported_tokens"),
               "unsupported_fraction": rate(labels, "unsupported"),
               "contradicted_fraction": rate(labels, "contradicted"),
               "citation_entailment_fraction": rate(row.get("citation_pairs", {}), "entails"),
               "reference_coverage_fraction_when_support_located": rate(coverage.get("located", {}), "covered")}
    if labels:
        metrics["sampled_supported_assertions"] = labels.get("supported", 0)
    metrics.update({f"usefulness_{key}": score if type(score) is int else None
                    for key, score in row.get("usefulness", {}).items()})
    return metrics


def describe(rows):
    fields = ("roles", "grounding", "citation_pairs", "structural_units")
    counts = {key: dict(sum((Counter(row.get(key, {})) for row in rows), Counter())) for key in fields}
    coverage = defaultdict(Counter)
    usefulness = defaultdict(Counter)
    for row in rows:
        for key, values in row.get("coverage_by_evidence_availability", {}).items():
            coverage[key].update(values)
        for key, score in row.get("usefulness", {}).items():
            usefulness[key][str(score)] += 1
    metrics = [row_metrics(row) for row in rows]
    means = {}
    for key in sorted({key for row in metrics for key in row}):
        values = [row[key] for row in metrics if row.get(key) is not None]
        means[key] = {"n": len(values), "mean": statistics.mean(values) if values else None}
    call_totals = {key: sum(row.get(key, 0) for row in rows)
                   for key in ("model_calls", "model_calls_with_usage", "model_call_errors", "observed_tokens")}
    exposure_totals = {key: sum(row.get("writer_exposure", {}).get(key, 0) for row in rows)
                       for key in ("writer_requests", "linked_source_views", "views_with_verbatim_supplied_field",
                                   "native_check_requests", "native_check_responses")}
    publications = [row["publication"] for row in rows if "publication" in row]
    return {"scheduled": len(rows), "generation_status": dict(Counter(row["status"] for row in rows)),
            "annotated_reports": sum("reviewer" in row for row in rows), **counts,
            "empirical_unit_citations_without_verdict": sum(row.get("empirical_unit_citations_without_verdict", 0) for row in rows),
            "coverage_by_evidence_availability": dict(coverage), "usefulness": dict(usefulness), "report_means": means,
            "call_totals": call_totals, "writer_exposure": exposure_totals,
            "native_fact_consistency_enabled_reports": sum(row.get("native_fact_consistency_enabled") is True for row in rows),
            "publication": {"rows": len(publications),
                            "status": dict(Counter(p["publication_status"] for p in publications)),
                            "audit_status": dict(Counter(p["audit_status"] for p in publications)),
                            "provided_fields_preserved": sum(p["provided_fields_preserved"] for p in publications)}}


def compare(rows):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["case_id"]][row["arm"]] = row
    deltas = defaultdict(list)
    for arms in pairs.values():
        baseline, candidate = (arms[arm] for arm in ARMS)
        if baseline["status"] != "completed" or candidate["status"] != "completed":
            continue
        if baseline["settings"] != candidate["settings"]:
            raise ValueError("Pair differs in model settings or sources")
        before, after = row_metrics(baseline), row_metrics(candidate)
        for key, value in before.items():
            if value is not None and after.get(key) is not None:
                deltas[key].append((baseline["family"], after[key] - value))
    comparison = {}
    for key, values in sorted(deltas.items()):
        result = interval(values)
        if result["family_count"] == 1:
            result["family_bootstrap_95_percentile_interval"] = None
        comparison[key] = result
    return comparison


def collect(run, packets, freeze, batches):
    receipt = read(packets / "receipt.json")
    verify_files(packets, receipt["sha256"])
    verify_files(freeze, read(freeze / "freeze.json")["sha256"])
    verify_files(freeze, read(freeze / "source-availability-freeze.json")["sha256"])
    protocol_sha = digest((run / "reserved-assessment-protocol.json").read_bytes())
    if receipt["phase"] != "reserved" or receipt["protocol_sha256"] != protocol_sha:
        raise ValueError("The terminal packet must use the frozen reserved protocol")
    report_ids = read(packets / "private-bindings.json")
    reports = keyed(read(packets / "review/reports.json"), "report_id")
    if reports.keys() != report_ids.keys() or len(reports) != 2 * read(run / "reserved-assessment-protocol.json")["scheduled_pairs"]:
        raise ValueError("Missing terminal reports or bindings")
    packs = read(packets / "review/source-packs.json")
    annotations = load_reviews(batches, reports, report_ids, protocol_sha)
    reference = read(freeze / "reference-alignment-frame.json")
    criteria = {r["family_id"]: {v["id"] for v in r["criteria"]} for r in reference["families"]}
    availability = defaultdict(dict)
    for entry in read(freeze / "reserved-obligation-source-availability.json")["rows"]:
        availability[entry["family_id"]][entry["criterion_id"]] = entry

    rows = []
    for report_id, report in reports.items():
        binding = report_ids[report_id]
        arm, case_id, family = binding["arm"], binding["case_id"], binding["family"]
        status = report["generation_status"]
        row = {"report_id": report_id, "arm": arm, "case_id": case_id, "family": family,
               "variant": binding["variant"], "domain": binding["domain"], "status": status,
               "structural_units": report["structural_units"], "sampled_units": len(report["sampled_units"])}
        rows.append(row)
        if binding["generated_sha256"] is not None:
            path = run / arm / f"{case_id}.json"
            verify_files(path.parent, {path.name: binding["generated_sha256"]})
            generated = read(path)
            events = read(path.with_suffix(".calls.json"))
            if len(events) != generated["model_calls"]:
                raise ValueError("Logical model-call log does not match run record")
            usage = [event["usage"]["total_tokens"] for event in events
                     if isinstance(event.get("usage"), dict) and type(event["usage"].get("total_tokens")) is int]
            row.update(latency_seconds=generated["latency_seconds"], model_calls=len(events),
                       model_calls_with_usage=len(usage), total_reported_tokens=sum(usage) if len(usage) == len(events) else None,
                       observed_tokens=sum(usage), model_call_errors=sum(e["status"] != "completed" for e in events),
                       native_fact_consistency_enabled=generated["settings"].get("general.enable_fact_checking"),
                       settings=[generated[k] for k in ("model", "temperature", "settings_sha256", "source_pack_sha256")])
        if report_id in annotations:
            if status != "completed":
                raise ValueError("Unexpected assessment of failed or missing report")
            annotation, reviewer = annotations[report_id]
            pack_sha = report["source_pack_sha256"]
            sources = {source["index"]: source for source in packs[pack_sha]}
            for item in availability[family].values():
                if item["source_pack_sha256"] != pack_sha:
                    raise ValueError("Source availability assessment belongs to a different pack")
                for span in item["source_spans"]:
                    exact_span(sources[span["index"]][span["field"]], span)
            row.update(count_annotations(report, annotation, sources, criteria[family],
                                         {key: item["preliminary_availability"] for key, item in availability[family].items()},
                                         set(reference["usefulness_dimensions"])), reviewer=reviewer)
        if status == "completed":
            exposure = binding["writer_exposure"]
            row["writer_exposure"] = {"writer_requests": exposure["writer_request_events"],
                                      "linked_source_views": len(exposure["linked_source_views"]),
                                      "views_with_verbatim_supplied_field": sum(bool(v["verbatim_supplied_fields"]) for v in exposure["linked_source_views"]),
                                      "native_check_requests": exposure["trace_records"].get("native_check_request/recorded", 0),
                                      "native_check_responses": exposure["trace_records"].get("native_check_response/recorded", 0)}
            row["publication"] = {key: binding[key] for key in ("publication_status", "audit_status", "provided_fields_preserved")}

    groups = {"all": rows}
    for key in ("domain", "variant", "family"):
        for value in sorted({row[key] for row in rows}):
            groups[f"{key}/{value}"] = [row for row in rows if row[key] == value]
    return {"review_protocol_sha256": protocol_sha, "terminal_packet_receipt_sha256": digest((packets / "receipt.json").read_bytes()),
            "annotated_reports": len(annotations), "scheduled_reports": len(reports),
            "missing_completed_reviews": sorted(row["report_id"] for row in rows if row["status"] == "completed" and "reviewer" not in row),
            "groups": {group: {**{arm: describe([row for row in group_rows if row["arm"] == arm]) for arm in ARMS},
                               "candidate_minus_baseline": compare(group_rows)} for group, group_rows in groups.items()},
            "reports": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("packets", type=Path)
    parser.add_argument("freeze", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("batches", nargs="+", type=Path)
    args = parser.parse_args()
    result = collect(args.run, args.packets, args.freeze, args.batches)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: result[key] for key in ("annotated_reports", "scheduled_reports")}))


if __name__ == "__main__":
    main()
