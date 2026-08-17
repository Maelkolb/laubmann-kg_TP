# Changelog

Alle wesentlichen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Changed (2026-08-17 — Extraktion ohne Heuristiken, Modell liest den Eintrag)

Leitprinzip: das Modell entscheidet den INHALT, der Code prüft nur die FORM (Vokabular-Mitgliedschaft, Datentypen, SHACL-Sicherheit, Autoritäten-Links). Was der Text nicht sagt, bleibt weg — keine Default-Evidenz, keine Platzhalter, keine injizierten Verhaltensweisen, keine Schlüsselwort-Regeln über Inhalt. Prompt-Änderung ⇒ vollständiger Live-Lauf (der Cache war seit der Adolf→Alfred-Korrektur ohnehin ungültig; alter Cache bleibt unter `llm_cache/`, neuer Lauf nutzt `llm_cache_v2/`).

- **Prompt/Schema (`prompts/observation_extraction.md`, `schemas/*.json`).** Das Modell bekommt zusätzlich `date_verbatim` und die Warnung, dass `date_iso`/`location_header` aus der Segmentierung stammen (Routen, Höhenangaben, Attributions-Tags "(Kiefer)", Prosafragmente, "19.III. 85.)" = laufende Artnummer). Es liefert jetzt auf Eintragsebene `entry_date {iso, end_iso, plausible, note}` (Datumskorrektur mit Audit-Spur), `entry_place {name, verbatim, kind}` (moderner Standardname; `settlement|locality|region|route|unknown`) und `entry_kind` (`field-day|species-digest|retrospective|correspondence|other`). Pro Beobachtung neu: `taxon_rank` (+ wissenschaftlicher Name AUF DIESEM RANG, z. B. "Limosa"), `is_bird`, `occurrence_status` (`absent` für "keine Schwalben mehr"), `individual_count ≥ 0` + `count_min/count_max` für Spannen, `locality {name, verbatim}` (Ort DIESES Nachweises, wenn er vom Eintragsort abweicht), `sex`, `life_stage`, `breeding_evidence` (Atlas-Kategorien confirmed/probable/possible), `vitality`, `movement_kind` + `flight_direction`, `identification_qualifier` (Hedge des Tagebuchschreibers, getrennt von der Modell-`confidence`), `event_date`/`event_time` (eigenes Datum/Uhrzeit von Digest-Zeilen); `evidence` NUR wenn der Text sagt wie (nie Default `visual`), `habitat` = Biotoptyp (nie Ortsname), `observer` exakt wie in `persons` geschrieben. Optionale leere Schlüssel werden weggelassen (Token-Ökonomie).
- **Mapper (`extraction/llm_observations.py`) — reine Formprüfung.** Enum-Felder nur per Mitgliedschaft (`vocab.normalize_enum`), nie aus Prosa geraten; keine Default-Evidenz mehr, kein `callTranscription`-Platzhalter "Ruf", kein injiziertes "Brüten" bei Nest-Evidenz; `record_type` des Modells bleibt (Widerspruch zu Beobachter/Zitat → Flag `record_type_conflict` statt stillem Umschreiben); Resolver-IRI nur für den Resolver-eigenen Binomialnamen; `_text` akzeptiert nur Strings; Diarist-Aliasse exakt (kein Substring — "Frau Laubmann" bleibt Person). Neue Mapper `map_entry_place`/`map_entry_date`; Beobachtungsort = eigene `locality`, sonst Eintragsort.
- **Orte.** `normalization/places.py`: neues `lookup_coordinates(name)` (Gazetteer liefert NUR Koordinaten für den vom Modell benannten Ort); die Regex-Kopfzeilenreinigung (`normalize_place`) bleibt für das Offline-Backend und als Fallback für Legacy-Antworten ohne `entry_place`. `pipeline.py`: `entry.place` kommt vom Modell; `result.places` aus Eintrags- und Beobachtungsorten.
- **QA (`qa.py`) — Schwellen statt Schlüsselwörter.** `plausible_bird`/`_BIRD_MORPHEMES` gelöscht (hatten Limose, Spötter, Kormoran, Kreuzschnabel, Uhu … ausgeschlossen: 892 Beobachtungen im letzten Lauf). Neu: `non_bird` (Modell: kein Vogel → Ausschluss, `exclude_non_bird`), `low_confidence_taxon` (kein Name, Rang unbekannt UND ausdrücklich niedrige Modell-Konfidenz < `min_taxon_confidence` 0.3), `implausible_date` (Modell: Datum widersprüchlich → Ausschluss), `date_corrected`, `record_type_conflict`; `misdate` ist jetzt Flag (Ausschluss nur mit `exclude_misdate: true`, nie für Digest/retrospektive Einträge — der Median±2-Test tötete echte Sammlungsbelege wie den Sperbereulen-Eintrag von 1859); `nonplace` keyt auf den Modell-Ort.
- **Zitat-Regex entfernt** (`extraction/citations.py`, feuerte auf 61/9.527 Einträge und stempelte "Quellenangabe: …" auf ALLE Beobachtungen des Eintrags); vollständig ersetzt durch `record_type`/`observer`/`literature_citation` pro Beobachtung. `DiaryEntry.citations` entfernt.
- **`sample.limit`** (Config) für Smoke-Tests: nur die ersten N Einträge; `ExtractionResult.provenance` (Backend, Modell, Prompt-SHA256, Startzeit, Methode) speist PROV und DwC-A.
- **Ontologie 0.3.0 (`ontologies/laubmann.ttl`)**: `lkg:ObservationEvent ⊑ dwc:Occurrence` (statt dwc:Event; DiaryEntry ⊑ dwc:Event passend zum Event-Core), `observedTaxon ⊑ dwciri:toTaxon` (dwciri:taxon existiert nicht), `observedAt ⊑ dwciri:inDescribedPlace` gestrichen (falscher Domänenbereich), `Place ⊑ geo:SpatialThing, dcterms:Location`, `Habitat ⊑ skos:Concept` (war fälschlich Place) + `lkg:habitatScheme`, `containsObservation owl:inverseOf derivedFromEntry`, `entryDate ⊑ dwc:eventDate`, Ranges `rdf:langString` wo emittiert; 18 neue Properties (entryPlace, hasLocality, entryKind, entryDateEnd, dateNote, datePlausible, individualCountMin/Max, breedingEvidence, movementKind, flightDirection, evidenceKind, matchMethod, matchConfidence, gbifMatchType, isBird, placeKind, backend); Header mit Lizenz/Creator/versionIRI; @de-Labels überall.
- **RDF-Emission (`kg/rdf.py`)**: Darwin-Core-Terme werden neben den lkg-Termen mitemittiert (`dwc:individualCount`, `dwc:occurrenceStatus` — jetzt auf der Beobachtung, nicht am Evidenzknoten —, `dwc:sex/lifeStage/vitality/identificationQualifier/reproductiveCondition/behavior/habitat/eventDate/eventTime/vernacularName/taxonRank/decimalLatitude/decimalLongitude/geodeticDatum`, `dwciri:recordedBy/habitat`); Evidenz verweist per `lkg:evidenceKind` auf die SKOS-Konzepte; PROV-Skelett (`prov:Activity` pro Lauf mit Modell/Prompt-Hash/Startzeit, `prov:SoftwareAgent`, `prov:wasGeneratedBy` an jeder Beobachtung/Reise/Wetter); `dcterms:identifier` an Eintrag/Seite, Seite `dcterms:isPartOf` Band, `lkg:hasSourceRegion`; Taxon mit `rdfs:label`, Match-Provenienz; `geo:`-Präfix wieder WGS84 (statt `geo1:`).
- **SHACL (`ontologies/shacl_shapes.ttl`)**: `callTranscription` optional (kein erzwungener Platzhalter), `hasEvidence` max 4 ohne min, `individualCount ≥ 0`, neue Property-Shapes (sh:in) für alle neuen Vokabulare, HabitatShape eigenständig, ExtractionRunShape; Header ohne `-i rdfs`. **SKOS-Vokabulare**: 9 neue Schemes (occurrenceStatus, sex, lifeStage, breedingEvidence, vitality, movementKind, taxonRank, placeKind, entryKind) + habitatScheme, @de-Labels; ein Test hält sie mit `vocabularies.py` synchron. JSON-LD-Kontext 1.1 mit allen Termen; Kontextpfad repo-relativ.
- **DwC-A (`dwca/`)**: `event.txt` mit `verbatimLocality`, `geodeticDatum`, Ort/Koordinaten aus dem Modell-Eintragsort; `occurrence.txt` mit kingdom/class/taxonRank, `individualCount` 0 bei Absenzen, `organismQuantity(+Type)` für Spannen, `occurrenceStatus`, sex/lifeStage/reproductiveCondition/vitality/behavior, identificationQualifier, eigener locality/eventDate/eventTime, habitat, dynamicProperties; MoF → **OBIS ExtendedMeasurementOrFact** (mit `occurrenceID`, eindeutigen `measurementID`s, `measurementTypeID`/`measurementValueID` auf die SKOS-Schemes/Konzepte, `measurementMethod` aus der Provenienz); `meta.xml` mappt `eventID` explizit als Term neben `<id>`; `ac:subjectPart` (kein Simple-Multimedia-Term) entfernt; EML mit konfigurierbarem Titel/packageId, Kontakt, Lizenz-`ulink`, zeitlicher/geographischer/taxonomischer Abdeckung, Methoden-Absatz; Validator prüft die neuen Regeln.
- **Linking (`linking/taxa.py`)**: Modell-Namen auf Gattungs-/Familienrang werden als EXACT/FUZZY-Treffer akzeptiert, wenn GBIF denselben Rang liefert (das Taxon IST die Gattung); Nicht-Vögel ohne `class=Aves`-Filter (eigener Cache-Key); Folk-Name-Proposer erhält `thinking_level` (Config `low`) und `max_output_tokens` 1024 (statt 256).
- **LLM-Client (`llm/clients.py`)**: abgeschnittene Antworten (`finish_reason MAX_TOKENS`) werden NICHT gecacht (nächster Lauf holt sie neu), leere Antworten werden retried; Cache-Record enthält die Generierungsparameter (Key unverändert = sha256(model, prompt)); `extraction.max_output_tokens` 16384.
- **Colab-Notebook `notebooks/07_full_workflow_colab.ipynb`**: frische `EXPORTS_DIR` pro Lauf (`kg_exports_<tag>`), Linking-Caches und Review-CSVs auf Drive (`linking_cache/`, `<exports>/review/`), `git checkout -- configs/full_llm.yaml` vor jedem Pull, Assert auf die Linking-Stufe, `pip -U google-genai`, Smoke-Test-Zelle (25 Einträge live via `sample.limit`), Review-Download-Zelle, erweiterte Coverage-Zelle, Log-Filter für die 9,5k Fortschrittszeilen.
- Tests 125 → 171 (neu: `test_entry_reading.py`, `test_rdf_emission.py`, `test_dwca_v2.py`, erweiterte QA-/Linking-/Cache-Tests). Offline-Replay der 9.527 gecachten Antworten vom 12.08. durch die neue Kette: 0 Mapper-Fehler, SHACL konform.

