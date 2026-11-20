"""Source-bound retrieval hints do not establish scientific attribution."""
from types import SimpleNamespace
from hashlib import sha256
from research_verify.evidence_selection import _terms, select_context_windows
from research_verify.evidence_flow import _review_material
from research_verify.generation import format_source_documents


def document(index, text):
    return SimpleNamespace(page_content=text, metadata={'index': index, 'title': 'Study', 'source': 'https://example.org/' + str(index)})


def test_compound_hint_retains_original_and_decimal_not_numeric_equivalence():
    text = '31-stage 2.5-fold well-being'
    legacy = _terms(text)
    assert legacy == {'31-stage', '2.5-fold', 'well-being'}
    expanded = _terms(text, compound_terms=True)
    assert legacy <= expanded and {'31', 'stage', '2.5', 'fold'} <= expanded
    assert '2' not in expanded and '5' not in expanded
    raw = 'Unrelated description.\n\nAn item uses a 31-stage procedure.'
    receipt = []
    selected = select_context_windows(raw, '31', window_chars=80, max_windows=1,
                                      overlap_chars=0, compound_terms=True, selection_receipts=receipt)
    assert selected[0].text == raw[selected[0].start:selected[0].end]
    assert '31-stage' in selected[0].text and receipt[0]['compound_terms'] is True


def test_source_queries_use_only_explicit_associations_and_preserve_claims():
    docs = [document(1, 'Useful original A. ' * 500), document(2, 'Useful original B. ' * 500)]
    claims = {0: {'text': 'Item alpha [1].', 'source_ids': [1]},
              1: {'text': 'Item beta [2].', 'source_ids': [2]}}
    before = repr(claims)
    result, same = _review_material(docs, 'Question\nItem alpha [1].\nItem beta [2].', claims, {1, 2}, 25000,
                                    source_scoped_question='Question', compound_terms=True)
    assert same is claims and repr(claims) == before
    for sid, text in [(1, 'Item alpha [1].'), (2, 'Item beta [2].')]:
        assert result.views[sid]['selection_query_sha256'] == sha256(('Question\n' + text).encode()).hexdigest()
    assert set(result.views) == {1, 2}


def test_absent_options_keep_blocks_registry_and_complete_text_identical():
    docs = [document(3, 'Original paper text. ' * 500)]
    base = format_source_documents(docs, 'Question', max_chars=25000)
    explicit = format_source_documents(docs, 'Question', max_chars=25000, source_queries=None, compound_terms=False)
    assert str(base) == str(explicit) and base.views == explicit.views
    guarded = format_source_documents(docs, 'Question', max_chars=25000, source_queries={3: 'Another hint'}, compound_terms=True)
    assert str(guarded) == str(base)  # Complete text fits; no excerpt selection needed.


def test_uncited_claim_and_foreign_query_do_not_become_source_attribution():
    docs = [document(1, 'Original source text. ' * 400)]
    claims = {0: {'text': 'Uncited item.', 'source_ids': []}}
    material, same = _review_material(docs, 'Question\nUncited item.', claims, {1}, 25000,
                                    source_scoped_question='Question')
    assert same[0]['source_ids'] == []
    assert material.views[1]['selection_query_sha256'] == sha256(b'Question\n').hexdigest()
