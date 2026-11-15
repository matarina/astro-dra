"""Quarto export service.

This module exports structural numeric citations and explicit source fields.
"""

import io
import re
import zipfile
from typing import Optional

from loguru import logger

from .base import BaseExporter, ExportOptions, ExportResult
from .registry import ExporterRegistry


@ExporterRegistry.register
class QuartoExporter(BaseExporter):
    """Quarto exporter preserving report text and provided bibliography fields.

    This exporter converts markdown content to Quarto (.qmd) format,
    which can be rendered to HTML, PDF, or other formats using the
    Quarto publishing system.

    The export produces a ZIP file containing:
    - The .qmd document
    - A references.bib bibliography file
    """

    @property
    def format_name(self) -> str:
        return "quarto"

    @property
    def file_extension(self) -> str:
        return ".zip"

    @property
    def mimetype(self) -> str:
        return "application/zip"

    def export(
        self,
        markdown_content: str,
        options: Optional[ExportOptions] = None,
    ) -> ExportResult:
        """Convert markdown content to Quarto format.

        Args:
            markdown_content: The markdown text to convert
            options: Optional export options (title, metadata)

        Returns:
            ExportResult with ZIP content as bytes containing .qmd and .bib files

        Raises:
            ValueError: If content exceeds maximum size limit
        """
        try:
            # Check content size limit to prevent OOM errors
            self._validate_content_size(markdown_content)

            options = options or ExportOptions()

            # Extract title from markdown if not provided
            title = options.title
            if not title:
                title_match = re.search(
                    r"^#\s+(.+)$", markdown_content, re.MULTILINE
                )
                title = (
                    title_match.group(1) if title_match else "Research Report"
                )

            from research_verify.quarto_sources import bibliography, document
            bib_content = bibliography(markdown_content)
            exported_content = document(markdown_content, title, bib_content)

            # Use base class method for safe filename generation, then extract base name
            base_filename = self._generate_safe_filename(options.title)
            # Remove the .zip extension that _generate_safe_filename adds
            safe_title = base_filename.replace(self.file_extension, "")

            # Create a zip file in memory containing both files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Add the Quarto document
                zipf.writestr(f"{safe_title}.qmd", exported_content)
                # Add the bibliography file
                zipf.writestr("references.bib", bib_content)

            zip_bytes = zip_buffer.getvalue()
            zip_buffer.close()

            filename = f"{safe_title}_quarto.zip"

            logger.info(
                f"Generated Quarto with bibliography in memory (zip), "
                f"size: {len(zip_bytes)} bytes"
            )

            return ExportResult(
                content=zip_bytes,
                filename=filename,
                mimetype=self.mimetype,
            )

        except Exception:
            logger.exception("Error generating Quarto")
            raise
