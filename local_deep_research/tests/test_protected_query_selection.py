from research_verify import generation
from research_verify.passages import Passage


def test_draft_expansion_retains_request_windows_and_only_spends_remaining_budget(monkeypatch):
    text = "request evidence" + "x" * 30 + "draft evidence" + "y" * 30
    baseline = Passage(0, 16, text[:16], 1)
    added = Passage(46, 60, text[46:60], 2)
    overlap = Passage(8, 24, text[8:24], 3)
    monkeypatch.setattr(generation, "retrieve_passages", lambda text, query, **kw:
                        (baseline,) if query == "request" else (overlap, added))
    receipts = []
    result = generation.page_excerpts(text, "request + draft", 32,
                                      protected_query="request", selection_receipts=receipts)
    assert baseline.text in result and added.text in result
    assert overlap.text not in result
    assert receipts[-1]["selected_text_chars"] == 30
    assert receipts[-1]["scientific_status"] == "not_assessed"
    smaller = generation.page_excerpts(text, "request + draft", 25, protected_query="request")
    assert smaller == baseline.text


def test_absent_or_identical_protected_query_keeps_legacy_selection_and_call_count(monkeypatch):
    calls = []
    def retrieve(text, query, **kw):
        calls.append(query)
        return (Passage(0, 8, text[:8], 1),)
    monkeypatch.setattr(generation, "retrieve_passages", retrieve)
    text = "original source bytes " * 20
    assert generation.page_excerpts(text, "query", 60) == text[:8]
    assert generation.page_excerpts(text, "query", 60, protected_query="query") == text[:8]
    assert calls == ["query", "query"]
