"""Regression checks for the feedback-driven provenance boundary."""
from __future__ import annotations

from datetime import datetime, timezone

from research_verify.evidence import paper_identity
from research_verify.evidence_cards import build_source_card
from research_verify.publication import publish_report
from research_verify.research_spec import parse_research_spec
from research_verify.source_evidence import is_search_page, source_rejection
from research_verify.source_identity import classify_source, reconcile_identities
from research_verify.retrieval import fallback_query_candidates
from research_verify.keyword_cov import KeywordCoverage
from research_verify.config import VerifyConfig


def api_record(source):
    """Synthetic returned PubMed metadata, not a real-paper accuracy fixture."""
    from research_verify.record_identity import make_record_provenance
    from research_verify.source_identity import identity_fields
    ids = identity_fields(source)
    remote = {"uid": ids["pmid"], "title": source.get("title", ""),
              "doi": ids.get("doi"), "pubtype": source.get("publication_types", [])}
    return {**source, "record_provenance": make_record_provenance("pubmed", remote)}


def test_authoritative_record_is_formal_and_web_lead_stays_visible():
    formal = classify_source(api_record({
        "index": "1", "pmid": "12345678",
        "link": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    }))
    lead = classify_source({"index": "2", "title": "Lead", "link": "https://example.org/post"})
    assert formal["publication_status"] == "formal"
    assert lead["publication_status"] == "unverified"
    assert lead["identity_status"] == "candidate"
    assert source_rejection(lead) == "no_matching_api_record"


def test_authoritative_url_supplies_missing_pmid_without_manual_metadata():
    record = classify_source({
        "title": "Record",
        "link": "https://pubmed.ncbi.nlm.nih.gov/98765432/",
    })
    assert record["pmid"] == "98765432"
    assert record["publication_status"] == "unverified"
    assert record["identity_status"] == "candidate"
    assert record["publication_state"] == "unknown"


def test_authoritative_index_of_preprint_is_still_preprint():
    record = classify_source({
        "title": "A posted study",
        "journal": "bioRxiv",
        "link": "https://pubmed.ncbi.nlm.nih.gov/98765433/",
    })
    assert record["source_kind"] == "preprint"
    assert record["publication_status"] == "preprint"


def test_document_type_is_separate_from_authoritative_identity():
    editorial = classify_source(api_record({
        "title": "Editorial about a research area",
        "publication_types": ["Editorial"],
        "journal": "A Journal",
        "link": "https://pubmed.ncbi.nlm.nih.gov/98765434/",
    }))
    meeting = classify_source(api_record({
        "title": "Annual meeting abstract",
        "publication_types": ["Meeting Abstract"],
        "link": "https://pubmed.ncbi.nlm.nih.gov/98765435/",
    }))
    title_only = classify_source(api_record({
        "title": "Conference proceedings on a normal study",
        "publication_types": ["Journal Article"],
        "link": "https://pubmed.ncbi.nlm.nih.gov/98765436/",
    }))
    assert editorial["publication_status"] == "formal"
    assert editorial["document_type"] == "editorial"
    assert editorial["publication_state"] == "indexed_record"
    assert meeting["document_type"] == "conference_abstract"
    assert meeting["publication_status"] == "formal"
    assert title_only["document_type"] == "journal_article"
    assert meeting["peer_review_status"] == "unknown"


def test_search_page_is_not_an_article_identity():
    source = {"title": "Search results", "link": "https://example.org/search?q=paper"}
    assert is_search_page(source)
    assert classify_source(source)["publication_status"] == "nonformal"


def test_url_alias_dedup_does_not_merge_conflicting_stable_ids():
    records = reconcile_identities([
        {"index": "1", "pmid": "12345678", "link": "https://example.org/paper"},
        {"index": "2", "doi": "10.1234/other", "link": "https://example.org/paper"},
    ])
    assert paper_identity(records[0]) != paper_identity(records[1])


def test_source_card_keeps_absent_metadata_unknown():
    card = build_source_card({"index": "1", "pmid": "12345678", "abstract": "Only an abstract."})
    assert card["evidence"]["abstract"]["available"]
    assert card["fields"]["sample_size"]["status"] == "unknown"
    assert "sample_size" in card["missing_metadata"]


def test_preprint_origin_does_not_establish_peer_review():
    for url in ("https://arxiv.org/abs/2501.12345", "https://europepmc.org/article/PPR/PPR279548"):
        record = {"link": url}
        assert classify_source(record)["peer_review_status"] == "unknown"
        positive = classify_source({**record, "peer_reviewed": True})
        assert positive["peer_review_status"] == "peer_reviewed"
        assert positive["peer_review_status_provenance"]["verification"] == "not_independently_verified"
        assert classify_source({**record, "peer_reviewed": False})["peer_review_status"] == "not_peer_reviewed"
        assert classify_source({**record, "peer_reviewed": "false"})["peer_review_status"] == "unknown"


