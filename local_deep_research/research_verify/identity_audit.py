"""Structured report-to-source identity comparison.

Callers provide citation-linked, coordinate-preserving report mentions and an
authoritative source registry.  This module compares declared bibliographic
fields without parsing rendered prompt delimiters, deleting prose, or imposing
publication gates.  Missing metadata remains ``unknown``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Iterable


IDENTITY_FIELDS = ("journal", "year", "authors", "publication_type", "publication_state")


@dataclass(frozen=True)
class IdentityMention:
    mention_id: str
    source_id: int | str
    role: str = "bibliographic_identity"
    claims: Mapping[str, Any] = field(default_factory=dict)
    report_start: int | None = None
    report_end: int | None = None
    report_text_sha256: str = ""

    def __post_init__(self):
        object.__setattr__(self, "source_id", str(self.source_id))


@dataclass(frozen=True)
class AuthoritativeIdentity:
    source_id: int | str
    fields: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "source_id", str(self.source_id))


def _normalise(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "|".join(sorted(_normalise(v) for v in value if _normalise(v)))
    return " ".join(str(value).casefold().replace("&", "and").split())


def _compare_value(claimed: Any, authoritative: Any) -> str:
    if claimed in (None, "", [], {}):
        return "unknown"
    if authoritative in (None, "", [], {}):
        return "unknown"
    if _normalise(claimed) == _normalise(authoritative):
        return "match"
    return "mismatch"


def audit_identity_mentions(
    mentions: Iterable[IdentityMention],
    registry: Mapping[str, AuthoritativeIdentity],
) -> tuple[Mapping[str, Any], ...]:
    """Compare each declared identity field and preserve source provenance."""
    results = []
    for mention in mentions:
        source = registry.get(str(mention.source_id))
        if source is None:
            results.append({
                "mention_id": mention.mention_id,
                "source_id": str(mention.source_id),
                "role": mention.role,
                "status": "unknown",
                "field_results": {field: {"status": "unknown", "claimed": mention.claims.get(field), "authoritative": None} for field in IDENTITY_FIELDS},
                "provenance": {"source_registry": "missing"},
            })
            continue
        field_results = {}
        for field_name in IDENTITY_FIELDS:
            claimed = mention.claims.get(field_name)
            authoritative = source.fields.get(field_name)
            field_results[field_name] = {
                "status": _compare_value(claimed, authoritative),
                "claimed": claimed,
                "authoritative": authoritative,
            }
        statuses = {row["status"] for row in field_results.values()}
        overall = "mismatch" if "mismatch" in statuses else ("unknown" if statuses <= {"unknown", "match"} and "match" not in statuses else "match")
        results.append({
            "mention_id": mention.mention_id,
            "source_id": str(mention.source_id),
            "role": mention.role,
            "status": overall,
            "field_results": field_results,
            "report_start": mention.report_start,
            "report_end": mention.report_end,
            "report_text_sha256": mention.report_text_sha256,
            "provenance": dict(source.provenance),
        })
    return tuple(results)
