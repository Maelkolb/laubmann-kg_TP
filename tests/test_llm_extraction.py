import json
from pathlib import Path

from laubmann_kg.extraction.llm_observations import (
    extract_observations_llm,
    load_array_schema,
)
from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import SeedTaxonResolver

PROMPTS = PromptLibrary(Path("prompts"))
SCHEMA = load_array_schema()


class FakeClient:
    """Stand-in for the Gemini client: returns a fixed payload, records prompts.
    Keeps the LLM wiring test deterministic and network-free."""

    model = "fake"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload


def _entry(text: str) -> DiaryEntry:
    return DiaryEntry(
        entry_uid="e_x", entry_id="L02-e0001", volume=2, page_uid="p", page_id="pid",
        region_uid="r", scan="4", entry_date="1918-04-07",
        verbatim_event_date="7. April 1918", location_raw="München", text_clean=text,
    )


def _run(text: str, payload: str, place=None):
    client = FakeClient(payload)
    obs = extract_observations_llm(_entry(text), client, SeedTaxonResolver(), place, PROMPTS, SCHEMA)
    return obs, client


def test_maps_structured_output_and_marks_uncertainty() -> None:
    payload = json.dumps([
        {"vernacular_de": "Buchfink", "scientific_name": "Fringilla coelebs",
         "verbatim_notes": "ein Buchfink singt", "individual_count": 1,
         "count_qualifier": "exact", "evidence": [{"kind": "auditory", "call_type": "song"}],
         "behaviour": ["singt"]},
        {"vernacular_de": "Kranich", "scientific_name": None,
         "verbatim_notes": "ein Kranich zieht", "evidence": [{"kind": "visual"}]},
    ])
    obs, _ = _run("...", payload, normalize_place("München"))
    assert len(obs) == 2
    assert obs[0].taxon.scientific_name == "Fringilla coelebs"
    assert any(e.is_call and e.call_type == "song" for e in obs[0].evidence)
    # Species the model could not resolve: no scientific name, uncertainty noted.
    assert obs[1].taxon.scientific_name is None
    assert obs[1].taxon.note


def test_prompt_carries_entry_text() -> None:
    _, client = _run("An der Isar Lachmöwen.", "[]")
    assert "Lachmöwen" in client.prompts[0]


def test_empty_output_yields_no_observations() -> None:
    obs, _ = _run("Wetter trüb", "[]")
    assert obs == []


def test_lenient_fallback_and_sanitization() -> None:
    # individual_count 0 and an unknown qualifier violate the schema; the lenient
    # path still maps the item, and both invalid values are dropped.
    payload = json.dumps([{"vernacular_de": "Amsel", "verbatim_notes": "eine Amsel",
                           "individual_count": 0, "count_qualifier": "lots", "evidence": []}])
    obs, _ = _run(".", payload)
    assert len(obs) == 1
    assert obs[0].individual_count is None
    assert obs[0].count_qualifier is None
    assert obs[0].evidence[0].kind == "visual"  # default when none given
