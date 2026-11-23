"""Structured adapter over the vendored ``jcr_mcp`` database.

The upstream project is an MCP server whose public search tool returns
formatted text. DRA needs a source-bound, machine-readable result, so this
adapter keeps the upstream database/parser and adds conservative identity,
year, and threshold handling around it.
"""
from __future__ import annotations

from functools import lru_cache
import math
import os
from pathlib import Path
import re
from typing import Any

from .jcr_mcp import JCRDatabase
from .jcr_mcp.jcr_database import DATABASE_PATH


@lru_cache(maxsize=1)
def get_database() -> JCRDatabase:
    configured = os.environ.get("LDR_JCR_CATALOG_PATH")
    volume_path = Path(os.environ.get("LDR_DATA_DIR", "/data")) / "journal_data" / "jcr.db"
    path = Path(configured) if configured else volume_path if volume_path.is_file() else Path(DATABASE_PATH)
    if not path.is_file():
        raise FileNotFoundError("JCR catalog is missing")
    return JCRDatabase(str(path), read_only=True)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _float_metric(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if text.startswith("<") or text.startswith(">"):
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def passes_threshold(metric: Any, minimum: float | None, operator: str) -> bool | None:
    value = _float_metric(metric)
    if value is None or minimum is None:
        return None
    if operator == ">":
        return value > minimum
    if operator == "=":
        return value == minimum
    if operator == ">=":
        return value >= minimum
    return None


def lookup_source(
    source: dict[str, Any],
    *,
    minimum: float | None = None,
    operator: str = ">=",
    year: int | str | None = "latest",
) -> dict[str, Any]:
    """Resolve a collected journal by ISSN, or by an exact normalized title."""
    if minimum is not None:
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
            return {"status": "invalid_input", "missing_reason": "minimum_if_invalid"}
        minimum = float(minimum)
        if not math.isfinite(minimum) or minimum < 0:
            return {"status": "invalid_input", "missing_reason": "threshold_invalid"}
    if operator not in {">", ">=", "="}:
        return {"status": "invalid_input", "missing_reason": "threshold_invalid"}
    requested_year = str(year) if year not in (None, "") else "latest"
    journal = str(
        source.get("journal")
        or source.get("journal_ref")
        or source.get("container_title")
        or ""
    ).strip()
    issns = tuple(dict.fromkeys(
        identifier for field in ("issn", "eissn", "essn")
        if re.fullmatch(r"[0-9]{7}[0-9X]",
                        identifier := str(source.get(field) or "").strip().replace("-", "").upper())
    ))
    if not journal and not issns:
        return {
            "status": "metric_unavailable",
            "missing_reason": "journal_identity_missing",
            "impact_factor": None,
            "passes_threshold": None,
            "requested_metric_year": requested_year,
        }
    try:
        database = get_database()
        exact = database.search_journal(journal, issns=issns) if issns else []
        match_method = "issn" if exact else "journal_title"
        if not exact and journal:
            exact = [row for row in database.search_journal(journal)
                     if _norm(row.journal_name) == _norm(journal) and (not issns or not row.issns)]
    except Exception as exc:
        return {
            "status": "metric_unavailable",
            "missing_reason": ("jcr_catalog_missing" if isinstance(exc, FileNotFoundError)
                               else "jcr_mcp_initialization_failed"),
            "error_type": type(exc).__name__,
            "impact_factor": None,
            "passes_threshold": None,
            "requested_metric_year": requested_year,
        }
    if not exact:
        return {
            "status": "metric_unavailable",
            "missing_reason": "journal_not_found",
            "query": journal,
            "impact_factor": None,
            "passes_threshold": None,
            "requested_metric_year": requested_year,
        }
    metric_rows = [row for row in exact if _float_metric(row.impact_factor) is not None]
    if match_method == "issn" and len({_norm(row.journal_name) for row in metric_rows}) > 1:
        return {"status": "ambiguous", "missing_reason": "conflicting_journal_identifiers",
                "query": journal, "impact_factor": None, "passes_threshold": None,
                "requested_metric_year": requested_year}
    if requested_year != "latest":
        try:
            exact = [row for row in metric_rows if str(row.year) == str(int(requested_year))]
        except (TypeError, ValueError):
            exact = []
    else:
        years = [int(row.year) for row in metric_rows if row.year and row.year.isdigit()]
        if years:
            latest = max(years)
            exact = [row for row in metric_rows if str(row.year) == str(latest)]
    if not exact:
        return {
            "status": "metric_unavailable",
            "missing_reason": "metric_year_unavailable",
            "query": journal,
            "impact_factor": None,
            "passes_threshold": None,
            "requested_metric_year": requested_year,
        }
    if len(exact) != 1:
        return {
            "status": "ambiguous",
            "missing_reason": "multiple_exact_jcr_records",
            "query": journal,
            "available_metric_years": sorted({row.year for row in exact}),
            "impact_factor": None,
            "passes_threshold": None,
            "requested_metric_year": requested_year,
        }
    row = exact[0]
    value = _float_metric(row.impact_factor)
    metric_year = int(row.year) if row.year and row.year.isdigit() else row.year
    return {
        "status": "found" if value is not None else "metric_unavailable",
        "missing_reason": None if value is not None else "metric_not_numeric",
        "query": journal,
        "journal": row.journal_name,
        "journal_match": match_method,
        "impact_factor": value,
        "metric_year": metric_year,
        "requested_metric_year": requested_year,
        "passes_threshold": passes_threshold(value, minimum, operator),
        "minimum_if": minimum,
        "threshold_operator": operator if minimum is not None else None,
        "partition": row.partition,
        "category": row.category,
        "warning_status": row.warning_status,
        "metric_source": "jcr_mcp ShowJCR JCR table",
        "source_url": "https://github.com/hitfyd/ShowJCR",
    }