### Added

- **Provenienz pro Beobachtung (Nachweistyp/Beobachter/Zitat) im selben LLM-Pass.** Observation-Schema um `record_type`/`observer`/`literature_citation` erweitert (alte gecachte Antworten bleiben gültig); der Mapper faltet deutsche Antworten aufs Vokabular (`normalize_record_type`), leitet fehlende Typen aus Zitat/Beobachter ab, repariert Widersprüche und löst Beobachternamen gegen `entry.persons` auf (Nachname-Match, Diarist-Aliasse wie "(Lbm.)" → kein Beobachter). Emission: `lkg:recordType`, abgeleitetes `dwc:basisOfRecord` (HumanObservation/PreservedSpecimen/MaterialCitation via `vocabularies.basis_of_record`, geteilt mit dem DwC-A-Export), `lkg:observedBy` (Default Alfred Laubmann nur bei Feldbeobachtungen — unattribuierte Fremd-/Literaturnachweise bekommen KEIN observedBy), `dwc:associatedReferences`. DwC-A: `recordedBy` provenienzbewusst, neue Spalten `associatedReferences`/`taxonID` (append-only).
- **Wetter auf Eintragsebene.** Neues Top-Level-Feld `weather` im Entry-Schema (Objekt oder Bare-String), toleranter Mapper `extraction/weather.py` (Verbatim ist primär und Pflicht; Temperatur nie einheitenkonvertiert, Réaumur bleibt Réaumur; Niederschlag/Himmel per Cue-Faltung auf kontrollierte Vokabulare). Neue Klasse `lkg:WeatherReport` + Properties in `laubmann.ttl`, SHACL-Shapes (`WeatherReportShape`, `NoOrphanWeatherShape`), SKOS-Schemes, DwC-A-Event-Spalten `eventRemarks`/`dynamicProperties` (append-only).
- **Externes Entity-Linking (GBIF-Backbone + Wikidata) als eigene Pipeline-Stufe** (`src/laubmann_kg/linking/`, Config-Sektion `linking`, default aus; CLI `link-entities`). Taxa: Resolver-Namen (und für unaufgelöste Vernakularnamen LLM-Vorschläge über das reaktivierte `prompts/taxon_normalization.md` + tolerantes `schemas/taxon_normalization.schema.json`) werden IMMER gegen `species/match` verifiziert — externe Keys/Namen kommen nur von GBIF, nie vom LLM (EXACT ≥ 90 / FUZZY ≥ 95, Rang-Gate SPECIES/SUBSPECIES, Synonym → `acceptedUsageKey`, Resolver+HIGHERRANK → `skos:broadMatch` ohne `taxonID`; LLM-verifizierte Backfills bekommen `match_method="llm+gbif"` → `skos:closeMatch`). Personen: Wikidata `wbsearchentities` mit Hochpräzisions-Auto-Regel (≥ 2 Tokens nach Titel-Stripping, eindeutiger Exakt-Label-Treffer, P31=Q5-Human-Check; alles andere → Review — der Top-Treffer für "Walter Wüst" ist ein Politiker, nicht der Ornithologe). Emission: `Taxon.gbif_key`/`gbif_match_type`/`gbif_canonical_name` → `skos:exactMatch`/`closeMatch`/`broadMatch` + `dwc:taxonID`; `Person.wikidata_iri` → `owl:sameAs`. Ontologie-Version 0.2.0. Betrieb: resumable JSON-Caches (`data/cache/linking/`, Fehlschläge nie gecacht, atomare Writes, Flush alle 25), Review-CSVs `taxon_link_review.csv`/`person_link_review.csv` (Spalte `decision`, nutzungssortiert; adjudizierte CSVs fließen über `reviewed_csv` zurück, Decision-Kontrakt y/yes/merge/1) — auch bei Teilläufen geschrieben (finally-Block); Linking bricht die Pipeline nie ab.

