"""Report expert-known-pool locating and transport, without treating unjudged as irrelevant."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from evidence_eval_metrics import _bootstrap


def collect(root):
    protocol=json.loads((root/"retrieval-protocol.json").read_text())
    for name,h in protocol["sha256"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:
            raise ValueError("Frozen retrieval artifact changed")
    results={};raw={}
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text()) if r["dataset"]=="BioASQ public sample"}
    scheduled_denominator=sum(len(r["known_pool_pmids"]) for r in gold.values())
    for arm in ["baseline","candidate"]:
        rows=[]
        for path in sorted((root/"retrieval"/arm).glob("*.json")):
            row=json.loads(path.read_text())
            if "engine" not in row:continue
            upstream=[];http_errors=0
            for event in row["requests"]:
                http_errors+=int(event.get("status_code",200)>=400 or "error_type" in event)
                if not event.get("file"):continue
                payload=(path.parent/event["file"]).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=event["sha256"]:
                    raise ValueError("Recorded HTTP response overwritten or changed")
                try:packet=json.loads(payload)
                except (ValueError,UnicodeDecodeError):continue
                if isinstance(packet,dict) and isinstance(packet.get("unresponsive_engines"),list):
                    upstream.extend(packet["unresponsive_engines"])
            row["upstream_failures"]=upstream
            row["http_errors"]=http_errors
            rows.append(row)
        raw[arm]=rows
        results[arm]={}
        for engine in protocol["engines"]:
            group=[r for r in rows if r["engine"]==engine]
            complete=[r for r in group if r["status"]=="completed"]
            numerator=sum(r["known_pool_numerator"] for r in complete)
            denominator=sum(r["known_pool_denominator"] for r in complete)
            results[arm][engine]={"scheduled_queries":8,"recorded_queries":len(group),"statuses":dict(Counter(r["status"] for r in group)),
                "known_reference_documents_located":numerator,"known_reference_document_denominator":denominator,
                "known_pool_micro_recall":numerator/denominator if denominator else None,
                "operational_reference_delivery":{"numerator":numerator,"denominator":scheduled_denominator,
                    "rate":numerator/scheduled_denominator,"failed_query_reference_count":sum(len(gold[r["task_family"]]["known_pool_pmids"]) for r in group if r["status"]!="completed"),
                    "meaning":"Confirmed delivered reference IDs / all scheduled expert-known IDs. Failed queries deliver no confirmed IDs; their scientific relevance remains unknown."},
                "known_pool_macro_recall":mean(r["known_pool_numerator"]/r["known_pool_denominator"] for r in complete) if complete else None,
                "queries_locating_at_least_one_reference":sum(r["known_pool_numerator"]>0 for r in complete),
                "returned_sources":sum(r.get("returned",0) for r in group),
                "http_requests":sum(len(r["requests"]) for r in group),"http_errors":sum(r["http_errors"] for r in group),
                "queries_with_upstream_failures":sum(bool(r["upstream_failures"]) for r in group),
                "mean_latency_seconds":mean(r["latency_seconds"] for r in group) if group else None,
                "cases":[{k:r.get(k) for k in ["case_id","domain","status","returned","known_pool_numerator","known_pool_denominator","upstream_failures","http_errors"]} for r in group]}
    pairs=[]
    for b in raw["baseline"]:
        c=next((x for x in raw["candidate"] if x["engine"]==b["engine"] and x["case_id"]==b["case_id"]),None)
        if c is None:continue
        def ids(row):return {s.get("pmid") or s.get("doi") or s.get("link") or s.get("id") for s in row.get("sources",[])}
        x,y=ids(b),ids(c)
        pairs.append({"engine":b["engine"],"case_id":b["case_id"],"shared_returned_ids":len(x&y),
            "baseline_only_ids":len(x-y),"candidate_only_ids":len(y-x),
            "known_reference_delta":c.get("known_pool_numerator",0)-b.get("known_pool_numerator",0)})
    paired_complete={}
    for engine in protocol["engines"]:
        group=[(b,c) for b in raw["baseline"] for c in raw["candidate"] if b["engine"]==c["engine"]==engine
            and b["case_id"]==c["case_id"] and b["status"]==c["status"]=="completed"]
        paired_complete[engine]={"queries":len(group),"known_pool_denominator":sum(b["known_pool_denominator"] for b,c in group),
            "baseline_located":sum(b["known_pool_numerator"] for b,c in group),"candidate_located":sum(c["known_pool_numerator"] for b,c in group),
            "macro_recall_delta":_bootstrap([c["known_pool_numerator"]/c["known_pool_denominator"]-b["known_pool_numerator"]/b["known_pool_denominator"] for b,c in group])}
    return {"status":"collected_native_preview_retrieval","arms":results,"pairs":pairs,"matched_completed_queries":paired_complete,
        "relevance_precision":None,"all_literature_recall":None,"model_calls":0,
        "limitations":["Eight old public biomedical benchmark questions, not representative current research traffic.",
            "Expert-known pool is incomplete. Unmatched returned papers remain unjudged, not false positives.",
            "Native preview adapters with verbatim question and LLM optimization/reranking off, not full search-agent performance.",
            "Different engines have different query semantics, sorts and indexes; do not rank engines by these counts alone.",
            "Concurrent live queries/counterbalanced order do not guarantee stable indexes or matched transport. Single-trial latency is not causal speed evidence.",
            "Empty responses with upstream failures are availability evidence, not evidence that literature is absent. No effectiveness pass assigned."]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=collect(args.root)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    for arm,engines in result["arms"].items():
        for engine,row in engines.items():
            print(arm,engine,{k:row[k] for k in ["recorded_queries","known_reference_documents_located","known_reference_document_denominator","returned_sources","http_requests","http_errors","queries_with_upstream_failures"]})
