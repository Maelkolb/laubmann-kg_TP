# laubmann-kg

Pipeline for digitizing, transcribing, and publishing the Laubmann ornithological diary as a knowledge graph and Darwin Core Archive.

## Layout

- `configs/` — pipeline, model, ontology, DwC-A, and prompt configuration
- `HistOrniGraph_addons/` — corpus builder (`build_corpus.py`, `laubmann_corpus/`) and page-dedup toolchain (`dedup/`)
- `notebooks/` — evaluation notebooks + Colab workflows (`07_full_workflow_colab.ipynb` runs corpus → dedup → KG for all 34 volumes)
- `data/` — raw scans, processed images, annotations, exports, and LLM cache
- `docs/` — methodology, data model, and evaluation documentation
- `prompts/` — LLM prompt templates per pipeline stage
- `schemas/` — JSON schemas for intermediate and export artifacts
- `ontologies/` — project ontology and SHACL shapes
- `src/laubmann_kg/` — Python package
- `scripts/` — stage runner scripts
- `tests/` — unit and integration tests

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## CLI

```bash
laubmann-kg --help
laubmann-kg preprocess --config configs/pipeline.yaml --input-dir data/raw/vol01/images --output-dir data/processed/vol01/images
```

## Full 34-volume workflow (Colab)

Open `notebooks/07_full_workflow_colab.ipynb` in Colab. It mounts Drive and runs:

1. **Corpus build** — `HistOrniGraph_addons/build_corpus.py` over the `Laubmann_NN_gemini/` region JSONs
2. **Dedup** — `dedup/detect_duplicates.py` → human review via `review.html` → `dedup/apply_dedup.py` writes `corpus_*_dedup/` (non-destructive, manifest of every dropped page)
3. **Knowledge graph** — `laubmann-kg export-jsonld / export-dwca --config configs/full_llm.yaml --input-dir <corpus_dedup>` (Gemini extraction, SHACL-validated, resumable via the on-Drive LLM cache)

## Pipeline stages

1. `preprocess` — split, deskew, enhance, and crop page images
2. `detect-layout` — detect layout regions and reading order
3. `detect-entries` — detect and link diary entries
4. `transcribe` — transcribe text from regions
5. `extract-observations` — extract structured observations
6. `export-jsonld` — export JSON-LD knowledge graph
7. `export-dwca` — export Darwin Core Archive
8. `evaluate` — compare outputs to gold annotations
