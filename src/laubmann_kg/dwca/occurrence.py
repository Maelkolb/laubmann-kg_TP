"""Build Darwin Core Occurrence extension rows (one per observation).

Every row carries the georeference of the record's EFFECTIVE place (its own
locality, else the entry place) itself. GBIF fills an empty occurrence field
from the event row, so a record at its own locality must never be left to
inherit the entry's point (the event writer drops its coordinates whenever a
record of the entry sits at another, un-georeferenced place).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from laubmann_kg.dwca.event import dumps_properties, event_date, georef_columns
from laubmann_kg.kg.model import data_iri
from laubmann_kg.normalization.dates import obs_event_date
from laubmann_kg.normalization.vocabularies import basis_of_record, reproductive_condition

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "occurrenceID", "basisOfRecord",
    "kingdom", "class", "order", "family", "scientificName", "taxonRank", "vernacularName", "taxonID",
    "individualCount", "occurrenceStatus", "sex", "lifeStage", "reproductiveCondition", "vitality",
    "behavior", "identificationQualifier", "identificationRemarks", "verbatimIdentification",
    "locality", "verbatimLocality", "locationID", "decimalLatitude", "decimalLongitude", "geodeticDatum",
    "coordinateUncertaintyInMeters", "georeferenceSources", "georeferenceProtocol",
    "minimumElevationInMeters", "maximumElevationInMeters",
    "eventDate", "eventTime", "habitat",
    "occurrenceRemarks", "recordedBy", "associatedReferences",
    "dynamicProperties",
]

DEFAULT_RECORDED_BY = "Alfred Laubmann"

# ranks GBIF interprets; the project's informal "group" (Limikolen, Greifvögel)
# has no Darwin Core rank and stays blank (identificationRemarks says why)
_DWC_RANKS = ("species", "subspecies", "genus", "family")
# taxon.rank values that mean "the diarist named a group, not a species"
_SUPRASPECIFIC_RANKS = ("genus", "family", "group")
# dwc:sex has no value for a mixed group; GBIF reads the pipe-separated list
_SEX = {"mixed": "male | female"}


def _basis_of_record(obs) -> str:
    return basis_of_record(obs.record_type, (e.kind for e in obs.evidence), bool(obs.literature_citation))


def _recorded_by(obs) -> str:
    """Same rule as dwciri:recordedBy in the graph (Observation.recorders): the
    diarist and his companions, or the third-party observer; an unattributed
    report or citation claims nobody."""
    return " | ".join(p.name for p in obs.recorders)


def _scientific_name(taxon) -> tuple[str, str]:
    """(scientificName, taxonRank). A bird the diarist named without a
    resolvable species is published as identified to class Aves (GBIF files a
    blank scientificName as incertae sedis); the written name stays in
    vernacularName."""
    if taxon.scientific_name:
        return taxon.scientific_name, taxon.rank if taxon.rank in _DWC_RANKS else ""
    if taxon.is_bird is True:
        return "Aves", "class"
    return "", ""


def _identification_remarks(taxon) -> str:
    if taxon.rank in _SUPRASPECIFIC_RANKS:
        return f"Bestimmung auf {taxon.rank}-Niveau"
    if taxon.scientific_name:
        return ""
    return "Art nicht sicher bestimmt; nur Trivialname"


def _reproductive_condition(obs) -> str:
    return reproductive_condition(obs.breeding_evidence, obs.behaviour) or ""


def _higher(taxon, rank: str) -> str:
    """GBIF classification of the linked taxon (kingdom/class/order/family)."""
    getter = getattr(taxon, "higher_rank", None)
    return (getter(rank) if getter else None) or ""


def _kingdom(taxon) -> str:
    # GBIF value when linked; the model's is_bird judgement as fallback
    return _higher(taxon, "kingdom") or ("Animalia" if taxon.is_bird is True else "")


def _class(taxon) -> str:
    return _higher(taxon, "class") or ("Aves" if taxon.is_bird is True else "")


def _coordinate_uncertainty(obs) -> str:
    """Radius of the circle the record lies in: the centroid radius of its
    place (GeoNames/OSM feature). Blank when the place has no coordinates or
    no known radius."""
    place = obs.place
    if place is None or place.lat is None or not getattr(place, "coordinate_uncertainty_m", None):
        return ""
    return str(int(place.coordinate_uncertainty_m))


def _elevation(obs) -> str:
    """The record's own stated elevation, else its place's (a header "843 m")."""
    value = obs.altitude_m
    if value is None and obs.place is not None:
        value = getattr(obs.place, "elevation_m", None)
    return "" if value is None else f"{value:g}"


def _occurrence_remarks(obs) -> str:
    """The diary passage of the record, plus a reviewer's correction note."""
    parts = [obs.verbatim_notes or "", obs.occurrence_remarks or ""]
    return " — ".join(" ".join(p.split()) for p in parts if p)


