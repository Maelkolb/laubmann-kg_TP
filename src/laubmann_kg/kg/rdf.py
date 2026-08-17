"""Build and serialize the knowledge graph as RDF, conforming to laubmann.ttl.

Design notes
- The data contract is ``kg/model.py``; this module only maps it onto triples.
- SHACL runs with ``inference="none"`` (see shacl_validate.py), so every
  superclass a shape relies on is materialised here at emit time
  (BirdCall→ObservationEvidence, Habitat→skos:Concept, SourceRegion→oa:Annotation).
- Project terms (``lkg:``) are primary; Darwin Core / PROV / DCTERMS / schema.org
  terms are co-emitted so generic consumers can read the graph without the
  ontology. Nothing is inferred from prose here: a value is emitted only when the
  extractor set it.
"""

from __future__ import annotations

import hashlib
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from laubmann_kg.kg.model import (
    DATA_NS,
    DIARIST,
    Behaviour,
    DiaryEntry,
    DiaryPage,
    DiaryVolume,
    Evidence,
    Habitat,
    Observation,
    Person,
    Place,
    Taxon,
    TravelEvent,
)
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.vocabularies import basis_of_record

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

LKG = Namespace("https://lkg.example.org/ontology#")
DWC = Namespace("http://rs.tdwg.org/dwc/terms/")
DWCIRI = Namespace("http://rs.tdwg.org/dwc/iri/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
SCHEMA = Namespace("https://schema.org/")
OA = Namespace("http://www.w3.org/ns/oa#")
DATA = Namespace(DATA_NS)
DE = "de"

# Evidence kinds map 1:1 onto the SKOS concepts in controlled_vocabularies.ttl.
_EVIDENCE_CONCEPTS = {kind: LKG[f"evidence_{kind}"] for kind in vocab.EVIDENCE_KINDS}
_BREEDING_IMPLIES_BREEDING = ("confirmed", "probable")


def _uri(uid: str) -> URIRef:
    return DATA[uid]


def _bind(graph: Graph) -> None:
    graph.bind("lkg", LKG)
    graph.bind("dwc", DWC)
    graph.bind("dwciri", DWCIRI)
    # rdflib pre-binds "geo" to GeoSPARQL; force it onto WGS84 so the Turtle
    # reads "geo:lat", not "geo1:lat".
    graph.bind("geo", GEO, override=True, replace=True)
    graph.bind("data", DATA)
    graph.bind("skos", SKOS)
    graph.bind("owl", OWL)
    graph.bind("prov", PROV)
    graph.bind("dcterms", DCTERMS)
    graph.bind("schema", SCHEMA)
    graph.bind("oa", OA)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)


def _decimal(value: float) -> Literal:
    return Literal(Decimal(str(value)), datatype=XSD.decimal)


