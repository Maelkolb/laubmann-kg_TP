# Round 4: record check of every entry, correction route, validation pages

2026-10-01. Follows `docs/human_validation_plan.md` (rounds 1–3). Export:
`kg_exports_2026-10-01_checked`. Tools: `tools/validation_ui/machine_review/`
(`record_check.py`, `record_check_combine.py`), `tools/validation_ui/graph_check/`,
`tools/validation_ui/link_check/`.

## 1. What has read the diaries so far

| pass | scope | by | cost |
|---|---|---|---|
| visual reading: transcription against the scan, text corrected | 9,895 entries | Gemini 3.8 Flash | $26.67 |
| extraction: records from the corrected text | 9,909 entries | Gemini 3.8 Flash | $38.16 |
| machine review rounds 1–3: names and links; record check of 115 sample entries | 7,066 name decisions, 1,652 records | Claude Sonnet subagents, Gemini as second opinion | $9.06 (Gemini) |
| **record check (round 4): every record against the scan** | **9,590 entries, 85,604 records** | **Gemini 3.8 Flash** | **$30.14** |

The record check skipped 302 entries without a record and with less than 60
characters of text, and 9 entries whose page scan is missing (Vol. 15). A
comparison run of the 115 sample entries with medium thinking cost $1.96 more.
No human has decided anything yet: `data/review/` holds no human decision file.

## 2. What the record check found

| verdict | records | share |
|---|---|---|
| right | 75,952 | 88.7 % |
| wrong in at least one field | 8,754 | 10.2 % |
| no such record in the text | 804 | 0.9 % |
| undecided | 65 | 0.1 % |

5,359 entries have all records right, 3,769 have at least one flagged record.
The model also lists 1,549 records the text states and the graph lacks (in 544
entries), and judges the entry header wrong for 120 dates, 203 places and 1,191
entry kinds.

| field flagged | records | | field flagged | records |
|---|---|---|---|---|
| locality | 2,836 | | count | 846 |
| georeference | 2,505 | | own date | 639 |
| observer | 2,032 | | breeding | 200 |
| species | 1,567 | | sex | 196 |
| record type | 1,232 | | status (absent) | 119 |

Of the 45,357 reading corrections that were applied, the check calls 3,793
wrong and 1,651 only partly right (12 %); the Claude agents found 16 % not
right on their sample.

## 3. How far a finding can be trusted

On the 115 entries both checks saw (1,618 records in common):

| | Gemini flags | Claude flags | both | Gemini's flags Claude shares | Claude's flags Gemini finds |
|---|---|---|---|---|---|
| any field | 129 | 197 | 87 | 67 % | 44 % |
| record type | 25 | 24 | 24 | 96 % | 100 % |
| georeference | 38 | 62 | 32 | 84 % | 52 % |
| locality | 38 | 57 | 28 | 74 % | 49 % |
| species | 12 | 29 | 6 | 50 % | 21 % |
| count | 12 | 38 | 3 | 25 % | 8 % |

Neither check is ground truth. Nine of the Claude agents' 39 count findings
are false alarms: the graph stores "3–5" as minimum 3 and maximum 5
(`lkg:individualCountMin/Max`; `countMin`/`countMax` in the archive's
`dynamicProperties`) and the agents overlooked it. So a single check is a
pointer for the reviewer, not a correction. Medium thinking raises Gemini's
recall of Claude's flags to 59 % but doubles its flags, lowers the agreement to
49 % and costs 4.5 times as much.

Rule kept from rounds 1–3: a machine verdict reaches the graph only with
confidence ≥ 0.9 and two independent sources. For records that is the case
only where both checks propose the same value for the same field: **39 rows**
(24 record types, 7 localities, 4 species, 2 dates, 1 count, 1 observer). The
other 9,549 findings are suggestions in the graph validation page.

