# Data Model

The knowledge graph conforms to `ontologies/laubmann.ttl` (v0.3.0, namespace
`https://lkg.example.org/ontology#`, prefix `lkg:`). Instances live under
`https://lkg.example.org/data/` (prefix `data:`). The Python contract is
`src/laubmann_kg/kg/model.py`; `kg/rdf.py` maps it onto triples and
`ontologies/shacl_shapes.ttl` validates the result **without inference** (every
superclass a shape relies on is materialised at emit time). Enumerated values
are defined once in `normalization/vocabularies.py` and mirrored as SKOS
concept schemes in `ontologies/controlled_vocabularies.ttl`.

Extraction is LLM-based (`extraction/llm_observations.py`; prompt in
`prompts/observation_extraction.md`); the offline rule-based backend is a
network-free test double. Nothing is inferred from prose in the emitter: a
value appears in the graph only when the extractor set it.

Diagrams (Mermaid, render with any Mermaid tool or paste into Mermaid Chart):
`docs/kg_structure.mmd` (classes, datatype properties, predicates as emitted)
and `docs/pipeline.mmd` (stages and where each decision is made).

## Node types and keys

| Class | IRI | Key |
|---|---|---|
| `lkg:DiaryEntry` (⊑ rico:Record, dwc:Event) | `data:entry_<entry_uid>` | corpus `entry_uid` |
| `lkg:DiaryPage` / `lkg:DiaryVolume` | `data:page_<page_uid>` / `data:volume_NN` | corpus |
| `lkg:SourceRegion` (⊑ oa:Annotation) | `data:region_<region_uid>` | corpus |
| `lkg:ObservationEvent` (⊑ dwc:Occurrence) | `data:obs_<sha1(entry_uid|vernacular|index)>` | derived |
| `lkg:Taxon` (⊑ dwc:Taxon) | `data:taxon_<sha1(vernacular lower)>` | German vernacular as written |
| `lkg:Place` (⊑ geo:SpatialThing, dcterms:Location) | `data:place_<sha1(canonical or verbatim)>` | place name |
| `lkg:Habitat` (⊑ skos:Concept, **not** a Place) | `data:habitat_<sha1(label)>` | habitat label |
| `lkg:ObservationEvidence` / `lkg:BirdCall` | `data:evidence_<obs>_<kind>_<i>` | per observation |
| `lkg:BehaviourNote` | `data:behaviour_<obs>_<sha1(label)>` | per observation |
| `lkg:Person` (⊑ schema:Person) | `data:person_<sha1(name lower)>` | name; the diarist is `person_c6b2ff6250e5` |
| `lkg:TravelEvent` (⊑ dwc:Event) / `lkg:TravelLeg` | `data:travel_<entry>_<i>` / `data:leg_…` | per entry |
| `lkg:WeatherReport` | `data:weather_<entry_uid>` | one per entry |
| `prov:Activity` (run) / `prov:SoftwareAgent` / `prov:Entity` (prompt) | `data:run_<sha1(model|prompt_sha|started)>` / `data:agent_<model>` / `data:prompt_<sha[:12]>` | `ExtractionResult.provenance` |

## Provenance chain

```
ObservationEvent
  ├─ lkg:derivedFromEntry (⊑ prov:wasDerivedFrom) → DiaryEntry
  │     ├─ lkg:hasPage → DiaryPage ─ dcterms:isPartOf → DiaryVolume
  │     ├─ lkg:hasVolume → DiaryVolume
  │     ├─ lkg:hasSourceRegion → SourceRegion (dcterms:isPartOf the page)
  │     ├─ lkg:entryPlace → Place            (entry's main locality)
  │     ├─ lkg:entryDate / lkg:entryDateEnd / dwc:eventDate / dwc:verbatimEventDate
  │     ├─ lkg:entryKind, lkg:datePlausible, lkg:dateNote (⊑ skos:note), dcterms:identifier
  │     └─ lkg:mentionsPerson → Person, lkg:hasWeather → WeatherReport, lkg:containsTravelEvent → TravelEvent
  ├─ lkg:observedTaxon (⊑ dwciri:toTaxon) → Taxon
  ├─ lkg:observedAt → Place                  (EFFECTIVE place: own locality, else entry place)
  ├─ lkg:hasLocality → Place                 (only when the record states its OWN locality; + dwc:verbatimLocality)
  ├─ lkg:hasEvidence → ObservationEvidence / BirdCall  (0–4; lkg:evidenceKind → lkg:evidence_*)
  ├─ lkg:hasBehaviour → BehaviourNote        (+ dwc:behavior literal)
  ├─ lkg:hasHabitat / dwciri:habitat → Habitat (+ dwc:habitat literal)
  ├─ lkg:observedBy / dwciri:recordedBy → Person   (diarist by default; never fabricated for 3rd-party records)
  └─ prov:wasGeneratedBy → run (prov:Activity ─ prov:wasAssociatedWith → SoftwareAgent, prov:used → prompt)
```

TravelEvents and WeatherReports carry `prov:wasGeneratedBy` too. When
`ExtractionResult.provenance` is empty (hand-built results) no run node and no
`wasGeneratedBy` are emitted.

