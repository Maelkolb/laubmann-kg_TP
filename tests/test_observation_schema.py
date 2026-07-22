import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from laubmann_kg.llm.structured_output import parse_structured

SCHEMA = json.loads(Path("schemas/observation.schema.json").read_text())


def test_observation_schema_is_valid_json() -> None:
    assert SCHEMA["title"] == "Observation"


def test_parse_structured_accepts_conforming_output() -> None:
    text = '```json\n{"vernacular_de": "Buchfink", "verbatim_notes": "ein Buchfink singt"}\n```'
    data = parse_structured(text, SCHEMA)
    assert data["vernacular_de"] == "Buchfink"


def test_parse_structured_rejects_nonconforming_output() -> None:
    with pytest.raises(ValidationError):
        parse_structured('{"verbatim_notes": "kein Name"}', SCHEMA)
