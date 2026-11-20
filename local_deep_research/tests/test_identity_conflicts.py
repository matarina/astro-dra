import hashlib
import pytest
from research_verify.identity_conflicts import identity_conflict_candidates


def row(report,start,end,source,value,field='journal'):
    a=report.index(value,start,end)
    return dict(mention_id=f'm{start}',source_id=source,claims={field:value},
                report_start=start,report_end=end,
                report_text_sha256=hashlib.sha256(report[start:end].encode()).hexdigest(),
                field_positions={field:[a,a+len(value)]})


def test_same_source_differences_preserve_both_values_without_a_truth_verdict():
    report='Journal A [9].\nJournal B [9].\nJournal C [10].'
    rows=[row(report,0,14,9,'Journal A'),row(report,15,29,'9','Journal B'),
          row(report,30,len(report),10,'Journal C')]
    result=identity_conflict_candidates(report,rows)
    assert len(result)==1 and result[0]['source_id']=='9'
    assert result[0]['status']=='different_reported_values_need_primary_review'
    assert {v['normalized_value'] for v in result[0]['values']}=={'journal a','journal b'}


def test_case_and_spacing_variants_are_grouped_but_wrong_coordinates_fail():
    report='Journal A [9].\nJOURNAL  A [9].'
    rows=[row(report,0,14,9,'Journal A'),row(report,15,len(report),9,'JOURNAL  A')]
    assert identity_conflict_candidates(report,rows)==[]
    rows[1]['field_positions']['journal'][0]+=1
    with pytest.raises(ValueError,match='coordinate'):identity_conflict_candidates(report,rows)


def test_different_years_remain_candidates_without_assuming_date_semantics():
    report='Online 2025 [4]. Print 2026 [4].'
    rows=[row(report,0,16,4,'2025','year'),row(report,17,len(report),4,'2026','year')]
    assert identity_conflict_candidates(report,rows)[0]['field']=='year'