### Changed

- **QA: Reason-Split für leere Einträge.** Einträge ohne Beobachtung, aber mit Wetter ODER Reise, werden jetzt als `no_observations` geflaggt (vorher `empty`); `empty` bleibt für Einträge ohne alles. Betroffen sind auch reine Reise-Einträge (Relabel `empty` → `no_observations`). Weiterhin nur geflaggt, nie ausgeschlossen.

### Added

- **Extraktion auf Eintragsebene erweitert: Reisen, Personen, Habitat in einem LLM-Pass.** Das Antwortformat ist jetzt ein Objekt `{observations, travel_events, persons}` (`schemas/entry_extraction.schema.json`; Observation-Schema um `habitat` ergänzt und weiterhin single-source). Der Prompt (`prompts/observation_extraction.md`) gibt dem Modell die volle Leseverantwortung; die Korrektheit sichert das Mapping: Transportmodi werden auf das SHACL-Vokabular gefaltet (`normalize_transport_mode`), Uhrzeiten nur bei Konsistenz mit dem Eintragsdatum zu `xsd:dateTime` kombiniert, Legs ohne beide Endpunkte verworfen (Abfahrt erbt Vor-Leg-Ankunft bzw. Eintragsort), Events ohne Legs verworfen. Neue Domänenklassen `TravelEvent`/`TravelLeg`/`Person`/`Habitat` (`kg/model.py`), RDF-Emission über `lkg:containsTravelEvent`/`hasLeg`/`departurePlace`/`arrivalPlace`/`viaPlace`/`transportMode`/`departureTime`/`arrivalTime`, `lkg:hasHabitat` (+ `dwc:habitat`) und neu `lkg:mentionsPerson` (⊑ `schema:mentions`, in `ontologies/laubmann.ttl` ergänzt). Alte Array-Antworten (Cache/Konfig) werden weiter akzeptiert. `configs/full_llm.yaml`: `max_output_tokens` 8192. Tests: Mapping, Zeit-/Endpunkt-Sanitisierung, Legacy-Kompatibilität, End-to-End-SHACL-Konformität (`tests/test_travel_extraction.py`).

