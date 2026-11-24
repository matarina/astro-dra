"""Original material survives subtask synthesis and imperfect model output."""
import json

import pytest

from research_verify.subtask_handoff import build_handoff, render_handoff


ABSTRACT = ("Loss of factor Q caused tissue damage. "
            "Factor Q promotes degradation of R and maintains metabolic balance. "
            "Restoring factor Q improved outcomes in model mice.")


def source(index=7, **kwargs):
    return {"index": str(index), "title": "Factor Q study", "abstract": ABSTRACT,
            "link": "https://example.org/paper", "doi": "10.1234/example", **kwargs}


def deliver(summary, selections, sources=None, **kwargs):
    sources = sources if sources is not None else {7: source()}
    return build_handoff(json.dumps({"summary": summary, "evidence": selections}), sources.get, **kwargs)


def test_short_abstract_keeps_distinct_subjects_and_states_even_with_bad_summary():
    wrong = "Loss of factor Q maintains metabolic balance [7]."
    handoff = deliver(wrong, [{"source_id": 7, "quote": "promotes degradation of R"}])
    assert handoff["summary"] == wrong  # Formatting does not pretend to repair meaning.
    card = handoff["materials"][0]
    assert card["text"] == ABSTRACT and card["status"] == "complete_abstract"
    assert card["quote_status"] == "located"
    assert handoff["semantic_verification"] == "not_performed"
    text = render_handoff(handoff)
    assert "RESEARCH MAP" in text and "ORIGINAL SOURCE MATERIAL" in text
    assert text.index(wrong) < text.index("BEGIN ORIGINAL SOURCE EXCERPT")
    assert card["text"] == source()[card["field"]][card["start"]:card["end"]]


def test_invented_quote_is_never_returned_as_original():
    handoff = deliver("Use study [7].", [{"source_id": 7, "quote": "An invented numerical benefit of 90%."}])
    card = handoff["materials"][0]
    assert card["quote_status"] == "not_located" and card["text"] == ABSTRACT
    assert "invented numerical" not in render_handoff(handoff)
    assert "not uniquely located" in render_handoff(handoff)


def test_unknown_source_does_not_borrow_a_different_papers_text():
    handoff = deliver("Suggested papers [7, 99].", [{"source_id": 99, "quote": ABSTRACT}])
    cards = {c["source_id"]: c for c in handoff["materials"]}
    assert cards[99]["status"] == "source_unavailable" and "text" not in cards[99]
    assert cards[7]["text"] == ABSTRACT


def test_same_paper_selections_share_complete_abstract_once():
    handoff = deliver("Paper [7].", [{"source_id": 7, "quote": "Loss of factor Q caused tissue damage."},
                                    {"source_id": "7", "quote": "Factor Q promotes degradation of R"}])
    assert len(handoff["materials"]) == 1 and handoff["material_chars"] == len(ABSTRACT)


def test_long_original_keeps_selected_paragraph_and_neighboring_subjects():
    before = "Background. " * 800
    target = "Deleting factor Q increased damage. Factor Q itself has a protective effect."
    raw = before + "\n\n" + target + "\n\n" + "Restoring Q reduced damage.\n\n" + "Methods. " * 1000
    handoff = deliver("Use study [7].", [{"source_id": 7, "quote": "Factor Q itself has a protective effect."}],
                      {7: source(abstract="", content=raw, content_type="full_text")})
    card = handoff["materials"][0]
    assert target in card["text"] and "Restoring Q reduced damage." in card["text"]
    assert card["text"] == raw[card["start"]:card["end"]]
    assert card["status"] == "selected_excerpt"


def test_full_text_selection_is_not_replaced_by_short_abstract():
    raw = "Detailed experiment found a 12-unit decrease after treatment."
    handoff = deliver("Paper [7].", [{"source_id": 7, "quote": raw}],
                      {7: source(content_type="full_text", full_content=raw)})
    assert handoff["materials"][0]["text"] == raw
    assert handoff["materials"][0]["basis"] == "retrieved full text"


def test_ambiguous_long_quote_does_not_guess_between_experiments():
    raw = "First experiment. Shared result. " + "Background. " * 1000 + "Second experiment. Shared result."
    handoff = deliver("Paper [7].", [{"source_id": 7, "quote": "Shared result."}],
                      {7: source(abstract="", content=raw, content_type="full_text")})
    assert handoff["materials"][0]["quote_status"] == "ambiguous"
    assert "text" not in handoff["materials"][0]


