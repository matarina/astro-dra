"""Exercise truncation accounting with saved outputs and a fake provider."""
import json

import pytest

from research_verify.generation_receipt import output_completeness
from scripts.review_saved_jobs import review
from scripts import run_astro_dra_heldout_v1 as runner


@pytest.mark.parametrize("text,finish,expected", [
    ("Answer", "stop", "complete"), ("Answer", "length", "truncated"),
    ("", "stop", "empty"), ("  ", "length", "empty"),
    ("Answer", None, "unknown"), ("Answer", "content_filter", "unknown"),
])
def test_completeness_never_infers_success_from_nonempty_text(text, finish, expected):
    assert output_completeness(text, finish) == expected


@pytest.mark.parametrize("finish,status", [("stop", "completed"), ("length", "incomplete"), (None, "incomplete")])
def test_runner_keeps_partial_output_without_calling_it_complete(tmp_path, monkeypatch, finish, status):
    monkeypatch.setattr(runner, "call_model", lambda *a, **kw: ("Saved answer", {"finish_reason": finish}))
    case = {"case_id": "case", "question": "Question", "source_text": "Evidence",
            "source_packet_sha256": "fixture"}
    row = runner.run_one(case, "baseline", tmp_path)
    assert row["status"] == status
    assert json.loads((tmp_path / "case.json").read_text())["output"] == "Saved answer"


def test_inventory_preserves_unknown_and_ambiguous_states_and_excludes_private(tmp_path):
    paired = tmp_path / "baseline"
    paired.mkdir()
    (paired / "C1.json").write_text(json.dumps({"case_id": "C1", "status": "completed",
                                               "output": "Partial", "finish_reason": "length"}))
    private = tmp_path / "gold.private"
    private.mkdir()
    (private / "summary.json").write_text("Do not parse private material")
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "report.md").write_text("A finding [1].\n\n## Sources\n[2] Uncited")
    (result_dir / "sources.json").write_text(json.dumps([
        {"index": 1, "title": "One"}, {"index": 1, "title": "Other"}, {"index": 2}]))
    result = review(tmp_path)
    assert result["counts"] == {"generation": 1, "research_report": 1}
    assert result["completed_without_completion_evidence"] == 1
    assert result["truncated_marked_completed"] == 1
    report = next(r for r in result["artifacts"] if r["kind"] == "research_report")
    assert report["unresolved_citation_ids"] == [1]
    assert report["uncited_source_ids"] == [2]
    assert result["errors"] == []
