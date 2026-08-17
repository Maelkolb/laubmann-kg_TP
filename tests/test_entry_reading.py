"""The model reads the entry (date, place, kind) and the per-record detail; the
mapper only enforces form. These tests pin the no-heuristics contract:
nothing is fabricated, nothing is guessed from prose, model signals win."""

import json
from pathlib import Path

from laubmann_kg.extraction.llm_observations import (
    extract_observations_llm,
    load_entry_schema,
    map_entry_date,
    map_entry_place,
)
from laubmann_kg.kg.model import DiaryEntry, Place
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.normalization.taxa import SeedTaxonResolver

PROMPTS = PromptLibrary(Path("prompts"))
SCHEMA = load_entry_schema()


class FakeClient:
    model = "fake"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload


def _entry(text="...", location_raw="München - Kaufbeuren 843 m (Kiefer)",
           date="1949-03-19", date_raw="19.III. 49") -> DiaryEntry:
    return DiaryEntry(
        entry_uid="e_read", entry_id="L20-e0001", volume=20, page_uid="p", page_id="pid",
        region_uid="r", scan="4", entry_date=date, verbatim_event_date=date_raw,
        location_raw=location_raw, text_clean=text,
    )


def _run(payload, entry=None, fallback_place=None):
    entry = entry or _entry()
    client = FakeClient(json.dumps(payload) if not isinstance(payload, str) else payload)
    obs = extract_observations_llm(entry, client, SeedTaxonResolver(), fallback_place,
                                   PROMPTS, SCHEMA)
    return entry, obs, client


def _item(**kw):
    base = {"vernacular_de": "Buchfink", "verbatim_notes": "n", "is_bird": True, "confidence": 0.9}
    base.update(kw)
    return base


# --- prompt input -----------------------------------------------------------

def test_prompt_carries_verbatim_date_and_header():
    _, _, client = _run({"observations": []})
    p = client.prompts[0]
    assert "date_iso: 1949-03-19" in p
    assert "date_verbatim: 19.III. 49" in p
    assert "location_header: München - Kaufbeuren 843 m (Kiefer)" in p
    assert "$" not in p.split("## Output")[0]     # every placeholder substituted


# --- entry-level reading ----------------------------------------------------

def test_entry_place_from_model_replaces_header_heuristics():
    entry, obs, _ = _run({
        "entry_place": {"name": "Kaufbeuren", "verbatim": "München - Kaufbeuren 843 m (Kiefer)",
                        "kind": "route"},
        "entry_kind": "field-day",
        "observations": [_item()],
    })
    assert entry.place is not None
    assert entry.place.name == "Kaufbeuren" and entry.place.kind == "route"
    assert entry.place.verbatim == "München - Kaufbeuren 843 m (Kiefer)"
    assert entry.place.lat is not None                 # gazetteer only adds coordinates
    assert entry.entry_kind == "field-day"
    assert obs[0].place is entry.place                 # inherits the entry place
    assert obs[0].locality is None


def test_entry_place_null_means_no_place_and_legacy_response_uses_fallback():
    fallback = Place(verbatim="München", canonical="München")
    entry, obs, _ = _run({"entry_place": None, "observations": [_item()]}, fallback_place=fallback)
    assert entry.place is None and obs[0].place is None
    # kind unknown == no usable place
    entry, _, _ = _run({"entry_place": {"name": "Rauchschwalben", "kind": "unknown"},
                        "observations": []}, fallback_place=fallback)
    assert entry.place is None
    # legacy response without the key keeps the caller's fallback
    entry, obs, _ = _run({"observations": [_item()]}, fallback_place=fallback)
    assert entry.place is fallback and obs[0].place is fallback


def test_map_entry_place_tolerates_bare_string_and_garbage():
    assert map_entry_place("Ismaning", None).name == "Ismaning"
    assert map_entry_place({"name": ""}, "x") is None
    assert map_entry_place(42, "x") is None
    p = map_entry_place({"name": "Ismaning", "kind": "Dorf"}, "Ismaning (Kiefer)")
    assert p.kind == "settlement"                       # non-vocab kind -> default, never guessed
    assert p.verbatim == "Ismaning (Kiefer)"


def test_entry_date_model_reading_wins_with_audit_trail():
    entry, _, _ = _run({
        "entry_date": {"iso": "1949-03-19", "note": "85.) ist die laufende Artnummer"},
        "observations": [],
    }, entry=_entry(date="1985-03-19", date_raw="19.III. 85.)"))
    assert entry.entry_date == "1949-03-19"
    assert entry.header_date == "1985-03-19"
    assert "Artnummer" in entry.date_note
    # a silent correction gets an automatic note
    entry, _, _ = _run({"entry_date": {"iso": "1949-03-20"}, "observations": []})
    assert entry.entry_date == "1949-03-20" and "1949-03-19" in entry.date_note
    # invalid model dates never replace the header date
    entry, _, _ = _run({"entry_date": {"iso": "1949-13-40"}, "observations": []})
    assert entry.entry_date == "1949-03-19" and entry.date_note is None


def test_entry_date_end_and_plausibility():
    d = map_entry_date({"iso": "1949-06-11", "end_iso": "1949-06-13", "plausible": "false"},
                       "1949-06-11")
    assert d == {"iso": "1949-06-11", "end_iso": "1949-06-13", "plausible": False, "note": None}
    assert map_entry_date({"iso": "1949-06-13", "end_iso": "1949-06-11"}, "1949-06-13")["end_iso"] is None
    assert map_entry_date("1949-06-11", None)["iso"] == "1949-06-11"
    assert map_entry_date(None, "1949-06-11")["iso"] == "1949-06-11"