def test_budget_omission_is_explicit_and_does_not_truncate_original():
    handoff = deliver("Papers [7, 8].", [], {7: source(), 8: source(8)}, material_budget=len(ABSTRACT))
    assert handoff["materials"][0]["text"] == ABSTRACT
    assert handoff["materials"][1]["status"] == "omitted_material_budget"
    assert "text" not in handoff["materials"][1]
    assert handoff["material_chars"] == len(ABSTRACT)
    assert "omitted_material_budget" in render_handoff(handoff)


@pytest.mark.parametrize("content", ["Legacy summary [7].", "```json\nnot JSON [7]\n```",
                                    [{"type": "text", "text": "Legacy summary [7]."}]])
def test_legacy_or_bad_json_preserves_summary_and_attaches_original(content):
    handoff = build_handoff(content, {7: source()}.get)
    assert handoff["status"] == "unstructured_fallback"
    assert handoff["materials"][0]["text"] == ABSTRACT
    assert "Delivery format fallback" in render_handoff(handoff)


def test_fetch_summary_is_not_accepted_as_raw_source_material():
    handoff = deliver("Paper [7].", [{"source_id": 7, "quote": "Model says the treatment cured disease."}],
                      {7: source(abstract="", snippet="Model says the treatment cured disease.",
                                 fetched_content="The measured difference was not significant.")})
    card = handoff["materials"][0]
    assert card["quote_status"] == "not_located" and "text" not in card
    assert "cured disease" not in render_handoff(handoff)


def test_chinese_subject_change_and_negation_are_copied_unchanged():
    abstract = "缺失因子甲会加重损伤。因子甲本身抑制乙。补回因子甲可改善损伤，但不代表临床疗效。"
    handoff = deliver("用于机制章节[7]。", [{"source_id": 7, "quote": "因子甲本身抑制乙。"}],
                      {7: source(abstract=abstract)})
    assert handoff["materials"][0]["text"] == abstract


def test_non_biomedical_experiment_context_is_preserved_without_topic_rules():
    original = "In dataset A, method M increased error. In dataset B, method M reduced error."
    handoff = deliver("Compare settings [7].", [{"source_id": 7, "quote": "method M reduced error"}],
                      {7: source(abstract=original)})
    assert handoff["materials"][0]["text"] == original


def test_boolean_ids_are_not_silently_mapped_to_source_one():
    handoff = deliver("No references selected.", [{"source_id": True, "quote": ABSTRACT}], {1: source(1)})
    assert handoff["materials"] == []


@pytest.mark.parametrize("fenced", [True, False])
def test_prefaced_model_json_is_read_without_losing_its_original_selections(fenced):
    payload = json.dumps({"summary": "Use study [7].", "evidence": [{"source_id": 7, "quote": ABSTRACT}]})
    if fenced:
        payload = "```json\n" + payload + "\n```"
    handoff = build_handoff("I have enough material. Here is the deliverable.\n" + payload,
                            {7: source()}.get)
    assert handoff["status"] == "structured"
    assert handoff["summary"] == "Use study [7]."
    assert handoff["materials"][0]["text"] == ABSTRACT


def test_competing_deliverables_are_not_silently_resolved_by_order():
    first = json.dumps({"summary": "First proposal [7].", "evidence": []})
    second = json.dumps({"summary": "Different proposal [7].", "evidence": []})
    handoff = build_handoff(first + "\n" + second, {7: source()}.get)
    assert handoff["status"] == "unstructured_fallback"
    assert "First proposal" in handoff["summary"] and "Different proposal" in handoff["summary"]


