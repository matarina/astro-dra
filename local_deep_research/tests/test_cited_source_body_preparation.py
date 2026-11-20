from research_verify.source_evidence import prepare_cited_source_bodies


class FakeFetcher:
    def __init__(self):
        self.calls = []
        self.events = []

    def article(self, source):
        self.calls.append(int(source["index"]))
        return "Methods used BD FACS Fusion and Smart-seq2 on seven samples."


def test_opt_in_cited_body_preparation_fetches_only_cited_records():
    fetcher = FakeFetcher()
    sources = [
        {"index": "13", "pmid": "123", "abstract": "Abstract only."},
        {"index": "14", "pmid": "124", "abstract": "Another abstract."},
    ]
    result = prepare_cited_source_bodies(sources, [13], fetcher=fetcher, limit=24)
    assert fetcher.calls == [13]
    assert result["fetched_sources"] == 1
    assert sources[0]["content_type"] == "full_text"
    assert sources[1].get("fetched_content") is None


def test_cited_body_preparation_preserves_missing_source_state():
    fetcher = FakeFetcher()
    result = prepare_cited_source_bodies([], [99], fetcher=fetcher)
    assert result["status"] == "unavailable"
    assert result["unavailable_sources"] == [99]
