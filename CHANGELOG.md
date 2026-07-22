# Changelog

Alle wesentlichen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Added

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
