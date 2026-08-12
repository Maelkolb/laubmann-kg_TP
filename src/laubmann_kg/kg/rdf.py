"""Build and serialize the knowledge graph as RDF, conforming to laubmann.ttl."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD, OWL

from laubmann_kg.kg.model import (
    DATA_NS,
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

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

LKG = Namespace("https://lkg.example.org/ontology#")
DWC = Namespace("http://rs.tdwg.org/dwc/terms/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
DATA = Namespace(DATA_NS)
DE = "de"


def _uri(uid: str) -> URIRef:
    return DATA[uid]


def _bind(graph: Graph) -> None:
    graph.bind("lkg", LKG)
    graph.bind("dwc", DWC)
    graph.bind("geo", GEO)
    graph.bind("data", DATA)
    graph.bind("skos", SKOS)


def _add_taxon(graph: Graph, taxon: Taxon) -> URIRef:
    node = _uri(taxon.uid)
    if (node, RDF.type, LKG.Taxon) in graph:
        return node
    graph.add((node, RDF.type, LKG.Taxon))
    graph.add((node, LKG.vernacularNameDE, Literal(taxon.vernacular_de, lang=DE)))
    if taxon.scientific_name:
        graph.add((node, LKG.scientificName, Literal(taxon.scientific_name)))
        graph.add((node, DWC.scientificName, Literal(taxon.scientific_name)))
    else:
        note = taxon.note or "wissenschaftlicher Name nicht aufgelöst"
        graph.add((node, SKOS.note, Literal(note, lang=DE)))
    if taxon.taxon_iri:
        graph.add((node, OWL.sameAs, URIRef(taxon.taxon_iri)))
    return node


def _add_place(graph: Graph, place: Place) -> URIRef:
    node = _uri(place.uid)
    if (node, RDF.type, LKG.Place) not in graph:
        graph.add((node, RDF.type, LKG.Place))
        graph.add((node, RDFS.label, Literal(place.name, lang=DE)))
        graph.add((node, LKG.verbatimLocality, Literal(place.verbatim)))
        if place.lat is not None and place.long is not None:
            graph.add((node, GEO.lat, Literal(Decimal(str(place.lat)), datatype=XSD.decimal)))
            graph.add((node, GEO.long, Literal(Decimal(str(place.long)), datatype=XSD.decimal)))
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
    if evidence.is_call:
        graph.add((node, LKG.callTranscription, Literal(evidence.call_transcription or "Ruf")))
        if evidence.call_type:
            graph.add((node, LKG.callType, Literal(evidence.call_type)))
    else:
        graph.add((node, DWC.occurrenceStatus, Literal(evidence.occurrence_status)))
    return node


def _add_habitat(graph: Graph, habitat: Habitat) -> URIRef:
    node = _uri(habitat.uid)
    if (node, RDF.type, LKG.Habitat) not in graph:
        graph.add((node, RDF.type, LKG.Habitat))
        graph.add((node, RDF.type, LKG.Place))  # materialized superclass, see _add_evidence
        graph.add((node, RDFS.label, Literal(habitat.label, lang=DE)))
        graph.add((node, DWC.habitat, Literal(habitat.label, lang=DE)))
    return node


def _add_person(graph: Graph, person: Person) -> URIRef:
    node = _uri(person.uid)
    if (node, RDF.type, LKG.Person) not in graph:
        graph.add((node, RDF.type, LKG.Person))
        graph.add((node, RDFS.label, Literal(person.name)))
        if person.role:
            graph.add((node, SKOS.note, Literal(person.role)))
    return node


def _add_travel_event(graph: Graph, entry_node: URIRef, event: TravelEvent) -> None:
    ev = _uri(event.uid)
    graph.add((ev, RDF.type, LKG.TravelEvent))
    graph.add((ev, RDFS.label,
               Literal(f"Reise · {len(event.legs)} Etappe(n)", lang=DE)))
    graph.add((entry_node, LKG.containsTravelEvent, ev))
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


def _add_observation(graph: Graph, obs: Observation) -> Optional[URIRef]:
    if obs.taxon.vernacular_de is None:
        return None
    node = _uri(obs.uid)
    graph.add((node, RDF.type, LKG.ObservationEvent))
    label = f"Beobachtung {obs.taxon.vernacular_de}"
    graph.add((node, RDFS.label, Literal(label, lang=DE)))
    graph.add((node, LKG.observedTaxon, _add_taxon(graph, obs.taxon)))
    graph.add((node, LKG.derivedFromEntry, _uri(f"entry_{obs.entry_uid}")))
    graph.add((node, LKG.verbatimNotes, Literal(obs.verbatim_notes, lang=DE)))
    if obs.place is not None:
        graph.add((node, LKG.observedAt, _add_place(graph, obs.place)))
    if obs.individual_count is not None and obs.individual_count >= 1:
        graph.add((node, LKG.individualCount,
                   Literal(int(obs.individual_count), datatype=XSD.integer)))
    if obs.count_qualifier:
        graph.add((node, LKG.countQualifier, Literal(obs.count_qualifier)))
    if obs.occurrence_remarks:
        graph.add((node, DWC.occurrenceRemarks, Literal(obs.occurrence_remarks, lang=DE)))
    for i, evidence in enumerate(obs.evidence):
        graph.add((node, LKG.hasEvidence, _add_evidence(graph, obs.uid, evidence, i)))
    for behaviour in obs.behaviour:
        graph.add((node, LKG.hasBehaviour, _add_behaviour(graph, obs.uid, behaviour)))
    if obs.habitat is not None:
        graph.add((node, LKG.hasHabitat, _add_habitat(graph, obs.habitat)))
    return node


def _add_entry(graph: Graph, entry: DiaryEntry) -> None:
    node = _uri(entry.uid)
    graph.add((node, RDF.type, LKG.DiaryEntry))
    graph.add((node, RDFS.label, Literal(entry.label, lang=DE)))
    graph.add((node, LKG.entryDate, Literal(entry.entry_date, datatype=XSD.date)))
    if entry.verbatim_event_date:
        graph.add((node, DWC.verbatimEventDate, Literal(entry.verbatim_event_date)))
    if entry.text_clean:
        graph.add((node, LKG.rawText, Literal(entry.text_clean)))
    for citation in entry.citations:
        graph.add((node, DWC.associatedReferences, Literal(citation, lang=DE)))
    volume = DiaryVolume(entry.volume)
    graph.add((node, LKG.hasVolume, _uri(volume.uid)))
    graph.add((_uri(volume.uid), RDF.type, LKG.DiaryVolume))
    graph.add((_uri(volume.uid), RDFS.label, Literal(volume.label, lang=DE)))
    if entry.page_uid:
        page = DiaryPage(entry.page_uid, entry.volume, entry.page_id, entry.scan)
        graph.add((node, LKG.hasPage, _uri(page.uid)))
        graph.add((_uri(page.uid), RDF.type, LKG.DiaryPage))
        graph.add((_uri(page.uid), RDFS.label, Literal(page.label)))
    for obs in entry.observations:
        obs_node = _add_observation(graph, obs)
        if obs_node is not None:
            graph.add((node, LKG.containsObservation, obs_node))
    for event in entry.travel_events:
        _add_travel_event(graph, node, event)
    for person in entry.persons:
        graph.add((node, LKG.mentionsPerson, _add_person(graph, person)))


def build_graph(result: "ExtractionResult") -> Graph:
    """Build an rdflib Graph. Only dated entries are emitted (SHACL requires a
    single xsd:date entryDate); undated entries are skipped and logged."""
    graph = Graph()
    _bind(graph)
    skipped = 0
    for entry in result.entries:
        if not entry.entry_date:
            skipped += 1
            continue
        _add_entry(graph, entry)
    if skipped:
        logger.warning("skipped %d undated entries (SHACL entryDate requirement)", skipped)
    return graph


def serialize_turtle(graph: Graph, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(path), format="turtle")
    logger.info("wrote %d triples to %s", len(graph), path)
    return path
