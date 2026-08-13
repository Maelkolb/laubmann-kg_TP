"""Observation provenance: record_type/observer/citation — mapping, RDF, DwC-A."""

import json
from pathlib import Path

from rdflib import Literal, URIRef

from laubmann_kg.dwca.occurrence import build_occurrences
from laubmann_kg.extraction.llm_observations import (
    extract_observations_llm,
    load_entry_schema,
)
from laubmann_kg.kg.model import DiaryEntry, Evidence, Observation, Person, Taxon
from laubmann_kg.kg.rdf import DATA, DWC, LKG, build_graph, serialize_turtle
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
        entry_uid="e_prov1", entry_id="L02-e0002", volume=2, page_uid="p",
        page_id="pid", region_uid="r", scan="5", entry_date="1918-04-07",
        verbatim_event_date="7. April 1918", location_raw="München",
        text_clean=text,
    )


def _run(payload: str):
    entry = _entry()
    obs = extract_observations_llm(entry, FakeClient(payload), SeedTaxonResolver(),
                                   normalize_place("München"), PROMPTS, SCHEMA)
    entry.observations = obs
    return entry, obs


def _obs_item(vernacular: str = "Amsel", **extra) -> dict:
    return {"vernacular_de": vernacular, "verbatim_notes": f"{vernacular} beobachtet",
            **extra}


def test_defaults_when_fields_absent() -> None:
    # Legacy cached payloads without the new fields must stay compatible.
    payload = json.dumps([{"vernacular_de": "Amsel", "verbatim_notes": "eine Amsel"}])
    _, obs = _run(payload)
    assert obs[0].record_type == "field-observation"
    assert obs[0].observer is None
    assert obs[0].literature_citation is None


def test_observer_links_to_entry_person_by_surname() -> None:
    payload = json.dumps({
        "observations": [_obs_item("Milan", observer="Kiel")],
        "persons": [{"name": "Förster Kiel", "role": "source"}],
    })
    entry, obs = _run(payload)
    assert obs[0].observer is entry.persons[0]         # same object, no duplicate
    assert len(entry.persons) == 1
    # unmatched observer name -> fresh Person appended to entry.persons
    payload = json.dumps({"observations": [_obs_item("Milan", observer="Meyer")],
                          "persons": []})
    entry, obs = _run(payload)
    assert obs[0].observer is not None
    assert obs[0].observer.role == "source"
    assert obs[0].observer in entry.persons


def test_lbm_tag_is_diarist() -> None:
    payload = json.dumps({"observations": [
        _obs_item("Amsel", observer="(Lbm.)"),
        _obs_item("Buchfink", observer="ich"),
        _obs_item("Star", observer="Laubmann"),
    ]})
    _, obs = _run(payload)
    for o in obs:
        assert o.observer is None
        assert o.record_type == "field-observation"


def test_record_type_derivation_and_repair() -> None:
    payload = json.dumps({"observations": [
        _obs_item("Amsel", record_type=None, literature_citation="A.S.Z. 1949, S. 12"),
        _obs_item("Buchfink", record_type=None, observer="Kiel"),
        _obs_item("Star", record_type="field-observation",
                  literature_citation="Orn. Monatsber. 41"),
        _obs_item("Milan", record_type="third-party-report",
                  literature_citation="Orn. Monatsber. 41"),
    ]})
    _, obs = _run(payload)
    assert obs[0].record_type == "literature-record"    # null + citation
    assert obs[1].record_type == "third-party-report"   # null + observer
    assert obs[2].record_type == "literature-record"    # repaired contradiction
    assert obs[3].record_type == "third-party-report"   # explicit value respected


def test_hostile_inputs() -> None:
    payload = json.dumps({"observations": [
        _obs_item("Amsel", record_type="Feldbeobachtung"),
        _obs_item("Buchfink", record_type=42),
        _obs_item("Star", observer=17),
        _obs_item("Milan", observer={}),
        _obs_item("Meise", observer=[]),
        _obs_item("Fink", observer="", literature_citation="  "),
    ]})
    _, obs = _run(payload)
    assert obs[0].record_type == "field-observation"    # German cue folded
    assert obs[1].record_type == "field-observation"    # garbage -> default
    for o in obs[2:]:
        assert o.observer is None
    assert obs[5].literature_citation is None


def test_observer_placeholders_rejected() -> None:
    # Letterless / placeholder observer values must not mint a Person or flip
    # the record type away from field-observation.
    payload = json.dumps({"observations": [
        _obs_item(v, observer=o) for v, o in
        [("Amsel", "-"), ("Buchfink", "."), ("Star", "?"),
         ("Milan", "n/a"), ("Meise", "unbekannt"), ("Fink", "Unknown")]
    ]})
    entry, obs = _run(payload)
    for o in obs:
        assert o.observer is None
        assert o.record_type == "field-observation"
    assert entry.persons == []


