"""Offline blinded assisted assessment, preserving invalid and missing labels."""
import gzip
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


def writer_views(root, arm, case_id):
    identifier = hashlib.sha256(("fulltext-budget-" + arm + "-" + case_id).encode()).hexdigest()[:32]
    folder = root / arm / "traces" / identifier
    prompts, views = [], []
    for log in folder.rglob("events.jsonl"):
        for line in log.read_text().splitlines():
            event = json.loads(line)
            if event.get("status") != "recorded" or event["stage"] not in {"writer_request", "source_material_views"}:
                continue
            raw = gzip.open(log.parent / event["file"], "rb").read()
            if hashlib.sha256(raw).hexdigest() != event["sha256"] or len(raw) != event["bytes"]:
                raise ValueError("Trace payload changed")
            payload = json.loads(raw)
            if event["stage"] == "writer_request":
                prompts.append(payload["prompt"])
            else:
                views.extend(payload["sources"])
    if not prompts:
        raise ValueError("Actual writer prompt missing")
    return prompts, views


def validate(annotation, draft, sources):
    claims, invalid = [], []
    corpus = {int(s["index"]): [s.get(k) for k in ("full_content", "content", "abstract")
                               if isinstance(s.get(k), str)] for s in sources}
    if not isinstance(annotation.get("empirical_claims"), list):
        raise ValueError("Missing empirical claim array")
    for index, unit in enumerate(annotation["empirical_claims"]):
        if not isinstance(unit, dict) or not isinstance(unit.get("text"), str) or not unit["text"] or unit["text"] not in draft or unit.get("grounding") not in {"supported", "partial", "unsupported", "contradicted", "unverifiable"}:
            invalid.append({"index": index, "raw": unit, "reason": "Draft span or label invalid"})
            continue
        evidence = unit.get("evidence")
        quotes_valid = isinstance(evidence, list) and bool(evidence) and all(
            isinstance(e, dict) and isinstance(e.get("source_id"), int) and not isinstance(e["source_id"], bool)
            and isinstance(e.get("quote"), str) and bool(e["quote"])
            and any(e["quote"] in text for text in corpus.get(e["source_id"], [])) for e in evidence)
        citations = unit.get("citations")
        citation_binding = quotes_valid and isinstance(citations, list) and bool(citations) and all(
            isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in citations) and all(e["source_id"] in citations for e in evidence)
        claims.append({**unit, "source_quotes_localized": quotes_valid,
                       "raw_citation_entails": unit.get("citation_entails"),
                       "citation_entails": unit.get("citation_entails") if citation_binding else None,
                       "quote_checked_grounding": "unverifiable" if not quotes_valid and unit["grounding"] in {"supported", "partial", "contradicted"} else unit["grounding"]})
    other = annotation.get("nonempirical_units")
    if not isinstance(other, list):
        other = []
    other_invalid = [unit for unit in other if not isinstance(unit, dict) or not isinstance(unit.get("text"), str)
                     or not unit["text"] or unit["text"] not in draft]
    return claims, invalid, other_invalid


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
            raise ValueError("Frozen assessment artifact changed: " + name)
    cfg = json.loads((root / "experiment.json").read_text())
    gold = {x["family"]: x for x in json.loads((root / "reference-gold.json").read_text())}
    families = {x["family"]: x for x in json.loads((root / "families.json").read_text())}
    phase = os.environ["ASSESS_PHASE"]
    cases = [c for c in cfg["cases"] if c["split"] == phase and (phase == "reserved" or c["variant"] == "original")]
    queue = [(arm, c) for c in cases for arm in ["baseline", "candidate"]]
    random.Random(20261111).shuffle(queue)
    defaults = Path(local_deep_research.__file__).parent / "defaults/default_settings.json"
    settings = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in json.loads(defaults.read_text()).items()})
    settings.update(cfg["settings"])
    out = root / "assessment"
    out.mkdir(exist_ok=True)
    with settings_context(SimpleNamespace(username=None, get_setting=lambda k, d=None: settings.get(k, d))):
        model = get_llm(settings_snapshot=settings)
        for position, (arm, case) in enumerate(queue):
            if position % 2 != int(os.environ.get("ASSESS_SHARD", "0")):
                continue
            path = root / arm / (case["case_id"] + ".json")
            row = json.loads(path.read_text())
            if row.get("status") != "completed":
                continue
            sources = json.loads((root / case["source_pack"]).read_text())
            for method in ["grounding", "answer_alignment"]:
                stem = out / (arm + "-" + case["case_id"] + "-" + method)
                destination = Path(str(stem) + ".json")
                if destination.exists():
                    continue
                if method == "grounding":
                    prompts, scope = writer_views(root, arm, case["case_id"])
                    # The judge sees exact supplied source regions, without the
                    # writer's preceding generation instructions or benchmark gold.
                    evidence_views = [p[p.index("BEGIN SOURCE TEXT"):p.rindex("END SOURCE TEXT") + len("END SOURCE TEXT")]
                                      for p in prompts if "BEGIN SOURCE TEXT" in p and "END SOURCE TEXT" in p]
                    scientific_sources = [{"index": s["index"], "title": s.get("title"), "url": s.get("link"),
                                           "abstract": s.get("abstract"),
                                           "acquired_text": s.get("full_content") or s.get("content") or ""} for s in sources]
                    data = {"question": case["query"], "draft": row["body"], "scientific_sources": scientific_sources,
                            "actual_writer_source_regions": evidence_views, "application_reading_scope": scope}
                    rubric = (root / "grounding-rubric.txt").read_text()
                else:
                    reference = gold[case["task_family"]]
                    family = families[case["task_family"]]
                    data = {"original_question": family["original"], "draft": row["body"]}
                    if case["domain"] == "medicine":
                        rubric = (root / "direction-rubric.txt").read_text()
                    else:
                        rubric = (root / "alignment-rubric.txt").read_text()
                        data["original_practitioner_answers"] = reference["original_reference"]["answers"]
                prompt = rubric + "\nINPUT DATA:\n" + json.dumps(data, ensure_ascii=False)
                Path(str(stem) + ".prompt.txt").write_text(prompt)
                record = {"arm": arm, "case_id": case["case_id"], "method": method,
                          "draft_sha256": sha(path), "source_pack_sha256": sha(root / case["source_pack"]),
                          "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                          "assessor_model": settings["llm.model"], "independence": "Same-backbone blinded request; benchmark author references independent, not new expert draft review"}
                begin = time.monotonic()
                try:
                    response = model.invoke(prompt)
                    raw = response.content
                    Path(str(stem) + ".response.txt").write_text(raw)
                    parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
                    record.update(raw_annotation=parsed, usage=getattr(response, "usage_metadata", None))
                    if method == "grounding":
                        valid, invalid, other_invalid = validate(parsed, row["body"], sources)
                        record.update(claims=valid, invalid_claims=invalid, invalid_nonempirical=other_invalid,
                                      status="partial_annotation" if invalid or other_invalid else "annotated_model_assisted")
                    elif case["domain"] == "medicine":
                        label = parsed.get("reported_direction")
                        if label not in {"-1", "0", "1", "mixed", "unclear"}:
                            raise ValueError("Invalid extracted direction")
                        quote = parsed.get("draft_quote")
                        localized = isinstance(quote, str) and bool(quote) and quote in row["body"]
                        reference = gold[case["task_family"]]
                        record.update(extracted_direction=label, draft_quote_localized=localized,
                                      author_majority_direction=reference["majority_author_label_code"],
                                      valid_author_label_counts=reference["valid_author_label_counts"],
                                      direction_matches_author=label == reference["majority_author_label_code"] and localized,
                                      status="annotated_direction_extraction")
                    else:
                        if parsed.get("alignment") not in {"covered", "partial", "missing", "conflicting", "unknown"}:
                            raise ValueError("Invalid alignment")
                        quote = parsed.get("draft_quote")
                        record.update(draft_quote_localized=isinstance(quote, str) and bool(quote) and quote in row["body"],
                                      status="annotated_reference_alignment")
                except Exception as error:
                    record.update(status="annotation_invalid_or_failed", error_type=type(error).__name__, error=str(error))
                record["latency_seconds"] = time.monotonic() - begin
                destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps({k: record.get(k) for k in ["arm", "case_id", "method", "status", "latency_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