- **HistOrniGraph-Add-ons ins Repo integriert** (`HistOrniGraph_addons/`): Korpus-Builder (`build_corpus.py` + `laubmann_corpus/`-Paket) und Dedup-Toolchain (`dedup/`: Erkennung, Review-GUI, nicht-destruktives Anwenden, 13 Unit-Tests). Damit läuft der komplette Workflow Korpus → Dedup → KG aus einem Klon.
- `apply_dedup.py` regeneriert `entries.csv` jetzt über `laubmann_corpus.stream` (identische Segmentierung wie der Builder) und schreibt damit auch `entry_uid`/`page_uid`/`region_uid` + Provenienz-Spalten — ohne diese kollabierten alle Einträge im KG auf eine einzige Entry-URI. Zusätzlich tolerant gegenüber `id`/`region_id`-Schreibweisen und Warnung bei Decisions ohne `drop`-Liste.
- `configs/full_llm.yaml`: 34-Bände-Lauf gegen das deduplizierte Korpus (`sample.volume: null`), Gemini-Backend, QA an.
- `extraction.cache_dir` konfigurierbar (LLM-Cache z. B. auf Drive für unterbrechungsfeste Colab-Läufe).
- Colab-Notebooks in `notebooks/`: `05_corpus_dedup_colab` (Korpus + Dedup), `06_kg_book2_colab` (Band-2-KG-Lauf), `07_full_workflow_colab` (alle 34 Bände end-to-end: Korpus → Dedup-Review → KG + DwC-A + CQ-Check).

