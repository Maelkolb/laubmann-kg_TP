"""Parse and validate structured JSON from LLM responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    """Extract a JSON value from raw model text, tolerating code fences."""
    text = text.strip()
    block = _JSON_BLOCK.search(text)
    candidate = block.group(1).strip() if block else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = min([i for i in (candidate.find("{"), candidate.find("[")) if i >= 0], default=-1)
        if start >= 0:
            return json.loads(candidate[start:])
        raise


def parse_structured(text: str, schema: dict) -> Any:
    """Extract JSON from ``text`` and validate it against ``schema``.

    Raises ``jsonschema.ValidationError`` on non-conformance so the caller can
    trigger a retry / repair.
    """
    data = extract_json(text)
    Draft202012Validator(schema).validate(data)
    return data
