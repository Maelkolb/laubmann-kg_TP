"""Extraction prompt v4 / ontology 0.7.0 contract.

Prompt v4 omits defaults (rank species, is_bird true, qualifier exact …), so
the mapper fills them; the record keeps only what the text states. This module
pins the new mapper rules (counts, ranks, companions, localities, dates), the
emission of several recorders and of observation date intervals, the DwC-A
georeference safety rule, the harmonisation of shared nodes, the OCR-year
repair of record dates and the truncated-output QA flag.
"""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import Literal
from rdflib.namespace import XSD

from laubmann_kg.extraction.llm_observations import (
    _resolve_observer,
    extract_observations_llm,
    load_entry_schema,
)
from laubmann_kg.kg.model import (
    DATA_NS,
    DIARIST,
    DiaryEntry,
    Evidence,
    Observation,
    Person,
    Place,
    Taxon,
    TravelEvent,
    TravelLeg,
    data_iri,
)
from laubmann_kg.kg.rdf import DATA, DWC, DWCIRI, LKG, build_graph, serialize_turtle
from laubmann_kg.kg.rdf import SCHEMA as SDO
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization.taxa import SeedTaxonResolver, TaxonResolution
from laubmann_kg.pipeline import ExtractionResult

REPO_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = REPO_ROOT / "ontologies" / "laubmann.ttl"
SHAPES = REPO_ROOT / "ontologies" / "shacl_shapes.ttl"
PROMPTS = PromptLibrary(REPO_ROOT / "prompts")
SCHEMA = load_entry_schema()


class FakeClient:
    model = "fake"

    def __init__(self, payload) -> None:
        self.payload = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> str:
        return self.payload


