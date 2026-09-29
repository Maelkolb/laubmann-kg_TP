# Laubmann-Abgleich (validation UI)

Standalone HTML page (German) for reviewing and correcting the graph's main
entities: species, persons, places, habitats. Background and rationale:
[`docs/validation.md`](../../docs/validation.md).

## Four tasks

The review unit is the **entity** (one authority record) with the written names
and diary passages behind it. Decisions are stored on the written name and the
diary passage, so they survive a re-extraction with the final ontology.

| tab | what | question |
|---|---|---|
| **Prüfen** | entities that already have an authority link | Is the GBIF species / Wikidata–GND record / location / EUNIS class right? `Y` stimmt · `A` anders … · `N` keine / nicht bestimmbar · `U` unsicher. Below it the written names with a checkbox each: unticking a name asks "zu welchem Eintrag?" or "kein(e) …". |
| **Verknüpfen** | entities without a link | Search GBIF (`A`, ⏎ searches GBIF), pick a Wikidata candidate (digits `1`–`9`), search OSM/Wikidata or click the map, pick an EUNIS class — or **"ist dasselbe wie …"** an existing entity (`⇧A`–`⇧E`): all names move there. Persons carry a suggestion from Claude Opus 5.5 (see below). |
| **Namen** | entities with unsafe names or likely missing ones | Tick = belongs here. Candidates from similar names of other entities (`merge_candidates.py`), plus a search box for any name of the graph. "Namensgruppe stimmt so" (`Y`) confirms all. |
| **Lesefehler** | mentions where the models read the line differently than the transcription | Line image on top, the page on the right, one table with transcription / Gemini / Opus readings and an agreement badge. `Y` transcription right · `1`/`2` accept a model reading (sets word + species) · `E` type the word · `A` other species · `N` not a bird · `U`. |

Plus **Stichprobe** (stratified random sample of 403 species mentions, live
accuracy with 95 % Wilson interval), **Hinweise** (QA flags) and **Protokoll**
(progress per task, every decision, removable one by one). Undo (`Z`), global
search (`Ctrl+K`), no automatic advancing unless "automatisch weiter" is ticked,
stable list order, fixed-width tab counters.

## Model readings

* **Second reading** (`second_reading.py`): the line image of every doubtful
  species mention goes to Gemini 3.5 Flash ("what is written, which bird?").
* **Third reading** (`third_reading_sheets.py` → contact sheets of 10 line crops
  → one Claude Opus 5.5 subagent per sheet → `model_answers_merge.py`): the
  mentions where Gemini disagrees with the transcription are read a second time
  by another model. The page shows both readings; "beide Modelle lesen dasselbe"
  is usually right, but the reviewer decides at the image. The third readers
  mark misaligned or illegible crops as not legible (rotated pages, wrong line).
* **Person matching** (`person_batches.py` → batches of 15 persons with all
  written names, mention years, roles, passages and the Wikidata candidates
  enriched with dates/GND/occupation → Opus subagents → `model_answers_merge.py`):
  a conservative decision per person (candidate / none / unclear) with a reason,
  shown as a box above the candidates; `Y` confirms the model's candidate.

Nothing from the models is applied automatically.

## Export

Decisions live in the browser (localStorage). "Sichern & Export" can connect a
backup file (File System Access API, Chrome/Edge): every decision is then
written to that file at once. The ZIP export contains:

| file in the ZIP | goes to | read by |
|---|---|---|
| `review/identities.csv` | `data/review/` | `review.identities` (linking + resolution): `same`/`own`/`none`/`unsure` per written name, `link`/`nolink` per entity with `gbif:`/`wd:`/`gnd:`/`gn:`/`osm:`/`eunis:` |
| `review/value_corrections.csv` | `data/review/` | `corrections.csv` (after extraction) |
| `review/text_corrections.csv` | `data/review/` | `review.text_corrections` (before extraction; those entries are re-read) |
| `review/evaluation_taxa.csv` | — | evaluation (taxon identification accuracy) |
| `review/qa_flags.csv` | — | not read by the pipeline yet |
| `model_readings.csv` | — | both model readings with the decision state (information) |

Backups of the earlier UI versions (v1 pair review, v2, v3) can be loaded.

## Build

From one export folder (`rdf/laubmann_sample.ttl` + `review/`) and the
deduplicated corpus (`corpus.json`, `entries.jsonl`):

