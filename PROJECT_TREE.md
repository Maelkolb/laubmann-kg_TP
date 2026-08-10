# Projektstruktur — laubmann-kg

Stand: 2026-08-10. Ausgeschlossen: `.git/`, `__pycache__/`, `.pytest_cache/`, `.venv/`.

```text
laubmann-kg/
├── HistOrniGraph_addons/      # Korpus-Builder + Dedup-Toolchain (siehe COMBINED_GUIDE.md darin)
│   ├── build_corpus.py
│   ├── build_multimodal_corpus.py
│   ├── laubmann_corpus/       # loading, stream, entries, render, corpus, multimodal, report, ids
│   └── dedup/                 # laubmann_dedup.py, detect_duplicates.py, build_review_gui.py,
│                              #   apply_dedup.py, md_to_corpus.py, METHODS.md, 13 Unit-Tests
├── .cursorrules
├── .env.example
├── .gitignore
├── CHANGELOG.md
├── INTERFACES.md              # Korpus- und links_long-Vertrag
├── PROJECT_TREE.md
├── README.md
├── STATUS.md                  # Ontologie-Abdeckung + Sample-Kennzahlen
├── pyproject.toml
│
├── configs/
│   ├── dwca.yaml
│   ├── models.yaml
│   ├── ontology.yaml
│   ├── pipeline.yaml
│   ├── prompts.yaml
│   ├── full_llm.yaml          # 34-Bände-Lauf gegen corpus_*_dedup (Gemini)
│   ├── sample_llm.yaml
│   └── sample.yaml            # Vol.-2-Sample; Umschalten auf Volltext nur hier
│
├── data/
│   ├── annotations/
│   │   ├── generated/.gitkeep
│   │   └── gold/.gitkeep
│   ├── cache/
│   │   └── llm/.gitkeep
│   ├── examples/
│   │   └── raw/
│   │       ├── jsonl/                          # (leer)
│   │       ├── md/                             # 8 Beispiel-Transkriptionen
│   │       │   ├── 52b78822-…_0067_L.md
│   │       │   ├── 52b78822-…_0067_R.md
│   │       │   ├── 52b78822-…_0068_L.md
│   │       │   ├── 900847d2-…_0046_L.md
│   │       │   ├── 900847d2-…_0046_R.md
│   │       │   ├── 900847d2-…_0047_L.md
│   │       │   ├── 900847d2-…_0047_R.md
│   │       │   └── 900847d2-…_0048_L.md
│   │       └── pagexml/                        # 8 PAGE-XML-Dateien (gleiche IDs)
│   ├── exports/
│   │   ├── dwca/.gitkeep
│   │   ├── jsonld/.gitkeep
│   │   └── rdf/.gitkeep
│   ├── processed/
│   │   └── vol01/images/.gitkeep
│   └── raw/
│       └── vol01/images/.gitkeep
│
├── docs/
│   ├── annotation_guidelines.md
│   ├── competency_questions.md
│   ├── data_model.md
│   ├── evaluation_plan.md
│   ├── methodology.md
│   ├── ontology_mapping.md
│   └── prompt_catalogue.md
│
├── notebooks/
│   ├── 01_explore_pages.ipynb
│   ├── 02_evaluate_layout.ipynb
│   ├── 03_evaluate_transcription.ipynb
│   ├── 04_evaluate_observation_extraction.ipynb
│   ├── 05_corpus_dedup_colab.ipynb        # Colab: Korpus bauen + Dedup
│   ├── 06_kg_book2_colab.ipynb            # Colab: Band-2-KG-Lauf (Gemini)
│   └── 07_full_workflow_colab.ipynb       # Colab: alle 34 Bände end-to-end
│
├── ontologies/
│   ├── controlled_vocabularies.ttl
│   ├── laubmann.ttl
│   └── shacl_shapes.ttl
│
├── prompts/
│   ├── citation_classification.md
│   ├── diary_entry_detection.md
│   ├── dwca_mapping.md
│   ├── entity_extraction.md
│   ├── jsonld_generation.md
│   ├── layout_detection.md
│   ├── observation_extraction.md
│   ├── region_transcription.md
│   ├── taxon_normalization.md
│   └── validation_repair.md
│
├── schemas/
│   ├── diary_entry.schema.json
│   ├── dwca_occurrence.schema.json
│   ├── jsonld_context.json
│   ├── observation.schema.json
│   ├── page_layout.schema.json
│   └── transcription.schema.json
│
├── scripts/
│   ├── evaluate_pipeline.py
│   ├── run_dwca_export.py
│   ├── run_extraction.py
│   ├── run_kg_export.py
│   ├── run_layout_detection.py
│   ├── run_preprocessing.py
│   └── run_transcription.py
│
├── src/
│   └── laubmann_kg/
│       ├── __init__.py
│       ├── cli.py
│       ├── logging_config.py
│       ├── pipeline.py             # Korpus → Modell → Extraktion (Stage-übergreifend)
│       ├── py.typed
│       ├── diary/
│       │   ├── __init__.py
│       │   ├── detect_entries.py
│       │   ├── link_entries_across_pages.py
│       │   ├── normalize_dates.py
│       │   └── normalize_places.py
│       ├── dwca/
│       │   ├── __init__.py
│       │   ├── archive.py
│       │   ├── event.py
│       │   ├── measurement_or_fact.py
│       │   ├── meta_xml.py
│       │   ├── multimedia.py
│       │   ├── occurrence.py
│       │   └── validate.py
│       ├── evaluation/
│       │   ├── __init__.py
│       │   ├── compare_to_gold.py
│       │   ├── metrics_extraction.py
│       │   ├── metrics_layout.py
│       │   ├── metrics_transcription.py
│       │   └── reports.py
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── behavior.py
│       │   ├── citations.py
│       │   ├── entities.py
│       │   ├── habitats.py
│       │   ├── observations.py
│       │   ├── quantities.py
│       │   └── weather.py
│       ├── io/
│       │   ├── __init__.py
│       │   ├── csv.py
│       │   ├── images.py
│       │   ├── json.py
│       │   └── metadata.py
│       ├── kg/
│       │   ├── __init__.py
│       │   ├── jsonld.py
│       │   ├── model.py
│       │   ├── rdf.py
│       │   ├── shacl_validate.py
│       │   └── sparql.py
│       ├── layout/
│       │   ├── __init__.py
│       │   ├── detect_regions.py
│       │   ├── reading_order.py
│       │   ├── region_models.py
│       │   └── visualize_regions.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── cache.py
│       │   ├── clients.py
│       │   ├── prompts.py
│       │   ├── retry.py
│       │   └── structured_output.py
│       ├── normalization/
│       │   ├── __init__.py
│       │   ├── dates.py
│       │   ├── persons.py
│       │   ├── places.py
│       │   ├── taxa.py
│       │   └── vocabularies.py
│       ├── preprocessing/
│       │   ├── __init__.py
│       │   ├── crop.py
│       │   ├── deskew.py
│       │   ├── enhance_images.py
│       │   ├── split_pages.py
│       │   └── thumbnails.py
│       ├── review/
│       │   ├── __init__.py
│       │   ├── export_review_table.py
│       │   └── import_review_decisions.py
│       └── transcription/
│           ├── __init__.py
│           ├── align_text_to_regions.py
│           ├── postcorrect.py
│           ├── transcribe_regions.py
│           └── uncertainty.py
│
└── tests/
    ├── conftest.py                 # sample_config-Fixture
    ├── fixtures/
    │   ├── .gitkeep
    │   ├── lkg_full.ttl
    │   └── sample_entries.csv       # Mini-Korpus für Offline-Tests
    ├── test_date_normalization.py
    ├── test_dwca_export.py
    ├── test_extraction.py
    ├── test_jsonld_generation.py
    ├── test_llm_cache.py
    ├── test_observation_schema.py
    ├── test_pipeline.py
    ├── test_region_schema.py
    └── test_taxa.py
```