class SpyResolver:
    """Records which names the seed resolver was asked for."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(self, vernacular_de: str) -> TaxonResolution:
        self.calls.append(vernacular_de)
        return TaxonResolution("Seedus seedii", "https://example.org/taxon/seed", "gazetteer", 1.0)


def _entry(uid: str = "e_v4", date: str = "1921-05-03", text: str = "Eintragstext",
           location_raw: str | None = "München") -> DiaryEntry:
    return DiaryEntry(entry_uid=uid, entry_id="L05-e0001", volume=5, page_uid="p_v4", page_id="pid_v4",
                      region_uid="r_v4", scan="12", entry_date=date, verbatim_event_date=date,
                      location_raw=location_raw, text_clean=text)


def _extract(payload, entry: DiaryEntry | None = None, resolver=None, client=None):
    entry = entry or _entry()
    obs = extract_observations_llm(entry, client or FakeClient(payload), resolver or SeedTaxonResolver(),
                                   None, PROMPTS, SCHEMA)
    entry.observations = obs
    return entry, obs


def _item(name: str, **kw) -> dict:
    return {"vernacular_de": name, "verbatim_notes": f"{name} gesehen", **kw}


def _shacl_ok(graph, tmp_path: Path, name: str = "v4.ttl") -> bool:
    ttl = tmp_path / name
    serialize_turtle(graph, ttl)
    return run_shacl_validation(data_path=str(ttl), ontology_path=str(ONTOLOGY), shapes_path=str(SHAPES))


# --- counts ----------------------------------------------------------------------

def test_count_rules_ranges_lone_bounds_and_default_qualifier() -> None:
    _, obs = _extract({"observations": [
        _item("Kiebitz", count_min=40, count_max=50),                            # range
        _item("Möwe", count_min=5, count_max=3),                                 # swapped range
        _item("Star", count_min=7, count_max=7),                                 # equal bounds
        _item("Lerche", count_min=30),                                           # lone minimum
        _item("Ente", count_max=20),                                             # lone maximum
        _item("Amsel", individual_count=12),                                     # no qualifier
        _item("Drossel", individual_count="12", count_qualifier="approximate"),  # stated qualifier kept
        _item("Gans", count_min=10, count_max=20, count_qualifier="minimum"),    # stated beats default
        _item("Fink", count_qualifier="plural-unspecified"),                     # no number
        _item("Meise"),                                                          # nothing stated
    ]})
    got = {o.taxon.vernacular_de: (o.individual_count, o.count_min, o.count_max, o.count_qualifier)
           for o in obs}
    assert got == {
        "Kiebitz": (40, 40, 50, "approximate"),     # individualCount = lower bound of the range
        "Möwe": (3, 3, 5, "approximate"),
        "Star": (7, None, None, "exact"),           # equal bounds collapse to an exact count
        "Lerche": (30, None, None, "minimum"),      # "über 30"
        "Ente": (20, None, None, "maximum"),        # "bis zu 20"
        "Amsel": (12, None, None, "exact"),         # prompt v4 omits "exact"
        "Drossel": (12, None, None, "approximate"),
        "Gans": (10, 10, 20, "minimum"),
        "Fink": (None, None, None, "plural-unspecified"),
        "Meise": (None, None, None, None),
    }


def test_absence_and_zero_counts(tmp_path: Path) -> None:
    from laubmann_kg.qa import run_qa
    entry, obs = _extract({"observations": [
        _item("Wachtelkönig", occurrence_status="absent", individual_count=3),   # contradiction
        _item("Rauchschwalbe", occurrence_status="absent", individual_count=0),
        _item("Star", individual_count=0),                                       # 0 without absence
    ]})
    wk, rs, st = obs
    assert wk.occurrence_status == "absent" and wk.individual_count is None
    assert "absent_with_count" in wk.flags and wk.count_qualifier is None
    assert rs.individual_count == 0 and "absent_with_count" not in rs.flags
    assert st.occurrence_status == "present" and st.individual_count is None and st.count_qualifier is None
    _, flags = run_qa([entry], {"misdate": False})
    assert [(f.reason, f.value) for f in flags if f.reason == "absent_with_count"] == \
        [("absent_with_count", "Wachtelkönig")]
    graph = build_graph(ExtractionResult(entries=[entry]))
    assert graph.value(DATA[wk.uid], DWC.individualCount) is None
    assert graph.value(DATA[rs.uid], DWC.individualCount) == Literal(0, datatype=XSD.integer)
    assert _shacl_ok(graph, tmp_path)


# --- taxon defaults and the seed resolver -------------------------------------------

def test_omitted_rank_and_is_bird_defaults() -> None:
    _, obs = _extract({"observations": [
        _item("Buchfink", scientific_name="Fringilla coelebs"),        # rank / is_bird omitted
        _item("Limikolen", taxon_rank="group"),
        _item("Reh", is_bird=False),
        _item("Irgendwas", taxon_rank="Gattung"),                       # outside the vocabulary
        _item("Nochwas", taxon_rank=None),                              # explicit null = omitted
    ]})
    ranks = {o.taxon.vernacular_de: (o.taxon.rank, o.taxon.is_bird) for o in obs}
    assert ranks == {"Buchfink": ("species", True), "Limikolen": ("group", True),
                     "Reh": ("species", False), "Irgendwas": (None, True),
                     "Nochwas": ("species", True)}
    assert all(o.taxon.rank != "unknown" for o in obs)


def test_seed_resolver_only_for_unnamed_species() -> None:
    spy = SpyResolver()
    _, obs = _extract({"observations": [
        _item("Bussard", taxon_rank="genus"),                           # never the seed's species
        _item("Möwen", taxon_rank="group"),
        _item("Buchfink", scientific_name="Fringilla coelebs"),         # the model named it
        _item("Amsel"),                                                 # species without a name
    ]}, resolver=spy)
    assert spy.calls == ["Amsel"]
    t = {o.taxon.vernacular_de: o.taxon for o in obs}
    assert t["Bussard"].scientific_name is None and t["Bussard"].match_method == "unresolved"
    assert t["Bussard"].taxon_iri is None and t["Bussard"].note is not None
    assert t["Buchfink"].scientific_name == "Fringilla coelebs" and t["Buchfink"].match_method == "llm"
    assert t["Buchfink"].taxon_iri is None
    assert t["Amsel"].scientific_name == "Seedus seedii" and t["Amsel"].match_method == "gazetteer"
    assert t["Amsel"].taxon_iri == "https://example.org/taxon/seed"


# --- mapper: localities, notes, travel ------------------------------------------------

def test_locality_equal_to_entry_place_is_dropped_and_notes_fall_back_to_the_name() -> None:
    entry, obs = _extract({
        "entry_place": {"name": "München", "kind": "settlement"},
        "observations": [
            {"vernacular_de": "Amsel", "locality": {"name": "münchen", "verbatim": "in München"}},
            {"vernacular_de": "Kiebitz", "locality": {"name": "Ismaning"}, "verbatim_notes": "bei Ismaning"},
        ]}, entry=_entry(text="Ein langer Eintragstext über vieles."))
    amsel, kiebitz = obs
    assert amsel.locality is None and amsel.place is entry.place       # the entry place itself
    assert kiebitz.locality is not None and kiebitz.place.name == "Ismaning"
    # no verbatim_notes: the vernacular name, not the whole entry text
    assert amsel.verbatim_notes == "Amsel"
    assert kiebitz.verbatim_notes == "bei Ismaning"


def test_travel_places_carry_no_guessed_kind_and_mode_is_optional(tmp_path: Path) -> None:
    from laubmann_kg.normalization.vocabularies import normalize_transport_mode
    assert normalize_transport_mode(None) is None
    assert normalize_transport_mode("unknown") is None
    assert normalize_transport_mode("mit der Bahn") == "train"
    entry, _ = _extract({
        "entry_place": {"name": "Nürnberg"},
        "travel_events": [{"legs": [
            {"departure_place": "München", "arrival_place": "Nürnberg", "transport_mode": "unknown"},
            {"departure_place": "Nürnberg", "arrival_place": "Erlangen", "transport_mode": "zu Fuß"},
        ]}],
        "observations": []})
    first, second = entry.travel_events[0].legs
    assert first.transport_mode is None and second.transport_mode == "foot"
    assert first.departure_place.lat is not None                        # gazetteer adds coordinates
    for place in (first.departure_place, first.arrival_place, second.arrival_place):
        assert place.kind is None                                       # no "settlement" guess
    graph = build_graph(ExtractionResult(entries=[entry]))
    legs = set(graph.subjects(LKG.arrivalPlace, None))
    assert len(legs) == 2
    # the leg whose mode the text does not state carries no lkg:transportMode at all
    assert [str(m) for leg in legs for m in graph.objects(leg, LKG.transportMode)] == ["foot"]
    for place in (first.departure_place, second.arrival_place):          # travel-only places
        assert graph.value(DATA[place.uid], LKG.placeKind) is None
    assert _shacl_ok(graph, tmp_path)


# --- companions ---------------------------------------------------------------------

def test_resolve_observer_respects_given_name_initials() -> None:
    persons = [Person("W. Wüst", role="companion"), Person("Förster Kiel", role="source")]
    assert _resolve_observer("W. Wüst", persons) is persons[0]              # exact
    assert _resolve_observer("Wüst", persons) is persons[0]                 # surname, no initials
    assert _resolve_observer("Dr. W. Wüst", persons) is persons[0]         # title skipped
    assert _resolve_observer("Walter Wüst", persons) is persons[0]         # initial agrees
    other = _resolve_observer("H. Wüst", persons)                           # contradicting initial
    assert other is not persons[0] and other.name == "H. Wüst" and other.role == "source"
    assert _resolve_observer("Kiel", persons) is persons[1]
    assert _resolve_observer("Kiefer", persons, role="companion").role == "companion"


def test_observed_with_becomes_co_observers_and_several_recorders(tmp_path: Path) -> None:
    entry, obs = _extract({
        "persons": [{"name": "Walter Wüst", "role": "companion"}],
        "observations": [
            _item("Kiebitz", observed_with=["Wüst", "Kiefer", "Kiefer"]),
            _item("Uhu", observed_with="Kiefer"),                            # a bare string
            _item("Milan", record_type="third-party-report", observer="Kiel", observed_with=["Kiel"]),
            _item("Amsel"),
        ]})
    kiebitz, uhu, milan, amsel = obs
    wuest = next(p for p in entry.persons if p.name == "Walter Wüst")
    kiefer = next(p for p in entry.persons if p.name == "Kiefer")
    assert kiefer.role == "companion"                                      # appended once as a companion
    assert [p.name for p in entry.persons].count("Kiefer") == 1
    assert kiebitz.co_observers == [wuest, kiefer]                         # resolved against entry.persons
    assert uhu.co_observers == [kiefer]
    assert milan.co_observers == []                                        # the observer is not his own companion
    # Observation.recorders: the diarist + companions; the observer for a report
    assert kiebitz.recorders == [DIARIST, wuest, kiefer]
    assert [p.name for p in milan.recorders] == ["Kiel"]
    assert amsel.recorders == [DIARIST]
    unattributed = Observation(entry_uid="e", taxon=Taxon("X"), verbatim_notes="x",
                               record_type="literature-record")
    assert unattributed.recorders == []

    graph = build_graph(ExtractionResult(entries=[entry]))
    names = {str(graph.value(p, SDO.name)) for p in graph.objects(DATA[kiebitz.uid], DWCIRI.recordedBy)}
    assert names == {"Alfred Laubmann", "Walter Wüst", "Kiefer"}
    assert len(set(graph.objects(DATA[amsel.uid], DWCIRI.recordedBy))) == 1
    assert _shacl_ok(graph, tmp_path)


def test_dwca_recorded_by_lists_the_companions() -> None:
    from laubmann_kg.dwca.occurrence import build_occurrences
    entry = _entry()
    kiefer = Person("Kiefer", role="companion")
    entry.observations = [
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Kiebitz", "Vanellus vanellus", rank="species",
                                                           is_bird=True),
                    verbatim_notes="n", index=0, co_observers=[kiefer]),
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Milan", "Milvus milvus", rank="species",
                                                           is_bird=True),
                    verbatim_notes="n", index=1, record_type="third-party-report",
                    observer=Person("Kiel", role="source"), co_observers=[kiefer]),
    ]
    rows = build_occurrences(ExtractionResult(entries=[entry]))
    assert rows[0]["recordedBy"] == "Alfred Laubmann | Kiefer"
    assert rows[1]["recordedBy"] == "Kiel | Kiefer"


# --- dates ----------------------------------------------------------------------------

def test_event_date_helpers() -> None:
    from laubmann_kg.normalization.dates import event_date, obs_event_date
    entry = _entry(date="1921-05-03")
    assert event_date(entry) == "1921-05-03"
    entry.entry_date_end = "1921-05-03"
    assert event_date(entry) == "1921-05-03"                        # end == start: a day
    entry.entry_date_end = "1921-05-05"
    assert event_date(entry) == "1921-05-03/1921-05-05"
    own = Observation(entry_uid="e", taxon=Taxon("A"), verbatim_notes="a", event_date="1921-05-04")
    assert obs_event_date(own, event_date(entry)) == "1921-05-04"
    own.event_date_end = "1921-05-05"
    assert obs_event_date(own, event_date(entry)) == "1921-05-04/1921-05-05"
    plain = Observation(entry_uid="e", taxon=Taxon("B"), verbatim_notes="b")
    assert obs_event_date(plain, event_date(entry)) == "1921-05-03/1921-05-05"


def test_observation_interval_dates_in_rdf_conform_to_shacl(tmp_path: Path) -> None:
    entry, obs = _extract({
        "entry_date": {"iso": "1921-05-03", "end_iso": "1921-05-05"},
        "entry_place": {"name": "München"},
        "observations": [
            _item("Kiebitz", event_date="1921-05-04"),                                   # own day
            _item("Storch", event_date="1921-05-04", event_date_end="1921-05-05"),      # own range
            _item("Amsel"),                                                              # entry interval
            _item("Star", event_date="1921-05-04", event_date_end="1921-05-02"),        # bad end dropped
            _item("Fink", event_date_end="1921-05-05"),                                 # end without start
        ]})
    assert entry.entry_date_end == "1921-05-05"
    kiebitz, storch, amsel, star, fink = obs
    assert (storch.event_date, storch.event_date_end) == ("1921-05-04", "1921-05-05")
    assert star.event_date_end is None and fink.event_date is None and fink.event_date_end is None
    graph = build_graph(ExtractionResult(entries=[entry]))
    date = lambda o: graph.value(DATA[o.uid], DWC.eventDate)   # noqa: E731
    assert date(kiebitz) == Literal("1921-05-04", datatype=XSD.date)
    assert date(storch) == Literal("1921-05-04/1921-05-05")                # plain literal interval
    assert date(amsel) == Literal("1921-05-03/1921-05-05")                 # no falsely precise start day
    assert date(star) == Literal("1921-05-04", datatype=XSD.date)
    assert date(fink) == Literal("1921-05-03/1921-05-05")
    assert graph.value(DATA[entry.uid], DWC.eventDate) == Literal("1921-05-03/1921-05-05")
    assert _shacl_ok(graph, tmp_path)


def test_dwca_occurrence_dates_follow_the_same_rule() -> None:
    from laubmann_kg.dwca.occurrence import build_occurrences
    entry = _entry(date="1921-05-03")
    entry.entry_date_end = "1921-05-05"
    entry.observations = [
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Storch"), verbatim_notes="s", index=0,
                    event_date="1921-05-04", event_date_end="1921-05-05"),
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Amsel"), verbatim_notes="a", index=1),
    ]
    rows = build_occurrences(ExtractionResult(entries=[entry]))
    assert [r["eventDate"] for r in rows] == ["1921-05-04/1921-05-05", "1921-05-03/1921-05-05"]


# --- DwC-A: georeference safety, identifiers, columns -----------------------------------

ERLANGEN = Place("Erlangen", "Erlangen", lat=49.5897, long=11.0040, kind="settlement",
                 coordinate_uncertainty_m=3000, georef_source="geonames", geonames_id=2929567)


def _safety_entry(own: Place) -> DiaryEntry:
    entry = _entry(uid="e_safe")
    entry.place = ERLANGEN
    entry.observations = [
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Amsel", "Turdus merula", rank="species",
                                                           is_bird=True),
                    verbatim_notes="a", index=0, place=ERLANGEN),
        Observation(entry_uid=entry.entry_uid, taxon=Taxon("Kiebitz", "Vanellus vanellus", rank="species",
                                                           is_bird=True),
                    verbatim_notes="k", index=1, place=own, locality=own),
    ]
    return entry


def test_coordinates_safe_drops_the_event_point_when_a_record_could_inherit_it() -> None:
    from laubmann_kg.dwca.event import build_events, coordinates_safe
    unmapped = Place("Irgendein Weiher", "Irgendein Weiher", kind="locality")        # no coordinates
    mapped = Place("Dechsendorfer Weiher", "Dechsendorfer Weiher", lat=49.62, long=10.96)
    risky, safe = _safety_entry(unmapped), _safety_entry(mapped)
    assert coordinates_safe(risky) is False and coordinates_safe(safe) is True
    row = build_events(ExtractionResult(entries=[risky]))[0]
    assert row["eventID"] == data_iri("entry_e_safe") == DATA_NS + "entry_e_safe"
    assert row["locality"] == "Erlangen"                                    # the name stays
    for column in ("decimalLatitude", "decimalLongitude", "geodeticDatum", "coordinateUncertaintyInMeters",
                   "georeferenceSources", "georeferenceProtocol", "locationID"):
        assert row[column] == "", column
    row = build_events(ExtractionResult(entries=[safe]))[0]
    assert (row["decimalLatitude"], row["coordinateUncertaintyInMeters"]) == ("49.5897", "3000")
    assert row["locationID"] == "https://sws.geonames.org/2929567/"
    no_place = _entry(uid="e_np")
    no_place.observations = [Observation(entry_uid="e_np", taxon=Taxon("A"), verbatim_notes="a")]
    assert coordinates_safe(no_place) is True


def test_occurrence_rows_carry_their_own_georeference() -> None:
    from laubmann_kg.dwca.occurrence import build_occurrences
    unmapped = Place("Irgendein Weiher", "Irgendein Weiher", kind="locality")
    rows = build_occurrences(ExtractionResult(entries=[_safety_entry(unmapped)]))
    at_entry, at_own = rows
    assert (at_entry["decimalLatitude"], at_entry["decimalLongitude"], at_entry["geodeticDatum"]) == \
        ("49.5897", "11.0040", "WGS84")
    assert at_entry["coordinateUncertaintyInMeters"] == "3000"
    assert at_entry["locationID"] == "https://sws.geonames.org/2929567/"
    assert at_own["locality"] == "Irgendein Weiher"
    assert at_own["decimalLatitude"] == at_own["coordinateUncertaintyInMeters"] == at_own["geodeticDatum"] == ""


def test_dwca_occurrence_v4_columns() -> None:
    from laubmann_kg.dwca.occurrence import build_occurrences
    entry = _entry()
    t = lambda *a, **k: Taxon(*a, **k)   # noqa: E731
    entry.observations = [
        Observation(entry_uid=entry.entry_uid, taxon=t("Kiebitze", "Vanellus vanellus", rank="species",
                                                       is_bird=True),
                    verbatim_notes="♂♂ und ♀♀", index=0, sex="mixed",
                    occurrence_remarks="Lesung korrigiert"),
        Observation(entry_uid=entry.entry_uid, taxon=t("Limikolen", "Charadrii", rank="group", is_bird=True),
                    verbatim_notes="l", index=1),
        Observation(entry_uid=entry.entry_uid, taxon=t("Raubvogel", None, rank="group", is_bird=True),
                    verbatim_notes="r", index=2),
        Observation(entry_uid=entry.entry_uid, taxon=t("Reh", None, rank="species", is_bird=False),
                    verbatim_notes="h", index=3),
        Observation(entry_uid=entry.entry_uid, taxon=t("Singdrossel", "Turdus philomelos", rank="species",
                                                       is_bird=True),
                    verbatim_notes="s", index=4, time_of_day="dawn", flight_direction="NO",
                    evidence=[Evidence("auditory", "Gesang", is_call=True, call_type="song",
                                       call_transcription="judit judit"),
                              Evidence("auditory", "Ruf", is_call=True, call_type="song",
                                       call_transcription="zipp")]),
    ]
    rows = {r["vernacularName"]: r for r in build_occurrences(ExtractionResult(entries=[entry]))}
    assert rows["Kiebitze"]["sex"] == "male | female"                       # no DwC value for "mixed"
    assert rows["Kiebitze"]["occurrenceRemarks"] == "♂♂ und ♀♀ — Lesung korrigiert"
    assert (rows["Limikolen"]["scientificName"], rows["Limikolen"]["taxonRank"]) == ("Charadrii", "")
    assert (rows["Raubvogel"]["scientificName"], rows["Raubvogel"]["taxonRank"]) == ("Aves", "class")
    assert (rows["Reh"]["scientificName"], rows["Reh"]["taxonRank"]) == ("", "")
    props = json.loads(rows["Singdrossel"]["dynamicProperties"])
    assert props == {"flightDirection": "NO", "callTranscription": "judit judit | zipp"}
    assert rows["Singdrossel"]["occurrenceID"] == data_iri(entry.observations[4].uid)


def test_emof_dedups_evidence_and_call_types_and_emits_time_of_day() -> None:
    from laubmann_kg.dwca.measurement_or_fact import build_measurements
    entry = _entry()
    singdrossel = Observation(
        entry_uid=entry.entry_uid, taxon=Taxon("Singdrossel", "Turdus philomelos"), verbatim_notes="s",
        index=0, time_of_day="dawn",
        evidence=[Evidence("auditory", "Gesang", is_call=True, call_type="song"),
                  Evidence("auditory", "Gesang 2", is_call=True, call_type="song"),
                  Evidence("auditory", "Ruf", is_call=True, call_type="call")])
    entry.observations = [singdrossel]
    rows = build_measurements(ExtractionResult(entries=[entry]))
    occ = data_iri(singdrossel.uid)
    assert [(r["measurementType"], r["measurementValue"]) for r in rows] == [
        ("evidenceKind", "auditory"), ("callType", "song"), ("callType", "call"),
        ("recordType", "field-observation"), ("timeOfDay", "dawn")]
    by_type = {r["measurementType"]: r for r in rows}
    assert by_type["timeOfDay"]["measurementTypeID"].endswith("#timeOfDayScheme")
    assert by_type["timeOfDay"]["measurementValueID"].endswith("#timeofday_dawn")
    assert by_type["timeOfDay"]["measurementID"] == f"{occ}:timeOfDay:0"
    assert [r["measurementID"] for r in rows if r["measurementType"] == "callType"] == \
        [f"{occ}:callType:0", f"{occ}:callType:1"]
    assert all(r["eventID"] == data_iri(entry.uid) for r in rows)


# --- harmonisation of shared nodes ---------------------------------------------------------

def test_harmonize_gives_every_name_one_taxon_and_one_place() -> None:
    from laubmann_kg.normalization.harmonize import harmonize
    isar_region = Place("Isar", "Isar", kind="region")
    isar_locality = Place("Isar", "Isar", kind="locality", lat=48.2, long=11.7)
    entries = []
    readings = [("Numenius", "genus", 0.9, isar_locality), ("Numenius", "genus", 0.8, isar_locality),
                ("Numenius arquata", "species", 0.7, isar_region), (None, None, None, isar_locality)]
    for i, (sci, rank, conf, place) in enumerate(readings):
        e = _entry(uid=f"e_h{i}")
        e.place = place
        e.observations = [Observation(entry_uid=e.entry_uid, verbatim_notes="b", index=0, place=place,
                                      taxon=Taxon("Brachvogel", sci, rank=rank, confidence=conf,
                                                  is_bird=True if i else None))]
        entries.append(e)
    # an unambiguous name is left alone
    entries[0].observations.append(Observation(entry_uid="e_h0", verbatim_notes="a", index=1,
                                               taxon=Taxon("Amsel", "Turdus merula", rank="species")))
    result = ExtractionResult(entries=entries)
    summary = harmonize(result)
    assert summary == {"taxa": 1, "places": 1}
    taxa = [e.observations[0].taxon for e in entries]
    # the most frequent (scientific name, rank) PAIR wins: a genus never gets rank species
    assert {(t.scientific_name, t.rank) for t in taxa} == {("Numenius", "genus")}
    assert all(t.is_bird is True for t in taxa)                            # majority of stated values
    assert [t.confidence for t in taxa] == [0.9, 0.8, 0.7, None]           # per-record confidence kept
    assert entries[0].observations[1].taxon.scientific_name == "Turdus merula"
    # places: kind (and coordinates) by majority, one object for every use
    places = {id(e.place) for e in entries} | {id(e.observations[0].place) for e in entries}
    assert len(places) == 1
    assert entries[2].place.kind == "locality" and (entries[2].place.lat, entries[2].place.long) == (48.2, 11.7)
    graph = build_graph(result)
    assert graph.value(DATA[entries[2].place.uid], LKG.placeKind) == Literal("locality")
    assert graph.value(DATA[taxa[0].uid], DWC.taxonRank) == Literal("genus")


def test_harmonize_reaches_travel_places() -> None:
    from laubmann_kg.normalization.harmonize import harmonize_places
    a = Place("Ulm", "Ulm", kind="settlement", elevation_m=478.0)
    b = Place("Ulm", "Ulm", kind="settlement", elevation_m=478.0)
    c = Place("Ulm", "Ulm", kind="region")
    e = _entry(uid="e_tr")
    e.place = a
    e.observations = [Observation(entry_uid="e_tr", taxon=Taxon("A"), verbatim_notes="a", place=b)]
    e.travel_events = [TravelEvent("e_tr", legs=[TravelLeg(None, c, via_places=(c,))])]
    assert harmonize_places([e]) == 1
    leg = e.travel_events[0].legs[0]
    assert leg.arrival_place.kind == "settlement" and leg.arrival_place.elevation_m == 478.0
    assert leg.via_places[0] == leg.arrival_place == e.place == e.observations[0].place


# --- OCR year repair of the record dates -----------------------------------------------------

def test_coverage_year_repair_shifts_record_dates_and_travel_times() -> None:
    from laubmann_kg.normalization.coverage import Span, VolumeCoverage, apply_coverage

    def mk(uid: str, date: str, raw: str | None = None) -> DiaryEntry:
        e = DiaryEntry(entry_uid=uid, entry_id=f"L23-{uid}", volume=23, page_uid=f"p_{uid}",
                       page_id="docA_0001_L", region_uid=None, scan=None, entry_date=date,
                       verbatim_event_date=raw or date, location_raw=None,
                       text_clean=f"Text {uid} " + "x" * 100)
        e.entry_kind = "field-day"
        return e

    x = mk("x", "1901-04-07", raw="7. April 1901")                          # OCR 0 for 5
    x.entry_date_end = "1901-04-08"
    x.date_plausible = False                                               # the model saw the contradiction
    x.observations = [
        Observation(entry_uid="x", taxon=Taxon("Kiebitz"), verbatim_notes="k", index=0,
                    event_date="1901-04-08", event_date_end="1901-04-09"),
        Observation(entry_uid="x", taxon=Taxon("Storch"), verbatim_notes="s", index=1,
                    event_date="1949-06-01"),                                # own, different year: stays
        Observation(entry_uid="x", taxon=Taxon("Amsel"), verbatim_notes="a", index=2),
    ]
    x.travel_events = [TravelEvent("x", legs=[TravelLeg(
        None, Place("Ismaning"), departure_time="1901-04-07T06:00:00", arrival_time="1901-04-07T07:30:00")])]
    seq = [mk("a", "1951-04-01"), mk("b", "1951-04-05"), x, mk("c", "1951-04-09"), mk("d", "1951-04-12")]
    kept, flags = apply_coverage(seq, VolumeCoverage({23: Span("1950-07", "1951-08")}))
    x = next(e for e in kept if e.entry_uid == "x")
    assert (x.entry_date, x.entry_date_end) == ("1951-04-07", "1951-04-08")
    assert x.date_plausible is None                                        # contradiction resolved
    kiebitz, storch, amsel = x.observations
    assert (kiebitz.event_date, kiebitz.event_date_end) == ("1951-04-08", "1951-04-09")
    assert storch.event_date == "1949-06-01"
    assert amsel.event_date is None
    leg = x.travel_events[0].legs[0]
    assert (leg.departure_time, leg.arrival_time) == ("1951-04-07T06:00:00", "1951-04-07T07:30:00")
    assert [f.reason for f in flags] == ["date_year_corrected"]


def test_shift_years_keeps_ranges_consistent() -> None:
    from laubmann_kg.normalization.coverage import _shift_years
    e = _entry(uid="e_sh", date="1901-12-30")
    e.entry_date_end = "1902-01-02"                                        # spans the new year
    moved = Observation(entry_uid="e_sh", taxon=Taxon("A"), verbatim_notes="a", index=0,
                        event_date="1901-12-30", event_date_end="1901-12-31")
    inverted = Observation(entry_uid="e_sh", taxon=Taxon("B"), verbatim_notes="b", index=1,
                           event_date="1960-05-01", event_date_end="1901-05-03")   # own start stays
    e.observations = [moved, inverted]
    _shift_years(e, 1901, 1951)
    assert e.entry_date_end == "1952-01-02"                                # by the same 50 years
    assert (moved.event_date, moved.event_date_end) == ("1951-12-30", "1951-12-31")
    # an end that would now lie before its start is dropped
    assert inverted.event_date == "1960-05-01" and inverted.event_date_end is None


# --- truncated model output ------------------------------------------------------------------

def test_truncated_output_flags_the_entry_for_qa(tmp_path: Path) -> None:
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import CachedClient, TruncatedOutput, TruncatedText
    from laubmann_kg.qa import run_qa

    class Truncating:
        model = "fake-truncating"

        def complete(self, prompt: str) -> str:
            raise TruncatedOutput('{"entry_place": {"name": "München"}, "observations": '
                                  '[{"vernacular_de": "Amsel", "verbatim_notes": "n"}, {"vernacular_de": "Buchf')

    client = CachedClient(Truncating(), cache=LLMCache(tmp_path / "cache"), attempts=1)
    entry, obs = _extract(None, client=client)
    assert isinstance(client.complete("x"), TruncatedText) and TruncatedText("x").truncated is True
    assert entry.flags == ["truncated_output"]
    assert obs and obs[0].taxon.vernacular_de == "Amsel"                  # the repaired prefix is used
    _, flags = run_qa([entry], {"misdate": False})
    truncated = [f for f in flags if f.reason == "truncated_output"]
    assert len(truncated) == 1 and truncated[0].action == "flagged" and truncated[0].entry_uid == entry.entry_uid
    # a complete answer carries no flag
    fine, _ = _extract({"observations": [_item("Amsel")]})
    assert fine.flags == []
    assert not [f for f in run_qa([fine], {"misdate": False})[1] if f.reason == "truncated_output"]


def test_person_corrections_reach_the_co_observers() -> None:
    from laubmann_kg.normalization.corrections import Correction, apply_corrections
    kifer, swallow = Person("Kifer", role="companion"), Person("Rauchschwalbe", role="companion")
    entry = _entry(uid="e_corr")
    entry.persons = [kifer, swallow]
    obs = Observation(entry_uid="e_corr", taxon=Taxon("Kiebitz"), verbatim_notes="k",
                      co_observers=[kifer, swallow])
    entry.observations = [obs]
    apply_corrections([entry], [Correction("person", "Kifer", "Kiefer", entry_uid="e_corr"),
                                Correction("person", "Rauchschwalbe", action="drop", entry_uid="e_corr")])
    assert [p.name for p in obs.co_observers] == ["Kiefer"]              # renamed; the non-person dropped
    assert [p.name for p in entry.persons] == ["Kiefer"]
    assert [p.name for p in obs.recorders] == ["Alfred Laubmann", "Kiefer"]


def test_only_confirmed_breeding_is_a_reproductive_condition() -> None:
    from laubmann_kg.kg.model import Behaviour
    from laubmann_kg.normalization.vocabularies import BREEDING_IMPLIES_BREEDING, basis_of_record, reproductive_condition
    assert BREEDING_IMPLIES_BREEDING == ("confirmed",)
    assert reproductive_condition("confirmed", []) == "breeding"
    assert reproductive_condition("probable", []) is None
    assert reproductive_condition("possible", [Behaviour("Balz", reproductive_condition="breeding")]) == "breeding"
    # basisOfRecord: MaterialCitation only for a literature record WITH a citation
    assert basis_of_record("literature-record", ["specimen"], True) == "MaterialCitation"
    assert basis_of_record("literature-record", ["specimen"], False) == "PreservedSpecimen"
    assert basis_of_record("literature-record", [], False) == "HumanObservation"
    assert basis_of_record("literature-record", []) == "MaterialCitation"      # default: has a citation


def test_entry_event_date_interval_only_for_a_real_range() -> None:
    entry = _entry(uid="e_day", date="1921-05-03")
    entry.entry_date_end = "1921-05-03"
    entry.observations = [Observation(entry_uid="e_day", taxon=Taxon("Amsel"), verbatim_notes="a")]
    graph = build_graph(ExtractionResult(entries=[entry]))
    assert graph.value(DATA[entry.uid], DWC.eventDate) == Literal("1921-05-03", datatype=XSD.date)
    assert graph.value(DATA[entry.observations[0].uid], DWC.eventDate) == Literal("1921-05-03", datatype=XSD.date)
    assert graph.value(DATA[entry.uid], DWC.verbatimLocality) == Literal("München")   # header wording


def test_literature_without_citation_is_flagged_for_qa() -> None:
    from laubmann_kg.qa import run_qa
    entry, obs = _extract({"observations": [
        _item("Uhu", record_type="literature-record"),
        _item("Kauz", record_type="literature-record", literature_citation="Jäckel 1891, S. 3"),
    ]})
    assert obs[0].flags == ("literature_without_citation",) and obs[1].flags == ()
    _, flags = run_qa([entry], {"misdate": False})
    assert [(f.reason, f.value) for f in flags if f.reason == "literature_without_citation"] == \
        [("literature_without_citation", "Uhu")]
