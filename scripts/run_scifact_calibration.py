"""Validate frozen existing judge components; no runtime/prompt tuning or edits.

Gold is deliberately never opened here. This is a supplied-claim/abstract
component experiment, not an end-to-end research-agent evaluation.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import re
import time
from types import SimpleNamespace


LABELS = {"supported","partial","unsupported","contradicted","unverifiable"}
ASSESSOR_MAP = {"supported":"SUPPORT","contradicted":"CONTRADICT",
                "unsupported":"NEI","unverifiable":"NEI","partial":"PARTIAL"}
NATIVE_MAP = {"supported":"SUPPORT","correct":"SUPPORT","contradiction":"CONTRADICT",
              "scope_correction":"NEI","insufficient_evidence":"NEI"}


def parse_object(raw):
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip()))


def aggregate_assessor(ann, claim, draft, abstract):
    claims = ann.get("claims")
    if not isinstance(claims,list) or not claims:
        raise ValueError("No empirical claim extracted")
    covered = set()
    raw_labels, validated_labels = [], []
    quotes = []
    for unit in claims:
        text = unit.get("text")
        label = unit.get("grounding")
        if not isinstance(text,str) or not text or text not in draft or label not in LABELS:
            raise ValueError("Unlocalizable claim or invalid label")
        start = draft.find(text)
        covered.update(range(start,start+len(text)))
        evidence = unit.get("evidence",[])
        good = bool(evidence) and all(isinstance(e,dict) and e.get("source_id")==1
            and isinstance(e.get("quote"),str) and e["quote"] and e["quote"] in abstract for e in evidence)
        quotes.append(good)
        raw_labels.append(label)
        validated_labels.append("unverifiable" if label in {"supported","partial","contradicted"} and not good else label)
    needed = {i for i,c in enumerate(claim) if not c.isspace()}
    complete = needed <= covered
    def combine(labels):
        if not complete: return "MISSING"
        if "contradicted" in labels:return "CONTRADICT"
        if all(x=="supported" for x in labels):return "SUPPORT"
        if "partial" in labels:return "PARTIAL"
        return "NEI"
    return {"raw_prediction":combine(raw_labels),"prediction":combine(validated_labels),
            "claim_text_fully_covered":complete,"decomposed_units":len(claims),
            "units_with_exact_quote":sum(quotes),"exact_quote_denominator":len(quotes),
            "raw_unit_labels":raw_labels,"validated_unit_labels":validated_labels}


def native_result(issues, checked, abstract):
    units = [u for u in issues+checked if u.get("claim_id")==0]
    if len(units)!=1:
        raise ValueError("Missing or duplicate native claim judgment")
    unit = units[0]
    status = unit.get("status")
    prediction = NATIVE_MAP.get(status,"MISSING")
    quote = unit.get("evidence_quote")
    quotes = [quote] if isinstance(quote,str) else quote if isinstance(quote,list) else []
    quoted = bool(quotes) and all(isinstance(q,str) and q and q in abstract for q in quotes)
    quoted = quoted and unit.get("source_id")==1
    return {"raw_prediction":prediction,
            "prediction":"MISSING" if prediction in {"SUPPORT","CONTRADICT"} and not quoted else prediction,
            "native_status":status,"native_reviewer_status":unit.get("reviewer_status"),
            "exact_quote_valid":quoted,"quote_source_id":unit.get("source_id")}


def main():
    from loguru import logger
    logger.remove()
    import local_deep_research
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.citation_handler import CitationHandler
    from research_verify.generation import format_source_documents
    from research_verify.evidence_flow import review_prompt,parse_review
    root = Path("/experiment")
    protocol = json.loads((root/"protocol.json").read_text())
    if hashlib.sha256((root/"cases.jsonl").read_bytes()).hexdigest()!=protocol["cases_sha256"]:
        raise ValueError("Input cases changed")
    cases = [json.loads(line) for line in (root/"cases.jsonl").read_text().splitlines()]
    rubric = (root/"rubric.txt").read_text()
    if hashlib.sha256(rubric.encode()).hexdigest()!=protocol["rubric_sha256"]:
        raise ValueError("Rubric changed")
    defaults = Path(local_deep_research.__file__).parent/"defaults/default_settings.json"
    settings = apply_environment_overrides_to_snapshot({k:v.get("value") for k,v in json.loads(defaults.read_text()).items()})
    settings.update(protocol["settings"])
    public = {k:settings.get(k) for k in protocol["record_setting_keys"]}
    public["settings_sha256"] = hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    shard = int(os.environ.get("CALIBRATION_SHARD","0"))
    (root/("settings-"+str(shard)+".json")).write_text(json.dumps(public,indent=2))
    queue = [(arm,case) for arm in protocol["arms"] for case in cases]
    random.Random(20261110).shuffle(queue)
    out = root/"outputs"
    out.mkdir(exist_ok=True)
    with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:settings.get(k,d))):
        model = get_llm(settings_snapshot=settings)
        handler = CitationHandler(model,handler_type="standard",settings_snapshot=settings)
        native = getattr(handler,"_handler",handler)
        for position,(arm,case) in enumerate(queue):
            if position%2!=shard:continue
            path = out/(arm+"-"+case["case_id"]+".json")
            if path.exists():continue
            draft = case["claim"]+" [1]"
            abstract = case["sources"][0]["abstract"]
            if arm=="existing_report_assessor":
                prompt = rubric+"\nINPUT DATA:\n"+json.dumps({"question":case["question"],
                    "obligations":[],"draft":draft,"sources":case["sources"]},ensure_ascii=False)
                targets = None
            else:
                docs = native._create_documents(case["sources"])
                material = format_source_documents(docs,case["question"]+"\n"+draft,
                                                    max_chars=60000,required_ids={1})
                targets = {0:{"claim_id":0,"text":draft,"source_ids":[1],
                              "section_context":[],"table_context":None}}
                prompt = review_prompt(case["question"],draft,material,claims=targets)
            base = path.with_suffix("")
            Path(str(base)+".prompt.txt").write_text(prompt)
            start = time.monotonic()
            row = {"case_id":case["case_id"],"arm":arm,"model":public["llm.model"],
                   "settings_sha256":public["settings_sha256"],"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest()}
            try:
                response = model.invoke(prompt)
                raw = response.content
                Path(str(base)+".response.txt").write_text(raw)
                row["usage"] = getattr(response,"usage_metadata",None)
                if arm=="existing_report_assessor":
                    ann = parse_object(raw)
                    result = aggregate_assessor(ann,case["claim"],draft,abstract)
                else:
                    issues,checked = parse_review(raw,targets,include_checked=True)
                    result = native_result(issues,checked,abstract)
                row.update(status="completed_component_assessment",**result)
            except Exception as error:
                row.update(status="invalid_or_failed",prediction="MISSING",raw_prediction="MISSING",
                           error_type=type(error).__name__,error=str(error))
            row["latency_seconds"] = time.monotonic()-start
            path.write_text(json.dumps(row,ensure_ascii=False,indent=2))
            print(json.dumps({k:row.get(k) for k in ("case_id","arm","status","error_type","prediction","latency_seconds")}),flush=True)


if __name__ == "__main__":main()
