"""Run a deterministic baseline/candidate provenance comparison.

This is deliberately narrower than hallucination evaluation.  It uses the
same fixed metadata records and query strings against two source trees, then
reports denominators for identity/type/publication/peer-review and constrained
IF parsing.  It does not measure report usefulness or claim entailment.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


RECORDS = [
    {"id": "editorial", "publication_types": ["Editorial"], "link": "https://pubmed.ncbi.nlm.nih.gov/99000001/"},
    {"id": "meeting", "publication_types": ["Meeting Abstract"], "link": "https://pubmed.ncbi.nlm.nih.gov/99000002/"},
    {"id": "title_only", "title": "Conference proceedings on a normal study", "publication_types": ["Journal Article"], "link": "https://pubmed.ncbi.nlm.nih.gov/99000003/"},
    {"id": "supplement", "content_type": "supplement", "link": "https://pubmed.ncbi.nlm.nih.gov/99000004/"},
    {"id": "preprint_indexed", "journal": "bioRxiv", "link": "https://pubmed.ncbi.nlm.nih.gov/99000005/"},
    {"id": "search_page", "title": "Search results", "link": "https://example.org/search?q=x"},
]
EXPECTED = {
    "editorial": "editorial",
    "meeting": "conference_abstract",
    "title_only": "journal_article",
    "supplement": "supplement",
    "preprint_indexed": "preprint",
    "search_page": "unknown",
}
QUERIES = [
    ("if_positive", "Find 20 papers with IF>10"),
    ("if_chinese", "影响因子10分以上的研究"),
    ("if_substring", "compare IFN signaling and diffusion"),
]
EXPECTED_IF = {"if_positive": 10.0, "if_chinese": 10.0, "if_substring": None}


def run_tree(root: Path) -> dict:
    code = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from research_verify.source_identity import classify_source
from research_verify.research_spec import parse_research_spec
records=json.loads(sys.argv[2]); queries=json.loads(sys.argv[3])
out={"records":{},"queries":{}}
for r in records:
    x=classify_source(r)
    out["records"][r["id"]]={k:x.get(k) for k in ("identity_status","source_kind","document_type","publication_status","publication_state","peer_review_status")}
for name,q in queries:
    x=parse_research_spec(q)
    out["queries"][name]={"min_if":getattr(x,"min_if_mentioned",None),"if_operator":getattr(x,"if_operator",None),"count":x.requested_count,"count_relation":getattr(x,"count_relation",None)}
print(json.dumps(out,ensure_ascii=False))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code, str(root / "local_deep_research"), json.dumps(RECORDS), json.dumps(QUERIES, ensure_ascii=False)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


def score(result: dict) -> dict:
    type_items = [x for x in RECORDS if x["id"] in EXPECTED]
    type_correct = sum(result["records"][x["id"]]["document_type"] == EXPECTED[x["id"]] for x in type_items)
    type_den = len(type_items)
    if_correct = sum(result["queries"][name]["min_if"] == expected for name, expected in EXPECTED_IF.items())
    if_den = len(EXPECTED_IF)
    return {"document_type_correct": type_correct, "document_type_denominator": type_den,
            "if_syntax_correct": if_correct, "if_syntax_denominator": if_den,
            "all_checks_pass": type_correct == type_den and if_correct == if_den}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    baseline, candidate = run_tree(args.baseline_root), run_tree(args.candidate_root)
    result = {"status": "diagnostic_only", "baseline_provenance": "caller_must_verify_snapshot_integrity", "scope": "constructed metadata fixtures; no generalization claim",
              "baseline": {"scores": score(baseline), "raw": baseline},
              "candidate": {"scores": score(candidate), "raw": candidate},
              "limitations": ["No generated reports, retrieval recall, claim entailment, usefulness, or latency are measured.", "This does not establish an overall hallucination reduction."]}
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.output: args.output.write_text(encoded,encoding="utf-8")
    else: print(encoded,end="")


if __name__ == "__main__":
    main()
