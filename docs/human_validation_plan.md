# Human validation of the final graph and the Darwin Core Archive

## 0. Where things stand (5 October 2026), start here

**Graph:** `kg_exports_2026-10-05_attribution`, 9,901 entries, 85,894 records. It carries the machine layer of
the text: where the scan check of round 4 gave a better reading of a reading correction, and for the scan agent's
corrections of round 3, that reading is in the text (4,310 changes in 3,076 entries). 830 better readings were
left to the reviewer (not placeable on their correction, a doubt, a word they would double). Since 5 October it
also carries the attribution of pasted reports: 4,259 records in 135 entries that the extraction credited to
Laubmann are credited to the report's author (Werner Rathmayer, Walter Wüst, Einhard Bezzel, …) or, where no
author can be named, to nobody (`tools/validation_ui/machine_review/README.md`, round 6), and Walter Wüst is no
longer labelled "Heinrich Wüst". The Gemini record check ran again for every entry whose records changed. No
human decision has been made yet.

**Pages** (Drive `HistOrniGraph_Final_Graph_NoVal`, open from disk in Edge or Chrome):

| page | for | build |
|---|---|---|
| `validation/Laubmann_Verknuepfungen.html` | authority links and merges, one entity at a time | `tools/validation_ui/link_check/` |
| `validation/Laubmann_Graphpruefung.html` | entry by entry against the scan: findings, missing records, automatic changes, reading corrections, entry head, the Text tab | `tools/validation_ui/graph_check/` |
| `explorer/Laubmann_Graph_Explorer.html` | the same page read-only | `build_graph_check.py --mode explorer` |

Keys and export files: `validation/LIESMICH.txt`. Numbers and limits: `Documentation.md` one level up.

**Order of work**

1. Link page, species first: 613 entities; the 359 the machine changed or confirmed cover 70,496 of 85,987
   mentions, so a few hundred decisions settle most of the graph. Then places with many mentions.
2. Graph page, queue *Stichprobe* (299 entries, fixed random sample): measures how often each check and each
   class of automatic change is right (section 1: release a class when the Wilson lower bound is ≥ 90 %,
   otherwise review it item by item or revert it). The text layer is one more class: in the Text tab its
   readings are orange; on a reading-correction card `J` takes the check's better reading, `K` keeps the
   machine's correction, `N` the old text, `E` an own reading.
   The attribution of pasted reports is a class the sample hardly reaches (3 of its entries): check it in the
   135 entries themselves, queue *Automatisch geändert* (record type and observer cards, 3,959 cards, most of
   them `leicht`); a report has one author, so one look at the page usually decides the whole entry. Where the
   author is unknown, the observer field stays empty unless the page or a cover note names the author.
3. The remaining findings, gravest first. Open in the full graph: 1,823 schwer, 8,621 mittel, 8,928 leicht
   (the `leicht` ones include the attribution cards); in the core 25, 3,026 and 6,100. The corpus bar (full,
   core, strict core, strict core with coordinates: 85,894, 61,304, 29,066, 17,585 records) narrows every list
   and count; `docs/corpus_tiers.md` says what each tier excludes and how many errors it is estimated to hold
   (29.2, 22.2, 9.5, 9.0 %).
4. Queue *Lesung an Art/Zahl/Ort* for the reading corrections that touch a record, including the better
   readings the layer left open.

Export ("Sichern & Export") after every session; the re-run is section 6.

The sections below are the plan of 1 October. Its principles (section 1), the decision files (section 3) and
the acceptance criteria (section 4) still hold; the single page it names was replaced by the two pages above.

