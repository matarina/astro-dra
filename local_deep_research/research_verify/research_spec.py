"""Topic-independent planning metadata for evidence-grounded research tasks."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re


@dataclass(frozen=True)
class ResearchSpec:
    language: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    requested_count: int | None = None
    count_relation: str | None = None
    requested_fields: tuple[str, ...] = field(default_factory=tuple)
    output_mode: str | None = None
    protocol_requested: bool | None = None
    min_if_mentioned: float | None = None
    if_operator: str | None = None
    if_deferred: bool = True
    intent_status: str = "unknown"
    provenance: dict[str, str] = field(default_factory=dict)
    unresolved: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self):
        data = asdict(self)
        data["requested_fields"] = list(self.requested_fields)
        return data


_IF_ASCII_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<label>IF|JIF)(?![A-Za-z0-9])\s*"
    r"(?P<op>>=|≥|>|=)\s*(?P<value>\d+(?:\.\d+)?)", re.I
)
_IF_ZH_RE = re.compile(
    r"影响因子\s*(?:(?P<op>>=|≥|>|=|至少|不低于|大于)\s*)?"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?:分以上|分及以上)?"
)


def parse_if_constraint(text: str) -> tuple[float | None, str | None]:
    """Parse only explicit IF/JIF comparison syntax."""
    match = _IF_ASCII_RE.search(text or "") or _IF_ZH_RE.search(text or "")
    if not match:
        return None, None
    op = match.groupdict().get("op") or (">=" if "分以上" in match.group(0) else None)
    op = {"至少": ">=", "不低于": ">=", "大于": ">", "≥": ">="}.get(op, op)
    if op is None:
        return None, None
    return float(match.group("value")), op


def _integer(value, minimum=1, maximum=9999):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) or (isinstance(value, str) and re.fullmatch(r"[0-9]+", value)):
        number = int(value)
        return number if minimum <= number <= maximum else None
    return None


def normalize_language(value):
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    value = {"english": "en", "eng": "en", "chinese": "zh", "chi": "zh", "zho": "zh"}.get(value, value)
    return value if re.fullmatch(r"[a-z]{2,3}", value) else None


def parse_research_spec(query: str, settings=None) -> ResearchSpec:
    """Validate explicit planning settings and retain unresolved scope."""
    configured = settings if isinstance(settings, dict) else {}
    values = {}
    provenance = {}
    unresolved = []
    validators = {
        "language": normalize_language,
        "year_from": lambda x: _integer(x, 1, 9999),
        "year_to": lambda x: _integer(x, 1, 9999),
        "requested_count": lambda x: _integer(x, 1, 10000),
        "output_mode": lambda x: x if isinstance(x, str) and x in {
            "literature_review", "field_extraction", "protocol", "focused_comparison"} else None,
        "protocol_requested": lambda x: x if isinstance(x, bool) else None,
        "count_relation": lambda x: x if isinstance(x, str) and x in {
            "at_most", "at_least", "top", "requested", "exact", "unknown"} else None,
    }
    for name, validate in validators.items():
        raw = configured.get(name)
        if raw is None:
            continue
        value = validate(raw)
        if value is None:
            unresolved.append(name)
        else:
            values[name] = value
            provenance[name] = "explicit_settings"
            if name == "count_relation" and value == "unknown":
                unresolved.append("count_relation")
    if values.get("year_from", 0) > values.get("year_to", 9999):
        values.pop("year_from", None)
        values.pop("year_to", None)
        provenance.pop("year_from", None)
        provenance.pop("year_to", None)
        unresolved.append("year_range")
    raw_fields = configured.get("requested_fields")
    if raw_fields is not None:
        if isinstance(raw_fields, (list, tuple)) and all(
                isinstance(x, str) and x.strip() and len(x) <= 80 for x in raw_fields):
            values["requested_fields"] = tuple(dict.fromkeys(x.strip() for x in raw_fields))
            provenance["requested_fields"] = "explicit_settings"
        else:
            unresolved.append("requested_fields")
    if "requested_count" not in values:
        values.pop("count_relation", None)
        provenance.pop("count_relation", None)
    elif "count_relation" not in values:
        values["count_relation"] = "unknown"
        unresolved.append("count_relation")
    min_if, operator = parse_if_constraint(str(query or ""))
    return ResearchSpec(**values, min_if_mentioned=min_if, if_operator=operator,
                        intent_status="explicit_partial" if provenance else "unknown",
                        provenance=provenance, unresolved=tuple(unresolved))


def format_research_spec(spec: ResearchSpec) -> str:
    """Render supplied planning metadata without inventing source evidence."""
    values = {name: getattr(spec, name) for name in spec.provenance}
    if spec.requested_count is not None:
        values.setdefault("requested_count", spec.requested_count)
        values.setdefault("count_relation", spec.count_relation or "unknown")
    if not values and not spec.unresolved:
        return ""
    return "Explicit report settings (planning data, not source evidence):\n" + json.dumps(
        {"values": values, "provenance": spec.provenance, "unresolved": list(spec.unresolved)},
        ensure_ascii=False)


__all__ = ["ResearchSpec", "format_research_spec", "normalize_language", "parse_if_constraint", "parse_research_spec"]
