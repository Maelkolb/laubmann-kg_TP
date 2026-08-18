# Ontology Mapping

Alignment of the project terms (`lkg:`, `ontologies/laubmann.ttl` v0.4.0) with
external vocabularies (v0.4.1 adds `skos:altLabel` / `dwc:verbatimIdentification` for entity resolution). Since 0.4.0 the graph is **Darwin-Core-first**: where a
standard term exists it is emitted *alone* ("direct" below); `lkg:` terms are
declared as sub-classes/sub-properties of external terms only where that adds
meaning ("axiom"). No `lkg:` twin of a standard term remains.

## Classes

| lkg class | External | How |
|---|---|---|
| `lkg:ArchivalUnit` (grouping) | `rico:Record` | axiom; not asserted in the data |
| `lkg:DiaryVolume`, `lkg:DiaryPage`, `lkg:SourceRegion` | `lkg:ArchivalUnit` | axiom |
| `lkg:DiaryEntry` | `lkg:ArchivalUnit`, `dwc:Event` | axiom |
| `lkg:EntryRecord` (grouping) | `prov:Entity` | axiom; not asserted in the data |
| `lkg:Observation` | `lkg:EntryRecord`, `dwc:Occurrence` | axiom (renamed from `ObservationEvent`) |
| `lkg:TravelEvent` | `lkg:EntryRecord`, `dwc:Event` | axiom |
| `lkg:WeatherReport` | `lkg:EntryRecord` | axiom |
| `lkg:RecordDetail` (grouping) | — | not asserted in the data |
| `lkg:Vocalisation`, `lkg:TravelLeg` | `lkg:RecordDetail` | axiom (`Vocalisation` renamed from `BirdCall`) |
| `lkg:Place` | `geo:SpatialThing`, `dcterms:Location` | axiom |
| `lkg:Taxon` | `dwc:Taxon` | axiom |
| `lkg:Person` | `schema:Person` | axiom; `schema:name` direct |
| habitat nodes | `skos:Concept` in `lkg:habitatScheme` | direct (no lkg class since 0.4.0) |
| run / agent / prompt | `prov:Activity`, `prov:SoftwareAgent`, `prov:Entity` | direct |

## Properties

| Meaning | Term in the data | How |
|---|---|---|
| observation → taxon | `lkg:observedTaxon` | ⊑ `dwciri:toTaxon` (axiom) |
| effective / own place | `lkg:observedAt`, `lkg:hasLocality` (+ `dwc:verbatimLocality` literal) | project terms; direct literal |
| observer | `dwciri:recordedBy` | direct (was `lkg:observedBy`) |
| record part of / derived from entry | `dcterms:isPartOf`, `prov:wasDerivedFrom` | direct on Observation, TravelEvent, WeatherReport (was `lkg:derivedFromEntry`) |
| entry → records / details | `lkg:containsObservation`, `lkg:containsTravelEvent`, `lkg:hasWeather`, `lkg:hasLeg`, `lkg:hasVocalisation` | ⊑ `dcterms:hasPart` (axiom); child carries `dcterms:isPartOf` |
| entry → page → volume, region → page | `dcterms:isPartOf` | direct (was `lkg:hasPage`/`hasVolume`) |
| entry → layout region | `lkg:hasSourceRegion` | project term |
| entry mentions person | `lkg:mentionsPerson` ⊑ `schema:mentions`; role edges `lkg:mentionsCompanion|Source|Collector|CitedAuthor|Other` ⊑ `lkg:mentionsPerson` | axiom; both edges emitted |
| entry date | `dwc:eventDate` (xsd:date or `"start/end"`), `dwc:verbatimEventDate` | direct (was `lkg:entryDate`/`entryDateEnd`) |
| entry text | `dwc:fieldNotes` | direct (was `lkg:rawText`) |
| date note | `skos:note` | direct (was `lkg:dateNote`) |
| individual count / range | `dwc:individualCount`; `lkg:individualCountMin`/`Max` | direct; project terms |
| vernacular / scientific name | `dwc:vernacularName`@de (+ `rdfs:label`), `dwc:scientificName`; merged spellings `skos:altLabel`; name as written on a merged observation `dwc:verbatimIdentification` | direct (was `lkg:vernacularNameDE`/`scientificName`) |
| GBIF classification | `dwc:kingdom`, `dwc:phylum`, `dwc:class`, `dwc:order`, `dwc:family`, `dwc:genus` | direct (new) |
| place name as written | `dwc:verbatimLocality` (on Place) | direct (was `lkg:verbatimLocality`) |
| coordinates | `geo:lat`/`geo:long`, `dwc:decimalLatitude`/`Longitude` + `dwc:geodeticDatum`, `gsp:asWKT` | direct |
| habitat | `dwciri:habitat` (concept IRI) + `dwc:habitat` (literal) | direct (was `lkg:hasHabitat`) |
| behaviour | `dwc:behavior` literals | direct (was `lkg:hasBehaviour` → BehaviourNote) |
| evidence kind | `lkg:evidenceKind` → `lkg:evidence_*` concepts (on the observation) | project term (was on evidence nodes) |
| breeding | `lkg:breedingEvidence` (+ `dwc:reproductiveCondition "breeding"` for confirmed/probable) | project term + direct |
| record type | `lkg:recordType` (deliberately not ⊑ `dwc:basisOfRecord`); derived `dwc:basisOfRecord` | project term + direct |
| Taxon ↔ GBIF | `skos:exactMatch` / `closeMatch` / `broadMatch`, `dwc:taxonID` | by match type |
| Person ↔ Wikidata | `owl:sameAs` | linking stage |

Darwin Core terms used directly on `lkg:Observation`: `dwc:occurrenceStatus`,
`dwc:individualCount`, `dwc:sex`, `dwc:lifeStage`, `dwc:vitality`,
`dwc:reproductiveCondition`, `dwc:behavior`, `dwc:habitat`, `dwciri:habitat`,
`dwc:identificationQualifier`, `dwc:eventDate`, `dwc:eventTime`,
`dwc:verbatimLocality`, `dwc:occurrenceRemarks`, `dwc:associatedReferences`,
`dwc:basisOfRecord`, `dwciri:recordedBy`; on `lkg:DiaryEntry`: `dwc:eventDate`,
`dwc:verbatimEventDate`, `dwc:fieldNotes`; on `lkg:Taxon`: `dwc:vernacularName`,
`dwc:scientificName`, `dwc:taxonRank`, `dwc:taxonID`, `dwc:kingdom` … `dwc:genus`.

## Controlled values

Every enumerated literal (`lkg:entryKind`, `lkg:placeKind`, `dwc:sex`, …) is
the English `skos:prefLabel` of a concept in
`ontologies/controlled_vocabularies.ttl`; the tuples in
`normalization/vocabularies.py` and the `sh:in` lists in `shacl_shapes.ttl`
mirror them. Observations point at the evidence concept IRIs via
`lkg:evidenceKind` (`lkg:evidence_visual` …). Habitat concepts are open data
(`data:habitat_*` in `lkg:habitatScheme`).
