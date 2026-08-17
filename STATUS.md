# STATUS

First end-to-end knowledge-graph build on a fixed sample. Numbers below are
**real**, from the Vol. 2 run — not projected. The full 34-volume build is
deferred until the deduplicated corpus is available (switching is a config path
change; see `INTERFACES.md`).

## Sample run (Vol. 2, offline rule-based extraction)

Command:

```bash
laubmann-kg export-jsonld --config configs/sample.yaml --input-dir data/corpus --output-dir data/exports
laubmann-kg export-dwca   --config configs/sample.yaml --input-dir data/corpus --output-dir data/exports
```

| Metric | Value |
|---|---|
| Diary entries (all dated) | 233 |
| Entries yielding ≥1 observation | 211 (90.6%) |
| Observations | 1158 |
| Distinct taxa | 78 (all resolved to a scientific name via seed gazetteer) |
| Observations with a place | 1156 (99.8%) |
| Observations with an integer count | 474 |
| Observations with a count qualifier | 596 |
| Bird-call (auditory) evidence records | 309 |
| Nest evidence / breeding behaviour | 139 |
| Specimen evidence | 1 |
| Multimodal regions joined (DwC-A multimedia) | 15 |
| RDF triples | 16,965 |
| **SHACL** | **0 violations**, 22 warnings |
| DwC-A | event=233, occurrence=1158, measurementOrFact=2071, multimedia=15 — **valid** |

The 22 SHACL warnings are the 22 entries with no matched bird name (weather- or
travel-only text, or a species outside the seed gazetteer) — a recall limit of
the deterministic extractor, not a data error. All are `sh:Warning`, so the
graph conforms.

## Competency questions

| ID | Answerable? | Note |
|---|---|---|
| CQ1 species frequency | yes | |
| CQ2 observations by date | yes | 207 distinct dates in sample |
| CQ3 species at a place | yes | by locality label; coords partial |
| CQ4 auditory observations | yes | 309 bird-call records |
| CQ5 unresolved taxa | yes | returns 0 in sample (gazetteer covers all matches) |
| CQ6 provenance | yes | entry date + page per observation |
| Travel / route questions | blocked | travel extraction is future work |
| Cross-dataset taxon IRIs | blocked | needs `links_long` (see INTERFACES.md) |

## Ontology coverage

`populated` = emitted by the sample build; `partial` = supported/validated but
sparsely or conditionally populated; `not yet` = modelled + SHACL-validated but
not produced by current extraction.

### Classes

| Class | Status |
|---|---|
| `lkg:DiaryVolume` | populated |
| `lkg:DiaryPage` | populated |
| `lkg:DiaryEntry` | populated |
| `lkg:SourceRegion` | not yet (region provenance kept in DwC-A multimedia) |
| `lkg:ObservationEvent` | populated |
| `lkg:Taxon` | populated |
| `lkg:Place` | populated (coords partial) |
| `lkg:Habitat` | not yet |
| `lkg:ObservationEvidence` | populated |
| `lkg:BirdCall` | populated |
| `lkg:BehaviourNote` | populated |
| `lkg:TravelEvent` / `lkg:TravelLeg` / `lkg:Route` | not yet |
| `lkg:TimeEstimate` | not yet |
| `lkg:Person` | partial (extracted in `entities`, not yet emitted to RDF) |

### Properties

| Property | Status |
|---|---|
| `lkg:hasVolume`, `lkg:hasPage` | populated |
| `lkg:entryDate`, `lkg:rawText` | populated |
| `lkg:containsObservation` | populated |
| `lkg:observedTaxon`, `lkg:derivedFromEntry` | populated |
| `lkg:observedAt` | populated |
| `lkg:verbatimNotes` | populated |
| `lkg:individualCount`, `lkg:countQualifier` | populated |
| `lkg:hasEvidence`, `lkg:hasBehaviour` | populated |
| `lkg:callType`, `lkg:callTranscription` | populated |
| `lkg:vernacularNameDE` | populated |
| `lkg:scientificName` | populated (gazetteer; no external IRIs yet) |
| `lkg:verbatimLocality`, `geo:lat`, `geo:long` | partial |
| `lkg:containsTravelEvent`, `lkg:hasLeg`, travel/route/time props | not yet |
| `lkg:hasHabitat` | not yet |
| `lkg:observedDuring`, `lkg:hasTimeEstimate` | not yet |

