# Ontology Mapping

Alignment of the project terms (`lkg:`, `ontologies/laubmann.ttl` v0.7.0) with
external vocabularies. Since 0.4.0 the graph is **Darwin-Core-first**: where a
standard term exists it is emitted *alone* ("direct" below); `lkg:` terms are
declared as sub-classes/sub-properties of external terms only where that adds
meaning ("axiom"). No `lkg:` twin of a standard term remains (0.7.0 removed
`lkg:altitudeM` in favour of the DwC elevation terms and the viewing radius
that had been mirrored as `dwc:coordinateUncertaintyInMeters`).

## Classes

| lkg class | External | How |
|---|---|---|
| `lkg:ArchivalUnit` (grouping) | `rico:RecordResource` | axiom; not asserted in the data (was ⊑ `rico:Record` until 0.6.0) |
| `lkg:DiaryVolume` | `lkg:ArchivalUnit`, `rico:Record` | axiom (0.7.0) |
| `lkg:DiaryPage`, `lkg:SourceRegion` | `lkg:ArchivalUnit`, `rico:RecordPart` | axiom (0.7.0) |
| `lkg:MultimodalRegion` | `lkg:SourceRegion` | axiom (0.6.0); `dcterms:type` DCMI type, `dcterms:description`, `dcterms:identifier`, `schema:image` direct |
| `lkg:DiaryEntry` | `lkg:ArchivalUnit`, `rico:RecordPart`, `dwc:Event` | axiom |
| `lkg:EntryRecord` (grouping) | `prov:Entity` | axiom; not asserted in the data |
| `lkg:Observation` | `lkg:EntryRecord`, `dwc:Occurrence` | axiom (renamed from `ObservationEvent` in 0.4.0) |
| `lkg:TravelEvent` | `lkg:EntryRecord` | axiom (⊑ `dwc:Event` until 0.6.0; never published as an event) |
| `lkg:TravelLeg` | `lkg:EntryRecord` | axiom (was ⊑ `lkg:RecordDetail` until 0.5.0) |
| `lkg:WeatherReport` | `lkg:EntryRecord` | axiom; at most one per entry (0.7.0) |
| ~~`lkg:RecordDetail`~~, ~~`lkg:Vocalisation`~~ | — | removed in 0.6.0 (calls are `lkg:callType` / `lkg:callTranscription` on the observation) |
| `lkg:Place` | `geo:SpatialThing`, `dcterms:Location`, `gsp:Feature` | axiom (`gsp:Feature` since 0.7.0) |
| point of a place | `gsp:Geometry` | direct (0.7.0; `data:geometry_place_…`, reached by `gsp:hasGeometry`) |
| `lkg:Taxon` | `dwc:Taxon` | axiom |
| `lkg:Person` | `schema:Person` | axiom; `schema:name` direct |
| habitat nodes | `skos:Concept` in `lkg:habitatScheme` | direct (no lkg class since 0.4.0) |
| authority records (GBIF, EUNIS, GeoNames, Wikidata, GND) | `skos:Concept` in `lkg:authority_*` (`skos:ConceptScheme`, `void:uriSpace`) | direct (0.6.0) |
| run / agent / prompt | `prov:Activity`, `prov:SoftwareAgent`, `prov:Entity` | direct |

## Properties