@pytest.mark.parametrize("iteration_failure", [False, True])
def test_real_subtopic_tool_returns_originals_and_private_trace_for_each_worker(monkeypatch, tmp_path, iteration_failure):
    import ast
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import nullcontext
    from datetime import UTC, datetime
    import gzip
    import math
    from pathlib import Path
    import sys
    import threading
    import time
    from types import ModuleType, SimpleNamespace
    import typing
    from loguru import logger
    from research_verify import synthesis_trace

    observed = {}
    recursion_error = type("GraphRecursionError", (Exception,), {})

    def create_agent(**kwargs):
        assert "original source selections" in kwargs["system_prompt"]
        def invoke(request, config):
            topic = request["messages"][0]["content"].splitlines()[0]
            index = 7 if topic == "alpha" else 8
            observed["collector"].find_by_index(index)
            if iteration_failure:
                raise recursion_error("Iteration limit reached after collecting material")
            return {"messages": [SimpleNamespace(type="tool", content=f"Retrieved [{index}]",
                                                  tool_call_id=f"tool-{topic}"),
                                 SimpleNamespace(type="ai", content=json.dumps({
                                     "summary": f"Organize {topic} around study [{index}].",
                                     "evidence": [{"source_id": index, "quote": "promotes degradation of R"}]}))]}
        def stream(request, config, stream_mode):
            topic = request["messages"][0]["content"].splitlines()[0]
            index = 7 if topic == "alpha" else 8
            observed["collector"].find_by_index(index)
            if iteration_failure:
                yield {"messages": [SimpleNamespace(type="ai", content="Search", tool_calls=[{"id": "q"}]),
                                    SimpleNamespace(type="tool", content=f"Retrieved [{index}]", tool_call_id="q")]}
                raise recursion_error("Iteration limit reached after collecting material")
            yield invoke(request, config)
        return SimpleNamespace(invoke=invoke, stream=stream)

    agents = ModuleType("langchain.agents")
    agents.create_agent = create_agent
    monkeypatch.setitem(sys.modules, "langchain.agents", agents)
    # AST-load the real factory while keeping upstream infrastructure offline.
    for name in ["test_handoff_runtime", "test_handoff_runtime.security", "test_handoff_runtime.security.egress"]:
        package = ModuleType(name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, name, package)
    audit = ModuleType("test_handoff_runtime.security.egress.audit_hook")
    audit.active_egress_context = lambda _: nullcontext()
    monkeypatch.setitem(sys.modules, audit.__name__, audit)
    monkeypatch.setenv("LDR_RESEARCH_TRACE_ENABLED", "true")
    monkeypatch.setenv("LDR_RESEARCH_TRACE_DIR", str(tmp_path / "traces"))
    real_start = synthesis_trace.start_trace
    monkeypatch.setattr(synthesis_trace, "start_trace", lambda kind: real_start(kind, "handoff-integration"))

    tree = ast.parse((Path(__file__).parents[1] / "langgraph_agent_strategy.py").read_text())
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_make_research_subtopic_tool")
    ns = {**vars(typing), "__package__": "test_handoff_runtime.advanced_search_system.strategies", "__spec__": None,
          "BaseChatModel": object, "SearchResultsCollector": object,
          "MAX_SUBAGENT_WORKERS": 4, "MAX_SUBTOPICS": 5, "MAX_SUBTOPICS_HARD_LIMIT": 10,
          "SUBAGENT_TIMEOUT_SECONDS": 30, "SUBAGENT_TIMEOUT_OVERALL_MULTIPLIER": 2,
          "NEUTRAL_PRIMARY_SEARCH_DESCRIPTION": "Search", "logger": logger,
          "tool": lambda **kw: lambda fn: fn, "ThreadPoolExecutor": ThreadPoolExecutor,
          "threading": threading, "math": math, "time": time, "datetime": datetime, "UTC": UTC, "json": json,
          "build_fetch_tool": lambda mode, collector, **kw: observed.update(collector=collector),
          "_load_specialized_engine_tools": lambda *a, **kw: [SimpleNamespace(name="search_mock")],
          "get_search_context": lambda: None, "thread_cleanup": nullcontext,
          "GraphRecursionError": recursion_error,
          "_scrub_tool_error": lambda text: text}
    exec(compile(ast.Module(body=[factory], type_ignores=[]), "subtask-tool", "exec"), ns)
    records = {7: source(), 8: source(8, abstract="Other experiment. " + ABSTRACT)}
    tool = ns["_make_research_subtopic_tool"]("mock", object(), {},
                SimpleNamespace(find_by_index=records.get), 3, search_enabled=False)
    deliveries = [tool(["alpha", "beta"])]
    for topic in ("alpha", "beta"):
        if not any(f"## {topic}\n" in text for text in deliveries):
            deliveries.append(tool(wait_for=[topic]))
    text = "\n".join(deliveries)
    assert text.count("RESEARCH MAP") == text.count("BEGIN ORIGINAL SOURCE EXCERPT") == 2
    assert records[7]["abstract"] in text and records[8]["abstract"] in text
    assert "## alpha" in text and "## beta" in text
    directories = list((tmp_path / "traces" / "handoff-integration").iterdir())
    assert len(directories) == 2
    for directory in directories:
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        assert {"subtask_request", "subtask_messages", "subtask_handoff"} <= {e["stage"] for e in events}
        event = next(e for e in events if e["stage"] == "subtask_messages")
        messages = json.loads(gzip.decompress((directory / event["file"]).read_bytes()))["messages"]
        if iteration_failure:
            assert [m["role"] for m in messages] == ["ai", "tool"]
        else:
            assert [m["role"] for m in messages] == ["tool", "ai"]
        assert directory.stat().st_mode & 0o777 == 0o700
