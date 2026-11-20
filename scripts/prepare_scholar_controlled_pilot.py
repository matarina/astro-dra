#!/usr/bin/env python3
"""Prepare frozen inputs for the bounded scholar completion pilot."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/scholar-controlled-pilot-20261112"
INPUT = OUT / "inputs"
FIXED = ROOT / "evaluation/fixed-source-role-20261112"
EXTERNAL = Path("/data1/maxw/ldr-evaluation/bioinformatics-retrieval-20261111/source-packs")
PACKET = ROOT / "evaluation/archive-claim-review-packet-20261112.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packet_source(blind_prefix: str, source_index: str) -> dict:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    for case in packet["cases"]:
        for arm in case["arms"]:
            if arm["blind_id"] == blind_prefix:
                for claim in arm.get("claims", []):
                    for source in claim.get("source_records", []):
                        if str(source.get("index")) == str(source_index) and (source.get("fetched_content") or source.get("full_content")):
                            return source
    raise KeyError((blind_prefix, source_index))


def add_full_source(base: list[dict], index: str, source: dict, evidence_label: str) -> tuple[list[dict], dict]:
    updated = copy.deepcopy(base)
    target = next(x for x in updated if str(x.get("index")) == str(index))
    body = source.get("fetched_content") or source.get("full_content") or source.get("content")
    target["full_content"] = body
    target["content_type"] = "full_text"
    target["evidence_intervention"] = evidence_label
    return updated, {"index": index, "title": target.get("title"), "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "label": evidence_label}


def fetch_biorxiv_html() -> tuple[str, dict]:
    url = "https://doi.org/10.64898/2026.10.13.758932"
    response = requests.get(url, timeout=60, headers={"User-Agent": "LDR controlled evidence pilot/2026-11-12"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    if len(text) < 3000:
        raise RuntimeError("bioRxiv full-text extraction unexpectedly short")
    raw = INPUT / "adipose-biorxiv-primary.html"
    raw.write_text(response.text, encoding="utf-8")
    return text, {"url": response.url, "status": response.status_code, "html_sha256": sha(raw), "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); INPUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ("historical-immune", "case2-sources.json", "目前关注嗜酸性粒细胞、嗜碱性粒细胞、肥大细胞、T细胞，针对于这些细胞，进行单细胞转录组测序，应该如何进行实验方案，提供文献中是否有能力去对目的细胞进行分选、富集及后续的单细胞实验文章，提取文章中的文选方案，单细胞测序平台，以及如此多的细胞如何分选？", "immune_fixed_source_roles-arm-1", "81"),
        ("historical-if", "case4-sources.json", "调研2026年发表的，影响因子10分以上肿瘤研究的文献，需要提取出20篇文献（按照IF由大到小的顺序）。文献必须同时包含单细胞测序和空间转录组，空转平台可以是10X HD、10X HD3'、Xenium、Stereo-seq之一或多个。", "if_fixed_source_roles-arm-2", "13"),
        ("historical-adipose", "case6-sources.json", "近3年（2023-2026年）脂肪组织/脂肪样本的空间转录组研究有哪些？请重点关注脂肪组织空间转录组的高影响力研究，整理研究对象、空间转录组平台、主要发现和影响因子；区分原始研究、综述、方法学文章和预印本，并说明证据局限。", None, "1"),
    ]
    manifest_cases = []
    intervention_notes = []
    for case_id, base_name, query, packet_arm, source_index in cases:
        base = json.loads((FIXED / base_name).read_text(encoding="utf-8"))
        base_path = INPUT / f"{case_id}-base.json"; base_path.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        supplemented = base
        note = {"case_id": case_id, "base_sha256": sha(base_path), "source_index": source_index}
        if packet_arm:
            supplemented, evidence = add_full_source(base, source_index, packet_source(packet_arm, source_index), "independently adjudicated primary full text")
            note["supplement"] = evidence
        else:
            text, fetch = fetch_biorxiv_html()
            supplemented = copy.deepcopy(base)
            target = next(x for x in supplemented if str(x.get("index")) == source_index)
            target["full_content"] = text; target["content_type"] = "full_text"; target["evidence_intervention"] = "independently fetched primary preprint HTML"
            note["supplement"] = {"index": source_index, **fetch}
        supp_path = INPUT / f"{case_id}-supplemented.json"; supp_path.write_text(json.dumps(supplemented, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        note["supplemented_sha256"] = sha(supp_path); intervention_notes.append(note)
        for arm in ("baseline", "candidate_a", "candidate_b", "supplemented"):
            manifest_cases.append({"case_id": case_id, "query": query, "source_files": {"base": str(base_path.relative_to(ROOT)), "supplemented": str(supp_path.relative_to(ROOT))}, "arm": arm})

    # Two reserved new tasks were frozen before looking at new candidate output.
    new = [
        ("reserved-patatin", "f_d4ccb057954e", "What is known about the protein patatin? Write an evidence-grounded research report of about 700 words with citations, useful synthesis, limitations and one bounded next research step."),
        ("reserved-dst1", "f_756956be128f", "How does Dst1 knock-out affect transcription in yeast? Write an evidence-grounded research report of about 700 words with citations, useful synthesis, limitations and one bounded next research step."),
    ]
    for case_id, stem, query in new:
        source = EXTERNAL / f"{stem}.json"
        if not source.exists(): raise FileNotFoundError(source)
        target = INPUT / f"{case_id}-base.json"; target.write_bytes(source.read_bytes())
        supplement = INPUT / f"{case_id}-supplemented.json"; supplement.write_bytes(source.read_bytes())
        for arm in ("baseline", "candidate_a", "candidate_b"):
            manifest_cases.append({"case_id": case_id, "query": query, "source_files": {"base": str(target.relative_to(ROOT)), "supplemented": str(supplement.relative_to(ROOT))}, "arm": arm})

    manifest = {
        "schema_version": "scholar_controlled_pilot_manifest.v1",
        "status": "frozen_before_candidate_outputs",
        "model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 5000, "native_fact_consistency": True, "max_review_calls": 6,
        "live_search": False, "body_fetch": False, "save_time_citation_qc": False,
        "historical_cases": [x[0] for x in cases], "reserved_new_cases": [x[0] for x in new],
        "arms": {"baseline": "roles off, inherited draft empty", "candidate_a": "quote-backed source-reading roles on", "candidate_b": "fresh synthesis on, roles off", "supplemented": "baseline writer with deliberate primary full-text evidence intervention"},
        "runs": manifest_cases,
        "intervention_notes": intervention_notes,
        "limits": ["Supplemented historical arms are not retrieval comparisons; they deliberately alter writer-visible evidence.", "The two reserved tasks are validation material, not a representative benchmark.", "Blinded semantic assessment is a separate post-generation pass."],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": len(manifest_cases), "historical": len(cases), "reserved": len(new), "interventions": intervention_notes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
