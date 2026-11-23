"""Advisory year, language, and model-selected jcr_mcp scope matching."""
from __future__ import annotations

import math

from .config import VerifyConfig, get_config
from .jcr_adapter import passes_threshold
from .models import ConstraintMatch, ResearchConstraint
from .research_spec import parse_research_spec
from .textutil import first_nonempty, first_year


class ConstraintMatcher:
    """Annotate sources without deleting or automatically querying journals."""

    def __init__(self, cfg: VerifyConfig | None = None, model=None) -> None:
        self._cfg = cfg or get_config()
        self._model = model

    def parse(self, user_query: str, settings: dict | None = None) -> ResearchConstraint:
        settings = settings if isinstance(settings, dict) else {}
        spec = parse_research_spec("", settings)
        c = ResearchConstraint(year_from=spec.year_from, year_to=spec.year_to,
                               language=spec.language, is_hard_default=False,
                               provenance=dict(spec.provenance), unresolved=list(spec.unresolved))
        if not c.provenance and str(user_query or "").strip():
            c.unresolved.append("query_intent_not_structured")
        if settings.get("min_if") is not None:
            try:
                value = float(settings["min_if"])
            except (TypeError, ValueError):
                value = None
            operator = settings.get("if_operator", ">=")
            if value is not None and math.isfinite(value) and value >= 0 and operator in {">", ">=", "="}:
                c.min_if = value
                c.if_operator = operator
                c.min_if_inclusive = operator != ">"
                c.provenance["min_if"] = "explicit_settings"
            else:
                c.unresolved.append("min_if")
        return c

    def match(self, source: dict, c: ResearchConstraint) -> ConstraintMatch:
        m = ConstraintMatch(detail={"scope_provenance": dict(c.provenance)})
        if c.is_empty:
            return m
        if c.year_from is not None or c.year_to is not None:
            year = first_year(source)
            if year is None:
                m.year_ok = None
            elif c.year_from is not None and year < c.year_from:
                m.year_ok = False; m.hard_violations.append("year")
            elif c.year_to is not None and year > c.year_to:
                m.year_ok = False; m.hard_violations.append("year")
            else:
                m.year_ok = True
        if c.min_if is not None:
            result = source.get("_jcr_check")
            if not isinstance(result, dict):
                result = {"status": "unverified", "missing_reason": "jcr_mcp_check_not_selected",
                          "impact_factor": None, "passes_threshold": None}
            m.detail["jcr_check"] = result
            metric = result.get("impact_factor")
            m.detail["if"] = metric
            # Older receipts did not carry a status. A numeric IF from such a
            # receipt can still be compared against the current constraint.
            passes = (passes_threshold(metric, c.min_if, c.if_operator)
                      if result.get("status", "found") == "found" else None)
            if passes is None:
                m.if_unknown = True
            elif passes is False:
                m.if_ok = False; m.hard_violations.append("if")
            else:
                m.if_ok = True
        if c.language is not None:
            lang = self._source_language(source)
            if lang is None:
                m.lang_ok = None
            elif lang != c.language:
                m.lang_ok = False; m.hard_violations.append("language")
            else:
                m.lang_ok = True
        pending = list(c.unresolved)
        if (c.year_from is not None or c.year_to is not None) and m.year_ok is None:
            pending.append("publication_year")
        if c.language is not None and m.lang_ok is None:
            pending.append("language")
        if c.min_if is not None and m.if_ok is None:
            pending.append("impact_factor")
        if pending:
            m.detail.update(pending=True, unresolved=pending)
        return m

    def match_many(self, sources: list[dict], c: ResearchConstraint) -> dict[int, ConstraintMatch]:
        if c.is_empty:
            return {}
        out: dict[int, ConstraintMatch] = {}
        for src in sources:
            if not isinstance(src, dict) or src.get("index") is None:
                continue
            try:
                out[int(src["index"])] = self.match(src, c)
            except Exception:
                continue
        return out

    @staticmethod
    def _source_language(source: dict) -> str | None:
        lang = first_nonempty(source, ("language", "lang"))
        aliases = {"eng": "en", "en": "en", "english": "en",
                   "chi": "zh", "zho": "zh", "zh": "zh", "chinese": "zh"}
        return aliases.get(str(lang).strip().lower()) if lang else None


def main(argv: list[str] | None = None) -> int:
    import argparse, json
    parser = argparse.ArgumentParser(); parser.add_argument("--query", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(ConstraintMatcher().parse(args.query).model_dump(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