def test_observer_wrapped_in_dict_or_list() -> None:
    # {"name": "Kiel"} must not be dropped — dropping it re-attributes the
    # record to the diarist.
    payload = json.dumps({"observations": [
        _obs_item("Amsel", observer={"name": "Kiel"}),
        _obs_item("Buchfink", observer=["Meyer"]),
        _obs_item("Star", observer=[None, {"name": "Huber"}]),
    ]})
    _, obs = _run(payload)
    assert [o.observer.name for o in obs] == ["Kiel", "Meyer", "Huber"]
    assert all(o.record_type == "third-party-report" for o in obs)


def test_citation_must_be_string() -> None:
    # A dict citation must neither become a Python repr nor flip record_type.
    payload = json.dumps({"observations": [
        _obs_item("Amsel", literature_citation={"title": "A.S.Z.", "year": 1949}),
        _obs_item("Buchfink", literature_citation=1949),
    ]})
    _, obs = _run(payload)
    for o in obs:
        assert o.literature_citation is None
        assert o.record_type == "field-observation"


def test_record_type_schriftlich_is_third_party() -> None:
    payload = json.dumps({"observations": [
        _obs_item("Amsel", record_type="schriftliche Mitteilung von Herrn Kiel"),
        _obs_item("Buchfink", record_type="Literaturangabe"),
    ]})
    _, obs = _run(payload)
    assert obs[0].record_type == "third-party-report"
    assert obs[1].record_type == "literature-record"


def test_rdf_emission_and_shacl_conforms(tmp_path) -> None:
    payload = json.dumps({"observations": [
        _obs_item("Amsel"),
        _obs_item("Buchfink", record_type="literature-record", observer="Kiefer",
                  literature_citation="A.S.Z. 1949, S. 12"),
        _obs_item("Star", evidence=[{"kind": "specimen"}]),
        _obs_item("Milan", record_type="third-party-report"),
    ]})
    entry, obs = _run(payload)
    graph = build_graph(ExtractionResult(entries=[entry]))

    nodes = [DATA[o.uid] for o in obs]
    assert graph.value(nodes[0], LKG.recordType) == Literal("field-observation")
    assert graph.value(nodes[1], LKG.recordType) == Literal("literature-record")
    assert graph.value(nodes[0], DWC.basisOfRecord) == Literal("HumanObservation")
    assert graph.value(nodes[1], DWC.basisOfRecord) == Literal("MaterialCitation")
    assert graph.value(nodes[2], DWC.basisOfRecord) == Literal("PreservedSpecimen")
    # default field observation -> the diarist
    diarist = graph.value(nodes[0], LKG.observedBy)
    assert isinstance(diarist, URIRef) and str(diarist).endswith("person_c6b2ff6250e5")
    # named observer on the literature record
    named = graph.value(nodes[1], LKG.observedBy)
    assert named is not None and named != diarist
    # unattributed third-party record: attribution is never fabricated
    assert graph.value(nodes[3], LKG.observedBy) is None
    citation = graph.value(nodes[1], DWC.associatedReferences)
    assert citation == Literal("A.S.Z. 1949, S. 12", lang="de")

    ttl = tmp_path / "provenance.ttl"
    serialize_turtle(graph, ttl)
    assert run_shacl_validation(
        data_path=str(ttl),
        ontology_path=str(REPO_ROOT / "ontologies" / "laubmann.ttl"),
        shapes_path=str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"),
    )


def test_dwca_provenance() -> None:
    entry = _entry()
    taxon_linked = Taxon(vernacular_de="Blaumeise", scientific_name="Cyanistes caeruleus",
                         gbif_key=2487879, gbif_match_type="EXACT")
    taxon_broad = Taxon(vernacular_de="Steinschmätzer", scientific_name="Oenanthe",
                        gbif_key=2492483, gbif_match_type="HIGHERRANK")
    entry.observations = [
        Observation(entry_uid=entry.entry_uid, taxon=taxon_linked,
                    verbatim_notes="n", index=0,
                    record_type="literature-record",
                    evidence=[Evidence("specimen", "Beleg / erlegtes Stück")],
                    literature_citation="A.S.Z.\t1949,\nS. 12"),
        Observation(entry_uid=entry.entry_uid, taxon=taxon_broad,
                    verbatim_notes="n", index=1,
                    observer=Person(name="Kiefer", role="source"),
                    record_type="third-party-report"),
        Observation(entry_uid=entry.entry_uid, taxon=Taxon(vernacular_de="Amsel"),
                    verbatim_notes="n", index=2),
    ]
    rows = build_occurrences(ExtractionResult(entries=[entry]))
    # literature wins over specimen evidence
    assert rows[0]["basisOfRecord"] == "MaterialCitation"
    assert rows[0]["recordedBy"] == ""                  # observerless literature record
    assert rows[0]["associatedReferences"] == "A.S.Z. 1949, S. 12"
    assert rows[0]["taxonID"] == "https://www.gbif.org/species/2487879"
    assert rows[1]["recordedBy"] == "Kiefer"
    assert rows[1]["taxonID"] == ""                     # HIGHERRANK anchor: no taxonID
    assert rows[2]["recordedBy"] == "Alfred Laubmann"   # field default
    assert rows[2]["basisOfRecord"] == "HumanObservation"
