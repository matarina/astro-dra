"""Parse model output at the boundary where its schema is known."""

import json
import re


def object_reply(reply):
    text = getattr(reply, "content", reply)
    if not isinstance(text, str):
        raise ValueError("expected a JSON object in a text response")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip().lstrip("\ufeff")
    if text.startswith("```") and text.endswith("```"):
        _, _, text = text.partition("\n")
        text = text[:-3]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def source_ids(reply, allowed):
    ids = object_reply(reply).get("selected_source_ids")
    if not isinstance(ids, list) or any(type(i) is not int for i in ids):
        raise ValueError("selected_source_ids must be a list of integers")
    if any(i not in allowed for i in ids):
        raise ValueError("selected_source_ids contains an ID outside this batch")
    return list(dict.fromkeys(ids))


def select_ids(invoke, prompt, allowed):
    try:
        return source_ids(invoke(prompt), allowed)
    except ValueError as error:
        return source_ids(invoke(
            f'{prompt}\nPrevious selection error: {error}. Submit only '
            '{"selected_source_ids": [integer, ...]} using the provided IDs.'
        ), allowed)
