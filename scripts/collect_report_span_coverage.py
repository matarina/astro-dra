"""Measure exact author-evidence span coverage in frozen report drafts.

This is a source-span coverage endpoint. It does not infer entailment, truth,
clinical importance or completeness of the generated report.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import re


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def interval(values: list[tuple[str, float]]) -> dict:
    grouped: dict[str, list[float]] = defaultdict(list)
    for family, value in values:
        grouped[family].append(value)
    means = [statistics.mean(items) for items in grouped.values()]
    if not means:
        return {"family_count": 0, "paired_observations": 0}
    rng = random.Random(20261111)
    draws = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(5000))
    return {
        "family_count": len(means),
        "paired_observations": len(values),
        "mean_family_delta": statistics.mean(means),
        "bootstrap_95_percentile_interval": [draws[124], draws[4874]],
    }


def main() -> None:
    root = Path("/data1/maxw/ldr-evaluation/fulltext-budget-20261111")
    experiment = json.loads((root / "experiment.json").read_text())
    cases = [case for case in experiment["cases"] if case["split"] == "reserved" and case["domain"] == "medicine"]
    gold = {row["family"]: row for row in json.loads((root / "reference-gold.json").read_text())}
    rows = []
    for case in cases:
        references = []
        for annotation in gold[case["task_family"]]["annotations"]:
            original = annotation["original_annotation"]
            derived = annotation["derived_localization"]
            if (original.get("Valid Label") == "True" and original.get("Valid Reasoning") == "True"
                    and original.get("Label Code") in {"-1", "0", "1"}
                    and derived.get("status") == "unique_exact"):
                references.append(derived["decoded_annotation"])
        for arm in ("baseline", "candidate"):
            path = root / "execution" / f"{arm}-{case['case_id']}.json"
            row = json.loads(path.read_text())
            body = row.get("body") or ""
            exact = [quote for quote in references if quote in body]
            body_normalized = normalized(body)
            whitespace = [quote for quote in references if normalized(quote) in body_normalized]
            rows.append({
                "family": case["task_family"],
                "case_id": case["case_id"],
                "variant": case["variant"],
                "arm": arm,
                "report_status": row.get("status"),
                "valid_author_span_count": len(references),
                "exact_quote_count": len(exact),
                "whitespace_normalized_quote_count": len(whitespace),
                "exact_quote_indices": [references.index(quote) for quote in exact],
                "whitespace_normalized_quote_indices": [references.index(quote) for quote in whitespace],
                "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_pack_sha256": case["source_pack_sha256"],
            })
    comparisons = []
    for family in sorted({row["family"] for row in rows}):
        baseline = [row for row in rows if row["family"] == family and row["arm"] == "baseline"]
        candidate = [row for row in rows if row["family"] == family and row["arm"] == "candidate"]
        for metric in ("exact_quote_count", "whitespace_normalized_quote_count"):
            if baseline and candidate:
                comparisons.append({"family": family, "metric": metric,
                                    "candidate_minus_baseline": candidate[0][metric] - baseline[0][metric]})
    exact_deltas = [(row["family"], row["candidate_minus_baseline"])
                    for row in comparisons if row["metric"] == "exact_quote_count"]
    normalized_deltas = [(row["family"], row["candidate_minus_baseline"])
                         for row in comparisons if row["metric"] == "whitespace_normalized_quote_count"]
    result = {
        "status": "completed_deterministic_report_source_span_coverage",
        "source_scope": "frozen Evidence Inference author annotations and existing reserved report bodies",
        "interpretation": "Exact source-span appearance in a draft is coverage evidence. It is not citation entailment, truth, clinical importance or a hallucination rate.",
        "raw_inputs": {
            "experiment_sha256": hashlib.sha256((root / "experiment.json").read_bytes()).hexdigest(),
            "reference_gold_sha256": hashlib.sha256((root / "reference-gold.json").read_bytes()).hexdigest(),
            "cases": len(cases),
            "families": len({case["task_family"] for case in cases}),
        },
        "rows": rows,
        "paired_family_comparisons": comparisons,
        "summary": {
            "scheduled_reports": len(rows),
            "baseline_reports": sum(row["arm"] == "baseline" for row in rows),
            "candidate_reports": sum(row["arm"] == "candidate" for row in rows),
            "valid_author_spans": sum(row["valid_author_span_count"] for row in rows if row["arm"] == "baseline"),
            "baseline_exact_quotes": sum(row["exact_quote_count"] for row in rows if row["arm"] == "baseline"),
            "candidate_exact_quotes": sum(row["exact_quote_count"] for row in rows if row["arm"] == "candidate"),
            "baseline_whitespace_normalized_quotes": sum(row["whitespace_normalized_quote_count"] for row in rows if row["arm"] == "baseline"),
            "candidate_whitespace_normalized_quotes": sum(row["whitespace_normalized_quote_count"] for row in rows if row["arm"] == "candidate"),
            "exact_family_bootstrap": interval(exact_deltas),
            "whitespace_normalized_family_bootstrap": interval(normalized_deltas),
        },
    }
    output = root / "report-span-coverage.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
