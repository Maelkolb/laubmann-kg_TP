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
