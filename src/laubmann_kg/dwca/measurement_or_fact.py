"""Build OBIS ExtendedMeasurementOrFact (eMoF) extension rows.

One row per categorical fact about an occurrence: evidence kind, call type,
count qualifier, breeding evidence, movement kind. measurementTypeID carries
the SKOS concept-scheme IRI of the project vocabulary, measurementValueID the
concept IRI (ontologies/controlled_vocabularies.ttl), so the values remain
machine-resolvable outside the RDF graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from laubmann_kg.kg.model import ONTO_NS

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "occurrenceID", "measurementID", "measurementType",
    "measurementTypeID", "measurementValue", "measurementValueID",
    "measurementMethod",
]

ROW_TYPE = "http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact"

DEFAULT_METHOD = "extraction from diary text"

# measurementType -> (SKOS scheme local name, concept local-name prefix)
SCHEMES = {
    "evidenceType": ("evidenceKindScheme", "evidence_"),
    "callType": ("callTypeScheme", "call_"),
    "countQualifier": ("countQualifierScheme", "count_"),
    "breedingEvidence": ("breedingEvidenceScheme", "breeding_"),
    "movementKind": ("movementKindScheme", "movement_"),
}


def scheme_iri(mtype: str) -> str:
    return ONTO_NS + SCHEMES[mtype][0]


def concept_iri(mtype: str, value: str) -> str:
    return ONTO_NS + SCHEMES[mtype][1] + value.strip().lower().replace("-", "_")


def build_measurements(result: "ExtractionResult") -> list[dict]:
    method = (result.provenance or {}).get("method") or DEFAULT_METHOD
    rows = []
    for entry in result.entries:
        if not entry.entry_date:
            continue
        for obs in entry.observations:
            counters: dict[str, int] = {}

            def _add(mtype: str, value) -> None:
                if value in (None, ""):
                    return
                index = counters.get(mtype, 0)
                counters[mtype] = index + 1
                rows.append(_row(entry, obs, mtype, str(value), index, method))

            for evidence in obs.evidence:
                _add("evidenceType", evidence.kind)
                if evidence.is_call and evidence.call_type:
                    _add("callType", evidence.call_type)
            _add("countQualifier", obs.count_qualifier)
            _add("breedingEvidence", obs.breeding_evidence)
            _add("movementKind", obs.movement_kind)
    return rows


def _row(entry, obs, mtype: str, value: str, index: int, method: str) -> dict:
    return {
        "eventID": entry.entry_uid,
        "occurrenceID": obs.uid,
        "measurementID": f"{obs.uid}:{mtype}:{index}",
        "measurementType": mtype,
        "measurementTypeID": scheme_iri(mtype),
        "measurementValue": value,
        "measurementValueID": concept_iri(mtype, value),
        "measurementMethod": method,
    }
