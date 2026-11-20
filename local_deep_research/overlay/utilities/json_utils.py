"""
Centralized utilities for extracting and parsing JSON from LLM responses.

Provides two public functions:
- get_llm_response_text: Extract text from LLM response objects
- extract_json: Parse JSON from LLM-generated text with robust cleaning
"""

import json
import re
from typing import Optional, Type, Union

from loguru import logger

from .search_utilities import remove_think_tags as _remove_think_tags


def get_llm_response_text(response) -> str:
    """Extract text content from an LLM response object.

    Handles LangChain AIMessage (.content), plain text responses (.text),
    list-type content blocks (Anthropic extended-thinking / tool-use, where
    ``.content`` is a list of blocks), and arbitrary objects (via str()).
    Removes <think> tags from the output.

    Args:
        response: LLM response object, string, or None.

    Returns:
        Extracted text with think tags removed. Empty string for None input.
    """
    if response is None:
        return ""
    if hasattr(response, "content") and response.content is not None:
        raw = response.content
    elif hasattr(response, "text") and response.text is not None:
        raw = response.text
    else:
        raw = str(response)
    if isinstance(raw, list):
        # Anthropic-style content blocks, e.g.
        # [{"type": "text", "text": "..."}, {"type": "tool_use", ...}].
        # Extract and join the text so downstream string ops get clean text
        # rather than the list's Python repr (the #4615 data-corruption bug).
        raw = _coerce_content_blocks(raw)
    if not isinstance(raw, str):
        raw = str(raw)
    return _remove_think_tags(raw)


def _coerce_content_blocks(blocks: list) -> str:
    """Join the text from a list of LLM content blocks into a plain string.

    Some providers (notably Anthropic, and some LangChain paths) return
    ``message.content`` as a list of blocks rather than a string — for
    example ``[{"type": "text", "text": "Paris"}, {"type": "tool_use", ...}]``.
    Keep only the textual parts; skip non-text blocks (tool_use, thinking,
    etc.) so callers that then ``.strip()`` / ``.split()`` operate on real
    text instead of the list's ``repr()``.

    Accepts blocks that are plain strings, dicts with a ``"text"`` key (when
    ``type`` is ``"text"`` or unset), or objects exposing a ``.text`` str
    attribute. Returns ``""`` for an empty/textless list.
    """
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type", "text") == "text" and isinstance(
                block.get("text"), str
            ):
                parts.append(block["text"])
        else:
            text_attr = getattr(block, "text", None)
            if isinstance(text_attr, str):
                parts.append(text_attr)
    return "".join(parts)


def extract_json(
    text: str,
    expected_type: Optional[Type] = None,
) -> Optional[Union[dict, list]]:
    """Extract and parse JSON from LLM-generated text.

    Applies a cleaning pipeline to handle common LLM output patterns:
    code fences, think tags, prose surrounding JSON, and minor artifacts.

    Args:
        text: Raw text potentially containing JSON.
        expected_type: Expected JSON type (dict or list). If specified,
            bracket extraction is ordered to prefer the matching type.
            None accepts either type.

    Returns:
        Parsed dict or list, or None if no valid JSON found.
    """
    if not text or not text.strip():
        return None

    text = text.strip()
    text = _strip_code_fences(text)
    text = _remove_think_tags(text)

    # Step 1: Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, (dict, list)):
            if expected_type is None or isinstance(result, expected_type):
                return result
            # Type mismatch — fall through to bracket extraction
    except (json.JSONDecodeError, ValueError):
        pass

    # Step 2: Bracket extraction ordered by expected_type
    if expected_type is list:
        bracket_pairs = [("[", "]"), ("{", "}")]
    elif expected_type is dict:
        bracket_pairs = [("{", "}"), ("[", "]")]
    else:
        bracket_pairs = [("{", "}"), ("[", "]")]

    for open_char, close_char in bracket_pairs:
        extracted = _extract_by_brackets(text, open_char, close_char)
        if extracted is None:
            continue

        # Try parsing the extracted substring
        try:
            result = json.loads(extracted)
            if isinstance(result, (dict, list)):
                if expected_type is None or isinstance(result, expected_type):
                    return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Try cleaning LLM artifacts and retrying
        cleaned = _clean_llm_json_artifacts(extracted)
        if cleaned != extracted:
            try:
                result = json.loads(cleaned)
                if isinstance(result, (dict, list)):
                    if expected_type is None or isinstance(
                        result, expected_type
                    ):
                        return result
            except (json.JSONDecodeError, ValueError):
                pass

    logger.debug("No valid JSON found in text")
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from text.

    Uses split-based extraction (not startswith) to handle fences
    appearing mid-text with surrounding prose.
    """
    if "```json" in text:
        parts = text.split("```json")
        if len(parts) > 1:
            return parts[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return text


def _extract_by_brackets(
    text: str, open_char: str, close_char: str
) -> Optional[str]:
    """Extract substring between outermost matching brackets.

    Uses find()/rfind() which is equivalent to re.search with re.DOTALL
    for bracket matching.
    """
    start = text.find(open_char)
    end = text.rfind(close_char)
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


def _clean_llm_json_artifacts(text: str) -> str:
    """Clean common LLM JSON artifacts from malformed JSON text.

    Only called after json.loads has already failed, so the text is
    already malformed. These regexes cannot corrupt valid JSON.

    Handles:
    - Trailing commas before ] or }
    - Inline // comments
    - Ellipsis entries (... or "...")
    """
    # Remove trailing commas
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Remove line comments only when ``//`` is outside a JSON string.  A
    # regex cannot distinguish a comment from the scheme in a URL such as
    # ``https://example.org/path``.  Preserve the raw response and make this
    # bounded recovery conservative: escaped quotes and backslashes retain
    # their JSON-string meaning; unterminated strings are left for json.loads
    # to reject rather than silently deleting scientific evidence.
    text = _strip_json_comments(text)
    # Remove ellipsis entries, preserving comma separator when between items
    text = re.sub(
        r',\s*"?\.\.\.+"?\s*,', ",", text
    )  # between items: keep one comma
    return re.sub(r',?\s*"?\.\.\.+"?\s*', "", text)  # trailing/leading ellipsis


def _strip_json_comments(text: str) -> str:
    out = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == '/' and i + 1 < len(text) and text[i + 1] == '/':
            newline = text.find("\n", i + 2)
            if newline < 0:
                break
            out.append("\n")
            i = newline + 1
            continue
        out.append(char)
        i += 1
    return "".join(out)
