"""Build Darwin Core Event core rows (one per dated diary entry)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

# Column contract: eventID first; the legacy prefix (indices 0-8) and the two
# weather columns at the very end are pinned by tests outside this package, so
# new columns go between fieldNotes and eventRemarks.
FIELDS = [
    "eventID", "eventDate", "verbatimEventDate", "locality",
    "decimalLatitude", "decimalLongitude", "samplingProtocol", "fieldNumber",
    "fieldNotes", "verbatimLocality", "geodeticDatum",
    "coordinateUncertaintyInMeters", "georeferenceSources", "georeferenceProtocol", "locationID",
    "eventRemarks", "dynamicProperties",
]

GEOREF_PROTOCOL = "gazetteer match on the diary's place name (GeoNames / OpenStreetMap); coordinates = feature centroid"


def georef_columns(place) -> dict:
    """The georeference columns of a place (empty strings when unknown)."""
    has = place is not None and place.lat is not None and place.long is not None
    return {
        "coordinateUncertaintyInMeters": str(place.coordinate_uncertainty_m) if has and getattr(place, "coordinate_uncertainty_m", None) else "",
        "georeferenceSources": _GEOREF_SOURCES.get(getattr(place, "georef_source", None), getattr(place, "georef_source", None) or "") if has else "",
        "georeferenceProtocol": GEOREF_PROTOCOL if has and getattr(place, "georef_source", None) else "",
        "locationID": f"https://sws.geonames.org/{place.geonames_id}/" if place is not None and getattr(place, "geonames_id", None) else "",
    }


_GEOREF_SOURCES = {
    "gazetteer": "built-in gazetteer (normalization/places.py)",
    "osm+geonames": "OpenStreetMap/Nominatim name match confirmed by GeoNames",
    "osm": "OpenStreetMap/Nominatim name match",
    "geonames": "GeoNames name match (unique in home region)",
    "reviewed": "reviewed place_link_review.csv",
}


def event_date(entry) -> str:
    """ISO date, or the ISO interval ``start/end`` for multi-day entries."""
    start = entry.entry_date or ""
    end = getattr(entry, "entry_date_end", None)
    if start and end and end != start:
        return f"{start}/{end}"
    return start


def build_events(result: "ExtractionResult") -> list[dict]:
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        place = entry.place            # the model's (or gazetteer's) reading of the header
        has_coords = place is not None and place.lat is not None and place.long is not None
        rows.append({
            "eventID": entry.entry_uid,
            "eventDate": event_date(entry),
            "verbatimEventDate": entry.verbatim_event_date or "",
            "locality": place.name if place is not None else "",
            "decimalLatitude": _fmt(place.lat) if has_coords else "",
            "decimalLongitude": _fmt(place.long) if has_coords else "",
            "samplingProtocol": "diary observation",
            "fieldNumber": entry.entry_id,
            "fieldNotes": (entry.text_clean or "").replace("\n", " ").replace("\t", " "),
            "verbatimLocality": entry.location_raw or "",
            "geodeticDatum": "WGS84" if has_coords else "",
            **georef_columns(place),
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
    return dumps_properties(props)


def dumps_properties(props: dict) -> str:
    """JSON for a dynamicProperties cell: drop empty values, no tabs/newlines
    (meta.xml declares fieldsEnclosedBy="")."""
    props = {k: v for k, v in props.items() if v not in (None, "")}
    if not props:
        return ""
    return json.dumps(props, ensure_ascii=False).replace("\t", " ").replace("\n", " ")


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.4f}"
