"""Parse and validate structured JSON from LLM responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _strip_to_json(text: str) -> str:
    """Drop code fences and any prose before the first JSON container."""
    text = text.strip()
    block = _JSON_BLOCK.search(text)
    candidate = block.group(1).strip() if block else text
    starts = [i for i in (candidate.find("{"), candidate.find("[")) if i >= 0]
    return candidate[min(starts):] if starts else candidate


def extract_json(text: str) -> Any:
    """Extract a JSON value from raw model text.

    Strict ``json.loads`` is tried first so well-formed output is never altered.
    Only on failure is a repair pass applied, covering the malformations LLMs
    commonly emit even under ``response_mime_type=application/json``: unescaped
    quotes inside string values, missing/trailing commas, and light truncation.
    """
    candidate = _strip_to_json(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        logger.debug("strict JSON parse failed; attempting repair")
    try:
        from json_repair import repair_json
    except ImportError as exc:  # repair lib absent (offline/dev without [llm] extra)
        raise json.JSONDecodeError(
            "malformed JSON and json-repair not installed", candidate, 0) from exc
    return repair_json(candidate, return_objects=True)


def parse_structured(text: str, schema: dict) -> Any:
    """Extract JSON from ``text`` and validate it against ``schema``.

    Raises ``jsonschema.ValidationError`` on non-conformance so the caller can
    trigger a retry / repair.
    """
    data = extract_json(text)
    Draft202012Validator(schema).validate(data)
    return data
