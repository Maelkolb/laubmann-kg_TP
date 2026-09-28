# Laubmann-Abgleich (validation UI)

Standalone HTML page (German) for reviewing and correcting the graph's main
entities: species, persons, places, habitats. Background and rationale:
[`docs/validation.md`](../../docs/validation.md).

## How it works

* **One entity at a time.** Left: a work list per tab (Arten, Personen, Orte,
  Lebensräume), most important first (unattested names, missing links,
  contradicting second readings, frequent entities). Middle: the entity with
  its authority record (GBIF with German names; Wikidata/GND candidates; map
  with GeoNames/Wikidata; EUNIS class) and every name the diary uses for it.
  Right: the scan, following the selected mention, with the line highlighted
  and every page of the entry (‹ › and page buttons).
* **The same four actions everywhere**, on the entity, a name or a single
  mention: ✓ stimmt (`Y`) · ↪ anders (`A`, search panel) · ✗ kein(e)
  Art/Person/Ort (`N`, with a reason) · ? unsicher (`U`). "Stimmt" on the
  entity also confirms its safe names (attested names, pure spelling
  variants); a relinked or undeterminable species carries its undecided names
  along. `J`/`K` move between entity, names and mentions; the next open entity
  follows automatically once everything is decided.
* **Readings.** ✎ (`E`) opens the full entry text next to a large line image;
  the edit is stored as minimal, unique text replacements
  (`text_corrections.csv`) and the pipeline re-reads that entry.
* **Second reading.** `second_reading.py` sent the line image of every doubtful
  species mention to Gemini ("what is written here, which bird?"). The page
  shows the answer next to the mention; `G` accepts it (reading + species).
  It is a suggestion only: the model can be wrong with high confidence.
* **Stichprobe**: a stratified random sample of 403 species mentions with a live
  accuracy estimate (95 % Wilson interval). **Hinweise**: QA flags.
  **Änderungen**: every decision with time and reviewer, removable one by one.
* **Undo** (`Z`), global search (`Ctrl+K`), dark mode, resizable scan panel.
* **Saving.** Decisions live in the browser (localStorage). "Sichern &
  Export" can connect a backup file (File System Access API, Chrome/Edge): every
  decision is then written to that file at once. The ZIP export contains:

| file in the ZIP | goes to | read by |
|---|---|---|
| `review/identities.csv` | `data/review/` | `review.identities` (linking + resolution) |
| `review/value_corrections.csv` | `data/review/` | `corrections.csv` (after extraction) |
| `review/text_corrections.csv` | `data/review/` | `review.text_corrections` (before extraction; those entries are re-read) |
| `review/evaluation_taxa.csv` | — | evaluation (taxon identification accuracy) |
| `review/qa_flags.csv` | — | not read by the pipeline yet |

Backups of the earlier UI versions (pair review, v2) can be loaded; pair
decisions become name decisions.

## Build

From one export folder (`rdf/laubmann_sample.ttl` + `review/`) and the
deduplicated corpus (`corpus.json`, `entries.jsonl`):

```bash
python tools/validation_ui/load.py <export>/rdf/laubmann_sample.ttl triples.pkl            # ~45 s
python tools/validation_ui/page_geometry.py <corpus_dir> "<HistOrniGraph_output>" pages_geometry.json   # PAGE-XML region boxes, ~1.5 min from Drive
python tools/validation_ui/vernaculars.py triples.pkl vernaculars.json                    # GBIF + Wikidata German names, ~3 min, resumable
python tools/validation_ui/drive_ids.py tools/validation_ui/drive_pages.json               # page scan ids (Drive for desktop)
python tools/validation_ui/build_payload.py <export>/review --triples triples.pkl --corpus <corpus_dir> \
    --geometry pages_geometry.json --vernaculars vernaculars.json --built 2026-09-29 --out payload.b64   # ~1.5 min
python tools/validation_ui/second_reading.py payload.b64 --pages "<HistOrniGraph_output>" --out second_reading.json   # Gemini, resumable
python tools/validation_ui/build_payload.py … --second-reading second_reading.json --out payload.b64                  # again, with suggestions
python tools/validation_ui/assemble.py payload.b64 Laubmann_Abgleich.html
```

`second_reading.py` reads the C-class mentions and rare (≤ 3) unlinked or
variant names: 2,586 mentions for the 2026-08-19 export, about 3.9 M input and
2.1 M output tokens with `gemini-3.5-flash` at thinking level low (minimal
thinking was clearly worse). Answers are cached by mention key.

`drive_pages.json` maps page ids to the Drive file ids of
`HistOrniGraph_output/Laubmann_XX_gemini/pages/<page id>.png` (6,742 of 6,750
corpus pages). Scans and line images only load for Google accounts with access
to that folder. The built page contains the full entry texts; it is not
committed.

Live lookups (GBIF, Wikidata, lobid GND, Nominatim) and the Esri basemap need
network access; everything else works offline.

## Smoke test

```bash
HOG_UI=Laubmann_Abgleich.html HOG_BROWSER="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
HOG_PAGES="G:/My Drive/HistOrniGraph_output" python tools/validation_ui/tests/smoke_abgleich.py
```

Playwright (Python) drives the page, serves the scans from the local Drive
folder, and feeds the exported CSVs through the pipeline's loaders.
