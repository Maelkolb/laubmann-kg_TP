from laubmann_kg.extraction.observations import extract_observations
from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import SeedTaxonResolver


def _entry(text: str, location: str = "München") -> DiaryEntry:
    return DiaryEntry(
        entry_uid="e_x", entry_id="L02-e0001", volume=2, page_uid="p_x",
        page_id="pid", region_uid="r_x", scan="4", entry_date="1918-04-07",
        verbatim_event_date="7. April 1918", location_raw=location, text_clean=text,
    )


def test_extracts_count_and_visual_evidence() -> None:
    entry = _entry("Am Ufer 3 Wildenten.")
    obs = extract_observations(entry, SeedTaxonResolver(), normalize_place("München"))
    assert len(obs) == 1
    assert obs[0].taxon.vernacular_de == "Wildente"
    assert obs[0].individual_count == 3
    assert obs[0].count_qualifier == "exact"
    assert obs[0].evidence[0].kind == "visual"


def test_detects_auditory_evidence_as_birdcall() -> None:
    entry = _entry("Ein Buchfink singt vom Baumwipfel.")
    obs = extract_observations(entry, SeedTaxonResolver(), None)
    kinds = {e.kind for e in obs[0].evidence}
    assert "auditory" in kinds
    call = next(e for e in obs[0].evidence if e.is_call)
    assert call.call_type == "song"


def test_detects_nest_behaviour() -> None:
    entry = _entry("Ein Storch hat sein besetztes Nest auf dem Kirchturm.")
    obs = extract_observations(entry, SeedTaxonResolver(), None)
    assert any(b.reproductive_condition == "breeding" for b in obs[0].behaviour)


def test_plural_cue_sets_qualifier() -> None:
    entry = _entry("einige Lachmöwen zu sehen")
    obs = extract_observations(entry, SeedTaxonResolver(), None)
    assert obs[0].count_qualifier == "plural-unspecified"
    assert obs[0].individual_count is None


def test_entry_without_bird_yields_no_observation() -> None:
    entry = _entry("Wetter trüb und kalt.")
    assert extract_observations(entry, SeedTaxonResolver(), None) == []
