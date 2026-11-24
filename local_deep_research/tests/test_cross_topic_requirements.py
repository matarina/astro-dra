import json
from types import SimpleNamespace

from research_verify.generation import format_source_documents
from research_verify.task_eligibility import assess_eligibility
from research_verify.synthesis_trace import source_snapshot
from test_generation_grounding import Capture, collector, handler


def test_shared_quote_keeps_design_check_independent_of_date():
    quote = "Randomized trials published from 2020 through 2024"
    plan = {"publication_years": {"start": 2020, "end": 2024, "user_quote": quote},
            "eligibility": [{"criterion": "randomized trial", "user_quote": quote}]}
    text = "This was an observational study."
    source = {"index": 1, "year": 2022, "abstract": text}
    docs = handler(Capture())._create_documents([source])

    def invoke(prompt, **kwargs):
        assert "randomized trial" in prompt
        return json.dumps({"checks": [{"source_id": 1, "criterion_id": 1,
                                        "status": "contradicted", "quotes": [text]}]})

    ledger = assess_eligibility(SimpleNamespace(_invoke_text=invoke), plan, docs, [source],
                                SimpleNamespace(record=lambda *args: None), {1})
    assert ledger[1]["status"] == "excluded"
    assert ledger[1]["criteria"][1]["quote"] == text


def test_later_search_can_extend_a_plan_and_retry_without_duplicates():
    c = collector()
    c.task_question = "Find trials with one year of follow-up. Report accuracy and cost."
    first = {"eligibility": [{"criterion": "trial", "user_quote": "trials"}],
             "questions": [{"question": "Accuracy?", "user_quote": "accuracy"}]}
    more = {"eligibility": [{"criterion": "one year of follow-up", "user_quote": "one year of follow-up"}],
            "questions": [{"question": "Cost?", "user_quote": "cost"}]}
    for update in [first, more, more]:
        c.record_task_requirements(update)
    assert c.task_plan["eligibility"] == first["eligibility"] + more["eligibility"]
    assert c.task_plan["questions"] == first["questions"] + more["questions"]


def test_source_block_preserves_cross_topic_fields_and_their_own_source():
    sources = [
        {"index": 1, "title": "Diagnostic accuracy", "sensitivity": "91.7%",
         "specificity": "83.4%", "follow_up_duration": "14 months",
         "confidence_interval": {"lower": 0.81, "upper": 0.97}, "adverse_events": 0,
         "abstract": "The paper compared diagnostic tests.", "_internal": "private marker",
         "headers": {"Authorization": "private marker"}, "settings_snapshot": {"key": "private marker"}},
        {"index": 2, "title": "Economic evaluation", "cost_per_qaly": "26000 EUR",
         "abstract": "The study evaluated costs."},
    ]
    docs = handler(Capture())._create_documents(sources)
    material = format_source_documents(docs, "Summarize both reports", max_chars=20000)
    first = material.views[1]["metadata"]
    second = material.views[2]["metadata"]
    for k in ("sensitivity", "specificity", "follow_up_duration", "confidence_interval", "adverse_events"):
        assert json.dumps({k: sources[0][k]})[1:-1] in first
        assert k not in second
    assert "26000 EUR" in second and "26000 EUR" not in first
    assert "private marker" not in str(material)
    snapshot = source_snapshot(sources)
    replay_docs = handler(Capture())._create_documents(snapshot)
    replay = format_source_documents(replay_docs, "Summarize both reports", max_chars=20000)
    assert replay.views[1]["metadata"] == first
    assert replay.views[2]["metadata"] == second
    assert "private marker" not in json.dumps(snapshot)
