"""Explicit bibliography/export contracts, not source or citation verification."""
import io
import json
from pathlib import Path
import re
import zipfile

import pytest

from local_deep_research.exporters.quarto_exporter import QuartoExporter
from local_deep_research.exporters.ris_exporter import RISExporter
from research_verify.quarto_sources import bibliography_entries


CASES = json.loads((Path(__file__).parent / "fixtures/quarto_source_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["id"])
def test_provided_url_contract_and_unknown_publication_metadata(case):
    original = case["body"]
    actual = bibliography_entries(original)
    assert {str(i): entry["url"] for i, entry in actual.items()} == case["expected"]
    result = QuartoExporter().export(original)
    with zipfile.ZipFile(io.BytesIO(result.content)) as bundle:
        bib = bundle.read("references.bib").decode()
        qmd = bundle.read(next(n for n in bundle.namelist() if n.endswith(".qmd"))).decode()
    for index, url in case["expected"].items():
        entry = re.search(r"@misc\{ref" + index + r",(.*?)(?=\n@misc|\Z)", bib, re.S)
        assert entry
        if url:
            assert url in entry.group()
    assert not re.search(r"(?m)^\s*(?:year|author)\s*=", bib)
    assert 'Accessed: \\today' not in bib
    assert original == case["body"]
    if case["id"] == "protected":
        assert "`literal [7]`" in qmd
        assert "[ordinary](https://example.org/[7])" in qmd
        assert "\\[7]" in qmd
        assert "````\n[7]\n```\n````" in qmd
        assert "A [@ref7]." in qmd
    if case["id"] == "unknown_citation":
        assert "unresolved [99]" in qmd and "@ref99" not in qmd
    ris = RISExporter().export(original).content.decode()
    assert ris.count("ER  -") == len(case["expected"])
    assert not re.search(r"(?m)^(?:Y1|PY|DA|LA|PB|AU)  -", ris)
    for index, url in case["expected"].items():
        record = next(record for record in ris.split("ER  -") if "ID  - ref" + index + "\n" in record)
        assert "TI  - " + actual[int(index)]["title"] in record
        if url:
            assert "UR  - " + url in record


def test_code_in_bibliography_cannot_create_an_export_record_or_url():
    content = "A [1].\n\n## Sources\n\n[1] Title\n\n```\nURL: https://example.org/not-a-field\n[2] Not a source\n```"
    entries = bibliography_entries(content)
    assert set(entries) == {1} and entries[1]["url"] == ""
    assert entries[1]["url_status"] == "unavailable"
    assert "[2] Not a source" in entries[1]["provided_text"]


def test_explicit_identifiers_survive_without_bibliographic_inference():
    content = "A [1].\n\n## Sources\n\n[1] Trial report\n   Identity: candidate\n   DOI: 10.1234/fixture\n   PMID: 12345"
    data = RISExporter().export(content).content.decode()
    assert "DO  - 10.1234/fixture" in data and "AN  - PMID:12345" in data
    assert "PY  -" not in data and "Y1  -" not in data and "LA  -" not in data
    assert "N1  -    Identity: candidate" in data


@pytest.mark.parametrize("heading", ["## Citations", "Citations:"])
def test_legacy_citations_bibliography_label_is_preserved(heading):
    text = "A [7].\n\n" + heading + "\n\n[17] Book\n   URL: https://example.org/book"
    assert set(bibliography_entries(text)) == {17}
    assert "UR  - https://example.org/book" in RISExporter().export(text).content.decode()
