"""Requirement 2 -- year / impact-factor / language hard-constraint matching.

Parses a user query (plus optional explicit settings) into a
:class:`ResearchConstraint`, then checks each deduplicated source against it.

Hard constraints (year range, minimum IF, language) that a source violates are
recorded in ``ConstraintMatch.hard_violations`` so the report can flag/drop the
source *without* silently relaxing the condition.

Impact factors come from the read-only ``journal_quality`` SQLite DB.  A crucial
detail from the baseline: some mainstream journals carry an ``impact_factor`` of
exactly ``0.0`` (not ``None``) -- ``0.0`` therefore means "not indexed / unknown"
and must set ``if_unknown`` rather than be compared as a real value.
"""

from __future__ import annotations

import argparse
import json
import re

from loguru import logger

from .config import VerifyConfig, get_config
from .models import ConstraintMatch, ResearchConstraint
from .textutil import first_nonempty, first_year, normalize_title

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_IF_RE = re.compile(r"\bIF\s*[>≥>=]+\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_IF_RE2 = re.compile(r"影响因子\s*[>≥>=>]+\s*(\d+(?:\.\d+)?)")
_EN_WORDS = ("英文", "英语", "english")
_ZH_WORDS = ("中文", "汉语", "chinese")

# Engines that only ever return English-language literature.
_ENGLISH_ENGINES = {"pubmed", "openalex", "crossref", "arxiv", "semantic_scholar"}


class ConstraintMatcher:
    """Parse and apply user hard-constraints to sources."""

    def __init__(self, cfg: VerifyConfig | None = None, model=None) -> None:
        self._cfg = cfg or get_config()
        self._model = model
        self._if_cache: dict[str, float | None] = {}

    # -- parsing ------------------------------------------------------------
    def parse(self, user_query: str, settings: dict | None = None) -> ResearchConstraint:
        """Extract a constraint from explicit settings first, then the query.

        LLM extraction is attempted only when regexes find nothing on a field;
        any LLM failure falls back to the regex result (or no constraint).
        """
        c = ResearchConstraint()
        settings = settings or {}

        # explicit settings win
        if settings.get("year_from") is not None or settings.get("year_to") is not None:
            c.year_from = _as_int(settings.get("year_from"))
            c.year_to = _as_int(settings.get("year_to"))
        if settings.get("min_if") is not None:
            c.min_if = _as_float(settings.get("min_if"))
        if settings.get("language"):
            c.language = str(settings["language"]).lower()

        text = user_query or ""
        if c.year_from is None and c.year_to is None:
            years = [int(m.group(0)) for m in _YEAR_RE.finditer(text)]
            if years:
                # A single year is treated as a lower bound ("2026年" == from 2026).
                c.year_from = min(years)
                c.year_to = max(years) if len(years) > 1 else None
        if c.min_if is None:
            m = _IF_RE.search(text) or _IF_RE2.search(text)
            if m:
                c.min_if = float(m.group(1))
        if c.language is None:
            low = text.lower()
            if any(w in low or w in text for w in _EN_WORDS):
                c.language = "en"
            elif any(w in low or w in text for w in _ZH_WORDS):
                c.language = "zh"

        if c.is_empty and self._model is not None:
            self._try_llm_parse(text, c)
        return c

    def _try_llm_parse(self, text: str, c: ResearchConstraint) -> None:
        prompt = (
            "Extract publication constraints from the query as strict JSON with "
            "keys year_from, year_to, min_if, language (values numeric/string or null). "
            "Only output JSON.\n\nQuery: " + text[:1000]
        )
        try:
            resp = self._model.invoke(prompt)
            raw = getattr(resp, "content", str(resp))
            data = json.loads(_extract_json(raw))
            c.year_from = _as_int(data.get("year_from")) or c.year_from
            c.year_to = _as_int(data.get("year_to")) or c.year_to
            c.min_if = _as_float(data.get("min_if")) or c.min_if
            c.language = (data.get("language") or c.language)
        except Exception as exc:
            logger.debug(f"constraint LLM parse failed, using regex only: {exc}")

    # -- matching -----------------------------------------------------------
    def match(self, source: dict, c: ResearchConstraint) -> ConstraintMatch:
        """Check one source against *c*; never raises."""
        m = ConstraintMatch()
        if c.is_empty:
            return m

        if c.year_from is not None or c.year_to is not None:
            year = first_year(source)
            if year is None:
                m.year_ok = None
            elif c.year_from is not None and year < c.year_from:
                m.year_ok = False
                m.hard_violations.append("year")
            elif c.year_to is not None and year > c.year_to:
                m.year_ok = False
                m.hard_violations.append("year")
            else:
                m.year_ok = True

        if c.min_if is not None:
            if_ = self._lookup_if(source)
            m.detail["if"] = if_
            if if_ is None:
                m.if_unknown = True  # not indexed OR impact_factor == 0.0
            elif if_ < c.min_if:
                m.if_ok = False
                m.hard_violations.append("if")
            else:
                m.if_ok = True

        if c.language is not None:
            lang = self._source_language(source)
            if lang is None:
                m.lang_ok = None
            elif lang != c.language:
                m.lang_ok = False
                m.hard_violations.append("language")
            else:
                m.lang_ok = True

        return m

    def match_many(
        self, sources: list[dict], c: ResearchConstraint
    ) -> dict[int, ConstraintMatch]:
        """Match a batch, pre-loading the IF cache in one DB round-trip."""
        if c.is_empty:
            return {}
        if c.min_if is not None:
            self._preload_if(sources)
        out: dict[int, ConstraintMatch] = {}
        for src in sources:
            if not isinstance(src, dict):
                continue
            idx = src.get("index")
            if idx is None:
                continue
            try:
                out[int(idx)] = self.match(src, c)
            except Exception as exc:
                logger.warning(f"constraint match failed for index {idx}: {exc}")
        return out

    # -- impact factor ------------------------------------------------------
    def _preload_if(self, sources: list[dict]) -> None:
        names = [
            str(first_nonempty(s, ("journal", "journal_ref", "container_title")) or "")
            for s in sources
            if isinstance(s, dict)
        ]
        names = [n for n in names if n]
        if not names:
            return
        try:
            from local_deep_research.journal_quality.db import get_db

            hits = get_db().lookup_sources_batch(names)
        except Exception as exc:
            logger.warning(f"journal_quality lookup failed: {exc}")
            return
        for name, row in hits.items():
            self._if_cache[normalize_title(name)] = _valid_if(row.get("impact_factor"))

    def _lookup_if(self, source: dict) -> float | None:
        name = str(first_nonempty(source, ("journal", "journal_ref", "container_title")) or "")
        if not name:
            return None
        key = normalize_title(name)
        if key in self._if_cache:
            return self._if_cache[key]
        self._preload_if([source])
        return self._if_cache.get(key)

    @staticmethod
    def _source_language(source: dict) -> str | None:
        lang = first_nonempty(source, ("language", "lang"))
        if lang:
            return str(lang).lower()[:2]
        engine = str(source.get("source_engine", "")).lower()
        if engine in _ENGLISH_ENGINES:
            return "en"
        return None


def _valid_if(value) -> float | None:
    """Return the IF, treating ``None`` and ``0.0`` as 'unknown'."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _as_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip())
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start : end + 1] if start != -1 and end != -1 else raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="research_verify constraint matcher")
    parser.add_argument("--query", required=True)
    parser.add_argument("--journal", default="Nature")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args(argv)
    c = ConstraintMatcher().parse(args.query)
    print("parsed constraint:", c.model_dump())
    src = {"index": "1", "journal": args.journal, "year": args.year or c.year_from or 2020}
    print("match:", json.dumps(ConstraintMatcher().match(src, c).model_dump(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
