"""Build the 18-case Astro-DRA held-out package from the manual README.

The builder fetches the named PubMed/Europe PMC records once, freezes the
returned text, writes public prompts and packets, and writes claim-level labels
under ``gold.private``.  Gold labels are never copied into the public manifest.
This script intentionally does not run Astro-DRA or inspect candidate outputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import requests


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "ASTRO_DRA_HELDOUT_DATASET_README.md"
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"
CASES = PACKAGE / "cases"
GOLD = PACKAGE / "gold.private"
STAMP = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


PRIMARY = {
    "SRC-TIROSH-2016": ("27124452", "primary_research"),
    "SRC-JERBY-2018": ("30388455", "primary_research"),
    "SRC-ZILIONIS-2019": ("30979687", "primary_research"),
    "SRC-MAYNARD-2020": ("32822576", "primary_research"),
    "SRC-SCHURCH-2020": ("32763154", "primary_research"),
    "SRC-KEREN-2018": ("30193111", "primary_research"),
    "SRC-BAGAEV-2021": ("34019806", "primary_research"),
}

CASES_18 = {
    "E01": ("E01_melanoma_cell_state_heterogeneity", ["SRC-TIROSH-2016"]),
    "E02": ("E02_checkpoint_resistance", ["SRC-JERBY-2018"]),
    "E03": ("E03_cross_species_myeloid", ["SRC-ZILIONIS-2019"]),
    "E04": ("E04_therapy_evolution", ["SRC-MAYNARD-2020"]),
    "E05": ("E05_colorectal_spatial_neighborhoods", ["SRC-SCHURCH-2020"]),
    "E06": ("E06_tnbc_spatial_immune", ["SRC-KEREN-2018"]),
    "E07": ("E07_pancancer_tme_subtypes", ["SRC-BAGAEV-2021"]),
    "E08": ("E08_cross_study_synthesis", list(PRIMARY)),
    "P01": ("P01_wrong_citation", ["SRC-ZILIONIS-2019", "SRC-TIROSH-2016"]),
    "P02": ("P02_primary_vs_review_editorial", ["SRC-JERBY-2018", "SRC-REVIEW-TME", "SRC-EDITORIAL-IMMUNO"]),
    "P03": ("P03_population_species_scope", ["SRC-ZILIONIS-2019"]),
    "P04": ("P04_assay_scope", ["SRC-TIROSH-2016", "SRC-SCHURCH-2020", "SRC-KEREN-2018"]),
    "C01": ("C01_unclear_count", ["SRC-TIROSH-2016", "SRC-JERBY-2018", "SRC-ZILIONIS-2019"]),
    "C02": ("C02_zero_sources", []),
    "C03": ("C03_abstract_only", ["SRC-TIROSH-2016"]),
    "C04": ("C04_conflicting_metadata", ["SRC-CONFLICT-A", "SRC-CONFLICT-B"]),
    "C05": ("C05_language_date_mismatch", ["SRC-LANG-EN-2022", "SRC-LANG-ZH-2019"]),
    "C06": ("C06_duplicate_identity", ["SRC-JOURNAL-VERSION", "SRC-PREPRINT-VERSION"]),
}


def digest(value: str | bytes) -> str:
    return sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def europepmc_record(pmid: str) -> dict:
    print(f"Fetching Europe PMC record {pmid}", flush=True)
    response = requests.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": f"EXT_ID:{pmid}", "format": "json", "resultType": "core"},
        timeout=(10, 45),
    )
    response.raise_for_status()
    result = response.json()["resultList"]["result"][0]
    return result


def bioc_text(pmcid: str) -> str | None:
    if not pmcid:
        return None
    print(f"Fetching PMC full text {pmcid}", flush=True)
    for _ in range(3):
        try:
            response = requests.get(
                f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode",
                timeout=(10, 90),
            )
            if response.status_code != 200:
                continue
            documents = response.json()
            passages = [
                passage.get("text", "").strip()
                for document in documents
                for article in document.get("documents", [])
                for passage in article.get("passages", [])
                if passage.get("text", "").strip()
            ]
            text = "\n\n".join(passages)
            if text:
                return text
        except (requests.RequestException, ValueError, TypeError):
            continue
    return None


def source_snapshot(source_id: str, record: dict, source_type: str, *, full_text=False) -> dict:
    abstract = str(record.get("abstractText") or "").strip()
    pmcid = str(record.get("pmcid") or "").strip() or None
    text = bioc_text(pmcid) if full_text else None
    if full_text and not text:
        # Rebuilds remain deterministic when the upstream BioC relay is
        # temporarily unavailable after an earlier successful freeze.
        fallback = PACKAGE / "cases" / "E06_tnbc_spatial_immune" / "source_packet.jsonl"
        if fallback.is_file():
            try:
                text = json.loads(fallback.read_text(encoding="utf-8").splitlines()[0])["text"]
            except (ValueError, KeyError, IndexError):
                text = None
        if not text:
            raise ValueError(f"Full-text snapshot unavailable for {source_id}")
    content_type = "full_text" if text else "abstract"
    text = text or abstract
    if not text:
        text = "No abstract or article text was supplied by the frozen bibliographic record."
        content_type = "metadata"
    return {
        "schema_version": "source_snapshot.v1",
        "source_id": source_id,
        "source_type": source_type,
        "title": record.get("title") or "",
        "authors": record.get("authorString") or "",
        "journal": record.get("journalTitle") or "",
        "publication_year": record.get("pubYear"),
        "doi": record.get("doi") or "",
        "pmid": record.get("pmid") or record.get("id") or "",
        "pmcid": pmcid or "",
        "publication_types": ((record.get("pubTypeList") or {}).get("pubType") or []),
        "content_type": content_type,
        "full_text_available": bool(text and content_type == "full_text"),
        "text": text,
        "text_sha256": digest(text),
        "retrieved_at": STAMP,
        "retrieval": {
            "provider": "Europe PMC",
            "endpoint": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            "query": f"EXT_ID:{record.get('pmid') or record.get('id')}",
        },
    }


def metadata_source(source_id: str, *, base: dict, **updates) -> dict:
    row = dict(base)
    row.update(updates)
    row["schema_version"] = "source_snapshot.v1"
    row["source_id"] = source_id
    row["retrieval"] = {"provider": "manual_fixture",
                         "source": "ASTRO_DRA_HELDOUT_DATASET_README.md"}
    row["text_sha256"] = digest(row.get("text", ""))
    return row


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def locator(source_rows: dict[str, dict], source_id: str, quote: str, *, claim_id: str) -> dict:
    text = source_rows[source_id]["text"]
    start = text.find(quote)
    if start < 0:
        # Europe PMC abstracts preserve non-breaking spaces in some records.
        # Locate the same literal words with whitespace flexibility, then save
        # the actual frozen substring as the exact quote.
        pattern = re.escape(quote).replace(r"\ ", r"\s+")
        match = re.search(pattern, text)
        if match:
            start = match.start()
            quote = text[match.start():match.end()]
        else:
            raise ValueError(f"Quote not found for {claim_id}: {source_id}: {quote[:80]}")
    return {
        "source_id": source_id,
        "field": "text",
        "basis": source_rows[source_id]["content_type"],
        "start": start,
        "end": start + len(quote),
        "quote": quote,
        "content_sha256": source_rows[source_id]["text_sha256"],
    }


def label(case_id: str, claim_id: str, claim_text: str, expected_label: str,
          claim_class: str, source_ids: list[str], source_rows: dict[str, dict],
          quote_source: str | None, quote: str | None, rationale: str,
          *, severity="high", allowed_abstention=True) -> dict:
    exact = [locator(source_rows, quote_source, quote, claim_id=claim_id)] if quote_source and quote else []
    return {
        "case_id": case_id,
        "claim_id": claim_id,
        "claim_text": claim_text,
        "claim_class": claim_class,
        "expected_label": expected_label,
        "source_ids": source_ids,
        "exact_locators": exact,
        "required_scope": {},
        "severity": severity,
        "allowed_abstention": allowed_abstention,
        "rationale": rationale,
    }


def prompts() -> dict[str, str]:
    return {
        "E01": "Summarize malignant-cell heterogeneity in metastatic melanoma using SRC-TIROSH-2016. Report the observed cell states, the cohort and the T-cell findings. Keep association, patient variability, and drug-resistance language within the study scope. Cite source IDs.",
        "E02": "Explain what SRC-JERBY-2018 shows about checkpoint resistance. Separate the malignant-cell program, T-cell exclusion, independent-cohort prediction, and the CDK4/6 plus immunotherapy experiment. Preserve the mouse-model boundary and cite source IDs.",
        "E03": "Compare human and mouse lung-tumor myeloid populations using SRC-ZILIONIS-2019. Preserve the asymmetric conservation across dendritic cells, monocytes, neutrophils, macrophages, and blood versus tumor. Cite source IDs.",
        "E04": "Summarize therapy-associated evolution in lung cancer from SRC-MAYNARD-2020. Distinguish residual disease from on-therapy progressive disease and do not turn the observed signatures into one universal causal resistance pathway. Cite source IDs.",
        "E05": "Explain the spatial immune findings in colorectal cancer from SRC-SCHURCH-2020. Report the cohort, nine cellular neighborhoods, and the survival associations while preserving the observational and subgroup scope. Cite source IDs.",
        "E06": "Describe the TNBC spatial immune categories from SRC-KEREN-2018. Report the MIBI-TOF measurements, cold/mixed/compartmentalized organization, cell-type and location-specific checkpoint expression, and survival association. Do not claim treatment benefit. Cite source IDs.",
        "E07": "Assess whether SRC-BAGAEV-2021 validates a pan-cancer immunotherapy rule. Report the four TME subtypes and studied-cohort response associations, then state what the paper does not establish. Cite source IDs.",
        "E08": "Synthesize the evidence in SRC-TIROSH-2016, SRC-JERBY-2018, SRC-ZILIONIS-2019, SRC-MAYNARD-2020, SRC-SCHURCH-2020, SRC-KEREN-2018, and SRC-BAGAEV-2021. State the strongest shared conclusion while preserving cancer type, species, tissue, assay, cohort, association, and causality boundaries. Cite source IDs.",
        "P01": "The claim is: human and mouse lung-tumor myeloid populations show selective conservation with macrophage differences and limited blood/tumor overlap. It is deliberately cited as SRC-TIROSH-2016. Assess the claim and citation alignment using SRC-ZILIONIS-2019 and SRC-TIROSH-2016.",
        "P02": "Using SRC-JERBY-2018 plus the supplied review and editorial records SRC-REVIEW-TME and SRC-EDITORIAL-IMMUNO, identify which source can support the specific mouse combination experiment and whether the review or editorial can replace the primary study as efficacy evidence. Preserve source type.",
        "P03": "Can the SRC-ZILIONIS-2019 findings be stated as blood findings or as complete human-mouse equivalence? Answer with the tissue, species, and population boundaries in the supplied source.",
        "P04": "Compare what SRC-TIROSH-2016, SRC-SCHURCH-2020, and SRC-KEREN-2018 measure. Explain why scRNA-seq, CODEX, and MIBI-TOF observations are complementary but not interchangeable evidence.",
        "C01": "Find 10 papers on tumor microenvironment heterogeneity from the supplied candidates. The request does not say exact, at least, at most, or top. State the count relation and whether the requested count can be claimed as satisfied.",
        "C02": "Find primary tumor-microenvironment evidence under the stated scope. The retrieval result contains zero sources. Respond with the appropriate abstention and explain the evidence boundary without inventing papers.",
        "C03": "Give the exact mechanism and quantitative result requested from SRC-TIROSH-2016. Only the abstract/metadata record is supplied. State what is and is not verifiable from this packet.",
        "C04": "Two records share the apparent identity of one paper but disagree on title, year, and authors. Reconcile the records for citation use. Do not silently choose one value.",
        "C05": "Return English papers from 2020–2022. The packet contains a 2019 Chinese-language record and a 2022 English-language record. Preserve the language and date scope and explain any unresolved fields.",
        "C06": "The packet contains a preprint and a journal record that may represent the same work, plus duplicate title metadata. Decide whether they are independent papers or an unresolved identity/version pair. Do not inflate the count.",
    }


def gold(source_rows: dict[str, dict]) -> dict[str, list[dict]]:
    q = lambda sid, text: (sid, text)
    return {
        "E01": [
            label("E01", "E01-C01", "The study profiled 4,645 single cells from 19 patients.", "supported", "quantity", ["SRC-TIROSH-2016"], source_rows, *q("SRC-TIROSH-2016", "4645 single cells isolated from 19 patients"), "The abstract states the cohort and cell count."),
            label("E01", "E01-C02", "All tumors contained high-MITF and low-MITF/elevated-AXL malignant-cell states.", "supported", "state", ["SRC-TIROSH-2016"], source_rows, *q("SRC-TIROSH-2016", "all tumors harbored malignant cells from two distinct transcriptional cell states"), "The abstract reports the two states and their distribution."),
            label("E01", "E01-C03", "T-cell exhaustion programs and patient variability were observed.", "supported", "outcome", ["SRC-TIROSH-2016"], source_rows, *q("SRC-TIROSH-2016", "their variability across patients"), "The abstract reports exhaustion programs and variability."),
            label("E01", "E01-C04", "The study proves that AXL causes drug resistance in every melanoma.", "unsupported", "causality", ["SRC-TIROSH-2016"], source_rows, *q("SRC-TIROSH-2016", "a drug-resistance program"), "The abstract reports an associated program and does not establish universal AXL causality."),
        ],
        "E02": [
            label("E02", "E02-C01", "The malignant-cell resistance program was associated with T-cell exclusion and immune evasion.", "supported", "association", ["SRC-JERBY-2018"], source_rows, *q("SRC-JERBY-2018", "associated with T cell exclusion and immune evasion"), "Directly stated in the abstract."),
            label("E02", "E02-C02", "The program predicted anti-PD-1 responses in an independent cohort of 112 melanoma patients.", "supported", "prediction", ["SRC-JERBY-2018"], source_rows, *q("SRC-JERBY-2018", "predicts clinical responses to anti-PD-1 therapy in an independent cohort of 112 melanoma patients"), "Directly stated in the abstract."),
            label("E02", "E02-C03", "The CDK4/6 plus immunotherapy experiment reduced tumor outgrowth in mouse models.", "supported", "species_scope", ["SRC-JERBY-2018"], source_rows, *q("SRC-JERBY-2018", "reduces melanoma tumor outgrowth in mouse models in vivo"), "The abstract preserves the mouse-model boundary."),
            label("E02", "E02-C04", "The combination is proven to benefit human patients.", "unsupported", "clinical_efficacy", ["SRC-JERBY-2018"], source_rows, *q("SRC-JERBY-2018", "in mouse models in vivo"), "The supplied evidence describes a mouse experiment, not human clinical efficacy."),
        ],
        "E03": [
            label("E03", "E03-C01", "The study identified 25 tumor-infiltrating myeloid states.", "supported", "quantity", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "uncovered 25 TIM states"), "Directly stated in the abstract."),
            label("E03", "E03-C02", "Dendritic-cell and monocyte population structures were nearly congruent across species.", "supported", "species_scope", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "near-complete congruence of population structures among dendritic cells and monocytes"), "Directly stated in the abstract."),
            label("E03", "E03-C03", "Macrophage structures differed between species and blood populations had limited overlap with tumor TIMs.", "supported", "scope", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "species differences among macrophages"), "The abstract reports both asymmetries."),
            label("E03", "E03-C04", "Human and mouse myeloid populations are equivalent in every tissue compartment.", "unsupported", "scope", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "showed limited overlap with those of TIMs"), "The source explicitly limits equivalence."),
        ],
        "E04": [
            label("E04", "E04-C01", "The study analyzed 49 biopsies from 30 patients before and during targeted therapy.", "supported", "cohort", ["SRC-MAYNARD-2020"], source_rows, *q("SRC-MAYNARD-2020", "49 clinical biopsies obtained from 30 patients before and during targeted therapy"), "Directly stated in the abstract."),
            label("E04", "E04-C02", "Residual disease showed an alveolar-regenerative signature.", "supported", "state", ["SRC-MAYNARD-2020"], source_rows, *q("SRC-MAYNARD-2020", "residual disease (RD) expressed an alveolar-regenerative cell signature"), "Directly stated in the abstract."),
            label("E04", "E04-C03", "Progressive disease upregulated kynurenine, plasminogen, and gap-junction pathways.", "supported", "pathway", ["SRC-MAYNARD-2020"], source_rows, *q("SRC-MAYNARD-2020", "on-therapy progressive disease (PD) upregulated kynurenine, plasminogen, and gap-junction pathways"), "Directly stated in the abstract."),
            label("E04", "E04-C04", "The study proves one universal causal resistance pathway for all lung cancer.", "unsupported", "causality", ["SRC-MAYNARD-2020"], source_rows, *q("SRC-MAYNARD-2020", "highlights how therapy-induced adaptation"), "The study reports therapy-associated adaptation and outcome-linked features, not a universal causal pathway."),
        ],
        "E05": [
            label("E05", "E05-C01", "CODEX profiled 140 tissue regions from 35 advanced-stage colorectal-cancer patients.", "supported", "cohort", ["SRC-SCHURCH-2020"], source_rows, *q("SRC-SCHURCH-2020", "140 tissue regions from 35 advanced-stage colorectal cancer (CRC) patients"), "Directly stated in the abstract."),
            label("E05", "E05-C02", "The study identified nine conserved cellular neighborhoods.", "supported", "quantity", ["SRC-SCHURCH-2020"], source_rows, *q("SRC-SCHURCH-2020", "identified nine conserved, distinct cellular neighborhoods"), "Directly stated in the abstract."),
            label("E05", "E05-C03", "PD-1-positive CD4-positive T cells within a granulocyte neighborhood positively correlated with survival in a high-risk subset.", "supported", "association", ["SRC-SCHURCH-2020"], source_rows, *q("SRC-SCHURCH-2020", "positively correlated with survival in a high-risk patient subset"), "The subgroup and association are explicit."),
            label("E05", "E05-C04", "The neighborhood causes survival and is validated for every colorectal-cancer patient.", "unsupported", "causality", ["SRC-SCHURCH-2020"], source_rows, *q("SRC-SCHURCH-2020", "associated with inferior outcomes"), "The source uses associations and selected subgroups."),
        ],
        "E06": [
            label("E06", "E06-C01", "MIBI-TOF quantified 36 proteins in 41 triple-negative breast-cancer patients.", "supported", "assay", ["SRC-KEREN-2018"], source_rows, *q("SRC-KEREN-2018", "36 proteins"), "Directly stated in the frozen source text."),
            label("E06", "E06-C02", "Tumors included cold, mixed, and compartmentalized spatial organizations.", "supported", "state", ["SRC-KEREN-2018"], source_rows, *q("SRC-KEREN-2018", "Cold"), "The frozen Keren full-text snapshot defines the three archetypes."),
            label("E06", "E06-C03", "Checkpoint expression varied by cell type and location and spatial organization was linked to survival.", "supported", "association", ["SRC-KEREN-2018"], source_rows, *q("SRC-KEREN-2018", "cell-type- and location-specific manner"), "The abstract reports cell/location-specific expression and survival linkage."),
            label("E06", "E06-C04", "The imaging study proves that changing the architecture improves immunotherapy benefit.", "unsupported", "clinical_efficacy", ["SRC-KEREN-2018"], source_rows, *q("SRC-KEREN-2018", "linked to survival"), "The source reports observational survival linkage, not an intervention."),
        ],
        "E07": [
            label("E07", "E07-C01", "Transcriptomic analysis of more than 10,000 patients identified four TME subtypes across 20 cancers.", "supported", "cohort", ["SRC-BAGAEV-2021"], source_rows, *q("SRC-BAGAEV-2021", ">10,000 cancer patients identifies four distinct TME subtypes conserved across 20 different cancers"), "Directly stated in the abstract."),
            label("E07", "E07-C02", "The subtypes correlated with immunotherapy response in multiple cancers.", "supported", "association", ["SRC-BAGAEV-2021"], source_rows, *q("SRC-BAGAEV-2021", "correlate with patient response to immunotherapy in multiple cancers"), "Directly stated in the abstract."),
            label("E07", "E07-C03", "The subtype guarantees response for every cancer patient.", "unsupported", "prediction", ["SRC-BAGAEV-2021"], source_rows, *q("SRC-BAGAEV-2021", "correlate with patient response"), "Correlation in studied cohorts does not guarantee response."),
            label("E07", "E07-C04", "The subtype proves one causal immune mechanism across cancers.", "unsupported", "causality", ["SRC-BAGAEV-2021"], source_rows, *q("SRC-BAGAEV-2021", "may aid in biomarker discovery"), "The source frames the result as biomarker discovery and personalization."),
        ],
        "E08": [
            label("E08", "E08-C01", "Across the packet, tumor ecosystems show heterogeneous cell states and spatial organization.", "supported", "synthesis", list(PRIMARY), source_rows, *q("SRC-TIROSH-2016", "Malignant cells within the same tumor displayed transcriptional heterogeneity"), "Multiple studies support this shared descriptive conclusion."),
            label("E08", "E08-C02", "The studies report associations with immune behavior or clinical outcomes.", "supported", "synthesis", list(PRIMARY), source_rows, *q("SRC-BAGAEV-2021", "correlate with patient response to immunotherapy in multiple cancers"), "The packet contains outcome and immune-association findings."),
            label("E08", "E08-C03", "The packet proves one universal causal mechanism or guaranteed therapy response.", "unsupported", "synthesis", list(PRIMARY), source_rows, *q("SRC-JERBY-2018", "in mouse models in vivo"), "The studies span designs and preserve association, species, and cohort limits."),
        ],
        "P01": [
            label("P01", "P01-C01", "The lung-myeloid cross-species claim is supported but the attached SRC-TIROSH-2016 citation is misaligned.", "misaligned", "citation_alignment", ["SRC-ZILIONIS-2019", "SRC-TIROSH-2016"], source_rows, *q("SRC-ZILIONIS-2019", "near-complete congruence of population structures among dendritic cells and monocytes"), "Tirosh concerns metastatic melanoma, while Zilionis supports the lung-myeloid claim."),
        ],
        "P02": [
            label("P02", "P02-C01", "SRC-JERBY-2018 is the primary source for the mouse combination experiment.", "supported", "provenance", ["SRC-JERBY-2018"], source_rows, *q("SRC-JERBY-2018", "in mouse models in vivo"), "The primary record is the experimental source."),
            label("P02", "P02-C02", "The review or editorial can replace the primary source as efficacy evidence.", "unsupported", "provenance", ["SRC-REVIEW-TME", "SRC-EDITORIAL-IMMUNO"], source_rows, None, None, "Context sources cannot replace the primary experimental record for a specific efficacy claim."),
        ],
        "P03": [
            label("P03", "P03-C01", "Blood myeloid population structures had limited overlap with tumor TIMs.", "supported", "population", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "blood showed limited overlap with those of TIMs"), "Directly stated in the abstract."),
            label("P03", "P03-C02", "The study establishes complete human-mouse equivalence.", "unsupported", "species_scope", ["SRC-ZILIONIS-2019"], source_rows, *q("SRC-ZILIONIS-2019", "species differences among macrophages"), "The source explicitly reports species differences."),
        ],
        "P04": [
            label("P04", "P04-C01", "The studies use different assays and measured entities.", "supported", "assay", ["SRC-TIROSH-2016", "SRC-SCHURCH-2020", "SRC-KEREN-2018"], source_rows, *q("SRC-KEREN-2018", "MIBI-TOF"), "The source identities and methods distinguish scRNA-seq, CODEX, and MIBI-TOF."),
            label("P04", "P04-C02", "Their observations are interchangeable without an explicit integration method.", "unsupported", "assay_scope", ["SRC-TIROSH-2016", "SRC-SCHURCH-2020", "SRC-KEREN-2018"], source_rows, None, None, "Different assays and measured entities cannot be treated as interchangeable by default."),
        ],
        "C01": [label("C01", "C01-C01", "The request means exactly 10 papers.", "unverifiable", "count_relation", [], source_rows, None, None, "No count relation is stated; preserve requested_count=10 and count_relation=unknown.")],
        "C02": [label("C02", "C02-C01", "The system can provide a source-backed answer despite zero retrievable sources.", "unsupported", "abstention", [], source_rows, None, None, "Zero-source input requires abstention and must not be filled from model memory.")],
        "C03": [label("C03", "C03-C01", "The unavailable full text establishes the exact requested mechanism and quantitative result.", "unverifiable", "availability", ["SRC-TIROSH-2016"], source_rows, None, None, "The frozen packet contains an abstract only; detailed full-text claims are unavailable.")],
        "C04": [label("C04", "C04-C01", "The two conflicting records can be silently merged into one authoritative identity.", "unsupported", "identity_conflict", ["SRC-CONFLICT-A", "SRC-CONFLICT-B"], source_rows, None, None, "Conflicting title/year/author values must remain visible and unresolved.")],
        "C05": [label("C05", "C05-C01", "Both candidates satisfy the English 2020–2022 scope.", "unsupported", "scope", ["SRC-LANG-EN-2022", "SRC-LANG-ZH-2019"], source_rows, None, None, "The Chinese 2019 record mismatches both declared scope fields.")],
        "C06": [label("C06", "C06-C01", "The preprint and journal records are definitely two independent studies.", "unverifiable", "identity_conflict", ["SRC-JOURNAL-VERSION", "SRC-PREPRINT-VERSION"], source_rows, None, None, "Identity/version linkage is ambiguous in the frozen packet and must not inflate counts.")],
    }


def main() -> None:
    if not README.is_file():
        raise SystemExit(f"Missing manual dataset README: {README}")
    PACKAGE.mkdir(parents=True, exist_ok=True)
    CASES.mkdir(parents=True, exist_ok=True)
    GOLD.mkdir(parents=True, exist_ok=True)

    records = {}
    print(f"Building held-out package at {PACKAGE}", flush=True)
    for source_id, (pmid, source_type) in PRIMARY.items():
        record = europepmc_record(pmid)
        records[source_id] = source_snapshot(source_id, record, source_type,
                                             full_text=source_id == "SRC-KEREN-2018")
    review = europepmc_record("42953944")
    editorial = europepmc_record("42774293")
    records["SRC-REVIEW-TME"] = source_snapshot("SRC-REVIEW-TME", review, "review")
    records["SRC-EDITORIAL-IMMUNO"] = source_snapshot("SRC-EDITORIAL-IMMUNO", editorial, "editorial")

    base = records["SRC-TIROSH-2016"]
    records["SRC-CONFLICT-A"] = metadata_source(
        "SRC-CONFLICT-A", base=base, title=base["title"], publication_year=2016,
        authors=base["authors"], text="Metadata-only conflict fixture; no text evidence.",
        content_type="metadata", full_text_available=False, source_type="metadata_fixture", pmid="27124452")
    records["SRC-CONFLICT-B"] = metadata_source(
        "SRC-CONFLICT-B", base=base, title="Conflicting title for the same PMID", publication_year=2017,
        authors="Conflicting author list", text="Metadata-only conflict fixture; no text evidence.",
        content_type="metadata", full_text_available=False, source_type="metadata_fixture", pmid="27124452")
    records["SRC-LANG-EN-2022"] = metadata_source(
        "SRC-LANG-EN-2022", base=base, title="English scope fixture", publication_year=2022,
        language="en", text="Metadata-only language/date fixture.", content_type="metadata",
        full_text_available=False, source_type="metadata_fixture", pmid="fixture-en-2022")
    records["SRC-LANG-ZH-2019"] = metadata_source(
        "SRC-LANG-ZH-2019", base=base, title="中文范围冲突样本", publication_year=2019,
        language="zh", text="元数据语言/日期冲突样本。", content_type="metadata",
        full_text_available=False, source_type="metadata_fixture", pmid="fixture-zh-2019")
    records["SRC-JOURNAL-VERSION"] = metadata_source(
        "SRC-JOURNAL-VERSION", base=base, title=base["title"], publication_year=2016,
        publication_state="journal", text="Version-linkage fixture.", content_type="metadata",
        full_text_available=False, source_type="journal_version_fixture", doi=base["doi"], pmid="27124452")
    records["SRC-PREPRINT-VERSION"] = metadata_source(
        "SRC-PREPRINT-VERSION", base=base, title=base["title"], publication_year=2015,
        publication_state="preprint", source_type="preprint", text="Version-linkage fixture.",
        content_type="metadata", full_text_available=False, doi=base["doi"], pmid="27124452")

    prompt_map = prompts()
    gold_map = gold(records)
    public_rows = []
    package_files = []
    for case_id, (slug, source_ids) in CASES_18.items():
        case_dir = CASES / slug
        case_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = case_dir / "prompt.md"
        prompt_path.write_text(prompt_map[case_id] + "\n", encoding="utf-8")
        packet_rows = [records[source_id] for source_id in source_ids]
        packet_path = case_dir / "source_packet.jsonl"
        write_jsonl(packet_path, packet_rows)
        public_rows.append({
            "schema_version": "astro_dra_heldout_case.v1",
            "case_id": case_id,
            "prompt_path": str(prompt_path.relative_to(PACKAGE)),
            "prompt_sha256": digest(prompt_path.read_bytes()),
            "source_packet_path": str(packet_path.relative_to(PACKAGE)),
            "source_packet_sha256": digest(packet_path.read_bytes()),
            "source_ids": source_ids,
            "expected_scope": {"domain": "tumor biology" if case_id.startswith(("E", "P")) else "biomedical evaluation"},
            "baseline_output_path": f"runs/baseline/{case_id}.json",
            "candidate_output_path": f"runs/candidate/{case_id}.json",
            "model_identity": "declared_at_run",
            "endpoint_identity": "declared_at_run",
            "settings_sha256": "declared_at_run",
            "review_status": "sealed_pending_run",
        })
        gold_path = GOLD / f"{case_id}_claim_labels.jsonl"
        write_jsonl(gold_path, gold_map[case_id])
        package_files.extend([prompt_path, packet_path])

    (PACKAGE / "manifest.public.jsonl").write_text(
        "".join(canonical(row) + "\n" for row in public_rows), encoding="utf-8")
    (PACKAGE / "rubric.md").write_text(
        "# Astro-DRA held-out review rubric\n\n"
        "Score each substantive claim for source support, citation alignment, "
        "scope, evidence strength, identity/metadata, abstention, useful-content "
        "retention, and newly introduced severe biological errors. Keep baseline "
        "and candidate labels blinded during first-pass review. A missing or "
        "unavailable field remains unknown. Acceptance requires a sealed private "
        "gold packet and paired non-inferiority review.\n",
        encoding="utf-8")
    (PACKAGE / "README.md").write_text(
        "# Astro-DRA held-out evidence-grounding package\n\n"
        "This public package freezes 18 cases: E01-E08, P01-P04, and C01-C06. "
        "E09-E12 remain reserved in the manual design and are excluded from this denominator.\n\n"
        "The package contains prompts, frozen source packets, a public JSONL manifest, "
        "and a review rubric. It does not contain expected claim labels or edge-category "
        "labels. Those are sealed separately under `gold.private/` and must not be supplied "
        "to tuning or generation before both paired outputs exist.\n\n"
        "Prompt and source-packet hashes are checked by `scripts/validate_astro_dra_heldout_v1.py`. "
        "The source packets preserve the retrieved text, source identity, provenance, "
        "content hash, and retrieval endpoint. Abstract-only packets remain explicitly "
        "limited to the abstract.\n\n"
        "This package is an acceptance input set, not a quality result. Candidate outputs "
        "must be run with identical prompts, packets, source IDs, model, endpoint, and settings. "
        "Manual review remains blinded and acceptance is evaluated with paired effects and uncertainty.\n",
        encoding="utf-8")
    gold_manifest = {"schema_version": "gold.private.v1", "status": "sealed", "sealed_at": STAMP,
                     "case_ids": list(CASES_18), "label_files": [f"{c}_claim_labels.jsonl" for c in CASES_18]}
    (GOLD / "SEAL.json").write_text(canonical(gold_manifest) + "\n", encoding="utf-8")

    # Compare exact prompt hashes with the six diagnostic input questions when
    # those archived inputs are available. This is an overlap check only.
    diagnostic = []
    for path in sorted((ROOT / "evaluation").glob("**/input.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("question_sha256"):
            diagnostic.append({"path": str(path), "question_sha256": data["question_sha256"]})
    prompt_hashes = {row["prompt_sha256"] for row in public_rows}
    overlaps = [row for row in diagnostic if row["question_sha256"] in prompt_hashes]
    receipt = {"schema_version": "astro_dra_heldout_build.v1", "status": "sealed_pending_run",
               "case_count": len(public_rows), "case_ids": list(CASES_18),
               "reserved_manual_cases": ["E09", "E10", "E11", "E12"],
               "built_at": STAMP, "diagnostic_prompt_inputs": diagnostic,
               "exact_prompt_hash_overlaps": overlaps,
               "gold_private": "gold.private", "candidate_outputs_inspected": False}
    (PACKAGE / "build_receipt.json").write_text(canonical(receipt) + "\n", encoding="utf-8")

    hash_lines = []
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and "gold.private" not in path.parts and path.name != "hashes.sha256":
            hash_lines.append(f"{digest(path.read_bytes())}  {path.relative_to(PACKAGE)}")
    (PACKAGE / "hashes.sha256").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    private_hashes = []
    for path in sorted(GOLD.glob("*.jsonl")):
        private_hashes.append(f"{digest(path.read_bytes())}  {path.name}")
    (GOLD / "SEAL.json").write_text(canonical({**gold_manifest, "label_hashes": private_hashes}) + "\n", encoding="utf-8")
    print(json.dumps({"package": str(PACKAGE), "case_count": len(public_rows),
                      "gold_case_count": len(gold_map), "prompt_overlaps": overlaps}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
