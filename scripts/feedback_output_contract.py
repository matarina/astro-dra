#!/usr/bin/env python3
"""Deterministic report-level checks for the second-feedback failure modes.

This is a local contract test, not a replacement for a live LDR run.  It uses
small source records with explicit metadata so that the checks exercise the
same card and publication code used by production without inventing article
facts or making network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_deep_research"))


def _optional_loguru():
    try:
        import loguru  # noqa: F401
    except ModuleNotFoundError:
        class _QuietLogger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None
        sys.modules["loguru"] = types.SimpleNamespace(logger=_QuietLogger())


def run() -> dict:
    _optional_loguru()
    from research_verify.config import VerifyConfig
    from research_verify.evidence_cards import build_source_cards
    from research_verify.publication import publish_report
    from research_verify.research_spec import parse_research_spec
    from research_verify.record_identity import make_record_provenance

    # These records deliberately state only the fields needed by this test.
    # Missing sample size/groups must remain missing; technology must not be
    # promoted to a platform merely because both are mentioned in prose.
    sources = [
        {
            "index": 1,
            "title": "FACS sorting and single-cell RNA sequencing of granulocytes",
            "journal": "PubMed test record",
            "year": 2025,
            "pmid": "41000001",
            "link": "https://pubmed.ncbi.nlm.nih.gov/41000001/",
            "platform": "FACSAria III",
            "technology": "scRNA-seq",
            "groups": "asthma and control",
            "abstract": "The supplied abstract names FACSAria III and scRNA-seq.",
        },
        {
            "index": 2,
            "title": "Circulating basophils profiled by CITE-seq",
            "journal": "Europe PMC test record",
            "year": 2024,
            "pmid": "41000002",
            "link": "https://europepmc.org/article/MED/41000002",
            "technology": "CITE-seq",
            "abstract": "The supplied abstract names CITE-seq but no instrument.",
        },
        {
            "index": 3,
            "title": "Search result lead with an unconfirmed platform claim",
            "link": "https://example.org/search?q=xenium",
            "content_type": "search_results_page",
            "platform": "Xenium",
        },
    ]
    for source in sources[:2]:
        source["record_provenance"] = make_record_provenance("pubmed", {
            "uid": source["pmid"], "title": source["title"], "doi": source.get("doi")})
    cards = build_source_cards(
        sources, requested_fields=("platform", "technology", "sample_size", "groups")
    )
    assert cards[0]["fields"]["platform"]["value"] == "FACSAria III"
    assert cards[0]["fields"]["technology"]["value"] == "scRNA-seq"
    assert cards[0]["fields"]["sample_size"]["status"] == "unknown"
    assert cards[1]["fields"]["technology"]["value"] == "CITE-seq"
    assert cards[1]["fields"]["platform"]["status"] == "unknown"
    assert cards[2]["provenance"]["publication_status"] == "nonformal"

    draft = (
        "The first supplied record names FACSAria III for scRNA-seq [1]. "
        "The second record reports CITE-seq but does not report an instrument [2]. "
        "The search lead is retained for follow-up only [3].\n\n"
        "## References\n"
    )
    publication = publish_report(
        draft, sources, cfg=VerifyConfig(enable_citation_qc=False)
    )
    assert publication.status == "unverified"
    assert publication.audit_status == "disabled"
    assert "The first supplied record" in publication.content
    assert "No formal source identity" not in publication.content
    assert "Sources with unconfirmed identity" in publication.content
    formal = [item for item in publication.sources if item.status == "formal"]
    leads = [item for item in publication.sources if item.status != "formal"]
    assert len(formal) == 2 and len(leads) == 1

    # A disclaimer is prose, not evidence.  With save-time citation QC off,
    # the report must remain explicitly unverified rather than being treated
    # as passed merely because it contains a limitation sentence.
    disclaimer = publish_report(
        "Evidence is limited and the following claim may be wrong [1].",
        sources[:1], cfg=VerifyConfig(enable_citation_qc=False)
    )
    assert disclaimer.status == "unverified"
    assert disclaimer.audit_status == "disabled"
    assert not disclaimer.citation_audit

    scope = parse_research_spec(
        "2026年肿瘤研究，影响因子≥10，提取每篇分组和样本量，共20篇",
        {"year_from":2026, "year_to":2026, "requested_count":20,
         "requested_fields":["groups", "sample_size"]}
    )
    assert (scope.year_from, scope.year_to) == (2026, 2026)
    assert scope.requested_count == 20
    assert {"groups", "sample_size"} <= set(scope.requested_fields)
    assert scope.if_deferred is True

    # Cross-domain guard: the same evidence-card and provenance boundary must
    # work for a non-biomedical question without topic-specific vocabulary.
    astronomy = [{
        "index": 4,
        "title": "A near-infrared stellar survey",
        "journal": "Astronomy test record",
        "doi": "10.5555/example.2026.001",
        "link": "https://doi.org/10.5555/example.2026.001",
        "platform": "JWST",
        "technology": "NIRSpec",
        "abstract": "The supplied abstract names the observatory and instrument.",
    }]
    astronomy_card = build_source_cards(
        astronomy, requested_fields=("platform", "technology", "sample_size")
    )[0]
    assert astronomy_card["fields"]["platform"]["value"] == "JWST"
    assert astronomy_card["fields"]["technology"]["value"] == "NIRSpec"
    assert astronomy_card["fields"]["sample_size"]["status"] == "unknown"

    return {
        "status": "structural_checks_pass",
        "semantic_assessment": "not_performed",
        "checks": [
            "platform_technology_separated",
            "missing_metadata_unknown",
            "formal_and_unverified_sources_separated",
            "body_preserved_when_citation_qc_disabled",
            "if_and_scope_metadata_deferred",
            "cross_domain_card_contract",
            "disclaimer_does_not_create_audit_pass",
        ],
        "publication": {
            "status": publication.status,
            "audit_status": publication.audit_status,
            "formal_sources": len(formal),
            "unverified_leads": len(leads),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = json.dumps(run(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