| Meaning | Term in the data | How |
|---|---|---|
| observation → taxon | `lkg:observedTaxon` | ⊑ `dwciri:toTaxon` (axiom) |
| effective / own place | `lkg:observedAt`, `lkg:hasLocality` | project terms |
| place wording as written | `dwc:verbatimLocality` on the DiaryEntry (header) and on the Observation (own locality) | direct; no longer on the shared Place (0.7.0) |
| observer(s) | `dwciri:recordedBy` (0..n: the diarist and the companions who observed with him, or the third-party observer) | direct (was `lkg:observedBy`; several values since 0.7.0) |
| record part of / derived from entry | `dcterms:isPartOf`, `prov:wasDerivedFrom` | direct on Observation, TravelEvent, TravelLeg (isPartOf its event), WeatherReport (was `lkg:derivedFromEntry`) |
| entry → records | `lkg:containsObservation`, `lkg:containsTravelEvent`, `lkg:hasWeather`, `lkg:hasLeg` | ⊑ `dcterms:hasPart` (axiom); child carries `dcterms:isPartOf` |
| entry → page → volume, region → page | `dcterms:isPartOf` | direct (was `lkg:hasPage`/`hasVolume`) |
| entry → layout region | `lkg:hasSourceRegion` (every body-text region the entry spans); `lkg:hasMultimodalRegion` ⊑ `lkg:hasSourceRegion` | project terms; both edges emitted for multimodal regions |
| entry mentions person | `lkg:mentionsPerson` ⊑ `schema:mentions`; role edges `lkg:mentionsCompanion\|Source\|Collector\|CitedAuthor\|Other` ⊑ `lkg:mentionsPerson` | axiom; both edges emitted |
| entry date | `dwc:eventDate` (xsd:date or `"start/end"`), `dwc:verbatimEventDate` | direct (was `lkg:entryDate`/`entryDateEnd`) |
| record date | `dwc:eventDate` on the Observation: own date or `"start/end"` range, else the entry's date or interval | direct (0.7.0 rule) |
| clock time / time of day | `dwc:eventTime` "HH:MM"; `lkg:timeOfDay` (dawn … dusk, night) | direct; project term (`lkg:daylightPhase` folded in, 0.7.0) |
| entry text | `dwc:fieldNotes` | direct (was `lkg:rawText`) |
| date note | `skos:note` | direct (was `lkg:dateNote`) |
| individual count / range | `dwc:individualCount`; `lkg:individualCountMin`/`Max`, `lkg:countQualifier` | direct; project terms |
| vernacular / scientific name | `dwc:vernacularName`@de (+ `rdfs:label`), `dwc:scientificName`; merged spellings `skos:altLabel`; name as written on a merged observation `dwc:verbatimIdentification` | direct (was `lkg:vernacularNameDE`/`scientificName`) |
| GBIF classification | `dwc:kingdom`, `dwc:phylum`, `dwc:class`, `dwc:order`, `dwc:family`, `dwc:genus` | direct |
| coordinates | `geo:lat`/`geo:long`, `dwc:decimalLatitude`/`Longitude` + `dwc:geodeticDatum`; `gsp:hasGeometry` → `gsp:Geometry` with `gsp:asWKT` | direct (`gsp:asWKT` on the Place until 0.6.0) |
| georeference quality | `dwc:coordinateUncertaintyInMeters` (centroid radius), `dwc:georeferenceSources` on the Place | direct; not on the Observation (0.7.0) |
| elevation | `dwc:minimumElevationInMeters` / `dwc:maximumElevationInMeters` on the Place (stated place elevation) and on the Observation (own site) | direct (was `lkg:altitudeM`, 0.5.0–0.6.0) |
| vantage, microhabitat, flight height | `lkg:spatialContext`, `lkg:microhabitat`, `lkg:relativeElevation` | project terms (literals as written) |
| habitat | `dwciri:habitat` (concept IRI) + `dwc:habitat` (literal) | direct (was `lkg:hasHabitat`) |
| behaviour | `dwc:behavior` literals | direct (was `lkg:hasBehaviour` → BehaviourNote) |
| evidence kind | `lkg:evidenceKind` literal "visual" … (on the observation; concept in `lkg:evidenceKindScheme`) | project term (concept IRIs until 0.5.0, evidence nodes before) |
| what was heard | `lkg:callType`, `lkg:callTranscription` literals on the observation | project terms (on `lkg:Vocalisation` nodes until 0.5.0) |
| breeding | `lkg:breedingEvidence` (+ `dwc:reproductiveCondition "breeding"` for confirmed only) | project term + direct |
| record type | `lkg:recordType` (deliberately not ⊑ `dwc:basisOfRecord`); derived `dwc:basisOfRecord` (`MaterialCitation` only with a citation in `dwc:associatedReferences`) | project term + direct |
| taxon match provenance | `lkg:matchMethod` (`lkg:matchMethodScheme`), `lkg:gbifMatchType` | project terms (`lkg:matchConfidence` removed in 0.7.0) |
| Taxon ↔ GBIF | `skos:exactMatch` / `closeMatch` / `broadMatch` → authority record, `dwc:taxonID` | by match type; machine review → `closeMatch` |
| Habitat ↔ EUNIS | `skos:exactMatch` / `closeMatch` / `broadMatch` → authority record (+ `skos:broader` chain) | model / reviewer judgement |
| Place ↔ GeoNames, Wikidata | `skos:exactMatch` (OSM + GeoNames agree, reviewed) / `closeMatch` (single-source, machine review) | linking stage (`owl:sameAs` until 0.5.0) |
| Person ↔ Wikidata, GND | `skos:exactMatch` (reviewed) / `closeMatch` (automatic, machine review) | linking stage (`owl:sameAs` until 0.5.0) |
| controlled property → its scheme | `rdfs:seeAlso` on the property (ontology) | axiom-level documentation (0.7.0) |

