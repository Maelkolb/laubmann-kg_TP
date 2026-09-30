"""Visual reading (extraction/reading.py): the transcription of an entry is
checked against its page scans and corrected before extraction."""

import json

from laubmann_kg.extraction.reading import MAX_INSERT_CHARS, apply_reading, read_entry
from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.llm.prompts import PromptLibrary


def _entry(text="16. August 1930. Pöcking. Vormittags beim Badeplatz in Garatshausen ein größerer Flug Staren."):
    return DiaryEntry("e1", "L08-e0001", 8, "p", "page_A", "r", None, "1930-08-16", "16. August 1930",
                      "Pöcking", text)


def test_corrections_are_applied_and_the_transcription_is_kept():
    e = _entry()
    apply_reading(e, {"quality": "minor", "corrections": [
        {"old": "Garatshausen", "new": "Possenhofen"},
        {"old": "Flug  Staren", "new": "Flug Fichtenkreuzschnäbel"},      # whitespace-tolerant
        {"old": "Amsel", "new": "Drossel"},                                # not in the text
    ]})
    assert "Possenhofen ein größerer Flug Fichtenkreuzschnäbel" in e.text_clean
    assert e.text_transcribed.endswith("Flug Staren.")
    assert e.transcript_quality == "minor"
    assert [c[2] for c in e.transcript_corrections] == [True, True, False]


def test_long_insertions_are_listed_but_not_applied():
    """A long insertion is most likely the next entry's text on the same page."""
    e = _entry()
    before = e.text_clean
    apply_reading(e, {"quality": "poor", "corrections": [
        {"old": "Staren.", "new": "Staren. " + "x" * (MAX_INSERT_CHARS + 1)}]})
    assert e.text_clean == before and e.text_transcribed is None
    assert e.transcript_corrections[0][2] is False


def test_good_quality_without_corrections_changes_nothing():
    e = _entry()
    apply_reading(e, {"quality": "good"})
    assert e.transcript_quality == "good" and e.text_transcribed is None and e.transcript_corrections == []


def test_read_entry_sends_the_page_scans_and_the_neighbours():
    seen = {}

    class Fake:
        model = "m"

        def complete(self, prompt, images=None):
            seen["prompt"], seen["images"] = prompt, images
            return json.dumps({"quality": "minor", "corrections": [{"old": "Garatshausen", "new": "Possenhofen"}]})

    e = _entry()
    e.neighbour_before, e.neighbour_after = "…Ende des Vortags.", "17. August 1930. Pöcking."
    ok = read_entry(e, Fake(), PromptLibrary(), lambda entry: [("page_A", b"jpeg")])
    assert ok and "Possenhofen" in e.text_clean
    assert seen["images"] == [("page_A", b"jpeg")]
    assert "next_entry_begins: 17. August 1930. Pöcking." in seen["prompt"]
    assert "previous_entry_ends: ……Ende des Vortags." in seen["prompt"]


def test_entries_without_scans_are_left_as_transcribed():
    class Fail:
        model = "m"

        def complete(self, prompt, images=None):
            raise AssertionError("no call without scans")

    e = _entry()
    assert read_entry(e, Fail(), PromptLibrary(), lambda entry: []) is False
    assert e.transcript_quality is None
