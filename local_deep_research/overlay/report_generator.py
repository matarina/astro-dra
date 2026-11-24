import importlib
import os
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC

from langchain_core.language_models import BaseChatModel
from loguru import logger

# Fix circular import by importing directly from source modules
from .config.llm_config import get_llm
from .config.thread_settings import get_setting_from_snapshot
from .search_system import AdvancedSearchSystem
from .text_optimization.citation_formatter import (
    LDR_APPENDED_SOURCES_SENTINEL,
)
from .utilities.json_utils import get_llm_response_text

# Default constants for context accumulation to avoid repetition
# These are used as fallbacks when settings are not available
DEFAULT_MAX_CONTEXT_SECTIONS = (
    3  # Number of previous sections to include as context
)
DEFAULT_MAX_CONTEXT_CHARS = (
    4000  # Max characters for context (safe for smaller local models)
)

# Spelled-out output rules appended to every per-subsection prompt. Small
# and/or quantized local models routinely ignore long, vague instructions,
# so this is intentionally short, numbered, and refers to the actual
# rendering consequences (a duplicate heading, a duplicate bibliography)
# rather than abstract guidance.
#
# The framework always (a) inserts `## i.j Name` itself before appending
# LLM content and (b) appends one consolidated `## Sources` block to the
# whole report at the end of _format_final_report. The LLM does not need
# to repeat either of those things, and historically has — producing
# visibly stacked duplicate headings and duplicate "## Sources" sections
# per subsection.
_SUBSECTION_OUTPUT_GUIDANCE = (
    "\n\nOUTPUT FORMAT RULES (FOLLOW EXACTLY):\n"
    "1. Do NOT start your output with a Markdown heading of any level "
    "(#, ##, ###, ####, etc.). The framework already inserts the "
    "subsection heading for you; starting with your own heading line "
    "creates a visible duplicate next to it in the final report.\n"
    "2. Do NOT end your output with a '## Sources', '## References', "
    "'## Bibliography', '## Citations', '## Key References', or "
    "'## Selected Bibliography' section. The framework appends a single "
    "consolidated '## Sources' block to the entire report after every "
    "subsection is written; including your own bibliography duplicates "
    "the same source list.\n"
    "3. Begin your output with prose (a paragraph or a table), not a "
    "heading and not an italic purpose statement. You may use '###' / "
    "'####' / deeper levels for internal sub-subheadings inside this "
    "subsection only."
)

def get_report_generator(search_system=None):
    """Return an instance of the report generator with default settings.

    Args:
        search_system: Optional existing AdvancedSearchSystem to use
    """
    return IntegratedReportGenerator(search_system=search_system)