To use the rest without reading every finding: the reviewer checks the fixed
random sample of entries in the page (queue "Stichprobe"); `graph_audit.csv`
then gives the precision per class of finding; a class that holds is released
as a whole with `record_check_combine.py --trust FIELD:MIN_CONFIDENCE[:quote]`
and applied at the next export.

## 4. The updated graph

`kg_exports_2026-10-01_checked`: 9,901 entries, 85,631 observations, 1,979,492
triples, SHACL 0 violations / 464 warnings, `tools/validate_export.py` 0
errors. Against `kg_exports_2026-10-01_machine`:

- 35 record fields corrected and 3 species replaced where both scan checks
  agree (a fourth species row matched no record and is reported as a QA flag).
- Habitat links are the ones the machine review judged. The habitat
  classification cached its answers per batch of 40 labels; the re-export of
  the night had re-asked the model and changed the EUNIS class of 371 labels
  that round 3 had just checked. `linking/habitats.py` now keeps one answer per
  label (`label_answers.json`), seeded from the reviewed export.
- New route for corrections of single record fields and for records added by
  hand: `review/observation_corrections.csv`
  (`normalization/observation_corrections.py`): count, locality, date,
  observer, co-observers, record type, sex, life stage, breeding, status;
  entry date and kind; added records. Until now such corrections were exported
  by the review page and read by nothing.

Run-to-run noise that remains: about 15 very long entries exceed the output
limit and are extracted anew in every run (about 90 of 85,631 records differ
between the two exports for this reason).

## 5. Reading corrections: which ones can change a record

| kind of change | corrections | can change a record |
|---|---|---|
| underlining only | 4,228 | no |
| punctuation or spacing only | 2,666 | no |
| capitalisation only | 524 | no |
| a number (count, date, time) | 4,172 | yes |
| a word | 34,412 | when it is a bird, place or person name |
| inserted or deleted text | 489 | yes |

17,890 corrections touch a number, a bird name of the graph or a place name
used at least three times; the page shows those first. 5,444 applied
corrections carry an objection of the record check.

## 6. Text inserts (Texteinlagen)

375 typed or printed inserts and lists are nodes of the graph
(`lkg:MultimodalRegion`, kind `text-insert` / `list`, with `lkg:visibleText`),
attached to the entry they sit in.

- For 320 the text is also part of their entry's text, so the extraction read
  it: at least 6,177 observations (7 % of the graph) come from insert text —
  5,444 third-party reports, 136 literature records, 597 field observations of
  the diarist.
- 22 are read under a neighbouring entry (the region hangs on one entry, its
  text was extracted with the next).
- 31 share little wording with their entry. Most of them have a second
  transcription of the same sheet in the entry text (the entries hold 24 to
  111 records). About six look unread: L25-e0170 (excursion report of
  15 March 1952), L28-e0118 (January observations Eching/Moosburg), L28-e0090,
  L29-e0198, L29-e0209, L24-e0239.

Open question for the historian: the 597 field observations attributed to
Laubmann that come from typed sheets (monthly reports "mit Heinz …") — his own
typed notes or another observer's report.

## 7. The two pages

Both are single HTML files (German, EN toggle), keep decisions in the browser
and in a backup file, and export a ZIP whose `review/*.csv` go to
`data/review/`; the next `export-all` applies them. Decisions are keyed by what
the diary says (written name, entry uid, record index), so they survive
re-exports. READMEs with keys, contracts, build and tests are in the tool
folders.

**Link page** — `Laubmann_Verknuepfungen.html` (`tools/validation_ui/link_check/`,
9.9 MB). One entity at a time, per type, sorted by mentions: the authority
record now in the graph, who set it (pipeline rule, machine round with sources
and confidence), the link before and after where the machine changed it, the
votes of the sources, candidates and live search (GBIF, Wikidata, GND,
Nominatim), the written names of the entity, sample passages with the line on
the scan, a map for places. Output: `review/identities.csv` only.

