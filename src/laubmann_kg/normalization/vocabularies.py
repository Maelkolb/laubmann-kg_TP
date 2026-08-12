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

# Diary phrasing → transport mode, for when the LLM answers in German instead of
# the vocabulary term. Order matters: "kraftwagen" must hit car before "wagen"
# hits carriage.
TRANSPORT_MODE_CUES = (
    ("train", ("bahn", "zug", "eisenbahn", "d-zug", "lokal", "express")),
    ("boat", ("dampfer", "boot", "schiff", "kahn", "fähre", "floß")),
    ("bicycle", ("fahrrad", "rad", "velo")),
    ("car", ("auto", "kraftwagen", "automobil")),
    ("carriage", ("kutsche", "droschke", "fuhrwerk", "chaise", "wagen")),
    ("foot", ("fuß", "fuss", "gegangen", "gelaufen", "marsch", "wander", "spazier")),
)


def normalize_transport_mode(raw: object) -> str:
    """Map an LLM-supplied transport mode onto the SHACL vocabulary."""
    if not raw:
        return "unknown"
    value = str(raw).strip().lower()
    if value in TRANSPORT_MODES:
        return value
    for mode, cues in TRANSPORT_MODE_CUES:
        if any(cue in value for cue in cues):
            return mode
    return "unknown"

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
