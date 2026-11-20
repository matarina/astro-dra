"""Offline regressions for planner verifier input provenance and budgets."""

import importlib.util
from pathlib import Path

from research_verify.independent_verification import SourcePassage


def _runner():
    path = Path(__file__).parents[2] / "scripts/run_hallucination_next_phase_experiment_20261113.py"
    spec = importlib.util.spec_from_file_location("next_phase_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_passages_use_canonical_fetched_material_and_scope():
    runner = _runner()
    fetched = "Methods and results acquired from the original article body."
    rows = runner._passages([{
        "index": "5", "title": "Paper", "pmid": "5",
        "abstract": "Short abstract.", "fetched_content": fetched,
        "content_type": "abstract",
    }])
    assert len(rows) == 1
    assert fetched in rows[0].text
    assert rows[0].field == "abstract+fetched_content"
    assert "canonical source_material" in rows[0].scope_note
    assert rows[0].start == 0 and rows[0].end == len(rows[0].text)


def test_bound_passages_marks_truncation_and_retains_later_source_identity():
    runner = _runner()
    passages = (
        SourcePassage(1, "large", text="a" * 70000, field="body", basis="full text"),
        SourcePassage(2, "second", text="evidence from second source", field="abstract", basis="abstract"),
    )
    kept, records = runner._bound_passages(passages, 60000)
    assert [p.source_id for p in kept] == [1]
    assert len(kept[0].text) == 60000
    assert records == (
        {"source_id": 1, "status": "truncated_budget", "original_chars": 70000, "kept_chars": 60000},
        {"source_id": 2, "status": "omitted_budget", "original_chars": 27, "kept_chars": 0},
    )
