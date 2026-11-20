"""Identity/provenance contracts, not scientific grounding accuracy tests."""
import asyncio
from copy import deepcopy

import pytest

from research_verify.config import VerifyConfig
from research_verify.doi_validator import DoiValidator
from research_verify.http_client import HttpResult
from research_verify.record_identity import make_record_provenance
from research_verify.source_identity import classify_source


def packet(**extra):
    return {"uid": "32678530", "title": "A supplied article.", "pubtype": ["Letter"], **extra}


def source(**extra):
    return {"pmid": "32678530", "title": "A supplied article.",
            "link": "https://pubmed.ncbi.nlm.nih.gov/32678530/", **extra}


def test_index_url_and_bare_positive_or_negative_flags_are_not_record_evidence():
    for check in ({}, {"verified": True}, {"verified": False},
                  {"verified": None, "warnings": ["incomplete"]}):
        item = classify_source(source(_verify=check))
        assert item["identity_status"] == "candidate"
        assert item["publication_status"] == "unverified"
        assert item["publication_state"] == "unknown"


def test_processed_record_binds_identity_without_inferring_peer_review_or_scientific_support():
    item = source(record_provenance=make_record_provenance("pubmed", packet()),
                  abstract="A hypothetical unsupported assertion in supplied text.")
    original = deepcopy(item)
    result = classify_source(item)
    assert result["identity_status"] == "confirmed" and result["document_type"] == "letter"
    assert result["publication_state"] == "indexed_record" and result["peer_review_status"] == "unknown"
    assert result["relevance_status"] == result["contradiction_status"] == "unknown"
    assert result["identity_provenance"]["scope"] == "bibliographic_metadata_only"
    assert item == original and result["abstract"] == item["abstract"]


def test_explicit_identifier_url_conflict_survives_a_matching_record():
    item = source(link="https://pubmed.ncbi.nlm.nih.gov/25516281/",
                  record_provenance=make_record_provenance("pubmed", packet()))
    result = classify_source(item)
    assert result["identity_status"] == result["publication_status"] == "conflict"
    assert result["publication_state"] == "unknown"


def test_check_for_another_explicit_identifier_does_not_bind_to_this_source():
    result = classify_source(source(_verify={"pmid": "25516281", "verified": True}))
    assert result["identity_status"] == "conflict"
    assert result["identity_provenance"]["reason"] == "check_identifier_binding_conflict"


def test_different_record_metadata_does_not_bind_to_a_local_title():
    item = source(record_provenance=make_record_provenance("pubmed", packet(title="A different article.")))
    result = classify_source(item)
    assert result["identity_status"] == "conflict"
    assert result["identity_provenance"]["reason"] == "record_title_metadata_difference"


def test_missing_title_or_an_extra_unconfirmed_alias_remains_unknown():
    receipt = make_record_provenance("pubmed", packet(title=""))
    assert classify_source(source(record_provenance=receipt))["identity_status"] == "candidate"
    receipt = make_record_provenance("pubmed", packet())
    assert classify_source(source(doi="10.1234/unconfirmed", record_provenance=receipt))["identity_status"] == "candidate"


def test_valid_index_metadata_is_not_negated_by_an_incomplete_secondary_lookup():
    result = classify_source(source(record_provenance=make_record_provenance("pubmed", packet()),
        _verify={"verified": None, "source": "crossref", "lookup_status": "not_found_in_registry",
                 "warnings": ["crossref_record_not_found"]}))
    assert result["identity_status"] == "confirmed" and result["publication_status"] == "formal"


def test_preprint_identity_and_review_state_are_orthogonal():
    record = {"id": "PPR123456", "source": "PPR", "title": "A supplied preprint",
              "doi": "10.1234/preprint", "pubTypeList": {"pubType": ["Preprint"]}}
    result = classify_source({"title": record["title"], "doi": record["doi"],
        "link": "https://europepmc.org/article/PPR/PPR123456",
        "record_provenance": make_record_provenance("europepmc", record)})
    assert result["identity_status"] == "confirmed"
    assert result["publication_status"] == result["publication_state"] == "preprint"
    assert result["peer_review_status"] == "unknown"


