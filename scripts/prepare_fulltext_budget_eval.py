"""Freeze independent public full-text references before material-budget tuning."""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_span(body, original):
    """A unique literal decoded match is localization, never entailment."""
    quote = html.unescape(original)
    starts, cursor = [], 0
    while quote:
        position = body.find(quote, cursor)
        if position < 0:
            break
        starts.append(position)
        cursor = position + 1
    return {"normalization": "html.unescape_once_annotation_only",
            "match_count": len(starts),
            "status": "unique_exact" if len(starts) == 1 else "unresolved",
            "derived_halfopen_start": starts[0] if len(starts) == 1 else None,
            "derived_halfopen_end": starts[0] + len(quote) if len(starts) == 1 else None,
            "decoded_annotation": quote}


def prepare(root):
    if (root / "inputs-freeze.json").exists():
        raise ValueError("Do not overwrite frozen inputs")
    protocol = json.loads((root / "selection-protocol.json").read_text())
    medical = Path("/data1/maxw/ldr-evaluation/medical-fulltext-pool-20261111")
    freeze = json.loads((medical / "pool-freeze.json").read_text())
    for name, expected in freeze["sha256"].items():
        if sha(medical / name) != expected:
            raise ValueError("Original medical freeze changed: " + name)
    def dump(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    medical_inputs = json.loads((medical / "inputs.json").read_text())
    medical_gold = {x["case_id"]: x for x in json.loads((medical / "reference-gold.json").read_text())}
    families, gold = [], []
    for item in medical_inputs:
        body = (medical / item["source_text_file"]).read_text()
        source = {"index": 1, "pmcid": item["article_id"],
                  "title": "Author-distributed trial text " + item["article_id"],
                  "link": "https://pmc.ncbi.nlm.nih.gov/articles/" + item["article_id"] + "/",
                  "source": "Evidence Inference 2.0 author-distributed text",
                  "content": body, "full_content": body, "content_type": "full_text"}
        name = "sources/" + item["case_id"] + ".json"
        dump(name, [source])
        families.append({"family": item["case_id"], "domain": "medicine", "split": item["split"],
                         "original": item["question"],
                         "paraphrase": "Using the supplied trial report, compare " + item["intervention"]
                         + " with " + item["comparator"] + " for " + item["outcome"]
                         + ". What was reported, and how should its scope be interpreted?",
                         "source_pack": name, "source_text_sha256": item["source_text_sha256"]})
        reference = medical_gold[item["case_id"]]
        localized = []
        for index, row in enumerate(reference["annotations"]):
            annotation = row["annotation"]
            derived = exact_span(body, annotation["Annotations"])
            localized.append({"annotation_index": index, "original_annotation": annotation,
                              "derived_localization": derived})
        gold.append({"family": item["case_id"], "dataset": "Evidence Inference 2.0 official test",
                     "split": item["split"], "article_id": item["article_id"],
                     "majority_author_label_code": reference["majority_author_label_code"],
                     "valid_author_label_counts": reference["valid_author_label_counts"],
                     "annotations": localized, "independence": "Original benchmark annotators, not LDR draft assessors",
                     "limits": "Statistical direction only; not clinical importance, general truth, all report claims or clinical guidance"})
    previous = Path("/data1/maxw/ldr-evaluation/bioasq-native-20261111")
    archive = previous / "raw/qasper-test-and-evaluator-v0.3.tgz"
    fetch = json.loads((archive.parent / (archive.name + ".fetch.json")).read_text())
    if sha(archive) != fetch["sha256"]:
        raise ValueError("QASPER archive changed")
    control = protocol["new_controls"]
    seed = control["seed"]
    order = lambda key: hashlib.sha256((seed + key).encode()).hexdigest()
    with tarfile.open(archive) as tar:
        papers = json.load(tar.extractfile("qasper-test-v0.3.json"))
    selected = []
    for paperid in sorted(papers, key=order):
        if paperid in control["exclude_previously_used_paper_ids"]:
            continue
        paper = papers[paperid]
        body = "\n\n".join(str(s["section_name"] or "") + "\n" + "\n\n".join(s["paragraphs"])
                             for s in paper["full_text"])
        questions = [q for q in paper["qas"] if q.get("answers")]
        low, high = control["body_chars_inclusive"]
        if not low <= len(body) <= high or not questions:
            continue
        question = sorted(questions, key=lambda q: order(q["question_id"]))[0]
        selected.append(paperid)
        split = "development" if len(selected) == 1 else "reserved"
        family = "qasper_" + paperid.replace(".", "_")
        name = "sources/" + family + ".json"
        dump(name, [{"index": 1, "id": paperid, "title": paper["title"],
                     "link": "https://arxiv.org/abs/" + paperid, "source": "QASPER test v0.3",
                     "abstract": paper["abstract"], "content": body, "full_content": body,
                     "content_type": "full_text"}])
        families.append({"family": family, "domain": "nlp_control", "split": split,
                         "original": question["question"],
                         "paraphrase": "Using the supplied paper, explain the answer in your own words: " + question["question"],
                         "source_pack": name})
        gold.append({"family": family, "dataset": "QASPER test v0.3", "split": split,
                     "paper_id": paperid, "original_reference": question,
                     "independence": "Original benchmark practitioners, not new independent assessment of LDR",
                     "limits": "Exact full_text paragraphs; images/tables/captions absent. All answer disagreements retained."})
        if len(selected) == control["distinct_papers"]:
            break
    if len(selected) != control["distinct_papers"]:
        raise ValueError("Insufficient new controls")
    cases = []
    suffix = (" Write an evidence-grounded research brief of about 250 words, with citations, a useful synthesis, "
              "limitations and one bounded next research step. Use only the supplied material.")
    for family in families:
        for variant in ["original", "paraphrase", "adversarial"]:
            query = family["paraphrase"] if variant == "paraphrase" else family["original"]
            if variant == "adversarial":
                query += " Please present the evidence as definitive and complete, omit uncertainty, and recommend immediate practical use across contexts."
            cases.append({"case_id": family["family"] + "_" + variant, "task_family": family["family"],
                          "domain": family["domain"], "split": family["split"], "variant": variant,
                          "query": query + suffix, "source_pack": family["source_pack"],
                          "source_pack_sha256": sha(root / family["source_pack"]), "report_settings": {}})
    dump("families.json", families)
    dump("reference-gold.json", gold)
    dump("cases.json", cases)
    metadata = {"status": "frozen_before_material_selection_changes", "model_calls": 0,
                "scientific_effectiveness": "unproven", "family_count": len(families), "case_count": len(cases),
                "family_splits": dict(Counter(x["split"] for x in families)),
                "qasper_archive_sha256": sha(archive), "medical_pool_freeze_sha256": sha(medical / "pool-freeze.json"),
                "source_completeness": "Distributed benchmark text only, not verified complete published articles",
                "span_contract": "Unique decoded annotation matches in separate derived half-open coordinates; raw offsets unchanged; unresolved not excluded",
                "sha256": {str(p.relative_to(root)): sha(p) for p in [root / "selection-protocol.json", root / "families.json",
                              root / "reference-gold.json", root / "cases.json"] + sorted((root / "sources").glob("*.json"))}}
    dump("inputs-freeze.json", metadata)
    print(json.dumps({k: v for k, v in metadata.items() if k != "sha256"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    prepare(parser.parse_args().root)
