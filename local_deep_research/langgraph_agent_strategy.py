"""
LangGraph agent-based research strategy with parallel subagent support.

Uses LangChain's create_agent() to build a tool-calling agent that autonomously
decides what to search, when to dig deeper, and when to synthesize. Complex
questions can be decomposed into subtopics researched in parallel by subagents.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from loguru import logger

from ...citation_handler import CitationHandler
from ...security.egress import EngineClassification, classify_engine
from ...security import sanitize_error_for_client
from ...utilities.thread_context import get_search_context, search_context
from ...utilities.url_utils import canonical_url_key
from ...database.thread_local_session import thread_cleanup
from ..tools.fetch import FETCH_MODES, build_fetch_tool, make_library_resolver
from .base_strategy import (
    BaseSearchStrategy,
    CHECK_CONTEXT_AGENT_STREAM,
    CHECK_CONTEXT_ENTRY,
    CHECK_CONTEXT_FALLBACK_SYNTHESIS,
)
from .primary_search_metadata import (
    NEUTRAL_PRIMARY_SEARCH_DESCRIPTION,
    PrimarySourceType,
    classify_primary_source,
    format_primary_search_description,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = (
    50  # agent needs many more cycles than pipeline strategies
)
MIN_ITERATIONS = 10  # below this the agent can barely do anything useful
SUBAGENT_TIMEOUT_SECONDS = 1800  # 30 minutes per subagent, measured from
# each subagent's *actual* start time (not from the drain-loop start, which
# used to make queued subagents inherit the wall-clock of everything that
# ran before them -- see #5014).
# User-facing sentinel for "the agent produced nothing". _finalize must
# not run the accumulated-sources citation pass over it — that would
# dress the failure up as a cited synthesis instead of surfacing it.
NO_RESULTS_MESSAGE = (
    "Research could not produce results. Try a different query."
)
MAX_SUBTOPICS = 5  # preferred batch size; must match the "pass 2-5" contract
# in the lead prompt and research_subtopic tool description. A bounded
# overflow is queued through the existing worker pool instead of discarded.
MAX_SUBTOPICS_HARD_LIMIT = 10  # reject larger batches before starting work
MAX_SUBAGENT_WORKERS = 4  # default pool size when the user has not set
# ``langgraph_agent.max_subagent_workers``. Surplus subtopics queue and
# start as workers free up; each queued subagent keeps its own per-task
# budget from its actual start time.
SUBAGENT_TIMEOUT_OVERALL_MULTIPLIER = 2  # safety cap multiplier: the overall
# drain-loop wall-clock is bounded to ``SUBAGENT_TIMEOUT_SECONDS * multiplier``
# seconds so a pathological hang cannot block the lead forever. This is a
# backstop only -- the per-task deadline above is what actually kills an
# individual subagent. The multiplier is intentionally small (2) because the
# worst case (queued subtopics) is already covered by per-task deadlines; we
# only need the overall cap to bound genuinely deadlocked / hung tasks.
# CONTENT_FETCH_TIMEOUT and CONTENT_MAX_LENGTH live alongside the fetch
# tool builders in advanced_search_system/tools/fetch/.

# Cap for credential-scrubbed tool/agent error strings. Larger than the
# 200-char HTTP-client default of ``sanitize_error_for_client`` because these
# strings feed the agent's reasoning AND the ErrorReporter pattern map, where
# over-aggressive truncation drops the categorizable error signal. Credential
# scrubbing still runs first on the full untruncated string (#4633).
_TOOL_ERROR_MAX_LEN = 500

# Keep a research run bounded.  The previous implementation retained every
# candidate returned by every lead/sub-agent search, which made a detailed
# report's bibliography grow into thousands of entries.  This is a candidate
# budget, not the number of references that must appear in the final answer.
DEFAULT_MAX_UNIQUE_SOURCES = 500

# Preprint repositories are useful for discovery, but are not suitable as the
# default evidence set for a bioinformatics service.  Blocking their pages at
# collection time also prevents repeated arXiv API calls from sub-agents.
PREPRINT_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "biorxiv.org",
    "www.biorxiv.org",
    "medrxiv.org",
    "www.medrxiv.org",
    "ssrn.com",
    "www.ssrn.com",
    "researchsquare.com",
    "www.researchsquare.com",
}


def _scrub_tool_error(message: str) -> str:
    """Scrub credentials from an LLM/agent-facing tool error string."""
    return sanitize_error_for_client(message, max_length=_TOOL_ERROR_MAX_LEN)


# ---------------------------------------------------------------------------
# Thread-safe search result collector
# ---------------------------------------------------------------------------


class SearchResultsCollector:
    """Accumulates search results from the lead agent and subagents.

    Thread-safe: multiple subagent threads may call ``add_results``
    concurrently.  The ``_all_links`` reference points to the strategy's
    shared ``all_links_of_system`` list and is never reassigned.
    """

    def __init__(
        self,
        all_links: list | None = None,
        max_results: int = DEFAULT_MAX_UNIQUE_SOURCES,
    ) -> None:
        self._results: list[dict] = []
        self._sources: list[str] = []
        self._lock = threading.Lock()
        self._all_links = all_links if all_links is not None else []
        self._max_results = max(10, int(max_results))
        self._identity_map: dict[str, dict] = {}
        for tracked in self._all_links:
            if isinstance(tracked, dict):
                for key in self._identity_keys(tracked):
                    self._identity_map.setdefault(key, tracked)

    @staticmethod
    def _is_preprint_url(result: dict) -> bool:
        url = str(result.get("link", result.get("url", "")) or "").strip()
        if not url:
            return False
        try:
            host = (urlparse(url).hostname or "").lower().rstrip(".")
        except ValueError:
            return False
        return host in PREPRINT_HOSTS or any(
            host.endswith("." + suffix) for suffix in PREPRINT_HOSTS
        )

    @staticmethod
    def _identity_keys(result: dict) -> list[str]:
        """Return stable identifiers for exact and cross-engine duplicates."""
        keys: list[str] = []

        doi = str(result.get("doi") or "").strip().lower()
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
        if doi:
            keys.append(f"doi:{doi}")

        for field in ("pmid", "pmcid", "arxiv_id"):
            value = str(result.get(field) or "").strip().lower()
            if value:
                if field == "arxiv_id":
                    value = re.sub(r"v\d+$", "", value)
                keys.append(f"{field}:{value}")

        url = str(result.get("link", result.get("url", "")) or "").strip()
        if url:
            keys.append(f"url:{canonical_url_key(url)}")

        # Exact normalized-title matching catches the same paper returned by
        # PubMed, PMC, a DOI resolver, and the publisher when IDs are absent.
        title = str(result.get("title") or result.get("name") or "").casefold()
        title = re.sub(r"[^\w]+", " ", title, flags=re.UNICODE).strip()
        if len(title) >= 30:
            year = str(
                result.get("year")
                or result.get("published")
                or result.get("publication_date")
                or ""
            )[:4]
            keys.append(f"title:{title}|{year}")

        return keys

    def _find_duplicate(self, result: dict) -> dict | None:
        for key in self._identity_keys(result):
            existing = self._identity_map.get(key)
            if existing is not None:
                return existing
        return None

    def _merge_duplicate(self, existing: dict, incoming: dict) -> None:
        """Keep richer metadata while preserving the original citation index."""
        raw = incoming.get("raw_content")
        previous_raw = existing.get("raw_content")
        if isinstance(raw, str) and (
            not isinstance(previous_raw, str) or len(raw) > len(previous_raw)
        ):
            existing["raw_content"] = raw
            existing["raw_content_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            if incoming.get("_fetched_evidence"):
                existing["_fetched_evidence"] = incoming["_fetched_evidence"]
        for field, value in incoming.items():
            value_is_empty = value is None or (
                isinstance(value, (str, list, tuple, dict, set)) and not value
            )
            if field in {"index", "link", "url", "source_engine", "raw_content", "raw_content_sha256", "_fetched_evidence"} or value_is_empty:
                continue
            current = existing.get(field)
            current_is_empty = current is None or (
                isinstance(current, (str, list, tuple, dict, set)) and not current
            )
            if current_is_empty or (
                isinstance(value, str)
                and isinstance(current, str)
                and field in {"snippet", "body", "abstract", "full_content"}
                and len(value) > len(current)
            ):
                existing[field] = value

        for key in self._identity_keys(incoming) + self._identity_keys(existing):
            self._identity_map[key] = existing

    # -- public API ----------------------------------------------------------

    def add_results(
        self,
        results: list[dict],
        engine_name: str = "web",
    ) -> int:
        """Deduplicate and index *results*, then append them internally.

        Also appends results to shared ``all_links_of_system`` and returns the
        starting citation index
        (0-based) assigned to the first result in this batch.

        The entire operation runs under a single lock acquisition so that
        citation indices are never duplicated.
        """
        if not results:
            return len(self._all_links)

        with self._lock:
            # Use global offset (all_links) not per-call offset (results)
            # so that indices are unique across sections in detailed reports.
            start_idx = len(self._all_links)
            unique_results: list[dict] = []
            for raw in results:
                if not isinstance(raw, dict):
                    continue
                r = dict(raw)  # shallow copy to avoid mutating engine output
                duplicate = self._find_duplicate(r)
                if duplicate is not None:
                    self._merge_duplicate(duplicate, r)
                    continue

                if len(self._results) >= self._max_results:
                    break

                r["index"] = str(len(self._all_links) + 1)
                r["source_engine"] = engine_name
                # Normalise URL key — citation handler expects "link"
                if "link" not in r and "url" in r:
                    r["link"] = r["url"]
                self._results.append(r)
                link = r.get("link", "")
                if link:
                    self._sources.append(link)
                self._all_links.append(r)
                unique_results.append(r)
                for key in self._identity_keys(r):
                    self._identity_map[key] = r

            # Both search tool callers format this same list immediately after
            # add_results(), so removing duplicates here keeps displayed and
            # stored citation numbers contiguous.
            results[:] = unique_results
            return start_idx

    def find_or_add_result(
        self,
        result: dict,
        engine_name: str = "web",
    ) -> int:
        """Atomically reuse or register one result and return its 1-based index.

        Fetch tools can run concurrently in pooled subagents. Keeping the URL
        lookup and append under one lock prevents two fetches of the same URL
        from allocating separate citation indices.
        """
        with self._lock:
            duplicate = self._find_duplicate(result)
            if duplicate is not None:
                self._merge_duplicate(duplicate, result)
                idx = duplicate.get("index")
                if idx is not None:
                    return int(idx)

            index = len(self._all_links) + 1
            tracked = dict(result)
            tracked["index"] = str(index)
            tracked["source_engine"] = engine_name
            if "link" not in tracked and "url" in tracked:
                tracked["link"] = tracked["url"]
            self._results.append(tracked)
            link = tracked.get("link", "")
            if link:
                self._sources.append(link)
            self._all_links.append(tracked)
            for key in self._identity_keys(tracked):
                self._identity_map[key] = tracked
            return index

    def find_by_url(self, url: str) -> int | None:
        """Return the 1-based citation index if *url* is already tracked, else ``None``."""
        with self._lock:
            r = self._identity_map.get(f"url:{canonical_url_key(url)}")
            if r is not None:
                idx = r.get("index")
                if idx is not None:
                    return int(idx)
            return None

    def find_by_index(self, idx: int) -> dict | None:
        """Return the result dict for a 1-based citation index, or ``None``.

        Reverse of ``find_by_url``: given ``[N]`` (the citation marker the
        LLM sees in the search-results block), look up the source it
        references so the fetch tool can resolve a confused "fetch [1062]"
        call to the real URL. Thread-safe via the collector lock; uses
        ``_all_links`` (the shared, monotonic list) so a citation registered
        by the lead agent is also resolvable by a pooled subagent.
        """
        if not isinstance(idx, int) or idx < 1:
            return None
        with self._lock:
            for r in self._all_links:
                stored = r.get("index")
                if stored is not None and int(stored) == idx:
                    return r
        return None

    def reset(self) -> None:
        """Clear per-call state.  ``_all_links`` is intentionally kept."""
        with self._lock:
            self._results.clear()
            self._sources.clear()

    def snapshot(self, indices):
        """Capture citation evidence under the same lock used by writers."""
        from copy import deepcopy
        from research_verify.evidence import SourceLookup
        wanted = set(indices)
        with self._lock:
            records = []
            for source in self._all_links:
                try:
                    index = int(source.get("index", 0))
                except (TypeError, ValueError, AttributeError):
                    continue
                if index in wanted:
                    records.append(deepcopy(source))
            return SourceLookup(records)

    @property
    def results(self) -> list[dict]:
        with self._lock:
            return list(self._results)

    @property
    def sources(self) -> list[str]:
        with self._lock:
            return list(self._sources)


# ---------------------------------------------------------------------------
# Tool factory helpers
# ---------------------------------------------------------------------------


# User-facing names for the agent's tools — used in the live milestone
# messages so the chat thinking-text reads "Searching PubMed for …"
# instead of "Tool: search_pubmed — …". Falls back to title-casing the
# raw tool name for tools without an explicit entry, so newly added
# engines work cleanly without a code change.
_TOOL_DISPLAY_NAMES = {
    "web_search": "the web",
    "search_pubmed": "PubMed",
    "search_arxiv": "arXiv",
    "search_semantic_scholar": "Semantic Scholar",
    "search_openalex": "OpenAlex",
    "search_searxng": "the web (SearXNG)",
    "search_google_scholar": "Google Scholar",
    "search_brave": "Brave Search",
    "search_duckduckgo": "DuckDuckGo",
    "search_serper": "Google (Serper)",
    "search_scaleserp": "Google (ScaleSERP)",
    "search_wikipedia": "Wikipedia",
    "search_github": "GitHub",
    "search_stackexchange": "Stack Exchange",
    "search_openlibrary": "Open Library",
    "search_gutenberg": "Project Gutenberg",
    "search_pubchem": "PubChem",
    "search_zenodo": "Zenodo",
    "search_nasa_ads": "NASA ADS",
    "search_local": "your library",
    "fetch_content": "the page",
    "research_subtopic": "subtopic researcher",
}

# The step heartbeat lists tools as a comma list ("selecting next action
# from X, Y, Z…"). The sentence-fragment display names of the two
# non-search tools read wrong in that context ("the page", "subtopic
# researcher"), so the heartbeat uses these list-friendly labels instead;
# every other tool falls through to ``_display_tool_name``.
_HEARTBEAT_TOOL_LABELS = {
    "fetch_content": "page fetching",
    "research_subtopic": "subtopic research",
}

# Bounds for observation progress events. The one-line preview feeds the
# log panel / current-task line / thinking bubble; the detail
# (``metadata["content"]``) is persisted per chat step and emitted per
# socket event, so it must stay bounded — but large enough to show what a
# search or page fetch actually returned when the user expands the step.
# Detail is only attached when the output exceeds the preview, so short
# results ("No results.") aren't shown twice in the expanded step.
_OBSERVATION_PREVIEW_MAX_CHARS = 150
_OBSERVATION_DETAIL_MAX_CHARS = 4000


def _truncate_arg(value: str, limit: int = 80) -> str:
    """Cap a tool-call arg for the one-line progress message.

    Marks the cut with an ellipsis so a shortened query/URL doesn't read
    as if it were the complete value.
    """
    return value[:limit] + "…" if len(value) > limit else value


def _tool_display_name(name: str) -> str:
    """Friendly name for a tool, falling back to a cleaned raw name."""
    if name in _TOOL_DISPLAY_NAMES:
        return _TOOL_DISPLAY_NAMES[name]
    # Strip leading "search_" and title-case for unknown engines.
    cleaned = name[len("search_") :] if name.startswith("search_") else name
    return cleaned.replace("_", " ").title()


def _format_results(results: list[dict], start_idx: int) -> str:
    """Format search results as ``[N] Title (URL)\\nSnippet``."""
    lines = []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        # The collector may remove duplicates or blocked preprint URLs from
        # the batch.  Use the index assigned to the retained record instead
        # of re-enumerating the original batch, otherwise the agent sees
        # citation numbers that point at a different source.
        idx = r.get("index", start_idx + i + 1)
        title = r.get("title", "No title")
        link = r.get("link", r.get("url", ""))
        snippet = r.get("snippet", r.get("body", ""))
        lines.append(f"[{idx}] {title} ({link})\n{snippet}")
    return "\n\n".join(lines) if lines else "No results."


def _make_web_search_tool(
    search_engine_name: str,
    model: BaseChatModel,
    settings_snapshot: dict,
    collector: SearchResultsCollector,
    programmatic_mode: bool = False,
    description: str = NEUTRAL_PRIMARY_SEARCH_DESCRIPTION,
):
    """Create a ``web_search`` tool that instantiates a fresh engine per call."""

    @tool
    def web_search(query: str) -> str:
        """Search the selected source and return result snippets with source indices."""
        from local_deep_research.utilities.resource_utils import safe_close
        from ...config.thread_settings import get_setting_from_snapshot
        from local_deep_research.web_search_engines.search_engine_factory import (
            create_search_engine,
        )

        max_results = int(
            get_setting_from_snapshot(
                "search.max_results", 10, settings_snapshot=settings_snapshot
            )
        )
        max_filtered_results = int(
            get_setting_from_snapshot(
                "search.max_filtered_results",
                10,
                settings_snapshot=settings_snapshot,
            )
        )

        engine = create_search_engine(
            engine_name=search_engine_name,
            llm=model,
            settings_snapshot=settings_snapshot,
            programmatic_mode=programmatic_mode,
            max_results=max_results,
            max_filtered_results=max_filtered_results,
        )
        if engine is None:
            return f"Failed to create search engine '{search_engine_name}'."
        try:
            results = engine.run(query)
            if not isinstance(results, list) or not results:
                return f"No results found for '{query}'. Try rephrasing."
            start = collector.add_results(
                results, engine_name=search_engine_name
            )
            return _format_results(results, start)
        except Exception as exc:
            logger.exception("web_search tool error")
            # Scrub credentials: a search-engine exception can embed the
            # request URL, which may carry an API key. Full detail is logged
            # server-side above.
            return _scrub_tool_error(f"Search error: {exc}")
        finally:
            safe_close(engine, "web search engine")

    web_search.description = description
    return web_search


# Fetch tool builders (full / summary_focus / summary_focus_query / disabled)
# live in ``advanced_search_system.tools.fetch``; see ``build_fetch_tool``.


def _make_specialized_search_tool(
    engine_name: str,
    description: str,
    model: BaseChatModel,
    settings_snapshot: dict,
    collector: SearchResultsCollector,
    programmatic_mode: bool = False,
):
    """Create a ``search_{engine}`` tool for a specific search engine."""

    @tool
    def specialized_search(query: str) -> str:
        """Search a specialized engine."""  # overridden below
        from local_deep_research.utilities.resource_utils import safe_close
        from ...config.thread_settings import get_setting_from_snapshot
        from local_deep_research.web_search_engines.search_engine_factory import (
            create_search_engine,
        )

        max_results = int(
            get_setting_from_snapshot(
                "search.max_results", 10, settings_snapshot=settings_snapshot
            )
        )
        max_filtered_results = int(
            get_setting_from_snapshot(
                "search.max_filtered_results",
                10,
                settings_snapshot=settings_snapshot,
            )
        )

        engine = create_search_engine(
            engine_name=engine_name,
            llm=model,
            settings_snapshot=settings_snapshot,
            programmatic_mode=programmatic_mode,
            max_results=max_results,
            max_filtered_results=max_filtered_results,
        )
        if engine is None:
            return f"Failed to create {engine_name} engine."
        try:
            results = engine.run(query)
            if not isinstance(results, list) or not results:
                return f"No results from {engine_name} for '{query}'. Try rephrasing."
            start = collector.add_results(results, engine_name=engine_name)
            return _format_results(results, start)
        except Exception as exc:
            logger.exception(f"search_{engine_name} tool error")
            return _scrub_tool_error(f"Search error ({engine_name}): {exc}")
        finally:
            safe_close(engine, f"{engine_name} search engine")

    # Override name and description after decoration
    specialized_search.name = f"search_{engine_name}"
    specialized_search.description = description
    return specialized_search


def _load_specialized_engine_tools(
    skip_engine: str | None,
    model: BaseChatModel,
    settings_snapshot: dict,
    collector: SearchResultsCollector,
    programmatic_mode: bool = False,
    egress_context=None,
) -> list:
    """Load tools for all available specialized search engines, filtered by
    egress policy and per-engine ``agent_enabled`` flag.

    ``skip_engine`` names the engine already exposed through the caller's
    generic ``web_search`` tool, so it isn't double-registered; pass ``None``
    when no ``web_search`` tool exists — every allowed engine then stays
    reachable as a specialized tool.

    Shared by ``_build_tools`` (lead agent) and subagent tool setup so both
    layers apply the SAME policy/enrichment logic — see the inline-block
    comment in ``_build_tools`` for why this pre-filtering matters (the
    factory PEP catches violations at instantiation time but the LLM still
    SEES forbidden tool names in the schema, leaking policy state).

    Each returned tool is a closure that creates a fresh engine per
    invocation, so the tool objects themselves are safe to reuse across
    threads (e.g. when a ``research_subtopic`` call fans out to parallel
    subagents that share one tool list).
    """
    tools: list = []
    try:
        from local_deep_research.web_search_engines.search_engines_config import (
            list_eligible_engine_configs,
        )
        from local_deep_research.security.egress.policy import (
            EgressScope,
            evaluate_engine,
            evaluate_retriever,
        )
        from local_deep_research.web_search_engines.retriever_registry import (
            retriever_registry,
        )

        # Discover the candidate pool INDEPENDENT of ``use_in_auto_search``.
        # The agent's "specialized tool surface" is governed by per-engine
        # ``agent_enabled``, credentials, and egress policy — NOT the
        # auto-search-mode toggle (which controls the non-agent ``auto``
        # search surface only). The two settings were siblings on the same
        # settings UI prior to #5015, but they actually control two
        # different surfaces; conflating them made it impossible to expose
        # Tavily / Google PSE (default ``use_in_auto_search=false``) to the
        # agent without also re-enabling them in the ``auto`` search path.
        # Dynamic ``collection_*`` engines never had a ``use_in_auto_search``
        # setting, so the old path locked them out of the agent entirely
        # — this discovery change restores symmetry with #4453.
        eligible = list_eligible_engine_configs(
            settings_snapshot=settings_snapshot,
            egress_context=egress_context,
            check_agent_enabled=True,
        )
    except Exception:
        logger.exception(
            "Failed to discover specialized search engines",
            skip_engine=skip_engine,
        )
        return tools

    for name, config in eligible.items():
        try:
            if name == skip_engine:
                continue

            # Per-engine usability switch (independent of egress). Collection
            # configs carry their DB flag; built-in engines receive the
            # flattened search.engine.web.<name>.agent_enabled setting.
            # Note: Re-checked here to log debug info for specialized tools.
            # Missing flags default to available for backward compatibility.
            # The primary engine was skipped above and remains reachable
            # through the caller's generic web_search tool.
            if not config.get("agent_enabled", True):
                logger.debug(
                    "specialized tool skipped: engine disabled for "
                    "the research agent",
                    engine=name,
                )
                continue

            # Under STRICT, register no specialized engines at all — the
            # agent gets only its primary web_search tool. (Note: STRICT-scope
            # blanket-skip is intentionally enforced here as list_eligible_engine_configs
            # does not blanket-enforce STRICT).
            if (
                egress_context is not None
                and egress_context.scope == EgressScope.STRICT
            ):
                continue

            # Under PUBLIC_ONLY / PRIVATE_ONLY, ask the PDP whether this
            # engine fits the scope. Re-evaluating here produces policy_audit
            # log entries for specialized tools filtered by egress policy.
            # Retrievers route to evaluate_retriever
            # (engine-PDP returns engine_unknown for them); plain engines
            # route to evaluate_engine.
            if egress_context is not None:
                try:
                    if config.get("is_retriever"):
                        try:
                            meta = retriever_registry.get_metadata(
                                name,
                                username=getattr(
                                    egress_context, "username", None
                                ),
                            )
                        except AttributeError:
                            meta = None
                        decision = evaluate_retriever(
                            name, egress_context, metadata=meta
                        )
                    else:
                        # Pass the engine config as metadata so a per-collection
                        # is_public classification is honored without a
                        # redundant DB lookup per collection.
                        decision = evaluate_engine(
                            name,
                            egress_context,
                            settings_snapshot=settings_snapshot,
                            metadata=config,
                        )
                except Exception:
                    logger.bind(policy_audit=True).exception(
                        "specialized tool skipped: policy evaluation failed",
                        engine=name,
                        scope=egress_context.scope.value,
                    )
                    continue
                if not decision.allowed:
                    logger.bind(policy_audit=True).info(
                        "specialized tool filtered by egress policy",
                        engine=name,
                        scope=egress_context.scope.value,
                        reason=decision.reason,
                    )
                    continue

            desc = config.get("description", f"Search using {name}")
            strengths = config.get("strengths", [])
            if strengths:
                desc += f" Best for: {', '.join(strengths[:2])}."
            tools.append(
                _make_specialized_search_tool(
                    name,
                    desc,
                    model,
                    settings_snapshot,
                    collector,
                    programmatic_mode=programmatic_mode,
                )
            )
        except Exception:
            logger.exception(
                "Failed to load specialized search engine",
                engine=name,
            )
    return tools


def _make_research_subtopic_tool(
    search_engine_name: str,
    model: BaseChatModel,
    settings_snapshot: dict,
    collector: SearchResultsCollector,
    max_sub_iterations: int,
    search_enabled: bool = True,
    progress_callback=None,
    programmatic_mode: bool = False,
    fetch_mode: str = "summary_focus_query",
    overall_query: str = "",
    egress_context=None,
    max_subagent_workers: int = MAX_SUBAGENT_WORKERS,
    library_resolver: Any = None,
    web_search_description: str = NEUTRAL_PRIMARY_SEARCH_DESCRIPTION,
):
    """Create the ``research_subtopic`` tool that spawns parallel subagents.

    ``overall_query`` is the original user query passed by the lead agent's
    strategy; it's forwarded to summary-mode fetch tools so the per-page
    extractor sees both the agent's per-fetch focus and the original
    research question.

    ``max_subagent_workers`` bounds the pool size. Surplus subtopics queue
    and start as workers free up; each queued subagent gets its own per-task
    deadline measured from when *it* actually begins executing (not from
    drain-loop start -- see #5014). The value comes from the user setting
    ``langgraph_agent.max_subagent_workers`` and falls back to
    ``MAX_SUBAGENT_WORKERS`` when unset / invalid.

    ``library_resolver`` is threaded into the subagent's fetch tool so a
    subagent researching a library-derived subtopic can also resolve
    ``/library/document/<uuid>`` URLs and ``[N]`` citation markers instead
    of burning the egress-denial quota on them (A3). When ``None``,
    library / citation URLs fall through to the egress gate unchanged.
    """

    @tool(
        description=(
            f"Delegate parallel research on multiple subtopics. Each subtopic is "
            f"investigated by a separate agent. Pass 2-{MAX_SUBTOPICS} focused "
            f"research questions. Batches up to {MAX_SUBTOPICS_HARD_LIMIT} are "
            f"accepted with surplus questions queued; larger batches are "
            f"rejected without starting any subagents."
        )
    )
    def research_subtopic(subtopics: list[str]) -> str:
        """Description passed via ``@tool(description=...)`` above — f-strings can't be docstrings."""
        from langchain.agents import create_agent

        if not subtopics:
            return "No subtopics provided."

        requested_count = len(subtopics)
        if requested_count > MAX_SUBTOPICS_HARD_LIMIT:
            logger.warning(
                "research_subtopic received {} subtopics; rejecting batch above hard limit {}",
                requested_count,
                MAX_SUBTOPICS_HARD_LIMIT,
            )
            return (
                f"Error: research_subtopic received {requested_count} subtopics, "
                f"above the hard limit of {MAX_SUBTOPICS_HARD_LIMIT}. No "
                f"subtopics were investigated. Split the request into batches "
                f"of at most {MAX_SUBTOPICS} focused subtopics and try again."
            )

        overflow_count = max(0, requested_count - MAX_SUBTOPICS)
        if overflow_count:
            logger.warning(
                "research_subtopic received {} subtopics; queuing {} above preferred limit {}",
                requested_count,
                overflow_count,
                MAX_SUBTOPICS,
            )

        # Keep overflow beyond the prompt-facing batch size queued even when
        # max_subagent_workers is configured above 5. Before overflow support,
        # at most MAX_SUBTOPICS tasks reached this pool, so this preserves the
        # established concurrency ceiling while allowing bounded extra work.
        # Clamp to >=1 so a bad direct caller cannot create a 0-worker pool.
        effective_workers = max(
            1, min(max_subagent_workers, MAX_SUBTOPICS, len(subtopics))
        )

        # Build subagent tools ONCE per ``research_subtopic`` call — reused
        # across all parallel subagent invocations. Each tool factory creates
        # a fresh engine per invocation and ``SearchResultsCollector`` is
        # lock-protected, so sharing the tool objects across pool workers
        # is safe. ``research_subtopic`` is itself excluded so subagents
        # cannot recurse.
        sub_tools: list = []
        if search_enabled:
            sub_tools.append(
                _make_web_search_tool(
                    search_engine_name,
                    model,
                    settings_snapshot,
                    collector,
                    programmatic_mode=programmatic_mode,
                    description=web_search_description,
                )
            )
        sub_fetch = build_fetch_tool(
            fetch_mode,
            collector,
            model=model,
            overall_query=overall_query,
            settings_snapshot=settings_snapshot,
            egress_context=egress_context,
            library_resolver=library_resolver,
        )
        if sub_fetch is not None:
            sub_tools.append(sub_fetch)
        # Give subagents the same specialized-engine set the lead agent
        # gets, filtered by the same egress policy / agent_enabled gate via
        # the shared helper — without this, a subagent researching a
        # medical topic couldn't call PubMed directly and would fall back
        # to the generic web_search.
        sub_tools.extend(
            _load_specialized_engine_tools(
                # Skip the primary only when web_search above exposes it —
                # with search_enabled=False the subagent has no web_search,
                # so skipping would make the primary engine unreachable.
                search_engine_name if search_enabled else None,
                model,
                settings_snapshot,
                collector,
                programmatic_mode=programmatic_mode,
                egress_context=egress_context,
            )
        )

        if not sub_tools:
            # No primary search engine, fetching disabled, and every
            # specialized engine filtered out (e.g. STRICT egress scope):
            # a tool-less subagent would return un-grounded LLM text
            # dressed up as research findings. Refuse instead — before the
            # milestone below, so the UI never announces sub-research that
            # won't run. (_build_tools drops research_subtopic entirely
            # when the lead toolbox is otherwise empty; this guard covers
            # any remaining divergence between the two layers' gating.)
            logger.warning(
                "research_subtopic invoked with no tools available; "
                "refusing to run tool-less subagents"
            )
            return (
                "research_subtopic is unavailable: no research tools "
                "(search, fetch, or specialized engines) are permitted in "
                "this configuration. Answer from sources already gathered."
            )

        # Emit progress for UI
        if progress_callback:
            meta = {
                "phase": "sub_research",
                "type": "milestone",
                "subtopics": subtopics,
            }
            if overflow_count:
                meta["overflow_strategy"] = "queued"
                meta["overflow_queued_count"] = overflow_count
            progress_message = (
                f"Researching {len(subtopics)} subtopics with up to "
                f"{effective_workers} in parallel ({overflow_count} above "
                f"the preferred limit queued)"
                if overflow_count
                else f"Researching {len(subtopics)} subtopics in parallel"
            )
            progress_callback(
                progress_message,
                None,
                meta,
            )

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        subagent_prompt = (
            f"You are a focused research assistant. Today's date: {current_date}. "
            "Search thoroughly and return a concise factual summary. "
            "Reference sources by their [N] index numbers. "
            "Cite every factual sentence and table row individually; do not put the only citation "
            "in a heading or at the end of a multi-sentence paragraph. "
            "Do NOT ask clarifying questions — provide your findings directly."
        )
        specialized_names = [
            t.name
            for t in sub_tools
            if isinstance(getattr(t, "name", None), str)
            and t.name.startswith("search_")
        ]
        if specialized_names:
            # Name only the tools actually registered — a static example
            # list could advertise policy-filtered engines the subagent
            # must never learn about.
            subagent_prompt += (
                " Prefer these domain-specific search tools when one "
                f"matches the topic: {', '.join(specialized_names)}."
            )

        def run_subagent(topic: str) -> str:
            try:
                # create_agent() calls model.bind_tools(); ProcessingLLMWrapper
                # (config/llm_config.py) overrides bind_tools to re-wrap the
                # bound model, so the wrapper's <think>-tag stripping survives
                # the agent loop and runs on every model call here (fix #4804).
                # Scope note: other Runnable transforms still escape the wrapper
                # — with_config/bind/stream delegate via __getattr__ to the
                # unwrapped base model (silent, unstripped), and `|` raises
                # TypeError (the wrapper defines no __or__). None are on this
                # create_agent path. Closing that whole class would need a full
                # Runnable-subclass wrapper.
                agent = create_agent(
                    model=model,
                    tools=sub_tools,
                    system_prompt=subagent_prompt,
                )
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": topic}]},
                    {"recursion_limit": max_sub_iterations * 2 + 1},
                )
                messages = result.get("messages", [])
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", str(last))
                    if content:
                        return content
                return f"No findings for: {topic}"
            except GraphRecursionError:
                return f"Research on '{topic}' reached iteration limit. Partial findings above."
            except Exception as exc:
                logger.exception(f"Subagent failed for: {topic[:80]}")
                return _scrub_tool_error(f"Research on '{topic}' failed: {exc}")

        # Capture the lead thread's search context (it carries the user's DB
        # password) so each pool worker can open the per-user ENCRYPTED database
        # when a subagent re-creates a search engine / registers the user's
        # document collections. stdlib ThreadPoolExecutor does NOT propagate the
        # ContextVar — without this, a collection/library primary fails inside a
        # subagent with "Unknown search engine 'collection_…'". This is the same
        # gap sibling strategies (source_based, focused_iteration) close with
        # @preserve_research_context; captured ONCE here on the lead thread.
        captured_search_context = get_search_context()

        # Worker lifecycle timestamps are written under a condition so the
        # drain loop wakes both when a queued task actually starts and when a
        # running task finishes. Submit time is deliberately not tracked: it
        # includes time spent waiting for a free worker and caused #5014. Task
        # IDs keep duplicate subtopic strings independent.
        task_state_changed = threading.Condition()
        task_start_times: dict[int, float] = {}
        task_end_times: dict[int, float] = {}

        def _run_subagent_with_egress(task: tuple[int, str]) -> str:
            task_id, topic = task
            with task_state_changed:
                task_start_times[task_id] = time.monotonic()
                task_state_changed.notify_all()

            try:
                with thread_cleanup():
                    # threading.local is NOT inherited by ThreadPoolExecutor
                    # workers, so re-arm the PEP-578 audit-hook backstop for the
                    # subagent's lifetime.
                    from ...security.egress.audit_hook import (
                        active_egress_context,
                    )

                    with active_egress_context(egress_context):
                        # search_context sets the password ContextVar for this
                        # worker and clears it on exit, preventing pool reuse from
                        # leaking credentials between tasks.
                        if captured_search_context is not None:
                            with search_context(captured_search_context):
                                return run_subagent(topic)
                        return run_subagent(topic)
            finally:
                with task_state_changed:
                    task_end_times[task_id] = time.monotonic()
                    task_state_changed.notify_all()

        ordered_results: dict[int, str] = {}
        # Overall safety cap for the drain loop. Sized to cover the worst-
        # case queue wait (ceil(subtopics/workers) waves) plus slack. This is
        # only a backstop; each started task has its own earlier deadline.
        overall_timeout_seconds = (
            SUBAGENT_TIMEOUT_SECONDS
            * max(1, math.ceil(len(subtopics) / effective_workers))
            * SUBAGENT_TIMEOUT_OVERALL_MULTIPLIER
        )
        drain_start = time.monotonic()
        overall_deadline = drain_start + overall_timeout_seconds

        def _record_per_task_timeout(
            task_id: int, topic: str, elapsed: float
        ) -> None:
            logger.warning(
                f"Subagent timed out (per-task): {topic[:80]} "
                f"ran {elapsed:.1f}s of "
                f"{SUBAGENT_TIMEOUT_SECONDS}s budget"
            )
            ordered_results[task_id] = (
                f"Research on '{topic}' timed out after {elapsed:.1f}s "
                f"(per-subagent budget is {SUBAGENT_TIMEOUT_SECONDS}s)."
            )

        executor = ThreadPoolExecutor(max_workers=effective_workers)
        futures = {}
        try:
            futures = {
                executor.submit(_run_subagent_with_egress, (task_id, topic)): (
                    task_id,
                    topic,
                )
                for task_id, topic in enumerate(subtopics)
            }
            pending = set(futures)

            while pending:
                completed = []
                expired = []
                overall_expired = False

                with task_state_changed:
                    while True:
                        now = time.monotonic()
                        completed = [
                            future
                            for future in pending
                            if futures[future][0] in task_end_times
                        ]
                        if completed:
                            break

                        expired = [
                            future
                            for future in pending
                            if (
                                futures[future][0] in task_start_times
                                and now - task_start_times[futures[future][0]]
                                >= SUBAGENT_TIMEOUT_SECONDS
                            )
                        ]
                        if expired:
                            break

                        if now >= overall_deadline:
                            overall_expired = True
                            break

                        deadlines = [overall_deadline]
                        deadlines.extend(
                            task_start_times[futures[future][0]]
                            + SUBAGENT_TIMEOUT_SECONDS
                            for future in pending
                            if futures[future][0] in task_start_times
                        )
                        task_state_changed.wait(
                            timeout=max(0.0, min(deadlines) - now)
                        )

                # A completed future can still have exceeded its own budget.
                # Check the worker-recorded duration before accepting its
                # result; future.result(timeout=...) cannot do this after a
                # completion iterator has already yielded the future.
                for future in completed:
                    pending.remove(future)
                    task_id, topic = futures[future]
                    start = task_start_times[task_id]
                    elapsed = max(0.0, task_end_times[task_id] - start)
                    if elapsed >= SUBAGENT_TIMEOUT_SECONDS:
                        _record_per_task_timeout(task_id, topic, elapsed)
                        continue
                    try:
                        ordered_results[task_id] = future.result()
                    except Exception as exc:
                        logger.exception(f"Subagent failed for: {topic[:80]}")
                        ordered_results[task_id] = _scrub_tool_error(
                            f"Research on '{topic}' failed: {exc}"
                        )

                # These futures are still running, but their individual
                # deadline has arrived. ThreadPoolExecutor cannot preempt a
                # running Python callable, so ignore its eventual result and
                # let shutdown(wait=False) release the lead agent promptly.
                now = time.monotonic()
                for future in expired:
                    pending.remove(future)
                    task_id, topic = futures[future]
                    elapsed = max(0.0, now - task_start_times[task_id])
                    _record_per_task_timeout(task_id, topic, elapsed)
                    future.cancel()

                if overall_expired:
                    now = time.monotonic()
                    for future in pending:
                        task_id, topic = futures[future]
                        start = task_start_times.get(task_id)
                        if start is None:
                            queued_elapsed = max(0.0, now - drain_start)
                            logger.warning(
                                f"Subagent exceeded overall safety cap: "
                                f"{topic[:80]} remained queued for "
                                f"{queued_elapsed:.1f}s and never started"
                            )
                            ordered_results[task_id] = (
                                f"Research on '{topic}' did not start before "
                                f"the overall safety budget of "
                                f"{overall_timeout_seconds}s expired "
                                f"(queued for {queued_elapsed:.1f}s; its "
                                f"{SUBAGENT_TIMEOUT_SECONDS}s per-subagent "
                                f"budget begins at task start)."
                            )
                        else:
                            elapsed = max(0.0, now - start)
                            logger.warning(
                                f"Subagent exceeded overall safety cap: "
                                f"{topic[:80]} ran {elapsed:.1f}s of "
                                f"{overall_timeout_seconds}s overall / "
                                f"{SUBAGENT_TIMEOUT_SECONDS}s per-task budget"
                            )
                            ordered_results[task_id] = (
                                f"Research on '{topic}' did not finish within "
                                f"the overall safety budget of "
                                f"{overall_timeout_seconds}s (ran "
                                f"{elapsed:.1f}s; per-subagent budget is "
                                f"{SUBAGENT_TIMEOUT_SECONDS}s)."
                            )
                        future.cancel()
                    pending.clear()
        finally:
            for future in futures:
                if not future.done():
                    future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

        # Return results in original order
        parts = []
        for task_id, topic in enumerate(subtopics):
            parts.append(
                f"## {topic}\n{ordered_results.get(task_id, 'No results')}"
            )
        result_text = "\n\n---\n\n".join(parts)

        # Tell the lead agent how an over-budget but bounded request was handled.
        # Every queued topic has a result section above, including timeout/error
        # text when its worker did not complete successfully.
        if overflow_count:
            result_text += (
                f"\n\nOverflow handling: {overflow_count} subtopic(s) beyond "
                f"the preferred per-call limit of {MAX_SUBTOPICS} were queued "
                f"for processing instead of being dropped; each appears in "
                f"the results above."
            )
        return result_text

    return research_subtopic