def test_nonmedline_index_ids_do_not_require_a_biomedical_source_code_or_doi():
    record = {"id": "opaque-record", "source": "AGR", "title": "Cross-domain index record"}
    result = classify_source({"title": record["title"], "link": "https://europepmc.org/article/AGR/opaque-record",
        "record_provenance": make_record_provenance("europepmc", record)})
    assert result["identity_status"] == "confirmed" and result["publication_state"] == "indexed_record"
    assert result["document_type"] == "unknown" and result["peer_review_status"] == "unknown"


def test_opaque_provider_ids_are_not_merged_by_case_normalization():
    record = {"id": "RecordA", "source": "AGR", "title": "Index record"}
    result = classify_source({"title": record["title"], "link": "https://europepmc.org/article/AGR/recorda",
        "record_provenance": make_record_provenance("europepmc", record)})
    assert result["identity_status"] == "conflict"


def test_malformed_known_identifier_namespaces_do_not_issue_a_record_receipt():
    for namespace in ("MED", "PMC", "PPR"):
        assert make_record_provenance("europepmc", {"source": namespace, "id": "not-an-id",
                                                   "title": "Malformed metadata"}) is None
    assert make_record_provenance("crossref", {"DOI": {"nested": "10.1234/not-a-scalar"},
                                               "title": ["Malformed metadata"]}) is None


def test_bibliography_groups_by_identity_without_calling_preprints_unconfirmed():
    from research_verify.publication import publish_report
    from research_verify.citation_display import cited_indices
    item = source(record_provenance=make_record_provenance("pubmed", packet(pubtype=["Preprint"])),
                  publication_types=["Preprint"], abstract="Supplied text.", index=1)
    result = publish_report("Finding [1].\n\n## Sources\n", [item], cfg=VerifyConfig(enable_citation_qc=False))
    assert "Identity: confirmed" in result.content and "Status: preprint" in result.content
    assert "Sources with unconfirmed identity" not in result.content
    assert cited_indices(result.content) == [1]


def test_unconfirmed_group_remains_inside_the_bibliography_not_prose():
    from research_verify.publication import publish_report
    from research_verify.citation_display import cited_indices
    item = source(index=41, abstract="Supplied text.")
    for heading in ("## Sources", "### References"):
        result = publish_report("Uncited framing.\n\n"+heading+"\n", [item], cfg=VerifyConfig(enable_citation_qc=False))
        # No cited sources are appended solely for appearing in the input pool.
        assert not result.sources
        result = publish_report("Finding [41].\n\n"+heading+"\n", [item], cfg=VerifyConfig(enable_citation_qc=False))
        assert "Sources with unconfirmed identity" in result.content
        assert cited_indices(result.content) == [1]


def test_web_origin_does_not_establish_unpublished_state_or_a_valid_record():
    for link in ("https://www.10xgenomics.com/support/documentation", "https://example.org/article"):
        result = classify_source({"link": link, "content": "Supplied text"})
        assert result["publication_state"] == "unknown"
        assert result["publication_status"] == "unverified"
        assert result["identity_status"] == "candidate"
        assert result["publication_status_reason"] == "no_matching_api_record"
    assert classify_source({"link": "https://example.org:invalid/article"})["identity_status"] == "missing"


@pytest.mark.parametrize("link", [
    "https://example.org/article", "https://www.researchgate.net/publication/123456",
    "https://www.10xgenomics.com/support/documentation", "https://example.org/search?q=article",
])
def test_bound_record_identity_is_separate_from_transport_and_content(link):
    item = source(link=link, content="Original supplied text; completeness unconfirmed.",
                  record_provenance=make_record_provenance("pubmed", packet()))
    original = deepcopy(item)
    result = classify_source(item)
    assert result["publication_status"] == "formal"
    assert result["identity_status"] == "confirmed"
    assert result["publication_state"] == "indexed_record"
    assert result["document_type"] == "letter" and result["peer_review_status"] == "unknown"
    assert result["content"] == original["content"] and item == original
    assert result["identity_provenance"]["scope"] == "bibliographic_metadata_only"


