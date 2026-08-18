# Data Model

The knowledge graph conforms to `ontologies/laubmann.ttl` (v0.4.0, namespace
`https://w3id.org/laubmann-kg/ontology#`, prefix `lkg:`). Instances live under
`https://w3id.org/laubmann-kg/data/` (prefix `data:`). The Python contract is
`src/laubmann_kg/kg/model.py`; `kg/rdf.py` maps it onto triples and
`ontologies/shacl_shapes.ttl` validates the result **without inference** (shapes
target the concrete classes; the grouping superclasses are not asserted in the
data). Enumerated values are defined once in `normalization/vocabularies.py` and
mirrored as SKOS concept schemes in `ontologies/controlled_vocabularies.ttl`.
`tests/test_ontology_alignment.py` enforces, in both directions, that the
emitter, the ontology, the shapes and the JSON-LD context use the same terms.

Extraction is LLM-based (`extraction/llm_observations.py`; prompt in
`prompts/observation_extraction.md`); the offline rule-based backend is a
network-free test double. Nothing is inferred from prose in the emitter: a
value appears in the graph only when the extractor set it.

Diagrams (Mermaid, render with any Mermaid tool or paste into Mermaid Chart):
`docs/kg_structure.mmd` (classes, datatype properties, predicates as emitted)
and `docs/pipeline.mmd` (stages and where each decision is made).
Human-readable ontology docs: `docs/ontology/index.html` (pyLODE).

## Design principles (0.4.0)

- **Darwin-Core-first.** Wherever a `dwc:`/`dwciri:`, DCTERMS, PROV-O, SKOS,
  GeoSPARQL or schema.org term exists, the graph uses that term alone;
  `lkg:` carries only project-specific meaning (record type, count qualifier and
  ranges, breeding evidence, movement, evidence kind, entry kind, weather,
  travel, mention roles). No `lkg:` twin of a standard term is emitted.
- **Three grouping superclasses** structure the hierarchy (declared, never
  asserted as `rdf:type` in the data):
  `lkg:ArchivalUnit` ⊑ rico:Record — DiaryVolume, DiaryPage, DiaryEntry, SourceRegion;
  `lkg:EntryRecord` ⊑ prov:Entity — Observation, TravelEvent, WeatherReport (what the
  model reads out of one entry); `lkg:RecordDetail` — Vocalisation, TravelLeg.
  Taxon, Place and Person are shared referents; habitats are `skos:Concept`s.
- **Explicit partonomy.** Containment properties (`lkg:containsObservation`,
  `lkg:containsTravelEvent`, `lkg:hasWeather`, `lkg:hasLeg`, `lkg:hasVocalisation`)
  are sub-properties of `dcterms:hasPart`; every child node carries
  `dcterms:isPartOf`.
- **Flat where a node adds nothing.** Behaviour = `dwc:behavior` literals;
  evidence kinds = `lkg:evidenceKind` concept links on the observation;
  only vocalisations, weather reports and travel legs stay nodes.

## Node types and keys

| Class | IRI | Key |
|---|---|---|
| `lkg:DiaryVolume` (⊑ ArchivalUnit) | `data:volume_NN` | corpus |
| `lkg:DiaryPage` (⊑ ArchivalUnit; `dcterms:isPartOf` volume) | `data:page_<page_uid>` | corpus |
| `lkg:DiaryEntry` (⊑ ArchivalUnit, dwc:Event; `dcterms:isPartOf` page or volume) | `data:entry_<entry_uid>` | corpus `entry_uid` |
| `lkg:SourceRegion` (⊑ ArchivalUnit; `dcterms:isPartOf` page) | `data:region_<region_uid>` | corpus |
| `lkg:Observation` (⊑ EntryRecord, dwc:Occurrence) | `data:obs_<sha1(entry_uid|vernacular|index)>` | derived |
| `lkg:TravelEvent` (⊑ EntryRecord, dwc:Event) / `lkg:TravelLeg` (⊑ RecordDetail) | `data:travel_<entry>_<i>` / `data:leg_…` | per entry |
| `lkg:WeatherReport` (⊑ EntryRecord) | `data:weather_<entry_uid>` | one per entry today (several allowed) |
| `lkg:Vocalisation` (⊑ RecordDetail; `dcterms:isPartOf` observation) | `data:vocalisation_<obs>_<i>` | per call |
| `lkg:Taxon` (⊑ dwc:Taxon) | `data:taxon_<sha1(vernacular lower)>` | German vernacular as written |
| `lkg:Place` (⊑ geo:SpatialThing, dcterms:Location) | `data:place_<sha1(canonical or verbatim)>` | place name |
| habitat `skos:Concept` in `lkg:habitatScheme` (**not** a class, **not** a Place) | `data:habitat_<sha1(label)>` | habitat label, shared across observations |
| `lkg:Person` (⊑ schema:Person) | `data:person_<sha1(name lower)>` | name; the diarist is `person_c6b2ff6250e5` |
| `prov:Activity` (run) / `prov:SoftwareAgent` / `prov:Entity` (prompt) | `data:run_<sha1(model|prompt_sha|started)>` / `data:agent_<model>` / `data:prompt_<sha[:12]>` | `ExtractionResult.provenance` |

