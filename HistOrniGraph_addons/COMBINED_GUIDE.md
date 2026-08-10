# HistOrniGraph add-ons — combined guide

Two toolsets that chain together. Both verified working end-to-end.

## Layout

```
HistOrniGraph_addons/
├── build_corpus.py              # CLI: text corpus (+ --multimodal / --report / --only)
├── build_multimodal_corpus.py   # CLI: multimodal catalogue only
├── laubmann_corpus/             # importable package (loading, entries, stream, render, corpus, multimodal, report, ids)
├── README_corpus.md             # corpus builder docs
├── CHANGELOG_corpus.md          # what changed vs the old build_corpus.py
└── dedup/
    ├── laubmann_dedup.py        # importable core (normalization, fingerprints, scoring, clustering, quality)
    ├── detect_duplicates.py     # CLI → duplicates_report + quality_report
    ├── build_review_gui.py      # CLI → self-contained review.html
    ├── apply_dedup.py           # CLI → new deduped corpus + manifest (non-destructive)
    ├── md_to_corpus.py          # rebuild corpus.json from by_volume/*.md if only markdown synced
    ├── test_laubmann_dedup.py   # 13 unit tests
    ├── README_dedup.md
    └── METHODS.md               # root-cause analysis + validation metrics
```

## How they connect

`build_corpus.py` writes `corpus.json` with stable `page_uid` / `region_uid` /
`entry_uid`. `detect_duplicates.py` reads that same `corpus.json`. `apply_dedup.py`
writes a new `corpus_*_dedup/`. The dedup tools read `volume` / `page_id` / `scan` /
`page_number` / `regions[].text` / `entry_starts`, so they work whether or not the
UID fields are present — but the UIDs are what let the index-linking and KG stages
join everything without re-parsing markdown.

## One-command corpus build

```bash
python build_corpus.py \
  --output-base "…/HistOrniGraph_output" \
  --corpus-dir  "…/HistOrniGraph_output/corpus_2026-07-22" \
  --per-volume --multimodal --report --volumes $(seq 1 34)
```

`--multimodal` and `--report` now ADD their outputs to a normal run. Use
`--only text|report|multimodal` to isolate a single phase.

## Dedup workflow

```bash
python dedup/detect_duplicates.py CORPUS/corpus.json -o CORPUS/dedup \
    --scan-window 3 --cluster-threshold 0.55 --high-threshold 0.80 \
    --image-root "…/HistOrniGraph_output"
python dedup/build_review_gui.py CORPUS/dedup/duplicates_report.jsonl \
    --corpus CORPUS/corpus.json -o CORPUS/dedup/review.html
# student reviews review.html → exports dedup_decisions.json
python dedup/apply_dedup.py --corpus-dir CORPUS \
    --decisions CORPUS/dedup/dedup_decisions.json --out-dir CORPUS_dedup
```

## Applied fix

`build_corpus.py` originally treated `--report` and `--multimodal` as mutually
exclusive (each returned early), so `--multimodal --report` silently skipped the
multimodal build. They are now independent phases; `--only` isolates one.

## Deps

- corpus builder: standard library only
- dedup: `rapidfuzz`, `datasketch` (core); `imagehash`, `pillow` (optional image layer)

## Integration fix (Agent 1 ↔ Agent 2 seam)

Agent 2's `apply_dedup.py` was written against the *old* monolithic
`build_corpus.py`, importing `find_entry_starts` / `strip_markup` from it. Agent
1's refactor moved those into `laubmann_corpus/entries.py`, so the import failed
silently and the deduplicated corpus was written **without regenerated
`entries.jsonl` / `entries.csv`**. Fixed: `apply_dedup.py` now imports from
`laubmann_corpus.entries` first, falling back to the old top-level `build_corpus`
import. It adds the add-ons root to `sys.path` itself, so it resolves from any
working directory. Verified: after the fix, apply reports "N pages, M entries"
and writes `entries.*`.