def test_bound_record_state_overrides_stale_local_preprint_category():
    result = classify_source(source(journal="bioRxiv", publication_types=["Preprint"],
        record_provenance=make_record_provenance("pubmed", packet())))
    assert result["publication_status"] == "formal"
    assert result["publication_state"] == "indexed_record"
    assert result["document_type"] == "letter" and result["peer_review_status"] == "unknown"


def test_bound_preprint_record_on_web_transport_remains_a_preprint():
    result = classify_source(source(link="https://example.org/article", content="Supplied text",
        record_provenance=make_record_provenance("pubmed", packet(pubtype=["Preprint"]))))
    assert result["publication_status"] == result["publication_state"] == "preprint"
    assert result["identity_status"] == "confirmed" and result["peer_review_status"] == "unknown"


class HTTP:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.response


def test_registry_absence_and_malformed_payloads_never_assert_global_identifier_absence():
    cases = [({"doi": "10.5281/zenodo.4663312"}, HttpResult(404, None, "not found")),
             ({"doi": "10.1038/s41586-020-2649-2"}, HttpResult(200, {}, "")),
             ({"pmid": "32678530"}, HttpResult(200, {}, "")),
             ({"pmid": "32678530"}, HttpResult(200, {"result": {"32678530": {"error": "cannot get document summary"}}}, ""))]
    for item, response in cases:
        http = HTTP(response)
        result = asyncio.run(DoiValidator(http, VerifyConfig()).verify(item))
        assert result.verified is None and not result.record_provenance
        assert len(http.calls) == 1  # no new registry/fallback requests


def test_returned_id_must_match_the_requested_identifier():
    cases = [({"doi": "10.1038/s41586-020-2649-2"}, {"message": {"DOI": "10.1234/other", "title": ["Other"]}}),
             ({"pmid": "32678530"}, {"result": {"32678530": {"uid": "25516281", "title": "Other"}}})]
    for item, body in cases:
        result = asyncio.run(DoiValidator(HTTP(HttpResult(200, body, "")), VerifyConfig()).verify(item))
        assert result.verified is None and result.lookup_status == "response_identifier_mismatch"


def test_matching_response_retains_checkable_provider_metadata():
    body = {"message": {"DOI": "10.1038/s41586-020-2649-2", "title": ["Array programming with NumPy"], "type": "journal-article"}}
    item = {"doi": body["message"]["DOI"], "title": body["message"]["title"][0]}
    result = asyncio.run(DoiValidator(HTTP(HttpResult(200, body, "")), VerifyConfig()).verify(item))
    assert result.verified is True and result.lookup_status == "record_found"
    state = classify_source({**item, "_verify": result.model_dump()})
    assert state["identity_status"] == "confirmed" and state["publication_state"] == "registered_record"
    assert state["peer_review_status"] == "unknown"


def test_resolvable_host_is_parsed_as_a_host_not_a_substring():
    http = HTTP(None)
    result = asyncio.run(DoiValidator(http, VerifyConfig()).verify({"link": "https://example.org/?next=pubmed.ncbi.nlm.nih.gov"}))
    assert result.source == "unavailable" and not http.calls


def test_pmid_syntax_does_not_mine_study_counts_or_confuse_identifier_namespaces():
    from research_verify.textutil import extract_pmid
    for value in ("1", 12345, "PMID: 32678530", "https://pubmed.ncbi.nlm.nih.gov/32678530/"):
        assert extract_pmid(value) is not None
    for value in ({"id": "32678530"}, True, "Sample count 32678530", "PMC32678530", "0", 1.5,
                  "https://example.org/32678530/", "https://pubmed.ncbi.nlm.nih.gov/?term=32678530"):
        assert extract_pmid(value) is None
    http = HTTP(None)
    result = asyncio.run(DoiValidator(http, VerifyConfig()).verify({"pmcid": "32678530"}))
    assert result.verified is None and not http.calls
