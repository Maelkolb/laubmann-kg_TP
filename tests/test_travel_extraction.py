"""Entry-level extraction: travel events, persons, habitat — mapping + SHACL."""

import json
from pathlib import Path

from rdflib import RDF

from laubmann_kg.extraction.llm_observations import (
    extract_observations_llm,
    load_entry_schema,
)
from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.kg.rdf import LKG, build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import SeedTaxonResolver
from laubmann_kg.pipeline import ExtractionResult

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS = PromptLibrary(REPO_ROOT / "prompts")
SCHEMA = load_entry_schema()


class FakeClient:
    model = "fake"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload


def _entry(text: str = "...") -> DiaryEntry:
    return DiaryEntry(
        entry_uid="e_travel1", entry_id="L02-e0002", volume=2, page_uid="p",
        page_id="pid", region_uid="r", scan="5", entry_date="1918-04-07",
        verbatim_event_date="7. April 1918", location_raw="München",
        text_clean=text,
    )


FULL_PAYLOAD = json.dumps({
    "observations": [{
        "vernacular_de": "Buchfink", "scientific_name": "Fringilla coelebs",
        "verbatim_notes": "ein Buchfink singt im Auwald", "individual_count": 1,
        "count_qualifier": "exact",
        "evidence": [{"kind": "auditory", "call_type": "song",
                      "call_transcription": "zick zick"}],
        "behaviour": ["singt"], "habitat": "Auwald", "confidence": 0.9,
    }],
    "travel_events": [{"legs": [
        {"departure_place": "München", "arrival_place": "Freising",
         "via_places": ["Moosach"], "transport_mode": "Bahn",
         "departure_time": "8:15", "arrival_time": "9.05",
         "verbatim": "8¼ Uhr ab München nach Freising"},
        {"departure_place": None, "arrival_place": "Garchinger Heide",
         "transport_mode": "zu Fuß", "departure_time": None,
         "arrival_time": None, "verbatim": "zu Fuß zur Heide"},
    ]}],
    "persons": [{"name": "Dr. Stresemann", "role": "companion",
                 "verbatim": "mit Dr. Stresemann"}],
})


def _run(payload: str):
    entry = _entry()
    obs = extract_observations_llm(entry, FakeClient(payload), SeedTaxonResolver(),
                                   normalize_place("München"), PROMPTS, SCHEMA)
    entry.observations = obs
    return entry, obs


def test_maps_travel_persons_habitat() -> None:
    entry, obs = _run(FULL_PAYLOAD)
    assert obs[0].habitat is not None and obs[0].habitat.label == "Auwald"
    assert len(entry.travel_events) == 1
    legs = entry.travel_events[0].legs
    assert len(legs) == 2
    assert legs[0].transport_mode == "train"          # "Bahn" folded onto vocab
    assert legs[0].departure_time == "1918-04-07T08:15:00"
    assert legs[0].arrival_time == "1918-04-07T09:05:00"
    assert legs[0].via_places and legs[0].via_places[0].name
    assert legs[1].transport_mode == "foot"
    # missing departure inherits the previous leg's arrival
    assert legs[1].departure_place.name == legs[0].arrival_place.name
    assert [p.name for p in (entry.persons and [entry.persons[0]] or [])]
    assert entry.persons[0].role == "companion"


def test_inconsistent_arrival_time_dropped() -> None:
    payload = json.dumps({"observations": [], "travel_events": [{"legs": [
        {"departure_place": "München", "arrival_place": "Freising",
         "transport_mode": "train", "departure_time": "10:00",
         "arrival_time": "09:00"}]}]})
    entry, _ = _run(payload)
    leg = entry.travel_events[0].legs[0]
    assert leg.departure_time == "1918-04-07T10:00:00"
    assert leg.arrival_time is None                    # would violate SHACL SPARQL rule


def test_leg_without_endpoint_dropped() -> None:
    payload = json.dumps({"observations": [], "travel_events": [
        {"legs": [{"arrival_place": ""}]}]})
    entry, _ = _run(payload)
    assert entry.travel_events == []                   # no valid leg → no event


def test_legacy_array_payload_still_maps() -> None:
    payload = json.dumps([{"vernacular_de": "Amsel", "verbatim_notes": "eine Amsel"}])
    entry, obs = _run(payload)
    assert len(obs) == 1
    assert entry.travel_events == [] and entry.persons == []


def test_graph_emits_full_ontology_and_conforms(tmp_path) -> None:
    entry, _ = _run(FULL_PAYLOAD)
    result = ExtractionResult(entries=[entry])
    graph = build_graph(result)
    assert set(graph.subjects(RDF.type, LKG.TravelEvent))
    assert set(graph.subjects(RDF.type, LKG.TravelLeg))
    assert set(graph.subjects(RDF.type, LKG.Habitat))
    assert set(graph.subjects(RDF.type, LKG.Person))
    assert set(graph.objects(None, LKG.mentionsPerson))
    ttl = tmp_path / "travel.ttl"
    serialize_turtle(graph, ttl)
    assert run_shacl_validation(
        data_path=str(ttl),
        ontology_path=str(REPO_ROOT / "ontologies" / "laubmann.ttl"),
        shapes_path=str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"),
    )
