"""Assemble matched native report inputs from preserved retrieval and reference material."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def paper_id(url):
    parsed = urlsplit(url)
    if parsed.hostname not in {"pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov"}:
        return None
    match = re.fullmatch(r"/(?:pubmed/)?([1-9][0-9]*)/?", parsed.path)
    return match[1] if match else None


def main():
    from loguru import logger
    from local_deep_research.web_search_engines.engines import search_engine_europepmc as epmc

    logger.remove()
    root = Path("/experiment")
    if (root / "source-packs-freeze.json").exists():
        raise ValueError("Preserve previously frozen source packs")
    for name, expected in json.loads((root / "freeze.json").read_text())["sha256"].items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError("Retrieval input changed: " + name)
    terminal = json.loads((root / "retrieval-worker-terminal.json").read_text())
    if terminal != {"baseline": 0, "candidate": 0}:
        raise ValueError("Retrieval workers did not terminate cleanly")
    retry = root / "searxng-direct-retry"
    if json.loads((retry / "retrieval-worker-terminal.json").read_text()) != terminal:
        raise ValueError("SearXNG direct retry did not terminate cleanly")
    protocol = json.loads((root / "retrieval-protocol.json").read_text())
    originals = {z["family"]: z for z in json.loads((root / "selected-original-rows.json").read_text())}
    author = {z["id"]: z for z in json.loads((root / "bioasq11-original-selected.json").read_text())}
    families = json.loads((root / "families.json").read_text())
    cases = json.loads((root / "cases.json").read_text())
    packet = json.loads((root / "known-reference-epmc-auth.response").read_bytes())
    epmc.service_get = lambda *args, **kwargs: SimpleNamespace(json=lambda: deepcopy(packet))
    engine = epmc.EuropePMCSearchEngine.__new__(epmc.EuropePMCSearchEngine)
    engine.max_results = 100
    med = {z["pmid"]: z for z in engine._get_previews("Frozen exact-ID MED packet")}
    output = root / "source-packs"
    output.mkdir(exist_ok=False)
    ledger, sources_by_family = [], {}
    for family in families:
        entries = {}

        def add(source, provenance):
            source = deepcopy(source)
            source.pop("index", None)
            source.setdefault("link", source.get("url") or "")
            key = digest(json.dumps(source, ensure_ascii=False, sort_keys=True, allow_nan=False).encode())
            if key not in entries:
                entries[key] = {"source": source, "origins": []}
            entries[key]["origins"].append(provenance)

        original = originals[family["family"]]["source_rows"][0]
        if family["dataset"] == "bioasq":
            reference = author[family["family"].removeprefix("bioasq_")]
            if reference["body"] != family["question"]:
                raise ValueError("Original BioASQ question differs from normalized row")
            for identifier in family["known_pool_pmids"]:
                record = med.get(identifier)
                if record is not None:
                    add(record, {"role": "exact_id_med_record", "pmid": identifier})
                if record is not None and record.get("abstract"):
                    continue
                snippets = [s for s in reference["snippets"] if paper_id(s["document"]) == identifier]
                for snippet in snippets:
                    add({"title": "BioASQ11 excerpt for PMID " + identifier, "link": snippet["document"],
                         "pmid": identifier, "source": "BioASQ11 author excerpt", "content": snippet["text"],
                         "content_type": "benchmark_excerpt"},
                        {"role": "original_author_excerpt", "pmid": identifier,
                         "begin_section": snippet.get("beginSection"), "end_section": snippet.get("endSection")})
        if family["dataset"] == "scholarqa_multi":
            for position, context in enumerate(original["ctxs"]):
                text = context.get("text")
                if not isinstance(text, str):
                    text = ""
                add({"title": context.get("title"), "link": context.get("url") or "",
                     "content": text, "content_type": "benchmark_excerpt",
                     "source": "ScholarQABench supplied context", "year": context.get("year"),
                     "authors": context.get("authors")},
                    {"role": "author_context", "zero_based_position": position})
        if family["dataset"] == "qasper":
            paper = original["paper"]
            text = "\n\n".join(str(s["section_name"] or "") + "\n" + "\n\n".join(s["paragraphs"])
                               for s in paper["full_text"])
            add({"title": paper["title"], "link": "https://arxiv.org/abs/" + original["paper_id"],
                 "abstract": paper["abstract"], "content": text, "full_content": text,
                 "content_type": "full_text", "evidence_scope": "author_distributed_paragraphs",
                 "source": "QASPER distributed paper paragraphs"},
                {"role": "author_distributed_body", "paper_id": original["paper_id"]})
        case_id = family["family_id"] + "_original"
        for arm in ["baseline", "candidate"]:
            for provider in protocol["engines"]:
                prefix = "searxng-direct-retry/" if provider == "searxng" else ""
                filename = prefix + "retrieval/" + arm + "/" + provider + "-" + case_id + ".json"
                row = json.loads((root / filename).read_text())
                for rank, source in enumerate(row.get("sources", [])[:4], 1):
                    add(source, {"role": "retrieved_preview", "path": filename, "rank": rank})
        sources, origins = [], []
        for index, key in enumerate(sorted(entries), 1):
            entry = entries[key]
            sources.append({**entry["source"], "index": index})
            origins.append({"index": index, "source_sha256_without_index": key, "origins": entry["origins"]})
        path = output / (family["family_id"] + ".json")
        write(path, sources)
        sources_by_family[family["family_id"]] = {"source_pack": str(path.relative_to(root)),
                                                 "source_pack_sha256": digest(path.read_bytes())}
        ledger.append({"family": family["family_id"], "domain": family["domain"], "sources": len(sources),
                       "origins": origins, "source_pack": str(path.relative_to(root))})
    write(root / "source-pack-ledger.json", ledger)
    report_cases = []
    for case in cases:
        report_cases.append({**case, **sources_by_family[case["family"]], "task_family": case["family"],
                             "query": case["report_query"], "report_settings": {}})
    write(root / "report-cases.json", report_cases)
    paths = [root / name for name in ["source-pack-protocol.json", "source-pack-supplement.json", "bioasq11-original-receipt.json",
             "bioasq11-original-selected.json", "source-pack-ledger.json", "report-cases.json"]]
    paths.extend(sorted(output.glob("*.json")))
    write(root / "source-packs-freeze.json", {"status": "Frozen before model generation",
          "sha256": {str(p.relative_to(root)): digest(p.read_bytes()) for p in paths},
          "families": len(families), "variants": len(report_cases)})
    print(json.dumps({"families": len(families), "variants": len(report_cases),
                      "source_counts": [row["sources"] for row in ledger]}))


if __name__ == "__main__":
    main()
