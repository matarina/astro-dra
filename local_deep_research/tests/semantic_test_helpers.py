"""Mock structured responses for tests of mapping/retrieval, not semantic truth."""
from research_verify.semantics import DIMENSIONS


def complete_payload(data):
    data = dict(data)
    if "dimensions" not in data:
        quote = data.get("supporting_fragment") or ""
        quote = quote if isinstance(quote,str) else ""
        data["dimensions"] = {
            name: {"status":"matched" if quote else "not_applicable",
                   "evidence_quote":quote,"reason":"isolated mock fixture"}
            for name in DIMENSIONS
        }
    return data
