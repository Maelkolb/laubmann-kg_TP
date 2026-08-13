"""Build Darwin Core Occurrence extension rows (one per observation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from laubmann_kg.normalization.vocabularies import basis_of_record

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "occurrenceID", "basisOfRecord", "scientificName", "vernacularName",
    "individualCount", "occurrenceStatus", "occurrenceRemarks",
    "identificationRemarks", "recordedBy", "associatedMedia",
    "associatedReferences", "taxonID",
]

DEFAULT_RECORDED_BY = "Alfred Laubmann"


def _basis_of_record(obs) -> str:
    return basis_of_record(obs.record_type, (e.kind for e in obs.evidence))


def _recorded_by(obs) -> str:
    if obs.observer is not None:
        return obs.observer.name
    if obs.record_type == "field-observation":
        return DEFAULT_RECORDED_BY          # == model.DIARIST.name
    return ""   # unattributed third-party/literature record: claim nothing


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
                "recordedBy": _recorded_by(obs),
                "associatedMedia": media,
                "associatedReferences": (obs.literature_citation or "").replace("\t", " ").replace("\n", " "),
                "taxonID": (f"https://www.gbif.org/species/{taxon.gbif_key}"
                            if taxon.gbif_key and taxon.gbif_match_type != "HIGHERRANK" else ""),
            })
    return rows
