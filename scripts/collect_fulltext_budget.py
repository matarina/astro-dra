"""Collect paired full-text evidence without certifying hallucination reduction."""
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(values):
    """Bootstrap paired family means; variants remain in one cluster."""
    groups = defaultdict(list)
    for family, value in values:
        groups[family].append(value)
    means = [statistics.mean(v) for v in groups.values()]
    if not means:
        return {"family_count": 0, "paired_observations": 0}
    rng = random.Random(20261111)
    draws = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(5000))
    return {"family_count": len(means), "paired_observations": len(values),
            "mean_paired_family_delta_candidate_minus_baseline": statistics.mean(means),
            "family_bootstrap_95_percentile_interval": [draws[124], draws[4874]],
            "limitations": "Convenience public sample; no model/annotation bias correction; small domain family counts"}


def traces(root, arm, case):
    folder = root / arm / "traces" / hashlib.sha256(("fulltext-budget-" + arm + "-" + case["case_id"]).encode()).hexdigest()[:32]
    stages, writers, inputs = Counter(), [], []
    for log in folder.rglob("events.jsonl"):
        for line in log.read_text().splitlines():
            event = json.loads(line)
            stages[event["stage"]] += 1
            if event.get("status") != "recorded":
                continue
            raw = gzip.open(log.parent / event["file"], "rb").read()
            if len(raw) != event["bytes"] or hashlib.sha256(raw).hexdigest() != event["sha256"]:
                raise ValueError("Trace bytes changed")
            payload = json.loads(raw)
            if event["stage"] == "writer_request":
                writers.append(payload["prompt"])
            elif event["stage"] == "input_sources":
                inputs.append(payload["sources"])
    return stages, writers, inputs


