"""Read-only replay of saved RNA stages and archive task provenance.

No inference engine, model calls, report repair, or scientific scoring. Writes a
new engineering sidecar only; refuses to replace an existing output directory.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = {}

    def load(path):
        path = Path(path)
        data = (ROOT / path).read_bytes()
        inputs[str(path)] = sha(data)
        return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

    base = Path("evaluation/frontier-strategy-20261113")
    reviewer = Path("evaluation/pane2-independent-review-20261113")
    inventory = load(reviewer / "full-feedback-issue-inventory.json")
    tasks = {t["task_id"]: t for t in inventory["tasks"]}
    assembly = load(base / "archive-locator-sourcepacks-20261114-v2/assembly-audit.json")
    # Explicit archive provenance map, NOT scientific selection or a topic rule.
    task_order = ["task-47c54edcc0eb", "task-6e8e8d113e76",
                  "task-6ac5d65ed736", "task-90ad0dce1609", "task-a9b2517baf83"]
    mappings = []
    for i, (report, task_id) in enumerate(zip(assembly["reports"], task_order, strict=True)):
        path = Path(report["report_path"])
        data = (ROOT / path).read_bytes()
        inputs[str(path)] = sha(data)
        assert inputs[str(path)] == assembly["inputs"][str(path)]
        pack_path = base / f"archive-pii-metadata-overlays-20261115-v1/report-{i:02}/sources.json"
        pack = load(pack_path)
        assert len(pack) == report["sources"]
        mappings.append({"report_id": f"report-{i:02}", "task_id": task_id,
                         "original_question_sha256": tasks[task_id]["original_prompt_sha256"],
                         "report_path": str(path), "report_sha256": sha(data),
                         "source_pack": str(pack_path), "source_records": len(pack)})
    assert sum(m["source_records"] for m in mappings) == 215

    rna = Path("evaluation/archive-prompt-reviewed-20261112/results/reviewed-20261112-archive-41d13d68b84e")
    manifest = load(rna / "manifest.json")
    assert manifest["query"] == tasks["task-41d13d68b84e"]["original_prompt"]
    sources = load(rna / "sources.json")
    source = next(s for s in sources if s["index"] == "81")
    assert source["pmid"] == "42685266"
    body = source["fetched_content"]
    # Exact saved passage, no new primary-source acquisition or gold label.
    quote = "yet they often contain a small fraction of non-human reads that can be exploited for microbial detection"
    assert quote in body
    traces = rna / "traces/reviewed-20261112-archive-41d13d68b84e"
    synth = next(p for p in (ROOT / traces).iterdir() if p.name.startswith("synthesis-"))

    def stage(name):
        return load((synth / name).relative_to(ROOT))

    draft = stage("0002-agent_draft.json.gz")
    writer = stage("0031-writer_request.json.gz")
    written = stage("0032-writer_response.json.gz")
    request = stage("0035-native_check_request.json.gz")
    response = stage("0036-native_check_response.json.gz")
    raw = response["text_used"].strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[len("```json"):-3].strip()
    verdict = json.loads(raw)
    issue = next(x for x in verdict["issues"] if x["claim_id"] == 5)
    atom = next(x for x in issue["atom_checks"] if quote == x["evidence_quote"])
    claim = atom["claim_value"]
    assert atom["result"] == issue["status"] == "supported"
    assert claim in written["text_used"] and claim in request["prompt"]
    assert quote in writer["prompt"] and quote in request["prompt"]
    report_path = rna / "report.md"
    report = (ROOT / report_path).read_bytes()
    inputs[str(report_path)] = sha(report)
    assert claim in report.decode()
    adjudication = load(reviewer / "nonimmune-adjudication.json")
    reviewed = next(x for x in adjudication["records"] if x["issue_id"] == "issue-08")
    assert sha(report) == reviewed["report"]["sha256"]
    assert reviewed["status"] == "unresolved_source_adjudication"

    result = {
        "scope": "Saved-stage engineering diagnosis; no new evaluation or independent adjudication",
        "archive_mapping": mappings,
        "mapping_correction": "Five packs include immune; RNA is absent. Directory name nonimmune-sources does not establish task scope.",
        "rna": {
            "task_id": "task-41d13d68b84e", "source_records": len(sources),
            "report_sha256": sha(report), "report_chars": len(report.decode()),
            "report_version": "Fresh research run on original query, not proved identical to the originally complained-about report",
            "manifest_scope": manifest["scope"],
            "original_feedback_report_uploaded_pdf_field": "empty in topic-09 workbook row",
            "source_index_before_publication": "81", "source_index_in_final_report": "3",
            "source_pmid": source["pmid"], "source_body_sha256": sha(body.encode()),
            "source_body_chars": len(body), "claim": claim, "saved_native_issue": issue,
            "source_quote": quote,
            "literal_exposure": {"writer_source_quote": quote in writer["prompt"],
                                 "native_source_quote": quote in request["prompt"],
                                 "writer_output_claim": claim in written["text_used"],
                                 "native_input_claim": claim in request["prompt"],
                                 "final_report_claim": claim in report.decode()},
            "draft_already_contains_inference": "在测序数据中对应的外源 reads 占比也会很小" in draft["text"],
            "provisional_engineering_interpretation": "A general observation about host-dominated datasets is used as support for the conditional sample-specific peak-to-read-fraction inference. Literal exposure is demonstrated; semantic entailment and original-feedback correction are not.",
            "independent_saved_status": reviewed["status"],
            "remaining_limit": "No matched original-feedback report established; neither usually-small impact nor possible-significant-impact receives a new adjudicated label here.",
        },
        "inputs": inputs, "model_calls": 0, "network_reads": 0,
        "report_modifications": 0, "newly_credited_corrections": 0,
        "next_mechanism_requirement": "Distinguish a measured source relationship from a sample-specific causal/quantitative inference; do not use missing evidence as contradiction or fix it with a topic-specific replacement.",
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    payloads = [{"path": "audit.json", "sha256": sha((args.output / "audit.json").read_bytes())},
                {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha(Path(__file__).read_bytes())}]
    (args.output / "manifest.json").write_text(json.dumps({"payloads": payloads}, indent=2) + "\n")
    print(json.dumps({"archive_tasks": len(mappings), "archive_records": 215,
                      "rna_records": len(sources), "exposure": result["rna"]["literal_exposure"],
                      "newly_credited_corrections": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
