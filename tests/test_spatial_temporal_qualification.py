"""Spatial / temporal qualification of observations (0.5.0, tightened 0.7.0).

Only what the text states survives prompt v4 / ontology 0.7.0: the vantage
(spatial_context), the position on the habitat (microhabitat), the flight
height (relative_elevation), a stated elevation (altitude_m -> Darwin Core
minimum/maximumElevationInMeters) and the qualitative time of day on ONE scale
dawn … night. The template-driven 0.5.0 fields (daylight phase, sampling
protocol, estimated viewing radius, spatial confidence, observation duration)
are gone from the model, the mapper and the graph.

The 1918-05-03 Mauersegler window-watch is the canonical sample: locality is
the street address, spatial_context keeps the vantage wording, and clock time
and forenoon slot are split.
"""

from __future__ import annotations

import dataclasses
import json
from decimal import Decimal
from pathlib import Path

from rdflib import Literal
from rdflib.namespace import RDF, XSD

from laubmann_kg.extraction.llm_observations import extract_observations_llm, load_entry_schema
from laubmann_kg.kg.model import DiaryEntry, Observation
from laubmann_kg.kg.rdf import DATA, DWC, LKG, build_graph
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.taxa import SeedTaxonResolver
from laubmann_kg.pipeline import ExtractionResult

REPO_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = REPO_ROOT / "ontologies" / "laubmann.ttl"
SHAPES = REPO_ROOT / "ontologies" / "shacl_shapes.ttl"
PROMPTS = PromptLibrary(REPO_ROOT / "prompts")
SCHEMA = load_entry_schema()

MAUERSEGLER_TEXT = (
    "Vormittags 1/2 12 h beobachtete ich vom Fenster meiner Wohnung an der "
    "äußeren Prinzregentenstraße 14 die ersten Mauersegler."
)

# fields of ontology 0.5.0 that 0.7.0 removed; a legacy answer may still carry them
REMOVED_FIELDS = ("daylight_phase", "sampling_protocol", "estimated_radius_m",
                  "spatial_confidence", "observation_duration_minutes")
REMOVED_TERMS = (LKG.daylightPhase, LKG.altitudeM, LKG.observationRadiusMeters,
                 LKG.spatialConfidence, LKG.observationDurationMinutes, DWC.samplingProtocol)

MAUERSEGLER_PAYLOAD = {
    "entry_date": {"iso": "1918-05-03"},
    "entry_place": {"name": "München", "kind": "settlement"},
    "entry_kind": "field-day",
    "observations": [{
        "vernacular_de": "Mauersegler",
        "scientific_name": "Apus apus",
        "verbatim_notes": MAUERSEGLER_TEXT,
        "locality": {
            "name": "Äußere Prinzregentenstraße 14",
            "verbatim": "äußeren Prinzregentenstraße 14",
        },
        "spatial_context": "vom Fenster meiner Wohnung an der äußeren Prinzregentenstraße 14",
        "microhabitat": "Wohngebäude/Fenster",
        "relative_elevation": "hoch über den Dächern",
        "altitude_m": "520",
        "time_of_day": "forenoon",
        "event_time": "11:30",
        "evidence": [{"kind": "visual"}],
        "confidence": 0.95,
        # legacy 0.5.0 keys: accepted by the tolerant envelope, ignored by the mapper
        "daylight_phase": "day",
        "sampling_protocol": "Ansitz/Fensterbeobachtung",
        "estimated_radius_m": 100,
        "spatial_confidence": "high",
        "observation_duration_minutes": 30,
    }],
    "travel_events": [],
    "persons": [],
    "weather": None,
}


class _FakeClient:
    model = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload)

    def complete(self, prompt: str) -> str:
        return self.payload


def _mauersegler_entry() -> DiaryEntry:
    return DiaryEntry(
        entry_uid="e_1918_05_03",
        entry_id="L02-e1918-05-03",
        volume=2,
        page_uid="p_1918_05_03",
        page_id="L02-p0503",
        region_uid="r_1918_05_03",
        scan=None,
        entry_date="1918-05-03",
        verbatim_event_date="3. V. 1918",
        location_raw="München",
        text_clean=MAUERSEGLER_TEXT,
    )


