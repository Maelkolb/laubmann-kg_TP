# CHANGELOG — corpus builder refactor

Refactored the monolithic `build_corpus.py` (~550 lines) into the importable
`laubmann_corpus` package with a thin CLI wrapper. All existing flags
(`--output-base`, `--corpus-dir`, `--per-volume`, `--include-nontext`,
`--loose`, `--volumes`) are unchanged, so the existing Colab notebook keeps
working as-is.

## Behavioral changes to the primary text corpus

The primary text corpus is preserved as close to byte-for-byte as possible.
Verified against the original builder on real sample volumes:

- **`corpus.txt` — byte-identical.**
- **`entries.jsonl` / `entries.csv` — all original keys/columns preserved, in
  the same order and with the same values.** New keys/columns are appended only
  (see additions below); no existing consumer breaks.
- **`corpus.md` — body text unchanged.** The only difference is inside the HTML
  `<!-- page ... -->` and `<!-- region ... -->` comments (see additions below).

Additions (the intended improvements — nothing removed or altered):

1. **`page_uid` / `region_uid`** are emitted at page and region level.
   - `corpus.md` / `by_volume/*.md`: `page_uid=` added to each `<!-- page -->`
     comment; `region_uid=` added to each `<!-- region -->` comment (comments
     only; no rendered prose changes).
   - `corpus.json`: a `page_uid` key on every page object and a `region_uid` key
     on every region object; each `entry_starts[*]` gains `entry_uid`.
   - `entries.csv` / `entries.jsonl`: `entry_uid`, `page_uid`, `region_uid`
     columns/keys appended after the original columns.

2. **Normalization provenance** appended to entries: `month_source`
   (`roman` | `numeric` | `name`), `year_form` (`4-digit` | `2-digit→19xx`),
   `loc_source` (`date-only` | `underlined` | `plain` | `weekday-stripped`).
   Present in `entries.jsonl`, `entries.csv`, and `corpus.json` entry starts.
   The final `date_norm` / `location_raw` values are unchanged.

3. **Page-inclusion rule is unchanged for the text corpus.** A page whose only
   content is a non-body-text region (e.g. an isolated marginal note) still does
   NOT appear in `corpus.md` / `corpus.txt` / `corpus.json`, exactly as before.
   Such pages ARE catalogued by the new multimodal builder.

No changes to: entry segmentation results, `date_norm` values, location
extraction results, region ordering, `corpus.txt` markers, or the `entry_id`
scheme (`L{vol:02d}-e{n:04d}`).

## Internal improvements (no output impact)

- **Scan-once entry segmentation.** The per-region entry-start scan that the
  original ran three times (in `render_volume_md`, `render_txt`, and the JSON
  export) now runs once per region in `stream.annotate_pages`; the Markdown, txt
  and JSON renderers and the volume-stream segmentation all reuse the same
  stored `reg["starts"]`. Same output, one scan.

## New capabilities (additive; do not touch the primary corpus)

- **`--report`** → `corpus/report.{json,md}`: per-volume coverage (pages seen,
  regions by type, regions with empty/failed transcription, entries detected,
  % of entries with a normalized date, % with a location).
- **`--multimodal`** (and standalone `build_multimodal_corpus.py`) →
  `corpus/multimodal/multimodal.{jsonl,csv,md}`: catalogue of every
  `ImageRegion`, `ObjectRegion`, `GraphicRegion`, `MarginaliaRegion` and insert
  region, including folded inserts (`folded: true`, empty description). Each row
  carries `region_uid`, `page_uid`, volume, scan, page number, region type,
  `insert_id` / `insert_state`, crop path, description, visible text, page side,
  reading order, and the `entry_uid` / date / location of the nearest preceding
  entry header in reading order. `multimodal.md` inlines the crop image paths.
- **Schema census** printed once per run (suppress with `--no-census`): the
  union of keys seen per region type across a sample of volumes, as an
  up-front sanity check that the on-disk shape matches expectations.

## Dependencies

Standard library only — unchanged.