```bash
python tools/validation_ui/load.py <export>/rdf/laubmann_sample.ttl triples.pkl            # ~45 s
python tools/validation_ui/page_geometry.py <corpus_dir> "<HistOrniGraph_output>" pages_geometry.json   # PAGE-XML region boxes, ~1.5 min from Drive
python tools/validation_ui/line_profiles.py <corpus_dir> pages_geometry.json "<HistOrniGraph_output>" --procs 8   # physical lines per region from the scans (ink profile), ~10 min
python tools/validation_ui/vernaculars.py triples.pkl vernaculars.json                    # GBIF + Wikidata German names, ~3 min, resumable
python tools/validation_ui/drive_ids.py tools/validation_ui/drive_pages.json               # page scan ids (Drive for desktop)
python tools/validation_ui/build_payload.py <export>/review --triples triples.pkl --corpus <corpus_dir> \
    --geometry pages_geometry.json --vernaculars vernaculars.json --built 2026-09-29 --out payload.b64   # ~1.5 min
python tools/validation_ui/second_reading.py payload.b64 --pages "<HistOrniGraph_output>" --out second_reading.json   # Gemini, resumable
python tools/validation_ui/third_reading_sheets.py payload.b64 second_reading.json --pages "<HistOrniGraph_output>" --out third/sheets
python tools/validation_ui/person_batches.py payload.b64 <export>/review --out persons/batches    # + Wikidata enrichment (cached)
#   … one subagent per sheet / batch (instructions in the scratch folder), answers next to the inputs …
python tools/validation_ui/model_answers_merge.py --sheets third/sheets --sheet-answers third/answers \
    --batches persons/batches --batch-answers persons/answers --out-third third_reading.json --out-persons person_matches.json
python tools/validation_ui/build_payload.py … --second-reading second_reading.json --third-reading third_reading.json \
    --person-matches person_matches.json --out payload.b64                                   # again, with all readings
python tools/validation_ui/assemble.py payload.b64 Laubmann_Abgleich.html
```

`second_reading.py` reads the C-class mentions and rare (≤ 3) unlinked or
variant names: 2,586 mentions for the 2026-08-19 export, about 3.9 M input and
2.1 M output tokens with `gemini-3.5-flash` at thinking level low. The third
reading covers the 1,176 mentions where Gemini disagrees (118 sheets); person
matching the 313 persons with Wikidata candidates and ≥ 2 mentions (21 batches).

The app script is kept in five parts (`app_core.js` data/state/model,
`app_ui.js` tabs/queue/scan, `app_views.js` task views, `app_actions.js`
decisions/panels/searches/editor/keys, `app_io.js` export/import/help/start);
`assemble.py` concatenates them inside one async IIFE.

**Line images.** The PAGE-XML carries region boxes only (no `TextLine`
coordinates). `line_profiles.py` finds the physical text lines of every region
by a horizontal ink profile of the scan and stores each band with its ink
mass; `build_payload.py` aligns the transcription lines to the bands by a
monotone dynamic-programming match of line length against ink mass (bands
without a line — sketch labels, rules — are skipped, lines without a band share
their neighbour's and are flagged "ungefähre Zeile", shown with more context),
and adds the word's horizontal position from its character offset. Without
profiles the region box is divided evenly. On the 2026-08-19 corpus 45,462 of the 71,324
located species mentions (64 %) sit on a matched physical line; the ink profile finds the
transcription's line count (±1) in 57 % of the 15,378 text regions and is within
25 % in another 15 %; the rest (dense handwriting with touching lines, sketches,
rotated pages) stays an estimate. Two-column species lists still defeat both.

**Decisions propagate.** One decision settles the same question everywhere:
a relinked or rejected entity closes its read items; an explicit decision on a
written name (checkbox, "Name → Art", "überall lesen als") closes every read
item of that name; a mention decided in *Lesefehler* shows up on its card in
the other tasks; names reassigned to an entity appear in its name group in
every task; an entity decided with its candidates on screen counts as reviewed
for *Namen*. Candidates and the name search are part of every task's name
group, so nothing has to be repeated in another tab.

`drive_pages.json` maps page ids to the Drive file ids of
`HistOrniGraph_output/Laubmann_XX_gemini/pages/<page id>.png` (6,742 of 6,750
corpus pages). Scans and line images only load for Google accounts with access
to that folder. The built page contains the full entry texts; it is not
committed.

Live lookups (GBIF, Wikidata, lobid GND, Nominatim) and the Esri basemap need
network access; everything else works offline. lobid.org refuses requests from
a page opened as a file, so the GND search then goes through Wikidata (P227).

## Smoke test

```bash
HOG_UI=Laubmann_Abgleich.html HOG_BROWSER="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
HOG_PAGES="G:/My Drive/HistOrniGraph_output" python tools/validation_ui/tests/smoke_abgleich.py
```

Playwright (Python) drives every task, serves the scans from the local Drive
folder, takes a screenshot per task and feeds the exported CSVs through the
pipeline's loaders.
