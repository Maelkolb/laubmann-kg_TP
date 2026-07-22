from laubmann_kg.qa import QAFlag, plausible_bird, run_qa, write_review_table
from laubmann_kg.kg.model import DiaryEntry, Observation, Taxon


def _entry(eid, date, loc="München", obs=None):
    return DiaryEntry(entry_uid="u_" + eid, entry_id=eid, volume=2, page_uid="p", page_id="pg",
                      region_uid=None, scan=None, entry_date=date, verbatim_event_date=date,
                      location_raw=loc, text_clean="x", observations=obs or [])


def _obs(vern, sci=None):
    return Observation(entry_uid="u", taxon=Taxon(vernacular_de=vern, scientific_name=sci),
                       verbatim_notes="n")


def test_plausible_bird_keeps_real_drops_garbage():
    assert plausible_bird("Gartenlaubvogel")   # folk name for a real warbler
    assert plausible_bird("Bergzeisig")
    assert plausible_bird("Drossel")
    assert not plausible_bird("Tolarla")
    assert not plausible_bird("Beidbeiß")


def test_misdate_entry_excluded():
    entries = [_entry("good", "1919-05-01", obs=[_obs("Buchfink", "Fringilla coelebs")]),
               _entry("bad", "1859-05-01", obs=[_obs("Buchfink", "Fringilla coelebs")])]
    kept, flags = run_qa(entries, {"exclude": True, "year_min": 1918, "year_max": 1919})
    assert {e.entry_id for e in kept} == {"good"}
    assert any(f.reason == "misdate" and f.action == "excluded" and f.entry_id == "bad"
               for f in flags)


def test_garbage_taxon_observation_excluded():
    e = _entry("e", "1919-05-01", obs=[_obs("Tolarla"), _obs("Buchfink", "Fringilla coelebs")])
    kept, flags = run_qa([e], {"exclude": True, "year_min": 1918, "year_max": 1919})
    assert [o.taxon.vernacular_de for o in kept[0].observations] == ["Buchfink"]
    assert any(f.reason == "garbage_taxon" and f.value == "Tolarla" for f in flags)


def test_nonplace_location_flagged():
    e = _entry("e", "1919-05-01", loc="Rauchschwalben",
               obs=[_obs("Buchfink", "Fringilla coelebs")])
    _, flags = run_qa([e], {"exclude": True, "year_min": 1918, "year_max": 1919})
    assert any(f.reason == "nonplace" and f.value == "Rauchschwalben" for f in flags)


def test_flag_only_mode_keeps_everything():
    e = _entry("e", "1859-05-01", obs=[_obs("Tolarla")])
    kept, flags = run_qa([e], {"exclude": False, "year_min": 1918, "year_max": 1919})
    assert len(kept) == 1 and len(kept[0].observations) == 1
    assert flags and all(f.action == "flagged" for f in flags)


def test_review_table_written(tmp_path):
    p = write_review_table([QAFlag("e", "u", "misdate", "d", "excluded", "1859-05-01")],
                           tmp_path / "review" / "qa.csv")
    assert p.exists() and "misdate" in p.read_text(encoding="utf-8")
