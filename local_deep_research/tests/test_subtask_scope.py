"""Preserve acquired context and keep reading limits distinct from study findings."""
from hashlib import sha256
import json
from types import SimpleNamespace

from research_verify.subtask_handoff import build_handoff, render_handoff
from research_verify.generation import format_source_documents
from test_generation_grounding import handler, Capture


ABSTRACT = "The review introduces experimental methods and possible applications."
PARAGRAPH = ("Several experimental methods process distinct datasets under measured conditions. "
             "The compared methods preserve sample labels and timing information (Table 2). "
             "Their functions include data acquisition, transformation and error assessment (Fig. 3).")


def selected(quote, *, body=None, abstract=ABSTRACT):
    body = body or ("Unrelated introduction.\n\n" * 1000 +
                    "Experimental setting and controls.\n\n" + PARAGRAPH +
                    "\n\nThe second dataset was evaluated independently.\n\n" +
                    "Additional methods.\n\n" * 1000)
    source = {"index": 7, "title": "Methods comparison", "abstract": abstract,
              "fetched_content": body, "content_type": "abstract"}
    content = json.dumps({"summary": "Use the acquired methods section [7].",
                          "evidence": [{"source_id": 7, "quote": quote}]})
    return build_handoff(content, {7: source}.get), source


def test_edited_cross_references_recover_real_body_without_promoting_the_quote():
    quote = PARAGRAPH.replace(" (Table 2)", "").replace(" (Fig. 3)", "")
    handoff, source = selected(quote)
    card = handoff["materials"][0]
    assert card["field"] == "fetched_content"
    assert PARAGRAPH in card["text"] and "independently" in card["text"]
    assert card["quote_status"] == "not_located"
    assert card["selection_method"] == "verbatim_anchors"
    assert card["text"] == source[card["field"]][card["start"]:card["end"]]
    assert card["source_text_sha256"] == sha256(source[card["field"]].encode()).hexdigest()
    assert "not uniquely located" in render_handoff(handoff)


def test_recovered_context_preserves_negation_instead_of_copying_changed_claim():
    raw = PARAGRAPH + " Treatment did not improve the measured outcome under these conditions."
    quote = raw.replace(" (Table 2)", "").replace("did not improve", "improved")
    handoff, _ = selected(quote, body="Introduction.\n\n" * 800 + raw + "\n\nOther methods.\n\n" * 800)
    card = handoff["materials"][0]
    assert card["field"] == "fetched_content" and card["quote_status"] == "not_located"
    assert "did not improve" in card["text"] and quote not in card["text"]
    assert handoff["semantic_verification"] == "not_performed"


def test_recovery_does_not_choose_between_repeated_body_passages():
    quote = PARAGRAPH.replace(" (Table 2)", "")
    body = PARAGRAPH + "\n\nOther experiment.\n\n" * 700 + PARAGRAPH
    handoff, _ = selected(quote, body=body)
    card = handoff["materials"][0]
    assert card["field"] == "abstract" and card["text"] == ABSTRACT
    assert card["quote_status"] == "ambiguous"


def test_recovery_needs_long_original_anchors_and_keeps_source_boundaries():
    handoff, _ = selected("An invented statement claims a large improvement in unrelated systems.")
    card = handoff["materials"][0]
    assert card["field"] == "abstract" and card["quote_status"] == "not_located"
    assert card.get("selection_method") != "verbatim_anchors"


def test_follow_up_questions_are_scoped_navigation_with_source_references():
    handoff = build_handoff(json.dumps({"summary": {
        "directions": ["Interacting processes"],
        "follow_up_questions": [{"question": "How do the measured processes interact?", "source_ids": [7]}]},
        "evidence": []}), {7: {"abstract": ABSTRACT}}.get)
    text = render_handoff(handoff)
    assert "How do the measured processes interact?" in text and "[7]" in text
    assert "not evidence of absence" in text
    assert "this subtask" in text and ABSTRACT in text


def test_legacy_gap_is_preserved_as_an_unverified_note_not_an_absence_finding():
    gap = "No acquired material discusses interacting processes."
    handoff = build_handoff(json.dumps({"summary": {"gaps": [gap]}, "evidence": []}), {}.get)
    assert gap in handoff["summary"]  # Do not silently rewrite old generated claims.
    assert "Legacy unverified scope notes" in render_handoff(handoff)


