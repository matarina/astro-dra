#!/usr/bin/env python3
"""Freeze two genuinely new source-backed validation tasks after overlap checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/scholar-controlled-pilot-corrected-v2-20261112"
INPUT = OUT / "inputs"
EXCLUSION = Path("/data1/maxw/.local/state/dra-hourly-monitor/known-used-task-exclusions-20261112.json")
SOURCE_ROOTS = [Path("/data1/maxw/ldr-evaluation/bioinformatics-retrieval-20261111/source-packs"), ROOT / "evaluation"]

TASKS = [
    ("new-art001-gene-editing", "42063796", "What safety and tolerability findings were reported for the in-vivo gene-editing drug ART001 in transthyretin amyloidosis? Keep the study population and follow-up scope explicit.", "biomedicine"),
    ("new-crustacean-single-cell", "42555179", "What did the single-cell transcriptomics and metabolomics study report about nitrogen-metabolic remodeling during alkalinity adaptation in crustaceans? Separate observations from mechanistic interpretation.", "bioinformatics"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_source(pmid: str) -> tuple[dict, str]:
    response = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params={"db": "pubmed", "id": pmid, "retmode": "xml"}, timeout=60)
    response.raise_for_status()
    xml_path = INPUT / f"{pmid}.pubmed.xml"
    xml_path.write_bytes(response.content)
    root = ET.fromstring(response.content)
    article = root.find(".//PubmedArticle")
    title = "".join(article.find(".//ArticleTitle").itertext()) if article is not None and article.find(".//ArticleTitle") is not None else ""
    abstract_parts = []
    for node in article.findall(".//Abstract/AbstractText") if article is not None else []:
        label = node.attrib.get("Label")
        value = "".join(node.itertext()).strip()
        abstract_parts.append((f"{label}: " if label else "") + value)
    abstract = "\n\n".join(abstract_parts)
    doi = ""
    # Restrict identity extraction to the selected article's own ArticleIdList;
    # descendant ArticleId nodes include cited-paper references.
    for aid in article.findall("./PubmedData/ArticleIdList/ArticleId") if article is not None else []:
        if aid.attrib.get("IdType") == "doi": doi = aid.text or ""
    publication_types = ["".join(node.itertext()).strip() for node in article.findall("./MedlineCitation/Article/PublicationTypeList/PublicationType")] if article is not None else []
    journal = "".join(article.find(".//Journal/Title").itertext()) if article is not None and article.find(".//Journal/Title") is not None else ""
    year = "".join(article.find(".//PubDate/Year").itertext()) if article is not None and article.find(".//PubDate/Year") is not None else ""
    source = {"index": 1, "title": title, "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "pmid": pmid, "doi": doi, "journal": journal, "pubdate": year, "abstract": abstract, "content_type": "abstract", "source_engine": "pubmed", "publication_types": publication_types, "primary_article_id_list": [(x.attrib.get("IdType"), x.text or "") for x in article.findall("./PubmedData/ArticleIdList/ArticleId")] if article is not None else []}
    return source, str(xml_path.relative_to(ROOT))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); INPUT.mkdir(parents=True, exist_ok=True)
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    excluded_pmids = {str(item.get("pmid")) for family in exclusion["families"] for item in family.get("source_identities", []) if item.get("pmid")}
    excluded_dois = {str(item.get("doi", "")).lower() for family in exclusion["families"] for item in family.get("source_identities", []) if item.get("doi")}
    existing_pmids = set(); existing_dois = set()
    for root in SOURCE_ROOTS:
        if not root.exists(): continue
        for path in root.rglob("*.json"):
            if OUT in path.parents: continue
            try: obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception: continue
            values = obj if isinstance(obj, list) else [obj]
            stack = list(values)
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    if item.get("pmid"): existing_pmids.add(str(item["pmid"]))
                    if item.get("doi"): existing_dois.add(str(item["doi"]).lower())
                    stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
                elif isinstance(item, list): stack.extend(item)

    tasks = []; overlap_rows = []
    for case_id, pmid, query, domain in TASKS:
        source, xml_rel = fetch_source(pmid)
        path = INPUT / f"{case_id}-base.json"; path.write_text(json.dumps([source], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pmid_overlap = pmid in excluded_pmids or pmid in existing_pmids
        doi_overlap = bool(source["doi"]) and (source["doi"].lower() in excluded_dois or source["doi"].lower() in existing_dois)
        overlap_rows.append({"case_id": case_id, "pmid": pmid, "doi": source["doi"], "excluded_inventory_overlap": pmid in excluded_pmids or (source["doi"].lower() in excluded_dois if source["doi"] else False), "existing_artifact_overlap": pmid in existing_pmids or (source["doi"].lower() in existing_dois if source["doi"] else False), "source_sha256": sha(path), "xml_sha256": sha(ROOT / xml_rel)})
        if pmid_overlap or doi_overlap:
            raise RuntimeError(f"overlap detected for {case_id}: {overlap_rows[-1]}")
        for arm in ("baseline_empty", "candidate_a_empty", "candidate_b_empty"):
            tasks.append({"case_id": case_id, "query": query, "domain": domain, "source_files": {"base": str(path.relative_to(ROOT)), "supplemented": str(path.relative_to(ROOT))}, "draft_files": {}, "arm": arm})

    manifest = {
        "schema_version": "scholar_new_validation_v2.v1",
        "status": "frozen_before_outputs",
        "model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 5000, "native_fact_consistency": True, "max_review_calls": 6, "live_search": False, "body_fetch": False,
        "supersedes_incorrect_new_labels": "evaluation/scholar-controlled-pilot-corrected-20261112/manifest.json",
        "historical_results_preserved": "evaluation/scholar-controlled-pilot-corrected-20261112/results",
        "new_tasks": TASKS,
        "novelty_receipt": {"exclusion_inventory": str(EXCLUSION), "exclusion_inventory_sha256": sha(EXCLUSION), "rows": overlap_rows, "textual_similarity": "not measured; DOI/PMID/source-pack identity overlap is zero", "generation_source_hashes": {row["case_id"]: row["source_sha256"] for row in overlap_rows}, "assessment_source_hashes": {row["case_id"]: row["source_sha256"] for row in overlap_rows}},
        "assessment_frozen_before_outputs": {"labels": ["supported", "partially_supported", "unsupported", "contradicted", "unverifiable"], "axes": ["citation_entailment", "qualifier_retention", "important_content_coverage", "scope_compliance", "usefulness"], "blinded": True},
        "runs": tasks,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": len(tasks), "novelty": overlap_rows}, ensure_ascii=False))


if __name__ == "__main__": main()
