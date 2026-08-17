from laubmann_kg.qa import QAFlag, run_qa, write_review_table
from laubmann_kg.kg.model import (
    DiaryEntry,
    Observation,
    Place,
    Taxon,
    TravelEvent,
    TravelLeg,
    WeatherReport,
)


def _entry(eid, date, loc="München", obs=None, volume=2, place="München", **kw):
    e = DiaryEntry(entry_uid="u_" + eid, entry_id=eid, volume=volume, page_uid="p",
                   page_id="pg", region_uid=None, scan=None, entry_date=date,
                   verbatim_event_date=date, location_raw=loc, text_clean="x",
                   observations=obs or [], **kw)
    e.place = Place(verbatim=loc or place, canonical=place) if place else None
    return e


def _obs(vern, sci=None, **taxon_kw):
    return Observation(entry_uid="u", taxon=Taxon(vernacular_de=vern, scientific_name=sci, **taxon_kw),
                       verbatim_notes="n")


# --- dates ------------------------------------------------------------------

def test_misdate_is_a_flag_by_default_and_exclusion_is_opt_in():
    ok = _obs("Buchfink", "Fringilla coelebs")
    entries = [_entry("good", "1919-05-01", obs=[ok]), _entry("bad", "1859-05-01", obs=[ok])]
    kept, flags = run_qa(entries, {"exclude": True, "year_min": 1918, "year_max": 1919})
    assert {e.entry_id for e in kept} == {"good", "bad"}      # kept: a real 1859 collection record is possible
    assert any(f.reason == "misdate" and f.action == "flagged" and f.entry_id == "bad" for f in flags)

    entries = [_entry("good", "1919-05-01", obs=[ok]), _entry("bad", "1859-05-01", obs=[ok])]
    kept, flags = run_qa(entries, {"exclude": True, "exclude_misdate": True,
                                   "year_min": 1918, "year_max": 1919})
    assert {e.entry_id for e in kept} == {"good"}
    assert any(f.reason == "misdate" and f.action == "excluded" for f in flags)


def test_misdate_exclusion_spares_retrospective_entries():
    ok = _obs("Buchfink", "Fringilla coelebs")
    e = _entry("digest", "1909-08-05", obs=[ok], entry_kind="species-digest")
    kept, flags = run_qa([e], {"exclude": True, "exclude_misdate": True,
                               "year_min": 1918, "year_max": 1919})
    assert len(kept) == 1
    assert any(f.reason == "misdate" and f.action == "flagged" for f in flags)


def test_misdate_span_is_per_volume():
    # Regression: the full 34-volume corpus spans decades. A GLOBAL median±2
    # excluded 89% of all entries; the span must be computed per volume.
    ok = _obs("Buchfink", "Fringilla coelebs")
    entries = ([_entry(f"v2-{i}", "1918-05-01", obs=[ok], volume=2) for i in range(3)]
               + [_entry(f"v30-{i}", "1955-06-01", obs=[ok], volume=30) for i in range(3)]
               + [_entry("v2-bad", "1859-05-01", obs=[ok], volume=2)])
    _, flags = run_qa(entries, {"exclude": True})
    misdates = [f for f in flags if f.reason == "misdate"]
    assert len(misdates) == 1 and misdates[0].entry_id == "v2-bad"
    assert "Band 2" in misdates[0].detail


def test_implausible_date_from_model_excludes_entry():
    ok = _obs("Buchfink", "Fringilla coelebs")
    e = _entry("bad", "1985-03-19", obs=[ok], date_plausible=False,
               date_note="Jahr 85 ist die laufende Artnummer")
    kept, flags = run_qa([e], {"exclude": True})
    assert kept == []
    f = next(f for f in flags if f.reason == "implausible_date")
    assert f.action == "excluded" and "Artnummer" in f.detail


def test_corrected_date_is_flagged_not_excluded():
    ok = _obs("Buchfink", "Fringilla coelebs")
    e = _entry("c", "1949-03-19", obs=[ok], header_date="1985-03-19")
    kept, flags = run_qa([e], {"exclude": True})
    assert len(kept) == 1
    assert any(f.reason == "date_corrected" and f.action == "flagged" for f in flags)


# --- taxa (model signals, no keyword rules) ---------------------------------

