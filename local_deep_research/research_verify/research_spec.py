"""Topic-independent query contract for evidence-grounded research tasks."""
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
    """Parse only explicit IF/JIF comparison syntax; never substring-match IF."""
    match = _IF_ASCII_RE.search(text or "") or _IF_ZH_RE.search(text or "")
    if not match:
        return None, None
    # Chinese "影响因子10分以上" is an explicit lower-bound form.
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
    """Normalize an explicitly supplied label, never words from a question."""
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    aliases = {"english": "en", "eng": "en", "chinese": "zh", "chi": "zh", "zho": "zh"}
    value = aliases.get(value, value)
    return value if re.fullmatch(r"[a-z]{2,3}", value) else None


def parse_research_spec(query: str, settings=None) -> ResearchSpec:
    """Validate explicit planning settings; natural-language intent stays unknown.

    The original question is passed intact to the agent/writer. Substring
    matches cannot establish language, paper count, requested fields, dates,
    or a scientific task type. Literal IF syntax is recorded but never applied.
    """
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
        for name in ("year_from", "year_to"):
            values.pop(name, None); provenance.pop(name, None)
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
        values.pop("count_relation", None); provenance.pop("count_relation", None)
    elif "count_relation" not in values:
        # A bare number does not say whether the user means an exact count,
        # lower bound, upper bound, or ranking.  Keep the number while making
        # the missing relation explicit so downstream writers cannot claim
        # completion from a source-pool size.
        values["count_relation"] = "unknown"
        unresolved.append("count_relation")
    min_if, operator = parse_if_constraint(str(query or ""))
    return ResearchSpec(**values, min_if_mentioned=min_if, if_operator=operator,
                        intent_status="explicit_partial" if provenance else "unknown",
                        provenance=provenance, unresolved=tuple(unresolved))


def report_spec_settings(get_setting):
    """One shared adapter for ordinary and detailed-report planning settings."""
    names = ("language", "year_from", "year_to", "requested_count", "count_relation",
             "requested_fields", "output_mode", "protocol_requested")
    return {name: get_setting("report." + name, None) for name in names}


def format_research_spec(spec: ResearchSpec) -> str:
    """Render supplied data only; unknown intent adds no instruction block."""
    values = {name: getattr(spec, name) for name in spec.provenance}
    if spec.requested_count is not None:
        values.setdefault("requested_count", spec.requested_count)
        values.setdefault("count_relation", spec.count_relation or "unknown")
    if not values and not spec.unresolved:
        return ""
    # Keep an explicit language setting machine-readable at the writer boundary.
    # This is advisory scope metadata, not a source filter or publication gate:
    # the writer still has to use each record's authoritative language field and
    # preserve mismatches/unknowns as labelled evidence limits.
    policy = {}
    if spec.language:
        policy["language"] = {
            "requested": spec.language,
            "match_field": "authoritative_source_language",
            "matching_records": "may support requested-language findings",
            "mismatch_records": "label as supplemental; do not present as satisfying the language scope",
            "unknown_records": "state language unknown rather than infer from title, prompt, journal, or affiliation",
            "no_matches": "state that no supplied record has a confirmed language match before any supplement",
        }
    count_policy = {}
    if spec.requested_count is not None:
        count_policy = {
            "requested_count": spec.requested_count,
            "count_relation": spec.count_relation or "unknown",
            "completion_claim": (
                "Do not claim the requested count was satisfied until the relation "
                "is explicit and the matching records are confirmed."
            ),
        }
    return "Explicit report settings (planning data, not source evidence):\n" + json.dumps(
        {"values": values, "provenance": spec.provenance, "unresolved": list(spec.unresolved),
         "evidence_scope_policy": policy, "count_policy": count_policy},
        ensure_ascii=False)