| | entities / mentions | changed by the machine | confirmed | suggestion | pipeline only | no link | merge candidates |
|---|---|---|---|---|---|---|---|
| species | 688 / 85,724 | 130 | 233 | 322 | 2 | 1 | 0 |
| persons | 3,730 / 9,219 | 105 | 5 | 910 | 0 | 2,710 | 91 |
| places | 8,690 / 37,384 | 92 | 1,362 | 1,571 | 58 | 5,607 | 535 |
| habitats | 1,861 / 14,327 | 23 | 1 | 1,772 | 61 | 4 | 180 |

The 363 species entries the machine changed or confirmed cover 70,216 of the
85,724 mentions.

**Graph page** — `Laubmann_Graphpruefung.html` (`tools/validation_ui/graph_check/`,
21 MB, opens in about a second). The explorer's entry view with a work list on
the left, the scan with the entry's regions and the selected record's line on
the right, and a "Prüfen" tab that lists everything decidable for the entry:
records a check flagged (from → to, which check, confidence, the quoted words
of the page; both checks side by side where both judged), missing records,
automatic name changes touching the entry, reading corrections that can change
a record, the entry header, what QA removed, text inserts. Nodes of the graph
carry the same state as rings (red finding, orange automatic change, blue
suggestion, green decided, grey removed); the middle switches to an editable
table of the records.

With the layer "Eigenschaften" every literal the graph holds for a node is a
row in its box (count and range, qualifier, evidence kind, behaviour, call,
sex, stage, breeding, record type, verbatim notes …); "Alles zeigen" turns on
every layer, and the table has one column per property found on the entry's
records.

Flags carry a level, shown by colour (the marker shows the kind of flag):
**schwer** — no such record, wrong species, present/absent, wrong entry date;
**mittel** — count, date, locality, observer, record type, a missing record,
a species relinked or removed by the machine, a contested reading of a bird
name or number, an unread text insert; **leicht** — georeference (decided on
the link page), sex, stage, breeding, entry kind, moved places; **Hinweis** —
confirmations, suggestions below the thresholds, notes. Both checks agreeing
raises a finding by one level, a confidence below 0.8 lowers it. The work
list sorts by gravity; the rules are one table (`gc_severity.js`, README,
help). Open items in the full graph: 2,141 schwer, 9,360 mittel, 5,153 leicht.

A selector in the header filters every view to one corpus of section 8 (full,
core, strict core, strict core with coordinates); each record shows its tier
and, in words, why it is not in the next one. In the core 84 schwer and 2,730
mittel items remain open.

Every drawing, map, photograph, print, object and text insert of an entry is
a card with its crop (from Drive by file id, else the local copy from
`tools/export_region_crops.py`, else cut from the page scan), its description
and visible text, and is outlined on the scan; 195 of the 1,625 regions have
no known position on their page.

| queue | entries |
|---|---|
| finding of a check | 3,993 |
| changed automatically | 1,662 |
| reading correction on a species, number or place | 6,087 |
| text inserts | 328 |
| images (drawing, map, photograph, print, object) | 729 |
| QA flags | 3,310 |
| sample (fixed, for precision figures) | 299 |

Exports: `review/observation_corrections.csv`, `value_corrections.csv`,
`transcript_decisions.csv`, `text_corrections.csv`, `qa_decisions.csv`,
`identities.csv`, plus `entry_checks.csv` and `graph_audit.csv` (every decision
with what the machine had proposed: the precision of each check and each class
of automatic change).

Tested: both pages' browser tests pass (link page 150 + 78 checks, graph page
250 + 154 + 23), each exported file loads with the pipeline's own loader, and
the graph page's test decisions were run through the real pipeline on the real
entries (15 record fields, 3 species, 4 struck and 2 added records, entry date,
kind and place, reading decisions: all applied as decided). Not tested: Edge
itself (Chromium only), scans from Drive (need a signed-in browser; the pages
fall back to local JPEGs), the backup-file picker.