def _make_jcr_tool(collector):
    """Expose the vendored jcr_mcp journal search as a model-selected tool."""
    @tool("search_journal")
    def search_journal(
        journal_name: str,
        source_index: int,
        minimum_if: float | None = None,
        year: str = "latest",
        operator: str = ">=",
    ) -> str:
        """Look up a collected paper's journal impact factor using its exact source_index.

        Use when the user requests journal impact factors or ranking by them.
        Pass minimum_if and operator only for a requested threshold. Use latest
        unless the user specifies a JCR metric year. The lookup uses the
        journal recorded for that source.
        """
        try:
            from research_verify.jcr_adapter import lookup_source
            source = collector.find_by_index(int(source_index))
            if source is None:
                result = {"status": "metric_unavailable",
                          "missing_reason": "source_index_not_found",
                          "source_index": source_index,
                          "minimum_if": minimum_if,
                          "threshold_operator": operator}
            else:
                result = lookup_source(source, minimum=minimum_if,
                                       operator=operator, year=year)
                result["source_index"] = int(source_index)
                source["_jcr_check"] = result
                source["jcr_check_status"] = result.get("status")
                source["jcr_provenance"] = {
                    "source": "jcr_mcp",
                    "metric_year": result.get("metric_year"),
                    "metric_source": result.get("metric_source"),
                    "source_url": result.get("source_url"),
                    "status": result.get("status"),
                    "missing_reason": result.get("missing_reason"),
                    "requested_minimum_if": result.get("minimum_if"),
                    "threshold_operator": result.get("threshold_operator"),
                }
                if result.get("status") == "found":
                    source["impact_factor"] = result.get("impact_factor")
                    source["metric_year"] = result.get("metric_year")
                    source["passes_threshold"] = result.get("passes_threshold")
            return json.dumps(result, ensure_ascii=False, sort_keys=True)
        except Exception as exc:
            logger.warning("jcr_mcp tool failed: %s", type(exc).__name__)
            return json.dumps({"status": "metric_unavailable",
                               "missing_reason": "jcr_mcp_tool_failed",
                               "error_type": type(exc).__name__},
                              ensure_ascii=False, sort_keys=True)

    return search_journal


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------


