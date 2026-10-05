"""Reviewer corrections of record fields and added records (review/observation_corrections.csv)."""

from __future__ import annotations

import csv
from pathlib import Path

from laubmann_kg.kg.model import DiaryEntry, Observation, Person, Place, Taxon
from laubmann_kg.normalization.observation_corrections import (
    FIELDS, RecordCorrection, apply_observation_corrections, load_observation_corrections, parse_count)

ISMANING = Place(verbatim="Ismaning", canonical="Ismaning", kind="settlement")
WESTBECKEN = Place(verbatim="Westbecken", canonical="Westbecken", kind="locality")
KIEBITZ = Taxon("Kiebitz", scientific_name="Vanellus vanellus", rank="species", is_bird=True)
STAR = Taxon("Star", scientific_name="Sturnus vulgaris", rank="species", is_bird=True)


def _entry(uid: str = "e1", observations=()) -> DiaryEntry:
    e = DiaryEntry(entry_uid=uid, entry_id="L24-" + uid, volume=24, page_uid="p", page_id="doc_0007_L", region_uid=None,
                   scan=None, entry_date="1951-05-13", verbatim_event_date=None, location_raw="Ismaning", text_clean="t")
    e.place = ISMANING
    e.observations = list(observations)
    for o in e.observations:
        o.entry_uid, o.place = uid, o.place or ISMANING
    return e


def _obs(taxon: Taxon, i: int, **kw) -> Observation:
    return Observation(entry_uid="", taxon=taxon, verbatim_notes=f"n{i}", index=i, **kw)


def _fix(field: str, new: str, written: str = "Kiebitz", **kw) -> RecordCorrection:
    return RecordCorrection("e1", "L24-e1", written, field=field, new=new, **kw)


def test_count_forms() -> None:
    assert parse_count("5") == {"individual_count": 5, "count_min": None, "count_max": None, "count_qualifier": "exact"}
    assert parse_count("3-5") == {"individual_count": 3, "count_min": 3, "count_max": 5, "count_qualifier": "approximate"}
    assert parse_count("80 bis 100")["count_max"] == 100
    assert parse_count("ca. 20")["count_qualifier"] == "approximate"
    assert parse_count("mind. 30")["count_qualifier"] == "minimum"
    assert parse_count("bis 20")["count_qualifier"] == "maximum"
    assert parse_count("1.200")["individual_count"] == 1200
    assert parse_count("einige") == {"individual_count": None, "count_min": None, "count_max": None,
                                     "count_qualifier": "plural-unspecified"}
    assert parse_count("-")["count_qualifier"] is None
    assert parse_count("5 Paare und 3") is None


def test_fields_of_one_record_are_set_and_reported() -> None:
    o = _obs(KIEBITZ, 0, individual_count=3, count_qualifier="exact", record_type="third-party-report",
             observer=Person("W. Wüst", role="source"))
    e = _entry(observations=[o, _obs(STAR, 1)])
    n, flags = apply_observation_corrections([e, _entry("e2", [_obs(WESTBECKEN and KIEBITZ, 0)])], [
        _fix("count", "200-250"), _fix("locality", "Westbecken"), _fix("date", "1951-05-12"),
        _fix("record_type", "field-observation"), _fix("observer", "-"), _fix("co_observers", "E. Bezzel; H. Remold"),
        _fix("sex", "male"), _fix("breeding", "confirmed")])
    assert n == 8 and [f.reason for f in flags] == ["record_corrected"] * 8
    assert (o.individual_count, o.count_min, o.count_max, o.count_qualifier) == (200, 200, 250, "approximate")
    assert o.locality.name == "Westbecken" and o.place is o.locality
    assert o.event_date == "1951-05-12" and o.record_type == "field-observation" and o.observer is None
    assert [p.name for p in o.co_observers] == ["E. Bezzel", "H. Remold"]
    assert {p.name for p in e.persons} >= {"E. Bezzel", "H. Remold"}
    assert o.sex == "male" and o.breeding_evidence == "confirmed"
    assert "Anzahl bei der Durchsicht korrigiert: „3“ → „200-250“" in o.occurrence_remarks
    assert e.observations[1].individual_count is None


def test_record_is_found_by_index_then_by_occurrence() -> None:
    a, b = _obs(KIEBITZ, 2, individual_count=1), _obs(KIEBITZ, 7, individual_count=1)
    e = _entry(observations=[a, _obs(STAR, 4), b])
    apply_observation_corrections([e], [_fix("count", "9", obs_index=7), _fix("count", "4", obs_index=99, occurrence=0)])
    assert (a.individual_count, b.individual_count) == (4, 9)
    # ambiguous without a key, and a name that is not there: reported, nothing changed
    n, flags = apply_observation_corrections([e], [_fix("count", "5"), _fix("count", "5", written="Amsel", occurrence=0)])
    assert n == 0 and [f.reason for f in flags] == ["correction_unmatched"] * 2


def test_merged_spelling_is_found_by_the_written_name() -> None:
    o = _obs(KIEBITZ, 0)
    o.taxon_verbatim = "Kibitz"
    e = _entry(observations=[o])
    assert apply_observation_corrections([e], [_fix("count", "2", written="Kibitz", obs_index=0)])[0] == 1
    assert o.individual_count == 2


def test_clearing_and_unreadable_values() -> None:
    o = _obs(KIEBITZ, 0, individual_count=3, count_qualifier="exact", sex="male", locality=WESTBECKEN, place=WESTBECKEN,
             event_date="1951-05-12")
    e = _entry(observations=[o])
    n, flags = apply_observation_corrections([e], [
        _fix("count", "-"), _fix("sex", "-"), _fix("locality", "-"), _fix("date", "-"),
        _fix("record_type", "eigene"), _fix("date", "12. Mai"), _fix("count", "viele 5er")])
    assert n == 4
    assert o.individual_count is None and o.sex is None and o.locality is None and o.place is ISMANING and o.event_date is None
    assert [f.reason for f in flags].count("correction_unmatched") == 3 and o.record_type == "field-observation"


