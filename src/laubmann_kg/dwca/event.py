"""Build Darwin Core Event core rows (one per dated diary entry)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

from laubmann_kg.kg.model import GEOREF_SOURCES, data_iri
from laubmann_kg.normalization.dates import event_date  # noqa: F401  (re-exported for the writers)

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
    source = getattr(place, "georef_source", None) if has else None
    return {
        "coordinateUncertaintyInMeters": str(place.coordinate_uncertainty_m) if has and getattr(place, "coordinate_uncertainty_m", None) else "",
        "georeferenceSources": GEOREF_SOURCES.get(source, source or "") if source else "",
        "georeferenceProtocol": GEOREF_PROTOCOL if source else "",
        "locationID": f"https://sws.geonames.org/{place.geonames_id}/" if place is not None and getattr(place, "geonames_id", None) else "",
    }


def coordinates_safe(entry) -> bool:
    """May the event row carry the entry place's point? GBIF fills an empty
    occurrence field from its event, so a record at ANOTHER place without
    coordinates would silently take the entry's point. The occurrence rows
    carry their own place's georeference; the event keeps the point only when
    no record of the entry could inherit it wrongly."""
    place = entry.place
    for obs in entry.observations:
        other = obs.place
        if other is None or (place is not None and other.uid == place.uid):
            continue
        if other.lat is None or other.long is None:
            return False
    return True


def build_events(result: "ExtractionResult") -> list[dict]:
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        place = entry.place            # the model's (or gazetteer's) reading of the header
        # the entry's georeference only when no record could inherit it wrongly
        safe = coordinates_safe(entry)
        has_coords = safe and place is not None and place.lat is not None and place.long is not None
        geo = georef_columns(place if safe else None)
        rows.append({
            "eventID": data_iri(entry.uid),
            "eventDate": event_date(entry),
            "verbatimEventDate": entry.verbatim_event_date or "",
            "locality": place.name if place is not None else "",
            "decimalLatitude": _fmt(place.lat) if has_coords else "",
            "decimalLongitude": _fmt(place.long) if has_coords else "",
            "samplingProtocol": "diary observation",
            "fieldNumber": entry.entry_id,
            "fieldNotes": (entry.text_clean or "").replace("\n", " ").replace("\t", " "),
            "verbatimLocality": (entry.location_raw or "").replace("\t", " ").replace("\n", " "),
            "geodeticDatum": "WGS84" if has_coords else "",
            **geo,
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
