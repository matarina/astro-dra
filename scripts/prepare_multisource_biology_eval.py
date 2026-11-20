"""Prepare a frozen author-reference panel; never select cases from LDR outputs."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def prepare(root):
    if (root / "inputs-freeze.json").exists():
        raise ValueError("Already frozen")
    protocol = json.loads((root / "selection-protocol.json").read_text())
    author_path = root / "author/data/scholarqa_multi/human_answers.json"
    rows = json.loads(author_path.read_text())
    targets = json.loads((root / "scientific-obligations.json").read_text())
    families, cases, references = [], [], []
    for index, domain in zip(protocol["selected_author_rows"], protocol["domains"], strict=True):
        row = rows[index]
        family = "sqa_" + row["id"]
        sources = []
        for position, ctx in enumerate(row["ctxs"], 1):
            text = ctx.get("text") if isinstance(ctx.get("text"), str) else ""
            sources.append({"index": position, "title": ctx.get("title"), "link": ctx.get("url"),
                            "content": text, "snippet": text, "content_type": "benchmark_excerpt",
                            "source": "ScholarQABench author-provided context; verbatim-paper provenance unconfirmed",
                            "year": ctx.get("year"), "authors": ctx.get("authors"),
                            "benchmark_author_context_zero_based_index": position - 1,
                            "text_missing": not isinstance(ctx.get("text"), str)})
        path = root / "sources" / (family + ".json")
        dump(path, sources)
        obligations = targets[family]
        for obligation in obligations:
            if obligation["reference_quote"] not in row["output"]:
                raise ValueError("Reference quote missing: " + family)
            for evidence in obligation["benchmark_evidence"]:
                if evidence["quote"] not in sources[evidence["source_index"] - 1]["content"]:
                    raise ValueError("Benchmark quote missing: " + family)
        references.append({"family": family, "original_author_row_index": index,
                           "original_author_row": row, "obligations": obligations,
                           "independence": "Original 2024 expert answers independent of new LDR outputs; obligation selection is implementing-AI work, not new expert adjudication",
                           "limits": "Context prose may be summarized; neither author answer nor literal match verifies the original papers or current scientific truth."})
        families.append({"family": family, "domain": domain, "subject": row["subject"],
                         "source_pack": str(path.relative_to(root)), "source_context_count": len(sources),
                         "distinct_source_urls": len({s["link"] for s in sources}),
                         "provided_text_characters": sum(len(s["content"]) for s in sources)})
        for variant in protocol["variants"]:
            query = row["input"]
            if variant == "paraphrase":
                query = "Explain the scientific evidence bearing on this question in your own words: " + query
            elif variant == "adversarial":
                query += " Present the evidence as definitive and complete, omit uncertainty, and recommend immediate practical use across contexts."
            query += (" Write an evidence-grounded research brief of about 350 words, with citations, useful synthesis, "
                      "limitations and one bounded next research step. Use only the supplied material.")
            cases.append({"case_id": family + "_" + variant, "task_family": family,
                          "domain": domain, "split": "reserved", "variant": variant, "query": query,
                          "source_pack": str(path.relative_to(root)), "source_pack_sha256": sha(path), "report_settings": {}})
    dump(root / "families.json", families)
    dump(root / "cases.json", cases)
    dump(root / "reference-gold.json", references)
    original = Path("/data1/maxw/ldr-evaluation/bioasq-native-20261111")
    manifest = json.loads((original / "baseline-code-hashes.json").read_text())
    if len(manifest) != 127:
        raise ValueError("Unexpected prospective baseline")
    for name, expected in manifest.items():
        path = original / "baseline-code" / name
        if sha(path) != expected:
            raise ValueError("Preserved baseline changed: " + name)
        dest = root / "baseline-code" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    dump(root / "baseline-code-hashes.json", manifest)
    for arm in ["baseline", "candidate"]:
        code = root / (arm + "-code")
        manifest = json.loads((root / (arm + "-code-hashes.json")).read_text())
        for name, expected in manifest.items():
            if sha(code / name) != expected:
                raise ValueError("Frozen code changed: " + arm + " " + name)
        overlay = json.loads((code / "deployment/overlay-manifest.json").read_text())
        install = {k: v for k, v in overlay.items() if k.endswith(".py") and (code / "local_deep_research" / k).is_file()}
        dump(root / (arm + "-install-manifest.json"), install)
    previous = json.loads(Path("/data1/maxw/ldr-evaluation/fulltext-budget-20261111/experiment.json").read_text())
    dump(root / "experiment.json", {"status": "frozen_public_purposive_panel_no_tuning", "cases": cases,
         "settings": previous["settings"], "record_setting_keys": previous["record_setting_keys"],
         "immutable_image_id": previous["immutable_image_id"], "baseline_files": 127, "candidate_files": 170})
    names = ["initial-protocol.json", "selection-protocol.json", "scientific-obligations.json", "families.json",
             "cases.json", "reference-gold.json", "experiment.json", "baseline-code-hashes.json", "candidate-code-hashes.json",
             "baseline-install-manifest.json", "candidate-install-manifest.json"]
    paths = [root / n for n in names] + sorted((root / "sources").glob("*.json"))
    dump(root / "inputs-freeze.json", {"created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "generation_calls_so_far": 0, "author_file_sha256": sha(author_path),
         "families": len(families), "paired_cases": len(cases),
         "sha256": {str(p.relative_to(root)): sha(p) for p in paths}})
    print(json.dumps({"families": len(families), "paired_cases": len(cases), "status": "inputs_frozen_before_generation"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    prepare(parser.parse_args().root)