def test_source_card_does_not_bind_distinct_scientific_fields():
    source = {"species": "stated organism", "cohort": "stated cohort", "n": 7,
              "instrument": "stated instrument", "method": "stated method",
              "publication_types": ["Letter"], "pubdate": "2025-09-03"}
    card = build_source_card(source)
    for field in ("population", "groups", "sample_size", "platform", "technology", "study_type", "year"):
        assert card["fields"][field]["status"] == "unknown"
    for key, value in source.items():
        assert card["fields"][key]["value"] == value
        assert card["fields"][key]["source_key"] == key


def test_source_card_preserves_zero_false_and_text_availability():
    card = build_source_card({"sample_size": 0, "groups": False, "abstract": "  ", "body": []})
    assert card["fields"]["sample_size"]["value"] == 0
    assert card["fields"]["sample_size"]["status"] == "provided_metadata"
    assert card["fields"]["groups"]["value"] is False
    assert card["evidence"]["abstract"] == {"available": False, "status": "not_available"}
    assert card["evidence"]["body"] == {"available": False, "status": "not_available"}


def test_publication_renders_unverified_leads_in_separate_group():
    sources = [
        api_record({"index": "1", "pmid": "12345678", "title": "Formal", "link": "https://pubmed.ncbi.nlm.nih.gov/12345678/", "abstract": "A"}),
        {"index": "2", "title": "Lead", "link": "https://example.org/post", "abstract": "B"},
    ]
    report = "A finding [1]. A lead [2].\n\n## Sources\n\nold"
    publication = publish_report(report, sources, cfg=VerifyConfig(enable_verify=False))
    assert "Sources with unconfirmed identity" in publication.content
    assert "Status: unverified" in publication.content


def test_research_spec_records_explicit_settings_and_defers_if():
    spec = parse_research_spec("Original IF>10 question", {
        "language":"en", "requested_count":10,
        "requested_fields":["platform", "sample_size", "groups"],
        "year_from":2022, "year_to":2026})
    assert spec.language == "en" and spec.requested_count == 10
    assert {"platform", "sample_size", "groups"} <= set(spec.requested_fields)
    assert spec.min_if_mentioned == 10 and spec.if_deferred
    assert spec.provenance["language"] == "explicit_settings"


def test_if_parser_is_syntax_not_implicit_scope():
    scoped = parse_research_spec("Find 20 papers with IF>10")
    assert scoped.min_if_mentioned == 10 and scoped.if_operator == ">"
    assert scoped.requested_count is None
    chinese = parse_research_spec("影响因子10分以上的研究")
    assert chinese.min_if_mentioned == 10 and chinese.if_operator == ">="
    assert parse_research_spec("compare IFN signaling and diffusion").min_if_mentioned is None


def test_keyword_coverage_does_not_guess_scientific_terms():
    kc = KeywordCoverage()
    assert kc.extract_keywords("Find 20 papers with IF>10 about JWST NIRSpec") == []
    assert kc.extract_keywords("question", {"keywords":["JWST", "NIRSpec"]}) == ["JWST", "NIRSpec"]


def test_unstructured_language_recency_and_task_mode_remain_unknown():
    recent = parse_research_spec("麻烦找一下中文文章，只要最近两年的")
    assert recent.language is None and recent.year_from is None and recent.year_to is None
    protocol = parse_research_spec("提取每篇文章的实验方案、测序平台和测序技术")
    assert protocol.protocol_requested is None and protocol.output_mode is None
    assert protocol.requested_fields == ()


def test_empty_conjunctive_queries_get_bounded_lexical_fallbacks():
    candidates = fallback_query_candidates(
        'RNA integrity number RNA-seq quality "last 10 years"[pdat]'
    )
    assert candidates
    assert candidates[0] == "RNA integrity number"
    assert all("last" not in candidate for candidate in candidates)
    assert len(candidates) <= 4



def test_journal_article_and_review_do_not_establish_peer_review():
    journal = classify_source({'publication_types':['Journal Article'], 'link':'https://pubmed.ncbi.nlm.nih.gov/12345678/'})
    assert journal['document_type'] == 'journal_article'
    assert journal['peer_review_status'] == 'unknown'
    review = classify_source({'publication_types':['Review', 'Journal Article'], 'link':'https://pubmed.ncbi.nlm.nih.gov/12345678/'})
    assert review['document_type'] == 'review'
    assert review['peer_review_status'] == 'unknown'


def test_source_language_never_inferred_from_pubmed_or_translation():
    from research_verify.constraint_matcher import ConstraintMatcher
    assert ConstraintMatcher._source_language({'source_engine':'pubmed', 'title':'An English translation'}) is None
    assert ConstraintMatcher._source_language({'language':'chi'}) == 'zh'
    assert ConstraintMatcher._source_language({'language':'eng'}) == 'en'


def test_search_results_words_in_article_title_do_not_override_identity():
    record = classify_source(api_record({'title':'Search results improve after supplementation',
                              'link':'https://pubmed.ncbi.nlm.nih.gov/12345678/'}))
    assert record['source_kind'] == 'pubmed_record'
    assert record['publication_status'] == 'formal'
