"""Citation/coordinate/routing contracts, without scientific meaning labels."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from research_verify.claims import extract_legacy_report_claims, extract_report_claims
from research_verify.citation_display import cited_indices
from research_verify.config import VerifyConfig
from research_verify.evidence_flow import review_units
from research_verify.publication import publish_report,validate_publication
from research_verify.source_collection import sources_for_draft

CASES=json.loads((Path(__file__).parent/"fixtures/markdown_role_cases.json").read_text())


@pytest.mark.parametrize("case",CASES,ids=lambda c:c["case_id"])
def test_frozen_numeric_citation_roles_and_original_coordinates(case):
    assert cited_indices(case["draft"])==case["expected_prose_citation_ids"]
    for unit in extract_report_claims(case["draft"]):
        assert case["draft"][unit.report_start:unit.report_end]==unit.text


def test_unknown_heading_question_and_recommendation_do_not_depend_on_science_words():
    for title in ["X enables resistance","X is resistant","αβ结论"]:
        text="## "+title+"\n\nA proposed follow-up?\n\nWe recommend further research."
        units=extract_report_claims(text)
        assert [u.kind for u in units]==["heading_candidate","prose_candidate","prose_candidate"]
        assert not any(u.citations for u in units)


def test_cited_heading_reaches_native_review_without_a_semantic_word_rule():
    text="## X enables resistance [17]"
    units=review_units(text)
    assert len(units)==1 and units[0].citations==[17]
    assert units[0].text==text


def test_source_recovery_preserves_current_archive_and_unknowns_under_normal_headings():
    current=[{"index":7,"abstract":"Current text.","link":"https://example.org/current"}]
    archive=[{"index":17,"abstract":"Prior text.","link":"https://example.org/prior"}]
    original=deepcopy((current,archive))
    selected,state=sources_for_draft(current,archive,"## Detailed Findings\nPrior [17], unresolved [123].")
    assert [s["index"] for s in selected]==[7,17]
    assert state["missing_ids"]==[123] and state["recovered_ids"]==[17]
    assert (current,archive)==original


def test_publication_keeps_unmapped_bibliography_and_non_citation_markup():
    code="`literal [99]` and [Read more](https://example.org/x[99])"
    body="## Detailed Findings\nEvidence [17]. "+code+"\n\n## References\n[99] Supplied unmatched entry.\n\n## Discussion\nKeep this sentence."
    source={"index":17,"abstract":"Supplied text.","link":"https://example.org/prior","title":"Known source"}
    p=publish_report(body,[source],cfg=VerifyConfig(enable_citation_qc=False))
    assert p.schema_version=="2.2" and p.report_body==body
    assert "Evidence [[1]](https://example.org/prior)." in p.content
    assert code in p.content and "[99] Supplied unmatched entry." in p.content
    assert "## Discussion\nKeep this sentence." in p.content
    assert p.status=="unverified" and p.audit_status=="disabled"
    assert validate_publication(p.content,p.metadata())==p


def test_reference_link_and_balanced_destination_preserve_original_coordinates():
    body="Finding [17][ref].\n\n[ref]: https://example.org/p(a)\n"
    assert cited_indices(body)==[17]
    source={"index":17,"abstract":"Supplied text.","link":"https://example.org/prior"}
    p=publish_report(body,[source],cfg=VerifyConfig(enable_citation_qc=False))
    assert "Finding [[1]](https://example.org/prior)." in p.content
    assert "[ref]: https://example.org/p(a)" in p.content


def test_crlf_coordinates_are_not_normalized_before_citation_formatting():
    text="## Detailed Findings\r\nObserved [17].\r\n"
    source={"index":17,"abstract":"Supplied text.","link":"https://example.org/prior"}
    p=publish_report(text,[source],cfg=VerifyConfig(enable_citation_qc=False))
    assert p.content=="## Detailed Findings\r\nObserved [[1]](https://example.org/prior).\r\n"


def test_unbalanced_labels_are_not_repaired_by_guessing_a_numeric_reference():
    for marker in ["[[17]", "[17]]", "[17,]", "[[17](https://example.org/p)"]:
        assert cited_indices("Literal "+marker+".")==[]


def test_legacy_sentence_split_protects_url_punctuation_and_citation():
    body="Evidence at https://www.10xgenomics.com/products/chromium. [17]."
    claims=extract_legacy_report_claims(body)
    assert len(claims)==1
    assert claims[0].citations==[17]
    assert claims[0].text==body