def _extract(payload: dict, entry: DiaryEntry | None = None) -> tuple[DiaryEntry, list[Observation]]:
    entry = entry or _mauersegler_entry()
    obs = extract_observations_llm(entry, _FakeClient(payload), SeedTaxonResolver(),
                                   None, PROMPTS, SCHEMA)
    entry.observations = obs
    return entry, obs


def _shacl_ok(graph, tmp_path: Path, name: str) -> bool:
    ttl = tmp_path / name
    graph.serialize(destination=str(ttl), format="turtle")
    return run_shacl_validation(data_path=str(ttl), ontology_path=str(ONTOLOGY),
                                shapes_path=str(SHAPES))


def test_removed_fields_are_gone_from_the_model_and_vocabulary() -> None:
    fields = {f.name for f in dataclasses.fields(Observation)}
    assert not fields & set(REMOVED_FIELDS)
    assert {"spatial_context", "microhabitat", "relative_elevation", "altitude_m",
            "time_of_day", "event_time", "event_date", "event_date_end"} <= fields
    # one time-of-day scale (the 0.5.0 daylight phase folded in)
    assert vocab.TIME_OF_DAY == ("dawn", "morning", "forenoon", "noon", "afternoon",
                                 "evening", "dusk", "night")
    assert not hasattr(vocab, "DAYLIGHT_PHASE") and not hasattr(vocab, "SPATIAL_CONFIDENCE")


def test_mauersegler_1918_05_03_window_watch_fields() -> None:
    entry, obs = _extract(MAUERSEGLER_PAYLOAD)
    assert len(obs) == 1
    record = obs[0]
    assert record.taxon.vernacular_de == "Mauersegler"
    assert record.spatial_context == (
        "vom Fenster meiner Wohnung an der äußeren Prinzregentenstraße 14"
    )
    assert record.microhabitat == "Wohngebäude/Fenster"
    assert record.relative_elevation == "hoch über den Dächern"
    assert record.altitude_m == 520.0                     # "520" -> metres as a number
    assert record.time_of_day == "forenoon"
    assert record.event_time == "11:30"
    for name in REMOVED_FIELDS:                           # legacy keys are not mapped
        assert name not in vars(record), name
    assert record.locality is not None
    assert record.locality.name == "Äußere Prinzregentenstraße 14"
    assert entry.place is not None
    assert entry.place.name == "München"
    assert record.locality.uid != entry.place.uid


def test_mauersegler_1918_05_03_rdf_and_shacl(tmp_path: Path) -> None:
    entry, _ = _extract(MAUERSEGLER_PAYLOAD)
    graph = build_graph(ExtractionResult(entries=[entry]))
    node = DATA[entry.observations[0].uid]
    assert (node, RDF.type, LKG.Observation) in graph
    assert graph.value(node, LKG.spatialContext) == Literal(
        "vom Fenster meiner Wohnung an der äußeren Prinzregentenstraße 14", lang="de"
    )
    assert graph.value(node, LKG.microhabitat) == Literal("Wohngebäude/Fenster", lang="de")
    assert graph.value(node, LKG.relativeElevation) == Literal("hoch über den Dächern", lang="de")
    assert graph.value(node, LKG.timeOfDay) == Literal("forenoon")
    assert graph.value(node, DWC.eventTime) == Literal("11:30")
    assert graph.value(node, DWC.eventDate) == Literal("1918-05-03", datatype=XSD.date)
    # altitude_m -> the Darwin Core elevation pair (xsd:decimal)
    for term in (DWC.minimumElevationInMeters, DWC.maximumElevationInMeters):
        value = graph.value(node, term)
        assert value.datatype == XSD.decimal and value.toPython() == Decimal("520")
    # the removed 0.5.0 terms are not emitted anywhere; no radius on the record
    for term in REMOVED_TERMS:
        assert list(graph.triples((None, term, None))) == [], term
    assert graph.value(node, DWC.coordinateUncertaintyInMeters) is None

    locality = graph.value(node, LKG.hasLocality)
    assert locality == DATA[entry.observations[0].locality.uid]
    assert graph.value(locality, RDF.type) == LKG.Place
    assert graph.value(node, DWC.verbatimLocality) == Literal("äußeren Prinzregentenstraße 14")
    assert graph.value(DATA[entry.uid], LKG.entryPlace) == DATA[entry.place.uid]
    assert locality != DATA[entry.place.uid]

    assert _shacl_ok(graph, tmp_path, "mauersegler_1918_05_03.ttl")


