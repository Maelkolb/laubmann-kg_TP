# Laubmann corpus deduplication

Detect and review duplicate / near-duplicate pages in the HistOrniGraph
corpus, then emit a clean corpus non-destructively. See `METHODS.md` for the
root-cause analysis and validation metrics.

## Install

```bash
pip install rapidfuzz datasketch          # core
pip install imagehash pillow              # optional image layer
```

The detector degrades gracefully: without `datasketch` the global pass falls
back to shingle bucketing; without `rapidfuzz` it uses `difflib`.

## Files

| file | role |
|------|------|
| `laubmann_dedup.py`   | core, importable, testable — normalization, fingerprints, candidate generation, scoring, clustering, quality screen |
| `detect_duplicates.py`| CLI → `duplicates_report.csv` / `.jsonl` + `quality_report.csv` |
| `build_review_gui.py` | CLI → self-contained `review.html` for a student assistant |
| `apply_dedup.py`      | CLI → new deduplicated corpus + `dedup_manifest.{json,csv}` (never mutates input) |
| `md_to_corpus.py`     | reconstruct `corpus.json` from `corpus/by_volume/*.md` when only the Markdown artifacts are synced |
| `test_laubmann_dedup.py` | unit tests (`python test_laubmann_dedup.py` or `pytest`) |
| `METHODS.md`          | thresholds, FP/FN behavior, sample metrics |

## Workflow

```bash
# 1. detect
python detect_duplicates.py corpus/corpus.json -o dedup_reports/ \
    --scan-window 3 --cluster-threshold 0.55 --high-threshold 0.80
# optional image adjudication of the review band:
#   --image-root "G:/My Drive/HistOrniGraph_output"

# 2. build the review GUI (embeds full region text for the diff view)
python build_review_gui.py dedup_reports/duplicates_report.jsonl \
    --corpus corpus/corpus.json -o dedup_reports/review.html

# 3. a student opens review.html, confirms/rejects each cluster, picks the
#    page to keep, and clicks "Export decisions" → dedup_decisions.json

# 4. apply (non-destructive: writes a NEW corpus dir)
python apply_dedup.py --corpus-dir corpus \
    --decisions dedup_reports/dedup_decisions.json \
    --out-dir corpus_dedup
```

`corpus_dedup/` gets a rebuilt `corpus.json`, `corpus.txt`, `entries.jsonl`
and `entries.csv` (re-segmented over the surviving pages), plus a
`dedup_manifest` recording every dropped page, the page kept in its place, the
cluster, and the confidence. The original corpus is untouched.

> `apply_dedup.py` re-segments entries via `find_entry_starts` / `strip_markup`
> from your repo's `build_corpus.py`. Run it from the repo root (or with
> `build_corpus.py` on the path) so those imports resolve. If `build_corpus.py`
> isn't importable it still writes the deduplicated `corpus.json`/`.txt` and the
> manifest — it just skips `entries.*` regeneration and says so.

## Report columns

`duplicates_report.csv` has `decision`, `keep_override` and `notes` columns
left blank — a reviewer can adjudicate in a spreadsheet instead of the GUI and
the same values feed `apply_dedup.py` (export them in the decisions schema).

## Using the core as a library

```python
from laubmann_dedup import load_corpus_pages, run_detection

pages = load_corpus_pages("corpus/corpus.json")
clusters, scored = run_detection(pages, cluster_threshold=0.55)
for c in clusters:
    print(c.cluster_id, c.confidence, c.relation,
          "keep", c.suggested_keep, "drop", c.suggested_drop)
```
