"""Collect frozen report comparisons; retain missing/partial assessment evidence."""
import argparse
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

from evidence_eval_metrics import paired


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer_strings(reference):
    values=[]
    def add(value):
        if isinstance(value,str):values.append(value)
        elif isinstance(value,list):
            for item in value:add(item)
    for key in ["ideal_answer","exact_answer"]:
        add(reference.get(key))
    for response in reference.get("answers",[]):
        answer=response["answer"]
        add(answer.get("free_form_answer"))
        add(answer.get("extractive_spans"))
        if isinstance(answer.get("yes_no"),bool):
            values.append("yes" if answer["yes_no"] else "no")
    return values


def collect(root):
    freeze=json.loads((root/"freeze.json").read_text())
    for name,h in freeze["sha256"].items():
        if sha(root/name)!=h:raise ValueError("Frozen artifact changed: "+name)
    cfg=json.loads((root/"experiment.json").read_text())
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text())}
    assessment_protocol=json.loads((root/"assessment-protocol.json").read_text())
    for name,h in assessment_protocol["sha256"].items():
        if sha(root/name)!=h:raise ValueError("Assessment artifact changed: "+name)
    if (root/"assessment-drafts-hashes.json").exists():
        for name,h in json.loads((root/"assessment-drafts-hashes.json").read_text()).items():
            if sha(root/name)!=h:raise ValueError("Frozen assessed draft changed")
    manifests={arm:json.loads((root/(arm+"-code-hashes.json")).read_text()) for arm in ["baseline","candidate"]}
    for arm,manifest in manifests.items():
        for name,h in manifest.items():
            if sha(root/(arm+"-code")/name)!=h:raise ValueError("Frozen code changed")
    # Common syntax-only parser for citation-use diagnostics, not a semantic scorer.
    sys.path.insert(0,str(root/"candidate-code/local_deep_research"))
    from research_verify.claims import extract_report_claims
    runs={}
    integrity={}
    coverage={}
    costs={}
    references={}
    for arm in manifests:
        rows=[];checks=[];summaries=[];reference_rows=[];usage=Counter()
        for case in cfg["cases"]:
            path=root/arm/(case["case_id"]+".json")
            if not path.exists():
                rows.append({**case,"status":"missing","claims":[]});continue
            row=json.loads(path.read_text())
            sources=json.loads((root/case["source_pack"]).read_text())
            if row["source_pack_sha256"]!=sha(root/case["source_pack"]):raise ValueError("Run source hash changed")
            installed=json.loads((root/arm/(case["case_id"]+".installed.json")).read_text())
            for name,h in installed.items():
                expected=manifests[arm][name]
                if name.endswith("/langgraph_agent_strategy.py"):
                    module=ast.parse((root/(arm+"-code/deployment/install_overlays.py")).read_text())
                    hook=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id=="COLLECTION_HOOK" for t in n.targets))
                    text=(root/(arm+"-code")/name).read_text()
                    expected=hashlib.sha256((text if "# Source collection feedback and stable-identifier deduplication." in text else text+hook).encode()).hexdigest()
                if h!=expected:raise ValueError("Installed module mismatch")
            same_sources=row.get("sources")==sources
            actual=row.get("sources",[])
            provided_fields_preserved=len(actual)==len(sources) and all(
                all(a.get(key)==value for key,value in b.items()) for a,b in zip(actual,sources))
            identifier=hashlib.sha256(("intent-"+arm+"-"+case["case_id"]).encode()).hexdigest()[:32]
            folder=root/arm/"traces"/identifier
            stages=Counter();writer_prompts=[];snapshots=[];trace_bytes=0
            for log in folder.rglob("events.jsonl"):
                for line in log.read_text().splitlines():
                    event=json.loads(line);stages[event["stage"]]+=1
                    if event.get("status")!="recorded":continue
                    raw=gzip.open(log.parent/event["file"],"rb").read()
                    if len(raw)!=event["bytes"] or hashlib.sha256(raw).hexdigest()!=event["sha256"]:
                        raise ValueError("Trace payload changed")
                    trace_bytes+=1;payload=json.loads(raw)
                    if event["stage"]=="input_sources":
                        received=payload["sources"]
                        snapshots.append(len(received)==len(sources) and all(
                            all(a.get(k)==b.get(k) for k in ["index","link","abstract","body","content","full_content"])
                            for a,b in zip(received,sources)))
                    if event["stage"]=="writer_request":writer_prompts.append(payload["prompt"])
            texts=[s.get("body") or s.get("abstract") or "" for s in sources]
            full=sum(bool(t.strip()) and any(t.strip() in p for p in writer_prompts) for t in texts)
            normalized_prompts=[" ".join(p.split()) for p in writer_prompts]
            full_whitespace=sum(bool(t.strip()) and any(" ".join(t.split()) in p for p in normalized_prompts) for t in texts)
            reference=gold[case["task_family"]]["original_reference"]
            expert_evidence=([s["text"] for s in reference.get("snippets",[])] if "snippets" in reference else
                [text for answer in reference.get("answers",[]) for text in answer["answer"].get("evidence",[])])
            evidence_present=sum(bool(text.strip()) and any(" ".join(text.split()) in p for p in normalized_prompts) for text in expert_evidence)
            cited={i for unit in extract_report_claims(row.get("body","")) for i in unit.citations}
            valid_ids={int(s["index"]) for s in sources}
            check={"case_id":case["case_id"],"status":row.get("status"),"installed_modules_verified":len(installed),
                "output_sources_exactly_preserved":same_sources,"input_source_snapshots":len(snapshots),
                "provided_output_source_fields_preserved":provided_fields_preserved,
                "input_text_snapshots_preserved":bool(snapshots) and all(snapshots),"trace_payloads_verified":trace_bytes,
                "native_check_requests":stages["native_check_request"],"stage_counts":dict(stages),
                "source_texts_with_complete_substring_in_writer_prompt":full,"nonempty_supplied_texts":sum(bool(t.strip()) for t in texts),
                "source_texts_with_complete_whitespace_equivalent_in_writer_prompt":full_whitespace,
                "expert_evidence_passages_lexically_present_in_writer_prompt":evidence_present,
                "expert_evidence_passage_denominator":len(expert_evidence),
                "citation_ids_outside_supplied_pool":sorted(cited-valid_ids)}
            publication=(row.get("publication") or {}).get("claim_publication") or {}
            check["publication_audit_disabled"]=publication.get("audit_status")=="disabled"
            check["report_status_unverified"]=publication.get("status")=="unverified"
            checks.append(check)
            summaries.append({"case_id":case["case_id"],"task_family":case["task_family"],"domain":case["domain"],
                "supplied_sources":len(sources),"cited_supplied_sources":len(cited&valid_ids),
                "complete_text_exposed":full,"whitespace_equivalent_complete_text_exposed":full_whitespace,
                "expert_evidence_passages_lexically_present_in_writer_prompt":evidence_present,
                "expert_evidence_passage_denominator":len(expert_evidence),
                "citation_use_basis":"common candidate claim-candidate parser; heading/role heuristics remain an open limitation, not an independently validated recall endpoint",
                "nonempty_texts":check["nonempty_supplied_texts"]})
            annpath=root/"assessment"/(arm+"-"+case["case_id"]+"-grounding.json")
            ann=json.loads(annpath.read_text()) if annpath.exists() else {"status":"missing"}
            if ann.get("draft_sha256") and ann["draft_sha256"]!=sha(path):raise ValueError("Assessed draft changed")
            if annpath.exists():
                prompt=Path(str(annpath.with_suffix(""))+".prompt.txt")
                if ann.get("prompt_sha256")!=sha(prompt):raise ValueError("Grounding prompt changed")
                data=json.loads(prompt.read_text().split("\nINPUT DATA:\n",1)[1])
                if data.get("draft")!=row.get("body") or data.get("sources")!=sources or data.get("question")!=case["query"] or "reference_answers" in data:
                    raise ValueError("Grounding input/arm/reference isolation mismatch")
                if ann.get("arm")!=arm or ann.get("case_id")!=case["case_id"]:
                    raise ValueError("Grounding result binding mismatch")
            valid=ann["status"] in {"annotated_model_assisted","partial_annotation"}
            claims=ann.get("claims",[]) if valid else []
            row.update(claims=claims,assessment_status=ann["status"],usefulness=ann.get("usefulness") if valid else None,
                invalid_claim_count=len(ann.get("invalid_claims",[])),claims_decomposition_completeness="not_independently_verified")
            rows.append(row)
            rp=root/"assessment"/(arm+"-"+case["case_id"]+"-reference_alignment.json")
            ref=json.loads(rp.read_text()) if rp.exists() else {"status":"missing"}
            if rp.exists():
                prompt=Path(str(rp.with_suffix(""))+".prompt.txt")
                if ref.get("prompt_sha256")!=sha(prompt) or ref.get("draft_sha256")!=sha(path):
                    raise ValueError("Reference prompt/draft changed")
                data=json.loads(prompt.read_text().split("\nINPUT DATA:\n",1)[1])
                expected_reference=gold[case["task_family"]]["original_reference"]
                expected_answers={k:expected_reference[k] for k in ["ideal_answer","exact_answer","answers"] if k in expected_reference}
                if data.get("draft")!=row.get("body") or data.get("reference_answers")!=expected_answers or data.get("original_question")!=(expected_reference.get("body") or expected_reference.get("question")):
                    raise ValueError("Reference input binding mismatch")
            original=answer_strings(gold[case["task_family"]]["original_reference"])
            units=[]
            for raw in ref.get("reference_units",[]):
                unit=dict(raw);quote=unit.get("reference_quote")
                unit["reference_quote_localized"]=isinstance(quote,str) and bool(quote) and any(quote in text for text in original)
                unit["draft_quote_localized"]=isinstance(unit.get("draft_quote"),str) and bool(unit["draft_quote"]) and unit["draft_quote"] in row.get("body","")
                unit["localized_alignment"]=unit.get("alignment") if unit["reference_quote_localized"] and (
                    unit.get("alignment") not in {"covered","partial","conflicting"} or unit["draft_quote_localized"]) else "unknown"
                units.append(unit)
            reference_rows.append({"case_id":case["case_id"],"status":ref["status"],"units":units})
            calls=root/arm/(case["case_id"]+".calls.json")
            if calls.exists():
                for event in json.loads(calls.read_text()):
                    usage["recorded_calls"]+=1
                    if isinstance(event.get("usage"),dict):
                        usage["calls_with_usage"]+=1
                        for key in ["input_tokens","output_tokens","total_tokens"]:
                            value=event["usage"].get(key)
                            if isinstance(value,int) and not isinstance(value,bool):usage[key]+=value
        runs[arm]={"system":arm,"cases":rows,"assessment":{"independence":"blinded same model family; original benchmark references independent, draft assessments not independent human"}}
        integrity[arm]=checks;coverage[arm]=summaries;costs[arm]=dict(usage);references[arm]=reference_rows
    raw_metrics=paired(runs["baseline"],runs["candidate"])
    checked={arm:json.loads(json.dumps(run)) for arm,run in runs.items()}
    for run in checked.values():
        for row in run["cases"]:
            for claim in row.get("claims",[]):claim["grounding"]=claim["quote_checked_grounding"]
    return {"status":"collected_with_explicit_missing_endpoints","root":str(root),"scheduled_families":10,"scheduled_pairs":30,
        "overall_effectiveness":"unproven",
        "empirical_hallucination_endpoint_validity":"not_established: assisted extraction/classification and writer-versus-source reading scope require independent adjudication",
        "runtime_tuning_during_evaluation":False,"raw_assisted_metrics":raw_metrics,
        "quote_checked_assisted_metrics":paired(checked["baseline"],checked["candidate"]),
        "integrity":integrity,"source_exposure_and_citation_use":coverage,"generation_token_usage":costs,
        "reference_alignment":references,
        "annotation_coverage":{arm:{"report_statuses":dict(Counter(r.get("assessment_status","missing") for r in run["cases"])),
            "invalid_claim_items":sum(r.get("invalid_claim_count",0) for r in run["cases"])} for arm,run in runs.items()},
        "limitations":["Public convenience sample; model pretraining exposure unknown, not representative heldout LDR traffic.",
            "Baseline is preserved127-file Python backend, not complete original production deployment; UI assets absent, both use Python-only install.",
            "Native generation with fixed sources; no search-agent or full-literature recall endpoint.",
            "Same-family assisted judgments can share mistakes; extraction completeness and reference-unit decomposition not independently adjudicated.",
            "Reference alignment is not source entailment; exact quotes and source preservation are not scientific correctness.",
            "The reference payload includes nested QASPER evidence, while reference-quote localization accepts answer strings only. Rejections remain unknown and do not prove missing answer content.",
            "Reference-passage exposure is whitespace-only string localization in writer prompts, not reading comprehension or semantic coverage. Repeated annotations/variants are not independent evidence units.",
            "Output dictionary equality can differ because baseline adds lexical advisory fields; preservation of every originally supplied field is measured separately.",
            "Common citation-use parser still skips some findings headings and uses lexical heading cues. Its diagnostic counts cannot establish true citation coverage; report text remains preserved.",
            "Two NLP controls are not broad cross-domain robustness evidence. No effectiveness pass is assigned."]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=collect(args.root)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"matched_pairs":result["raw_assisted_metrics"]["matched_cases"],
        "annotation_coverage":result["annotation_coverage"]},indent=2))
