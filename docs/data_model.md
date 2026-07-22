# Data Model

The knowledge graph conforms to `ontologies/laubmann.ttl` (namespace
`https://lkg.example.org/ontology#`, prefix `lkg:`). Instances live under
`https://lkg.example.org/data/` (prefix `data:`). This document maps the corpus
input to the ontology and to the Darwin Core Archive output.

## Provenance chain

Every observation is traceable to its source, following the frozen corpus
contract (see `INTERFACES.md`):

```
ObservationEvent
  └─ lkg:derivedFromEntry → DiaryEntry (entry_uid)
        └─ lkg:hasPage    → DiaryPage  (page_uid → volume, page_id)
        └─ lkg:hasVolume  → DiaryVolume
  └─ lkg:observedTaxon    → Taxon
  └─ lkg:observedAt       → Place
  └─ lkg:hasEvidence      → ObservationEvidence / BirdCall
  └─ lkg:hasBehaviour     → BehaviourNote
```

Linked images join by `entry_uid`: a `multimodal` region with
`entry_uid == observation's entry` becomes a DwC-A multimedia record for that
entry's event.

## Corpus → ontology mapping

| Corpus field (entries.csv) | KG target |
|---|---|
| `entry_uid` | `data:entry_<uid>` (`lkg:DiaryEntry`), primary key of every observation |
| `date_norm` / `date_raw` | `lkg:entryDate` (`xsd:date`), `dwc:verbatimEventDate` |
| `volume` | `lkg:hasVolume` → `lkg:DiaryVolume` |
| `page_uid`, `page_id`, `scan` | `lkg:hasPage` → `lkg:DiaryPage` |
| `location_raw` | `lkg:observedAt` → `lkg:Place` (+ seeded `geo:lat`/`geo:long`) |
| `text_clean` | `lkg:rawText`; extraction input |

## Extraction → ontology mapping

Extraction is rule-based and deterministic (`extraction/observations.py`):

| Extracted signal | KG target |
|---|---|
| German bird name (gazetteer match) | `lkg:Taxon` with `lkg:vernacularNameDE`; `lkg:scientificName` when resolved, else `skos:note` (uncertainty) |
| explicit number near the mention | `lkg:individualCount` (`xsd:integer` ≥ 1), `lkg:countQualifier` `exact`/`approximate` |
| plural cue ("einige", "mehrere") | `lkg:countQualifier` `plural-unspecified` |
| vocalisation cue ("singt", "ruft") | `lkg:BirdCall` with `lkg:callType`, `lkg:callTranscription` |
| nest/brood cue | `lkg:ObservationEvidence` (nest) + `lkg:BehaviourNote` (breeding) |
| collection cue ("erlegt") | `lkg:ObservationEvidence` (specimen) → DwC `PreservedSpecimen` |
| default | `lkg:ObservationEvidence` (visual) |
| source sentence | `lkg:verbatimNotes` |

Uncertainty is never invented: an unmatched or ambiguous name yields a Taxon
with a `skos:note` and no scientific name, and observations carry the verbatim
German term. Taxon IRIs are only asserted when a resolver supplies one.

## Ontology → Darwin Core Archive mapping

Event-core sampling-event archive (`configs/dwca.yaml`), joined by `eventID`:

| DwC-A file | rowType | Source |
|---|---|---|
| `event.txt` (core) | Event | one row per dated `DiaryEntry`; `eventID = entry_uid` |
| `occurrence.txt` | Occurrence | one row per `ObservationEvent`; `occurrenceID = obs uid` |
| `measurementorfact.txt` | MeasurementOrFact | evidence kind, call type, count qualifier per observation |
| `multimedia.txt` | Multimedia (GBIF) | one row per `multimodal` region joined on `entry_uid` |
