"""Build Darwin Core Event core rows (one per dated diary entry)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "eventDate", "verbatimEventDate", "locality",
    "decimalLatitude", "decimalLongitude", "samplingProtocol", "fieldNumber",
    "fieldNotes", "eventRemarks", "dynamicProperties",
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
            "eventRemarks": " ".join(entry.weather.verbatim.split()) if entry.weather else "",
            "dynamicProperties": _dynamic_properties(entry),
        })
    return rows


def _dynamic_properties(entry) -> str:
    w = entry.weather
    if w is None:
        return ""
    props = {"temperatureValue": w.temperature_value, "temperatureUnit": w.temperature_unit,
             "precipitation": w.precipitation, "wind": w.wind, "skyCondition": w.sky}
    props = {k: v for k, v in props.items() if v not in (None, "")}
    if not props:
        return ""
    return json.dumps(props, ensure_ascii=False).replace("\t", " ").replace("\n", " ")


def _place_uid(entry) -> str:
    from laubmann_kg.normalization.places import normalize_place
    place = normalize_place(entry.location_raw)
    return place.uid if place else ""


def _fmt(value) -> str:
    return "" if value is None else f"{value:.4f}"
