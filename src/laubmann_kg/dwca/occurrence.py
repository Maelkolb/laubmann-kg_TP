"""Build Darwin Core Occurrence extension rows (one per observation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "occurrenceID", "basisOfRecord", "scientificName", "vernacularName",
    "individualCount", "occurrenceStatus", "occurrenceRemarks",
    "identificationRemarks", "recordedBy", "associatedMedia",
]

DEFAULT_RECORDED_BY = "Adolf Laubmann"


def _basis_of_record(obs) -> str:
    if any(e.kind == "specimen" for e in obs.evidence):
        return "PreservedSpecimen"
    return "HumanObservation"


def build_occurrences(result: "ExtractionResult", media_by_entry: dict | None = None) -> list[dict]:
    media_by_entry = media_by_entry or {}
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        media = ";".join(media_by_entry.get(entry.entry_uid, []))
        for obs in entry.observations:
            taxon = obs.taxon
            ident = "" if taxon.scientific_name else "Art nicht sicher bestimmt; nur Trivialname"
            rows.append({
                "eventID": entry.entry_uid,
                "occurrenceID": obs.uid,
                "basisOfRecord": _basis_of_record(obs),
                "scientificName": taxon.scientific_name or "",
                "vernacularName": taxon.vernacular_de,
                "individualCount": str(obs.individual_count) if obs.individual_count else "",
                "occurrenceStatus": "present",
                "occurrenceRemarks": obs.verbatim_notes,
                "identificationRemarks": ident,
                "recordedBy": DEFAULT_RECORDED_BY,
                "associatedMedia": media,
            })
    return rows
