"""Source reading separates subjects/states and never substitutes invented prose."""
import json
from types import SimpleNamespace

import pytest

from test_generation_grounding import handler


TEXT = "Loss of factor Q caused damage. Factor Q itself maintained balance."


def payload():
    return {"readings": [{"source_id": 17, "observations": [
        {"subject_quote": "Loss of factor Q", "state_quote": "Loss",
         "quote": "Loss of factor Q caused damage."},
        {"subject_quote": "Factor Q", "state_quote": "",
         "quote": "Factor Q itself maintained balance."}], "reported_limits": []}]}


def test_source_reading_preserves_only_controlled_evidence_roles():
    from research_verify.source_reading import build_reading_notes, render_reading_notes
    p = {"readings": [{"source_id": 17, "observations": [
        {"subject_quote": "Loss of factor Q", "state_quote": "Loss",
         "evidence_role": "outcome", "quote": "Loss of factor Q caused damage."},
        {"subject_quote": "Factor Q", "state_quote": "",
         "evidence_role": ["invented_role"], "quote": "Factor Q itself maintained balance."}],
        "reported_limits": []}]}
    notes = build_reading_notes(json.dumps(p), {17: TEXT})
    assert [item.get("evidence_role") for item in notes["observations"]] == ["outcome", "other"]
    rendered = render_reading_notes(notes)
    assert "Evidence role: outcome" in rendered
    assert "Evidence role: other" in rendered


def test_source_reading_roles_can_be_disabled_for_a_paired_baseline():
    from research_verify.source_reading import build_reading_notes, render_reading_notes
    p = {"readings": [{"source_id": 17, "observations": [
        {"subject_quote": "Loss of factor Q", "state_quote": "Loss",
         "evidence_role": "outcome", "quote": "Loss of factor Q caused damage."}],
        "reported_limits": []}]}
    notes = build_reading_notes(json.dumps(p), {17: TEXT}, include_roles=False)
    assert "evidence_role" not in notes["observations"][0]
    assert "Evidence role:" not in render_reading_notes(notes)


def test_candidate_claim_units_are_bound_to_exact_quotes_and_rendered_before_writing():
    from research_verify.source_reading import build_reading_notes, render_reading_notes
    p = {"readings": [], "claim_units": [{
        "claim": "Factor Q has a reported effect, with a supplied limitation.",
        "evidence": [{"source_id": 17, "quote": "Factor Q itself maintained balance."}],
        "qualifiers": [{"source_id": 17, "quote": "Loss of factor Q caused damage."}],
    }]}
    notes = build_reading_notes(json.dumps(p), {17: TEXT}, include_roles=True)
    assert notes["claim_unit_count"] == 1
    rendered = render_reading_notes(notes)
    assert "ATTRIBUTION PLAN" in rendered
    assert "Claim unit 1 (unverified plan)" in rendered
    assert "Evidence source [17] original quotation" in rendered
    assert "Qualifying source [17] original quotation" in rendered


def test_claim_units_with_unlocatable_quotes_are_rejected_and_never_reach_writer():
    from research_verify.source_reading import build_reading_notes, render_reading_notes
    p = {"readings": [], "claim_units": [{
        "claim": "An invented claim.",
        "evidence": [{"source_id": 17, "quote": "The supplied text proves an invented result."}],
    }]}
    notes = build_reading_notes(json.dumps(p), {17: TEXT}, include_roles=True)
    assert notes["claim_units"] == []
    assert any(x.get("reason") == "claim_unit_evidence_invalid" for x in notes["rejections"])
    assert "An invented claim." not in render_reading_notes(notes)


def test_claim_units_are_not_created_for_roles_off_baseline():
    from research_verify.source_reading import build_reading_notes
    p = {"readings": [], "claim_units": [{
        "claim": "Factor Q has a reported effect.",
        "evidence": [{"source_id": 17, "quote": "Factor Q itself maintained balance."}],
    }]}
    notes = build_reading_notes(json.dumps(p), {17: TEXT}, include_roles=False)
    assert notes["claim_units"] == []