def test_time_of_day_scale_includes_dawn_and_dusk(tmp_path: Path) -> None:
    items = [{"vernacular_de": name, "verbatim_notes": name, "time_of_day": value}
             for name, value in (("Amsel", "dawn"), ("Rotkehlchen", "dusk"),
                                 ("Waldkauz", "night"), ("Star", "day"),         # 0.5.0 daylight value
                                 ("Buchfink", "Morgendämmerung"))]            # prose, never guessed
    entry, obs = _extract({"entry_place": {"name": "München"}, "observations": items})
    assert [o.time_of_day for o in obs] == ["dawn", "dusk", "night", None, None]
    graph = build_graph(ExtractionResult(entries=[entry]))
    assert [graph.value(DATA[o.uid], LKG.timeOfDay) for o in obs] == \
        [Literal("dawn"), Literal("dusk"), Literal("night"), None, None]
    assert list(graph.triples((None, LKG.daylightPhase, None))) == []
    assert _shacl_ok(graph, tmp_path, "time_of_day.ttl")


def test_elevation_only_when_plausible_and_place_elevation_from_header(tmp_path: Path) -> None:
    entry, obs = _extract({
        "entry_place": {"name": "Oberstdorf", "kind": "settlement", "altitude_m": 843},
        "observations": [
            {"vernacular_de": "Alpendohle", "verbatim_notes": "a", "altitude_m": "2000,5"},
            {"vernacular_de": "Bergpieper", "verbatim_notes": "b", "altitude_m": 12000},   # implausible
            {"vernacular_de": "Kolkrabe", "verbatim_notes": "c", "altitude_m": "hoch"},     # prose
        ]})
    assert [o.altitude_m for o in obs] == [2000.5, None, None]
    assert entry.place.elevation_m == 843.0                # stated place elevation
    graph = build_graph(ExtractionResult(entries=[entry]))
    place = DATA[entry.place.uid]
    assert graph.value(place, DWC.minimumElevationInMeters).toPython() == Decimal("843")
    assert graph.value(place, DWC.maximumElevationInMeters).toPython() == Decimal("843")
    assert graph.value(DATA[obs[0].uid], DWC.minimumElevationInMeters).toPython() == Decimal("2000.5")
    assert graph.value(DATA[obs[1].uid], DWC.minimumElevationInMeters) is None
    assert list(graph.triples((None, LKG.altitudeM, None))) == []
    assert _shacl_ok(graph, tmp_path, "elevation.ttl")


def test_dwca_occurrence_carries_elevation_and_detail_without_removed_fields() -> None:
    from laubmann_kg.dwca.occurrence import FIELDS, build_occurrences
    entry, obs = _extract({
        "entry_place": {"name": "Oberstdorf", "kind": "settlement", "altitude_m": 843},
        "observations": [
            {"vernacular_de": "Alpendohle", "verbatim_notes": "a", "altitude_m": 2000,
             "spatial_context": "vom Gipfel", "microhabitat": "Felsband",
             "relative_elevation": "sehr hoch", "time_of_day": "dusk"},
            {"vernacular_de": "Bergpieper", "verbatim_notes": "b"},
        ]})
    rows = {r["vernacularName"]: r for r in build_occurrences(ExtractionResult(entries=[entry]))}
    own, inherited = rows["Alpendohle"], rows["Bergpieper"]
    assert own["minimumElevationInMeters"] == own["maximumElevationInMeters"] == "2000"
    # a record without its own elevation takes its place's stated elevation
    assert inherited["minimumElevationInMeters"] == inherited["maximumElevationInMeters"] == "843"
    props = json.loads(own["dynamicProperties"])
    assert props == {"spatialContext": "vom Gipfel", "microhabitat": "Felsband",
                     "relativeElevation": "sehr hoch"}             # timeOfDay is an eMoF row
    for gone in ("daylightPhase", "spatialConfidence", "observationRadiusMeters",
                 "observationDurationMinutes"):
        assert gone not in props
    assert own["coordinateUncertaintyInMeters"] == ""               # no viewing radius
    assert "organismQuantity" not in FIELDS