class LangGraphAgentStrategy(BaseSearchStrategy):
    """Research strategy using LangGraph agents with parallel subagent support.

    The lead agent autonomously decides what to search, when to dig deeper
    (via subagents), and when to synthesize — replacing the manual ReAct loop
    in the MCP strategy.
    """

    def __init__(
        self,
        model: BaseChatModel,
        search,
        citation_handler=None,
        max_iterations: int = 50,
        max_sub_iterations: int = 8,
        include_sub_research: bool = True,
        all_links_of_system: list | None = None,
        settings_snapshot: dict | None = None,
        programmatic_mode: bool = False,
        **kwargs,
    ):
        super().__init__(
            all_links_of_system=all_links_of_system,
            settings_snapshot=settings_snapshot,
            **kwargs,
        )
        self.model = model
        self.search = search
        # Whether the parent AdvancedSearchSystem is running in programmatic
        # mode (no DB metrics/rate-limit persistence). Threaded into the
        # tool factory closures so engines created per tool call inherit it.
        self.programmatic_mode = programmatic_mode
        # search.iterations (typically 1-5) controls pipeline strategies.
        # For an agent, each "iteration" is one LLM→tool round-trip, so we
        # need many more.  Treat any value below the agent minimum as "use
        # default" rather than clamping to a uselessly low number.
        self.max_iterations = (
            int(max_iterations)
            if int(max_iterations) >= MIN_ITERATIONS
            else DEFAULT_MAX_ITERATIONS
        )
        self.max_sub_iterations = int(max_sub_iterations)
        # Detailed-report subsection research deliberately uses a short
        # bounded pass.  Keep this opt-in so normal user research retains the
        # minimum iteration budget while report generation cannot silently
        # expand a requested one-step pass back to the default 50 rounds.
        self._allow_short_runs = False
        self._run_deadline = None
        self.include_sub_research = include_sub_research
        self.citation_handler = citation_handler or CitationHandler(
            model,
            handler_type="standard",
            settings_snapshot=settings_snapshot,
        )
        raw_max_sources = self.get_setting(
            "langgraph_agent.max_unique_sources", DEFAULT_MAX_UNIQUE_SOURCES
        )
        try:
            self.max_unique_sources = max(10, min(DEFAULT_MAX_UNIQUE_SOURCES, int(raw_max_sources)))
        except (TypeError, ValueError):
            self.max_unique_sources = DEFAULT_MAX_UNIQUE_SOURCES
            logger.warning(
                f"Invalid langgraph_agent.max_unique_sources={raw_max_sources!r}; "
                f"using {DEFAULT_MAX_UNIQUE_SOURCES}"
            )
        self.collector = SearchResultsCollector(
            self.all_links_of_system, max_results=self.max_unique_sources
        )
        # The final citation writer may need to make its own model-selected
        # source-bound JCR lookup.  Keep the factory on the writer handler so
        # it uses the same collector/index space as the research agent.
        writer_handler = getattr(self.citation_handler, "_handler", self.citation_handler)
        if hasattr(writer_handler, "set_writer_jcr_tool_factory"):
            writer_handler.set_writer_jcr_tool_factory(
                lambda: _make_jcr_tool(self.collector)
            )
        # research_verify: last parsed constraint (set by _attach_constraint_match)
        self._constraint_spec = None
        self._citation_checks: list = []
        self._collection_tool_display_names: dict[str, str] = {}
        self._collection_tool_display_names_loaded = False

        fetch_mode = self.get_setting(
            "search.fetch.mode", "summary_focus_query"
        )
        if fetch_mode not in FETCH_MODES:
            logger.warning(
                f"Unknown search.fetch.mode={fetch_mode!r}, falling back to "
                f"'summary_focus_query'. Valid modes: {FETCH_MODES}"
            )
            fetch_mode = "summary_focus_query"
        self.fetch_mode = fetch_mode
        logger.info(f"LangGraph agent fetch_mode={self.fetch_mode}")

        # User-tunable pool size for parallel subagents (follow-up to #5014).
        # Lets users match their LLM backend's parallel-request capacity --
        # Ollama / LMStudio / llama.cpp ``OLLAMA_NUM_PARALLEL``, an OpenAI
        # tier limit, etc. -- without code changes. Falls back to the
        # constant default on missing/invalid input so a misconfigured
        # setting cannot silently break the drain loop.
        raw_max_workers = self.get_setting(
            "langgraph_agent.max_subagent_workers", MAX_SUBAGENT_WORKERS
        )
        self.max_subagent_workers = self._coerce_max_subagent_workers(
            raw_max_workers
        )

        # Derive the search engine name for creating fresh instances
        self._search_engine_name = self._resolve_engine_name()

    @staticmethod
    def _coerce_max_subagent_workers(raw: Any) -> int:
        """Validate and clamp the user-supplied pool size.

        - Non-numeric, non-finite, or unparsable values fall back to
          ``MAX_SUBAGENT_WORKERS`` with a warning so a misconfigured setting
          cannot crash the constructor or silently produce a 0-worker pool.
        - Values below 1 are clamped up to 1; a 0-worker pool would deadlock
          the drain loop waiting on tasks no thread will ever run.
        - Values above 32 are clamped down -- past that point the bottleneck
          is almost always the LLM/search backend, not pool size, and an
          unbounded value invites accidental denial-of-service against the
          user's own infrastructure.
        """
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError):
            logger.warning(
                f"langgraph_agent.max_subagent_workers={raw!r} is not an "
                f"integer; falling back to MAX_SUBAGENT_WORKERS="
                f"{MAX_SUBAGENT_WORKERS}"
            )
            return MAX_SUBAGENT_WORKERS
        if value < 1:
            logger.warning(
                f"langgraph_agent.max_subagent_workers={value} is below 1; "
                f"clamping to 1 to avoid a deadlocked pool"
            )
            return 1
        if value > 32:
            logger.warning(
                f"langgraph_agent.max_subagent_workers={value} is above the "
                f"32-thread soft cap; clamping to 32. Set via env or "
                f"settings only if your LLM/search backend explicitly "
                f"supports it."
            )
            return 32
        return value

    def _resolve_engine_name(self) -> Optional[str]:
        """Best-effort extraction of the configured engine name.

        Returns a CANONICAL engine id (the same string that
        ``search_config`` / ``engine_registry`` use as a dict key, e.g.
        ``semantic_scholar`` rather than the class-derived
        ``semanticscholar``). The class-name fallback historically returned
        a lowercased, ``SearchEngine``-stripped variant that was almost
        but not quite canonical — e.g. ``DuckDuckGoSearchEngine`` →
        ``"duckduckgo"`` instead of the registry key ``"ddg"``, and
        ``SemanticScholarSearchEngine`` → ``"semanticscholar"`` instead of
        ``"semantic_scholar"``. That mismatch leaked the configured primary
        engine back into the specialised-tools loop as a redundant
        ``search_<engine>`` tool alongside ``web_search``. Reverse-lookup
        via ``ENGINE_REGISTRY`` so both sides of the
        ``if name == skip_engine: continue`` comparison agree on the
        canonical id (#5015 follow-up).

        Returns ``None`` when no canonical id can be derived — callers
        then fall through and the helper's primary-skip never matches
        (which is the only safe behaviour, since the factory would also
        fail to resolve an unknown engine).
        """
        # Try settings first — `search.tool` is already the canonical id
        # the user typed in the UI / env var.
        tool_setting = self.get_setting("search.tool", None)
        if tool_setting and isinstance(tool_setting, str):
            return tool_setting
        # Fall back to the engine CLASS, but resolve via the registry so
        # we land on the canonical id (``semantic_scholar``,
        # ``ddg``, ...) rather than the class-derived heuristic. The
        # registry is the single source of truth for which Python class
        # implements which canonical id.
        if self.search is not None and hasattr(self.search, "__class__"):
            cls_name = self.search.__class__.__name__
            # Lazy import: ``engine_registry`` already lives in the same
            # package tree the strategy uses for ``ENGINE_REGISTRY``
            # construction; keeping it inside the function avoids a
            # ``from . import engine_registry`` cycle at module load.
            from local_deep_research.web_search_engines.engine_registry import (
                ENGINE_REGISTRY,
            )

            for name, entry in ENGINE_REGISTRY.items():
                if entry.class_name == cls_name:
                    return name
        return None

    def _display_tool_name(self, tool_name: str) -> str:
        """Return a user-friendly display name for a tool.

        ``web_search`` is a generic wrapper around the user's configured
        engine. Resolve it through the same curated ``_TOOL_DISPLAY_NAMES``
        map as the specialized search tools (keyed by ``search_<engine>``)
        so the UI shows brand-correct names like "DuckDuckGo" or
        "the web (SearXNG)" instead of the raw lowercase engine id
        (e.g. "searxng"). ``search_collection_<id>`` tools (including
        ``web_search`` remapped onto a collection primary engine) resolve
        through the per-run collection-label cache instead — a raw UUID
        title-cased through the map fallback is unreadable — and fall back
        to the generic "Collection" when no label is known. Other tools
        use the map directly.
        """
        resolved_tool_name = (
            f"search_{self._search_engine_name}"
            if tool_name == "web_search"
            else tool_name
        )
        if resolved_tool_name.startswith("search_collection_"):
            self._load_collection_display_names()
            return self._collection_tool_display_names.get(
                resolved_tool_name, "Collection"
            )
        return _tool_display_name(resolved_tool_name)

    def _load_collection_display_names(
        self, collection_configs: Optional[dict] = None
    ) -> None:
        """Cache each ``collection_*`` engine's configured ``display_name``,
        keyed by tool name (``search_collection_<id>``), for progress text.

        Runs at most once per research run. ``_build_tools`` passes the
        ``search_config()`` result it already fetched so the common path
        costs no extra DB round-trip; the no-argument call from
        ``_display_tool_name`` is the fallback for runs that never built
        tools, and fetches ``search_config()`` itself. Any failure —
        including one mid-parse — is swallowed: labels are cosmetic, so a
        broken config degrades to the generic "Collection" fallback
        (entries parsed before the failure keep their labels) rather than
        crashing progress reporting, and is not retried within the run.
        """
        if self._collection_tool_display_names_loaded:
            return
        self._collection_tool_display_names_loaded = True
        try:
            if collection_configs is None:
                from local_deep_research.web_search_engines.search_engines_config import (
                    search_config,
                )

                collection_configs = search_config(
                    settings_snapshot=self.settings_snapshot
                )
            for engine_id, engine_config in collection_configs.items():
                if not engine_id.startswith("collection_"):
                    continue
                # ``collection_*`` entries are built internally with a
                # guaranteed display_name; the check only shields the
                # cache from a missing/blank label ever reaching the UI.
                display_name = engine_config.get("display_name")
                if isinstance(display_name, str) and display_name.strip():
                    self._collection_tool_display_names[
                        f"search_{engine_id}"
                    ] = display_name.strip()
        except Exception:
            logger.warning(
                "Could not load collection display names; "
                "using generic collection labels"
            )
            logger.debug("Collection display name load failure", exc_info=True)

    def _format_tool_call_progress(self, tc, display_name: str) -> str:
        """Format a single tool call as a user-facing progress message.

        Extracted from the ``analyze_topic`` stream loop so the per-tool-type
        emoji + argument-extraction can be unit-tested without driving the full
        LangGraph stream. Behavior is preserved from the original inline block.

        - ``fetch_content`` → ``📖 Reading the page: "<url>"`` (URL arg).
        - ``research_subtopic`` → ``🔬 Investigating subtopic: "<…>"``
          (accepts ``subtopics`` list, ``subtopic``, or ``query`` for
          forward-compat with older signatures).
        - All other tools (specialized engines, ``web_search``) →
          ``🔍 Searching <Display Name>: "<query>"`` (falls back to
          ``url`` if ``query`` is absent).

        Arg extractions are truncated to 80 chars (marked with an ellipsis
        so a cut arg doesn't read as complete) to keep the chat-progress
        line bounded. Subtopic lists cap per item instead of cutting the
        joined string, so every subtopic stays visible — the collapsed
        step row ellipsizes via CSS and expands on click.
        """
        tc_args = tc.get("args", {})
        raw_name = tc.get("name", "")
        # `fetch_content` carries a URL arg; the search tools carry a query
        # arg. Either way, show the meaningful arg in quotes so the user
        # sees what the agent is actually looking up.
        if raw_name == "fetch_content":
            target = _truncate_arg(str(tc_args.get("url", "")))
            return f'📖 Reading {display_name}: "{target}"'
        if raw_name == "research_subtopic":
            # Tool signature is `subtopics: list[str]`. Accept either key for
            # forward-compat and stringify a list as a comma list.
            raw_sub = tc_args.get(
                "subtopics",
                tc_args.get(
                    "subtopic",
                    tc_args.get("query", ""),
                ),
            )
            if isinstance(raw_sub, list):
                sub = ", ".join(_truncate_arg(str(s)) for s in raw_sub)
            else:
                sub = _truncate_arg(str(raw_sub))
            return f'🔬 Investigating subtopic: "{sub}"'
        # Search-style tool — query arg (or URL if query missing). Use a
        # loop-local name here — do NOT reassign the `query` parameter, which
        # is still needed downstream by _synthesize_from_collector()/
        # _finalize() as the original research question.
        tc_query = _truncate_arg(
            str(
                tc_args.get(
                    "query",
                    tc_args.get("url", ""),
                )
            )
        )
        return f'🔍 Searching {display_name}: "{tc_query}"'

    def _observation_event(self, msg) -> tuple[str, dict]:
        """Build the (message, metadata) pair for a tool-result observation.

        The message stays a one-line 150-char preview — it feeds the log
        panel, the classic progress page's current-task line, and the chat
        thinking bubble, none of which can absorb a full tool result. When
        the output is longer than the preview, the (bounded) full output
        rides along in ``metadata["content"]``: the chat route persists it
        beneath the message so the click-to-expand step row shows what was
        actually fetched, and the classic progress page's agent-thinking
        panel appends it to its RESULT entry. Outputs the preview already
        shows verbatim attach no detail — the expanded step would just
        repeat the line ("No results." twice).

        Extracted from the ``analyze_topic`` stream loop so it can be
        unit-tested without driving the full LangGraph stream.
        """
        tool_name = getattr(msg, "name", "tool")
        display_name = self._display_tool_name(tool_name)
        raw = str(getattr(msg, "content", ""))

        # Suppress the misleading "📄 From the page: Cannot fetch <url>: ..."
        # pattern for ``fetch_content`` denial/error observations. The fetch
        # tool returns a "Cannot fetch …: blocked by egress policy (…)"
        # string when the egress gate refuses the URL (policy.py:_record_denial
        # already emits a WARNING with the same URL), and the chat panel
        # would re-emit that string under the "From the page:" label — which
        # reads to the user as if the page was read and its content is a
        # denial. The WARNING in the persisted log is the audit signal;
        # suppressing the MILESTONE here keeps the chat UI truthful. The
        # caller skips the _update_progress call when this returns None.
        # Gated on the tool name (not the content prefix alone) so a
        # non-fetch tool whose result happens to start with "Cannot fetch "
        # still surfaces normally — the suppression is about the
        # ``fetch_content`` denial framing, not a generic string-substring
        # match.
        if tool_name == "fetch_content" and (
            raw.startswith("Cannot fetch ") or raw.startswith("Error fetching ")
        ):
            return None

        preview = raw[:_OBSERVATION_PREVIEW_MAX_CHARS].replace("\n", " ")
        # Keep the stable tool id in metadata; the friendly label
        # already lives in the message.
        metadata = {"phase": "observation", "tool": tool_name}
        # Attach detail only when it adds something beyond the preview —
        # longer output, or short multi-line output whose newlines the
        # preview flattened. Outputs identical to the preview would just
        # be repeated in the expanded step.
        if raw != preview:
            detail = raw[:_OBSERVATION_DETAIL_MAX_CHARS]
            if len(raw) > _OBSERVATION_DETAIL_MAX_CHARS:
                detail += " …"
            metadata["content"] = detail
        return (f"📄 From {display_name}: {preview}", metadata)

    def _heartbeat_message(self, iteration: int) -> str:
        """Build the between-steps heartbeat line for the given iteration.

        Before any source is gathered the agent is still planning, so the
        line reports the size of its toolbox. Afterwards it lists EVERY
        enabled tool by friendly name — an earlier 3-name sample with
        "+N more" hid most engines, which users read as the agent having
        fewer options than it does.

        Extracted from the ``analyze_topic`` stream loop so it can be
        unit-tested without driving the full LangGraph stream.
        """
        sources_so_far = len(self.all_links_of_system)
        names = getattr(self, "_tool_names", []) or []
        if sources_so_far == 0:
            return (
                f"Step {iteration} · planning approach "
                f"with {len(names)} research tool"
                f"{'s' if len(names) != 1 else ''} available…"
            )
        listing = ", ".join(
            _HEARTBEAT_TOOL_LABELS.get(n) or self._display_tool_name(n)
            for n in names
        )
        return (
            f"Step {iteration} · {sources_so_far} source"
            f"{'s' if sources_so_far != 1 else ''} gathered · "
            f"selecting next action from {listing}"
        )

    def _build_egress_context(self):
        """Construct the frozen ``EgressContext`` for this run.

        Returns ``None`` if a context can't be built (no snapshot, or
        invariant violation) — callers fall through to current behavior
        rather than crashing. Lazy import to avoid pulling the security
        module at strategy-class import time.
        """
        if not self.settings_snapshot:
            return None
        from local_deep_research.security.egress.policy import (
            PolicyDeniedError,
            context_from_snapshot,
            resolve_run_primary_engine,
        )

        try:
            # Derive the primary engine the SAME way the factory PEP does —
            # from ``search.tool`` — NOT from the engine class name. Under the
            # default ADAPTIVE scope the primary IS what resolves the concrete
            # scope, so a divergent primary here silently under-filters the
            # agent's tool list: a private collection primary classified via the
            # class heuristic ("libraryrag" -> unknown -> BOTH) left public
            # engines visible, which the factory then hard-denied mid-run
            # (scope_mismatch_private_only). resolve_run_primary_engine raises
            # ValueError when no primary is configured; this advisory filter
            # then degrades to unfiltered (the factory PEP still enforces) —
            # research_service has already failed the run closed by that point.
            primary = resolve_run_primary_engine(self.settings_snapshot)
            # Thread the run's username so ADAPTIVE can classify a per-user
            # private retriever primary (registered under the user's
            # namespace) as PRIVATE_ONLY, and so the resulting
            # ``egress_context.username`` is populated for the per-user
            # retriever-metadata reads in _load_specialized_engine_tools.
            from ...search_system import username_from_snapshot

            username = username_from_snapshot(
                self.settings_snapshot
            ) or getattr(self, "_username", None)
            return context_from_snapshot(
                self.settings_snapshot, primary, username=username
            )
        except PolicyDeniedError:
            # Corrupted/invalid policy.egress_scope — re-raise so the
            # caller fails closed instead of silently running unfiltered.
            raise
        except (ValueError, KeyError, TypeError):
            logger.debug(
                "Could not build EgressContext for langgraph agent — "
                "falling back to unfiltered tool list"
            )
            return None

    def _build_library_resolver(self):
        """Build a ``library_resolver`` callable for the fetch tool.

        Returns ``None`` when no user is associated with the run (programmatic
        mode, benchmarks, news). The fetch tool then behaves exactly as it
        did before the A3 fix: library / citation URLs fall through to the
        egress gate and are rejected as ``unsupported_scheme``. Returning
        ``None`` keeps those callers' behaviour identical.
        """
        username = None
        if self.settings_snapshot:
            # The snapshot carries the username under the ``_username`` key
            # injected by ``AdvancedSearchSystem.ensure_snapshot_username``;
            # the strategy also checks ``self._username`` attribute as a fallback
            # for non-snapshot callers (tests, programmatic API).
            from ...search_system import username_from_snapshot

            username = username_from_snapshot(self.settings_snapshot)
        if not username:
            username = getattr(self, "_username", None)
        if not username:
            return None
        return make_library_resolver(username)

    def _build_tools(self, overall_query: str = "") -> list:
        """Build the LangChain tool list for the lead agent.

        ``overall_query`` is the original user query; it's threaded into
        summary-mode fetch tools so the per-page extractor sees both the
        agent's per-fetch focus and the original research question.
        """
        tools = []

        # Compute the policy context ONCE for this run. Threaded through
        # every tool builder so subagent threads — which don't inherit
        # thread-local state — get the same context as the lead agent.
        policy_ctx = self._build_egress_context()
        # Same lifetime rule as policy_ctx: build ONCE, thread through every
        # tool so the lead agent and pooled subagents resolve the same
        # library documents. Without this, every fetch call on a library
        # doc URL is rejected by the egress policy as ``unsupported_scheme``
        # (A3 — 26 of 26 "Reading the page" milestones produced no content
        # in the f3045c5b run).
        library_resolver = self._build_library_resolver()
        primary_search_description = NEUTRAL_PRIMARY_SEARCH_DESCRIPTION

        # Web search (always present if we have a search engine)
        if self.search is not None:
            try:
                from ...web_search_engines.search_engines_config import (
                    search_config,
                )

                engines_config = search_config(
                    settings_snapshot=self.settings_snapshot
                )
                # Seed the collection-label cache from the fetch we already
                # paid for — search_config() opens a per-user DB session, so
                # letting _display_tool_name lazy-load it again mid-run
                # would duplicate the round-trip.
                self._load_collection_display_names(engines_config)
                primary_source_config = engines_config.get(
                    self._search_engine_name
                )
                primary_source_type = PrimarySourceType.SEARCH
                primary_engine_classification: EngineClassification | None = (
                    None
                )
                if self._search_engine_name == "library":
                    primary_source_type = PrimarySourceType.LIBRARY
                if self._search_engine_name.startswith("collection_"):
                    primary_source_type = PrimarySourceType.COLLECTION
                if (
                    primary_source_config is not None
                    and primary_source_config.get("is_retriever") is True
                ):
                    from ...web_search_engines.retriever_registry import (
                        retriever_registry,
                    )

                    primary_source_type = PrimarySourceType.RETRIEVER
                    # Scope the lookup to this run's user so a per-user
                    # retriever's classification resolves (falls back to the
                    # shared namespace when no username is available).
                    from ...search_system import username_from_snapshot

                    _md_username = username_from_snapshot(
                        self.settings_snapshot
                    ) or getattr(self, "_username", None)
                    retriever_metadata = retriever_registry.get_metadata(
                        self._search_engine_name,
                        username=_md_username,
                    )
                    retriever_is_local = (
                        retriever_metadata.get("is_local")
                        if retriever_metadata is not None
                        else None
                    )
                    primary_engine_classification = EngineClassification(
                        is_public=(
                            not retriever_is_local
                            if isinstance(retriever_is_local, bool)
                            else None
                        ),
                        is_local=(
                            retriever_is_local
                            if isinstance(retriever_is_local, bool)
                            else None
                        ),
                    )
                elif policy_ctx is not None:
                    primary_engine_classification = classify_engine(
                        self._search_engine_name,
                        policy_ctx,
                        settings_snapshot=self.settings_snapshot,
                        metadata=primary_source_config,
                    )
                if primary_engine_classification is not None:
                    primary_source_classification = classify_primary_source(
                        primary_source_type,
                        primary_engine_classification,
                    )
                    primary_search_description = (
                        format_primary_search_description(
                            primary_source_classification
                        )
                    )
            except Exception:
                logger.debug(
                    "Could not resolve primary search metadata; using neutral "
                    "tool description"
                )
            tools.append(
                _make_web_search_tool(
                    self._search_engine_name,
                    self.model,
                    self.settings_snapshot,
                    self.collector,
                    programmatic_mode=self.programmatic_mode,
                    description=primary_search_description,
                )
            )

        # Content fetcher (returns None when fetch_mode == 'disabled')
        fetch = build_fetch_tool(
            self.fetch_mode,
            self.collector,
            model=self.model,
            overall_query=overall_query,
            settings_snapshot=self.settings_snapshot,
            egress_context=policy_ctx,
            library_resolver=library_resolver,
        )
        if fetch is not None:
            tools.append(fetch)

        # Specialized search engines (pre-filtered by egress policy).
        #
        # This is the core fix for the original LangGraph silent-expansion
        # complaint. The factory PEP catches engines at instantiation time,
        # but that's a runtime check — the LLM still SEES the forbidden
        # tool names in the schema and the latency of a denied tool call
        # leaks policy state. Filtering the tool list HERE means the
        # forbidden tools never reach create_agent(), and the LLM never
        # learns they exist.
        tools.extend(
            _load_specialized_engine_tools(
                # Skip the engine web_search above already wraps — the same
                # name it was built from, and only when it was built at all,
                # else the primary engine would become unreachable.
                self._search_engine_name if self.search is not None else None,
                self.model,
                self.settings_snapshot,
                self.collector,
                programmatic_mode=self.programmatic_mode,
                egress_context=policy_ctx,
            )
        )

        # Subagent research tool — only when the toolbox already holds at
        # least one real research tool. Subagents are gated on the same
        # search/fetch/egress state as the lead, so with nothing else here
        # they'd have nothing either: a research_subtopic-only agent would
        # fan out tool-less subagents whose un-grounded text reads as
        # findings. Dropping it lets the empty-toolbox error below fire.
        if self.include_sub_research and tools:
            tools.append(
                _make_research_subtopic_tool(
                    self._search_engine_name,
                    self.model,
                    self.settings_snapshot,
                    self.collector,
                    self.max_sub_iterations,
                    search_enabled=self.search is not None,
                    progress_callback=self.progress_callback,
                    programmatic_mode=self.programmatic_mode,
                    fetch_mode=self.fetch_mode,
                    overall_query=overall_query,
                    egress_context=policy_ctx,
                    max_subagent_workers=self.max_subagent_workers,
                    library_resolver=library_resolver,
                    web_search_description=primary_search_description,
                )
            )

        if tools:
            tools.append(_make_jcr_tool(self.collector))

        return tools

    # -- Main entry point ---------------------------------------------------

    def analyze_topic(self, query: str) -> Dict[str, Any]:
        from langchain.agents import create_agent

        logger.info(f"LangGraph agent research: {query[:100]}")

        # Reset collector for fresh subsection call (detailed report mode)
        self.collector.reset()
        nr_of_links = len(self.all_links_of_system)

        self._update_progress(
            f'Starting agent research: "{query[:80]}"',
            5,
            {"phase": "init", "type": "milestone", "query": query[:100]},
        )
        self.check_termination(CHECK_CONTEXT_ENTRY)

        # Build tools (overall_query feeds summary-mode fetch tools)
        tools = self._build_tools(overall_query=query)
        if not tools:
            return self._error_result("No tools available")
        # Stash tool names for the per-step heartbeat — gives the user
        # concrete info ("from the web (SearXNG), PubMed, …") instead of
        # a vague spinner while the LLM picks its next move. The raw ids
        # are mapped to friendly names at render time via
        # ``_display_tool_name``.
        self._tool_names = [getattr(t, "name", "?") for t in tools]

        # Build system prompt — fetch_line wording mirrors the active mode
        # so the agent isn't told to use a tool that doesn't exist.
        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.fetch_mode == "disabled":
            fetch_line = (
                "3. Rely on search snippets — full-page fetching is disabled "
                "for this run.\n"
            )
        elif self.fetch_mode in ("summary_focus", "summary_focus_query"):
            fetch_line = (
                "3. Use fetch_content(url, focus) when snippets aren't enough; "
                "always pass the specific question or claim you want answered "
                "as ``focus`` so the tool returns only the relevant facts.\n"
            )
        else:  # full
            fetch_line = "3. Use fetch_content to read full pages when snippets aren't enough.\n"
        # Build the policy addendum once so the system prompt can carry
        # explicit guidance to the LLM about which tools actually exist.
        # Closing the timing-leak attack requires both halves: the tool
        # list is pre-filtered above, AND the LLM is told what's
        # available, so it doesn't waste tokens probing for forbidden
        # engines and the latency of denial paths doesn't leak policy.
        policy_addendum = ""
        try:
            from local_deep_research.security.egress.policy import (
                EgressScope,
                PolicyDeniedError,
            )

            ctx = self._build_egress_context()
            if ctx is not None and ctx.scope == EgressScope.STRICT:
                policy_addendum = (
                    "\nRESTRICTED MODE: only the primary search tool is "
                    f"available ({ctx.primary_engine}). Do NOT reference or "
                    "attempt other search_* tools — they do not exist in "
                    "this session and will not work. Use web_search and "
                    "research_subtopic for everything.\n"
                )
            elif ctx is not None and ctx.scope == EgressScope.PRIVATE_ONLY:
                policy_addendum = (
                    "\nPRIVATE-ONLY MODE: public search engines (arxiv, "
                    "pubmed, brave, etc.) are not available in this "
                    "session. Use only local search tools.\n"
                )
            elif ctx is not None and ctx.scope == EgressScope.PUBLIC_ONLY:
                policy_addendum = (
                    "\nPUBLIC-ONLY MODE: local search tools (library, "
                    "collection, paperless) are not available in this "
                    "session.\n"
                )
        except PolicyDeniedError:
            # Corrupt/unknown scope must fail closed, never run unfiltered.
            # In practice _build_tools() (called above at the top of
            # analyze_topic) already raised this for the same snapshot, so
            # we never reach here with a bad scope — but re-raise rather
            # than swallow, so this stays correct if the call order changes.
            raise
        except Exception:
            logger.debug(
                "Could not derive policy addendum for system prompt — "
                "agent will see the unmodified prompt"
            )

        system_prompt = (
            f"You are a research assistant writing a research report. Today's date: {current_date}.\n"
            "This is NOT a chat conversation. Your only job is to research the "
            "given topic and produce a comprehensive, well-cited report.\n"
            "Do NOT ask clarifying questions, do NOT ask the user anything, "
            "do NOT offer to help further — just research and report.\n"
            "You MUST search the selected source before answering — never answer from memory alone.\n\n"
            "Strategy:\n"
            "1. Start with web_search — it queries your selected primary source — for initial exploration.\n"
            "2. For complex multi-faceted questions, use research_subtopic to "
            f"investigate specific aspects in parallel (pass 2-{MAX_SUBTOPICS} "
            f"focused, non-overlapping questions. Batches of "
            f"{MAX_SUBTOPICS + 1}-{MAX_SUBTOPICS_HARD_LIMIT} are queued; "
            f"larger batches are rejected without doing work).\n"
            f"{fetch_line}"
            "4. When available, use specialized search_[engine] tools for domain-specific searches "
            "(search_arxiv for science, search_pubmed for medical, etc.).\n"
            "5. Evidence policy: every factual claim, number, date, journal, "
            "method, or comparison must be supported by the retrieved sources "
            "and followed by its [N] citation. Do not fill gaps from memory, "
            "do not invent bibliographic metadata, and do not infer an impact "
            "factor or publication status unless a source explicitly states it. "
            "If the sources do not establish a claim, say that it could not be "
            "verified and omit the claim rather than guessing.\n"
            "If the user's request requires journal impact factors, use search_journal "
            "for relevant papers by source index. Use its reported metric and year, "
            "and mark unavailable or ambiguous results as unverified.\n"
            "6. When you have enough information, provide a comprehensive answer "
            "citing sources as [1], [2], etc. Keep each citation close to the "
            "claim it supports; one citation must not be used to imply support "
            "for unrelated claims.\n"
            "7. Cite every factual sentence and table row individually, including "
            "when summarizing one paper. Do not leave citations only in a heading "
            "or at the end of a multi-sentence paragraph. Abstracts guide initial "
            "checks; obtain body evidence for detailed claims. Do not describe "
            "an abstract or search snippet as a verified full-text reading.\n"
            f"{policy_addendum}"
        )

        # Create agent — may fail if model doesn't support tool calling.
        # create_agent() calls model.bind_tools(); ProcessingLLMWrapper overrides
        # bind_tools to re-wrap the bound model, so the wrapper's <think>-tag
        # stripping survives the agent loop here (fix #4804). Other Runnable
        # transforms still escape the wrapper (with_config/bind/stream delegate
        # via __getattr__ unstripped; `|` raises TypeError, no __or__), but none
        # are on this create_agent path — see config/llm_config.py.
        try:
            agent = create_agent(
                model=self.model,
                tools=tools,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            logger.exception("Failed to create LangGraph agent")
            return self._error_result(
                _scrub_tool_error(
                    f"Failed to create agent (model may not "
                    f"support tool calling): {exc}"
                )
            )

        # Stream agent execution
        minimum_iterations = 1 if getattr(self, "_allow_short_runs", False) else MIN_ITERATIONS
        effective_max = max(minimum_iterations, self.max_iterations)
        config = {"recursion_limit": effective_max * 2 + 1}
        iteration = 0
        final_content = ""
        agent_messages: list = []

        try:
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                config,
                stream_mode="updates",
            ):
                self.check_termination(CHECK_CONTEXT_AGENT_STREAM)

                run_deadline = getattr(self, "_run_deadline", None)
                if run_deadline is not None and time.monotonic() >= run_deadline:
                    logger.warning(
                        "LangGraph agent subsection deadline reached; synthesizing partial results"
                    )
                    self._update_progress(
                        "Subsection time limit reached; synthesizing partial results",
                        min(85, 10 + int((iteration / effective_max) * 75)),
                        {
                            "phase": "agent_timeout",
                            "iteration": iteration,
                            "effective_max_iterations": effective_max,
                        },
                    )
                    break

                if "agent" in chunk or "model" in chunk:
                    node_key = "agent" if "agent" in chunk else "model"
                    iteration += 1
                    progress = 10 + int((iteration / effective_max) * 75)
                    msgs = chunk[node_key].get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, AIMessage):
                            agent_messages.append(msg)
                            content = msg.content or ""
                            tool_calls = getattr(msg, "tool_calls", [])

                            # Surface the model's *thinking* output (the
                            # <think>…</think> reasoning) when reasoning
                            # mode is on. langchain-ollama puts the
                            # discarded thinking content into
                            # additional_kwargs["reasoning_content"]; we
                            # emit it as agent_reasoning so the thinking
                            # bubble shows the agent's actual rationale
                            # ("I should search for X because…") right
                            # before the next tool call fires. This is
                            # per-step (one emit per LLM round) —
                            # token-level streaming would require switching
                            # langgraph to stream_mode=["updates",
                            # "messages"] and capturing chunks inside agent
                            # nodes, which is a larger change.
                            reasoning_text = ""
                            if getattr(msg, "additional_kwargs", None):
                                reasoning_text = str(
                                    msg.additional_kwargs.get(
                                        "reasoning_content", ""
                                    )
                                    or ""
                                ).strip()
                            # Fall back to msg.content when the model
                            # emitted prose alongside tool_calls (rare for
                            # tool-calling LLMs — most emit only the tool
                            # call), but harmless when both apply.
                            if not reasoning_text and content and tool_calls:
                                reasoning_text = str(content).strip()
                            if reasoning_text:
                                self._update_progress(
                                    reasoning_text[:280],
                                    min(85, progress),
                                    {
                                        "phase": "agent_reasoning",
                                        "iteration": iteration,
                                    },
                                )

                            if tool_calls:
                                for tc in tool_calls:
                                    raw_name = tc.get("name", "")
                                    display_name = self._display_tool_name(
                                        raw_name
                                    )
                                    msg_text = self._format_tool_call_progress(
                                        tc, display_name
                                    )
                                    self._update_progress(
                                        msg_text,
                                        min(85, progress),
                                        {
                                            "phase": "tool_call",
                                            # Keep the stable tool id in
                                            # metadata; the friendly label
                                            # already lives in msg_text.
                                            "tool": raw_name,
                                            "iteration": iteration,
                                        },
                                    )
                            elif content:
                                # No tool calls = final answer
                                final_content = content

                elif "tools" in chunk:
                    msgs = chunk["tools"].get("messages", [])
                    for msg in msgs:
                        obs_event = self._observation_event(msg)
                        # _observation_event returns None when the tool
                        # result is a denial/error string ("Cannot fetch …"
                        # / "Error fetching …"); the WARNING in
                        # policy.py is the audit signal and the chat
                        # milestone would otherwise read as a successful
                        # page read whose content is a denial.
                        if obs_event is None:
                            continue
                        obs_message, obs_metadata = obs_event
                        self._update_progress(
                            obs_message,
                            min(
                                85,
                                10 + int((iteration / effective_max) * 75) + 3,
                            ),
                            obs_metadata,
                        )
                    # After every tool result, the agent immediately re-
                    # invokes the model to decide the next step. For
                    # thinking-mode LLMs (Qwen 3.x, deepseek-r1, etc.)
                    # that step can take 30+ seconds of silent <think>
                    # generation that gets stripped before display —
                    # leaving the last displayed line stale ("Result from
                    # web_search …") with no indication the agent is still
                    # working.
                    # Emit a contextual heartbeat so the user gets a real
                    # sense of progress (which iteration, how many sources
                    # collected, which tools are available) instead of
                    # a generic "Choosing next step…" spinner.
                    self._update_progress(
                        self._heartbeat_message(iteration),
                        min(
                            85,
                            10 + int((iteration / effective_max) * 75) + 4,
                        ),
                        {"phase": "agent_thinking", "iteration": iteration},
                    )

        except GraphRecursionError:
            logger.warning(
                "LangGraph agent hit recursion limit, synthesizing partial results"
            )
            if not final_content:
                final_content = self._synthesize_from_collector(query)
        except Exception as exc:
            logger.exception("LangGraph agent error")
            if not final_content:
                if self.collector.results:
                    final_content = self._synthesize_from_collector(query)
                else:
                    return self._error_result(self._format_agent_error(exc))

        if not final_content:
            if self.collector.results:
                final_content = self._synthesize_from_collector(query)
            else:
                final_content = NO_RESULTS_MESSAGE

        return self._finalize(
            query, final_content, iteration, nr_of_links, agent_messages
        )

    # -- Helpers ------------------------------------------------------------

    def _synthesize_from_collector(self, query: str) -> str:
        """Fallback synthesis when the agent was cut short."""
        # Check cancellation before any synthesis LLM work. This is the
        # fallback path for when the agent stream errored out; without an
        # early check, a cancel that arrived during the error path would
        # have to wait for the synthesis LLM call to complete before
        # terminating.
        self.check_termination(CHECK_CONTEXT_FALLBACK_SYNTHESIS)

        results = self.collector.results
        if not results:
            return "Research could not be completed within the iteration limit."
        summaries = []
        for r in results[:20]:
            summaries.append(
                f"[{r.get('index', '?')}] {r.get('title', '')}: "
                f"{r.get('snippet', '')}"
            )
        prompt = (
            f"Synthesize a comprehensive answer to: {query}\n\n"
            "Use only the evidence in the sources below. Every factual claim "
            "must have a nearby [N] citation. Do not invent missing details or "
            "metadata; if a point cannot be verified from these snippets, say "
            "it is unverified and leave it out.\n\n"
            f"Based on these sources:\n" + "\n".join(summaries)
        )
        try:
            response = self.model.invoke(prompt)
            return (
                response.content
                if hasattr(response, "content")
                else str(response)
            )
        except Exception as exc:
            logger.exception("Fallback synthesis failed")
            return _scrub_tool_error(
                f"Research collected {len(results)} sources but "
                f"synthesis failed: {exc}"
            )

    def _finalize(
        self,
        query: str,
        final_answer: str,
        iteration: int,
        nr_of_links: int,
        agent_messages: list,
    ) -> Dict[str, Any]:
        """Apply citation handling and build the return dict."""
        from research_verify.source_collection import sources_for_draft
        all_search_results, source_recovery = sources_for_draft(
            self.collector.results, self.all_links_of_system, final_answer
        )
        self._source_recovery = source_recovery
        from research_verify.research_spec import format_research_spec, parse_research_spec, report_spec_settings
        research_spec = parse_research_spec(query, report_spec_settings(self.get_setting))
        self._research_spec = research_spec
        field_evidence_preparation = {"status": "not_requested"}
        if research_spec.output_mode == "field_extraction" and research_spec.requested_fields:
            try:
                from research_verify.source_evidence import prepare_selected_evidence
                field_evidence_preparation = prepare_selected_evidence(
                    all_search_results,
                    limit=min(research_spec.requested_count or 6, 20),
                    egress_context=(
                        self._build_egress_context()
                        if hasattr(self, "_build_egress_context") else None
                    ),
                )
                from research_verify.evidence_cards import build_source_cards
                field_evidence_preparation["cards"] = build_source_cards(
                    all_search_results[:min(research_spec.requested_count or 6, 20)],
                    requested_fields=research_spec.requested_fields,
                )
            except Exception as exc:
                field_evidence_preparation = {
                    "status": "unavailable",
                    "error_type": type(exc).__name__,
                }
        self._field_evidence_preparation = field_evidence_preparation

        # --- research_verify: requirement 1 (DOI/PMID authenticity) --------
        # Runs on the deduplicated result set only; never blocks the report.
        self._attach_doi_verification(all_search_results)

        # --- research_verify: requirement 2 (year/IF/language constraints) --
        # Constraint matching is an advisory scope annotation.  It must never
        # turn a search miss into a publication gate or an instruction to
        # suppress otherwise useful evidence.
        self._attach_constraint_match(query, all_search_results)

        # Reuse only explicitly cited prior records. Missing/ambiguous labels
        # stay unresolved; neither the whole archive nor a guessed source is
        # substituted for them. Existing native source budgets still apply.
        if source_recovery["missing_ids"] or source_recovery["ambiguous_ids"]:
            logger.warning("Draft source lookup unresolved: missing={}, ambiguous={}",
                           source_recovery["missing_ids"], source_recovery["ambiguous_ids"])

        # Emit synthesis milestone if it is not an agent failure
        if final_answer != NO_RESULTS_MESSAGE:
            if not all_search_results and self.all_links_of_system:
                self._update_progress(
                    "No supplied source resolves the draft citations; preserving the draft",
                    90,
                    {
                        "phase": "synthesis",
                        "type": "milestone",
                        "new_sources": 0,
                        "accumulated_sources": len(self.all_links_of_system),
                        "citation_pass_skipped": True,
                    },
                )
            elif not all_search_results and not self.all_links_of_system:
                self._update_progress(
                    "No sources available for citation synthesis",
                    90,
                    {
                        "phase": "synthesis",
                        "type": "milestone",
                        "new_sources": 0,
                        "accumulated_sources": 0,
                        "citation_pass_skipped": True,
                    },
                )
            else:
                self._update_progress(
                    f"Synthesizing {len(all_search_results)} sources with citations",
                    90,
                    {"phase": "synthesis", "type": "milestone"},
                )

        synthesized_content = final_answer
        documents: list = []

        # Citation handling — only if we have results
        if all_search_results:
            try:
                scope_data = format_research_spec(research_spec)
                writer_query = query + ("\n\n" + scope_data if scope_data else "")
                citation_result = self.citation_handler.analyze_followup(
                    writer_query,
                    all_search_results,
                    previous_knowledge=final_answer,
                    nr_of_links=nr_of_links,
                )
                if isinstance(citation_result, dict):
                    synthesized_content = citation_result.get(
                        "content", citation_result.get("response", final_answer)
                    )
                    documents = citation_result.get("documents", [])
            except Exception:
                logger.warning(
                    "Citation handler failed, using raw agent answer"
                )

            if not re.search(r"\[\d", synthesized_content or ""):
                logger.warning(
                    f"Synthesis produced no inline [N] citation markers "
                    f"despite {len(all_search_results)} available sources — "
                    f"the report body will show no citations for this "
                    f"query ('{query[:80]}')"
                )

        # Check the actual synthesis BEFORE bibliography/metadata are appended.
        # Every output below uses this same revised body, including findings
        # consumed by the detailed report generator.
        checked_content, citation_checks = self._attach_citation_qc(
            synthesized_content, all_search_results
        )
        all_search_results = getattr(self, "_citation_evidence_sources", all_search_results)
        from research_verify.audit_io import publication_sources
        published_sources = publication_sources(all_search_results)
        if isinstance(getattr(self, "_citation_audit", None), dict):
            self._citation_audit["source_metadata_sha256"] = hashlib.sha256(
                json.dumps(published_sources, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()

        # Keep scope, identity, and optional fact-consistency results
        # in trace/metadata only.  The current biomedical flow deliberately
        # does not append rule-driven verification tables to the report body.
        # The renderer methods remain available for explicit diagnostics and
        # backwards-compatible callers, but are not part of publication text.
        current_knowledge = checked_content
        if isinstance(getattr(self, "_citation_audit", None), dict):
            self._citation_audit["sealed_content_sha256"] = hashlib.sha256(current_knowledge.encode()).hexdigest()
        formatted_output = self._format_citations(
            current_knowledge, all_search_results
        )

        # Build reasoning trace from agent messages
        reasoning_trace = []
        for msg in agent_messages:
            entry: Dict[str, Any] = {"role": "assistant"}
            if hasattr(msg, "content") and msg.content:
                entry["content"] = msg.content
            tool_calls = getattr(msg, "tool_calls", [])
            if tool_calls:
                entry["tool_calls"] = [
                    {"name": tc.get("name"), "args": tc.get("args", {})}
                    for tc in tool_calls
                ]
            reasoning_trace.append(entry)

        self._update_progress(
            "Research complete",
            100,
            {"phase": "complete", "type": "milestone", "iterations": iteration},
        )

        return {
            "findings": [
                {
                    "content": current_knowledge,
                    "question": query,
                    "search_results": all_search_results,
                    "documents": documents,
                }
            ],
            "iterations": iteration,
            "questions": {},
            "formatted_findings": formatted_output,
            "current_knowledge": current_knowledge,
            "final_report": {
                "content": current_knowledge,
                "content_sha256": hashlib.sha256(
                    current_knowledge.encode()
                ).hexdigest(),
                "verification": getattr(
                    self, "_citation_audit", {"status": "unverifiable"}
                ),
                "sources_for_publication": published_sources,
                "research_spec": research_spec.as_dict(),
                "field_evidence_preparation": field_evidence_preparation,
                "source_recovery": source_recovery,
            },
            "sources": list(dict.fromkeys([
                *self.collector.sources,
                *(source.get("link") or source.get("url") for source in all_search_results
                  if source.get("link") or source.get("url")),
            ])),
            "search_results": all_search_results,
            "documents": documents,
            "reasoning_trace": reasoning_trace,
            "error": None,
            "citation_qc": [
                c.model_dump() for c in getattr(self, "_citation_checks", [])
            ],
        }

    # -- research_verify helpers -------------------------------------------

    @staticmethod
    def _run_async(coro):
        """Run *coro* from the synchronous ``_finalize`` context.

        ``_finalize`` runs in a worker thread without a running event loop, so
        a plain ``asyncio.run`` is safe. If a loop ever happens to be running
        in this thread we fall back to a throw-away thread to avoid
        ``RuntimeError: event loop already running``.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _attach_doi_verification(self, sources: list[dict]) -> None:
        """Requirement 1: verify each source's DOI/PMID and stash the result.

        Mutates each source dict in place (``_verify`` / ``_verify_badge``).
        Silently degrades on any failure so the report always renders.
        """
        try:
            from research_verify import get_config
            from research_verify.doi_validator import DoiValidator, badge_for
            from research_verify.http_client import HttpClient
        except Exception as exc:  # package not shipped
            logger.warning(f"research_verify import failed: {exc}")
            return

        cfg = get_config()
        if not cfg.enable_verify or not cfg.module_enabled("doi_validation"):
            return
        if not sources:
            return

        async def _run():
            context = self._build_egress_context() if hasattr(self, "_build_egress_context") else None
            async with HttpClient(cfg, egress_context=context) as http:
                return await DoiValidator(http, cfg).verify_many(sources)

        try:
            results = self._run_async(_run())
        except Exception as exc:
            logger.warning(f"doi_validation skipped: {exc}")
            return

        for idx, vr in results.items():
            src = self.collector.find_by_index(idx)
            if src is None:
                continue
            src["_verify"] = vr.model_dump()
            src["_verify_badge"] = badge_for(vr)
        logger.info(f"doi_validation: verified {len(results)} sources")

    @staticmethod
    def _render_verify_section(sources: list[dict]) -> str:
        """Render the '文献真实性核验' Markdown table (empty when no data)."""
        rows = [s for s in sources if isinstance(s, dict) and s.get("_verify")]
        if not rows:
            return ""
        lines = [
            "### 文献真实性核验",
            "",
            "| # | 标题 | 状态 | 来源 | 备注 |",
            "|---|------|------|------|------|",
        ]
        for s in rows:
            v = s.get("_verify") or {}
            badge = s.get("_verify_badge", "❓未能核验")
            warnings = "; ".join(v.get("warnings") or []) or ""
            warnings = warnings.replace("|", "/")[:160]
            title = str(s.get("title", ""))[:80].replace("|", "/")
            lines.append(
                f"| {s.get('index', '?')} | {title} | {badge} | "
                f"{v.get('source', '')} | {warnings} |"
            )
        return "\n".join(lines)

    def _attach_constraint_match(
        self, query: str, sources: list[dict]
    ) -> bool:
        """Requirement 2: parse user constraints and match each source.

        Writes ``_constraint`` / ``_constraint_badge`` onto each source and
        The result is an advisory annotation only.  It never removes a source,
        changes the report body, or creates a publication gate.
        """
        try:
            from research_verify import get_config
            from research_verify.constraint_matcher import ConstraintMatcher
            from research_verify.models import ResearchConstraint
        except Exception as exc:
            logger.warning(f"research_verify import failed: {exc}")
            return False

        cfg = get_config()
        if not cfg.enable_verify or not cfg.module_enabled("constraint_match"):
            return False
        if not sources:
            return False

        try:
            from research_verify.research_spec import report_spec_settings
            matcher = ConstraintMatcher(cfg)
            settings = report_spec_settings(self.get_setting)
            # Journal metrics are selected by the jcr_mcp tool. Finalization
            # only records tool-produced annotations and does not infer a
            # journal constraint from prompt text.
            settings["min_if"] = None
            constraint = matcher.parse(query, settings)
            if constraint.is_empty:
                return False
            matches = matcher.match_many(sources, constraint)
        except Exception as exc:
            logger.warning(f"constraint_match skipped: {exc}")
            return False

        flagged = 0
        for idx, m in matches.items():
            src = self.collector.find_by_index(idx)
            if src is None:
                continue
            src["_constraint"] = m.model_dump()
            if m.detail.get("jcr_check"):
                src["_jcr_check"] = m.detail["jcr_check"]
                result = m.detail["jcr_check"]
                if result.get("status") == "found" and result.get("impact_factor") is not None:
                    src["impact_factor"] = result.get("impact_factor")
                    src["metric_year"] = result.get("metric_year")
                    src["passes_threshold"] = result.get("passes_threshold")
                    src["jcr_provenance"] = {
                        "source": "jcr_mcp",
                        "metric_year": result.get("metric_year"),
                        "metric_source": result.get("metric_source"),
                        "source_url": result.get("source_url"),
                        "status": result.get("status"),
                    }
            if m.excluded:
                src["_constraint_badge"] = "⚠️范围外/需复核"
                flagged += 1
            elif m.if_unknown:
                src["_constraint_badge"] = "⚠️JCR metric unavailable"
            elif m.detail.get("pending"):
                src["_constraint_badge"] = "❓条件待核验"
            else:
                src["_constraint_badge"] = "✅满足条件"
        self._constraint_spec = constraint
        logger.info(
            f"constraint_match: {flagged}/{len(matches)} sources flagged for scope review"
        )
        # Keep the historical return type for callers outside this class, but
        # do not expose an all-excluded gate to finalization.
        return False

    @staticmethod
    def _render_constraint_section(sources: list[dict]) -> str:
        rows = [s for s in sources if isinstance(s, dict) and s.get("_constraint")]
        if not rows:
            return ""
        lines = [
            "### 条件范围提示（仅供写作参考）",
            "",
            "| # | 期刊 | 年份 | IF | 结论 | 说明 |",
            "|---|------|------|----|------|------|",
        ]
        for s in rows:
            m = s.get("_constraint") or {}
            badge = s.get("_constraint_badge", "")
            detail = m.get("detail") or {}
            if_ = detail.get("if")
            notes = []
            if m.get("if_unknown"):
                notes.append("期刊IF未收录")
            if m.get("hard_violations"):
                notes.append("范围提示:" + ",".join(m["hard_violations"]))
            if detail.get("pending"):
                notes.append("待核验:" + ",".join(detail["pending"]))
            journal = str(s.get("journal", ""))[:40].replace("|", "/")
            lines.append(
                f"| {s.get('index', '?')} | {journal} | {s.get('year', '')} | "
                f"{if_ if if_ is not None else '—'} | {badge} | {'; '.join(notes)} |"
            )
        return "\n".join(lines)

    def _attach_citation_qc(
        self, report_text: str, sources: list[dict]
    ) -> tuple[str, list]:
        """Run the legacy citation check only as optional metadata.

        Returns ``(report_text, checks)``.  The current LDR flow keeps the
        generated body intact and does not append a body checklist or replace
        it with a withheld/error message.  Production disables this legacy
        audit; if an operator explicitly enables it for diagnostics, its
        result is stored outside the answer text.
        """
        self._citation_checks = []
        self._citation_evidence_sources = sources
        self._citation_publication_sources = sources
        self._citation_audit = {"status": "unverifiable"}
        if report_text == NO_RESULTS_MESSAGE:
            return report_text, []
        try:
            from research_verify import get_config
            from research_verify.citation_qc import CitationQc
        except Exception as exc:
            logger.warning(f"research_verify import failed: {exc}")
            self._citation_audit = {
                "status": "unavailable",
                "reason_code": "qc_import_error",
            }
            return report_text, []

        cfg = get_config()
        if not cfg.enable_verify or not cfg.module_enabled("citation_qc"):
            self._citation_audit = {"status": "disabled"}
            return report_text, []
        if not report_text:
            return report_text, []

        try:
            qc = CitationQc(
                judge_model=getattr(self, "model", None),
                cfg=cfg,
                review_model=getattr(self, "citation_review_model", None),
            )
            from research_verify.source_evidence import prepare_cited_evidence
            # The collector can resolve accumulated citations from earlier
            # detailed sections, even when this call collected no new sources.
            evidence_preparation = prepare_cited_evidence(
                qc.extract_claims(report_text), self.collector, cfg,
                egress_context=(
                    self._build_egress_context()
                    if hasattr(self, "_build_egress_context") else None
                ),
            ) if cfg.qc_require_body else {"status": "abstract_only_policy"}
            result = qc.verify_report(report_text, self.collector)
            from research_verify.audit_io import publication_sources
            self._citation_evidence_sources = qc.source_snapshot.records()
            self._citation_publication_sources = publication_sources(self._citation_evidence_sources)
            checks = result.original_checks
            self._citation_audit = result.model_dump(exclude={"content"})
            self._citation_audit["verified_body_chars"] = len(report_text)
            self._citation_audit["evidence_preparation"] = evidence_preparation
            self._citation_audit["rendered_content_sha256"] = hashlib.sha256(report_text.encode()).hexdigest()
            self._citation_audit["source_metadata_sha256"] = hashlib.sha256(
                json.dumps(self._citation_publication_sources, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            path = self._write_citation_qc_json(checks, {**self._citation_audit, "source_artifacts": qc.source_snapshot.records()})
            if path:
                self._citation_audit["evidence_artifact_file"] = path
            else:
                self._citation_audit["evidence_storage_status"] = "unavailable"
            self._citation_checks = checks
            logger.info(
                f"citation_qc: judged {len(checks)} claims "
                f"({sum(1 for c in checks if c.verdict == 'unsupported')} unsupported)"
            )
            # The audit is advisory metadata. Never rewrite or withhold the
            # generated answer at this boundary.
            return report_text, checks
        except Exception as exc:
            logger.warning("citation_qc failed: {}", type(exc).__name__)
            self._citation_audit = {"status": "unverifiable", "reason_code": "qc_error"}
            return report_text, []

    @staticmethod
    def _write_citation_qc_json(checks: list, audit: dict | None = None) -> str | None:
        try:
            from research_verify.audit_io import write_audit
            payload = dict(audit) if audit is not None else {"checks": [c.model_dump() for c in checks]}
            sources = payload.pop("source_artifacts", [])
            path = write_audit(payload, sources)
            logger.info(f"citation_qc audit written: {path}")
            return path
        except Exception as exc:
            logger.debug("citation_qc json write failed: {}", type(exc).__name__)
            return None

    @staticmethod
    def _format_agent_error(exc: BaseException) -> str:
        """Prefix the exception type so downstream rendering (and the
        `ErrorReportGenerator` pattern map) have a consistent shape to match
        on. The bare `str(exc)` produced by the catch-all loses the type,
        which makes deep LangChain / LangGraph failures hard to recognise.
        """
        # Scrub credentials before this error is rendered to the user. The
        # "Agent error: <Type>:" prefix stays at the front (no secrets, ahead
        # of any truncation) so the ErrorReportGenerator pattern map still
        # matches on the exception type.
        return _scrub_tool_error(f"Agent error: {type(exc).__name__}: {exc}")

    def _error_result(self, error: str) -> Dict[str, Any]:
        logger.error(f"LangGraph agent strategy error: {error}")
        self._update_progress(
            f"Error: {error}",
            100,
            {"phase": "error", "error": error, "status": "failed"},
        )
        return {
            "findings": [],
            "iterations": 0,
            "questions": {},
            "formatted_findings": f"Error: {error}",
            "current_knowledge": "",
            "sources": [],
            "search_results": [],
            "documents": [],
            "reasoning_trace": [],
            "error": error,
            "citation_qc": [],
        }

    def close(self):
        """No persistent resources to clean up."""
        pass
