"""Build MeasurementOrFact extension rows (evidence and count qualifiers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "measurementID", "measurementType", "measurementValue",
    "measurementMethod",
]

_METHOD = "rule-based extraction from diary text"


def build_measurements(result: "ExtractionResult") -> list[dict]:
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        for obs in entry.observations:
            for evidence in obs.evidence:
                rows.append(_row(entry, obs, "evidenceType", evidence.kind))
                if evidence.is_call and evidence.call_type:
                    rows.append(_row(entry, obs, "callType", evidence.call_type))
            if obs.count_qualifier:
                rows.append(_row(entry, obs, "countQualifier", obs.count_qualifier))
    return rows


def _row(entry, obs, mtype: str, value: str) -> dict:
    return {
        "eventID": entry.entry_uid,
        "measurementID": f"{obs.uid}:{mtype}",
        "measurementType": mtype,
        "measurementValue": value,
        "measurementMethod": _METHOD,
    }
