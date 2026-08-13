"""Entry-level weather: mapping, QA bookkeeping, RDF/SHACL, DwC-A."""

import json
from decimal import Decimal
from pathlib import Path

from rdflib import RDF, Literal, XSD

from laubmann_kg.dwca.event import FIELDS as EVENT_FIELDS, build_events
from laubmann_kg.extraction.llm_observations import (
    extract_observations_llm,
    load_entry_schema,
)
from laubmann_kg.extraction.weather import map_weather
from laubmann_kg.kg.model import (
    DiaryEntry,
    Evidence,
    Observation,
    Person,
    Taxon,
    TravelEvent,
    TravelLeg,
    WeatherReport,
)
from laubmann_kg.kg.rdf import DATA, LKG, build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import SeedTaxonResolver
from laubmann_kg.pipeline import ExtractionResult, run_pipeline
from laubmann_kg.qa import run_qa

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS = PromptLibrary(REPO_ROOT / "prompts")
SCHEMA = load_entry_schema()


class FakeClient:
    model = "fake"

    def __init__(self, payload: str) -> None:
        self.payload = payload

    def complete(self, prompt: str) -> str:
        return self.payload


def _entry(uid: str = "e_weather1", date: str = "1918-04-07") -> DiaryEntry:
    return DiaryEntry(
        entry_uid=uid, entry_id="L02-e0002", volume=2, page_uid="p",
        page_id="pid", region_uid="r", scan="5", entry_date=date,
        verbatim_event_date="7. April 1918", location_raw="München",
        text_clean="...",
    )


def test_map_weather_full_object() -> None:
    report = map_weather({"verbatim": "Trüb, −3,5° R", "temperature_value": "−3,5",
                          "temperature_unit": "°R", "precipitation": "Schneeregen",
                          "sky": "trüb"})
    assert report.verbatim == "Trüb, −3,5° R"
    assert report.temperature_value == -3.5
    assert report.temperature_unit == "R"
    assert report.precipitation == "sleet"      # cue order: Schneeregen ≠ snow/rain
    assert report.sky == "overcast"


def test_bare_string_and_list() -> None:
    assert map_weather("Wetter trüb") == WeatherReport(verbatim="Wetter trüb")
    assert map_weather([{"verbatim": "Regen"}]).verbatim == "Regen"
    # a truthy-but-unmappable first element must not eclipse a valid later one
    assert map_weather([{"verbatim": ""}, {"verbatim": "Regen"}]) == WeatherReport(verbatim="Regen")
    assert map_weather([{"verbatim": ""}, 42]) is None


def test_garbage() -> None:
    assert map_weather(42) is None
    assert map_weather(999) is None
    assert map_weather({"verbatim": ""}) is None
    report = map_weather({"verbatim": "x", "temperature_value": "warm",
                          "temperature_unit": "R"})
    assert report.temperature_value is None
    assert report.temperature_unit is None      # unit without a value is meaningless
    report = map_weather({"verbatim": "x", "temperature_unit": "R"})
    assert report.temperature_unit is None
    report = map_weather({"verbatim": "x", "precipitation": "Sturm?", "sky": "lila"})
    assert report is not None                   # unknown enums fold to None, report kept
    assert report.precipitation is None and report.sky is None
    report = map_weather({"verbatim": "x", "wind": {"richtung": "SW"}})
    assert report.wind is None                  # non-string wind, no repr coercion


def test_unit_folding() -> None:
    from laubmann_kg.normalization.vocabularies import normalize_temperature_unit
    for raw in ("reaumur", "°R", "R", "Grad Réaumur"):
        assert normalize_temperature_unit(raw) == "R"
    for raw in ("celsius", "Zentigrad", "Grad Celsius"):
        assert normalize_temperature_unit(raw) == "C"
    assert normalize_temperature_unit("°F") == "F"
    assert normalize_temperature_unit("Grad") is None


