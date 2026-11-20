"""Observable output completeness, separate from semantic correctness."""
from __future__ import annotations


def output_completeness(content: str | None, finish_reason: str | None) -> str:
    if not isinstance(content, str) or not content.strip():
        return "empty"
    if finish_reason == "length":
        return "truncated"
    if finish_reason == "stop":
        return "complete"
    # Missing historical finish reasons and tool/filter terminations do not
    # establish completion of a final answer. Never infer it from token count.
    return "unknown"
