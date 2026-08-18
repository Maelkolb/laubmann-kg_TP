# Competency Questions

The knowledge graph is designed to answer the questions below. Each maps to a
SPARQL query in `src/laubmann_kg/kg/sparql.py` (`QUERIES[...]`), runnable over the
exported Turtle graph (ontology 0.4.0 vocabulary: `dwc:vernacularName`,
`dwc:eventDate`, `dcterms:isPartOf`, `lkg:evidenceKind`, …). Answerability is
reported against the sample builds in `STATUS.md`.

| ID | Question | Query key | Status |
|---|---|---|---|
| CQ1 | Which species were observed, and how often? | `CQ1_species_frequency` | answerable |
| CQ2 | How many observations fall on each date? | `CQ2_observations_by_date` | answerable |
| CQ3 | Which species were seen at a given place? | `CQ3_observations_at_place` | answerable |
| CQ4 | Which observations are auditory, and what call type / transcription was noted? | `CQ4_auditory_observations` | answerable |
| CQ5 | Which taxa remain unresolved to a scientific name? | `CQ5_unresolved_taxa` | answerable |
| CQ6 | What is the source (entry date, page, volume, extraction run) of each observation? | `CQ6_provenance` | answerable |
| CQ7 | Which records state their own locality, which inherit the entry place? | `CQ7_own_locality_vs_entry_place` | answerable |
| CQ8 | Which records are explicit absences ("keine Störche mehr")? | `CQ8_absence_records` | answerable |
| CQ9 | How many records per family (GBIF classification)? | `CQ9_observations_by_family` | answerable for linked taxa |
| CQ10 | Which taxa were noted in which habitat? | `CQ10_taxa_by_habitat` | answerable |
| CQ11 | Which persons appear in which role (companion, source, collector, cited author)? | `CQ11_persons_by_role` | answerable |

## Partial

- **Place coordinates** are partial: only gazetteer-seeded (and post-hoc
  georeferenced) localities carry `geo:lat`/`geo:long`/`gsp:asWKT`. CQ3 answers
  by locality label regardless.
- **Higher taxonomy** (CQ9) is only present for taxa linked to the GBIF backbone
  (EXACT/FUZZY/HIGHERRANK matches, or reviewed names whose match is cached).
- **Travel questions** ("which route on day X?") are answerable from
  `lkg:TravelEvent`/`lkg:TravelLeg` when the model extracted legs; no dedicated
  CQ is shipped yet.

## Running the queries

```python
from laubmann_kg.kg.sparql import load_graph, run_query
graph = load_graph("data/exports/rdf/laubmann_sample.ttl")
for row in run_query(graph, "CQ1_species_frequency"):
    print(row)
```
