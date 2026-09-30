# Corpus builders

`build_corpus.py` turns the per-page `regions/*.json` files under each
`Laubmann_NN_gemini/` directory into a metadata-rich research corpus. It is a
thin CLI over the importable `laubmann_corpus` package; layout detection and
transcription are assumed done upstream. Standard library only — no install.

## Package layout

```
build_corpus.py              CLI: text corpus (+ --report / --multimodal)
build_multimodal_corpus.py   CLI: multimodal catalogue (== build_corpus --multimodal)
laubmann_corpus/
  loading.py     volume discovery, region loading, schema census
  entries.py     entry-header detection, date/location normalization + provenance
  stream.py      reading-order stream assembly, entry segmentation (scan-once)
  render.py      Markdown / txt renderers
  corpus.py      primary text corpus driver
  multimodal.py  non-body-text catalogue driver
  report.py      per-volume coverage report
  ids.py         content-addressed page_uid / region_uid / entry_uid
  boundaries.py  reviewed entry boundaries (missed headers, register stops)
dedup/apply_entry_boundaries.py   CLI: corpus_dedup + boundary CSV -> patched corpus
build_multimodal_regions.py       CLI: multimodal_regions.jsonl for the KG (lkg:MultimodalRegion)
```

Import surface for downstream tools:

```python
from laubmann_corpus import (
    build_text_corpus, build_multimodal_corpus, write_report,
    iter_volume_dirs, load_volume, region_uid, page_uid,
)
```

## Usage

```bash
# Primary text corpus (all volumes found under --output-base)
python build_corpus.py --output-base "/path/HistOrniGraph_output" \
                       --corpus-dir  "/path/HistOrniGraph_output/corpus"

# Restrict volumes, per-volume markdown, fold non-text descriptions into body
python build_corpus.py --volumes 1 5 9 --per-volume --include-nontext

# Higher-recall header detection (accept headers without a year)
python build_corpus.py --loose

# Coverage report only  →  corpus/report.{json,md}
python build_corpus.py --report

# Multimodal catalogue only  →  corpus/multimodal/multimodal.{jsonl,csv,md}
python build_corpus.py --multimodal
# equivalently:
python build_multimodal_corpus.py

# Skip the schema census sanity print
python build_corpus.py --no-census
```

Every run first prints a one-line-per-type **schema census** — the union of keys
seen per region type across a sample of volumes — as a sanity check that the
on-disk shape matches what the builder expects. Suppress with `--no-census`.

## Output artifacts

Primary text corpus (`corpus/`):

| file            | contents                                                        |
|-----------------|-----------------------------------------------------------------|
| `corpus.md`     | metadata-rich Markdown reconstruction, all volumes              |
| `corpus.json`   | structured page-by-page corpus + per-region entry starts        |
| `corpus.txt`    | flat text with page / entry markers (grep-friendly)             |
| `entries.jsonl` | one detected entry per line (full raw + cleaned text)           |
| `entries.csv`   | entry index (cleaned text + 120-char preview)                   |
| `by_volume/Laubmann_NN.md` | one Markdown file per volume (`--per-volume`)         |
| `report.{json,md}`         | per-volume coverage summary (`--report`)             |

Multimodal catalogue (`corpus/multimodal/`, `--multimodal`):

| file              | contents                                                      |
|-------------------|---------------------------------------------------------------|
| `multimodal.jsonl`| one non-body-text region per line                             |
| `multimodal.csv`  | flat catalogue                                                |
| `multimodal.md`   | browsable, inlines the crop image paths                       |

The multimodal catalogue covers every `ImageRegion`, `ObjectRegion`,
`GraphicRegion`, `MarginaliaRegion`, and any insert region — including folded
inserts (`insert_state == "folded"`), recorded with an empty description and
`folded: true` because they are physical objects worth cataloguing even though
they carry no readable text. Each region is linked to the nearest preceding
diary entry header in reading order (`entry_uid` / `entry_date_norm` /
`entry_location`), tying Laubmann's pasted-in photos, specimen sketches,
feathers, paper slips and marginal notes to the observation context they sit in.

## Joining corpora

`page_uid`, `region_uid` and `entry_uid` are content-addressed (SHA-1 over
salted inputs, 12 hex chars). They are stable across runs and identical wherever
the same page / region / entry appears, so Agents C and D can join
`entries.csv`, `corpus.json` and `multimodal.csv` on these keys without
re-parsing any Markdown. `entry_uid` in `multimodal.*` is exactly the
`entry_uid` of the linked entry in `entries.jsonl`.

