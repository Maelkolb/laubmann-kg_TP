"""Build OBIS ExtendedMeasurementOrFact (eMoF) extension rows.

One row per controlled value of an occurrence that has no Darwin Core term of
its own: evidence kind, call type, count qualifier, breeding evidence, movement
kind, record type, time of day, and the EUNIS class of its habitat.
measurementTypeID carries the SKOS concept-scheme IRI of the project vocabulary,
measurementValueID the concept IRI (ontologies/controlled_vocabularies.ttl,
skos:notation = the value), so the values remain machine-resolvable outside the
RDF graph. Free text and numbers without a DwC term go to dynamicProperties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from laubmann_kg.kg.model import ONTO_NS, data_iri
from laubmann_kg.normalization import vocabularies as vocab

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "occurrenceID", "measurementID", "measurementType",
    "measurementTypeID", "measurementValue", "measurementValueID",
    "measurementMethod",
]

ROW_TYPE = "http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact"

DEFAULT_METHOD = "extraction from diary text"
# the EUNIS habitat classification as published by Eionet (the maintained vocabulary)
EUNIS_SCHEME = "https://dd.eionet.europa.eu/vocabulary/biodiversity/eunishabitats/"

# measurementType (= the lkg property's local name) -> (SKOS scheme, concept local-name prefix)
SCHEMES = {
    "evidenceKind": ("evidenceKindScheme", "evidence_"),
    "callType": ("callTypeScheme", "call_"),
    "countQualifier": ("countQualifierScheme", "count_"),
    "breedingEvidence": ("breedingEvidenceScheme", "breeding_"),
    "movementKind": ("movementKindScheme", "movement_"),
    "recordType": ("recordTypeScheme", "record_"),
    "timeOfDay": ("timeOfDayScheme", "timeofday_"),
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

            for kind in dict.fromkeys(e.kind for e in obs.evidence):      # song + call: one "auditory"
                _add("evidenceKind", kind)
            for call_type in dict.fromkeys(e.call_type for e in obs.evidence
                                           if e.is_call and e.call_type in vocab.EMITTED_CALL_TYPES):
                _add("callType", call_type)
            _add("countQualifier", obs.count_qualifier)
            _add("breedingEvidence", obs.breeding_evidence)
            _add("movementKind", obs.movement_kind)
            _add("recordType", obs.record_type)
            _add("timeOfDay", obs.time_of_day)
            h = obs.habitat
            if h is not None and getattr(h, "eunis_code", None) and getattr(h, "eunis_uri", None):
                # the EUNIS class the diarist's habitat label maps to (linking/habitats.py)
                rows.append({
                    "eventID": data_iri(entry.uid), "occurrenceID": data_iri(obs.uid),
                    "measurementID": f"{data_iri(obs.uid)}:habitatEUNIS:0",
                    "measurementType": "habitat type (EUNIS 2012)",
                    "measurementTypeID": EUNIS_SCHEME,
                    "measurementValue": f"{h.eunis_code} {h.eunis_label or ''}".strip(),
                    "measurementValueID": h.eunis_uri,
                    "measurementMethod": f"{(h.eunis_match or 'close')} match of the diary habitat label '{h.label}' (LLM-assisted classification)",
                })
    return rows


def _row(entry, obs, mtype: str, value: str, index: int, method: str) -> dict:
    return {
        "eventID": data_iri(entry.uid),
        "occurrenceID": data_iri(obs.uid),
        "measurementID": f"{data_iri(obs.uid)}:{mtype}:{index}",
        "measurementType": mtype,
        "measurementTypeID": scheme_iri(mtype),
        "measurementValue": value,
        "measurementValueID": concept_iri(mtype, value),
        "measurementMethod": method,
    }