def test_precipitation_negation() -> None:
    from laubmann_kg.normalization.vocabularies import normalize_precipitation
    assert normalize_precipitation("Regen") == "rain"
    assert normalize_precipitation("kein Regen") == "none"
    assert normalize_precipitation("ohne Schnee") == "none"
    assert normalize_precipitation("nicht geregnet") == "none"


def test_fahrenheit_bounds() -> None:
    report = map_weather({"verbatim": "68° F", "temperature_value": 68,
                          "temperature_unit": "F"})
    assert report.temperature_value == 68.0
    assert report.temperature_unit == "F"
    # the wider band belongs to F alone: 68 is not a plausible C/R reading
    for unit in ("C", None):
        report = map_weather({"verbatim": "x", "temperature_value": 68,
                              "temperature_unit": unit})
        assert report.temperature_value is None
        assert report.temperature_unit is None


def test_entry_weather_attached() -> None:
    payload = json.dumps({"observations": [],
                          "weather": {"verbatim": "Wetter trüb und kalt",
                                      "precipitation": "Regen"}})
    entry = _entry()
    obs = extract_observations_llm(entry, FakeClient(payload), SeedTaxonResolver(),
                                   normalize_place("München"), PROMPTS, SCHEMA)
    assert obs == []                            # weather-only entry: no observations
    assert entry.weather is not None
    assert entry.weather.verbatim == "Wetter trüb und kalt"
    assert entry.weather.precipitation == "rain"


def test_offline_backend_unchanged(sample_config) -> None:
    result = run_pipeline(sample_config)
    by_id = {e.entry_id: e for e in result.entries}
    assert by_id["L02-e0003"].observations == []
    assert by_id["L02-e0003"].weather is None
    flags = [f for f in result.qa_flags if f.entry_id == "L02-e0003"]
    assert any(f.reason == "empty" for f in flags)


def test_qa_no_observations_reason() -> None:
    weather_entry = _entry("e_qa_w")
    weather_entry.weather = WeatherReport(verbatim="Regen")
    travel_entry = _entry("e_qa_t")
    place = normalize_place("München")
    travel_entry.travel_events = [TravelEvent(entry_uid="e_qa_t", legs=[
        TravelLeg(departure_place=place, arrival_place=place)])]
    bare_entry = _entry("e_qa_e")
    _, flags = run_qa([weather_entry, travel_entry, bare_entry],
                      {"exclude": True, "year_min": 1918, "year_max": 1919})
    by_uid = {f.entry_uid: f for f in flags}
    assert by_uid["e_qa_w"].reason == "no_observations"
    assert by_uid["e_qa_t"].reason == "no_observations"
    assert by_uid["e_qa_e"].reason == "empty"
    assert all(f.action == "flagged" for f in flags)


def _enum_exercising_entries() -> list[DiaryEntry]:
    """Entries whose weather/provenance literals cover EVERY new sh:in value."""
    precip = ("rain", "snow", "sleet", "hail", "drizzle", "fog", "thunderstorm", "none")
    skies = ("clear", "partly-cloudy", "overcast", "variable")
    units = ("C", "R", "F")
    entries = []
    for i, p in enumerate(precip):
        e = _entry(f"e_enum{i}", date=f"1918-04-{i + 1:02d}")
        e.weather = WeatherReport(verbatim=f"Wetter {p}", temperature_value=float(i - 4),
                                  temperature_unit=units[i % 3], wind="starker SW-Wind",
                                  precipitation=p, sky=skies[i % 4])
        entries.append(e)
    hot = _entry("e_enum_f", date="1918-05-01")
    hot.weather = WeatherReport(verbatim="100° F", temperature_value=100.0,
                                temperature_unit="F", precipitation="none", sky="clear")
    entries.append(hot)
    obs_entry = _entry("e_enum_obs", date="1918-04-30")
    taxon = Taxon(vernacular_de="Amsel", scientific_name="Turdus merula")
    obs_entry.observations = [
        Observation(entry_uid="e_enum_obs", taxon=taxon, verbatim_notes="n", index=0),
        Observation(entry_uid="e_enum_obs", taxon=taxon, verbatim_notes="n", index=1,
                    record_type="third-party-report",
                    observer=Person(name="Kiefer", role="source")),
        Observation(entry_uid="e_enum_obs", taxon=taxon, verbatim_notes="n", index=2,
                    record_type="literature-record",
                    literature_citation="A.S.Z. 1949, S. 12"),
        Observation(entry_uid="e_enum_obs", taxon=taxon, verbatim_notes="n", index=3,
                    evidence=[Evidence("specimen", "Beleg / erlegtes Stück")]),
    ]
    entries.append(obs_entry)
    return entries


