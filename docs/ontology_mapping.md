# Ontology Mapping

Alignment of the project terms (`lkg:`, `ontologies/laubmann.ttl` v0.3.0) with
external vocabularies. "Axiom" = declared in the ontology; "co-emit" = the
external term is written into the data graph next to the project term by
`kg/rdf.py`, so consumers need no reasoning.

## Classes

| lkg class | External | How |
|---|---|---|
| `lkg:DiaryEntry` | `rico:Record`, `dwc:Event` | axiom |
| `lkg:DiaryPage`, `lkg:DiaryVolume` | `rico:Record` | axiom |
| `lkg:SourceRegion` | `oa:Annotation` | axiom + materialised type |
| `lkg:ObservationEvent` | `dwc:Occurrence` | axiom (was `dwc:Event` in v0.2) |
| `lkg:TravelEvent` | `dwc:Event` | axiom |
| `lkg:Place` | `geo:SpatialThing`, `dcterms:Location` | axiom |
| `lkg:Habitat` | `skos:Concept` (in `lkg:habitatScheme`) | axiom + materialised type (was `lkg:Place` in v0.2) |
| `lkg:Taxon` | `dwc:Taxon` | axiom |
| `lkg:Person` | `schema:Person` | axiom; `schema:name` co-emitted |
| `lkg:BirdCall` | `lkg:ObservationEvidence` | axiom + materialised type |
| `lkg:TimeEstimate` | `time:Interval` | axiom (reserved, not emitted) |
| run / agent / prompt | `prov:Activity`, `prov:SoftwareAgent`, `prov:Entity` | emitted directly |

## Properties

| lkg property | External | How |
|---|---|---|
| `lkg:observedTaxon` | `dwciri:toTaxon` | sub-property axiom (v0.2 pointed at the non-existent `dwciri:taxon`) |
| `lkg:observedAt` | — | no longer ⊑ `dwciri:inDescribedPlace` (that term's subject is a Location) |
| `lkg:hasLocality` | `dwc:verbatimLocality` (literal) | co-emit on the observation |
| `lkg:observedBy` | `dwciri:recordedBy` | sub-property axiom + co-emit |
| `lkg:derivedFromEntry` | `prov:wasDerivedFrom` | sub-property axiom; `owl:inverseOf lkg:containsObservation` |
| `lkg:mentionsPerson` | `schema:mentions` | sub-property axiom |
| `lkg:entryDate` | `dwc:eventDate` | sub-property axiom + co-emit (interval string when `entryDateEnd` set) |
| `lkg:dateNote` | `skos:note` | sub-property axiom + co-emit |
| `lkg:individualCount` | `dwc:individualCount` | sub-property axiom + co-emit |
| `lkg:vernacularNameDE` | `dwc:vernacularName`, `rdfs:label` | sub-property axiom + co-emit |
| `lkg:scientificName` | `dwc:scientificName` | sub-property axiom + co-emit |
| `lkg:verbatimLocality` (Place) | `dwc:verbatimLocality` | sub-property axiom |
| `lkg:hasHabitat` | `dwciri:habitat` (IRI), `dwc:habitat` (literal) | co-emit |
| `lkg:hasBehaviour` | `dwc:behavior` (literal) | co-emit |
| `lkg:breedingEvidence` confirmed/probable | `dwc:reproductiveCondition "breeding"` | co-emit |
| `geo:lat` / `geo:long` | `dwc:decimalLatitude` / `dwc:decimalLongitude` + `dwc:geodeticDatum` | co-emit |
| `lkg:recordType` | — (deliberately not ⊑ `dwc:basisOfRecord`) | derived `dwc:basisOfRecord` co-emitted |
| Taxon ↔ GBIF | `skos:exactMatch` / `closeMatch` / `broadMatch`, `dwc:taxonID` | by match type |
| Person ↔ Wikidata | `owl:sameAs` | linking stage |

Darwin Core terms used directly on `lkg:ObservationEvent` (no lkg twin):
`dwc:occurrenceStatus`, `dwc:sex`, `dwc:lifeStage`, `dwc:vitality`,
`dwc:identificationQualifier`, `dwc:eventDate`, `dwc:eventTime`,
`dwc:occurrenceRemarks`, `dwc:associatedReferences`, `dwc:basisOfRecord`;
on `lkg:Taxon`: `dwc:taxonRank`.

## Controlled values

Every enumerated literal (`lkg:entryKind`, `lkg:placeKind`, `dwc:sex`, …) is
the English `skos:prefLabel` of a concept in
`ontologies/controlled_vocabularies.ttl`; the tuples in
`normalization/vocabularies.py` and the `sh:in` lists in `shacl_shapes.ttl`
mirror them. Evidence nodes additionally point at the concept IRI via
`lkg:evidenceKind` (`lkg:evidence_visual` …). Habitat concepts are open data
(`data:habitat_*` in `lkg:habitatScheme`).
