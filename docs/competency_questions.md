# Competency Questions

The knowledge graph is designed to answer the questions below. Each maps to a
SPARQL query in `src/laubmann_kg/kg/sparql.py` (`QUERIES[...]`), runnable over the
exported Turtle graph. Answerability is reported against the Vol. 2 sample in
`STATUS.md`.

| ID | Question | Query key | Status |
|---|---|---|---|
| CQ1 | Which species were observed, and how often? | `CQ1_species_frequency` | answerable |
| CQ2 | How many observations fall on each date? | `CQ2_observations_by_date` | answerable |
| CQ3 | Which species were seen at a given place? | `CQ3_observations_at_place` | answerable |
| CQ4 | Which observations are auditory, and what call was noted? | `CQ4_auditory_observations` | answerable |
| CQ5 | Which taxa remain unresolved to a scientific name? | `CQ5_unresolved_taxa` | answerable |
| CQ6 | What is the source (entry date, page) of each observation? | `CQ6_provenance` | answerable |

## Blocked / partial

- **Taxon IRIs and cross-dataset alignment (GBIF/Avibase/Wikidata).** Blocked on
  the Vol. 35 index-linker `links_long` table (see `INTERFACES.md`). The resolver
  interface is in place; until the table is delivered, taxa carry scientific
  names from the seed gazetteer but no external IRIs.
- **Travel events and routes** (`lkg:TravelEvent`, `lkg:TravelLeg`,
  `lkg:Route`, `lkg:TimeEstimate`). The ontology models these and the SHACL
  shapes validate them, but reliable extraction of itineraries from free text is
  future work; not populated in the sample.
- **Place coordinates** are partial: only gazetteer-seeded localities carry
  `geo:lat`/`geo:long`. CQ3 answers by locality label regardless.

## Running the queries

```python
from laubmann_kg.kg.sparql import load_graph, run_query
graph = load_graph("data/exports/rdf/laubmann_sample.ttl")
for row in run_query(graph, "CQ1_species_frequency"):
    print(row)
```