## Dedup toolchain (integrated 2026-08-10)

The corpus/dedup add-ons now live in `HistOrniGraph_addons/` in this repo
(corpus builder + duplicate detector + review GUI + non-destructive apply;
13 unit tests, all passing). `apply_dedup.py` regenerates `entries.csv` with
the same segmentation and `entry_uid`/`page_uid`/`region_uid` derivation as
the builder, so the deduped corpus drops straight into the KG stage
(`--input-dir corpus_*_dedup`). Verified locally end-to-end on a synthetic
corpus: build → detect → decisions → apply → `export-jsonld` (SHACL: 0/0).

Remaining human step: adjudicate `review.html` for the full corpus and export
`dedup_decisions.json` (see `notebooks/07_full_workflow_colab.ipynb`, stage B).

## Current state (2026-08-17)

- Extraction is **model-driven, heuristics removed** (see CHANGELOG 2026-08-17):
  the LLM reads entry date/place/kind and every observation detail (locality,
  rank, absence, counts/ranges, sex, life stage, breeding evidence, vitality,
  movement, hedges, own date/time, provenance); code checks form only. QA is
  threshold-based on model signals. Ontology 0.3.0, DwC co-emission, PROV run
  node, OBIS eMoF in the DwC-A. Structure diagrams: `docs/kg_structure.mmd`,
  `docs/pipeline.mmd`.
- Full 34-volume rerun: run `notebooks/07_full_workflow_colab.ipynb` (v2:
  Drive-resident caches for LLM + linking + review CSVs, smoke-test cell,
  fresh `kg_exports_<tag>` per run). The prompt changed, so the run is fully
  live (~2–3 h extraction + linking); the old `llm_cache/` is dead.
- Offline replay of the 9,527 cached 2026-08-12 responses through the new
  mapper → RDF → SHACL → DwC-A: 0 mapper errors, 68,990 observations, ~1.95 M
  triples, SHACL conformant.

## Deferred / not done

- Person/taxon variant merging inside the pipeline (today post hoc via
  `HistOrniGraph_addons/kg_enrich/dedup_entities.py`); Nominatim georeferencing
  as a `linking/places.py` stage (today post hoc `georef_places.py`).
- w3id namespace migration (prefix rewrite; all uids are content-addressed).
- Gemini structured output (`response_json_schema`) — would retire json-repair;
  needs a live A/B on ~50 entries.
- Travel legs in the DwC-A (`parentEventID` sub-events); `observedDuring`,
  Route/TimeEstimate emission.
- Avibase alignment (needs `links_long`).
- `preprocess` / `detect-layout` / `transcribe` stages remain stubs (handled
  upstream by HistOrniGraph, per the task brief).
- LLM extraction backend: **wired**. A Gemini provider adapter and an
  LLM extractor are connected via `extraction.backend: llm`
  (`configs/sample_llm.yaml`); calls are cached and run at temperature 0. The
  wiring/mapping is tested offline with a fake client; live runs need an API key
  (`pip install -e ".[llm]"`, set `GOOGLE_API_KEY`). OpenAI/Anthropic adapters
  are not yet added. No formal LLM-vs-gold evaluation harness yet
  (`evaluation/` modules remain stubs) — quality is currently judged by review.
- Live Gemini run on Vol. 2 (Colab, 2026-08): 233 entries → 1,573 observations,
  28,298 triples. The 6 `callTranscription` SHACL violations seen in that run
  came from an export made before da5739f (evidence URIs without the index
  suffix); since da5739f evidence URIs are unique, and since 2026-08-17
  `callTranscription` is optional (no placeholder), so re-exports validate clean.
