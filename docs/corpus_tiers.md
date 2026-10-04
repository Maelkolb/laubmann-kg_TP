# Corpus tiers

Every record of the export belongs to one of four nested corpora. The graph itself is not changed:
the tiers are a filter, computed after the export from the machine checks and from the text.

| Tier | Corpus | A record is in it when |
|---|---|---|
| K0 | full | always |
| K1 | core | the occurrence itself is not in doubt: species, count, date and status |
| K2 | strict core | no field is in doubt: also observer, record type, place, identification and reading |
| K3 | strict core with coordinates | the place also has reliable coordinates |

`tools/validation_ui/graph_check/corpus_tiers.py` holds the rules. `build_review.py --dwca` applies
them, writes the tier `t` and the reasons `tw` of every record into the review layer, and with
`--tiers-csv` writes `record_tiers.csv` (one row per occurrence of the Darwin Core Archive). The graph page,
the explorer and the link page read the tiers from the review layer.

## Rules

A record leaves a corpus for any one of these reasons; `tw` lists all reasons of its lowest tier.

| Code | Keeps out of | Meaning |
|---|---|---|
| `spurious` | core | a scan check does not find the record on the page |
| `flagged` | core | a scan check calls the species, count, date or status wrong |
| `unchecked` | core | no scan check judged the record |
| `duplicate` | core | same event, taxon, count, place, date, sex, stage and behaviour as an earlier record |
| `no-taxon` | core | no GBIF taxon |
| `list` | core | the entry is a species list or a retrospective |
| `literature-date` | core | a literature record carries the diary entry's date instead of its own |
| `entry-checks` | core | a quarter of the entry's other records are flagged, the entry date is judged wrong (record without own date), or the scan is illegible |
| `ungrounded` | core | the written name, or the count, is not in the entry text |
| `long-entry` | core | the entry has more than 100 records |
| `flagged-attribution` | strict core | a scan check calls only the observer or record type wrong |
| `flagged-place` | strict core | a scan check calls only the place wrong |
| `flagged-georef` | strict core | a scan check calls only the coordinates wrong |
| `attribution` | strict core | credited to Laubmann inside a pasted report of somebody else (separately dated report entry, Ismaning report abbreviations, typed insert, numbered typed list), or the observer's first name contradicts the initials in the text |
| `identification` | strict core | the diarist's own hedge, not at species level, or the written name is not an attested name of the taxon |
| `count` | strict core | approximate count, or 100 and more |
| `absence` | strict core | record of absence |
| `reading` | strict core | an objected reading correction inside the record's passage (also where the machine layer of the text put the check's better reading there: only a person settles it), or the entry's transcription was rated poor |
| `entry` | strict core | the scan check objects to the entry's kind |
| `entry-place` | strict core | the record has no place of its own and the entry's place is in doubt: objected to, header read differently, or used by three entries or fewer |
| `no-coords` | with coordinates | the place has no coordinates |
| `georef-unconfirmed` | with coordinates | coordinates from a gazetteer name match only, not from the reviewed place links |
| `place-doubt` | with coordinates | more than 15 % of the other records at the same coordinates are flagged for their place or coordinates |

A flag of a scan check counts where its field belongs: a record flagged only for its coordinates is a
correct occurrence with a wrong place, so it stays in the core and leaves the strict core.

## Calibration

Neither the old tiers nor the machine checks had been measured against the scans independently. The
rules above come from a blind audit.

**Sample.** 734 records in 645 entries, drawn from 29 strata: records the Gemini check accepted, split by
18 risk signals and a stratum without any signal; records Gemini flagged, by flagged field; unchecked
records (`strata.csv`). Each record carries the weight records-in-stratum / records-sampled.

**Audit.** 30 batches, each checked by a Claude Opus 5.5 subagent with crops of the page scans, the
transcription and the records, without the verdicts of the earlier checks
(`evaluation/corpus_tiers/auditor_instructions.md`, `answers/`). Per record: species, count, date,
locality, coordinates, observer, record type, status; per entry: date, place, boundaries, transcription
quality. 723 records were judged, 11 were unclear. Two species verdicts were checked by hand against the
scans; both held.

**Result** (`evaluation/corpus_tiers/evaluate_tiers.py <record_tiers.csv>`): weighted share of records with an
error; *occurrence* = species, count, date or status wrong, or no such record. Export `kg_exports_2026-10-04_text`
(with the machine layer of the text). 691 of the 723 judged records are in it; 32 have a new IRI, their entry was
read anew or their species corrected. The verdicts are those of the records of 1 October: a record the text layer
has corrected since still counts as wrong.