def document(index, text, **metadata):
    return SimpleNamespace(page_content=text, metadata={"index": index, "title": f"Study {index}",
                           "source": f"https://example.org/{index}", **metadata})


def test_reading_inventory_describes_the_actual_view_and_does_not_claim_full_paper_absence():
    scope = []
    a = "The abstract describes an association."
    docs = [document(7, a, abstract=a, evidence_type="abstract"),
            document(8, "Unrelated introduction.\n\n" * 500 + "Endpoint Q improved.",
                     evidence_type="retrieved full text")]
    material = format_source_documents(docs, "Endpoint Q", reading_scope=scope)
    assert a in material and "Endpoint Q improved" in material
    assert {v["index"] for v in scope} == {7, 8}
    assert scope[0]["view_kind"] == "abstract_only"
    assert scope[1]["view_kind"] == "selected_excerpts"
    assert all(v["exhaustive_assessment"] is False for v in scope)


def test_reading_inventory_excludes_sources_not_selected_for_the_writer():
    scope = []
    docs = [document(i, "Original abstract. " * 65, abstract="Original abstract. " * 65)
            for i in range(1, 5)]
    material = format_source_documents(docs, "Question", selector=lambda _: "[3]",
                                       max_chars=4200, required_ids={2}, reading_scope=scope)
    assert {v["index"] for v in scope} == {2, 3}
    assert "[1]\nTitle:" not in material and "[4]\nTitle:" not in material


def test_real_writer_receives_reading_scope_separately_from_the_unverified_draft():
    model = Capture()
    writer = handler(model)
    writer.settings_snapshot = {"general.enable_fact_checking": False}
    writer.analyze_followup("What remains unknown?", [{"index": 17, "title": "Study",
        "abstract": "The treatment sometimes restores function.", "content_type": "abstract"}],
        "**Interpretation:** Most studies did not report durability outcomes [17].", 0)
    prompt = model.prompts[0]
    assert "EVIDENCE READING LIMITS" in prompt
    assert "abstract_only" in prompt and "[17]" in prompt
    assert "not establish what full studies did or did not report" in prompt
    assert "Most studies did not report durability outcomes" not in prompt
    assert "Draft interpretation follow-up questions (unverified)" in prompt
    assert len(model.prompts) == 1  # No added audit, correction call or report gate.


def test_tagged_interpretation_is_separated_but_factual_prose_tables_and_sources_survive():
    from research_verify.generation import prepare_draft_for_writing
    factual = "A measured result was reported [7]."
    note = "**解读（Interpretation）：** Most studies omitted durability measurements [9]."
    table = "| Model | Measurement | Source |\n| --- | --- | --- |\n| Population A | Observed change | [11] |"
    draft = "## Mechanisms\n\n" + factual + "\n\n" + note + "\n\n" + table
    prepared, notes = prepare_draft_for_writing(draft)
    assert "## Mechanisms" in prepared and factual in prepared and table in prepared
    assert "Most studies omitted" not in prepared and "[9]" in prepared
    assert notes == [{"original": note, "source_ids": [9], "kind": "draft_interpretation"}]
    assert note in draft  # Original is not rewritten or deleted.


def test_ordinary_prose_is_not_filtered_by_factual_or_absence_keywords():
    from research_verify.generation import prepare_draft_for_writing
    draft = "Most studies reported outcomes [17]. The authors explicitly did not measure X [17]."
    assert prepare_draft_for_writing(draft) == (draft, [])


def test_authors_explicit_negative_statement_is_preserved_in_original_source_text():
    original = "Interpretation: No participants in this cohort reported outcome X."
    draft = "**Interpretation:** No study in the literature reported outcome X [17]."
    model = Capture()
    writer = handler(model)
    writer.settings_snapshot = {"general.enable_fact_checking": False}
    writer.analyze_followup("What was reported?", [{"index": 17, "title": "Cohort A",
                            "abstract": original, "content_type": "abstract"}], draft, 0)
    prompt = model.prompts[0]
    assert original in prompt  # Source text is not processed as a draft annotation.
    assert "No study in the literature reported outcome X" not in prompt
    assert "[17]" in prompt and len(model.prompts) == 1
