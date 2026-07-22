"""Build Darwin Core Event core rows (one per dated diary entry)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "eventDate", "verbatimEventDate", "locality",
    "decimalLatitude", "decimalLongitude", "samplingProtocol", "fieldNumber",
    "fieldNotes",
]


def build_events(result: "ExtractionResult") -> list[dict]:
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        place = result.places.get(_place_uid(entry))
        rows.append({
            "eventID": entry.entry_uid,
            "eventDate": entry.entry_date,
            "verbatimEventDate": entry.verbatim_event_date or "",
            "locality": entry.location_raw or "",
            "decimalLatitude": _fmt(place.lat) if place else "",
            "decimalLongitude": _fmt(place.long) if place else "",
            "samplingProtocol": "diary observation",
            "fieldNumber": entry.entry_id,
            "fieldNotes": (entry.text_clean or "").replace("\n", " ").replace("\t", " "),
        })
    return rows


def _place_uid(entry) -> str:
    from laubmann_kg.normalization.places import normalize_place
    place = normalize_place(entry.location_raw)
    return place.uid if place else ""


def _fmt(value) -> str:
    return "" if value is None else f"{value:.4f}"
