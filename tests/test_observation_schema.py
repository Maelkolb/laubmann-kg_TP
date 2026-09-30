import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from laubmann_kg.extraction.llm_observations import load_entry_schema
from laubmann_kg.llm.structured_output import parse_structured

SCHEMA = json.loads(Path("schemas/observation.schema.json").read_text())
ENTRY_SCHEMA = load_entry_schema()


def test_observation_schema_is_valid_json() -> None:
    assert SCHEMA["title"] == "Observation"


def test_parse_structured_accepts_conforming_output() -> None:
    text = '```json\n{"vernacular_de": "Buchfink", "verbatim_notes": "ein Buchfink singt"}\n```'
    data = parse_structured(text, SCHEMA)
    assert data["vernacular_de"] == "Buchfink"


def test_parse_structured_rejects_nonconforming_output() -> None:
    with pytest.raises(ValidationError):
        parse_structured('{"verbatim_notes": "kein Name"}', SCHEMA)


def test_provenance_fields_validate_strictly() -> None:
    payload = json.dumps({"observations": [
        {"vernacular_de": "Amsel", "verbatim_notes": "n",
         "record_type": "third-party-report", "observer": "Kiel",
         "literature_citation": None}]})
    data = parse_structured(payload, ENTRY_SCHEMA)
    assert data["observations"][0]["observer"] == "Kiel"


def test_weather_object_string_and_null_validate_strictly() -> None:
    for weather in ({"verbatim": "Regen", "temperature_value": "-5",
                     "temperature_unit": "R", "precipitation": "rain",
                     "wind": None, "sky": "overcast"},
                    "Wetter trüb", None):
        payload = json.dumps({"observations": [], "weather": weather})
        parse_structured(payload, ENTRY_SCHEMA)


def test_bogus_record_type_fails_enum_but_mapper_still_folds() -> None:
    # The response schema is a tolerant envelope (a German label passes) ...
    payload = json.dumps({"observations": [
        {"vernacular_de": "Amsel", "verbatim_notes": "n",
         "record_type": "Feldbeobachtung"}]})
    parse_structured(payload, ENTRY_SCHEMA)
    # ... and the mapper folds the model's own label onto the vocabulary.
    from laubmann_kg.extraction.llm_observations import extract_observations_llm
    from laubmann_kg.kg.model import DiaryEntry
    from laubmann_kg.llm.prompts import PromptLibrary
    from laubmann_kg.normalization.taxa import SeedTaxonResolver

    class FakeClient:
        model = "fake"

        def complete(self, prompt: str) -> str:
            return payload

    entry = DiaryEntry(entry_uid="e_schema1", entry_id="L02-e9999", volume=2,
                       page_uid="p", page_id="pid", region_uid=None, scan=None,
                       entry_date="1918-04-07", verbatim_event_date=None,
                       location_raw=None, text_clean="...")
    obs = extract_observations_llm(entry, FakeClient(), SeedTaxonResolver(), None,
                                   PromptLibrary(Path("prompts")), ENTRY_SCHEMA)
    assert len(obs) == 1
    assert obs[0].record_type == "field-observation"


def test_unknown_top_level_key_is_accepted_and_ignored() -> None:
    # prompt v4: the entry envelope has no "required" and no additionalProperties
    # false (a model that adds a key must not lose the whole entry) ...
    assert "required" not in ENTRY_SCHEMA and "additionalProperties" not in ENTRY_SCHEMA
    payload = json.dumps({"observations": [{"vernacular_de": "Amsel", "verbatim_notes": "n"}],
                          "bogus": 1})
    assert parse_structured(payload, ENTRY_SCHEMA)["bogus"] == 1
    parse_structured("{}", ENTRY_SCHEMA)                  # every key may be omitted
    # ... and the mapper ignores what it does not know
    from laubmann_kg.extraction.llm_observations import extract_observations_llm
    from laubmann_kg.kg.model import DiaryEntry
    from laubmann_kg.llm.prompts import PromptLibrary
    from laubmann_kg.normalization.taxa import SeedTaxonResolver

    class FakeClient:
        model = "fake"

        def complete(self, prompt: str) -> str:
            return payload

    entry = DiaryEntry(entry_uid="e_schema2", entry_id="L02-e9998", volume=2,
                       page_uid="p", page_id="pid", region_uid=None, scan=None,
                       entry_date="1918-04-07", verbatim_event_date=None,
                       location_raw=None, text_clean="...")
    obs = extract_observations_llm(entry, FakeClient(), SeedTaxonResolver(), None,
                                   PromptLibrary(Path("prompts")), ENTRY_SCHEMA)
    assert [o.taxon.vernacular_de for o in obs] == ["Amsel"]


def test_observation_schema_v4_fields() -> None:
    props = SCHEMA["properties"]
    for gone in ("daylight_phase", "sampling_protocol", "estimated_radius_m",
                 "spatial_confidence", "observation_duration_minutes"):
        assert gone not in props, gone
    assert {"event_date_end", "observed_with", "altitude_m", "time_of_day"} <= set(props)
    data = parse_structured(json.dumps({
        "vernacular_de": "Kiebitz", "verbatim_notes": "n", "event_date": "1921-05-03",
        "event_date_end": "1921-05-05", "observed_with": ["Kiefer"]}), SCHEMA)
    assert data["observed_with"] == ["Kiefer"]