## Provenance / partonomy chain

```
Observation  (dwc:Occurrence)
  ├─ dcterms:isPartOf + prov:wasDerivedFrom → DiaryEntry   (dwc:Event; lkg:containsObservation back)
  │     ├─ dcterms:isPartOf → DiaryPage ─ dcterms:isPartOf → DiaryVolume   (page unknown: entry → volume)
  │     ├─ lkg:hasSourceRegion → SourceRegion ─ dcterms:isPartOf → DiaryPage
  │     ├─ lkg:entryPlace → Place            (entry's main locality)
  │     ├─ dwc:eventDate (xsd:date | "start/end"), dwc:verbatimEventDate, dwc:fieldNotes (entry text)
  │     ├─ lkg:entryKind, lkg:datePlausible, skos:note (date note), dcterms:identifier
  │     ├─ lkg:mentionsPerson → Person  + role edge lkg:mentionsCompanion|Source|Collector|CitedAuthor|Other
  │     ├─ lkg:hasWeather → WeatherReport   (dcterms:isPartOf + prov:wasDerivedFrom the entry)
  │     └─ lkg:containsTravelEvent → TravelEvent ─ lkg:hasLeg → TravelLeg (dcterms:isPartOf the event)
  ├─ lkg:observedTaxon (⊑ dwciri:toTaxon) → Taxon
  ├─ lkg:observedAt → Place                  (EFFECTIVE place: own locality, else entry place)
  ├─ lkg:hasLocality → Place                 (only when the record states its OWN locality; + dwc:verbatimLocality)
  ├─ lkg:evidenceKind → lkg:evidence_visual|auditory|nest|specimen   (0–4 concepts)
  ├─ lkg:hasVocalisation → Vocalisation      (lkg:callType, lkg:callTranscription; dcterms:isPartOf back)
  ├─ dwc:behavior "…"@de                     (literals, no node)
  ├─ dwciri:habitat → habitat concept        (+ dwc:habitat literal)
  ├─ dwciri:recordedBy → Person              (diarist by default; never fabricated for 3rd-party records)
  └─ prov:wasGeneratedBy → run (prov:Activity ─ prov:wasAssociatedWith → SoftwareAgent, prov:used → prompt)
```

When `ExtractionResult.provenance` is empty (hand-built results) no run node
and no `wasGeneratedBy` are emitted.

## Observation detail (all optional unless noted)

| model.py field | Predicate(s) | Notes |
|---|---|---|
| `verbatim_notes` (required) | `lkg:verbatimNotes`@de | source passage |
| `occurrence_status` | `dwc:occurrenceStatus` present\|absent | |
| `individual_count` | `dwc:individualCount` (xsd:integer ≥ 0) | 0 only with `absent` |
| `count_min` / `count_max` | `lkg:individualCountMin` / `Max` | ranges ("3-4") |
| `count_qualifier` | `lkg:countQualifier` | exact\|minimum\|approximate\|plural-unspecified |
| `sex`, `life_stage`, `vitality` | `dwc:sex`, `dwc:lifeStage`, `dwc:vitality` | vocab values |
| `breeding_evidence` | `lkg:breedingEvidence` (+ `dwc:reproductiveCondition "breeding"` for confirmed/probable, via `vocabularies.reproductive_condition`) | atlas categories |
| `movement_kind`, `flight_direction` | `lkg:movementKind`, `lkg:flightDirection`@de | direction as written |
| `identification_qualifier` | `dwc:identificationQualifier` | the diarist's hedge as written |
| `event_date`, `event_time` | `dwc:eventDate` (xsd:date; falls back to the entry date), `dwc:eventTime` "HH:MM" | |
| `record_type`, `observer`, `literature_citation` | `lkg:recordType`, derived `dwc:basisOfRecord`, `dwciri:recordedBy`, `dwc:associatedReferences` | see ontology comment on recordType |
| `evidence[]` | `lkg:evidenceKind` concept per kind; calls additionally a `lkg:Vocalisation` node (`lkg:callType` always, `lkg:callTranscription` only when written) | no placeholder |
| `behaviour[]` | `dwc:behavior`@de literals | |
| `habitat` | `dwciri:habitat` → shared concept + `dwc:habitat` literal | |
| `flags` | not emitted (QA only) | |

