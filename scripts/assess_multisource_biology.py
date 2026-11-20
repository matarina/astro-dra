"""Bounded target assessment; this cannot estimate all-claim hallucination rates."""
import hashlib
import json
import os
from pathlib import Path
import random
import re
import time
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(annotation, draft, sources):
    corpus = {s["index"]: s["content"] for s in sources}
    targets, invalid = [], []
    raw = annotation.get("targets")
    if not isinstance(raw, list):
        raise ValueError("Missing targets")
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            invalid.append({"raw": item, "reason": "Target is not an object"})
            continue
        index = item.get("target_index")
        quote = item.get("draft_quote")
        coverage = item.get("coverage")
        if type(index) is not int or index not in {0, 1} or index in seen or coverage not in {"complete", "partial", "absent", "conflicting", "unclear"}:
            invalid.append({"raw": item, "reason": "Target ID/coverage invalid"})
            continue
        seen.add(index)
        localized = isinstance(quote, str) and bool(quote) and quote in draft
        evidence = item.get("evidence")
        evidence_localized = isinstance(evidence, list) and bool(evidence) and all(
            isinstance(e, dict) and type(e.get("source_index")) is int
            and isinstance(e.get("quote"), str) and bool(e["quote"])
            and e["quote"] in corpus.get(e["source_index"], "") for e in evidence)
        ids = set()
        if localized:
            for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", quote):
                ids.update(int(n.strip()) for n in group.split(","))
        bound = evidence_localized and bool(ids) and all(e["source_index"] in ids for e in evidence)
        if coverage in {"complete", "partial", "conflicting"} and not localized:
            invalid.append({"raw": item, "reason": "Positive/conflicting coverage lacks exact draft span"})
        grounding = item.get("grounding")
        if grounding not in {"entailed", "partial", "unsupported", "contradicted", "unknown", "not_applicable"}:
            invalid.append({"raw": item, "reason": "Grounding label invalid"})
        targets.append({**item, "draft_quote_localized": localized, "evidence_quotes_localized": evidence_localized,
                        "citation_ids_in_quote": sorted(ids), "evidence_citation_ids_bound": bound,
                        "mechanical_support_eligible": localized and evidence_localized,
                        "mechanical_citation_eligible": localized and bound})
    if seen != {0, 1}:
        invalid.append({"reason": "Missing target IDs", "seen": sorted(seen)})
    rating = annotation.get("usefulness", {}).get("rating") if isinstance(annotation.get("usefulness"), dict) else None
    if type(rating) is not int or not 1 <= rating <= 5:
        invalid.append({"reason": "Usefulness rating invalid"})
    return targets, invalid


def main():
    from loguru import logger
    logger.remove()
    import local_deep_research
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    root = Path("/experiment")
    protocol = json.loads((root / "assessment-protocol.json").read_text())
    for name, expected in protocol["sha256"].items():
        if sha(root / name) != expected:
            raise ValueError("Frozen assessment changed: " + name)
    for name, expected in json.loads((root / "generation-artifacts-freeze.json").read_text())["sha256"].items():
        if sha(root / name) != expected:
            raise ValueError("Frozen generation changed: " + name)
    cfg = json.loads((root / "experiment.json").read_text())
    references = {r["family"]: r for r in json.loads((root / "reference-gold.json").read_text())}
    queue = [(arm, c) for c in cfg["cases"] for arm in ["baseline", "candidate"]]
    random.Random(847191).shuffle(queue)
    defaults = Path(local_deep_research.__file__).parent / "defaults/default_settings.json"
    settings = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in json.loads(defaults.read_text()).items()})
    settings.update(cfg["settings"])
    out = root / "assessment"
    out.mkdir(exist_ok=True)
    with settings_context(SimpleNamespace(username=None, get_setting=lambda k, d=None: settings.get(k, d))):
        model = get_llm(settings_snapshot=settings)
        for position, (arm, case) in enumerate(queue):
            if position % 2 != int(os.environ["ASSESS_SHARD"]):
                continue
            stem = out / (arm + "-" + case["case_id"])
            destination = Path(str(stem) + ".json")
            if destination.exists():
                continue
            path = root / arm / (case["case_id"] + ".json")
            row = json.loads(path.read_text())
            record = {"arm": arm, "case_id": case["case_id"], "draft_sha256": sha(path),
                      "assessor_model": settings["llm.model"], "independence": "Same-backbone arm-blinded request; no independent expert draft judgment"}
            begin = time.monotonic()
            try:
                if row.get("status") != "completed":
                    raise ValueError("Generation failed; no replacement")
                sources = json.loads((root / case["source_pack"]).read_text())
                reference = references[case["task_family"]]
                targets = [{"target_index": i, **t} for i, t in enumerate(reference["obligations"])]
                data = {"original_question": reference["original_author_row"]["input"], "draft": row["body"],
                        "targets": targets, "benchmark_sources": sources,
                        "limits": "These are supplied benchmark contexts, possibly summaries. Original-paper truth and completeness unconfirmed. Targets provisional, selected before draft generation."}
                prompt = (root / "target-assessment-rubric.txt").read_text() + "\nINPUT:\n" + json.dumps(data, ensure_ascii=False)
                Path(str(stem) + ".prompt.txt").write_text(prompt)
                response = model.invoke(prompt)
                raw = response.content
                Path(str(stem) + ".response.txt").write_text(raw)
                parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
                targets, invalid = validate(parsed, row["body"], sources)
                record.update(raw_annotation=parsed, targets=targets, invalid=invalid,
                              status="partial_annotation" if invalid else "annotated_model_assisted",
                              usage=getattr(response, "usage_metadata", None))
            except Exception as error:
                record.update(status="annotation_invalid_or_failed", error_type=type(error).__name__, error=str(error))
            record["latency_seconds"] = time.monotonic() - begin
            destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({k: record.get(k) for k in ["arm", "case_id", "status", "latency_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