### Changed (Dedup-Integration)

- `configs/sample_llm.yaml`: Extraktionsmodell auf `gemini-3.5-flash` (synchron mit `configs/models.yaml`); vorher musste das Notebook das Modell zur Laufzeit patchen.

- **LLM-Extraktions-Backend (Gemini) an die Pipeline angebunden.** `extraction/llm_observations.py` rendert den Prompt pro Eintrag, ruft einen gecachten Gemini-Client (Temperature 0, JSON-Ausgabe) und mappt die strukturierte Antwort auf SHACL-konforme `Observation`-Objekte; wissenschaftliche Namen werden gegen den Resolver abgesichert, Taxon-IRIs nie erfunden. Umschaltung über `extraction.backend: llm` (`configs/sample_llm.yaml`), Provider-Adapter `GeminiClient` in `llm/clients.py`, optionales Extra `[llm]` (`google-genai`). Verdrahtung/Mapping offline mit Fake-Client getestet; Live-Läufe brauchen `GOOGLE_API_KEY`.
- **Korpus→KG-Builder (erster End-to-End-Lauf auf Vol.-2-Sample).** Deterministische, netzwerkfreie Extraktion und Export gemäß bestehender Ontologie/SHACL.
- `pipeline.py`: lädt den Korpus (`entries.csv` + `multimodal.md`), baut Domänenobjekte, führt Extraktion aus; Sample→Volltext ist reine Konfigsache (`configs/sample.yaml`).
- Domänenmodell `kg/model.py` als Dataclasses gespiegelt zu `laubmann.ttl`; inhaltsadressierte, reproduzierbare UIDs.
- Regelbasierte Extraktion: `extraction/observations.py` (Taxa-Gazetteer-Matching, Evidenz-/Ruf-/Zähl-/Verhaltensheuristik), `extraction/entities.py`, `extraction/citations.py`.
- Normalisierung: `normalization/{dates,places,persons,taxa}.py`; deutscher Vogel-Gazetteer und `TaxonResolver`-Interface mit Offline-Seed- und `links_long`-Implementierung (nie erfundene Taxon-IRIs).
- LLM-Infrastruktur: `llm/{cache,retry,structured_output,prompts,clients}.py` — inhaltsgehashter On-Disk-Cache, deterministischer Retry, jsonschema-Validierung, Offline-Client als Default.
- KG-Export: `kg/{rdf,jsonld,sparql}.py` und Orchestrierung in `kg/__init__.py` — Turtle + JSON-LD, SHACL-validiert (0 Violations auf dem Sample).
- DwC-A-Export: `dwca/{event,occurrence,measurement_or_fact,multimedia,meta_xml,archive,validate}.py` — Event-Core-Sternschema (Event + Occurrence + MeasurementOrFact + Multimedia), gezippt und strukturell validiert.
- `io/{csv,json,metadata}.py`: toleranter `entries.csv`-Reader und `multimodal.md`-Parser (auch `multimodal.csv`).
- Ausgefüllte JSON-Schemas, JSON-LD-Kontext, Prompt-Vorlagen (Observation/Entity/Taxon) und SKOS-Controlled-Vocabularies (Spiegel der `sh:in`-Listen).
- Neue/erweiterte Tests: Datumsnormalisierung, Taxa-Matching/Resolver, Extraktion, Pipeline-Determinismus, LLM-Cache/Retry, SHACL-valider JSON-LD-Export, valider DwC-A.
- Dokumentation: `docs/data_model.md`, `docs/competency_questions.md`, `STATUS.md`, `INTERFACES.md`.
- Abhängigkeiten `rdflib`, `pyshacl`, `jsonschema` in `pyproject.toml`.