def test_source_notes_keep_loss_and_the_factors_own_action_as_distinct_originals():
    from research_verify.source_reading import build_reading_notes, render_reading_notes
    notes = build_reading_notes(json.dumps(payload()), {17: TEXT})
    assert len(notes["observations"]) == 2
    assert [x["subject_quote"] for x in notes["observations"]] == ["Loss of factor Q", "Factor Q"]
    for observation in notes["observations"]:
        assert observation["quote"] == TEXT[observation["start"]:observation["end"]]
    rendered = render_reading_notes(notes)
    assert "Loss of factor Q caused damage." in rendered
    assert "Factor Q itself maintained balance." in rendered
    assert "not a semantic verification" in rendered
    assert "distinct quoted subject groups" in rendered
    assert rendered.index("Quoted subject: Factor Q") < rendered.index("Quoted subject: Loss of factor Q")


@pytest.mark.parametrize("edit", ["invented_quote", "wrong_subject", "inferred_state", "unknown_source", "boolean_source"])
def test_unlocatable_or_cross_subject_notes_never_reach_the_writer_as_originals(edit):
    from research_verify.source_reading import build_reading_notes
    p = payload()
    item = p["readings"][0]
    if edit == "invented_quote":
        item["observations"][0]["quote"] = "Loss of factor Q protected all tissues."
    elif edit == "wrong_subject":
        item["observations"][0]["subject_quote"] = "Factor Q itself"
    elif edit == "inferred_state":
        item["observations"][0]["state_quote"] = "overexpression"
    elif edit == "unknown_source":
        item["source_id"] = 99
    else:
        item["source_id"] = True
    notes = build_reading_notes(json.dumps(p), {17: TEXT, 1: TEXT})
    assert notes["rejections"]
    assert len(notes["observations"]) < 2
    assert all(x["source_id"] == 17 for x in notes["observations"])


def test_only_a_supplied_author_statement_can_be_included_as_a_reported_limit():
    from research_verify.source_reading import build_reading_notes
    p = payload();p["readings"][0]["reported_limits"] = ["No trial in the literature measured durability."]
    notes = build_reading_notes(json.dumps(p), {17: TEXT})
    assert notes["reported_limits"] == [] and notes["rejections"]


def test_excerpts_cannot_be_quoted_as_a_continuous_original_across_a_material_boundary():
    from research_verify.source_reading import build_reading_notes
    text = "Factor Q was measured.\n\n[... source excerpt boundary ...]\n\nFactor R improved."
    p = {"readings": [{"source_id": 17, "observations": [
        {"subject_quote": "Factor Q", "state_quote": "", "quote": text}]}]}
    notes = build_reading_notes(json.dumps(p), {17: text})
    assert notes["observations"] == [] and notes["status"] == "unavailable"
    assert notes["rejections"][0]["reason"] == "quote_crosses_material_boundary"


def test_real_writer_reads_originals_before_writing_without_invoking_native_review():
    class Model:
        prompts = []
        def invoke(self, prompt):
            self.prompts.append(prompt)
            return SimpleNamespace(content=json.dumps(payload()) if len(self.prompts) == 1 else "Q maintained balance [17].")
    model = Model();writer = handler(model)
    writer.settings_snapshot = {"citation.enable_source_reading": True, "general.enable_fact_checking": False}
    result = writer.analyze_followup("What did Q do?", [{"index": 17, "abstract": TEXT}], "Organize findings [17].", 0)
    assert len(model.prompts) == 2
    assert "Previous Knowledge:" not in model.prompts[0] and TEXT in model.prompts[0]
    assert "Quoted subject: Loss of factor Q" in model.prompts[1]
    assert "Quoted subject: Factor Q" in model.prompts[1]
    assert result["content"] == "Q maintained balance [17]."


@pytest.mark.parametrize("failure", [TimeoutError("reader unavailable"), "malformed JSON"])
def test_reader_failure_falls_back_to_full_original_evidence_and_still_writes(failure):
    class Model:
        prompts = []
        def invoke(self, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                if isinstance(failure, Exception):
                    raise failure
                return SimpleNamespace(content=failure)
            return SimpleNamespace(content="Q maintained balance [17].")
    model = Model();writer = handler(model)
    writer.settings_snapshot = {"citation.enable_source_reading": True, "general.enable_fact_checking": False}
    result = writer.analyze_followup("Question", [{"index": 17, "abstract": TEXT}], "", 0)
    assert len(model.prompts) == 2 and TEXT in model.prompts[1]
    assert result["content"] == "Q maintained balance [17]."
