"""Raw report offsets follow CommonMark lines, including PDF text artifacts."""
import pytest
from research_verify.report_syntax import layout, citation_spans
from research_verify.claims import extract_report_claims


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('separator', ['\f', '\v', '\x85', '\u2028', '\u2029'])
def test_non_commonmark_separators_do_not_shift_subsequent_report_coordinates(newline, separator):
    report = ('Introduction' + separator + 'continued.' + newline * 2 +
              'A paper in Calibration Journal reported measurements [81].' + newline * 2 +
              '## References' + newline + '[81] Bibliographic record.' + newline)
    blocks, bibliography = layout(report)
    target = 'A paper in Calibration Journal reported measurements [81].'
    claims = extract_report_claims(report)
    cited = [c for c in claims if c.citations == [81]]
    assert len(cited) == 1 and cited[0].text == target
    assert report[cited[0].report_start:cited[0].report_end] == target
    citations = citation_spans(report)
    assert len(citations) == 1
    assert report[citations[0].start:citations[0].end] == '[81]'
    assert bibliography[0].start == report.index('## References')
    assert all(report[b.start:b.end].strip() for b in blocks)


def test_empty_and_final_newline_layouts_keep_raw_boundaries():
    assert layout('') == ([], [])
    for report in ['Claim [1].', 'Claim [1].\n', 'Claim [1].\r\n']:
        c = extract_report_claims(report)[0]
        assert report[c.report_start:c.report_end] == 'Claim [1].'
