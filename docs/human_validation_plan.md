# Human validation of the final graph and the Darwin Core Archive

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
| `transcript_decisions.csv` | visual reading | accept / reject / edit a machine reading correction (entry re-extracted when the text changes) |
| `qa_decisions.csv` | QA | false alarm: the flag and its exclusion are dropped |
| `observation_corrections.csv` | — (measured only) | count, locality, date, observer of single records: evaluation, no consumer yet |

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
