# Data Model

The knowledge graph conforms to `ontologies/laubmann.ttl` (v0.7.0, namespace
`https://w3id.org/laubmann-kg/ontology#`, prefix `lkg:`). Instances live under
`https://w3id.org/laubmann-kg/data/` (prefix `data:`). The Python contract is
`src/laubmann_kg/kg/model.py`; `kg/rdf.py` maps it onto triples and
`ontologies/shacl_shapes.ttl` validates the result **without inference** (shapes
target the concrete classes; the grouping superclasses are not asserted in the
data). Enumerated values are defined once in `normalization/vocabularies.py` and
mirrored as SKOS concept schemes in `ontologies/controlled_vocabularies.ttl`.
`tests/test_ontology_alignment.py` enforces, in both directions, that the
emitter, the ontology, the shapes and the JSON-LD context use the same terms.

Extraction is LLM-based (`extraction/llm_observations.py`; prompt
`prompts/observation_extraction.md` **v4**, model `gemini-3.8-flash` in
`configs/full_llm.yaml`); the offline rule-based backend is a network-free test
double. Prompt v4 puts the instructions first (a constant, cached prefix) and
the entry last, and asks for one compact JSON line that omits defaults; the
mapper restores them (`taxon_rank` species, `is_bird` true, `count_qualifier`
exact next to a number, `record_type` field-observation, `confidence` ≥ 0.9).
Nothing is inferred from prose in the emitter: a value appears in the graph
only when the extractor set it.

Diagrams (Mermaid, render with any Mermaid tool or paste into Mermaid Chart):
`docs/kg_structure.mmd` (classes, datatype properties, predicates as emitted)
and `docs/pipeline.mmd` (stages and where each decision is made).
Human-readable ontology docs: `docs/ontology/index.html` (pyLODE), with
`vocabularies.html` and `shapes.html`.

## Design principles (0.4.0, tightened in 0.7.0)

- **Darwin-Core-first.** Wherever a `dwc:`/`dwciri:`, DCTERMS, PROV-O, SKOS,
  GeoSPARQL or schema.org term exists, the graph uses that term alone;
  `lkg:` carries only project-specific meaning (record type, count qualifier and
  ranges, breeding evidence, movement, evidence kind, call type, entry kind,
  weather, travel, mention roles, spatial/temporal qualification, region
  kind). No `lkg:` twin of a standard term is emitted: 0.7.0 removed the last
  ones (`lkg:altitudeM` gave way to `dwc:minimumElevationInMeters` /
  `dwc:maximumElevationInMeters`; `lkg:observationRadiusMeters`, which was
  mirrored as `dwc:coordinateUncertaintyInMeters`, is gone).
- **Only what the text states (0.7.0).** Template-driven fields the diaries
  never state are removed: viewing radius (`lkg:observationRadiusMeters`),
  `lkg:spatialConfidence`, `lkg:observationDurationMinutes`,
  `dwc:samplingProtocol` and `dwc:coordinateUncertaintyInMeters` on the
  observation (the radius had been published as the uncertainty around a
  settlement centroid), and `lkg:matchConfidence` on the taxon (it mixed four
  confidences on a shared node). Placeholders are gone as well: no
  `transportMode "unknown"` (the leg omits the mode), no `taxonRank
  "unknown"`, no `placeKind "route"`/`"unknown"`, no `vitality "alive"` (only
  `dead` is stated).
- **Two grouping superclasses** structure the hierarchy (declared, never
  asserted as `rdf:type` in the data):
  `lkg:ArchivalUnit` ⊑ `rico:RecordResource` — DiaryVolume (⊑ `rico:Record`),
  DiaryPage, DiaryEntry, SourceRegion and its subclass MultimodalRegion (all ⊑
  `rico:RecordPart`);
  `lkg:EntryRecord` ⊑ `prov:Entity` — Observation, TravelEvent, TravelLeg,
  WeatherReport (what the model reads out of one entry; each is
  `prov:wasDerivedFrom` its entry). `lkg:RecordDetail` was dropped in 0.6.0.
  Only the DiaryEntry is a `dwc:Event`; the TravelEvent is not (0.7.0 — it is
  never published as one). Taxon, Place and Person are shared referents;
  habitats are `skos:Concept`s.
