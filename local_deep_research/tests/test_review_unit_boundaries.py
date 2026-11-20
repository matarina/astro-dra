"""Keep independent list entries independent without discarding assertions."""
import pytest
from research_verify.evidence_flow import review_units


@pytest.mark.parametrize('bullet',['-','*','1.','•','‣','◦','⁃'])
def test_separate_list_entries_keep_their_own_citation_scope(bullet):
    second='2.' if bullet=='1.' else bullet
    report=f'{bullet} First statement [1].\n{second} Second statement [2].'
    units=review_units(report)
    assert len(units)==2
    assert [u.citations for u in units]==[[1],[2]]
    assert all(report[u.report_start:u.report_end]==u.text for u in units)


def test_sentences_and_wrapped_lines_inside_one_item_keep_context():
    report='• An uncited opening. The same item\n  continues [1].\n• Another item [2].'
    units=review_units(report)
    assert len(units)==2
    assert units[0].text=='• An uncited opening. The same item\n  continues [1].'
    assert [u.citations for u in units]==[[1],[2]]


def test_unpunctuated_pdf_items_are_not_one_multi_source_assertion():
    report='• First assertion [1]\n• Second assertion [2].'
    assert [u.citations for u in review_units(report)]==[[1],[2]]


def test_form_feed_does_not_join_distinct_page_assertions():
    report='First assertion [1].\n\fNext assertion [2].'
    units=review_units(report)
    assert [u.citations for u in units]==[[1],[2]]
    assert all(report[u.report_start:u.report_end]==u.text for u in units)