### Changed

- `configs/dwca.yaml` auf Event-Core-Layout aktualisiert (ein Core + drei Extensions, Join über `eventID`).
- Platzhalter-Tests für Export-Stages durch echte End-to-End-Tests ersetzt.

- Python-Paket `laubmann_kg` mit `src`-Layout und `pyproject.toml` (Hatchling, Python ≥ 3.10)
- Typer-CLI `laubmann-kg` mit acht Pipeline-Befehlen: `preprocess`, `detect-layout`, `detect-entries`, `transcribe`, `extract-observations`, `export-jsonld`, `export-dwca`, `evaluate`
- Gemeinsame CLI-Optionen `--config`, `--input-dir`, `--output-dir` für alle Stages
- Paketstruktur mit Modulen für `io`, `preprocessing`, `llm`, `layout`, `diary`, `transcription`, `extraction`, `normalization`, `kg`, `dwca`, `evaluation` und `review`
- Stage-Orchestrierung über `run(config, input_dir, output_dir)` in den jeweiligen Subpackages
- Zentrale Logging-Konfiguration (`logging_config.py`) mit strukturierten Log-Ausgaben
- Konfigurationsdateien unter `configs/` (`pipeline.yaml`, `models.yaml`, `ontology.yaml`, `dwca.yaml`, `prompts.yaml`)
- Datenverzeichnis-Struktur unter `data/` (raw, processed, annotations, exports, cache) mit `.gitkeep`
- Dokumentations-Stubs unter `docs/`
- Prompt-Vorlagen unter `prompts/`
- JSON-Schema-Stubs unter `schemas/`
- Ontologie-Stubs unter `ontologies/` (Turtle)
- Jupyter-Notebooks für Exploration und Evaluation unter `notebooks/`
- Stage-Runner-Skripte unter `scripts/`
- Erste Tests unter `tests/` (Schema-Validierung, Placeholder für Export-Stages)
- `README.md`, `.gitignore`, `.env.example`
- Dev-Abhängigkeiten: `pytest` (optional via `[dev]`)

### Changed

- Flache Stage-Module (`preprocess.py`, `detect_layout.py` usw.) in thematische Subpackages überführt
- CLI importiert Stage-Funktionen aus den neuen Subpackages (`preprocessing`, `layout`, `diary` usw.)
- `.cursorrules`: Regel ergänzt, dass der Nutzer Commits selbst pusht

## [0.1.0] - 2026-06-18

### Added

- Erstes Projekt-Scaffolding und CLI-Grundgerüst

[Unreleased]: https://github.com/desyLoyz/laubmann-kg/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/desyLoyz/laubmann-kg/releases/tag/v0.1.0