- **Explicit partonomy.** Containment properties (`lkg:containsObservation`,
  `lkg:containsTravelEvent`, `lkg:hasWeather`, `lkg:hasLeg`)
  are sub-properties of `dcterms:hasPart`; every child node carries
  `dcterms:isPartOf`. An entry has at most one WeatherReport (0.7.0).
- **Controlled values are literals.** Every enumerated value is the
  `skos:notation` of a concept in a SKOS scheme of the project namespace (the
  notation equals the English `skos:prefLabel`; checked with `sh:in`), and
  every controlled datatype property names its scheme with `rdfs:seeAlso`
  (0.7.0). New schemes in 0.7.0: `lkg:timeOfDayScheme` and
  `lkg:matchMethodScheme`.
- **Flat where a node adds nothing.** Behaviour = `dwc:behavior` literals;
  evidence kinds = `lkg:evidenceKind` literals on the observation ("visual" |
  "auditory" | "nest" | "specimen"); what was heard = `lkg:callType` (song |
  call | alarm | drumming, no "unknown" placeholder) and
  `lkg:callTranscription` literals on the observation (0.6.0 — the former
  `lkg:Vocalisation` node and the `dwc:behavior` copies such as "singend" are
  gone; the extraction mapper folds purely vocal behaviour phrases into the
  call type). Only weather reports and travel events/legs stay nodes.