# --- per-observation detail -------------------------------------------------

def test_locality_overrides_entry_place_for_that_record_only():
    entry, obs, _ = _run({
        "entry_place": {"name": "München", "kind": "settlement"},
        "observations": [
            _item(vernacular_de="Kiebitz", locality={"name": "Ismaning", "verbatim": "bei Ismaning"}),
            _item(vernacular_de="Amsel"),
        ],
    })
    assert obs[0].place.name == "Ismaning" and obs[0].locality.verbatim == "bei Ismaning"
    assert obs[0].locality.kind == "locality"
    assert obs[1].place.name == "München" and obs[1].locality is None


def test_absence_range_and_zero_handling():
    _, obs, _ = _run({"observations": [
        _item(vernacular_de="Rauchschwalbe", occurrence_status="absent", individual_count=0),
        _item(vernacular_de="Star", individual_count=0),                       # 0 without absence
        _item(vernacular_de="Kiebitz", count_min=40, count_max=50, count_qualifier="approximate"),
        _item(vernacular_de="Möwe", count_min=5, count_max=3),                  # swapped bounds
        _item(vernacular_de="Ente", individual_count="12"),
    ]})
    assert obs[0].occurrence_status == "absent" and obs[0].individual_count == 0
    assert obs[1].occurrence_status == "present" and obs[1].individual_count is None
    assert (obs[2].individual_count, obs[2].count_min, obs[2].count_max) == (40, 40, 50)
    assert (obs[3].count_min, obs[3].count_max) == (3, 5)
    assert obs[4].individual_count == 12


def test_enum_fields_membership_only_never_guessed():
    _, obs, _ = _run({"observations": [
        _item(sex="male", life_stage="juvenile", breeding_evidence="confirmed", vitality="dead",
              movement_kind="passing-over", flight_direction="NO→SW",
              identification_qualifier="wohl", event_date="1949-03-05", event_time="7.30",
              taxon_rank="genus", scientific_name="Limosa"),
        _item(sex="Männchen", life_stage="ad.", breeding_evidence="yes", vitality="lebend",
              movement_kind="ziehend", event_date="5.3.49", event_time="früh",
              taxon_rank="Gattung", is_bird="ja"),
    ]})
    a, b = obs
    assert (a.sex, a.life_stage, a.breeding_evidence, a.vitality, a.movement_kind) == \
        ("male", "juvenile", "confirmed", "dead", "passing-over")
    assert a.flight_direction == "NO→SW" and a.identification_qualifier == "wohl"
    assert a.event_date == "1949-03-05" and a.event_time == "07:30"
    assert a.taxon.rank == "genus" and a.taxon.scientific_name == "Limosa"
    # German/prose values are NOT folded onto the vocabulary by guessing
    assert (b.sex, b.life_stage, b.breeding_evidence, b.vitality, b.movement_kind) == \
        (None, None, None, None, None)
    assert b.event_date is None and b.event_time is None
    assert b.taxon.rank == "unknown"                    # said something, but not a rank we know
    assert b.taxon.is_bird is True                      # "ja" is an unambiguous boolean


def test_nothing_fabricated_no_evidence_no_transcription_no_behaviour_injection():
    _, obs, _ = _run({"observations": [
        _item(vernacular_de="Amsel"),                                        # no evidence key
        _item(vernacular_de="Star", evidence=[{"kind": "unknown"}]),
        _item(vernacular_de="Fink", evidence=[{"kind": "auditory"}]),
        _item(vernacular_de="Meise", evidence=[{"kind": "nest"}]),
    ]})
    assert obs[0].evidence == [] and obs[1].evidence == []
    call = obs[2].evidence[0]
    assert call.is_call and call.call_type == "unknown" and call.call_transcription is None
    assert obs[3].behaviour == []                       # no "Brüten" injected from a nest
    assert obs[3].breeding_evidence is None


def test_resolver_iri_only_for_the_resolvers_own_name():
    _, obs, _ = _run({"observations": [
        _item(vernacular_de="Buchfink"),                                     # resolver name
        _item(vernacular_de="Buchfink", scientific_name="Fringilla coelebs"),
        _item(vernacular_de="Buchfink", scientific_name="Fringilla montifringilla"),
    ]})
    assert obs[0].taxon.scientific_name == "Fringilla coelebs"
    assert obs[1].taxon.taxon_iri == obs[0].taxon.taxon_iri
    assert obs[2].taxon.taxon_iri is None               # a different binomial: no borrowed IRI


def test_observer_exact_name_link_and_diarist_aliases():
    entry, obs, _ = _run({
        "persons": [{"name": "Förster Kiel", "role": "source"}, {"name": "Frau Laubmann"}],
        "observations": [
            _item(observer="Förster Kiel"),
            _item(observer="Frau Laubmann"),
            _item(observer="Lbm."),
            _item(observer="ich"),
        ],
    })
    assert obs[0].observer is entry.persons[0]
    assert obs[1].observer is not None and obs[1].observer.name == "Frau Laubmann"
    assert obs[2].observer is None and obs[3].observer is None
