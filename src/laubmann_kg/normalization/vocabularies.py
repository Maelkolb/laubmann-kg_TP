"""Controlled vocabularies mirroring the SHACL sh:in constraints."""

from __future__ import annotations

TRANSPORT_MODES = ("train", "foot", "boat", "car", "carriage", "bicycle", "unknown")
CALL_TYPES = ("song", "call", "alarm", "drumming", "unknown")
COUNT_QUALIFIERS = ("exact", "minimum", "approximate", "plural-unspecified")
EVIDENCE_KINDS = ("visual", "auditory", "nest", "specimen")

# Diary phrasing → evidence kind. Order matters: nest/specimen beat generic sound.
AUDITORY_CUES = (
    "ruft", "rufen", "ruf ", "gesang", "singt", "singen", "sang", "schlägt",
    "schlagen", "schrei", "schreien", "schwirrt", "schnarren", "trommelt",
    "trommeln", "gehört", "hört", "locken", "lockt", "pfeift", "pfiff",
)
NEST_CUES = ("nest", "brut", "gelege", "eier", "horst", "junge")
SPECIMEN_CUES = ("erlegt", "geschossen", "gesammelt", "eingesandt", "präpar", "balg", "sammlung")

SONG_CUES = ("gesang", "singt", "singen", "sang", "schlägt", "schlagen", "schwirrt")
DRUMMING_CUES = ("trommelt", "trommeln")

# Approximate / plural quantity cues (no exact integer available).
PLURAL_CUES = (
    "einige", "mehrere", "viele", "zahlreiche", "etliche", "manche",
    "einzelne", "verschiedene", "diverse", "wenige", "einigen", "vielen",
)
APPROX_CUES = ("etwa", "ungefähr", "ca.", "circa", "gegen", "an die", "rund")

GERMAN_NUMBER_WORDS = {
    "ein": 1, "eine": 1, "einen": 1, "einem": 1, "einer": 1, "eines": 1,
    "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7,
    "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "ein paar": 2,
    "zwanzig": 20, "dreißig": 30, "hundert": 100,
}


def is_valid(term: str, vocabulary: tuple[str, ...]) -> bool:
    return term in vocabulary
