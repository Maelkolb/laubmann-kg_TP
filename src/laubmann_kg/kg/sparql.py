"""Competency-question SPARQL queries over the sample graph."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from rdflib import Graph

logger = logging.getLogger(__name__)

PREFIXES = """
PREFIX lkg:  <https://lkg.example.org/ontology#>
PREFIX dwc:  <http://rs.tdwg.org/dwc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

# Keyed by the competency-question id in docs/competency_questions.md.
QUERIES: dict[str, str] = {
    "CQ1_species_frequency": PREFIXES + """
        SELECT ?vernacular (COUNT(?obs) AS ?n) WHERE {
            ?obs a lkg:ObservationEvent ; lkg:observedTaxon ?t .
            ?t lkg:vernacularNameDE ?vernacular .
        } GROUP BY ?vernacular ORDER BY DESC(?n)
    """,
    "CQ2_observations_by_date": PREFIXES + """
        SELECT ?date (COUNT(?obs) AS ?n) WHERE {
            ?entry a lkg:DiaryEntry ; lkg:entryDate ?date ;
                   lkg:containsObservation ?obs .
        } GROUP BY ?date ORDER BY ?date
    """,
    "CQ3_observations_at_place": PREFIXES + """
        SELECT ?place ?vernacular WHERE {
            ?obs a lkg:ObservationEvent ; lkg:observedAt ?p ;
                 lkg:observedTaxon ?t .
            ?p rdfs:label ?place .
            ?t lkg:vernacularNameDE ?vernacular .
        } ORDER BY ?place
    """,
    "CQ4_auditory_observations": PREFIXES + """
        SELECT ?vernacular ?callType ?transcription WHERE {
            ?obs a lkg:ObservationEvent ; lkg:observedTaxon ?t ;
                 lkg:hasEvidence ?e .
            ?e a lkg:BirdCall .
            OPTIONAL { ?e lkg:callType ?callType }
            OPTIONAL { ?e lkg:callTranscription ?transcription }
            ?t lkg:vernacularNameDE ?vernacular .
        }
    """,
    "CQ5_unresolved_taxa": PREFIXES + """
        SELECT DISTINCT ?vernacular WHERE {
            ?t a lkg:Taxon ; lkg:vernacularNameDE ?vernacular .
            FILTER NOT EXISTS { ?t lkg:scientificName ?s }
        } ORDER BY ?vernacular
    """,
    "CQ6_provenance": PREFIXES + """
        SELECT ?obs ?entryDate ?page ?run WHERE {
            ?obs a lkg:ObservationEvent ; lkg:derivedFromEntry ?entry .
            ?entry lkg:entryDate ?entryDate .
            OPTIONAL { ?entry lkg:hasPage ?page }
            OPTIONAL { ?obs prov:wasGeneratedBy ?run }
        } LIMIT 25
    """,
    # Records that state their OWN locality (lkg:hasLocality) vs. records that
    # inherit the entry place: ?ownLocality is bound only for the former.
    "CQ7_own_locality_vs_entry_place": PREFIXES + """
        SELECT ?vernacular ?effectivePlace ?ownLocality ?entryPlace WHERE {
            ?obs a lkg:ObservationEvent ; lkg:observedTaxon ?t ;
                 lkg:derivedFromEntry ?entry .
            ?t lkg:vernacularNameDE ?vernacular .
            OPTIONAL { ?obs lkg:observedAt ?p . ?p rdfs:label ?effectivePlace }
            OPTIONAL { ?obs lkg:hasLocality ?l . ?l rdfs:label ?ownLocality }
            OPTIONAL { ?entry lkg:entryPlace ?ep . ?ep rdfs:label ?entryPlace }
        } ORDER BY ?vernacular
    """,
    # Explicit absence records ("keine Störche mehr"): occurrenceStatus absent.
    "CQ8_absence_records": PREFIXES + """
        SELECT ?vernacular ?entryDate ?place ?notes WHERE {
            ?obs a lkg:ObservationEvent ; dwc:occurrenceStatus "absent" ;
                 lkg:observedTaxon ?t ; lkg:derivedFromEntry ?entry .
            ?t lkg:vernacularNameDE ?vernacular .
            ?entry lkg:entryDate ?entryDate .
            OPTIONAL { ?obs lkg:observedAt ?p . ?p rdfs:label ?place }
            OPTIONAL { ?obs lkg:verbatimNotes ?notes }
        } ORDER BY ?entryDate ?vernacular
    """,
}


def run_query(graph: Graph, key: str) -> list[dict]:
    result = graph.query(QUERIES[key])
    rows = []
    for row in result:
        rows.append({str(var): (row[var].toPython() if row[var] is not None else None)
                     for var in result.vars})
    return rows


def run_all(graph: Graph, keys: Iterable[str] | None = None) -> dict[str, list[dict]]:
    return {key: run_query(graph, key) for key in (keys or QUERIES.keys())}


def load_graph(ttl_path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")
    return graph
