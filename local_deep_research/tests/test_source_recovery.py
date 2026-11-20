"""Explicit source routing and preservation; no scientific verdicts or models."""
from copy import deepcopy

from research_verify.source_collection import sources_for_draft


def source(index, text="Original source."):
    return {"index": index, "abstract": text, "link": "https://example.org/"+str(index)}


def test_only_cited_archive_records_join_all_current_sources():
    current = [source(3), source(5)]
    archive = [*deepcopy(current), source(17), source(41)]
    selected, state = sources_for_draft(current, archive, "Prior work [17] and current work [3].")
    assert [s["index"] for s in selected] == [3, 5, 17]
    assert state["requested_ids"] == [17, 3] and state["recovered_ids"] == [17]
    assert state["status"] == "resolved" and state["scope"] == "citation_index_lookup_only"
    assert current == [source(3), source(5)]
    selected[2]["abstract"] = "A downstream annotation cannot change the archive."
    assert archive[2]["abstract"] == "Original source."


def test_missing_and_ambiguous_indices_stay_distinct_without_source_substitution():
    one, other = source(17), source(17, "Different supplied record.")
    selected, state = sources_for_draft([], [one, other, source(41)], "Unresolved [17, 999].")
    assert selected == [] and state["recovered_ids"] == []
    assert state["missing_ids"] == [999] and state["ambiguous_ids"] == [17]
    assert state["status"] == "incomplete"


def test_conflict_does_not_delete_current_source_or_choose_archive_identity():
    current = [source(17)]
    selected, state = sources_for_draft(current, [source(17, "Conflicting archive record.")], "Finding [17].")
    assert selected == current and selected[0] is current[0]
    assert state["ambiguous_ids"] == [17] and state["recovered_ids"] == []


def test_bibliography_and_code_only_labels_do_not_expand_the_archive():
    draft = "Uncited prose.\n\n```text\n[17]\n```\n\n## References\n\n[41] Entry."
    selected, state = sources_for_draft([], [source(17), source(41)], draft)
    assert selected == [] and state["requested_ids"] == []
    assert state["status"] == "no_citations"


def test_grouped_linked_and_chinese_citations_resolve_same_explicit_ids_once():
    draft = "Finding [[17]](https://example.org/17), further work 【41】 and repeated [17, 41]."
    selected, state = sources_for_draft([], [source(17), source(41)], draft)
    assert [s["index"] for s in selected] == [17, 41]
    assert state["requested_ids"] == state["recovered_ids"] == [17, 41]


def test_identical_repeated_records_do_not_create_false_ambiguity():
    record = source(17)
    selected, state = sources_for_draft([], [record, deepcopy(record)], "Finding [17].")
    assert selected == [record] and state["ambiguous_ids"] == []


def test_invalid_record_indices_never_alias_a_numeric_citation():
    selected, state = sources_for_draft([], [source(True), source(-1), source("not-an-index")], "Finding [1].")
    assert selected == [] and state["missing_ids"] == [1]


def test_uncited_current_records_and_unknown_labels_remain_available():
    current = [source(3), source(5)]
    selected, state = sources_for_draft(current, [source(17)], "Unknown finding [999].")
    assert selected == current and state["missing_ids"] == [999]
    assert state["recovered_ids"] == []