def test_absent_status_drops_the_count() -> None:
    o = _obs(KIEBITZ, 0, individual_count=3, count_qualifier="exact")
    apply_observation_corrections([_entry(observations=[o])], [_fix("status", "absent")])
    assert o.occurrence_status == "absent" and o.individual_count is None


def test_entry_date_and_kind() -> None:
    e = _entry(observations=[_obs(KIEBITZ, 0)])
    n, _ = apply_observation_corrections([e], [RecordCorrection("e1", field="entry_date", new="1951-05-12/1951-05-14"),
                                               RecordCorrection("e1", field="entry_kind", new="species-digest")])
    assert n == 2 and (e.entry_date, e.entry_date_end, e.entry_kind) == ("1951-05-12", "1951-05-14", "species-digest")
    assert "1951-05-13" in e.date_note


def test_added_record_reuses_known_taxon_and_is_added_once() -> None:
    e = _entry(observations=[_obs(STAR, 3)])
    other = _entry("e2", [_obs(KIEBITZ, 0)])
    add = RecordCorrection("e1", "L24-e1", "Kiebitz", action="add", add=(
        ("species_de", "Kiebitz"), ("count", "ca. 40"), ("locality", "Westbecken"), ("observer", "E. Bezzel"),
        ("text", "ca. 40 Kiebitze über dem Wb. (Bezzel)")))
    n, flags = apply_observation_corrections([e, other], [add])
    new = e.observations[-1]
    assert n == 1 and [f.reason for f in flags] == ["record_added"]
    assert new.taxon is KIEBITZ and new.index == 4 and new.individual_count == 40 and new.count_qualifier == "approximate"
    assert new.locality.name == "Westbecken" and new.observer.name == "E. Bezzel" and new.record_type == "third-party-report"
    assert apply_observation_corrections([e, other], [add])[0] == 0 and len(e.observations) == 2
    fresh = RecordCorrection("e1", written="Zwergmöwe", action="add", add=(("species_de", "Zwergmöwe"),
                             ("scientific_name", "Hydrocoloeus minutus"), ("gbif_key", "6065810")))
    apply_observation_corrections([e, other], [fresh])
    t = e.observations[-1].taxon
    assert (t.scientific_name, t.rank, t.gbif_key, t.match_method) == ("Hydrocoloeus minutus", "species", 6065810, "review")


def test_load_validates_rows_and_filters_confidence(tmp_path: Path) -> None:
    path = tmp_path / "observation_corrections.csv"
    rows = [
        {"entry_uid": "e1", "written": "Kiebitz", "obs_index": "3", "field": "count", "new_value": "5", "confidence": "0.95"},
        {"entry_uid": "e1", "written": "Kiebitz", "field": "count", "new_value": "5", "confidence": "0.5"},
        {"entry_uid": "e1", "written": "Kiebitz", "field": "colour", "new_value": "x"},          # unknown field
        {"entry_uid": "e1", "written": "", "field": "count", "new_value": "5"},                  # record field without a record
        {"entry_uid": "e1", "written": "Kiebitz", "field": "entry_kind", "new_value": "other"},  # entry field with a record
        {"entry_uid": "", "written": "Kiebitz", "field": "count", "new_value": "5"},
        {"entry_uid": "e1", "action": "add", "species_de": "Star", "count": "3", "text": "3 Stare"},
        {"entry_uid": "e1", "action": "add"},                                                    # add without a species
        {"entry_uid": "e1", "field": "entry_date", "new_value": "1951-05-12"},
    ]
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=FIELDS + ["confidence"])
        w.writeheader()
        w.writerows(rows)
    loaded = load_observation_corrections(path, min_confidence=0.9)
    assert [(c.action, c.field, c.written) for c in loaded] == [("set", "count", "Kiebitz"), ("add", "", "Star"), ("set", "entry_date", "")]
    assert loaded[0].obs_index == 3 and dict(loaded[1].add) == {"species_de": "Star", "count": "3", "text": "3 Stare"}
    assert len(load_observation_corrections(path)) == 4
    assert load_observation_corrections(tmp_path / "absent.csv") == []


def test_attribution_rows_move_a_record_from_the_diarist_to_the_report_author() -> None:
    # review.machine.attribution (attribution_check.py): a pasted report's record credited to Laubmann
    own = _obs(KIEBITZ, 0, co_observers=[Person("Walter Wüst", role="companion"), Person("Heinz Remold", role="companion")])
    unknown = _obs(STAR, 1)
    e = _entry(observations=[own, unknown])
    assert [p.name for p in own.recorders] == ["Alfred Laubmann", "Walter Wüst", "Heinz Remold"]
    n, _ = apply_observation_corrections([e], [
        _fix("record_type", "third-party-report", obs_index=0), _fix("observer", "Walter Wüst", obs_index=0),
        _fix("co_observers", "Heinz Remold", obs_index=0),
        _fix("record_type", "third-party-report", written="Star", obs_index=1)])     # author unknown: no observer row
    assert n == 4
    assert own.record_type == "third-party-report" and [p.name for p in own.recorders] == ["Walter Wüst", "Heinz Remold"]
    assert unknown.record_type == "third-party-report" and unknown.recorders == []   # no recordedBy, not the diarist
    assert "Walter Wüst" in {p.name for p in e.persons}
