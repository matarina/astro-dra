"""Evidence exposure and fallback boundaries, not scientific quality labels."""
from copy import deepcopy
from types import SimpleNamespace

from research_verify.generation import format_source_documents, _source_blocks


def document(index, text, **metadata):
    return SimpleNamespace(page_content=text, metadata={"index": index,
        "title": "Source " + str(index), "source": "https://example.org/" + str(index), **metadata})


def test_complete_acquired_text_keeps_distant_evidence_and_original_metadata():
    body = "Introduction. " * 1400 + "A distant result with its original qualifiers."
    abstract = "Separate supplied abstract."
    docs = [document(17, body, abstract=abstract, evidence_type="retrieved text (completeness unconfirmed)")]
    original = deepcopy(docs)
    scopes, calls = [], []
    output = format_source_documents(docs, "Introduction?", selector=lambda p: calls.append(p), reading_scope=scopes)
    assert body in output and abstract in output
    assert docs == original and not calls
    assert "published-paper completeness unconfirmed" in output
    assert scopes[0]["view_kind"] == "complete_acquired_text"
    assert scopes[0]["exhaustive_assessment"] is False


def test_serialized_metadata_size_decides_fit_and_above_budget_keeps_old_path():
    docs = [document(i, ("Original acquired text. " * 600), abstract="Concise abstract " + str(i))
            for i in (7, 17, 27)]
    original = deepcopy(docs)
    old_blocks = list(_source_blocks(docs, "text"))
    expected = "\n\n".join(block for _, block in old_blocks)
    assert len(expected) < 25000 < sum(len(d.page_content) for d in docs)
    output = format_source_documents(docs, "text", max_chars=25000)
    assert output == expected
    assert docs == original


def test_fit_boundary_counts_headers_and_separators_without_calling_selector():
    docs = [document(7, "Acquired text. " * 700), document(17, "Other text. " * 700)]
    complete = "\n\n".join(block for _, block in _source_blocks(docs, "", complete_acquired=True))
    calls = []
    output = format_source_documents(iter(docs), max_chars=len(complete), required_ids=(7, 17),
                                     selector=lambda p: calls.append(p))
    assert output == complete and not calls
    assert len(output) <= len(complete)
    # One character below the full serialization must use the existing view.
    output = format_source_documents(docs, max_chars=len(complete)-1)
    old = "\n\n".join(block for _, block in _source_blocks(docs, ""))
    assert output == old


def test_abstract_only_evidence_keeps_complete_abstract_scope():
    abstract = "Original abstract. " * 1000
    doc = document(9, abstract, abstract=abstract, evidence_type="abstract (not the full paper)")
    scopes = []
    result = format_source_documents([doc], reading_scope=scopes)
    assert abstract in result and result.count(abstract) == 1
    assert scopes[0]["view_kind"] == "abstract_only"
    assert "complete supplied abstract" in result
