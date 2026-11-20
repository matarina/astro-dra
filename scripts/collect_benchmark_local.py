"""Summarize predeclared AREX auxiliary judgments without promoting them to gold."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from collect_benchmark_reports import answer_strings


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    out=root/"arex-assessment"
    protocol=json.loads((out/"protocol.json").read_text())
    terminal=json.loads((out/"terminal.json").read_text())
    for name,h in {**protocol["drafts_sha256"],**protocol["inputs_sha256"]}.items():
        if sha(root/name)!=h:raise ValueError("Local assessor input changed")
    if sha(out/"checkpoint-files.json")!=protocol["checkpoint_sha256"]:raise ValueError("Checkpoint manifest changed")
    runners=json.loads((out/"runner-manifest.json").read_text())
    for name,h in runners["sha256"].items():
        if sha(out/"run-code"/name)!=h:raise ValueError("Preserved local runner changed")
    cfg=json.loads((root/"experiment.json").read_text())
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text())}
    result={"status":"completed_auxiliary_different_family_assessment","scope":protocol["selection"],"terminal":terminal,"arms":{}}
    for arm in ["baseline","candidate"]:
        rows=[];units=[];invalid=0;refs=[];tokens=Counter();latencies=[]
        for a,caseid,method in protocol["order"]:
            if a!=arm:continue
            path=out/(arm+"-"+caseid+"-"+method+".json");row=json.loads(path.read_text())
            packet=json.loads(Path(str(path.with_suffix(""))+".http.json").read_text())
            if packet["choices"][0]["finish_reason"]!=row.get("finish_reason"):raise ValueError("Raw response differs")
            if row["draft_sha256"]!=sha(root/arm/(caseid+".json")):raise ValueError("Draft changed")
            rows.append({"case_id":caseid,"method":method,"status":row["status"]})
            latencies.append(row["latency_seconds"])
            for key in ["prompt_tokens","completion_tokens","total_tokens"]:
                if isinstance((row.get("usage") or {}).get(key),int):tokens[key]+=row["usage"][key]
            if method=="grounding":
                units.extend(row.get("claims",[]));invalid+=len(row.get("invalid_claims",[]))
            else:
                case=next(c for c in cfg["cases"] if c["case_id"]==caseid)
                source=answer_strings(gold[case["task_family"]]["original_reference"])
                draft=json.loads((root/arm/(caseid+".json")).read_text())["body"]
                for original in row.get("reference_units",[]):
                    unit=dict(original);quote=unit.get("reference_quote");draftquote=unit.get("draft_quote")
                    unit["reference_quote_localized"]=isinstance(quote,str) and bool(quote) and any(quote in s for s in source)
                    unit["draft_quote_localized"]=isinstance(draftquote,str) and bool(draftquote) and draftquote in draft
                    unit["localized_alignment"]=unit.get("alignment") if unit["reference_quote_localized"] and (
                        unit.get("alignment") in {"missing","unknown"} or unit["draft_quote_localized"]) else "unknown"
                    refs.append(unit)
        result["arms"][arm]={"requests":rows,"localized_claim_items":len(units),"invalid_or_unlocalizable_claim_items":invalid,
            "raw_labels":dict(Counter(u["raw_grounding"] for u in units)),"quote_checked_labels":dict(Counter(u["quote_checked_grounding"] for u in units)),
            "units_with_exact_source_quotes":sum(u["quoted_span_exists"] for u in units),
            "citation_entailment_labels":{"true":sum(u.get("citation_entails") is True for u in units),"false":sum(u.get("citation_entails") is False for u in units),"missing":sum(not isinstance(u.get("citation_entails"),bool) for u in units)},
            "reference_unit_alignments":dict(Counter(u["localized_alignment"] for u in refs)),
            "assessor_usage":dict(tokens),"assessor_total_seconds":sum(latencies),
            "grounding_report_usefulness":[json.loads((out/(arm+"-"+caseid+"-grounding.json")).read_text()).get("usefulness") for a,caseid,m in protocol["order"] if a==arm and m=="grounding"]}
    result["artifact_sha256"]={str(p.relative_to(out)):sha(p) for p in out.rglob("*") if p.is_file()}
    result["limitations"]=["Only two original bioinformatics families, four drafts; no paraphrase/adversarial or cross-domain model comparison.",
        "Different-model-family judgments and original references do not constitute new independent human draft gold.",
        "Fresh decomposition differs across assessors; aggregate counts cannot establish same-claim agreement. Invalid items remain explicit missing labels.",
        "Exact quote presence is not entailment. Reference alignment is not source truth. No overall hallucination or model-superiority claim.",
        "Times/tokens are assessment costs, not generation latency; shared GPU performance impact on neighbors not measured."]
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=collect(args.root);args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({a:{k:v for k,v in d.items() if k not in ["requests"]} for a,d in result["arms"].items()},indent=2))
