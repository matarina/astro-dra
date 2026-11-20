"""Run inside the application image: synthetic citation/storage/export regression."""
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from loguru import logger
logger.remove()
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from local_deep_research.config.thread_settings import settings_context
from local_deep_research.database.models import ResearchHistory
from local_deep_research.database.models.base import Base
from local_deep_research.storage.database import DatabaseReportStorage
from local_deep_research.storage.file import FileReportStorage
from local_deep_research.web.services.report_assembly_service import assemble_full_report
from local_deep_research.web.services.research_service import export_report_to_memory
from research_verify.config import VerifyConfig
from research_verify.publication import (
    Publication, PublishedSource, _render_report_v2, digest, publish_report, validate_publication,
)

sources = [
    dict(index=3, doi="10.1234/b", title="Fixture B", url="https://example.org/b"),
    dict(index=9, doi="10.1234/a", title="Fixture A", url="https://example.org/a"),
    dict(index=17, doi="10.1234/a", title="Fixture A duplicate", url="https://example.org/a"),
]
body = "# Findings\n\nAlpha [9]. Beta [3]. Repeat alpha [17].\n\nUncited context remains."
detailed = body + "\n\n## Sources\n\n[3] Fixture B\n   URL: https://example.org/b\n\n[9, 17] Fixture A\n   URL: https://example.org/a"
engine = create_engine("sqlite:////data/citation-format.sqlite")
Base.metadata.create_all(engine)
settings = SimpleNamespace(username=None, get_setting=lambda key, default=None:
    True if key == "report.enable_file_backup" else default)
result = {"synthetic": True, "modes": [], "scope": "Citation presentation, not semantic accuracy"}

with settings_context(settings), Session(engine) as session:
    files = FileReportStorage(Path("/data/reports"))
    for mode, draft in [("quick", body), ("detailed", detailed)]:
        publication = publish_report(draft, sources, cfg=VerifyConfig(enable_verify=False))
        validate_publication(publication.content, publication.metadata())
        assert publication.report_body == draft
        assert [s.index for s in publication.sources] == [1, 2]
        assert publication.sources[0].original_indices == [9, 17]
        assert "Alpha [[1]](https://example.org/a)" in publication.content
        assert "Beta [[2]](https://example.org/b)" in publication.content
        assert "Repeat alpha [[1]](https://example.org/a)" in publication.content
        row = ResearchHistory(id=mode, query="format fixture", mode=mode, status="completed",
            created_at=datetime.now(timezone.utc).isoformat(), research_meta={})
        session.add(row)
        session.commit()
        assert DatabaseReportStorage(session).save_report(mode, publication.content, publication.metadata())
        assert files.save_report(mode, publication.content, publication.metadata())
        assert files.get_report(mode) == publication.content
        assembled = assemble_full_report(row, session)
        if mode == "quick":
            assert assembled.index("[1] Fixture A") < assembled.index("[2] Fixture B")
        else:
            # Preserve the supplied bibliography's order/wording while the
            # structured source map above still follows first citation use.
            assert assembled.index("[2] Fixture B") < assembled.index("[1] Fixture A")
        assert "Uncited context remains." in assembled
        exports = {}
        for fmt in ["quarto", "latex", "odt", "pdf", "ris"]:
            data, _, _ = export_report_to_memory(assembled, fmt)
            assert data
            if fmt == "quarto":
                with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                    qmd = bundle.read(next(n for n in bundle.namelist() if n.endswith(".qmd"))).decode()
                    assert "Alpha [@ref1]" in qmd and "Beta [@ref2]" in qmd
                    bibliography = bundle.read("references.bib").decode()
                    for number, url in [(1, "https://example.org/a"), (2, "https://example.org/b")]:
                        entry = re.search(r"@misc\{ref" + str(number) + r",(.*?)(?=\n@misc|\Z)", bibliography, re.S)
                        assert entry and url in entry.group()
            elif fmt == "ris":
                records = data.decode().split("ER  -")
                assert len(records) - 1 == 2
                assert any("ID  - ref1\n" in record and "Fixture A" in record and "https://example.org/a" in record for record in records)
                assert any("ID  - ref2\n" in record and "Fixture B" in record and "https://example.org/b" in record for record in records)
            exports[fmt] = len(data)
        result["modes"].append({"mode": mode, "display_indices": [1, 2], "body_preserved": True,
                               "storage_roundtrip": True, "exports": exports})

    legacy_sources = [PublishedSource(index=s["index"], original_indices=[s["index"]],
        paper_id="doi:" + s["doi"], artifact_id="", title=s["title"], url=s["url"])
        for s in sources]
    old_content = _render_report_v2(body, legacy_sources)
    old = Publication(schema_version="2.0", status="unverified", content=old_content,
        content_sha256=digest(old_content), report_body=body, sources=legacy_sources)
    old_row = SimpleNamespace(report_content=old_content, research_meta=old.metadata(), completed_at=None)
    before = json.dumps(old_row.research_meta, sort_keys=True)
    display = assemble_full_report(old_row, None)
    assert "Alpha [[1]](https://example.org/a)" in display
    assert "[1] Fixture A" in display and "[2] Fixture B" in display
    assert old_row.report_content == old_content and json.dumps(old_row.research_meta, sort_keys=True) == before
    result["old_report_view_fixed_without_write"] = True

result["checks_passed"] = True
print(json.dumps(result))