def test_rdf_weather_and_shacl(tmp_path) -> None:
    entries = _enum_exercising_entries()
    graph = build_graph(ExtractionResult(entries=entries))

    node = DATA["weather_e_enum0"]
    assert (node, RDF.type, LKG.WeatherReport) in graph
    assert (DATA["entry_e_enum0"], LKG.hasWeather, node) in graph
    verbatim = graph.value(node, LKG.weatherVerbatim)
    assert verbatim.language == "de"
    temp = graph.value(node, LKG.temperatureValue)
    assert temp.datatype == XSD.decimal and temp.toPython() == Decimal("-4")
    unit = graph.value(node, LKG.temperatureUnit)
    assert unit == Literal("C") and unit.language is None   # enum literals: no lang tag
    assert graph.value(node, LKG.precipitation).language is None
    assert graph.value(node, LKG.skyCondition).language is None
    assert graph.value(node, LKG.wind).language == "de"

    ttl = tmp_path / "weather.ttl"
    serialize_turtle(graph, ttl)
    assert run_shacl_validation(
        data_path=str(ttl),
        ontology_path=str(REPO_ROOT / "ontologies" / "laubmann.ttl"),
        shapes_path=str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"),
    )


def test_shacl_temperature_bound_covers_fahrenheit() -> None:
    # Warning-severity, so run_shacl_validation would not fail on a regression;
    # pin the widened bound on the shapes graph itself.
    from rdflib import Graph
    from rdflib.namespace import SH
    shapes = Graph()
    shapes.parse(str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"), format="turtle")
    prop = next(shapes.subjects(SH.path, LKG.temperatureValue))
    assert shapes.value(prop, SH.minInclusive).toPython() == -76
    assert shapes.value(prop, SH.maxInclusive).toPython() == 140


def test_dwca_weather() -> None:
    with_weather = _entry("e_dwca_w")
    with_weather.weather = WeatherReport(verbatim="Trüb  und\nkalt,\tRegen",
                                         temperature_value=-3.5, temperature_unit="R",
                                         precipitation="rain", sky="overcast")
    without = _entry("e_dwca_n", date="1918-04-08")
    rows = build_events(ExtractionResult(entries=[with_weather, without]))
    assert rows[0]["eventRemarks"] == "Trüb und kalt, Regen"
    props = json.loads(rows[0]["dynamicProperties"])
    assert props == {"temperatureValue": -3.5, "temperatureUnit": "R",
                     "precipitation": "rain", "skyCondition": "overcast"}
    assert "\t" not in rows[0]["dynamicProperties"]
    assert "\n" not in rows[0]["dynamicProperties"]
    assert rows[1]["eventRemarks"] == "" and rows[1]["dynamicProperties"] == ""
    # append-only contract: new columns at the very end, prefix untouched
    assert EVENT_FIELDS[-2:] == ["eventRemarks", "dynamicProperties"]
    assert EVENT_FIELDS[:9] == ["eventID", "eventDate", "verbatimEventDate", "locality",
                                "decimalLatitude", "decimalLongitude",
                                "samplingProtocol", "fieldNumber", "fieldNotes"]