Limits: the line highlight is exact for about 57 % of the records, estimated
for 32 % and missing for 11 %; reading corrections, missing records and
inserts have no position on the scan; a finding on the georeference concerns
the place name and is decided for all entries on the link page.

## 8. A core graph from the machine checks

Every record carries the verdicts, so a core is a filter over the export, not
a new run. Filters per record (an entry-level filter such as "transcript rated
poor" would discard 31 % of all records, most of them right):

| step | filter | records | share | entries |
|---|---|---|---|---|
| – | all | 85,631 | 100 % | 9,148 |
| 1 | **core**: the record check calls every field right and the Claude check does not object; not a duplicate; has a GBIF taxon | 74,909 | 87.5 % | 8,607 |
| 2 | **strict core**: named at species level; name attested for the linked species or confirmed by two sources; no contested reading correction inside the record's own passage; entry date not judged wrong unless the record has its own date; scan legible | 69,150 | 80.8 % | 8,198 |
| 3 | **strict core with coordinates** | 44,372 | 51.8 % | 6,743 |

Outside the core, by first reason: a check calls a field wrong 8,681, exact
duplicate 939, a check finds no such record 816, no GBIF taxon 165, no verdict
121. Core but not strict: contested reading 3,318, not at species level 1,512,
entry date 461, name 459, scan 9. About 40,000 of the strict-core records have
coordinates whose place link two sources confirm.

On the 115 entries both checks saw, the Claude check objects to 108 of the
1,460 records Gemini calls right (7.4 %: count 34, locality 24, georeference
24, species 21), so the core still holds an estimated 5–7 % of records with a
wrong field and 1–2 % with a wrong species; a machine estimate until the
sample is reviewed. For 12 % of the records the passage cannot be located in
the entry text; the strict core excludes those whenever their entry has a
contested correction. The tier of every record is part of the review layer
(`build_review.py --dwca`: `t`, `tw`) and a filter of the graph page; it is
not written into the graph.

## 9. Order of work

1. **Links first** (link page): one decision per name covers all its
   mentions, including the largest record error class, the georeference.
2. **Sample** (graph page, queue "Stichprobe", about 300 entries): gives the
   precision of each checker and each class of automatic change.
3. **Release or revert classes** on that evidence (`--trust`, or revert a kind
   of reading correction), re-export.
4. **Work the findings** that remain, entries with most findings first.
5. Final random sample for the quality statement of the release.

## 10. Open points

- 87 names (865 observations) carry a scientific name that is not the
  canonical name of their GBIF key (subspecies named, species linked; lumped
  species) — to decide per name in the link page.
- 3,705 occurrences have no `recordedBy` (third-party records without a named
  observer).
- The six unread text inserts stay as they are (decision of 2026-10-01); their
  records can be added by hand in the graph page.
- A second independent source for record findings exists only for 115 entries.
- `kg_exports_2026-10-01` is not a pipeline-only export: the round-1 machine
  rows were already applied in the full run (33 taxa, 584 places, 63 person
  names). The link page takes the state before the machine for those names
  from the 2026-08-19 graph; the graph page shows them without a "before".
- Five applied machine rows have no effect: `none` for the place names See,
  Park, Wald and unbekannt (they survive as places of travel legs, which the
  removal does not touch) and `nolink` for St. Bartholomä (its merged spelling
  Sankt Bartholomä keeps the GeoNames record in Styria).
- 352 applied machine rows match no name of the graph (names of the 2026-08-19
  extraction that the new reading no longer produces).
- A machine confirmation lowers the grade of a GBIF link the pipeline had
  matched exactly: `match_method` becomes `machine-review`, which
  `kg/authority.py` grades `skos:closeMatch` (example Lachmöwe). To decide:
  keep `exactMatch` when the machine confirms the key of an exact GBIF match.
