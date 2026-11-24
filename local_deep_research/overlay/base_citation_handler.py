"""
Base class for all citation handlers.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

from langchain_core.documents import Document
from loguru import logger
from research_verify.generation import IncompleteSynthesisError, source_material, format_source_documents
from research_verify.synthesis_trace import record_model_response

from ..exceptions import ResearchTerminatedException
from ..utilities.type_utils import unwrap_setting
from ..utilities.json_utils import get_llm_response_text


class BaseCitationHandler(ABC):
    """Abstract base class for citation handlers."""

    def __init__(self, llm, settings_snapshot=None):
        self.llm = llm
        self.settings_snapshot = settings_snapshot or {}
        self._fact_checking_logged = False
        self.stream_callback: Optional[Callable[[str], None]] = None
        self._writer_incomplete = False

    def _check_writer_text(self, response, text) -> None:
        if not text.strip() or getattr(response, "tool_calls", None) or getattr(response, "invalid_tool_calls", None):
            raise IncompleteSynthesisError("Writer returned no report body")
        self._writer_incomplete = self._response_stopped_at_length(response)

    def set_stream_callback(self, callback: Callable[[str], None]):
        """Set a callback that receives each streamed LLM token."""
        self.stream_callback = callback

    def _invoke_with_streaming(self, prompt: str, *, trace=None, stage="writer") -> str:
        """
        Invoke the LLM, streaming tokens through the callback if set.

        Falls back to a single ``invoke()`` call when no callback is
        registered or when the LLM does not support ``.stream()``.

        Returns:
            The complete response text.
        """
        if stage == "writer":
            self._writer_incomplete = False
        if self.stream_callback and hasattr(self.llm, "stream"):
            chunks = []
            last_chunk = None
            finish_chunk = None
            try:
                for chunk in self.llm.stream(prompt):
                    last_chunk = chunk
                    if self._finish_reason(chunk):
                        finish_chunk = chunk
                    text = (
                        chunk
                        if isinstance(chunk, str)
                        else getattr(chunk, "content", str(chunk))
                    )
                    if text:
                        chunks.append(text)
                        try:
                            self.stream_callback(text)
                        except Exception:
                            logger.debug(
                                "stream_callback failed"
                            )  # Non-critical: don't break synthesis
                # Normalize the joined chunks exactly like the invoke() path
                # below: .stream() bypasses ProcessingLLMWrapper.invoke (which
                # is the only place <think> blocks are stripped), so without
                # this a reasoning model's <think>…</think> would leak into the
                # persisted answer. The live token stream is a separate concern.
                raw = "".join(chunks)
                text = get_llm_response_text(raw)
                record_model_response(trace, stage, raw, text, streamed=True, partial=False,
                                      provider_finish_reason=self._finish_reason(finish_chunk or last_chunk))
                if stage == "writer":
                    self._check_writer_text(finish_chunk or last_chunk, text)
                    if self._writer_incomplete and raw.strip() == text:
                        # stream_callback already emitted these boundary characters.
                        text = raw
                    text = self._finish_writer(prompt, text, trace, emit=self.stream_callback)
                return text
            except ResearchTerminatedException:
                raise
            except Exception as exc:
                # If any chunks already crossed the wire to the client,
                # restarting via .invoke() would (a) double-bill the LLM
                # and (b) cause the frontend's accumulated streamed text
                # to diverge from the new full response — the chat bubble
                # then shows partial chunks while the DB row carries the
                # invoke()-result. Only fall back when nothing was emitted.
                if chunks:
                    logger.warning(
                        "Stream errored after {} chunks; returning partial "
                        "content (no invoke() fallback to avoid double-bill "
                        "and UI/DB divergence)",
                        len(chunks),
                    )
                    raw = "".join(chunks)
                    text = get_llm_response_text(raw)
                    record_model_response(trace, stage, raw, text, streamed=True, partial=True,
                                          error_type=type(exc).__name__)
                    if stage == "writer":
                        self._writer_incomplete = True
                    return text
                logger.debug(
                    "Stream failed before any chunk; falling back to invoke()"
                )

        # No callback (non-chat research) or stream unavailable: delegate to
        # the same normalization _invoke_text uses, so <think> blocks
        # are stripped and str/object responses are handled uniformly.
        return self._invoke_text(prompt, trace=trace, stage=stage)

    def _invoke_text(self, prompt: str, *, trace=None, stage="model") -> str:
        """Invoke the LLM and return normalized text.

        Handles both message objects (``.content``) and raw string responses,
        and strips ``<think>`` reasoning blocks via ``get_llm_response_text``.
        """
        if stage == "writer":
            self._writer_incomplete = False
        try:
            response = self.llm.invoke(prompt)
            text = get_llm_response_text(response)
            record_model_response(trace, stage, response, text)
            if ((stage == "native_check" or stage.startswith(("task_coverage", "repair_validation")))
                    and self._response_stopped_at_length(response)):
                from research_verify.generation import ModelOutputTruncated
                raise ModelOutputTruncated(stage)
            # Reasoning models can exhaust the completion budget before emitting
            # any answer text.  A structured consumer (source selection, native
            # review, repair validation) can report a JSON error even though the
            # transport succeeded. Retry only for an explicit provider length
            # stop. This is a transport/runtime recovery seam: it adds no prompt
            # rules, does not rewrite reports, and preserves the first response
            # in the trace for diagnosis.
            structured_length_stop = stage in {"source_selection", "source_reading"}
            if ((not str(text or "").strip() or structured_length_stop)
                    and self._response_stopped_at_length(response)
                    and hasattr(self.llm, "bind")):
                retry_tokens = self.get_setting(
                    "citation.empty_response_retry_max_tokens", 12000
                )
                try:
                    retry_tokens = max(1, int(retry_tokens))
                except (TypeError, ValueError):
                    retry_tokens = 12000
                if trace:
                    trace.record("empty_response_retry", {
                        "stage": stage, "max_tokens": retry_tokens,
                        "reason": ("length_stop_without_text"
                                   if not str(text or "").strip()
                                   else "length_stop_structured_response"),
                    })
                try:
                    retry_response = self.llm.bind(max_tokens=retry_tokens).invoke(prompt)
                    retry_text = get_llm_response_text(retry_response)
                    record_model_response(trace, stage + "_retry", retry_response, retry_text,
                                          retry_of=("length_stop_without_text"
                                                    if not str(text or "").strip()
                                                    else "length_stop_structured_response"),
                                          retry_max_tokens=retry_tokens)
                except Exception as retry_exc:
                    if trace:
                        trace.record("empty_response_retry_error", {
                            "stage": stage, "error_type": type(retry_exc).__name__,
                            "max_tokens": retry_tokens,
                        })
                else:
                    response, text = retry_response, retry_text
            if stage == "writer":
                self._check_writer_text(response, text)
                text = self._finish_writer(prompt, text, trace)
            return text
        except Exception as exc:
            if trace:
                trace.record(stage + "_error", {"error_type": type(exc).__name__})
            raise

    def _finish_writer(self, prompt, text, trace, *, emit=None):
        """Resume only provider-declared length stops at a checked text boundary."""
        for attempt in range(1, 3):
            if not self._writer_incomplete:
                break
            anchor = text.rstrip()[-80:].lstrip()
            if not anchor:
                break
            request = (
                f"{prompt}\n\nContinue the same report using the original source IDs and evidence. "
                "The earlier output hit the output limit. Begin by copying the final anchor "
                "verbatim, then immediately finish the interrupted text and remaining report. "
                "Do not restart the answer.\nEnd of prior output:\n"
                f"{text[-4000:]}\nExact anchor to repeat:\n{anchor}"
            )
            try:
                response = self.llm.invoke(request)
                continuation = get_llm_response_text(response)
                record_model_response(trace, "writer_continuation", response, continuation, attempt=attempt)
            except ResearchTerminatedException:
                raise
            except Exception as exc:
                if trace:
                    trace.record("writer_continuation_error", {"attempt": attempt, "error_type": type(exc).__name__})
                break
            if (not continuation.startswith(anchor) or not continuation[len(anchor):].strip()
                    or getattr(response, "tool_calls", None) or getattr(response, "invalid_tool_calls", None)):
                if trace:
                    trace.record("writer_continuation_unjoined", {"attempt": attempt})
                break
            reason = self._finish_reason(response)
            length_stop = self._response_stopped_at_length(response)
            if not length_stop and reason not in {"stop", "end_turn", "stop_sequence", "eos", "completed"}:
                if trace:
                    trace.record("writer_continuation_unconfirmed", {"attempt": attempt, "finish_reason": reason})
                break
            suffix = continuation[len(anchor):]
            emitted_whitespace = text[len(text.rstrip()):]
            if emitted_whitespace and suffix.startswith(emitted_whitespace):
                suffix = suffix[len(emitted_whitespace):]
            text += suffix
            self._writer_incomplete = length_stop
            if emit:
                try:
                    emit(suffix)
                except Exception:
                    logger.debug("stream_callback failed")
        return text

    @staticmethod
    def _finish_reason(response):
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("token_usage") or {}
        return str(metadata.get("finish_reason") or metadata.get("stop_reason")
                   or usage.get("finish_reason") or "").lower()

    @classmethod
    def _response_stopped_at_length(cls, response) -> bool:
        return cls._finish_reason(response) in {"length", "max_tokens", "max_output_tokens"}

    def get_setting(self, key: str, default=None):
        """Get a setting value from the snapshot."""
        if key in self.settings_snapshot:
            return unwrap_setting(self.settings_snapshot[key])
        return default

    def is_fact_checking_enabled(self) -> bool:
        """Check if fact-checking is enabled and log the state once."""
        enabled = self.get_setting("general.enable_fact_checking", False)
        if not self._fact_checking_logged:
            handler_name = type(self).__name__
            if enabled:
                logger.info(
                    f"[{handler_name}] Fact-checking is ENABLED — "
                    f"extra LLM call per synthesis"
                )
            else:
                logger.info(f"[{handler_name}] Fact-checking is DISABLED")
            self._fact_checking_logged = True
        return bool(enabled)

    def _get_output_instruction_prefix(self) -> str:
        """
        Get formatted output instructions from settings if present.

        This allows users to customize output language, tone, style, and formatting
        for research answers and reports. Instructions are prepended to prompts
        sent to the LLM.

        Returns:
            str: Formatted instruction prefix if custom instructions are set,
                 empty string otherwise.

        Examples:
            - "Respond in Spanish with formal academic tone"
            - "Use simple language suitable for beginners"
            - "Be concise with bullet points"
        """
        output_instructions = self.get_setting(
            "general.output_instructions", ""
        ).strip()

        if output_instructions:
            return f"User-Specified Output Style: {output_instructions}\n\n"
        return ""

    def _create_documents(
        self, search_results: Union[str, List[Dict]], nr_of_links: int = 0
    ) -> List[Document]:
        """
        Convert search results to LangChain documents format and add index
        to original search results.
        """
        documents: List[Document] = []
        if isinstance(search_results, str):
            return documents

        from research_verify.source_relations import associated_notices
        from research_verify.evidence_cards import additional_source_metadata
        for i, result in enumerate(search_results):
            if isinstance(result, dict) and "index" not in result:
                result["index"] = str(i + nr_of_links + 1)
        notices = associated_notices(search_results)

        for i, result in enumerate(search_results):
            if isinstance(result, dict):
                # Add index to the original search result dictionary if it doesn't exist
                # This preserves indices that were already set (e.g., for topic organization)
                if "index" not in result:
                    result["index"] = str(i + nr_of_links + 1)

                content, evidence_type = source_material(result)
                from research_verify.source_identity import classify_source
                provenance = classify_source(result)
                # Use the index from the result if it exists, otherwise calculate it
                doc_index = int(result.get("index", i + nr_of_links + 1))
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": result.get("link", f"source_{i + 1}"),
                            "title": result.get("title", f"Source {i + 1}"),
                            "_search_query": result.get("_search_query"),
                            "_screened_task": result.get("_screened_task"),
                            "index": doc_index,
                            "evidence_type": evidence_type,
                            "abstract": result.get("abstract"),
                            "doi": result.get("doi"),
                            "pmid": result.get("pmid"),
                            "journal": result.get("journal") or result.get("journal_ref"),
                            "authors": result.get("authors") or result.get("authorString") or result.get("author_string"),
                            "publication_date": result.get("pubdate") or result.get("publication_date") or result.get("year"),
                            "language": result.get("language") or result.get("languages") or result.get("lang"),
                            "platform": result.get("platform"),
                            "technology": result.get("technology"),
                            "population": result.get("population"),
                            "sample_size": result.get("sample_size"),
                            "groups": result.get("groups"),
                            "outcome": result.get("outcome"),
                            "impact_factor": result.get("impact_factor"),
                            "metric_year": result.get("metric_year"),
                            "passes_threshold": result.get("passes_threshold"),
                            "_jcr_check": result.get("_jcr_check"),
                            "_jcr_checks": result.get("_jcr_checks"),
                            "_evidence_passages": result.get("_evidence_passages"),
                            "_body_acquisition": result.get("_body_acquisition"),
                            "jcr_provenance": result.get("jcr_provenance"),
                            "additional_source_metadata": additional_source_metadata(result),
                            "related_notices": notices.get(str(doc_index), []),
                            "publication_types": result.get("publication_types", []),
                            "related_articles": result.get("related_articles", []),
                            "publication_versions": result.get("publication_versions", []),
                            "version_resolution": result.get("version_resolution", ""),
                            "authority_status": result.get("authority_status", ""),
                            "source_kind": provenance.get("source_kind", "unknown"),
                            "document_type": provenance.get("document_type", "unknown"),
                            "publication_status": provenance.get("publication_status", "unverified"),
                            "identity_status": provenance.get("identity_status", "candidate"),
                            "identity_provenance": provenance.get("identity_provenance", {}),
                            "publication_status_reason": provenance.get("publication_status_reason", ""),
                            "publication_state": provenance.get("publication_state", "unknown"),
                            "peer_review_status": provenance.get("peer_review_status", "unknown"),
                            "peer_review_status_provenance": provenance.get("peer_review_status_provenance", {}),
                            "relevance_status": provenance.get("relevance_status", "unknown"),
                            "evidence_scope": provenance.get("evidence_scope", "unknown"),
                            "temporal_validity": provenance.get("temporal_validity", "unknown"),
                            "contradiction_status": provenance.get("contradiction_status", "unknown"),
                            "identity_status": provenance.get("identity_status", "missing"),
                        },
                    )
                )
        return documents

    def _format_sources(self, documents: List[Document], query: str = "", *, trace=None, required_ids=()) -> str:
        """Format sources with numbers for citation."""
        return format_source_documents(
            documents, query,
            selector=lambda prompt: self._invoke_text(prompt, trace=trace, stage="source_selection"),
            trace=trace,
            required_ids=required_ids,
        )

    def _no_sources_response(self, question: str) -> Dict[str, Any]:
        """
        Explicit no-sources result returned instead of invoking the LLM.

        Prompting the LLM to "answer with citations [1], [2]…" while the
        sources section is empty makes it fall back on its training data
        and fabricate references. Handlers call this to refuse synthesis
        instead.
        """
        logger.warning(
            f"[{type(self).__name__}] No sources available for synthesis of "
            f"'{question[:100]}' — skipping LLM call to avoid fabricated "
            f"citations"
        )
        content = (
            "No sources were found for this question. The selected search "
            "engines or document collections returned no results; this can "
            "also happen when a search fails with an error (check the "
            "research logs). No answer was generated because, without "
            "sources, it would have to rely on the language model's "
            "built-in knowledge and could contain fabricated citations."
        )
        return {"content": content, "documents": []}

    @abstractmethod
    def analyze_initial(
        self, query: str, search_results: Union[str, List[Dict]]
    ) -> Dict[str, Any]:
        """Process initial analysis with citations."""
        pass

    @abstractmethod
    def analyze_followup(
        self,
        question: str,
        search_results: Union[str, List[Dict]],
        previous_knowledge: str,
        nr_of_links: int,
    ) -> Dict[str, Any]:
        """Process follow-up analysis with citations."""
        pass