- **One link pattern for every authority (0.6.0).** Taxa → GBIF, habitat
  concepts → EUNIS, places → GeoNames and Wikidata, persons → Wikidata and
  GND: always `skos:exactMatch` (same referent, strong evidence),
  `skos:closeMatch` (same referent, weaker evidence) or `skos:broadMatch` (the
  target is broader) from the project node to the authority IRI; the IRI is a
  `skos:Concept` with `skos:inScheme lkg:authority_gbif | _eunis | _geonames
  | _wikidata | _gnd`, `skos:notation` (the authority's id) and
  `skos:prefLabel` when known (`kg/authority.py` derives the grade from what
  linking recorded: GBIF match type, EUNIS judgement, OSM+GeoNames agreement,
  reviewed vs. automatic person match). A human review decision gives
  `exactMatch`, the machine review (LLM subagents, `review.machine`) gives
  `closeMatch` (taxa: `lkg:matchMethod "machine-review"`; places:
  georeference source `machine-review`; persons: `Person.gnd_match` /
  `wikidata_match`). No `owl:sameAs`: it cannot grade a match and would merge
  the external records into the graph under OWL reasoning. Query: `?x
  skos:exactMatch|skos:closeMatch|skos:broadMatch ?a . ?a skos:inScheme
  lkg:authority_gnd ; skos:notation ?id`.
- **Regions (0.6.0).** An entry links every body-text region its text runs
  through (`lkg:hasSourceRegion`; the continuation pages of a long entry are
  in the graph as `lkg:DiaryPage`s) and its multimodal regions
  (`lkg:hasMultimodalRegion` ⊑ `lkg:hasSourceRegion` → `lkg:MultimodalRegion`:
  drawings, maps, photographs, prints, mounted objects, inserted texts, with
  `lkg:regionKind`, `dcterms:type` (DCMI), `dcterms:description`,
  `lkg:visibleText`, `dcterms:identifier` = crop file, `schema:image` = public
  URL of the crop once the images are hosted — config
  `multimodal.image_base_url`; only then does the DwC-A get multimedia rows).
- **Travel legs never invent a start.** `lkg:departurePlace` is the stated
  start, else the previous leg's arrival, else the entry's place for a leg
  that leads elsewhere; a leg to the entry's own place with no stated start
  has an arrival only (0.6.0; before: "Kaufbeuren → Kaufbeuren").
  `lkg:transportMode` is emitted only when the text states it (0.7.0).
- **Count qualifier** `exact | minimum | maximum | approximate |
  plural-unspecified` ("maximum" = "höchstens", "bis zu", since 0.6.0). A
  range is `lkg:individualCountMin` / `Max` (with `dwc:individualCount` = the
  lower bound and qualifier `approximate` unless stated); a single bound is a
  count with qualifier `minimum` or `maximum`.
- **Record dates (0.7.0).** An observation's `dwc:eventDate` is its own date
  or date range when the text gives one (`event_date` / `event_date_end`, e.g.
  a digest line, "Pfingsten 1925"; the year of a list line comes from the
  line, else the list heading, else the entry), otherwise the entry's date or
  multi-day interval (`"start/end"`). Before 0.7.0 a record of a multi-day or
  position-dated entry got the entry's start day, a falsely precise date.
- **Who recorded it (0.7.0).** `dwciri:recordedBy` may be several persons.
  The diarist's own records name the diarist plus the companions the text
  says observed with him (`observed_with` in the prompt, e.g. "Alfred
  Laubmann | Frau Laubmann"); a third-party record names its observer (a
  name tag, "Kiel meldet", or `entry_observer`: the author of a pasted report
  or the person of a header tag "Feldwies (Kiefer)", given once per entry);
  an unattributed report or a citation gets no `recordedBy`. A
  `literature-record` needs a citation (`dwc:associatedReferences`); only then
  is its `dwc:basisOfRecord` `MaterialCitation`.
- **Time and space on the observation (Ziel 1, 0.5.0, tightened in 0.7.0).**
  The named site stays a `lkg:Place` (`lkg:hasLocality` when it differs from
  `lkg:entryPlace`; only proper names — generic nouns such as "am See" are
  habitat or microhabitat); vantage wording, microhabitat and flight height
  are literals (`lkg:spatialContext`, `lkg:microhabitat`,
  `lkg:relativeElevation`); a stated elevation of the record's own site is
  `dwc:minimumElevationInMeters` = `dwc:maximumElevationInMeters`. Clock time
  is `dwc:eventTime` (`HH:MM`); the qualitative slot is one scale,
  `lkg:timeOfDay` (dawn | morning | forenoon | noon | afternoon | evening |
  dusk | night; `lkg:daylightPhase` was folded into it in 0.7.0).
- **Per-use wording stays on the use (0.7.0).** `dwc:verbatimLocality` is
  emitted on the DiaryEntry (the header's place wording) and on the
  Observation (its own locality as written), no longer on the shared Place.
- **One reading per shared node (0.7.0).** The model reads every record on its
  own, so one written name can come back with different details ("Brachvogel"
  as *Numenius*/genus ×481 and *N. arquata*/species ×22). After QA,
  `normalization/harmonize.py` gives all records of a vernacular name the same
  Taxon (the most frequent scientific-name + rank pair, majority `is_bird`)
  and all uses of a place name the same Place (kind, elevation, coordinates),
  so the RDF and the DwC-A publish the same reading.
- **One node per real-world entity.** The entity-resolution stage
  (`resolution/`, after linking) merges spellings that denote the same taxon
  (same accepted GBIF key at species level, or same scientific name), person
  (title-stripped/folded key, Wikidata item, unique initial/surname, dominant
  usage) or place/habitat (orthographic variants; similar strings only after
  review). The canonical spelling is the most-used one; merged spellings are
  `skos:altLabel`, and an observation whose written taxon name was merged keeps
  it as `dwc:verbatimIdentification`. Observation IRIs never change (they hash
  the name as written). Every merge is a row in `review/*_merges.csv`
  (`decision` column: `auto` rows apply unless rejected, `candidate` rows only
  when accepted).
- **Habitats linked to EUNIS.** After resolution, `linking/habitats.py` asks
  the LLM (cached, batched) for the EUNIS habitat class (2012 classification,
  Eionet vocabulary `http://eunis.eea.europa.eu/eunishabitats/<code>`) of every
  distinct habitat label and how it relates to it: the habitat concept gets at
  most one `skos:exactMatch` / `skos:closeMatch` / `skos:broadMatch`; the EUNIS
  class is a `skos:Concept` with `skos:notation`, `skos:prefLabel`@en and its
  `skos:broader` chain up to the level-1 group, so "everything in woodland" is
  `skos:broader* G`. The class URIs are identifiers (the eunis.eea.europa.eu
  web application is retired); each class node carries `rdfs:seeAlso` to its
  Eionet Data Dictionary page and to the BISE hierarchical view of the 2012
  classification. Confidence ≥ 0.7 is applied, the rest waits in
  `review/habitat_link_review.csv` (`y`/`n` decisions → `reviewed_csv`). The
  DwC-A carries the class as an eMoF row (`habitat type (EUNIS 2012)`,
  `measurementValueID` = EUNIS URI); `dwc:habitat` stays verbatim.
- **Places georeferenced with an identity.** `linking/places.py` combines a
  pre-warmed Nominatim cache (OSM: name-matched hit of an acceptable type),
  the GeoNames country dumps (a record with the same name within 10 km of the
  OSM point, or unique in Bavaria) and Wikidata (QID from the OSM tag or
  GeoNames P1566): `geo:lat/long`, a GeoSPARQL geometry (`lkg:Place` ⊑
  `gsp:Feature`, `gsp:hasGeometry` → `gsp:Geometry` with `gsp:asWKT`; 0.7.0 —
  `asWKT` on the place itself made every place a geometry under RDFS),
  `skos:exactMatch` (OSM and GeoNames agree, or reviewed) / `skos:closeMatch`
  (single-source match or machine review) `https://sws.geonames.org/<id>/` and
  `wd:Q…`, `dwc:coordinateUncertaintyInMeters` (centroid radius by feature
  type: town 2 km, lake 1 km, peak 300 m …) and `dwc:georeferenceSources`. In
  the DwC-A every occurrence row carries the georeference of its own place
  (`locationID` = GeoNames URI, coordinates, uncertainty, sources, protocol);
  the event row keeps the entry place's point only when no record of the
  entry sits at another, un-georeferenced place that would otherwise inherit
  it at GBIF. Labels that cannot be gazetteer entries (prepositional
  fragments, generic nouns, micro-localities) are never tried; everything
  else lands in `review/place_link_review.csv` (linked | review | no_match,
  decision column).
- **Dates checked against the volume span.** `configs/volume_coverage.yaml`
  (title pages; each `lkg:DiaryVolume` states its span as `dcterms:temporal
  "YYYY-MM/YYYY-MM"`) drives `normalization/coverage.py`: misfiled scans go
  back to their document's volume (a `skos:note` names the scan set they were
  digitised in; the corpus id in `dcterms:identifier` is kept), isolated OCR
  years are repaired from the sequence neighbours for every entry kind (`1901`
  → `1951`; recorded as `skos:note`, the raw date stays
  `dwc:verbatimEventDate`; since 0.7.0 the repair also moves the records' own
  dates and date ranges, the entry's end date and travel times that carried
  the misread year, and lifts `datePlausible false`), an entry dated outside
  the diary period (April 1917 – December 1965) that cannot be repaired is
  dated by its position in the volume (an interval between the neighbouring
  in-span entries; a pre-diary written date whose records the model read as
  historic — own event dates, literature records, specimens — is a record
  date and passes to the entry's observations as their own `dwc:eventDate`),
  non-entries (`other`) outside the period are excluded, off-span entries
  inside the period are kept and flagged (QA reasons `volume_reassigned`,
  `date_year_corrected`, `date_from_position`, `date_out_of_coverage`,
  `date_out_of_span`, `duplicate_entry`). No entry is dated before the first
  or after the last title page.

## Node types and keys

| Class | IRI | Key |
|---|---|---|
| `lkg:DiaryVolume` (⊑ ArchivalUnit, rico:Record; `dcterms:temporal` title-page span) | `data:volume_NN` | corpus |
| `lkg:DiaryPage` (⊑ ArchivalUnit, rico:RecordPart; `dcterms:isPartOf` volume) | `data:page_<page_uid>` | corpus |
| `lkg:DiaryEntry` (⊑ ArchivalUnit, rico:RecordPart, dwc:Event; `dcterms:isPartOf` page or volume) | `data:entry_<entry_uid>` | corpus `entry_uid` |
| `lkg:SourceRegion` (⊑ ArchivalUnit, rico:RecordPart; `dcterms:isPartOf` page) | `data:region_<region_uid>` | corpus (every body-text region the entry spans) |
| `lkg:MultimodalRegion` (⊑ SourceRegion; `dcterms:isPartOf` page) | `data:region_<region_uid>` | `multimodal_regions.jsonl` (catalogue v2 + selected text inserts) |
| `lkg:Observation` (⊑ EntryRecord, dwc:Occurrence) | `data:obs_<sha1(entry_uid\|vernacular\|index)>` | derived |
| `lkg:TravelEvent` (⊑ EntryRecord; no dwc:Event) / `lkg:TravelLeg` (⊑ EntryRecord) | `data:travel_<entry>_<i>` / `data:leg_…` | per entry |
| `lkg:WeatherReport` (⊑ EntryRecord) | `data:weather_<entry_uid>` | at most one per entry |
| authority record (`skos:Concept`, `skos:inScheme lkg:authority_*`) | the authority's IRI (gbif.org/species/…, eunis…/eunishabitats/…, sws.geonames.org/…/, wikidata.org/entity/Q…, d-nb.info/gnd/…) | external id (`skos:notation`) |
| `lkg:Taxon` (⊑ dwc:Taxon) | `data:taxon_<sha1(vernacular lower)>` | German vernacular as written |
| `lkg:Place` (⊑ geo:SpatialThing, dcterms:Location, gsp:Feature) | `data:place_<sha1(canonical or verbatim)>` | place name |
| `gsp:Geometry` (point of a georeferenced place) | `data:geometry_place_<sha1>` | the place |
| habitat `skos:Concept` in `lkg:habitatScheme` (**not** a class, **not** a Place) | `data:habitat_<sha1(label)>` | habitat label, shared across observations |
| `lkg:Person` (⊑ schema:Person) | `data:person_<sha1(name lower)>` | name; the diarist is `person_c6b2ff6250e5` |
| `prov:Activity` (run) / `prov:SoftwareAgent` / `prov:Entity` (prompt) | `data:run_<sha1(model\|prompt_sha\|started)>` / `data:agent_<model>` / `data:prompt_<sha[:12]>` | `ExtractionResult.provenance` |

## Provenance / partonomy chain

```
Observation  (dwc:Occurrence)
  ├─ dcterms:isPartOf + prov:wasDerivedFrom → DiaryEntry   (dwc:Event; lkg:containsObservation back)
  │     ├─ dcterms:isPartOf → DiaryPage ─ dcterms:isPartOf → DiaryVolume   (page unknown: entry → volume)
  │     ├─ lkg:hasSourceRegion → SourceRegion ─ dcterms:isPartOf → DiaryPage   (one per page the entry spans)
  │     ├─ lkg:hasMultimodalRegion → MultimodalRegion ─ dcterms:isPartOf → DiaryPage
  │     ├─ lkg:entryPlace → Place            (entry's main locality) + dwc:verbatimLocality (header wording)
  │     ├─ dwc:eventDate (xsd:date | "start/end"), dwc:verbatimEventDate, dwc:fieldNotes (entry text)
  │     ├─ lkg:entryKind, lkg:datePlausible, skos:note (date / reading notes), dcterms:identifier
  │     ├─ lkg:mentionsPerson → Person  + role edge lkg:mentionsCompanion|Source|Collector|CitedAuthor|Other
  │     ├─ lkg:hasWeather → WeatherReport   (0..1; dcterms:isPartOf + prov:wasDerivedFrom the entry)
  │     └─ lkg:containsTravelEvent → TravelEvent ─ lkg:hasLeg → TravelLeg (dcterms:isPartOf the event, prov:wasDerivedFrom the entry)
  ├─ lkg:observedTaxon (⊑ dwciri:toTaxon) → Taxon
  ├─ lkg:observedAt → Place                  (EFFECTIVE place: own locality, else entry place)
  ├─ lkg:hasLocality → Place                 (only when the record states its OWN locality; + dwc:verbatimLocality on the observation)
  ├─ dwc:eventDate                           (own date or "start/end" range, else the entry's date or interval)
  ├─ dwc:eventTime, lkg:timeOfDay, dwc:minimumElevationInMeters / dwc:maximumElevationInMeters (own site)
  ├─ lkg:evidenceKind "visual"|"auditory"|"nest"|"specimen"   (0–4 values)
  ├─ lkg:callType "song"|"call"|"alarm"|"drumming", lkg:callTranscription "…"   (literals; 0.6.0)
  ├─ dwc:behavior "…"@de                     (literals, no node)
  ├─ dwciri:habitat → habitat concept        (+ dwc:habitat literal)
  ├─ dwciri:recordedBy → Person (0..n)       (diarist + companions, or the third-party observer; never fabricated)
  └─ prov:wasGeneratedBy → run (prov:Activity ─ prov:wasAssociatedWith → SoftwareAgent, prov:used → prompt)

Place ─ gsp:hasGeometry → gsp:Geometry ─ gsp:asWKT "POINT(lon lat)"^^gsp:wktLiteral
```

When `ExtractionResult.provenance` is empty (hand-built results) no run node
and no `wasGeneratedBy` are emitted.

## Observation detail (all optional unless noted)

Field names are those of `kg/model.py`; the prompt v4 key is the same unless
noted.

| model.py field | Predicate(s) | Notes |
|---|---|---|
| `verbatim_notes` (required) | `lkg:verbatimNotes`@de | source passage (clause or digest line) |
| `occurrence_status` (required) | `dwc:occurrenceStatus` present\|absent | an absence with a count > 0 loses the count (QA flag `absent_with_count`) |
| `individual_count` | `dwc:individualCount` (xsd:integer ≥ 0) | 0 only with `absent`; the lower bound of a range |
| `count_min` / `count_max` | `lkg:individualCountMin` / `Max` | ranges ("3-4"); a single bound becomes the count with qualifier minimum/maximum |
| `count_qualifier` | `lkg:countQualifier` | exact\|minimum\|maximum\|approximate\|plural-unspecified; exact is the default next to a number |
| `sex`, `life_stage`, `vitality` | `dwc:sex`, `dwc:lifeStage`, `dwc:vitality` | vocab values; vitality only `dead` (no "alive" placeholder) |
| `breeding_evidence` | `lkg:breedingEvidence` (+ `dwc:reproductiveCondition "breeding"` for confirmed only, via `vocabularies.reproductive_condition`) | atlas categories |
| `movement_kind`, `flight_direction` | `lkg:movementKind`, `lkg:flightDirection`@de | direction as written |
| `identification_qualifier` | `dwc:identificationQualifier` | the diarist's hedge as written |
| `event_date`, `event_date_end` | `dwc:eventDate` (xsd:date, or `"start/end"` for an own range; else the entry's date or interval) | only when the record has its own date |
| `event_time` | `dwc:eventTime` "HH:MM" | stated clock time |
| `time_of_day` | `lkg:timeOfDay` | dawn\|morning\|forenoon\|noon\|afternoon\|evening\|dusk\|night (`lkg:timeOfDayScheme`) |
| `spatial_context`, `microhabitat`, `relative_elevation` | `lkg:spatialContext`@de, `lkg:microhabitat`@de, `lkg:relativeElevation`@de | as written |
| `altitude_m` | `dwc:minimumElevationInMeters` = `dwc:maximumElevationInMeters` (xsd:decimal) | stated elevation of the record's own site |
| `locality` | `lkg:hasLocality` → Place + `dwc:verbatimLocality` | proper names only; dropped when equal to the entry place |
| `record_type`, `literature_citation` | `lkg:recordType`, derived `dwc:basisOfRecord`, `dwc:associatedReferences` | HumanObservation / PreservedSpecimen / MaterialCitation (only with a citation) |
| `observer`, `co_observers` (prompt: `observer`, `observed_with`, entry-level `entry_observer`) | `dwciri:recordedBy` (0..n, `Observation.recorders`) | diarist (+ companions) for own records; the observer (+ companions) for third-party records; none for an unattributed report or citation |
| `evidence[]` | `lkg:evidenceKind` value per kind; calls additionally `lkg:callType` (only when the type is stated) and `lkg:callTranscription` (only when written) on the observation | no placeholder; purely vocal behaviour phrases are folded in here |
| `taxon_verbatim` | `dwc:verbatimIdentification` | the name as written, when resolution merged it into a canonical taxon |
| `behaviour[]` | `dwc:behavior`@de literals | |
| `habitat` | `dwciri:habitat` → shared concept + `dwc:habitat` literal | |
| `occurrence_remarks` | `dwc:occurrenceRemarks`@de | reviewer notes (value corrections) |
| `flags` | not emitted (QA only) | |

Taxon: `rdfs:label` + `dwc:vernacularName`@de (+ `skos:altLabel` for merged
spellings), `dwc:scientificName` or `skos:note` (unresolved), `dwc:taxonRank`
(species | subspecies | genus | family | group, `lkg:taxonRankScheme`),
`lkg:isBird`, GBIF classification `dwc:kingdom/phylum/class/order/family/genus`
(from the cached `species/match` response, `Taxon.higher_taxonomy`), match
provenance (`lkg:matchMethod`: gazetteer | llm | llm+gbif | review |
machine-review | unresolved, `lkg:matchMethodScheme`; `lkg:gbifMatchType`) and
the GBIF link as `skos:exactMatch` / `closeMatch` (fuzzy, LLM-mediated or
machine-reviewed) / `broadMatch` (HIGHERRANK) to the authority record
(`lkg:authority_gbif`) plus `dwc:taxonID` (not for broad matches). A linked
taxon without a model-given scientific name takes the GBIF name.

Place: `rdfs:label`@de (canonical; merged spellings as `skos:altLabel`),
`lkg:placeKind` (settlement | locality | region), a stated elevation as
`dwc:minimumElevationInMeters` / `dwc:maximumElevationInMeters`; when
georeferenced `geo:lat`/`geo:long` co-emitted as
`dwc:decimalLatitude`/`Longitude` + `dwc:geodeticDatum "WGS84"`,
`gsp:hasGeometry` → `gsp:Geometry` with `gsp:asWKT "POINT(lon
lat)"^^gsp:wktLiteral`, `dwc:coordinateUncertaintyInMeters` (centroid
radius), `dwc:georeferenceSources` and the GeoNames/Wikidata links. No
`dwc:verbatimLocality` on the shared place (0.7.0).

Person: `rdfs:label`, `schema:name`, `skos:altLabel` (merged name variants),
`skos:exactMatch` (reviewed) / `skos:closeMatch` (automatic unique-label match
or machine review) to the Wikidata item and the GND record. The role is on
the mention edge of each entry, not on the shared node. Relatives are named,
not described ("meine Frau" → "Frau Laubmann").

## Corpus → ontology mapping

| Corpus field (entries.csv) | KG target |
|---|---|
| `entry_uid`, `entry_id` | `data:entry_<uid>`, `dcterms:identifier` |
| `date_norm` / `date_raw` | `dwc:eventDate` (`xsd:date`, model-corrected; multi-day → `"start/end"`), `dwc:verbatimEventDate` |
| `volume`, `page_uid`, `page_id`, `scan`, `region_uid` | `dcterms:isPartOf` page → volume (+ `dcterms:identifier` on the page), `lkg:hasSourceRegion` |
| `source_regions` (patched corpus, JSON) | one `lkg:hasSourceRegion` per body-text region the entry spans (continuation pages become `lkg:DiaryPage`s) |
| `location_raw` | `dwc:verbatimLocality` on the entry; fallback for `lkg:entryPlace` (LLM backend replaces it with the model's reading) |
| `text_clean` | `dwc:fieldNotes`; extraction input |
| `context_before`, `boundary_kind` (patched corpus) | not emitted; shown to the model for attribution only (`context_before`, `segment_note`) |

Multimodal regions join by `entry_uid` (`multimodal_regions.jsonl`, relinked to
the patched corpus by `HistOrniGraph_addons/build_multimodal_regions.py`): each
becomes a `lkg:MultimodalRegion` of that entry and, once the crops are hosted,
a DwC-A multimedia record for the entry's event.

## Ontology → Darwin Core Archive mapping

Event-core sampling-event archive (`configs/dwca.yaml`), joined by `eventID`.
Identifiers are the IRIs of the graph nodes (`eventID` = the entry IRI,
`occurrenceID` = the observation IRI), so both publications name the same
things.

| DwC-A file | rowType | Source |
|---|---|---|
| `event.txt` (core) | Event | one row per dated `DiaryEntry`; `eventDate` = date or interval; `locality` = the model-read entry place, `verbatimLocality` = header, `fieldNumber` = `entry_id`; the entry place's coordinates and georeference only when no record of the entry could inherit them wrongly; weather in `eventRemarks`/`dynamicProperties` |
| `occurrence.txt` | Occurrence | one row per `Observation`; kingdom/class/order/family (GBIF classification, is_bird fallback), `scientificName` (unresolved birds: `Aves`, rank `class`), `taxonRank` (blank for informal groups, explained in `identificationRemarks`), `taxonID`, `individualCount` (0 for absences), `occurrenceStatus`, sex (`mixed` → `male \| female`)/lifeStage/reproductiveCondition/vitality, `behavior` (German call-type labels first, then the behaviours as written), identificationQualifier, `verbatimIdentification`; the georeference of the record's own effective place (`locality`, `verbatimLocality` of the own locality, `locationID`, coordinates, uncertainty = centroid radius, sources, protocol), `minimum/maximumElevationInMeters`, `eventDate` (own date/range, else the entry's)/`eventTime`, habitat, `occurrenceRemarks` (the diary passage + reviewer note), `recordedBy` as in the graph (`" \| "`-separated), `associatedReferences`; free text and numbers without a DwC term (count range, flight direction, call transcription, spatial context, microhabitat, relative elevation) in `dynamicProperties` |
| `measurementorfact.txt` | ExtendedMeasurementOrFact (OBIS eMoF, keyed on `occurrenceID`) | one row per controlled value without a DwC term: evidence kind (deduplicated), call type, count qualifier, breeding evidence, movement kind, record type, time of day, plus the EUNIS class of the habitat; `measurementTypeID` = the SKOS scheme, `measurementValueID` = the concept IRI (`skos:notation` = the value); `measurementMethod` from run provenance |
| `multimedia.txt` | Multimedia (GBIF Simple Multimedia) | only when `multimodal.image_base_url` is set: one row per region crop of a dated entry, `identifier` = public URL, `type` StillImage; no `associatedMedia` |

## Competency queries

`kg/sparql.py` ships CQ1–CQ11 (species frequency, by date, by place, auditory
incl. vocalisation detail, unresolved taxa, provenance chain incl. page/volume/run,
own locality vs. entry place, absence records, observations by family, taxa by
habitat, persons by role).