Removed in 0.7.0 without replacement: `lkg:observationRadiusMeters`,
`lkg:spatialConfidence`, `lkg:observationDurationMinutes`,
`lkg:matchConfidence`, and `dwc:samplingProtocol` /
`dwc:coordinateUncertaintyInMeters` on the Observation (template values the
diaries never state).

Darwin Core terms used directly on `lkg:Observation`: `dwc:occurrenceStatus`,
`dwc:individualCount`, `dwc:sex`, `dwc:lifeStage`, `dwc:vitality`,
`dwc:reproductiveCondition`, `dwc:behavior`, `dwc:habitat`, `dwciri:habitat`,
`dwc:identificationQualifier`, `dwc:verbatimIdentification`, `dwc:eventDate`,
`dwc:eventTime`, `dwc:verbatimLocality`, `dwc:minimumElevationInMeters`,
`dwc:maximumElevationInMeters`, `dwc:occurrenceRemarks`,
`dwc:associatedReferences`, `dwc:basisOfRecord`, `dwciri:recordedBy`; on
`lkg:DiaryEntry`: `dwc:eventDate`, `dwc:verbatimEventDate`,
`dwc:verbatimLocality`, `dwc:fieldNotes`; on `lkg:Place`:
`dwc:decimalLatitude`, `dwc:decimalLongitude`, `dwc:geodeticDatum`,
`dwc:coordinateUncertaintyInMeters`, `dwc:georeferenceSources`,
`dwc:minimumElevationInMeters`, `dwc:maximumElevationInMeters`; on
`lkg:Taxon`: `dwc:vernacularName`, `dwc:scientificName`, `dwc:taxonRank`,
`dwc:taxonID`, `dwc:kingdom` … `dwc:genus`.

## Controlled values

Every enumerated literal (`lkg:entryKind`, `lkg:placeKind`, `lkg:timeOfDay`,
`lkg:matchMethod`, `dwc:sex`, …) is the `skos:notation` of a concept in
`ontologies/controlled_vocabularies.ttl` (equal to its English
`skos:prefLabel`; every concept carries a notation since 0.7.0), and the
ontology points each controlled property at its scheme with `rdfs:seeAlso`.
The tuples in `normalization/vocabularies.py` and the `sh:in` lists in
`shacl_shapes.ttl` mirror them — `lkg:evidenceKind` included since 0.6.0
(before, it pointed at the concept IRIs `lkg:evidence_visual` …). No scheme
has a placeholder value (0.7.0 removed transportMode/taxonRank/placeKind
"unknown", placeKind "route" and vitality "alive"). The Darwin Core Archive
publishes every controlled value without a DwC term as an eMoF row whose
`measurementTypeID` is the scheme and `measurementValueID` the concept IRI.
Habitat concepts are open data (`data:habitat_*` in `lkg:habitatScheme`),
because they carry their own EUNIS links; external authority records are
`skos:Concept`s in `lkg:authority_*`.
