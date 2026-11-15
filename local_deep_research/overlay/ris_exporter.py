"""Export provided bibliographic fields without inferred dates or publishers."""
from typing import Optional

from .base import BaseExporter, ExportOptions, ExportResult
from .registry import ExporterRegistry


@ExporterRegistry.register
class RISExporter(BaseExporter):
    @property
    def format_name(self):
        return "ris"

    @property
    def file_extension(self):
        return ".ris"

    @property
    def mimetype(self):
        return "text/plain"

    def export(self, markdown_content: str, options: Optional[ExportOptions] = None):
        self._validate_content_size(markdown_content)
        from research_verify.quarto_sources import bibliography_entries
        records = []
        for index, entry in sorted(bibliography_entries(markdown_content).items()):
            # GEN is a generic record, not a journal/web/peer-review inference.
            fields = ["TY  - GEN", "ID  - ref" + str(index), "TI  - " + entry["title"]]
            if entry["url"]:
                fields.append("UR  - " + entry["url"])
            identifiers = entry.get("provided_identifiers", {})
            if identifiers.get("DOI"):
                fields.append("DO  - " + identifiers["DOI"])
            if identifiers.get("PMID"):
                fields.append("AN  - PMID:" + identifiers["PMID"])
            # Keep additional supplied metadata/text as literal notes rather
            # than infer author, publication year, language or publisher.
            fields.extend("N1  - " + line for line in entry["provided_text"].splitlines())
            records.append("\n".join(fields + ["ER  - "]))
        options = options or ExportOptions()
        return ExportResult(content=("\n\n".join(records) + ("\n" if records else "")).encode("utf-8"),
                            filename=self._generate_safe_filename(options.title), mimetype=self.mimetype)
