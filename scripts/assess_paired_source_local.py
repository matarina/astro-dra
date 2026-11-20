"""Additional model-family assessment of preserved drafts; never human gold.

Uses the original frozen rubric and source pool. No production configuration
or report is changed. Raw responses, invalid annotations and usage are retained.
"""
import argparse
import hashlib
import json
import random
import re
import time
import urllib.request
from pathlib import Path

from assess_paired_source_pilot import RUBRIC


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18473/v1")
    parser.add_argument("--model", default="arex2-eval")
    parser.add_argument("--case-id", action="append", help="Explicit predeclared subset; repeatable")
    args = parser.parse_args()
    # An explicit direct opener keeps local evaluation out of any proxy route.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    models = json.loads(opener.open(args.base_url + "/models", timeout=10).read())
    if args.model not in {row["id"] for row in models["data"]}:
        raise ValueError("Unexpected local model endpoint")
    cfg = json.loads((args.experiment / "experiment.json").read_text())
    sources = json.loads((args.experiment / "sources.json").read_text())
    corpus = {int(s["index"]): s["abstract"] for s in sources}
    queue = [(arm, case["case_id"]) for arm in ("baseline", "candidate")
             for case in cfg["cases"]]
    if args.case_id:
        available = {case["case_id"] for case in cfg["cases"]}
        if not set(args.case_id) <= available:
            raise ValueError("Unknown case ID")
        queue = [(arm, caseid) for arm, caseid in queue if caseid in args.case_id]
    random.Random(20261110).shuffle(queue)
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "rubric": RUBRIC,
        "rubric_sha256": hashlib.sha256(RUBRIC.encode()).hexdigest(),
        "source_pool_sha256": digest(args.experiment / "sources.json"),
        "experiment_sha256": digest(args.experiment / "experiment.json"),
        "drafts_sha256": {f"{a}/{c}.json": digest(args.experiment / a / (c + ".json"))
                          for a, c in queue},
        "model": args.model, "endpoint_models": models,
        "temperature": 0, "max_tokens": 7000,
        "chat_template_kwargs": {"enable_thinking": False},
        "independence": "different_model_family_auxiliary_not_independent_human_gold",
        "order": [f"{a}/{c}" for a, c in queue],
        "claim_decomposition": "fresh_each_assessor_not_matched_atomic_units",
        "frozen_before_requests": True,
    }
    protocol_path = args.output / "protocol.json"
    if protocol_path.exists():
        if json.loads(protocol_path.read_text()) != protocol:
            raise ValueError("Protocol changed; use a new output directory")
    else:
        protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2))
    for arm, caseid in queue:
        stem = args.output / (arm + "-" + caseid)
        dest = stem.with_suffix(".json")
        if dest.exists():
            continue
        row = json.loads((args.experiment / arm / (caseid + ".json")).read_text())
        if row.get("status") != "completed":
            raise ValueError("Generation incomplete")
        prompt = RUBRIC + "\nINPUT DATA:\n" + json.dumps({
            "question": row["query"], "obligations": row["obligations"],
            "draft": row["body"], "sources": sources,
        }, ensure_ascii=False)
        payload = {"model": args.model, "temperature": 0, "max_tokens": 7000,
                   "chat_template_kwargs": {"enable_thinking": False},
                   "messages": [{"role": "user", "content": prompt}]}
        stem.with_suffix(".request.json").write_text(json.dumps(payload, ensure_ascii=False))
        start = time.monotonic()
        request = urllib.request.Request(args.base_url + "/chat/completions",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with opener.open(request, timeout=1200) as response:
                raw_http = response.read()
            stem.with_suffix(".http.json").write_bytes(raw_http)
            http = json.loads(raw_http)
            choice = http["choices"][0]
            raw = choice["message"]["content"] or ""
            stem.with_suffix(".response.txt").write_text(raw)
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            ann = json.loads(clean)
            if choice["finish_reason"] != "stop" or not isinstance(ann.get("claims"), list):
                raise ValueError("Truncated or invalid annotation")
            for claim in ann["claims"]:
                if claim.get("grounding") not in {"supported", "partial", "unsupported", "contradicted", "unverifiable"}:
                    raise ValueError("Invalid verdict")
                if not claim.get("text") or claim["text"] not in row["body"]:
                    raise ValueError("Claim text not in draft")
                quote_ok = bool(claim.get("evidence")) and all(
                    e.get("quote") and e["quote"] in corpus.get(e.get("source_id"), "")
                    for e in claim.get("evidence", []))
                claim["quoted_span_exists"] = quote_ok
                if claim["grounding"] in {"supported", "partial", "contradicted"} and not quote_ok:
                    claim["assessor_grounding"] = claim["grounding"]
                    claim["grounding"] = "unverifiable"
                if claim.get("citation_entails") is True and not (quote_ok and all(
                    e.get("source_id") in claim.get("citations", [])
                    for e in claim.get("evidence", []))):
                    claim["citation_entails"] = None
            ann.update(status="annotated_model_assisted", usage=http.get("usage"),
                       finish_reason=choice["finish_reason"])
        except Exception as error:
            ann = {"status": "annotation_invalid", "error_type": type(error).__name__,
                   "error": str(error)}
        ann.update(latency_seconds=time.monotonic() - start,
                   rubric_sha256=protocol["rubric_sha256"], assessor_model=args.model,
                   independence=protocol["independence"])
        dest.write_text(json.dumps(ann, ensure_ascii=False, indent=2))
        print(json.dumps({"case_id": caseid, "arm": arm, "status": ann["status"],
                          "seconds": round(ann["latency_seconds"], 2)}), flush=True)


if __name__ == "__main__":
    main()