| Corpus | Records | Any field | Occurrence | Place | Observer / type | Coordinates | 90 % interval, any |
|---|---|---|---|---|---|---|---|
| full | 85,896 | 35.3 % | 13.8 % | 11.5 % | 15.4 % | 21.2 % | 31.3–39.5 % |
| core | 60,793 | 27.5 % | 7.4 % | 11.1 % | 13.3 % | 20.9 % | 22.7–32.8 % |
| strict core | 27,464 | 9.2 % | 1.8 % | 3.7 % | 4.7 % | 9.7 % | 5.8–13.0 % |
| strict core with coordinates | 16,834 | 6.9 % | 1.5 % | 1.9 % | 3.5 % | 6.8 % | 2.6–12.2 % |

The same tiers on the export of 1 October (`kg_exports_2026-10-01_checked`, all 723 judged records): full 85,631
records, 34.5 %; core 59,755, 25.5 %; strict core 27,408, 8.7 %; with coordinates 16,677, 6.4 %. On the 691
records in both exports the core goes from 26.8 % to 27.5 %: the new Gemini check of the entries read anew no
longer flags some records with an error, and they move into the core.

The tiers of 2 October 2026 measured on the same audit:

| Corpus | Records | Any field | Occurrence | Coordinates |
|---|---|---|---|---|
| core | 74,909 | 30.7 % | 11.3 % | 18.2 % |
| strict core | 69,150 | 30.0 % | 11.6 % | 19.2 % |
| strict core with coordinates | 44,372 | 28.5 % | 10.5 % | 19.2 % |

The old tiers hardly differed in quality. The Gemini check is right when it flags (two thirds of its flags
hold), but it misses most errors of attribution and many of place: about 30 % of the records it accepted
still have an error.

## What the audit found

- **Pasted reports credited to Laubmann.** Walter Wüst's numbered "Speichersee-Begehung" reports, Einhard
  Bezzel's and Werner Rathmayer's typed sheets and letters are transcribed as part of the entry and their
  records carry Laubmann as observer and `field-observation`. The rule `attribution` catches them through the
  separately dated report entries (ids with a letter suffix; 78 % of the audited records credited to
  Laubmann there are wrong in attribution), typed inserts and numbered typed lists (all audited ones wrong) and
  the report abbreviations Wb, Vkl, Ft, SD … (44 %).
- **"Heinrich Wüst".** Entity resolution merged Walter Wüst, W. Wüst, Dr. W. Wüst, H. Wüst and Wüst
  into one person labelled "Heinrich Wüst" (`resolution/persons.py` prefers the longest first name
  over usage: two mentions of "Heinrich Wüst" beat 1,218 of "Walter Wüst"). About 4,900 records carry this
  label; the rule `attribution` catches them where the text gives other initials (73 % of the audited
  records it flags are wrong in the observer). The label is a pipeline bug, to be fixed with the next export.
- **Dates of quoted records.** Literature records carry the date of the diary entry that quotes them
  (79 % wrong in the audit), so do records from cumulative species lists and retrospectives.
- **Misread names and places.** The transcription, and in a few cases the visual reading correction,
  turned "Fichtenkreuzschnäbel" into "Parus ater" or "Pöcking" into "Garching"; whole entries then carry
  the wrong place. In entries whose transcription the reading stage rated poor, 45 % of the records the
  Gemini check accepted still have an error.
- **Places of entries.** An entry place used by three entries or fewer is wrong in 36 % of the audited
  entries, a header read differently from the resolved place in 19 %.
- **Coordinates.** Gazetteer-only georeferences (OpenStreetMap or GeoNames name matches the place review did
  not confirm) are wrong in four of five audited records; reviewed place links in about one in ten.
- **Counts and names in the text.** A count that does not occur in the text (also not as a number word or
  sum) or a written name that does not occur in it marks a record wrong in about half of the audited cases.

## Limits

- The reference is a model audit, not a human one. The auditor is strict: a finer locality named in the
  text counts as a place error, a missing first name of an observer does not.
- The intervals are wide for the small corpora (153 audited records in the strict core with coordinates).
- The thresholds (a quarter flagged, 100 records, 100 individuals, three entries, 15 %) were chosen on this
  audit. They should be checked again with the human validation, which the graph page records per record.
