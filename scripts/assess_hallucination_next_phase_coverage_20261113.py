#!/usr/bin/env python3
"""Create a transparent useful-coverage proxy for the bounded pilot.

This is deliberately a visibility/obligation diagnostic, not a medical
semantic assessor. It never assigns support, contradiction, or entailment.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = {
    "population_or_model": [r"\bpatient", r"\bmouse", r"\bcell", r"\bLCMV", r"\bT[- ]?cell", r"\bB[- ]?cell", r"\beosinophil", r"\bmast"],
    "assay_or_modality": [r"single[- ]cell", r"scRNA", r"RNA[- ]?seq", r"TCR", r"proteom", r"FACS", r"flow cytometry", r"transcriptom", r"sequencing"],
    "finding_or_direction": [r"found", r"showed", r"identified", r"revealed", r"expression", r"increased", r"decreased", r"associated", r"trajectory"],
    "qualifier_or_unknown": [r"unknown", r"not reported", r"abstract", r"limited", r"unclear", r"however", r"although", r"cannot", r"did not", r"not establish"],
}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cited_ids(report):
    return sorted({int(x) for x in re.findall(r"\[(\d+)\]", report)})
def hit(report, pats):
    low = report.lower()
    return any(re.search(p, low, re.I) for p in pats)
def assess(attempt):
    rows=[]
    for result in sorted(attempt.glob("historical-immune/*/result.json")):
        d=json.loads(result.read_text()); report=d.get("body","")
        if not report:
            rp=result.parent/"report.md"
            report=rp.read_text() if rp.exists() else ""
        row={"arm":d.get("arm"),"result":str(result.relative_to(ROOT)),"result_sha256":sha(result),
             "report_sha256":hashlib.sha256(report.encode()).hexdigest(),"report_chars":len(report),
             "cited_source_ids":cited_ids(report),"cited_source_count":len(cited_ids(report)),
             "coverage_proxy":{k:{"visible":hit(report,p),"basis":"lexical visibility only; not semantic support"} for k,p in DIMENSIONS.items()},
             "semantic_verdicts":"unassessed","citation_entailment":"unassessed","usefulness":"unassessed",
             "limitations":["No independent medical adjudication.","A visible term does not prove the requested fact is correct or cited.","Coverage proxy does not measure source recall or omission of important content."]}
        if d.get("semantic_ranking"):
            row["candidate_activation"]={k:d["semantic_ranking"].get(k) for k in ("injected","calls","failures","writer_selection_reached")}
        if d.get("evidence_gap"):
            row["candidate_activation"]={k:d["evidence_gap"].get(k) for k in ("status","influences_writer_input","follow_up_acquisition","writer_context_sha256")}
        if d.get("independent_verification"):
            row["candidate_activation"]={k:d["independent_verification"].get(k) for k in ("status","question_count","batch_count","failures","revision")}
        rows.append(row)
    return {"schema_version":"hallucination_next_phase_coverage_proxy.v1","status":"diagnostic_not_semantic_assessment",
            "attempt":str(attempt.relative_to(ROOT)),"rows":rows,
            "comparison_policy":"Do not interpret lexical visibility, citation count, report length, or candidate execution as hallucination reduction.",
            "missing":"claim-level supported/partial/unsupported/contradicted/unverifiable labels, citation entailment, independent usefulness and source-recall assessment remain unresolved."}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("attempt",type=Path); ap.add_argument("--out",type=Path,required=True); a=ap.parse_args()
    out=a.out if a.out.is_absolute() else ROOT/a.out; out.write_text(json.dumps(assess(a.attempt if a.attempt.is_absolute() else ROOT/a.attempt),ensure_ascii=False,indent=2)+"\n")
    print(out)
if __name__=='__main__': main()
