from research_verify.nli_windows import source_windows


def test_complete_claim_and_source_survive_overlapping_windows():
    text = 'Title\nA 248-gene panel; 中文关系不能丢。\n' * 5
    hypothesis = 'Full claim with uncertainty and both entities.'
    prefix = 'Exact record identity\n'
    count = lambda p, h: len(p) + len(h) + 3
    r = source_windows(text, hypothesis, prefix, count, max_tokens=115, overlap_chars=8)
    assert r['text_coverage_complete']
    covered = set()
    for w in r['windows']:
        assert w['text'] == text[w['start']:w['end']]
        assert w['premise'] == prefix + w['text']
        assert count(w['premise'], r['complete_hypothesis']) <= 115
        covered.update(range(w['start'], w['end']))
    assert covered == set(range(len(text)))
    assert r['semantic_verdict'] is None


def test_long_claim_is_unrun_rather_than_silently_shortened():
    r = source_windows('important source', 'h' * 50, '', lambda p, h: len(p+h), max_tokens=40)
    assert not r['windows'] and not r['text_coverage_complete']
    assert r['complete_hypothesis'] == 'h' * 50


def test_window_cap_preserves_explicit_uncovered_region():
    r = source_windows('a' * 150, 'h', '', lambda p, h: len(p+h),
                       max_tokens=40, overlap_chars=5, max_windows=2)
    assert not r['text_coverage_complete']
    assert r['status'] == 'window_budget_exhausted'
    assert r['first_uncovered_char'] == r['windows'][-1]['end'] < 150