## Observation detail (all optional unless noted)

| model.py field | Predicate(s) | Notes |
|---|---|---|
| `verbatim_notes` (required) | `lkg:verbatimNotes`@de | source passage |
| `occurrence_status` | `dwc:occurrenceStatus` present\|absent | on the **observation** (moved off the evidence node) |
| `individual_count` | `lkg:individualCount` + `dwc:individualCount` (xsd:integer ≥ 0) | 0 only with `absent` |
| `count_min` / `count_max` | `lkg:individualCountMin` / `Max` | ranges ("3-4") |
| `count_qualifier` | `lkg:countQualifier` | exact\|minimum\|approximate\|plural-unspecified |
| `sex`, `life_stage`, `vitality` | `dwc:sex`, `dwc:lifeStage`, `dwc:vitality` | vocab values |
| `breeding_evidence` | `lkg:breedingEvidence` (+ `dwc:reproductiveCondition "breeding"` for confirmed/probable) | atlas categories |
| `movement_kind`, `flight_direction` | `lkg:movementKind`, `lkg:flightDirection`@de | direction as written |
| `identification_qualifier` | `dwc:identificationQualifier` | the diarist's hedge as written |
| `event_date`, `event_time` | `dwc:eventDate` (xsd:date; falls back to the entry date), `dwc:eventTime` "HH:MM" | |
| `record_type`, `literature_citation` | `lkg:recordType`, derived `dwc:basisOfRecord`, `dwc:associatedReferences` | see ontology comment on recordType |
| `evidence[]` | BirdCall: `lkg:callType` (always), `lkg:callTranscription` only when written | no placeholder |
| `flags` | not emitted (QA only) | |

Taxon: `lkg:vernacularNameDE`/`rdfs:label`/`dwc:vernacularName`@de,
`lkg:scientificName`+`dwc:scientificName` or `skos:note` (unresolved),
`dwc:taxonRank`, `lkg:isBird`, match provenance (`lkg:matchMethod`,
`lkg:matchConfidence`, `lkg:gbifMatchType`) and the GBIF link as
`skos:exactMatch` / `closeMatch` (fuzzy or LLM-mediated) / `broadMatch`
(HIGHERRANK) plus `dwc:taxonID` (not for broad matches).

Place: `rdfs:label`@de (canonical), `lkg:verbatimLocality`, `lkg:placeKind`,
`geo:lat`/`geo:long` co-emitted as `dwc:decimalLatitude`/`Longitude` +
`dwc:geodeticDatum "WGS84"`.

## Corpus → ontology mapping

| Corpus field (entries.csv) | KG target |
|---|---|
| `entry_uid`, `entry_id` | `data:entry_<uid>`, `dcterms:identifier` |
| `date_norm` / `date_raw` | `lkg:entryDate` (`xsd:date`, model-corrected), `dwc:verbatimEventDate`; multi-day → `lkg:entryDateEnd` and `dwc:eventDate "start/end"` |
| `volume`, `page_uid`, `page_id`, `scan`, `region_uid` | `lkg:hasVolume`, `lkg:hasPage` (+ `dcterms:identifier`, `dcterms:isPartOf`), `lkg:hasSourceRegion` |
| `location_raw` | fallback for `lkg:entryPlace` (LLM backend replaces it with the model's reading) |
| `text_clean` | `lkg:rawText`; extraction input |

Linked images join by `entry_uid`: a `multimodal` region with
`entry_uid == observation's entry` becomes a DwC-A multimedia record for that
entry's event.

## Ontology → Darwin Core Archive mapping

Event-core sampling-event archive (`configs/dwca.yaml`), joined by `eventID`:

| DwC-A file | rowType | Source |
|---|---|---|
| `event.txt` (core) | Event | one row per dated `DiaryEntry`; `eventID = entry_uid`; locality/coordinates from the model-read entry place, `verbatimLocality` = header, weather in `eventRemarks`/`dynamicProperties` |
| `occurrence.txt` | Occurrence | one row per `ObservationEvent`; `occurrenceID = obs uid`; kingdom/class/taxonRank/taxonID, `individualCount` (0 for absences), `organismQuantity(+Type)` for ranges, `occurrenceStatus`, sex/lifeStage/reproductiveCondition/vitality/behavior, identificationQualifier, own locality + eventDate/eventTime, habitat, provenance-aware `recordedBy` |
| `measurementorfact.txt` | ExtendedMeasurementOrFact (OBIS eMoF, keyed on `occurrenceID`) | evidence kind, call type, count qualifier, breeding evidence, movement kind per observation; `measurementTypeID`/`measurementValueID` point at the SKOS schemes/concepts; `measurementMethod` from run provenance |
| `multimedia.txt` | Multimedia (GBIF Simple Multimedia) | one row per `multimodal` region joined on `entry_uid` |

## Competency queries

`kg/sparql.py` ships CQ1–CQ8 (species frequency, by date, by place, auditory,
unresolved taxa, provenance incl. run, own locality vs. entry place, absence
records).