def test_non_bird_observation_excluded_by_default():
    e = _entry("e", "1919-05-01", obs=[_obs("Reh", "Capreolus capreolus", is_bird=False),
                                        _obs("Buchfink", "Fringilla coelebs", is_bird=True)])
    kept, flags = run_qa([e], {"exclude": True})
    assert [o.taxon.vernacular_de for o in kept[0].observations] == ["Buchfink"]
    assert any(f.reason == "non_bird" and f.value == "Reh" and f.action == "excluded" for f in flags)
    # opt-out keeps natural-history records in the graph
    e = _entry("e", "1919-05-01", obs=[_obs("Reh", "Capreolus capreolus", is_bird=False)])
    kept, flags = run_qa([e], {"exclude": True, "exclude_non_bird": False})
    assert len(kept[0].observations) == 1 and flags[0].action == "flagged"


def test_low_confidence_unranked_taxon_excluded_but_genus_level_kept():
    e = _entry("e", "1919-05-01", obs=[
        _obs("Tolarla", None, rank="unknown", confidence=0.1),          # noise: model itself unsure
        _obs("Limose", "Limosa", rank="genus", confidence=1.0),         # genus-level record: kept
        _obs("Spötter", None, rank="genus", confidence=0.9),            # rank stated -> kept
        _obs("Kormoran", None, is_bird=True, confidence=1.0),           # unresolved but confident -> kept
        _obs("Wied", None),                                             # offline/legacy: no signal -> kept
    ])
    kept, flags = run_qa([e], {"exclude": True})
    assert [o.taxon.vernacular_de for o in kept[0].observations] == ["Limose", "Spötter", "Kormoran", "Wied"]
    assert any(f.reason == "low_confidence_taxon" and f.value == "Tolarla" for f in flags)
    assert not any(f.reason == "low_confidence_taxon" and f.value == "Wied" for f in flags)


def test_record_type_conflict_flagged():
    o = _obs("Buchfink", "Fringilla coelebs")
    o.flags = ("record_type_conflict",)
    _, flags = run_qa([_entry("e", "1919-05-01", obs=[o])], {"exclude": True})
    assert any(f.reason == "record_type_conflict" and f.action == "flagged" for f in flags)


# --- place / structure ------------------------------------------------------

def test_nonplace_flagged_when_model_found_no_place():
    e = _entry("e", "1919-05-01", loc="Rauchschwalben", place=None,
               obs=[_obs("Buchfink", "Fringilla coelebs")])
    _, flags = run_qa([e], {"exclude": True})
    assert any(f.reason == "nonplace" and f.value == "Rauchschwalben" for f in flags)


def test_flag_only_mode_keeps_everything():
    e = _entry("e", "1859-05-01", obs=[_obs("Reh", is_bird=False)], date_plausible=False)
    kept, flags = run_qa([e], {"exclude": False, "year_min": 1918, "year_max": 1919})
    assert len(kept) == 1 and len(kept[0].observations) == 1
    assert flags and all(f.action == "flagged" for f in flags)


def test_empty_entry_with_weather_or_travel_reason_no_observations():
    e_weather = _entry("w", "1919-05-01")
    e_weather.weather = WeatherReport(verbatim="Regen")
    place = Place(verbatim="München")
    e_travel = _entry("t", "1919-05-01")
    e_travel.travel_events = [TravelEvent(entry_uid="u_t", legs=[
        TravelLeg(departure_place=place, arrival_place=place)])]
    kept, flags = run_qa([e_weather, e_travel], {"exclude": True})
    assert len(kept) == 2                       # flagged, never excluded
    by_id = {f.entry_id: f for f in flags}
    assert by_id["w"].reason == "no_observations"
    assert by_id["t"].reason == "no_observations"
    assert all(f.action == "flagged" for f in flags)


def test_empty_entry_without_weather_or_travel_stays_empty():
    e = _entry("e", "1919-05-01")
    kept, flags = run_qa([e], {"exclude": True})
    assert len(kept) == 1
    assert any(f.reason == "empty" and f.action == "flagged" for f in flags)


def test_review_table_written(tmp_path):
    p = write_review_table([QAFlag("e", "u", "misdate", "d", "excluded", "1859-05-01")],
                           tmp_path / "review" / "qa.csv")
    assert p.exists() and "misdate" in p.read_text(encoding="utf-8")