def collect(root):
    for name in ["freeze.json", "inputs-freeze.json", "assessment-protocol.json"]:
        for relative, expected in json.loads((root / name).read_text())["sha256"].items():
            if sha(root / relative) != expected:
                raise ValueError("Frozen artifact changed: " + relative)
    cfg = json.loads((root / "experiment.json").read_text())
    cases = [c for c in cfg["cases"] if c["split"] == "reserved" or c["variant"] == "original"]
    gold = {g["family"]: g for g in json.loads((root / "reference-gold.json").read_text())}
    rows, manifests = {}, {}
    for arm in ["baseline", "candidate"]:
        manifest = json.loads((root / (arm + "-code-hashes.json")).read_text())
        manifests[arm] = manifest
        for name, expected in manifest.items():
            if sha(root / (arm + "-code") / name) != expected:
                raise ValueError("Frozen code changed")
        for case in cases:
            path = root / arm / (case["case_id"] + ".json")
            key = (arm, case["case_id"])
            row = {k: case[k] for k in ["case_id", "task_family", "domain", "split", "variant"]}
            row.update(arm=arm, generation_status="missing", assessment_status="missing", answer_assessment_status="missing")
            rows[key] = row
            if not path.exists():
                continue
            generated = json.loads(path.read_text())
            row["generation_status"] = generated["status"]
            row["output_word_count"] = len((generated.get("body") or "").split())
            row["latency_seconds"] = generated["latency_seconds"]
            events = json.loads(path.with_name(case["case_id"] + ".calls.json").read_text())
            row["logical_model_calls"] = len(events)
            row["events_with_reported_usage"] = sum(isinstance(e.get("usage"), dict) for e in events)
            row["model_event_errors"] = sum(e["status"] != "completed" for e in events)
            row["usage"] = dict(sum((Counter({k: v for k, v in (e.get("usage") or {}).items() if isinstance(v, int)}) for e in events), Counter()))
            if generated["status"] != "completed":
                continue
            sources = json.loads((root / case["source_pack"]).read_text())
            if generated["source_pack_sha256"] != sha(root / case["source_pack"]) or generated["query"] != case["query"]:
                raise ValueError("Generation binding mismatch")
            installed = json.loads(path.with_name(case["case_id"] + ".installed.json").read_text())
            for name, actual in installed.items():
                expected = manifest[name]
                if name.endswith("/langgraph_agent_strategy.py"):
                    tree = ast.parse((root / (arm + "-code/deployment/install_overlays.py")).read_text())
                    hook = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == "COLLECTION_HOOK" for t in n.targets))
                    original = (root / (arm + "-code") / name).read_text()
                    expected = hashlib.sha256((original if "# Source collection feedback and stable-identifier deduplication." in original else original + hook).encode()).hexdigest()
                if actual != expected:
                    raise ValueError("Installed module mismatch: " + name)
            actual = generated["sources"]
            fields_preserved = len(actual) == len(sources) and all(all(a.get(k) == v for k, v in b.items()) for a, b in zip(actual, sources))
            stages, writers, received = traces(root, arm, case)
            input_preserved = bool(received) and all(len(got) == len(sources) and all(all(a.get(k) == b.get(k) for k in ["index", "link", "content", "full_content", "abstract"]) for a, b in zip(got, sources)) for got in received)
            publication = generated["publication"]["claim_publication"]
            row.update(installed_modules_verified=len(installed), provided_source_fields_preserved=fields_preserved,
                       trace_input_texts_preserved=input_preserved, native_check_requests=stages["native_check_request"],
                       writer_requests=len(writers), source_count=len(sources),
                       complete_source_texts_in_writer=sum(bool(s.get("full_content")) and any(s["full_content"] in p for p in writers) for s in sources),
                       publication_unverified_audit_disabled=publication["status"] == "unverified" and publication["audit_status"] == "disabled",
                       model=generated["model"], settings_sha256=generated["settings_sha256"], source_pack_sha256=generated["source_pack_sha256"])
            reference = gold[case["task_family"]]
            if "annotations" in reference:
                evidence = [(a["derived_localization"]["decoded_annotation"], a["derived_localization"]["status"] == "unique_exact") for a in reference["annotations"]]
                valid_author_evidence = [(a["derived_localization"]["decoded_annotation"], a["derived_localization"]["status"] == "unique_exact")
                    for a in reference["annotations"] if a["original_annotation"].get("Valid Label") == "True"
                    and a["original_annotation"].get("Valid Reasoning") == "True"
                    and a["original_annotation"].get("Label Code") in {"-1", "0", "1"}]
                row.update(valid_author_passage_observations=len(valid_author_evidence),
                           valid_author_source_localized_passages=sum(ok for _, ok in valid_author_evidence),
                           valid_author_full_passages_in_writer=sum(ok and any(text in p for p in writers) for text, ok in valid_author_evidence))
            else:
                evidence = [(text, any(text in (s.get("full_content") or "") for s in sources))
                            for a in reference["original_reference"]["answers"] for text in a["answer"].get("evidence", [])]
            row.update(reference_passage_observations=len(evidence), source_localized_passages=sum(ok for _, ok in evidence),
                       full_reference_passages_in_writer=sum(ok and any(text in p for p in writers) for text, ok in evidence))
            for method in ["grounding", "answer_alignment"]:
                apath = root / "assessment" / (arm + "-" + case["case_id"] + "-" + method + ".json")
                if not apath.exists():
                    continue
                annotation = json.loads(apath.read_text())
                promptpath = apath.with_suffix(".prompt.txt")
                if annotation["draft_sha256"] != sha(path) or annotation["prompt_sha256"] != sha(promptpath):
                    raise ValueError("Assessment binding changed")
                data = json.loads(promptpath.read_text().split("\nINPUT DATA:\n", 1)[1])
                if data["draft"] != generated["body"]:
                    raise ValueError("Assessed draft mismatch")
                if method == "grounding":
                    if "original_practitioner_answers" in data or "majority_author_label_code" in data:
                        raise ValueError("Gold leakage into grounding")
                    claims = annotation.get("claims", [])
                    raw = annotation.get("raw_annotation")
                    raw = raw if isinstance(raw, dict) else {}
                    nonempirical = raw.get("nonempirical_units")
                    nonempirical = nonempirical if isinstance(nonempirical, list) else []
                    row.update(assessment_status=annotation["status"], extracted_valid_claims=len(claims),
                               invalid_claims=len(annotation.get("invalid_claims", [])),
                               invalid_nonempirical=len(annotation.get("invalid_nonempirical", [])),
                               raw_labels=dict(Counter(c["grounding"] for c in claims)),
                               quote_checked_labels=dict(Counter(c["quote_checked_grounding"] for c in claims)),
                               citation_true=sum(c.get("citation_entails") is True for c in claims if c.get("citations")),
                               citation_false=sum(c.get("citation_entails") is False for c in claims if c.get("citations")),
                               citation_unknown=sum(c.get("citation_entails") is not True and c.get("citation_entails") is not False for c in claims if c.get("citations")),
                               citation_pair_claims=sum(bool(c.get("citations")) for c in claims),
                               usefulness=raw.get("usefulness"),
                               nonempirical_schema_valid=isinstance(raw.get("nonempirical_units"), list),
                               nonempirical_types=dict(Counter(x.get("type") if isinstance(x.get("type"), str) else "invalid_type"
                                                              for x in nonempirical if isinstance(x, dict))))
                    row["raw_unsupported_units"] = sum(c["grounding"] == "unsupported" for c in claims)
                    row["raw_contradicted_units"] = sum(c["grounding"] == "contradicted" for c in claims)
                    row["quote_checked_supported_units"] = sum(c["quote_checked_grounding"] == "supported" for c in claims)
                    if claims:
                        row["unsupported_fraction_valid_extracted"] = row["raw_unsupported_units"] / len(claims)
                        row["contradicted_fraction_valid_extracted"] = row["raw_contradicted_units"] / len(claims)
                    if row["citation_pair_claims"]:
                        row["citation_true_fraction_all_extracted_cited"] = row["citation_true"] / row["citation_pair_claims"]
                else:
                    row["answer_assessment_status"] = annotation["status"]
                    row["answer_quote_localized"] = annotation.get("draft_quote_localized")
                    if case["domain"] == "medicine":
                        # Extraction prompt contains only the question and draft.
                        if set(data) != {"original_question", "draft"}:
                            raise ValueError("Direction extractor saw reference/source")
                        row.update(extracted_direction=annotation.get("extracted_direction"),
                                   direction_matches_author=annotation.get("direction_matches_author"))
                    else:
                        raw = annotation.get("raw_annotation")
                        raw = raw if isinstance(raw, dict) else {}
                        row.update(answer_alignment=raw.get("alignment"), reference_disagreement=raw.get("reference_disagreement"))
                        row["answer_alignment_localized"] = raw.get("alignment") if annotation.get("draft_quote_localized") is True else "unlocalized"
    aggregates = {}
    for split in ["development", "reserved"]:
        for domain in ["medicine", "nlp_control"]:
            for arm in ["baseline", "candidate"]:
                group = [r for r in rows.values() if r["split"] == split and r["domain"] == domain and r["arm"] == arm]
                completed = [r for r in group if r["generation_status"] == "completed"]
                usable = [r for r in completed if r["assessment_status"] in {"annotated_model_assisted", "partial_annotation"}]
                scored = [r["usefulness"] for r in usable if isinstance(r.get("usefulness"), (int, float)) and not isinstance(r["usefulness"], bool) and 1 <= r["usefulness"] <= 5]
                summary = {"scheduled_reports": len(group), "completed_reports": len(completed),
                           "grounding_status": dict(Counter(r["assessment_status"] for r in group)),
                           "answer_assessment_status": dict(Counter(r["answer_assessment_status"] for r in group)),
                           "raw_assisted_claim_labels": dict(sum((Counter(r.get("raw_labels", {})) for r in usable), Counter())),
                           "quote_checked_assisted_labels": dict(sum((Counter(r.get("quote_checked_labels", {})) for r in usable), Counter())),
                           "usefulness_mean_assisted": statistics.mean(scored) if scored else None,
                           "usefulness_scored_reports": len(scored), "usage": dict(sum((Counter(r.get("usage", {})) for r in group), Counter()))}
                for field in ["provided_source_fields_preserved", "trace_input_texts_preserved", "publication_unverified_audit_disabled", "native_check_requests", "writer_requests", "source_count", "complete_source_texts_in_writer", "reference_passage_observations", "source_localized_passages", "full_reference_passages_in_writer", "valid_author_passage_observations", "valid_author_source_localized_passages", "valid_author_full_passages_in_writer", "logical_model_calls", "events_with_reported_usage", "model_event_errors", "extracted_valid_claims", "invalid_claims", "invalid_nonempirical", "citation_true", "citation_false", "citation_unknown", "citation_pair_claims"]:
                    summary[field] = sum(r.get(field, 0) for r in group)
                latencies = sorted(r["latency_seconds"] for r in completed)
                summary["latency_mean_seconds"] = statistics.mean(latencies) if latencies else None
                summary["latency_median_seconds"] = statistics.median(latencies) if latencies else None
                summary["latency_p95_observed_seconds"] = latencies[min(len(latencies)-1, int(.95*len(latencies)))] if latencies else None
                summary["output_word_count_mean_descriptive"] = statistics.mean(r["output_word_count"] for r in completed) if completed else None
                if domain == "medicine":
                    summary["author_direction_matches"] = sum(r.get("direction_matches_author") is True for r in group)
                    summary["extracted_directions"] = dict(Counter(r.get("extracted_direction", "missing") for r in group))
                else:
                    summary["reference_alignment"] = dict(Counter(r.get("answer_alignment", "missing") for r in group))
                    summary["reference_alignment_with_localized_draft_quote"] = dict(Counter(r.get("answer_alignment_localized", "missing") for r in group))
                aggregates[split + "/" + domain + "/" + arm] = summary
    comparisons = {}
    for split in ["development", "reserved"]:
        for domain in ["medicine", "nlp_control"]:
            for metric in ["direction_matches_author", "usefulness", "latency_seconds", "output_word_count", "raw_unsupported_units", "raw_contradicted_units", "quote_checked_supported_units", "unsupported_fraction_valid_extracted", "contradicted_fraction_valid_extracted", "citation_true_fraction_all_extracted_cited"]:
                deltas = []
                for case in cases:
                    if case["split"] != split or case["domain"] != domain:
                        continue
                    a, b = [rows[(arm, case["case_id"])] for arm in ["baseline", "candidate"]]
                    if a.get("generation_status") == "completed" and b.get("generation_status") == "completed":
                        if a["settings_sha256"] != b["settings_sha256"] or a["source_pack_sha256"] != b["source_pack_sha256"] or a["model"] != b["model"]:
                            raise ValueError("Unmatched pair")
                    av, bv = a.get(metric), b.get(metric)
                    valid_numbers = isinstance(av, (int, float)) and isinstance(bv, (int, float))
                    if metric == "usefulness":
                        valid_numbers = valid_numbers and not isinstance(av, bool) and not isinstance(bv, bool) and 1 <= av <= 5 and 1 <= bv <= 5
                    if valid_numbers:
                        deltas.append((case["task_family"], bv-av))
                comparisons[split + "/" + domain + "/" + metric] = interval(deltas)
    role_path = root / "contradicted-label-role-audit.json"
    role_audit = json.loads(role_path.read_text()) if role_path.exists() else None
    assessment_files = [json.loads(p.read_text()) for p in (root / "assessment").glob("*.json")]
    return {"status": "collected_with_explicit_missing_runs", "root": str(root), "aggregates": aggregates,
            "paired_family_comparisons": comparisons, "rows": list(rows.values()),
            "assessment_request_status_counts": dict(Counter(a["status"] for a in assessment_files)),
            "empirical_contradiction_endpoint_validity": "not_established: same-model assessor still mixes reading-scope assertions with scientific claims despite frozen rubric; raw68-to0 reserved labels are not a scientific contradiction-rate reduction",
            "citation_entailment_endpoint_validity": "not_independently_validated; empirical-role contamination and same-backbone judgments remain; exact quotes/pair binding do not prove entailment",
            "manual_contradicted_role_audit": {"counts": role_audit["counts"], "reserved_counts": role_audit["reserved_counts"],
                "independence": role_audit["status"], "sha256": sha(role_path)} if role_audit else None,
            "reference_alignment_caveat": "Original independent benchmark references retained; extraction errors, source inconsistencies and a practitioner-yes/downstream-definition ambiguity remain. No post-hoc gold corrections or score replacements.",
            "output_length_endpoint": "Post-hoc descriptive whitespace word count, not a registered scientific quality measure",
            "runtime_changed_files": [n for n in manifests["candidate"] if n.endswith(".py") and "/tests/" not in n and manifests["candidate"][n] != manifests["baseline"].get(n)],
            "overall_effectiveness": "unproven", "independent_new_expert_draft_assessment": False,
            "limitations": ["Public selected single-source briefs; not representative multi-paper research, biology/bioinformatics or live retrieval.",
                "Original benchmark direction/answers independent, but report extraction and entailment/usefulness judge use the generation model family.",
                "Quote existence, source exposure and author-label matching are different endpoints; no overall hallucination rate is certified.",
                "Annotation invalids/missing retained; extracted claim denominator is not all actual empirical claims.",
                "Character budget is not a token/context-window guarantee; source reading and consistency calls can still miss/misinterpret evidence.",
                "Shared model load, one stochastic run and small family counts limit cost/latency and domain causal inference."]}


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/experiment")
    result = collect(root)
    (root / "collected-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"aggregates": result["aggregates"], "runtime_changed_files": result["runtime_changed_files"]}, indent=2))