> **Update 2026-10-01 (round 4).** Every record has since been checked against
> the scan by Gemini, corrections of single record fields have a pipeline
> consumer (`review/observation_corrections.csv`), and the work is split over
> two focused pages: the link page (`tools/validation_ui/link_check/`, section
> 2 tasks 2, 3 and 7 for names) and the graph page
> (`tools/validation_ui/graph_check/`, tasks 1, 4, 5 and 6 entry by entry with
> the scan). Results, the agreement of the checks and the order of work:
> `docs/validation_round4_report.md`. The page described below
> (`Laubmann_Validierung.html`) stays usable; its decisions use the same keys
> and files.

Plan for the validation of `kg_exports_2026-10-01_machine` (ontology 0.7.0,
prompt v4, visual reading, three machine review rounds applied above the
thresholds). The reviewer works in ONE page, `Laubmann_Validierung.html`
(tools/validation_ui/pruefung, German/English); every decision is exported in
the pipeline's review contracts and applied by a cheap re-run from the caches.

## 1. Principle

- **The machine sorts, the human decides.** Language-model agents (Claude
  Sonnet 5.5 subagents, Gemini 3.8 Flash as an independent second opinion)
  have judged names, links, records and transcript corrections. A machine
  verdict reaches the graph only with confidence ≥ 0.9 **and** ≥ 2 agreeing
  independent sources; everything else is a suggestion.
- **The human checks the machine by sampling, not item by item.** Each class
  of machine decision gets a stratified random sample; its precision (with a
  95 % Wilson interval) decides whether the class is accepted as a whole
  (lower bound ≥ 90 %) or reviewed item by item.
- **Decisions are keyed by what the diary says** (written name, authority id,
  entry uid + name + occurrence, the transcript passage), never by graph IRIs,
  so they survive every re-export. A human decision always wins over a machine
  row.

## 2. Tasks for the assistant, in this order

| # | task (tab) | what | how many | time |
|---|---|---|---|---|
| 1 | **Stichprobe** | precision sample of the machine's confirmations and changes, 5–7 strata × 40 | ~280 | 4–5 h |
| 2 | **Änderungen** | machine-proposed changes the pipeline applied automatically (red "auto"), by number of mentions | see Übersicht | 6–8 h |
| 3 | **Offen** | names the machine left unsure (species, persons, places, habitats), by mentions; stop at ≤ 2 mentions | see Übersicht | 8–10 h |
| 4 | **Transkript** | reading corrections: acceptance sample per kind (bird name, number, place, word, insertion, deletion) × applied/not applied, then all corrections the machine judged wrong/unclear and the unapplied ones in entries with records | 300 + 1,122 | 5–6 h |
| 5 | **Extraktion** | the entry dossiers checked by the agents (records, missing records, dates, places, georeferences): confirm the findings | 115 + 178 earlier | 6–8 h |
| 6 | **Hinweise** | QA flags by reason: confirm / false alarm / fix, samples for the large groups (1,675 transcript_poor) | 4,510 | 2–3 h |
| 7 | **Nicht geprüft** | everything no machine saw (long tail), linked and unlinked, by mentions — optional | long tail | open |

About 35–45 hours for tasks 1–6. Rhythm: export ("Sichern & Export") at the
end of every session; the orchestrator copies the ZIP's `review/*.csv` into
`data/review/` and re-runs the pipeline weekly (cached: minutes of Gemini
cost, only entries whose text changed are re-extracted).

## 3. What each decision changes

| decision file | pipeline stage | effect |
|---|---|---|
| `identities.csv` | linking, resolution | name → taxon/person/place/habitat, authority links (GBIF, Wikidata, GND, GeoNames, OSM, EUNIS), merges |
| `value_corrections.csv` | after extraction | one mention: other species, not a bird, drop |
| `text_corrections.csv` | before extraction | the reviewer's own reading of a passage (entry re-extracted) |
| `transcript_decisions.csv` | visual reading | accept / reject / edit a machine reading correction (`J`, `K`, `N`, `E`); the entry is read and extracted anew |
| `qa_decisions.csv` | QA | false alarm: the flag and its exclusion are dropped |
| `observation_corrections.csv` | after the value corrections | single record fields (count, locality, date, observer, record type, status …) and records added by hand |
| `machine/text_layer_machine.csv`, `machine/value_corrections_text_machine.csv` | visual reading and right after extraction | the machine layer of the text; a reviewer's decision on a correction wins, and an entry with any reviewer decision on its text is read anew with the layer's other changes |