Taxon: `rdfs:label` + `dwc:vernacularName`@de, `dwc:scientificName` or
`skos:note` (unresolved), `dwc:taxonRank`, `lkg:isBird`, GBIF classification
`dwc:kingdom/phylum/class/order/family/genus` (from the cached `species/match`
response, `Taxon.higher_taxonomy`), match provenance (`lkg:matchMethod`,
`lkg:matchConfidence`, `lkg:gbifMatchType`) and the GBIF link as
`skos:exactMatch` / `closeMatch` (fuzzy or LLM-mediated) / `broadMatch`
(HIGHERRANK) plus `dwc:taxonID` (not for broad matches).

Place: `rdfs:label`@de (canonical), `dwc:verbatimLocality`, `lkg:placeKind`,
`geo:lat`/`geo:long` co-emitted as `dwc:decimalLatitude`/`Longitude` +
`dwc:geodeticDatum "WGS84"` + `gsp:asWKT "POINT(lon lat)"^^gsp:wktLiteral`.

Person: `rdfs:label`, `schema:name`, `owl:sameAs` (Wikidata). The role is on the
mention edge of each entry, not on the shared node.

## Corpus → ontology mapping

| Corpus field (entries.csv) | KG target |
|---|---|
| `entry_uid`, `entry_id` | `data:entry_<uid>`, `dcterms:identifier` |
| `date_norm` / `date_raw` | `dwc:eventDate` (`xsd:date`, model-corrected; multi-day → `"start/end"`), `dwc:verbatimEventDate` |
| `volume`, `page_uid`, `page_id`, `scan`, `region_uid` | `dcterms:isPartOf` page → volume (+ `dcterms:identifier` on the page), `lkg:hasSourceRegion` |
| `location_raw` | fallback for `lkg:entryPlace` (LLM backend replaces it with the model's reading) |
| `text_clean` | `dwc:fieldNotes`; extraction input |

Linked images join by `entry_uid`: a `multimodal` region with
`entry_uid == observation's entry` becomes a DwC-A multimedia record for that
entry's event.

## Ontology → Darwin Core Archive mapping

Event-core sampling-event archive (`configs/dwca.yaml`), joined by `eventID`:

| DwC-A file | rowType | Source |
|---|---|---|
| `event.txt` (core) | Event | one row per dated `DiaryEntry`; `eventID = entry_uid`; locality/coordinates from the model-read entry place, `verbatimLocality` = header, weather in `eventRemarks`/`dynamicProperties` |
| `occurrence.txt` | Occurrence | one row per `Observation`; `occurrenceID = obs uid`; kingdom/class/order/family (GBIF classification, is_bird fallback), taxonRank/taxonID, `individualCount` (0 for absences), `organismQuantity(+Type)` for ranges, `occurrenceStatus`, sex/lifeStage/reproductiveCondition/vitality/behavior, identificationQualifier, own locality + eventDate/eventTime, habitat, provenance-aware `recordedBy` |
| `measurementorfact.txt` | ExtendedMeasurementOrFact (OBIS eMoF, keyed on `occurrenceID`) | evidence kind, call type, count qualifier, breeding evidence, movement kind per observation; `measurementTypeID`/`measurementValueID` point at the SKOS schemes/concepts; `measurementMethod` from run provenance |
| `multimedia.txt` | Multimedia (GBIF Simple Multimedia) | one row per `multimodal` region joined on `entry_uid` |

## Competency queries

`kg/sparql.py` ships CQ1–CQ11 (species frequency, by date, by place, auditory
incl. vocalisation detail, unresolved taxa, provenance chain incl. page/volume/run,
own locality vs. entry place, absence records, observations by family, taxa by
habitat, persons by role).