class IntegratedReportGenerator:
    def __init__(
        self,
        searches_per_section: int = 2,
        search_system=None,
        llm: BaseChatModel | None = None,
        settings_snapshot: Optional[Dict] = None,
    ):
        """
        Args:
            searches_per_section: Number of searches to perform for each
                section in the report.
            search_system: Custom search system to use, otherwise just uses
                the default.
            llm: Custom LLM to use. Required if search_system is not provided.
            settings_snapshot: Optional settings snapshot for configurable values.

        """
        # If search_system is provided, use its LLM; otherwise use the provided LLM
        self._owns_llm = False
        self.settings_snapshot = settings_snapshot
        if search_system:
            self.search_system = search_system
            self.model = llm or search_system.model
        elif llm:
            self.model = llm
            self.search_system = AdvancedSearchSystem(llm=self.model)  # type: ignore[call-arg]
        else:
            # Fallback for backwards compatibility - will only work with auth
            self._owns_llm = True
            self.model = get_llm()
            self.search_system = AdvancedSearchSystem(llm=self.model)  # type: ignore[call-arg]

        self.searches_per_section = (
            searches_per_section  # Control search depth per section
        )

        # Load context settings from snapshot or use defaults
        self.max_context_sections = get_setting_from_snapshot(
            "report.max_context_sections",
            default=DEFAULT_MAX_CONTEXT_SECTIONS,
            settings_snapshot=settings_snapshot,
        )
        self.max_context_chars = get_setting_from_snapshot(
            "report.max_context_chars",
            default=DEFAULT_MAX_CONTEXT_CHARS,
            settings_snapshot=settings_snapshot,
        )

    def close(self) -> None:
        """Close the LLM client if this instance created it."""
        from .utilities.resource_utils import safe_close

        if self._owns_llm:
            safe_close(self.model, "report generator LLM")

    def generate_report(
        self,
        initial_findings: Dict,
        query: str,
        progress_callback=None,
    ) -> Dict:
        """Generate a complete research report with section-specific research.

        Args:
            initial_findings: Results from initial research phase.
            query: Original user query.
            progress_callback: Optional callable(message, progress_percent, metadata)
                for reporting progress (0-100%) and checking cancellation.
        """

        from research_verify.research_spec import format_research_spec, parse_research_spec, report_spec_settings
        from .utilities.type_utils import unwrap_setting
        self._research_spec = parse_research_spec(query, report_spec_settings(
            lambda name, default=None: unwrap_setting(
                (self.settings_snapshot or {}).get(name, default))))
        self._scope_contract = format_research_spec(self._research_spec)

        # Step 1: Determine structure
        if progress_callback:
            progress_callback(
                "Determining report structure",
                0,
                {"phase": "report_structure"},
            )
        structure = self._determine_report_structure(initial_findings, query)

        # Step 2: Research and generate content for each section in one step
        self._incomplete_sections = False
        sections = self._research_and_generate_sections(
            initial_findings,
            structure,
            query,
            progress_callback=progress_callback,
        )

        # Step 3: Format final report
        if progress_callback:
            progress_callback(
                "Formatting final report",
                90,
                {"phase": "report_formatting"},
            )
        report = self._format_final_report(sections, structure, query)
        synthesis_error = None
        if self._incomplete_sections:
            from research_verify.generation import INCOMPLETE_SYNTHESIS_MESSAGE
            synthesis_error = INCOMPLETE_SYNTHESIS_MESSAGE
            report["content"] = f"> **{synthesis_error}**\n\n{report['content']}"
            report["metadata"]["synthesis_error"] = synthesis_error

        if progress_callback:
            progress_callback(
                synthesis_error or "Report complete",
                95 if synthesis_error else 100,
                {"phase": "report_complete"},
            )

        from research_verify.publication import publish_report, collect_publication_sources
        publication = publish_report(
            report["content"],
            collect_publication_sources(
                self.search_system, getattr(self.search_system, "all_links_of_system", [])
            ),
            self.model,
            research_spec=getattr(self, "_research_spec", None),
        )
        report["content"] = publication.content
        report.setdefault("metadata", {}).update(publication.metadata())
        return report

    def _determine_report_structure(
        self, findings: Dict, query: str
    ) -> List[Dict]:
        """Analyze content and determine optimal report structure."""
        combined_content = findings["current_knowledge"]
        scope_contract = getattr(self, "_scope_contract", "")
        prompt = f"""
        Analyze this research content about: {query}

        {scope_contract}

        Content Summary:
        {combined_content[:1000]}... [truncated]

        Determine the most appropriate report structure by:
        1. Analyzing the type of content (technical, business, academic, etc.)
        2. Identifying main themes and logical groupings
        3. Considering the depth and breadth of the research

        Return only a JSON object with an ordered "sections" list. Each section
        has a non-empty "name" and a "subsections" list. Each subsection has a
        "name" and a "purpose". Empty subsection lists are allowed. Example:
        {{"sections": [{{"name": "Findings", "subsections": [
            {{"name": "Results", "purpose": "Compare the observed outcomes"}}
        ]}}]}}
        Supply titles without display numbering.

        Make the structure specific to the content, not generic.
        DO NOT include sections about sources, citations, references, or methodology.
        {"For field extraction, prefer one compact section with the requested fields and avoid background discussion or a broad review." if getattr(getattr(self, "_research_spec", None), "output_mode", "") == "field_extraction" else ""}
        """

        from research_verify.structured_output import object_reply

        try:
            sections = object_reply(get_llm_response_text(self.model.invoke(prompt))).get("sections")
            if not isinstance(sections, list) or not sections:
                raise ValueError("outline requires at least one section")
            for section in sections:
                if not isinstance(section, dict) or not isinstance(section.get("name"), str) or not section["name"].strip():
                    raise ValueError("outline section requires a name")
                if not isinstance(section.get("subsections"), list):
                    raise ValueError("subsections must be a list")
                for child in section["subsections"]:
                    if not isinstance(child, dict) or any(
                        not isinstance(child.get(key), str) or not child[key].strip()
                        for key in ("name", "purpose")
                    ):
                        raise ValueError("outline subsection requires a name and purpose")
        except ValueError as error:
            logger.warning("Using generic report outline: {}", error)
            return [{"name": "Findings", "subsections": []}]
        return sections

    def _truncate_at_sentence_boundary(self, text: str, max_chars: int) -> str:
        """Truncate text at a sentence boundary to preserve readability.

        Attempts to cut at the last sentence-ending punctuation (.!?) before
        the limit. If no suitable boundary is found within 80% of the limit,
        falls back to hard truncation.

        Args:
            text: Text to truncate.
            max_chars: Maximum characters allowed.

        Returns:
            Truncated text with ``[...truncated]`` marker if truncation
            occurred, otherwise the original text unchanged.
        """
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]

        # Look for sentence boundaries (. ! ?) followed by space or newline
        # Search backwards from the end for the last complete sentence
        last_sentence_end = -1
        for i in range(len(truncated) - 1, -1, -1):
            if truncated[i] in ".!?" and (
                i + 1 >= len(truncated) or truncated[i + 1] in " \n"
            ):
                last_sentence_end = i + 1
                break

        # Only use sentence boundary if it preserves at least 80% of content
        min_acceptable = int(max_chars * 0.8)
        if last_sentence_end > min_acceptable:
            return truncated[:last_sentence_end] + "\n[...truncated]"

        # Fall back to hard truncation
        return truncated + "\n[...truncated]"

    def _strip_subsection_boilerplate(self, content: str, subsection_name: str) -> str:
        """Remove an exact repeated heading and explicitly formatted bibliography."""
        from research_verify.report_syntax import layout

        blocks, bibliography = layout(content, require_entries=True)
        if blocks and blocks[0].kind == "heading_candidate":
            heading = blocks[0]
            if (not content[:heading.start].strip()
                and content[heading.start:heading.end].strip().lstrip("# ").strip() == subsection_name):
                content = content[:heading.start] + content[heading.end:]
                bibliography = layout(content, require_entries=True)[1]
        for section in reversed(bibliography):
            content = content[:section.start] + content[section.end:]
        return content.strip()

    def _build_previous_context(self, accumulated_findings: List[str]) -> str:
        """Build context block from previously generated sections.

        Creates a formatted context block containing content from the last
        N sections (defined by self.max_context_sections) with explicit instructions
        not to repeat this content. Context is truncated if it exceeds
        self.max_context_chars to stay safe for smaller local models.

        Args:
            accumulated_findings: List of previously generated section content,
                each formatted as "[Section > Subsection]\\n{content}"

        Returns:
            Formatted context block with delimiters, or empty string if no
            previous findings exist
        """
        if not accumulated_findings:
            return ""

        recent_findings = accumulated_findings[-self.max_context_sections :]
        previous_context = "\n\n---\n\n".join(recent_findings)

        # Truncate at sentence boundary if too long
        if len(previous_context) > self.max_context_chars:
            previous_context = self._truncate_at_sentence_boundary(
                previous_context, self.max_context_chars
            )

        return (
            f"\n\n=== CONTENT ALREADY WRITTEN (DO NOT REPEAT) ===\n"
            f"{previous_context}\n"
            f"=== END OF PREVIOUS CONTENT ===\n\n"
            f"CRITICAL: The above content has already been written. Do NOT repeat "
            f"these points, examples, or explanations. Focus on NEW information "
            f"not covered above. Preserve study populations, conditions and other "
            f"necessary qualifiers even when earlier sections mentioned them.\n"
        )

    def _research_and_generate_sections(
        self,
        initial_findings: Dict,
        structure: List[Dict],
        query: str,
        progress_callback=None,
    ) -> Dict[str, str]:
        """Research and generate content for each section in one step.

        This method processes sections sequentially, accumulating generated
        content as it goes. For each new section/subsection, it passes context
        from the last few previously generated sections to help the LLM avoid
        repetition.

        The context accumulation mechanism:
        - Tracks all generated content in accumulated_findings list
        - Before generating each section, builds context from recent findings
        - Uses self.max_context_sections (configurable, default: 3) to limit context size
        - Truncates context to self.max_context_chars (configurable, default: 4000) for safety
        - Includes explicit "DO NOT REPEAT" instructions with actual content

        Args:
            initial_findings: Results from initial research phase, may contain
                questions_by_iteration to preserve search continuity
            structure: List of section definitions, each with name and subsections
            query: Original user query for context

        Returns:
            Dict mapping section names to their generated markdown content
        """
        sections = {}

        # Accumulate content from previous sections to avoid repetition
        accumulated_findings: List[str] = []

        scope_contract = getattr(self, "_scope_contract", "")
        focused_mode = getattr(getattr(self, "_research_spec", None), "output_mode", "") == "field_extraction"

        # Count total subsections for progress tracking
        total_subsections = sum(
            max(len(section.get("subsections", [])), 1) for section in structure
        )
        completed_subsections = 0
        try:
            total_report_timeout = float(
                os.getenv("LDR_REPORT_TOTAL_TIMEOUT_SECONDS", "900")
            )
        except (TypeError, ValueError):
            total_report_timeout = 900.0
        report_deadline = (
            time.monotonic() + total_report_timeout
            if total_report_timeout > 0
            else None
        )
        stop_report_research = False

        # Preserve questions from initial research to avoid repetition
        # This follows the same pattern as citation tracking (all_links_of_system)
        existing_questions = initial_findings.get("questions_by_iteration", {})
        if existing_questions:
            # Set questions on both search system and its strategy
            if hasattr(self.search_system, "questions_by_iteration"):
                self.search_system.questions_by_iteration = (
                    existing_questions.copy()
                )

            # More importantly, set it on the strategy which actually uses it
            if hasattr(self.search_system, "strategy") and hasattr(
                self.search_system.strategy, "questions_by_iteration"
            ):
                self.search_system.strategy.questions_by_iteration = (
                    existing_questions.copy()
                )
                logger.info(
                    f"Initialized strategy with {len(existing_questions)} iterations of previous questions"
                )

        for i, section in enumerate(structure, 1):
            if report_deadline is not None and time.monotonic() >= report_deadline:
                self._incomplete_sections = True
                logger.warning(
                    "Report generation total time limit reached before section %s; "
                    "finalizing partial report",
                    section.get("name", i),
                )
                if progress_callback:
                    progress_callback(
                        "Report generation time limit reached; finalizing partial report",
                        95,
                        {"phase": "report_section_research_timeout"},
                    )
                break
            logger.info(f"Processing section: {section['name']}")
            section_content = []

            section_content.append(f"# {i}. {section['name']}\n")

            subsections = section["subsections"] or [{
                "name": section["name"],
                "purpose": f"Cover {section['name']}",
            }]

            # Process each subsection by directly researching it
            for j, subsection in enumerate(subsections, 1):
                if report_deadline is not None and time.monotonic() >= report_deadline:
                    logger.warning(
                        "Report generation total time limit reached during %s > %s; "
                        "finalizing partial report",
                        section.get("name", i),
                        subsection.get("name", j),
                    )
                    self._incomplete_sections = True
                    stop_report_research = True
                    break
                # Only add subsection header if there are multiple subsections
                if len(subsections) > 1:
                    section_content.append(f"## {i}.{j} {subsection['name']}\n")
                    section_content.append(f"_{subsection['purpose']}_\n\n")

                # Get other subsections in this section for context
                other_subsections = [
                    f"- {s['name']}: {s['purpose']}"
                    for s in subsections
                    if s["name"] != subsection["name"]
                ]
                other_subsections_text = (
                    "\n".join(other_subsections)
                    if other_subsections
                    else "None"
                )

                # Get all other sections for broader context
                other_sections = [
                    f"- {s['name']}"
                    for s in structure
                    if s["name"] != section["name"]
                ]
                other_sections_text = (
                    "\n".join(other_sections) if other_sections else "None"
                )

                # Check if this is actually a section-level content (only one subsection, likely auto-created)
                is_section_level = len(subsections) == 1

                # Build context from previously generated sections to avoid repetition
                previous_context_section = self._build_previous_context(
                    accumulated_findings
                )

                # Generate appropriate search query
                if is_section_level:
                    # Section-level prompt - more comprehensive
                    subsection_query = (
                        f"Research task: Create {'focused field-by-field' if focused_mode else 'concise evidence-grounded'} content for the '{subsection['name']}' section in a report about '{query}'. "
                        f"Section purpose: {subsection['purpose']} "
                        f"\n{scope_contract}\n"
                        f"\n"
                        f"Other sections in the report:\n{other_sections_text}\n"
                        f"{previous_context_section}"
                        f"Keep the scope limited to the requested fields and supplied evidence. "
                        f"Use synthesis only where the supplied sources support it. "
                        f"Use retrieved evidence for examples and numbers; add detail only "
                        f"when the supplied sources support it. Label your interpretation "
                        f"separately from reported study findings. "
                        f"Use tables to organize information where applicable. "
                        f"For conclusion sections: synthesize key findings and explicitly label "
                        f"forward-looking interpretation; do not invent additional study results. "
                        f"Build upon the research findings from earlier sections to create a cohesive narrative."
                        f"{_SUBSECTION_OUTPUT_GUIDANCE}"
                    )
                else:
                    # Subsection-level prompt - more focused
                    subsection_query = (
                        f"Research task: Create content for subsection '{subsection['name']}' in a report about '{query}'. "
                        f"This subsection's purpose: {subsection['purpose']} "
                        f"\n{scope_contract}\n"
                        f"Part of section: '{section['name']}' "
                        f"\n"
                        f"Other sections in the report:\n{other_sections_text}\n"
                        f"\n"
                        f"Other subsections in this section will cover:\n{other_subsections_text}\n"
                        f"{previous_context_section}"
                        f"Focus ONLY on information specific to your subsection's purpose. "
                        f"Use retrieved evidence for details, examples and numbers. Do not "
                        f"fill missing abstract details from memory; distinguish interpretation "
                        f"from reported findings. "
                        f"Use tables to organize information where applicable. "
                        f"IMPORTANT: Avoid repeating information that would logically be covered in other sections - focus on what makes this subsection unique. "
                        f"Previous research exists - find specific angles for this subsection."
                        f"{_SUBSECTION_OUTPUT_GUIDANCE}"
                    )

                logger.info(
                    f"Researching subsection: {subsection['name']} with query: {subsection_query}"
                )

                # Report progress and check for cancellation
                if progress_callback:
                    pct = int(
                        10
                        + (completed_subsections / max(total_subsections, 1))
                        * 80
                    )
                    progress_callback(
                        f"Researching: {section['name']} > {subsection['name']}",
                        pct,
                        {
                            "phase": "report_section_research",
                            "subsection": subsection["name"],
                        },
                    )

                # Fix iteration override: modify strategy's settings_snapshot
                # which is read dynamically via get_setting()
                strategy = self.search_system.strategy
                original_iterations = strategy.settings_snapshot.get(
                    "search.iterations"
                )
                had_iterations_key = (
                    "search.iterations" in strategy.settings_snapshot
                )
                strategy.settings_snapshot["search.iterations"] = 1
                # Belt-and-suspenders: also override max_iterations for
                # strategies that cache it at __init__ time
                original_max_iter = getattr(strategy, "max_iterations", None)
                original_short_run = getattr(strategy, "_allow_short_runs", False)
                original_deadline = getattr(strategy, "_run_deadline", None)
                strategy.max_iterations = 1
                strategy._allow_short_runs = True
                try:
                    subsection_timeout = float(
                        os.getenv("LDR_REPORT_SUBSECTION_TIMEOUT_SECONDS", "300")
                    )
                except (TypeError, ValueError):
                    subsection_timeout = 300.0
                subsection_deadline = time.monotonic() + subsection_timeout if subsection_timeout > 0 else None
                deadlines = [value for value in (subsection_deadline, report_deadline) if value is not None]
                strategy._run_deadline = min(deadlines, default=None)

                try:
                    # Perform search for this subsection
                    subsection_results = self.search_system.analyze_topic(
                        subsection_query
                    )
                finally:
                    # Restore original iteration settings
                    if had_iterations_key:
                        strategy.settings_snapshot["search.iterations"] = (
                            original_iterations
                        )
                    else:
                        strategy.settings_snapshot.pop(
                            "search.iterations", None
                        )
                    if original_max_iter is not None:
                        strategy.max_iterations = original_max_iter
                    strategy._allow_short_runs = original_short_run
                    strategy._run_deadline = original_deadline

                completed_subsections += 1
                if subsection_results.get("synthesis_error") or subsection_results.get("error"):
                    self._incomplete_sections = True

                # Add the researched content for this subsection
                if subsection_results.get("current_knowledge"):
                    generated_content = self._strip_subsection_boilerplate(
                        subsection_results["current_knowledge"], subsection["name"]
                    )
                    if generated_content:
                        section_content.append(generated_content + "\n")
                        # Accumulate for context in subsequent sections
                        accumulated_findings.append(
                            f"[{section['name']} > {subsection['name']}]\n{generated_content}"
                        )
                    else:
                        section_content.append(
                            "*Limited information was found for this subsection.*\n"
                        )
                else:
                    section_content.append(
                        "*Limited information was found for this subsection.*\n"
                    )

                section_content.append("\n\n")

            if stop_report_research:
                break

            # Combine all content for this section
            sections[section["name"]] = "\n".join(section_content)

        return sections

    def _format_final_report(
        self,
        sections: Dict[str, str],
        structure: List[Dict],
        query: str,
    ) -> Dict:
        """Format the final report with table of contents and sections."""
        # Generate TOC
        toc = ["# Table of Contents\n"]
        for i, section in enumerate(structure, 1):
            toc.append(f"{i}. **{section['name']}**")
            if len(section["subsections"]) > 1:
                for j, subsection in enumerate(section["subsections"], 1):
                    toc.append(
                        f"   {i}.{j} {subsection['name']} | _{subsection['purpose']}_"
                    )

        # Combine TOC and sections
        report_parts = ["\n".join(toc), ""]

        # Add a summary of the research.  Field-extraction requests need a
        # compact scope marker; generic boilerplate makes them look like a
        # broad review and competes with the requested fields.
        report_parts.append("# Research Summary")
        if getattr(getattr(self, "_research_spec", None), "output_mode", "") == "field_extraction":
            report_parts.append("The report presents the requested fields where the supplied sources support them.")
        else:
            report_parts.append("This report was researched using an advanced search system.")
            report_parts.append("Research included targeted searches for each section and subsection.")
        report_parts.append("\n---\n")

        # Add each section's content
        for section in structure:
            if section["name"] in sections:
                report_parts.append(sections[section["name"]])
                report_parts.append("")

        # Format links from search system
        # Get utilities module dynamically to avoid circular imports
        utilities = importlib.import_module("local_deep_research.utilities")
        # Imported here for the same reason, and directly rather than off
        # the module object above so the count is computed by the real
        # grouping helper.
        from .utilities.search_utilities import count_distinct_sources

        formatted_all_links = (
            utilities.search_utilities.format_links_to_markdown(
                all_links=self.search_system.all_links_of_system
            )
        )

        # Create final report with all parts. The Sources tail is
        # kept here so in-memory consumers (MCP `generate_report`,
        # programmatic API) get the full assembled blob unchanged.
        # The DB save site (research_service.py) strips this Sources
        # section via format_document_split before persisting, so the
        # answer-only invariant on report_content still holds.
        final_report_content = "\n\n".join(report_parts)
        # Explicit "\n\n" separator: downstream regex consumers
        # (_SOURCES_SECTION_PATTERNS in text_optimization/citation_formatter.py
        # and _LEGACY_SOURCES_RE in web/services/report_assembly_service.py)
        # use line-anchored `re.MULTILINE` matching. Today the trailing
        # newlines produced by `"\n\n".join` happen to keep `## Sources`
        # at the start of a line, but that is incidental; an explicit
        # separator preserves the invariant against future section
        # template changes.
        #
        # The HTML-comment sentinel around the appended `## Sources`
        # block lets ``format_document_split`` locate this section
        # unambiguously, even when the LLM has emitted its own
        # `## Sources` header earlier in the prose. The legacy regex
        # patterns would otherwise match the first `## Sources` they
        # find and could over-strip a multi-section report where the
        # LLM happened to include an inline sources block. Without the
        # sentinel, a 1380-source run legitimately pushes the
        # answer/sources ratio below the 50% safety threshold and the
        # splitter logs a misleading "over-stripped" warning.
        # The sentinel is imported at module top; no circular-import
        # concern at use time.
        final_report_content += (
            f"\n\n{LDR_APPENDED_SOURCES_SENTINEL}\n\n"
            f"## Sources\n\n{formatted_all_links}"
        )

        # Create metadata dictionary
        metadata = {
            "generated_at": datetime.now(UTC).isoformat(),
            # SOURCES, not entries. ``all_links_of_system`` holds one
            # entry per distinct (url, snippet) pair under the LangGraph
            # strategy, and raw un-deduped engine dicts under the others,
            # so its length counts occurrences. This number is reported
            # as "sources", so it must group the way the ## Sources block
            # above does.
            "initial_sources": count_distinct_sources(
                self.search_system.all_links_of_system
            ),
            "sections_researched": len(structure),
            "searches_per_section": self.searches_per_section,
            "query": query,
        }

        # Return both content and metadata
        return {"content": final_report_content, "metadata": metadata}