## 4. Acceptance criteria for the release (v1.0, GBIF/Zenodo)

1. SHACL: 0 violations; `tools/validate_export.py`: 0 errors.
2. Precision sample per stratum: Wilson lower bound ≥ 90 % for every class of
   machine decision that stays in the graph unreviewed; classes below are
   reviewed item by item or reverted.
3. Species identification on the random mention sample ≥ 95 % (lower bound).
4. Transcript corrections: per kind, the kinds with precision < 90 % are
   reverted unless confirmed one by one.
5. Every name with ≥ 10 mentions has a human or two-source machine decision.
6. DwC-A passes the GBIF data validator (https://www.gbif.org/tools/data-validator)
   without blocking issues; EML metadata (creator, license, citation) complete.

## 5. What the machine rounds did (rounds 1–2 on 2026-09-30, round 3 on the final graph 2026-10-01)

Round 3: about 170 Claude Sonnet 5.5 subagent runs, Gemini 3.8 Flash as second
opinion on every name batch ($9.06). Earlier rounds' verdicts are kept for names
they judged (`--known`); a later round wins where both judged a name.

| check | unit | result |
|---|---|---|
| extraction (scan + text + graph + DwC-A) | 115 entries, stratified (random 60, poor transcript 20, third-party reports 15, long lists 10, no records 10), 1,652 records | 86.4 % right, 11.5 % wrong (georeference 62, locality 57, count 39, species 31, record type 24), 0.8 % spurious, 1.2 % unsure; 48 records missing |
| visual reading corrections | 669 corrections in the 115 entries | 79 % right, 12 % partly, 5 % wrong, 5 % unclear |
| species (GBIF) | 467 new/changed entities, 340 line crops of doubtful names | 309 links confirmed, 80 relinked or newly linked, 24 no bird, 52 unsure |
| persons (Wikidata/GND) | 552 persons with ≥ 2 mentions + 222 re-searched by surname | 76 linked (with GND), 25 automatic links rejected; most local persons have no authority record |
| places (GeoNames/OSM) | 1,414 places with ≥ 2 mentions + 5,955 single mentions | 1,219 locations confirmed, 246 wrong (namesakes), 239 newly located/relocated, 167 not a place, 5,231 micro-toponyms without a record (location hint only) |
| habitats (EUNIS) | all 1,851 concepts | 1,555 right, 140 other class, 93 no habitat, 63 unsure |

Applied automatically in `kg_exports_2026-10-01_machine` (confidence ≥ 0.9 and
≥ 2 independent sources, all rounds): 2,753 decisions — 1,468 place links,
1,047 species names, 46 names removed as no taxon, 133 person links, 17 wrong
person links dropped, 18 places removed/unlinked, 24 habitats. Everything else
is a suggestion in the page. Known weak spots for the assistant: georeferences
of namesakes (the most frequent error), counts given as ranges, record type of
third-party lists, persons written as initial + surname (no candidates found),
habitat verdicts given with default confidence.

## 6. Re-run after a review session

The ZIP's `review/*.csv` go to `data/review/`. The page inputs that cannot be rebuilt from an export
(`pages_geometry.json`, `drive_regions.json`, `drive_pages.json`, `vernaculars.json`, `second_reading.json`,
`third_reading.json`, `person_matches.json`, `payload_pipeline.b64`) are on Drive in
`HistOrniGraph_output/graph_check_inputs/` and belong in `data/cache/graph_check/in/`; the model caches are in
`HistOrniGraph_output/llm_cache_v4`, `reading_cache_v1`, `linking_cache`, `record_check_cache_v1`.

```powershell
$X = "data/exports/<new export>"; $I = "data/cache/graph_check/in"
$M = "G:/My Drive/Laubmann_KG_Maschinenpruefung_2026-10-01/machine_review"
$R = "G:/My Drive/HistOrniGraph_Final_Graph_NoVal/machine_review"
laubmann-kg export-all --config configs/full_llm.yaml --input-dir data/corpus_patched --output-dir $X
python tools/validation_ui/load.py $X/rdf/laubmann_sample.ttl $I/triples_checked.pkl
python tools/validate_export.py $X --triples $I/triples_checked.pkl
python tools/validation_ui/build_payload.py $X/review --triples $I/triples_checked.pkl --corpus data/corpus_patched `
    --geometry $I/pages_geometry.json --vernaculars $I/vernaculars.json --built <date> --export-name <new export> `
    --second-reading $I/second_reading.json --third-reading $I/third_reading.json --person-matches $I/person_matches.json `
    --machine-review $M/machine_review.json --machine-readings $M/readings_machine.json --out $I/payload_checked.b64
# record check only for entries whose records changed (file of entry ids); answers of the others stay
python tools/validation_ui/machine_review/record_check.py $I/payload_checked.b64 $I/triples_checked.pkl `
    --out data/cache/machine_review_r5 --review $X/review --dwca $X/dwca --only changed_ids.txt --budget 10
python tools/validation_ui/machine_review/record_check.py $I/payload_checked.b64 $I/triples_checked.pkl `
    --out data/cache/machine_review_r5 --review $X/review --dwca $X/dwca --merge-only
python tools/validation_ui/graph_check/build_review.py --payload $I/payload_checked.b64 `
    --payload-before $I/payload_pipeline.b64 --triples $I/triples_checked.pkl --corpus data/corpus_patched `
    --geometry $I/pages_geometry.json --review $X/review --machine data/review/machine `
    --record-check data/cache/machine_review_r5/record_check `
    --transcript-checks $R/transcript_checks_gemini.csv --sonnet-check $M `
    --sonnet-stale data/review/machine/sonnet_checks_stale.txt --drive-regions $I/drive_regions.json --dwca $X/dwca `
    --text-layer data/review/machine/text_layer_machine.csv --reading-base data/review/machine/reading_corrections_base.csv `
    --tiers-csv data/cache/graph_check/record_tiers.csv --out data/cache/graph_check/review.json
python tools/validation_ui/graph_check/build_graph_check.py $X/rdf/laubmann_sample.ttl data/cache/graph_check/review.json data/exports/graph_check/Laubmann_Graphpruefung.html
python tools/validation_ui/graph_check/build_graph_check.py $X/rdf/laubmann_sample.ttl data/cache/graph_check/review.json data/exports/graph_check/Laubmann_Graph_Explorer.html --mode explorer
python tools/validation_ui/link_check/build_data.py --export-review $X/review
python tools/validation_ui/link_check/assemble.py
# estimated error share of the corpora; attributions the new export changed are judged against the audit's reading
python evaluation/corpus_tiers/evaluate_tiers.py data/cache/graph_check/record_tiers.csv --dwca $X/dwca --before-dwca data/exports/kg_exports_2026-10-04_text/dwca
```

Without a local `data/cache/machine_review_r5`, `--record-check $R` reads the merged checks on Drive.
The attribution of pasted reports (`data/review/machine/attribution_machine.csv`, `review.machine.attribution`) is applied by
`export-all` like the other machine files; a reviewer's row in `review/observation_corrections.csv` wins over it.
`changed_ids.txt` and `sonnet_checks_stale.txt` list the entries whose records (occurrence id, species, count,
locality, observer, date) differ from the export they were checked on. The text layer itself is fixed against
`kg_exports_2026-10-01_checked`: `build_review.py --machine-text-layer` is not run again (it refuses an export
that already contains the layer).