def _dynamic_properties(obs) -> str:
    """Free-text and numeric details without a Darwin Core term (the
    controlled values are eMoF rows with concept IRIs)."""
    transcriptions = [e.call_transcription for e in obs.evidence if e.call_transcription]
    return dumps_properties({
        "countMin": obs.count_min,
        "countMax": obs.count_max,
        "flightDirection": obs.flight_direction,
        "callTranscription": " | ".join(transcriptions) or None,
        "spatialContext": obs.spatial_context,
        "microhabitat": obs.microhabitat,
        "relativeElevation": obs.relative_elevation,
    })


_CALL_LABELS_DE = {"song": "Gesang", "call": "Ruf", "alarm": "Warnruf", "drumming": "Trommeln"}


def _behavior(obs) -> str:
    """dwc:behavior of the flat archive: the call types heard (German labels of
    lkg:callTypeScheme, since 0.6.0 no longer repeated as behaviour phrases in
    the graph) followed by the other behaviours as written."""
    calls = []
    for evidence in obs.evidence:
        label = _CALL_LABELS_DE.get(evidence.call_type or "") if evidence.is_call else None
        if label and label not in calls:
            calls.append(label)
    return "; ".join(calls + [b.label for b in obs.behaviour])


def _taxon_id(taxon) -> str:
    if taxon.gbif_key and taxon.gbif_match_type != "HIGHERRANK":
        return f"https://www.gbif.org/species/{taxon.gbif_key}"
    return ""


def _clean(text: str) -> str:
    return (text or "").replace("\t", " ").replace("\n", " ")


def build_occurrences(result: "ExtractionResult") -> list[dict]:
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        entry_date = event_date(entry)
        for obs in entry.observations:
            taxon = obs.taxon
            place = obs.place
            has_coords = place is not None and place.lat is not None and place.long is not None
            scientific, rank = _scientific_name(taxon)
            elevation = _elevation(obs)
            geo = georef_columns(place)
            rows.append({
                "eventID": data_iri(entry.uid),
                "occurrenceID": data_iri(obs.uid),
                "basisOfRecord": _basis_of_record(obs),
                "kingdom": _kingdom(taxon),
                "class": _class(taxon),
                "order": _higher(taxon, "order"),
                "family": _higher(taxon, "family"),
                "scientificName": scientific,
                "taxonRank": rank,
                "vernacularName": taxon.vernacular_de,
                "taxonID": _taxon_id(taxon),
                # 0 is a real value (absence record), so test against None
                "individualCount": ("" if obs.individual_count is None
                                    else str(obs.individual_count)),
                "occurrenceStatus": obs.occurrence_status or "present",
                "sex": _SEX.get(obs.sex or "", obs.sex or ""),
                "lifeStage": obs.life_stage or "",
                "reproductiveCondition": _reproductive_condition(obs),
                "vitality": obs.vitality or "",
                "behavior": _behavior(obs),
                "identificationQualifier": obs.identification_qualifier or "",
                "identificationRemarks": _identification_remarks(taxon),
                "verbatimIdentification": obs.taxon_verbatim or "",
                "locality": place.name if place is not None else "",
                "verbatimLocality": _clean(obs.locality.verbatim) if obs.locality is not None else "",
                "locationID": geo["locationID"],
                "decimalLatitude": f"{place.lat:.4f}" if has_coords else "",
                "decimalLongitude": f"{place.long:.4f}" if has_coords else "",
                "geodeticDatum": "WGS84" if has_coords else "",
                "coordinateUncertaintyInMeters": _coordinate_uncertainty(obs),
                "georeferenceSources": geo["georeferenceSources"],
                "georeferenceProtocol": geo["georeferenceProtocol"],
                "minimumElevationInMeters": elevation,
                "maximumElevationInMeters": elevation,
                # a record without its own date inherits the event's date (or
                # multi-day interval)
                "eventDate": obs_event_date(obs, entry_date),
                "eventTime": obs.event_time or "",
                "habitat": obs.habitat.label if obs.habitat is not None else "",
                "occurrenceRemarks": _clean(_occurrence_remarks(obs)),
                "recordedBy": _recorded_by(obs),
                "associatedReferences": _clean(obs.literature_citation or ""),
                "dynamicProperties": _dynamic_properties(obs),
            })
    return rows

