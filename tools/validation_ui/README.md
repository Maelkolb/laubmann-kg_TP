# Validation UI ("Abgleich")

Standalone HTML page (German) for reviewing an export by hand. The review unit
is the **name form**: a taxon, person, place or habitat name as written in the
diary, assigned to one entity of the graph. The reviewer confirms or changes
that assignment; merges follow from it (all forms of one entity are one node).
Single mentions can be decided differently, and misread text is corrected
where it happened. Background and rationale: [`docs/validation.md`](../../docs/validation.md).

What the page offers:

* four queues (Arten, Personen, Orte, Lebensräume), risky forms first
  (unattested, not linked, merged by a rule), most frequent first;
* per form: the assigned entity with its authority record (GBIF with German
  names, Wikidata/GND, GeoNames/Wikidata/coordinates on a map, EUNIS), the
  sibling forms of the same entity, and the mentions with a **line image** cut
  from the scan next to the transcription;
* a scan viewer that pages through every page an entry spans (‹ › and the page
  buttons) with the mention's line highlighted;
* per-mention decisions (✓ ↪ ✗) and reading corrections (✎);
* *Stichprobe*: a stratified random sample of taxon mentions with a live
  accuracy estimate (95 % Wilson interval);
* QA flag review; import of backups of the first UI version (pair decisions
  are converted to name-form decisions).

The page runs from a local file (no server). Decisions are kept in the browser
(localStorage) and exported as a ZIP:

| file in the ZIP | goes to | read by |
|---|---|---|
| `review/identities.csv` | `data/review/` | `review.identities` (linking + resolution) |
| `review/value_corrections.csv` | `data/review/` | `corrections.csv` (after extraction) |
| `review/text_corrections.csv` | `data/review/` | `review.text_corrections` (before extraction; those entries are re-read) |
| `review/evaluation_taxa.csv` | — | evaluation (taxon identification accuracy) |
| `review/qa_flags.csv` | — | not read by the pipeline yet |

## Build

From one export folder (`rdf/laubmann_sample.ttl` + `review/`) and the
deduplicated corpus (`corpus.json`, `entries.jsonl`):

```bash
python tools/validation_ui/load.py <export>/rdf/laubmann_sample.ttl triples.pkl            # ~45 s
python tools/validation_ui/page_geometry.py <corpus_dir> "<HistOrniGraph_output>" pages_geometry.json   # PAGE-XML region boxes, ~1.5 min from Drive
python tools/validation_ui/vernaculars.py triples.pkl vernaculars.json                    # GBIF + Wikidata German names, ~3 min, resumable
python tools/validation_ui/drive_ids.py tools/validation_ui/drive_pages.json               # page scan ids (Drive for desktop)
python tools/validation_ui/build_payload.py <export>/review --triples triples.pkl --corpus <corpus_dir> \
    --geometry pages_geometry.json --vernaculars vernaculars.json --built 2026-09-28 --out payload.b64   # ~1.5 min
python tools/validation_ui/assemble.py payload.b64 HistOrniGraph_Abgleich.html
```

`drive_pages.json` maps page ids to the Drive file ids of
`HistOrniGraph_output/Laubmann_XX_gemini/pages/<page id>.png` (6,742 of 6,750
corpus pages); `drive_ids.py` reads them from the local Drive-for-desktop
metadata. Scan previews and line images only load for Google accounts with
access to that folder. The built page contains the full entry texts; it is not
committed.

Live lookups (GBIF, Wikidata, lobid GND, Nominatim) and the Esri basemap need
network access; everything else works offline.

## Smoke tests

The Playwright scripts in `tests/` were written for the first version and are
not updated yet.