def _iri_slug(value: str) -> str:
    """Readable, IRI-safe local-name fragment (model names like 'gemini-2.5-flash')."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower()).strip("-.")
    return slug or "unknown"


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------

def _add_taxon(graph: Graph, taxon: Taxon) -> URIRef:
    node = _uri(taxon.uid)
    if (node, RDF.type, LKG.Taxon) in graph:
        return node
    graph.add((node, RDF.type, LKG.Taxon))
    graph.add((node, RDFS.label, Literal(taxon.vernacular_de, lang=DE)))
    graph.add((node, LKG.vernacularNameDE, Literal(taxon.vernacular_de, lang=DE)))
    graph.add((node, DWC.vernacularName, Literal(taxon.vernacular_de, lang=DE)))
    if taxon.scientific_name:
        graph.add((node, LKG.scientificName, Literal(taxon.scientific_name)))
        graph.add((node, DWC.scientificName, Literal(taxon.scientific_name)))
    else:
        note = taxon.note or "wissenschaftlicher Name nicht aufgelöst"
        graph.add((node, SKOS.note, Literal(note, lang=DE)))
    if taxon.rank:
        graph.add((node, DWC.taxonRank, Literal(taxon.rank)))
    if taxon.is_bird is not None:
        graph.add((node, LKG.isBird, Literal(bool(taxon.is_bird), datatype=XSD.boolean)))
    # match provenance (how the vernacular was resolved)
    graph.add((node, LKG.matchMethod, Literal(taxon.match_method)))
    if taxon.confidence is not None:
        graph.add((node, LKG.matchConfidence, _decimal(taxon.confidence)))
    if taxon.gbif_match_type:
        graph.add((node, LKG.gbifMatchType, Literal(taxon.gbif_match_type)))
    if taxon.taxon_iri:
        graph.add((node, OWL.sameAs, URIRef(taxon.taxon_iri)))
    if taxon.gbif_key:
        gbif = URIRef(f"https://www.gbif.org/species/{taxon.gbif_key}")
        if taxon.gbif_match_type == "HIGHERRANK":
            pred = SKOS.broadMatch          # genus anchor is broader, not equal
        elif taxon.match_method == "llm+gbif" or taxon.gbif_match_type == "FUZZY":
            pred = SKOS.closeMatch          # LLM-mediated or fuzzy: weaker claim
        else:
            pred = SKOS.exactMatch
        graph.add((node, pred, gbif))
        if taxon.gbif_match_type != "HIGHERRANK":
            graph.add((node, DWC.taxonID, Literal(str(gbif))))
    return node


def _add_place(graph: Graph, place: Place) -> URIRef:
    node = _uri(place.uid)
    if (node, RDF.type, LKG.Place) not in graph:
        graph.add((node, RDF.type, LKG.Place))
        graph.add((node, RDFS.label, Literal(place.name, lang=DE)))
        graph.add((node, LKG.verbatimLocality, Literal(place.verbatim)))
        if place.kind:
            graph.add((node, LKG.placeKind, Literal(place.kind)))
        if place.lat is not None and place.long is not None:
            graph.add((node, GEO.lat, _decimal(place.lat)))
            graph.add((node, GEO.long, _decimal(place.long)))
            graph.add((node, DWC.decimalLatitude, _decimal(place.lat)))
            graph.add((node, DWC.decimalLongitude, _decimal(place.long)))
            graph.add((node, DWC.geodeticDatum, Literal("WGS84")))
    return node


def _add_evidence(graph: Graph, obs_uid: str, evidence: Evidence, index: int = 0) -> URIRef:
    node = _uri(evidence.uid(obs_uid, index))
    cls = LKG.BirdCall if evidence.is_call else LKG.ObservationEvidence
    graph.add((node, RDF.type, cls))
    if evidence.is_call:
        # Materialize the superclass so SHACL sh:class checks hold without
        # running RDFS inference over the full graph (prohibitive at 1M+ triples).
        graph.add((node, RDF.type, LKG.ObservationEvidence))
    graph.add((node, RDFS.label, Literal(evidence.label, lang=DE)))
    concept = _EVIDENCE_CONCEPTS.get(evidence.kind)
    if concept is not None:
        graph.add((node, LKG.evidenceKind, concept))
    if evidence.is_call:
        # No placeholder transcription: only what the diary actually wrote.
        if evidence.call_transcription:
            graph.add((node, LKG.callTranscription, Literal(evidence.call_transcription)))
        graph.add((node, LKG.callType, Literal(evidence.call_type or "unknown")))
    return node


def _add_habitat(graph: Graph, habitat: Habitat) -> URIRef:
    node = _uri(habitat.uid)
    if (node, RDF.type, LKG.Habitat) not in graph:
        graph.add((node, RDF.type, LKG.Habitat))
        graph.add((node, RDF.type, SKOS.Concept))  # materialized superclass, see _add_evidence
        graph.add((node, RDFS.label, Literal(habitat.label, lang=DE)))
        graph.add((node, SKOS.prefLabel, Literal(habitat.label, lang=DE)))
        graph.add((node, SKOS.inScheme, LKG.habitatScheme))
        graph.add((node, DWC.habitat, Literal(habitat.label, lang=DE)))
        graph.add((LKG.habitatScheme, RDF.type, SKOS.ConceptScheme))
    return node


def _add_person(graph: Graph, person: Person) -> URIRef:
    node = _uri(person.uid)
    if (node, RDF.type, LKG.Person) not in graph:
        graph.add((node, RDF.type, LKG.Person))
        graph.add((node, RDFS.label, Literal(person.name)))
        graph.add((node, SCHEMA.name, Literal(person.name)))
        if person.role:
            graph.add((node, SKOS.note, Literal(person.role)))
    # Outside the type guard: an enriched Person instance may arrive after a
    # bare one; rdflib set semantics dedupes the repeated add.
    if person.wikidata_iri:
        graph.add((node, OWL.sameAs, URIRef(person.wikidata_iri)))
    return node


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def _add_travel_event(graph: Graph, entry_node: URIRef, event: TravelEvent,
                      run: Optional[URIRef] = None) -> None:
    ev = _uri(event.uid)
    graph.add((ev, RDF.type, LKG.TravelEvent))
    graph.add((ev, RDFS.label,
               Literal(f"Reise · {len(event.legs)} Etappe(n)", lang=DE)))
    graph.add((entry_node, LKG.containsTravelEvent, ev))
    if run is not None:
        graph.add((ev, PROV.wasGeneratedBy, run))
    for i, leg in enumerate(event.legs):
        node = _uri(leg.uid(event.uid, i))
        graph.add((node, RDF.type, LKG.TravelLeg))
        graph.add((ev, LKG.hasLeg, node))
        graph.add((node, LKG.departurePlace, _add_place(graph, leg.departure_place)))
        graph.add((node, LKG.arrivalPlace, _add_place(graph, leg.arrival_place)))
        for via in leg.via_places:
            graph.add((node, LKG.viaPlace, _add_place(graph, via)))
        graph.add((node, LKG.transportMode, Literal(leg.transport_mode)))
        if leg.departure_time:
            graph.add((node, LKG.departureTime,
                       Literal(leg.departure_time, datatype=XSD.dateTime)))
        if leg.arrival_time:
            graph.add((node, LKG.arrivalTime,
                       Literal(leg.arrival_time, datatype=XSD.dateTime)))
        if leg.verbatim:
            # skos:note, NOT lkg:verbatimNotes — that property's rdfs:domain is
            # ObservationEvent and would re-type the leg under RDFS inference.
            graph.add((node, SKOS.note, Literal(leg.verbatim, lang=DE)))


def _add_behaviour(graph: Graph, obs_uid: str, behaviour: Behaviour) -> URIRef:
    node = _uri(behaviour.uid(obs_uid))
    graph.add((node, RDF.type, LKG.BehaviourNote))
    graph.add((node, RDFS.label, Literal(behaviour.label, lang=DE)))
    if behaviour.reproductive_condition:
        graph.add((node, DWC.reproductiveCondition, Literal(behaviour.reproductive_condition)))
    return node


def _add_weather(graph: Graph, entry_node: URIRef, entry: DiaryEntry,
                 run: Optional[URIRef] = None) -> None:
    w = entry.weather
    node = _uri(w.uid(entry.entry_uid))
    graph.add((node, RDF.type, LKG.WeatherReport))  # no superclass, nothing to materialize
    graph.add((node, RDFS.label, Literal(f"Wetter {entry.entry_date}", lang=DE)))
    graph.add((node, LKG.weatherVerbatim, Literal(w.verbatim, lang=DE)))
    if w.temperature_value is not None:
        graph.add((node, LKG.temperatureValue, _decimal(w.temperature_value)))
        if w.temperature_unit:
            graph.add((node, LKG.temperatureUnit, Literal(w.temperature_unit)))
    if w.precipitation:
        graph.add((node, LKG.precipitation, Literal(w.precipitation)))
    if w.wind:
        graph.add((node, LKG.wind, Literal(w.wind, lang=DE)))
    if w.sky:
        graph.add((node, LKG.skyCondition, Literal(w.sky)))
    graph.add((entry_node, LKG.hasWeather, node))
    if run is not None:
        graph.add((node, PROV.wasGeneratedBy, run))


def _add_observation(graph: Graph, obs: Observation, entry_date: Optional[str] = None,
                     run: Optional[URIRef] = None) -> Optional[URIRef]:
    if obs.taxon.vernacular_de is None:
        return None
    node = _uri(obs.uid)
    graph.add((node, RDF.type, LKG.ObservationEvent))
    label = f"Beobachtung {obs.taxon.vernacular_de}"
    graph.add((node, RDFS.label, Literal(label, lang=DE)))
    graph.add((node, LKG.observedTaxon, _add_taxon(graph, obs.taxon)))
    graph.add((node, LKG.derivedFromEntry, _uri(f"entry_{obs.entry_uid}")))
    graph.add((node, LKG.verbatimNotes, Literal(obs.verbatim_notes, lang=DE)))

    # --- where: effective place (own locality, else inherited entry place) ---
    if obs.place is not None:
        graph.add((node, LKG.observedAt, _add_place(graph, obs.place)))
    if obs.locality is not None:
        # Own locality stated in the record: consumers can tell it apart from
        # the inherited entry place via hasLocality / dwc:verbatimLocality.
        graph.add((node, LKG.hasLocality, _add_place(graph, obs.locality)))
        graph.add((node, DWC.verbatimLocality, Literal(obs.locality.verbatim)))

    # --- when: the record's own date/time, else the entry date -----------
    event_date = obs.event_date or entry_date
    if event_date:
        graph.add((node, DWC.eventDate, Literal(event_date, datatype=XSD.date)))
    if obs.event_time:
        graph.add((node, DWC.eventTime, Literal(obs.event_time)))

    # --- what: status, counts, demography ---------------------------------
    graph.add((node, DWC.occurrenceStatus, Literal(obs.occurrence_status)))
    if obs.individual_count is not None:
        count = Literal(int(obs.individual_count), datatype=XSD.integer)
        graph.add((node, LKG.individualCount, count))
        graph.add((node, DWC.individualCount, count))
    if obs.count_min is not None:
        graph.add((node, LKG.individualCountMin, Literal(int(obs.count_min), datatype=XSD.integer)))
    if obs.count_max is not None:
        graph.add((node, LKG.individualCountMax, Literal(int(obs.count_max), datatype=XSD.integer)))
    if obs.count_qualifier:
        graph.add((node, LKG.countQualifier, Literal(obs.count_qualifier)))
    if obs.sex:
        graph.add((node, DWC.sex, Literal(obs.sex)))
    if obs.life_stage:
        graph.add((node, DWC.lifeStage, Literal(obs.life_stage)))
    if obs.vitality:
        graph.add((node, DWC.vitality, Literal(obs.vitality)))
    if obs.identification_qualifier:
        graph.add((node, DWC.identificationQualifier, Literal(obs.identification_qualifier)))
    if obs.breeding_evidence:
        graph.add((node, LKG.breedingEvidence, Literal(obs.breeding_evidence)))
        if obs.breeding_evidence in _BREEDING_IMPLIES_BREEDING:
            graph.add((node, DWC.reproductiveCondition, Literal("breeding")))
    if obs.movement_kind:
        graph.add((node, LKG.movementKind, Literal(obs.movement_kind)))
    if obs.flight_direction:
        graph.add((node, LKG.flightDirection, Literal(obs.flight_direction, lang=DE)))
    if obs.occurrence_remarks:
        graph.add((node, DWC.occurrenceRemarks, Literal(obs.occurrence_remarks, lang=DE)))

    # --- record provenance ------------------------------------------------
    graph.add((node, LKG.recordType, Literal(obs.record_type)))
    graph.add((node, DWC.basisOfRecord,
               Literal(basis_of_record(obs.record_type, (e.kind for e in obs.evidence)))))
    # Unattributed third-party/literature records get NO observedBy — never
    # fabricate attribution.
    observer = obs.observer or (DIARIST if obs.record_type == "field-observation" else None)
    if observer is not None:
        person = _add_person(graph, observer)
        graph.add((node, LKG.observedBy, person))
        graph.add((node, DWCIRI.recordedBy, person))
    if obs.literature_citation:
        graph.add((node, DWC.associatedReferences, Literal(obs.literature_citation, lang=DE)))
    if run is not None:
        graph.add((node, PROV.wasGeneratedBy, run))

    # --- evidence / behaviour / habitat -----------------------------------
    for i, evidence in enumerate(obs.evidence):
        graph.add((node, LKG.hasEvidence, _add_evidence(graph, obs.uid, evidence, i)))
    for behaviour in obs.behaviour:
        graph.add((node, LKG.hasBehaviour, _add_behaviour(graph, obs.uid, behaviour)))
        graph.add((node, DWC.behavior, Literal(behaviour.label, lang=DE)))
    if obs.habitat is not None:
        habitat = _add_habitat(graph, obs.habitat)
        graph.add((node, LKG.hasHabitat, habitat))
        graph.add((node, DWCIRI.habitat, habitat))
        graph.add((node, DWC.habitat, Literal(obs.habitat.label, lang=DE)))
    return node


def _add_entry(graph: Graph, entry: DiaryEntry, run: Optional[URIRef] = None) -> None:
    node = _uri(entry.uid)
    graph.add((node, RDF.type, LKG.DiaryEntry))
    graph.add((node, RDFS.label, Literal(entry.label, lang=DE)))
    if entry.entry_id:
        graph.add((node, DCTERMS.identifier, Literal(entry.entry_id)))
    graph.add((node, LKG.entryDate, Literal(entry.entry_date, datatype=XSD.date)))
    if entry.entry_date_end:
        graph.add((node, LKG.entryDateEnd, Literal(entry.entry_date_end, datatype=XSD.date)))
        # DwC interval notation for multi-day entries
        graph.add((node, DWC.eventDate, Literal(f"{entry.entry_date}/{entry.entry_date_end}")))
    else:
        graph.add((node, DWC.eventDate, Literal(entry.entry_date, datatype=XSD.date)))
    if entry.verbatim_event_date:
        graph.add((node, DWC.verbatimEventDate, Literal(entry.verbatim_event_date)))
    if entry.date_plausible is not None:
        graph.add((node, LKG.datePlausible,
                   Literal(bool(entry.date_plausible), datatype=XSD.boolean)))
    if entry.date_note:
        note = Literal(entry.date_note, lang=DE)
        graph.add((node, LKG.dateNote, note))
        graph.add((node, SKOS.note, note))       # lkg:dateNote ⊑ skos:note, materialised
    if entry.entry_kind:
        graph.add((node, LKG.entryKind, Literal(entry.entry_kind)))
    if entry.place is not None:
        graph.add((node, LKG.entryPlace, _add_place(graph, entry.place)))
    if entry.text_clean:
        graph.add((node, LKG.rawText, Literal(entry.text_clean)))

    volume = DiaryVolume(entry.volume)
    volume_node = _uri(volume.uid)
    graph.add((node, LKG.hasVolume, volume_node))
    graph.add((volume_node, RDF.type, LKG.DiaryVolume))
    graph.add((volume_node, RDFS.label, Literal(volume.label, lang=DE)))
    page_node: Optional[URIRef] = None
    if entry.page_uid:
        page = DiaryPage(entry.page_uid, entry.volume, entry.page_id, entry.scan)
        page_node = _uri(page.uid)
        graph.add((node, LKG.hasPage, page_node))
        graph.add((page_node, RDF.type, LKG.DiaryPage))
        graph.add((page_node, RDFS.label, Literal(page.label)))
        if page.page_id:
            graph.add((page_node, DCTERMS.identifier, Literal(page.page_id)))
        graph.add((page_node, DCTERMS.isPartOf, volume_node))
    if entry.region_uid:
        # The layout region on the scanned page whose text became this entry.
        region = _uri(f"region_{entry.region_uid}")
        graph.add((node, LKG.hasSourceRegion, region))
        graph.add((region, RDF.type, LKG.SourceRegion))
        graph.add((region, RDF.type, OA.Annotation))  # materialized superclass
        graph.add((region, RDFS.label, Literal(f"Region {entry.region_uid}")))
        if page_node is not None:
            graph.add((region, DCTERMS.isPartOf, page_node))

    for obs in entry.observations:
        obs_node = _add_observation(graph, obs, entry.entry_date, run)
        if obs_node is not None:
            graph.add((node, LKG.containsObservation, obs_node))
    for event in entry.travel_events:
        _add_travel_event(graph, node, event, run)
    for person in entry.persons:
        graph.add((node, LKG.mentionsPerson, _add_person(graph, person)))
    if entry.weather is not None:
        _add_weather(graph, node, entry, run)


# --------------------------------------------------------------------------
# PROV skeleton
# --------------------------------------------------------------------------

def run_uid(provenance: dict) -> Optional[str]:
    """Stable local name of the extraction-run activity, or None when the result
    carries no provenance (e.g. hand-built test results)."""
    if not provenance:
        return None
    key = "|".join(str(provenance.get(k) or "")
                   for k in ("model", "prompt_sha256", "started_at"))
    return f"run_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def _add_provenance(graph: Graph, provenance: dict) -> Optional[URIRef]:
    uid = run_uid(provenance)
    if uid is None:
        return None
    run = _uri(uid)
    model = str(provenance.get("model") or "unknown")
    backend = provenance.get("backend")
    graph.add((run, RDF.type, PROV.Activity))
    graph.add((run, RDFS.label, Literal(f"Extraction run · {model}")))
    if provenance.get("method"):
        graph.add((run, RDFS.comment, Literal(str(provenance["method"]))))
    if provenance.get("started_at"):
        graph.add((run, PROV.startedAtTime,
                   Literal(str(provenance["started_at"]), datatype=XSD.dateTime)))
    agent = _uri(f"agent_{_iri_slug(model)}")
    graph.add((run, PROV.wasAssociatedWith, agent))
    graph.add((agent, RDF.type, PROV.SoftwareAgent))
    graph.add((agent, RDFS.label, Literal(model)))
    if backend:
        graph.add((agent, LKG.backend, Literal(str(backend))))
    sha = provenance.get("prompt_sha256")
    if sha:
        prompt = _uri(f"prompt_{str(sha)[:12]}")
        graph.add((run, PROV.used, prompt))
        graph.add((prompt, RDF.type, PROV.Entity))
        graph.add((prompt, RDFS.label, Literal(str(provenance.get("prompt") or "prompt"))))
        graph.add((prompt, DCTERMS.identifier, Literal(str(sha))))
    return run


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def build_graph(result: "ExtractionResult") -> Graph:
    """Build an rdflib Graph. Only dated entries are emitted (SHACL requires a
    single xsd:date entryDate); undated entries are skipped and logged."""
    graph = Graph()
    _bind(graph)
    run = _add_provenance(graph, getattr(result, "provenance", None) or {})
    skipped = 0
    for entry in result.entries:
        if not entry.entry_date:
            skipped += 1
            continue
        _add_entry(graph, entry, run)
    if skipped:
        logger.warning("skipped %d undated entries (SHACL entryDate requirement)", skipped)
    return graph


def serialize_turtle(graph: Graph, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(path), format="turtle")
    logger.info("wrote %d triples to %s", len(graph), path)
    return path
