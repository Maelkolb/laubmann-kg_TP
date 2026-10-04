"""The machine layer of the text: the checks' better readings placed on the correction's span, how
each change reaches the graph (patched after the extraction or read anew), and the patch itself."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from laubmann_kg.extraction.reading import apply_reading, load_transcript_decisions
from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.review.better_readings import (classify, commentary, doubled_edges, doubled_in_reading, overrun_in_reading, layer_parts, machine_decision, machine_readings,
                                                patch, place, reviewed_entries)
from laubmann_kg.review.readings import Reading

DECISION_FIELDS = ["entry_uid", "entry_id", "old_text", "new_text", "decision", "final_text", "note", "reviewed_by", "reviewed_at"]
TAXA = {"kranich": ("Kranich", "Grus grus", "2474953"), "turmfalke": ("Turmfalke", "Falco tinnunculus", "2481139"),
        "weidenlaubvogel": ("Weidenlaubvogel", "Phylloscopus collybita", "2493052")}
PLACES = {"kaufbeuren": "Kaufbeuren", "pöcking": "Pöcking"}


def _entry(text: str) -> DiaryEntry:
    return DiaryEntry("e1", "L08-e0001", 8, "p", "page_A", "r", None, "1930-08-16", "16. August 1930", "Pöcking", text)


def _write(path: Path, fields, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def _classify(now, final, header=False, records=(), here=(), entry_place="München", location_raw="München"):
    return classify(now, final, header=header, records=list(records), places_here=set(here), taxa=TAXA, places=PLACES,
                    entry_place=entry_place, location_raw=location_raw)


# ---------------------------------------------------------------- placing a better reading

def test_the_quoted_context_is_cut_to_the_span():
    text = "Nachmittags auf der Halbinsel. Über denselben von von Hirschzell ein alter Turmfalke."
    pos = text.index("denselben von")
    assert place("denselben", "denselben von", True, pos, "Über den Feldern von Hirschzell", text) == "den Feldern"


def test_a_header_reading_is_the_whole_span():
    text = "1. Juni 1917. Rauschen. Im Garten sind heuer Rabenkrähen."
    assert place("1. Juni 1917. Rabenkrähen.", "1. Juni 1917. Rauschen.", True, 0, "1. Juni 1917. Kaufbeuren.", text) == "1. Juni 1917. Kaufbeuren."


def test_a_reading_of_other_words_is_left_to_the_reviewer():
    text = "das Liedchen des Fitislaubsängers sowie den einfachen Silberblick des Weidenlaubsängers."
    pos = text.index("Silberblick")
    assert place("Zilpzalp", "Silberblick", True, pos, "sowie den einfachen Zilpzalp des Weidenlaubvogels", text) is None
    assert place("Zilpzalp", "Silberblick", True, pos, "sowie den einfachen Zilpzalp des Weidenlaubvogels", text, loose=True) == "Zilpzalp des Weidenlaubvogels"


def test_a_reading_with_the_checks_doubt_is_left_to_the_reviewer():
    text = "Ein Trupp Mauersegler über dem Haus."
    assert place("Trupp Mauersegel", "Trupp Mauersegler", True, text.index("Trupp"), "Trupp [?]", text) is None
    assert commentary("Bitringen", "vermutlich Bidingen") and commentary("Heidelerche", "Heidemeisen (?)")
    assert not commentary("Ermatingen (?)", "Ermatingen (?)") and not commentary("Söcking", "Pöcking")


def test_header_fields_keep_their_field_and_decide_nothing():
    assert place("location_header: Rabenkrähen", "location_header: Rauschen.", False, -1, "Kaufbeuren.", "") == "location_header: Kaufbeuren."
    assert machine_decision("location_header: Rabenkrähen", "location_header: Rauschen.", False, "location_header: Kaufbeuren.") is None


def test_machine_decisions():
    assert machine_decision("a", "b", True, "c") == ("edit", "c")
    assert machine_decision("a", "b", True, "a") == ("reject", "a")
    assert machine_decision("a", "b", True, "b") is None
    assert machine_decision("a", "b", False, "b") == ("accept", "b")
    assert machine_decision("a", "b", True, None) is None


# ---------------------------------------------------------------- after the extraction, or read anew

def test_words_no_record_depends_on_are_patched():
    assert _classify("Bauch das Gelege", "Bau des Geleges") == ("after", [])


def test_a_bird_name_of_one_record_becomes_a_species_correction():
    mode, vals = _classify("1 Kamin", "1 Kranich", records=[{"written": "Kamin", "taxon": "Aves"}, {"written": "Storch", "taxon": "Storch"}])
    assert mode == "after" and vals == [{"kind": "taxon", "old_value": "Kamin", "new_value": "Kranich", "scientific_name": "Grus grus", "gbif_key": "2474953"}]


def test_a_plural_resolves_and_the_same_bird_needs_only_the_text():
    mode, vals = _classify("Weidenlaubsänger;", "Weidenlaubvögel;", records=[{"written": "Weidenlaubsänger", "taxon": "Weidenlaubvogel"}])
    assert (mode, vals) == ("after", [])


def test_a_bird_without_a_single_record_is_read_anew():
    two = [{"written": "Baumfalke", "taxon": "Baumfalke"}, {"written": "Baumfalke", "taxon": "Baumfalke"}]
    assert _classify("ein Baumfalke", "ein Turmfalke", records=two)[0] == "before"
    assert _classify("ein Baumfalke", "ein Turmfalke", records=[])[0] == "before"


def test_places_the_entry_uses_move_to_known_places():
    assert _classify("in Söcking,", "in Pöcking,", here={"söcking"}) == ("after", [{"kind": "place", "old_value": "Söcking", "new_value": "Pöcking"}])
    mode, vals = _classify("1. Juni 1917. Rauschen.", "1. Juni 1917. Kaufbeuren.", header=True, location_raw="Rabenkrähen")
    assert mode == "after" and vals == [{"kind": "place", "old_value": "München", "new_value": "Kaufbeuren", "header": "Kaufbeuren"}]
    assert _classify("bei Anhalting", "bei Ankering", here={"anhalting"})[0] == "before"     # no known place: the model decides


def test_numbers_and_dates_are_read_anew():
    assert _classify("i3 Exemplare", "13 Exemplare")[0] == "before"
    assert _classify("um 7º", "um 7 h") == ("after", [])
    assert _classify("8. Juni 1917.", "8. Juli 1917.")[0] == "before"
    assert _classify("10. X. 1932", "10. XI. 1932")[0] == "before"


def test_a_reviewed_entry_takes_the_whole_layer_before_the_extraction():
    rows = [{"entry_uid": "e1", "entry_id": "L08-e0001", "source": "check", "old_text": "a", "new_text": "b", "decision": "edit", "final_text": "c",
             "text_now": "b", "apply": "after", "header_place": "", "note": ""},
            {"entry_uid": "e2", "entry_id": "L08-e0002", "source": "scan", "old_text": "x", "new_text": "y", "decision": "accept", "final_text": "y",
             "text_now": "x", "apply": "after", "header_place": "", "note": ""},
            {"entry_uid": "e3", "entry_id": "L08-e0003", "source": "check", "old_text": "p", "new_text": "q", "decision": "reject", "final_text": "p",
             "text_now": "q", "apply": "before", "header_place": "", "note": ""}]
    reviewed = reviewed_entries({("e2", "x", "y"): ("reject", "x")}, [Reading("u", "v", "e9")])
    decisions, readings, after, after_uids = layer_parts(rows, reviewed)
    assert reviewed == {"e2", "e9"}
    assert decisions == {("e3", "p", "q"): ("reject", "p")}
    assert [(r.old, r.new) for r in readings] == [("x", "y")]
    assert after_uids == {"e1"}


def test_the_patch_changes_text_header_and_passages():
    from laubmann_kg.kg.model import Observation, Taxon
    e = _entry("1. Juni 1917. Rauschen. Im Garten 1 Kamin und 8 Störche.")
    e.location_raw = "Rabenkrähen"
    o = Observation(entry_uid="e1", taxon=Taxon(vernacular_de="Kamin"), verbatim_notes="1 Kamin und 8 Störche.")
    e.observations = [o]
    rows = [{"entry_uid": "e1", "entry_id": "L08-e0001", "text_now": "1. Juni 1917. Rauschen.", "final_text": "1. Juni 1917. Kaufbeuren.", "header_place": "Kaufbeuren"},
            {"entry_uid": "e1", "entry_id": "L08-e0001", "text_now": "1 Kamin", "final_text": "1 Kranich", "header_place": ""},
            {"entry_uid": "e1", "entry_id": "L08-e0001", "text_now": "Wildgänse", "final_text": "Wildenten", "header_place": ""}]
    flags = patch([e], rows)
    assert e.text_clean == "1. Juni 1917. Kaufbeuren. Im Garten 1 Kranich und 8 Störche."
    assert e.location_raw == "Kaufbeuren" and o.verbatim_notes == "1 Kranich und 8 Störche."
    assert Counter(f.reason for f in flags) == {"reading_corrected": 2, "reading_unmatched": 1}


# ---------------------------------------------------------------- the reviewer wins

def test_the_reviewer_wins_over_the_machine_layer(tmp_path):
    machine = _write(tmp_path / "m.csv", DECISION_FIELDS, [
        {"entry_uid": "e1", "old_text": "Staaren", "new_text": "Scharen", "decision": "edit", "final_text": "Staren"},
        {"entry_uid": "e1", "old_text": "Garatshausen", "new_text": "Garatshofen", "decision": "reject", "final_text": "Garatshausen"}])
    human = _write(tmp_path / "h.csv", DECISION_FIELDS, [
        {"entry_uid": "e1", "old_text": "Staaren", "new_text": "Scharen", "decision": "accept", "final_text": "Scharen"}])
    decisions = load_transcript_decisions(machine)
    decisions.update(load_transcript_decisions(human))
    e = _entry("Vormittags beim Badeplatz in Garatshausen ein größerer Flug Staaren.")
    apply_reading(e, {"quality": "good", "corrections": [{"old": "Staaren", "new": "Scharen"}, {"old": "Garatshausen", "new": "Garatshofen"}]}, decisions)
    assert e.text_clean == "Vormittags beim Badeplatz in Garatshausen ein größerer Flug Scharen."


def test_scan_agent_corrections_after_the_reading(tmp_path):
    rows = [{"entry_uid": "e1", "entry_id": "L08-e0001", "old_text": "Taucherenten", "new_text": "Haubentaucher"},
            {"entry_uid": "e1", "entry_id": "L08-e0001", "old_text": "Stocktauben", "new_text": "Hohltauben"},
            {"entry_uid": "e1", "entry_id": "L08-e0001", "old_text": "Pöcking", "new_text": "Söcking"}]
    path = _write(tmp_path / "text_corrections_machine.csv", ["entry_uid", "entry_id", "old_text", "new_text", "note"], rows)
    human = _write(tmp_path / "h.csv", DECISION_FIELDS, [
        {"entry_uid": "e1", "old_text": "Stocktauben", "new_text": "Hohltauben", "decision": "reject", "final_text": "Stocktauben"},
        {"entry_uid": "e1", "old_text": "Pöcking", "new_text": "Söcking", "decision": "edit", "final_text": "Pöcking am See"}])
    e = _entry("Pöcking. Auf dem See 3 Taucherenten, im Wald Stocktauben.")
    flags = machine_readings([e], path, human)
    assert e.text_clean == "Pöcking am See. Auf dem See 3 Haubentaucher, im Wald Stocktauben."
    assert sorted(f.reason for f in flags) == ["reading_corrected", "reading_corrected"]


def test_the_patch_lands_at_its_position_not_the_first_occurrence():
    e = _entry("Früh eine Kohlmeise. Abends wieder eine Kohlmeise am Haus.")
    second = e.text_clean.rindex("Kohlmeise")
    rows = [{"entry_uid": "e1", "entry_id": "L08-e0001", "text_now": "Kohlmeise", "final_text": "Blaumeise", "pos": second, "header_place": ""}]
    patch([e], rows)
    assert e.text_clean == "Früh eine Kohlmeise. Abends wieder eine Blaumeise am Haus."


def test_a_change_that_doubles_a_word_at_its_edge_is_left_out() -> None:
    text = "Ganz in der Nähe ein Flug Schwanzmeisen. Ein Zaunkönig singt. Dort kuik ruft es."
    changes = [{"text_now": "Zaunkönig singt", "final_text": "Ein Zaunkönig singt", "pos": text.index("Zaunkönig")},
               {"text_now": "kuik", "final_text": "kuik kuik", "pos": text.index("kuik")}]
    assert doubled_edges(text, changes) == {0}
    text = "nur Bläßhühner, einen einzelnen ein ♂♀ trieb sich und im Schilf"
    changes = [{"text_now": "einen einzelnen", "final_text": "einen einzelnen Haubentaucher", "pos": -1},
               {"text_now": "ein ♂♀ trieb sich", "final_text": "Haubentaucher", "pos": -1}]
    assert doubled_edges(text, changes) == {0, 1}
    assert doubled_edges("sondern recht gut.", [{"text_now": "recht gut.", "final_text": "recht recht gut.", "pos": 8}]) == set()


def test_a_change_that_doubles_a_word_in_the_reading_stage_is_left_out() -> None:
    text = "Schergenweiher: nur Bläßhühner, einige einzelne Haubentaucher und im Schilf ein Teichrohrsänger."
    corrections = [("einige einzelne", "einen einzelnen"), ("Haubentaucher", "ein ♂♀ trieb sich")]
    changes = [{"old_text": "einige einzelne", "new_text": "einen einzelnen", "decision": "edit", "final_text": "einen einzelnen Haubentaucher"},
               {"old_text": "Haubentaucher", "new_text": "ein ♂♀ trieb sich", "decision": "edit", "final_text": "Ein Haubentaucher"}]
    assert doubled_in_reading(text, corrections, changes) == {0, 1}
    assert doubled_in_reading(text, corrections, changes[1:]) == set()


def test_a_change_a_later_correction_of_the_reading_lands_in_is_left_out() -> None:
    text = "eine Beobachtung von 2 Seidenschwanz Ringamseln (vergl. p. 32), sowie von Ringamseln am See."
    corrections = [("Seidenschwanz Ringamseln", "Ringdrosseln"), ("Ringamseln", "")]
    changes = [{"old_text": "Seidenschwanz Ringamseln", "new_text": "Ringdrosseln", "decision": "edit", "final_text": "Nordischen Ringamseln"}]
    assert overrun_in_reading(text, corrections, changes) == {0}
    changes[0]["final_text"] = "Nordischen Ringdrosseln"
    assert overrun_in_reading(text, corrections, changes) == set()