## Entry-header detection

A header is a line-initial date with a year, e.g. `7. April 1917. <u>München</u>.`,
`30. Juli 1960. München.`, `26. I. 48 Karlsfeld`. The date is the anchor; the
location may be underlined or plain, and may be absent (date-only header). Dates
inside running prose are rejected. Normalization returns provenance
(`month_source`, `year_form`, `loc_source`) alongside the final `date_norm` /
`location_raw`, so ambiguous headers can be reviewed later. `--loose` also
accepts headers without a year (higher recall, lower precision).


## Patched corpus (ontology 0.6.0)

The date-anchored detector misses entries and glues every volume's register
onto its last entry. `data/corpus_patches/entry_boundaries.csv` (repo root)
records reviewed boundaries on top of the deduplicated corpus:

| action | source | rows | what |
|---|---|---|---|
| `start` | `review` | 260 | missed headers found by reading all 2,096 half-pages that had no detected header (the "Seiten ohne Eintrag" list): numeric-dated typed reports (Bezzel, Wüst, Remold …), day ranges, year-less and OCR-damaged dates, digest sections; 34 of them sit in masked text (below) and are not applied, 1 line was not found |
| `start` | `review-resumption` | 1 | the 26 May 1936 entry resumes after the interleaved life list (Vol. 14) |
| `start` | `auto-markup` | 107 | day headers the detector misses because `<u>` sits inside the date (`27. <u>December 1938.</u>`), header-shaped lines only, Roman-month digest lines excluded (1 in masked text) |
| `start` | `auto-dropped-copy` | 6 | headers read cleanly on a page the dedup dropped, mapped to the kept copy's line |
| `stop` | `review` | 751 | register / index / end matter pages |
| `stop` | `review-duplicate` | 16 | repeat photographs of a typed report or a day page (the best copy stays an entry) |
| `stop` | `auto-register`, `auto-junk` | 16 | the register begins on the last entry's own page; a page of `[illegible]` placeholders before it |

`data/corpus_patches/masked_regions.csv` blanks 549 body-text regions out of
the entry text (offsets unchanged): the 347 regions the multimodal cleaning v2
removed as unreliable (239 faint bleed-through readings of folded typed
reports — corrupted dates and names —, loops, gibberish, hallucinations), the
151 paragraphs that are really maps/photographs (their "transcription" is a
reading of a picture) and 51 irrelevant inserts (clipping backsides: ads,
local news; duplicates) — text the extraction model no longer reads.

```bash
python HistOrniGraph_addons/dedup/apply_entry_boundaries.py --corpus-dir data/corpus_dedup \
    --boundaries data/corpus_patches/entry_boundaries.csv \
    --mask data/corpus_patches/masked_regions.csv --out-dir data/corpus_patched
python HistOrniGraph_addons/build_multimodal_regions.py --corpus-dir data/corpus_patched \
    --catalogue-dir <multimodal_catalogue_v2_2026-08-18> \
    --reading-order data/corpus_dedup/multimodal_clean.md \
    --insert-decisions data/corpus_patches/text_insert_decisions.csv \
    --duplicates data/corpus_patches/multimodal_duplicates.csv \
    --catalogue-entries <corpus_2026-07-21>/entries.csv \
    --out data/corpus_patched/multimodal_regions.jsonl
```

Result (2026-09-30): 9,527 → 9,857 entries — 338 new (166 field days, 158
typed reports/letters, 13 digest sections, 1 other; every existing `entry_uid`
and `entry_id` kept, new entries are `L05-e0123a` …), 8 dropped (entries whose
header lies in a bleed-through reading, i.e. unreliable duplicates of a
report), 549 existing entries shorter (register cut off, missed day split off,
masked text); entry text 9.10M → 7.81M characters. `source_regions` lists
every body-text region an entry runs through (3,257 entries span several).
Multimodal: 1,299 image/object regions after removing 121 duplicate scans
(`multimodal_duplicates.csv`: dHash of the catalogue thumbnails on adjacent
scans, looser when the text dedup paired the scans as rescans, plus a visual
check of the borderline pairs) and 375 of 426 paragraph/list inserts
(`text_insert_decisions.csv`, marginalia never); 1,626 regions linked to an
entry (1,253 images/objects, 373 inserts; 88 links taken from the catalogue
where the dedup had moved the facing text page). `data/corpus_patches/dedup_lost_headers.csv` lists 74 headers that only
exist on a page the dedup dropped (its kept twin is a partial capture) — those
days are missing from the corpus until the dedup decision is revisited.
