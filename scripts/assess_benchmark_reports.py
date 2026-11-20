"""Blinded assisted grounding and separate benchmark-reference alignment.

Reference answers never enter the grounding prompt. Raw and quote-localized
verdicts stay separate. Neither assessor is independent human adjudication.
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(raw):
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip()))


def validate_claims(annotation, draft, sources):
    claims = annotation.get("claims")
    if not isinstance(claims,list):
        raise ValueError("Missing empirical claim list")
    corpus = {int(s["index"]):s.get("body") or s.get("abstract") or "" for s in sources}
    valid,invalid = [],[]
    for position,claim in enumerate(claims):
        if not isinstance(claim,dict) or claim.get("grounding") not in LABELS or not isinstance(claim.get("text"),str) or not claim["text"] or claim["text"] not in draft:
            invalid.append({"position":position,"raw":claim,"reason":"invalid label or nonlocalizable draft text"})
            continue
        evidence=claim.get("evidence")
        quote_ok = isinstance(evidence,list) and bool(evidence) and all(isinstance(e,dict) and
            isinstance(e.get("source_id"),int) and not isinstance(e.get("source_id"),bool) and
            isinstance(e.get("quote"),str) and e["quote"] and e["quote"] in corpus.get(e.get("source_id"),"") for e in evidence)
        unit=dict(claim)
        unit["raw_grounding"]=claim["grounding"]
        unit["quoted_span_exists"]=quote_ok
        unit["quote_checked_grounding"]="unverifiable" if claim["grounding"] in {"supported","partial","contradicted"} and not quote_ok else claim["grounding"]
        cited=claim.get("citations")
        cited_quote=quote_ok and isinstance(cited,list) and all(isinstance(i,int) and not isinstance(i,bool) and i>0 for i in cited) and all(e.get("source_id") in cited for e in evidence)
        unit["raw_citation_entails"]=claim.get("citation_entails")
        if claim.get("citation_entails") is True and not cited_quote:
            unit["citation_entails"]=None
        valid.append(unit)
    return valid,invalid


def main():
    from loguru import logger
    logger.remove()
    import local_deep_research
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    root=Path("/experiment")
    cfg=json.loads((root/"experiment.json").read_text())
    protocol=json.loads((root/"assessment-protocol.json").read_text())
    for name,h in protocol["sha256"].items():
        if sha(root/name)!=h:
            raise ValueError("Assessment input/protocol changed: "+name)
    rubric=(root/"assessment-rubric.txt").read_text()
    reference_rubric=(root/"reference-rubric.txt").read_text()
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text())}
    defaults=Path(local_deep_research.__file__).parent/"defaults/default_settings.json"
    settings=apply_environment_overrides_to_snapshot({k:v.get("value") for k,v in json.loads(defaults.read_text()).items()})
    settings.update(cfg["settings"])
    output=root/"assessment"
    output.mkdir(exist_ok=True)
    queue=[(arm,case) for arm in ["baseline","candidate"] for case in cfg["cases"]]
    random.Random(20261111).shuffle(queue)
    shard=int(os.environ.get("ASSESS_SHARD","0"))
    with settings_context(SimpleNamespace(username=None,get_setting=lambda k,d=None:settings.get(k,d))):
        model=get_llm(settings_snapshot=settings)
        for position,(arm,case) in enumerate(queue):
            if position%2!=shard:
                continue
            row_path=root/arm/(case["case_id"]+".json")
            if not row_path.exists():
                raise ValueError("Scheduled generation result missing")
            row=json.loads(row_path.read_text())
            if row.get("status")!="completed":
                continue
            sources=json.loads((root/case["source_pack"]).read_text())
            for method in ["grounding","reference_alignment"]:
                stem=output/(arm+"-"+case["case_id"]+"-"+method)
                dest=Path(str(stem)+".json")
                if dest.exists():
                    continue
                if method=="grounding":
                    data={"question":row["query"],"obligations":case["obligations"],"draft":row["body"],"sources":sources}
                    prompt=rubric+"\nINPUT DATA:\n"+json.dumps(data,ensure_ascii=False)
                else:
                    reference=gold[case["task_family"]]
                    original=reference["original_reference"]
                    answers={k:original[k] for k in ["ideal_answer","exact_answer","answers"] if k in original}
                    data={"original_question":original.get("body") or original.get("question"),"reference_answers":answers,"draft":row["body"]}
                    prompt=reference_rubric+"\nINPUT DATA:\n"+json.dumps(data,ensure_ascii=False)
                Path(str(stem)+".prompt.txt").write_text(prompt)
                start=time.monotonic()
                ann={"arm":arm,"case_id":case["case_id"],"method":method,"draft_sha256":sha(row_path),
                    "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"assessor_model":settings["llm.model"],
                    "independence":"blinded separate same-model-family request; independent original references only, no new human assessment"}
                try:
                    response=model.invoke(prompt)
                    raw=response.content
                    Path(str(stem)+".response.txt").write_text(raw)
                    ann["usage"]=getattr(response,"usage_metadata",None)
                    parsed=parse(raw)
                    if method=="grounding":
                        valid,invalid=validate_claims(parsed,row["body"],sources)
                        ann.update(status="partial_annotation" if invalid else "annotated_model_assisted",
                            claims=valid,invalid_claims=invalid,raw_claim_count=len(parsed["claims"]),
                            obligations=parsed.get("obligations"),nonempirical=parsed.get("nonempirical"),
                            usefulness=parsed.get("usefulness"),usefulness_rationale=parsed.get("usefulness_rationale"))
                    else:
                        if not isinstance(parsed.get("reference_units"),list):
                            raise ValueError("Missing reference units")
                        for unit in parsed["reference_units"]:
                            if unit.get("alignment") not in {"covered","partial","missing","conflicting","unknown"}:
                                raise ValueError("Invalid reference alignment")
                            quote=unit.get("draft_quote")
                            unit["draft_quote_localized"]=isinstance(quote,str) and bool(quote) and quote in row["body"]
                        ann.update(status="annotated_reference_alignment",**parsed)
                except Exception as error:
                    ann.update(status="annotation_invalid_or_failed",error_type=type(error).__name__,error=str(error))
                ann["latency_seconds"]=time.monotonic()-start
                dest.write_text(json.dumps(ann,ensure_ascii=False,indent=2)+"\n")
                print(json.dumps({k:ann.get(k) for k in ["arm","case_id","method","status","error_type","latency_seconds"]}),flush=True)


if __name__=="__main__":
    main()
