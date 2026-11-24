"""Agent-facing ``fetch_content`` tool builders.

Public API:
    FETCH_MODES         — tuple of valid mode strings.
    build_fetch_tool()  — returns a LangChain ``@tool`` (or ``None`` when
                          mode == "disabled" so the caller can skip
                          registration).

Modes:
    disabled              — fetch tool is not registered with the agent.
    full                  — return the full extracted page text (legacy
                            behavior; can flood small-model context with
                            boilerplate / metadata enrichment).
    summary_focus         — LLM extracts only spans relevant to a focus
                            question the agent supplies per call.
    summary_focus_query   — same as above, but the prompt also includes
                            the original research query (passed in
                            programmatically by the strategy) so the
                            extractor can disambiguate vague focuses.

Each tool registers fetched URLs in the strategy's
``SearchResultsCollector`` for citation tracking, returning the result as
``[N] Title: ...\\nURL: ...\\n\\n<body>`` exactly like the original
in-strategy implementation, so downstream prompt formatting is unchanged.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from loguru import logger
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.generation import page_excerpts
from research_verify.semantic_evidence import semantic_passages
from research_verify.source_identity import identity_fields

from local_deep_research.utilities.js_rendering import (
    read_js_rendering_setting as _read_js_rendering_setting,
)
from local_deep_research.security import (
    redact_url_for_log,
    sanitize_error_for_client,
)

from .library_resolver import (
    is_citation_reference,
    make_library_resolver,
    resolve_citation_reference as _resolve_citation_reference,
)
from .prompts import SUMMARY_FOCUS_PROMPT, SUMMARY_FOCUS_QUERY_PROMPT


# Per-call timeouts and caps. Kept here rather than in the strategy file
# because they are properties of the fetch tool, not of agent
# orchestration.
CONTENT_FETCH_TIMEOUT = 30
CONTENT_MAX_LENGTH = 500_000

# Cap for credential-scrubbed fetch-tool error strings. Larger than the
# 200-char HTTP-client default because these errors feed the agent's
# reasoning; credential scrubbing still runs first on the full string (#4633).
_TOOL_ERROR_MAX_LEN = 500


def _scrub_tool_error(message: str) -> str:
    """Scrub credentials from an LLM/agent-facing fetch-tool error string."""
    return sanitize_error_for_client(message, max_length=_TOOL_ERROR_MAX_LEN)


FETCH_MODES = (
    "disabled",
    "full",
    "summary_focus",
    "summary_focus_query",
)


def _register_in_collector(
    collector: Any,
    url: str,
    title: str,
    snippet_source: str,
    raw_content: str | None = None,
    evidence: list | None = None,
    status: str | None = None,
    **identity,
) -> int:
    """Register a fetched URL in the collector and return its 1-based citation index.

    If the URL was already tracked (via a prior search hit) the existing
    index is reused so the agent sees a stable citation per URL.

    .. note::
        The ``find_or_add_result``-less branch below is **speculative
        generality**: ``SearchResultsCollector`` is the only collector in
        this repo and it has that method, so nothing in-tree reaches the
        fallback and no test exercises it against a real collector. It
        exists for third-party or pre-#5363 collectors. Treat it as
        unverified against any live caller — do not assume a bug there is
        affecting production, and do not grow it further without a real
        consumer to justify it.

        This branch was left at its pre-existing shape deliberately. An
        earlier revision of this follow-up grew it — duck-typed tuple
        unpacking for a bare-``int`` ``add_results`` contract, a ``getattr``
        guard on ``find_by_url`` — for a collector that does not exist in
        any repo we can see, which is precisely what the paragraph above
        forbids. That growth was reverted rather than shipped.
    """
    snippet = snippet_source[:200].strip()
    if len(snippet_source) > 200:
        snippet += "..."
    if not hasattr(collector, "find_or_add_result"):
        # Legacy/custom collectors without find_or_add_result fallback
        _, indexed = collector.add_results(
            [{"title": title, "link": url, "snippet": snippet}],
            engine_name="fetch",
        )
        if indexed:
            raw_idx = indexed[0].get("index")
            try:
                return int(raw_idx)
            except (ValueError, TypeError):
                logger.warning(
                    "Failed to parse citation index for url={}: {!r}",
                    redact_url_for_log(url),
                    raw_idx,
                )
        existing_idx = collector.find_by_url(url)
        if existing_idx is not None:
            return existing_idx
        raise RuntimeError(
            f"Failed to register fetched URL in collector: {redact_url_for_log(url)}"
        )

    record = {"title": title, "link": url, "snippet": snippet, **identity}
    if evidence:
        record["_evidence_passages"] = [dict(passage, url=url) for passage in evidence]
    if status:
        record["_body_acquisition"] = status
    if isinstance(raw_content, str) and raw_content.strip():
        # Preserve acquired text separately from the model-produced focus
        # summary. Its completeness/type is not established by ContentFetcher.
        record["fetched_content"] = raw_content
    return collector.find_or_add_result(
        record,
        engine_name="fetch",
    )


def _enforce_url_policy(url: str, egress_context: Any) -> None:
    """Run ``evaluate_url`` against ``egress_context`` and raise
    ``PolicyDeniedError`` on denial.

    No-op when no context is configured (callers without policy enforcement,
    e.g. legacy non-LangGraph strategies, see the legacy behavior).
    """
    if egress_context is None:
        return
    from local_deep_research.security.egress.policy import (
        PolicyDeniedError,
        evaluate_url,
    )

    decision = evaluate_url(url, egress_context)
    if not decision.allowed:
        raise PolicyDeniedError(decision, target=url)


def _denial_reason(exc: Any) -> str:
    """Best-effort egress-denial reason code for an agent-facing message."""
    return getattr(getattr(exc, "decision", None), "reason", "policy_denied")


# Shared instruction appended to every per-URL egress denial returned to the
# agent. Tells it WHY the fetch was refused and what to do instead, so it
# adapts (stays in-scope) rather than retrying the same out-of-scope URL.
_EGRESS_DENIAL_HINT = (
    "In this run only local collection/library documents can be fetched; "
    "skip external URLs."
)

# ---------------------------------------------------------------------------
# Pre-resolution: rewrite non-network URLs BEFORE the egress gate.
#
# Two URL-shaped strings reach the fetch tool that aren't actually network
# fetches and that the egress policy correctly rejects as
# ``unsupported_scheme``. Resolving them here lets the agent get the page
# content (or a helpful error) instead of a generic denial — A3 from
# research_f3045c5b_issue_analysis.md.
# ---------------------------------------------------------------------------

# ``_KIND_RESULT`` marks a pre-resolved local document; the fetch tool
# consumes the dict directly. ``_KIND_ERROR`` short-circuits the fetch
# tool with the message in ``payload`` (already routed through the
# credential scrubber by the caller). ``_KIND_REWRITTEN`` means "this
# URL was rewritten to a new one — use the new URL going forward but
# keep running the normal HTTP flow" (e.g. a ``[N]`` citation marker
# that resolves to an external URL). ``None`` means "no pre-resolution;
# run the normal HTTP path with the original URL."
_KIND_RESULT = "result"
_KIND_ERROR = "error"
_KIND_REWRITTEN = "rewritten"


def _try_resolve_url(
    url: str,
    library_resolver: Any,
    collector: Any,
    _visited: set[str] | None = None,
) -> tuple[str, Any] | None:
    """Pre-resolve a fetch URL that isn't a network URL.

    Returns one of:

    - ``(``_KIND_RESULT``, dict)`` — local-content payload shaped like a
      ``ContentFetcher.fetch()`` success result, ready for the post-fetch
      pipeline. The caller MUST skip the egress gate (it's a local read).
    - ``(``_KIND_ERROR``, str)`` — short-circuit with this error message.
    - ``(``_KIND_REWRITTEN``, str)`` — *url* was rewritten (e.g. a
      citation marker ``[N]`` that resolved to an external URL); use
      the new URL but otherwise run the normal HTTP flow (the egress
      gate still applies).
    - ``None`` — no pre-resolution; run the normal HTTP path with *url*.

    Handles:

    - ``[N]`` citation markers → ``SearchResultsCollector.find_by_index``,
      then recurse with the resolved URL (so a citation whose source is a
      library doc still hits the local fast path, while a citation whose
      source is external surfaces a ``_KIND_REWRITTEN`` URL for the gate).
    - ``/library/document/<uuid>[/pdf]`` → ``Document.text_content`` read
      from the user DB via the library resolver.
    """
    if not isinstance(url, str):
        return None

    if _visited is None:
        _visited = set()
    if url in _visited:
        return (
            _KIND_ERROR,
            f"Circular citation reference detected for '{url}'.",
        )
    if len(_visited) >= 5:
        return (
            _KIND_ERROR,
            f"Citation resolution depth limit exceeded for '{url}'.",
        )
    _visited.add(url)

    # 1. Citation marker [N] → resolve to citation's URL.
    citation = _resolve_citation_reference(url, collector)
    if citation is not None:
        resolved_url = citation.get("link") or citation.get("url") or ""
        if not resolved_url:
            return (
                _KIND_ERROR,
                (
                    f"Citation {url} has no URL field. "
                    "Use the citation's URL or a different source instead."
                ),
            )
        # First, check if the citation's URL is itself a library doc
        # (the recursive call sees the library path and returns _KIND_RESULT
        # directly). Otherwise surface the citation's URL as a rewrite so
        # the fetch tool updates its ``url`` variable before the egress
        # gate / HTTP fetch runs against the resolved URL — not the marker.
        recursive = _try_resolve_url(
            resolved_url, library_resolver, collector, _visited=_visited
        )
        if recursive is not None:
            return recursive
        return (_KIND_REWRITTEN, resolved_url)

    # 2. Citation marker that doesn't match a tracked citation.
    # ``_resolve_citation_reference`` only returns the citation for a
    # well-formed ``[N]`` marker; anything else falls through to the
    # library-resolver check below.
    if is_citation_reference(url) is not None:
        return (
            _KIND_ERROR,
            (
                f"No registered citation matches {url}. The agent's "
                "search results use citation markers; use the source URL "
                "(the link next to the marker) or a tracked citation "
                "instead of a raw marker."
            ),
        )

    # 3. Library document URL.
    if library_resolver is not None:
        content = library_resolver(url)
        if content is not None:
            text = content.get("content") or ""
            if len(text) > CONTENT_MAX_LENGTH:
                text = text[:CONTENT_MAX_LENGTH]
            return (
                _KIND_RESULT,
                {
                    "status": "success",
                    "title": content.get("title") or "",
                    "content": text,
                    "url": content.get("url") or url,
                },
            )

    return None


def _fetch_raw_content(
    url: str,
    library_resolver: Any,
    collector: Any,
    egress_context: Any,
    settings_snapshot: dict | None,
    mode_label: str,
) -> tuple[dict | None, str, str | None]:
    """Pre-resolve non-network URL shapes or fetch via HTTP.

    Returns:
        (result, final_url, error_string)
        If error_string is not None, a pre-resolution error occurred (already
        scrubbed) and should be returned immediately by the fetch tool.
    """
    from local_deep_research.content_fetcher import ContentFetcher

    source = _resolve_citation_reference(url, collector)
    if source is None and hasattr(collector, "find_by_index"):
        index = collector.find_by_url(url)
        if index:
            source = collector.find_by_index(index)
    if source and (identity := identity_fields(source)):
        held = source.get("fetched_content")
        acquisition = source.get("_body_acquisition", "")
        if not held or acquisition in {"full_text_unavailable", ""}:
            client = EvidenceFetcher({**(settings_snapshot or {}),
                                      "_egress_context": egress_context}, seconds=24, requests=6)
            article = client.source_article(source)
            for attempt in client.events:
                logger.info("Article retrieval source={} {}", source.get("index"), attempt)
            updated = {"index": source.get("index"), **identity,
                       "link": source.get("link") or source.get("url"),
                       "title": source.get("title") or "",
                       "_body_acquisition": article["status"] if article else "full_text_unavailable",
                       "_body_attempts": client.events}
            if article:
                updated["fetched_content"] = article["body"]
                updated["_body_url"] = article["url"]
            collector.find_or_add_result(updated, engine_name="fetch")
            held = article["body"] if article else None
        if held:
            return {"status": "success", "content": held, "title": source.get("title"),
                    "identity": identity, "body_status": source.get("_body_acquisition")}, (
                        source.get("_body_url") or source["link"]), None
        if source.get("abstract"):
            return {"status": "success", "content": source["abstract"], "title": source.get("title"),
                    "identity": identity, "body_status": "full_text_unavailable"}, source["link"], None
        return None, url, "Full text could not be verified for this source ID."

    pre = _try_resolve_url(url, library_resolver, collector)
    result: dict | None = None
    if pre is not None:
        kind, payload = pre
        if kind == _KIND_ERROR:
            return None, url, _scrub_tool_error(payload)
        if kind == _KIND_RESULT:
            # A local library document was resolved directly from the user DB.
            # Skip both the egress gate (local read) and ContentFetcher (no HTTP).
            result = payload
            url = result.get("url") or url
            logger.info(
                f"[FETCH] mode={mode_label} source=library url={url} — "
                "resolved local library document directly"
            )
        else:  # _KIND_REWRITTEN — citation marker resolved to a URL
            url = payload

    if result is None:
        if hasattr(collector, "find_by_index"):
            index = collector.find_by_url(url)
            cached = collector.find_by_index(index) if index else None
            if cached and cached.get("fetched_content"):
                return {"status": "success", "content": cached["fetched_content"],
                        "title": cached.get("title")}, url, None
        # Either no pre-resolution or a citation-marker rewrite —
        # run the normal HTTP path. Per-URL egress gate (pre-fetch)
        # + ContentFetcher's own per-redirect gate both raise
        # PolicyDeniedError on an out-of-scope URL. Run the gate
        # INSIDE the try so the denial is returned as a recoverable
        # tool message.
        _enforce_url_policy(url, egress_context)
        enable_js = _read_js_rendering_setting(settings_snapshot)
        with ContentFetcher(
            timeout=CONTENT_FETCH_TIMEOUT,
            enable_js_rendering=enable_js,
            egress_context=egress_context,
        ) as fetcher:
            result = fetcher.fetch(url, max_length=CONTENT_MAX_LENGTH)

    return result, url, None


def _make_full_fetch_tool(
    collector: Any,
    settings_snapshot: dict | None = None,
    egress_context: Any = None,
    library_resolver: Any = None,
    overall_query: str = "",
    model: BaseChatModel | None = None,
):
    mode_label = "full"

    @tool
    def fetch_content(url: str = "", source_id: int | None = None) -> str:
        """Read collected paper by source_id, or acquire a new web page by URL."""
        if source_id is not None:
            url = f"[{source_id}]"
        if not url:
            return "Supply source_id or url."
        from local_deep_research.security.egress.policy import (
            PolicyDeniedError,
        )

        try:
            result, url, err_msg = _fetch_raw_content(
                url,
                library_resolver,
                collector,
                egress_context,
                settings_snapshot,
                mode_label,
            )
            if err_msg is not None:
                return err_msg

            if result.get("status") == "success":
                title = result.get("title", "")
                content = result.get("content", "")
                status = result.get("body_status") or "acquired_text"
                evidence = None
                if model is not None:
                    evidence, selected = semantic_passages(content, overall_query, model.invoke)
                    view = "\n\n".join(passage["text"] for passage in evidence)
                    scope = f"Body availability: {status}. Passage selection: {selected}.\n\n"
                else:
                    view = page_excerpts(content, "")
                    scope = f"Body availability: {status}. Other acquired text is stored.\n\n"
                cite_idx = _register_in_collector(
                    collector, url, title, content,
                    raw_content=content if status != "full_text_unavailable" else None,
                    evidence=evidence, status=status, **(result.get("identity") or {}),
                )
                return f"[{cite_idx}] Title: {title}\nURL: {url}\n\n{scope}{view}"
            # result['error'] comes from ContentFetcher, which returns a
            # raw str(exception) — scrub it (and the url) before this
            # reaches the agent/LLM and user-visible output (#4633).
            return _scrub_tool_error(
                f"Failed to fetch {url}: {result.get('error', 'unknown error')}"
            )
        except PolicyDeniedError as exc:
            # An out-of-scope URL is a RECOVERABLE, per-call decision (the agent
            # picked one bad URL among many). Return it as a tool message — like
            # the transient-error path below — so the lead agent and pooled
            # subagents handle it identically and the agent can adapt, instead
            # of re-raising (which aborts a subagent and depends on each agent's
            # tool-error layer). The URL was already NOT fetched; the policy
            # already enforced — only the REPORTING changes, not security.
            target_url = getattr(exc, "target", "") or url
            return _scrub_tool_error(
                f"Cannot fetch {target_url}: blocked by egress policy "
                f"({_denial_reason(exc)}). {_EGRESS_DENIAL_HINT}"
            )
        except Exception as exc:
            # Message carries the mode + a REDACTED scheme://host only (no
            # userinfo/path/query) so an operator can locate the failure without
            # the log line leaking credentials, query tokens, or page content.
            # The traceback follows the sink's diagnose setting (off by default;
            # see utilities/log_utils). The agent/user-facing return is scrubbed
            # separately below.
            target_url = getattr(exc, "target", "") or url
            logger.exception(
                "fetch_content tool error (mode={}, url={})",
                mode_label,
                redact_url_for_log(target_url),
            )
            return _scrub_tool_error(f"Error fetching {target_url}: {exc}")

    return fetch_content


def _make_summary_fetch_tool(
    collector: Any,
    model: BaseChatModel,
    overall_query: str | None,
    settings_snapshot: dict | None = None,
    egress_context: Any = None,
    library_resolver: Any = None,
):
    """Build the summary-mode fetch tool.

    overall_query=None → focus-only prompt (``summary_focus`` mode).
    overall_query=str  → focus + overall-query prompt (``summary_focus_query``).
    """
    use_query = bool(overall_query)
    template = SUMMARY_FOCUS_QUERY_PROMPT if use_query else SUMMARY_FOCUS_PROMPT

    mode_label = "summary_focus_query" if use_query else "summary_focus"

    @tool
    def fetch_content(url: str = "", focus: str = "", source_id: int | None = None) -> str:
        """Read a known paper by source_id, or a new web page by URL.
        For papers pass the existing numeric ID. Pass the precise evidence gap
        as focus, such as the original experiment groups or a claim to check.
        """
        if source_id is not None:
            url = f"[{source_id}]"
        if not url or not focus:
            return "Supply source_id or url and a specific focus."
        from local_deep_research.security.egress.policy import (
            PolicyDeniedError,
        )

        try:
            result, url, err_msg = _fetch_raw_content(
                url,
                library_resolver,
                collector,
                egress_context,
                settings_snapshot,
                mode_label,
            )
            if err_msg is not None:
                return err_msg

            if result.get("status") != "success":
                # result['error'] comes from ContentFetcher, which returns a
                # raw str(exception) — scrub it (and the url) before this
                # reaches the agent/LLM / user output (#4633).
                return _scrub_tool_error(
                    f"Failed to fetch {url}: "
                    f"{result.get('error', 'unknown error')}"
                )

            title = result.get("title") or ""
            raw_content = result.get("content") or ""
            evidence_query = f"{overall_query or ''}\nSpecific evidence question: {focus}"
            evidence, selection = semantic_passages(raw_content, evidence_query, model.invoke)
            content = "\n\n[... source excerpt boundary ...]\n\n".join(
                passage["text"] for passage in evidence
            )

            # Guard 1 — empty page content (paywalls, JS-only SPAs that
            # static fetch can't render, deleted pages with HTTP 200).
            # Skipping the LLM call here means we don't pay the round-trip
            # to summarise nothing, AND we don't register an empty
            # citation in the collector — `_register_in_collector` caches
            # by URL, so an empty snippet would lock the URL in as
            # "already fetched, nothing here" and the agent would never
            # retry it under a different focus.
            if not content.strip():
                logger.info(
                    f"[FETCH] mode={mode_label} url={url} — "
                    "empty page content, returning NOT RELEVANT without "
                    "LLM call or collector registration"
                )
                return f"NOT RELEVANT (no extractable content at {url})"

            fmt_kwargs = {
                "focus": focus,
                "title": title,
                "url": url,
                "content": content,
            }
            if use_query:
                fmt_kwargs["overall_query"] = overall_query
            prompt = template.format(**fmt_kwargs)

            try:
                summary_msg = model.invoke(prompt)
                summary = getattr(
                    summary_msg, "content", str(summary_msg)
                ).strip()
            except Exception as exc:
                # Redacted scheme://host + mode only — no page content,
                # focus, or credentials in the message. Traceback follows
                # the sink's diagnose setting (off by default).
                logger.exception(
                    "fetch_content summary LLM error (mode={}, url={})",
                    mode_label,
                    redact_url_for_log(url),
                )
                return _scrub_tool_error(f"Error summarizing {url}: {exc}")

            # Diagnostic log: per-fetch input/output for evaluating the
            # summariser. Single multi-line block so it's atomic per call
            # and easy to grep with ``grep -A1000 "[FETCH] mode="``.
            log_lines = [
                f"[FETCH] mode={mode_label} url={url}",
                f"[FETCH] focus: {focus}",
            ]
            if use_query:
                log_lines.append(f"[FETCH] overall_query: {overall_query}")
            log_lines.extend(
                [
                    f"[FETCH] title: {title}",
                    f"[FETCH] acquired_text ({len(raw_content)} chars); model_view ({len(content)} chars); selection={selection}:",
                    content,
                    f"[FETCH] summary returned ({len(summary)} chars):",
                    summary or "(empty)",
                    "[FETCH] ---",
                ]
            )
            logger.info("\n".join(log_lines))

            body_status = result.get("body_status") or "acquired_text"
            cite_idx = _register_in_collector(
                collector, url, title, summary,
                raw_content=raw_content if body_status != "full_text_unavailable" else None,
                evidence=evidence, status=body_status, **(result.get("identity") or {}),
            )
            scope = f"Body availability: {body_status}. Passage selection: {selection}."
            if not summary or summary.upper().startswith("NOT RELEVANT"):
                return (f"[{cite_idx}] {scope} Focus evidence was not located in the supplied "
                        "passages. Paper-wide absence and exclusion are unverified.")
            return f"[{cite_idx}] Title: {title}\nURL: {url}\n{scope}\n\n{summary}"
        except PolicyDeniedError as exc:
            # Recoverable per-URL denial — return a tool message so both the
            # lead agent and pooled subagents handle it identically and the
            # agent stays in-scope. The URL was already NOT fetched; only the
            # reporting changes, not security. (See the full-fetch variant.)
            target_url = getattr(exc, "target", "") or url
            return _scrub_tool_error(
                f"Cannot fetch {target_url}: blocked by egress policy "
                f"({_denial_reason(exc)}). {_EGRESS_DENIAL_HINT}"
            )
        except Exception as exc:
            # Message carries the mode + a REDACTED scheme://host only (no
            # userinfo/path/query) so an operator can locate the failure without
            # the log line leaking credentials, query tokens, or page content.
            # The traceback follows the sink's diagnose setting (off by default;
            # see utilities/log_utils). The agent/user-facing return is scrubbed
            # separately below.
            target_url = getattr(exc, "target", "") or url
            logger.exception(
                "fetch_content tool error (mode={}, url={})",
                mode_label,
                redact_url_for_log(target_url),
            )
            return _scrub_tool_error(f"Error fetching {target_url}: {exc}")

    return fetch_content


def build_fetch_tool(
    mode: str,
    collector: Any,
    *,
    model: BaseChatModel | None = None,
    overall_query: str = "",
    settings_snapshot: dict | None = None,
    egress_context: Any = None,
    library_resolver: Any = None,
):
    """Build the agent-facing ``fetch_content`` tool for *mode*.

    Returns ``None`` when ``mode == 'disabled'``; the caller should not
    register the tool with the agent in that case (and the system prompt
    should also drop the corresponding instruction line so the agent
    isn't told to use a tool that doesn't exist).

    ``settings_snapshot`` is captured by the tool closure so the per-call
    JS-rendering toggle can be read on a worker thread (where
    ``threading.local`` context does not propagate).

    ``egress_context`` is captured by the closure so the per-call URL
    can be policy-gated; when ``None``, no policy enforcement runs
    (preserves legacy non-LangGraph callers).

    ``library_resolver`` is captured by the closure so a fetch call can
    short-circuit on ``/library/document/<uuid>[/pdf]`` URLs (a local DB
    read, not a network fetch) and on bare ``[N]`` citation markers
    (rewritten to the citation's URL via ``SearchResultsCollector``).
    When ``None``, the tool falls through to the egress gate unchanged
    (which, when ``egress_context`` is configured, rejects library / citation
    URLs as ``unsupported_scheme``) — same as the pre-fix behaviour.
    """
    if mode == "disabled":
        return None
    if mode == "full":
        return _make_full_fetch_tool(
            collector,
            settings_snapshot=settings_snapshot,
            egress_context=egress_context,
            library_resolver=library_resolver,
            overall_query=overall_query,
            model=model,
        )
    if mode == "summary_focus":
        if model is None:
            raise ValueError("summary_focus fetch mode requires a model")
        return _make_summary_fetch_tool(
            collector,
            model,
            overall_query=None,
            settings_snapshot=settings_snapshot,
            egress_context=egress_context,
            library_resolver=library_resolver,
        )
    if mode == "summary_focus_query":
        if model is None:
            raise ValueError("summary_focus_query fetch mode requires a model")
        # Empty overall_query falls back to focus-only behaviour at format
        # time; we keep the *_query mode label so logs stay diagnostic.
        return _make_summary_fetch_tool(
            collector,
            model,
            overall_query=overall_query or None,
            settings_snapshot=settings_snapshot,
            egress_context=egress_context,
            library_resolver=library_resolver,
        )
    raise ValueError(
        f"Unknown fetch mode {mode!r}; expected one of {FETCH_MODES}"
    )


__all__ = ["FETCH_MODES", "build_fetch_tool", "make_library_resolver"]
