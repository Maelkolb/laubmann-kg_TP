# Estimated quality of every record

Every record of the graph carries an estimate of how likely it is to be wrong, per field and as a whole. It
replaces the four corpus tiers of 3 October (`docs/corpus_tiers.md`, kept for the record): the tiers asked one
question of every user (is anything about this record in doubt?) and threw away two thirds of the data to answer
it; the estimate lets a user choose the field that matters for the question at hand and see how many errors the
chosen records still hold.

The graph itself does not change. The estimate is a layer: `record_quality.csv` (one row per occurrence of the
Darwin Core Archive), the review layer of the validation pages (`q` of every record, `build_review.py
--quality`), the filter of the graph page, the explorer and the link page.

## Two checks of every record

| | Record check (round 4, re-run for changed entries) | Blind check (round 7) |
|---|---|---|
| Tool | `tools/validation_ui/machine_review/record_check.py` | `tools/validation_ui/machine_review/blind_check.py`, compared by `blind_compare.py` |
| Model | Gemini 3.8 Flash | Gemini 3.7 Flash |
| Sees | page scans, transcription, every value the graph holds for the record | page scans, transcription, the record's written name and the passage it was taken from; numbered lists of the places and persons the graph holds for the entry, without saying which record has which |
| Says | right, or which fields are wrong and the right values | its own reading of every field: does the record exist, species, count, absence, the places that correctly say where it was made (the specific site and every place containing it), date (the entry's day, its own day, a year, undated), observers, record type |
| Weakness the audit showed | accepts what it is shown: about 30 % of the records it calls right have an error, mostly place, observer and date | reads a passage the way the extraction did when the transcription or the passage misleads both |

`blind_compare.py` compares the blind reading with the graph field by field: species by GBIF key (the
check's scientific name matched against the backbone, so synonyms agree) or name; counts as numbers or ranges;
dates as days or intervals (a year or "undated" agrees only with a coarse interval); places by the listed place
the record has; observers by surname, the diarist apart; record type by its kind.

## From two verdicts to a probability

For every field the two verdicts give a status:

| Status | Meaning |
|---|---|
| `ok` | both checks accept the graph's value |
| `one` | only one check judged the field and accepts it |
| `c1` | only the record check doubts it |
| `c2` | only the blind check reads something else |
| `both` | both doubt it |

Coordinates have their own status: from a reviewed place link (`rev`) or a gazetteer name match only (`gaz`),
with `-c1` when the record check flags them.

The blind audit of 3 October (`evaluation/corpus_tiers/`: 734 records drawn from 29 strata, checked against the
scans by Opus subagents that saw no machine verdict, each weighted to its stratum) gives the share of wrong fields
in each status. `tools/validation_ui/graph_check/record_quality.py` measures it per field, per status and per
risk group (the record's old corpus tier: outside the core, core, strict core and above), each rate shrunk
toward the coarser one when few audited records fall into it. Audited records whose field changed since the
audit (the entries read anew on 4 October) do not count for that field; attributions changed on 5 October are
judged against the auditor's reading, as in `evaluate_tiers.py`. A record's estimated error is
1 − Π(1 − p<sub>field</sub>) over existence, species, count, date, place, observer and record type; the
occurrence estimate uses existence, species, count and date; coordinates are estimated apart.

Levels for display: 1 under 10 %, 2 from 10 to 25 %, 3 from 25 to 50 %, 4 from 50 %.

## Results

Export `kg_exports_2026-10-05_attribution`; blind check of 9,145 entries (85,787 records; 9 entries without a page
scan and 75 records the check did not answer keep the record check alone), $50.52. Summary:
`data/cache/graph_check/quality/quality_summary.json` (Drive `HistOrniGraph_Final_Graph_NoVal/quality/`).

| Estimated error of the record | Records | Share | Estimated for the audited records | Found in the audit (audited records) |
|---|---|---|---|---|
| under 10 % | 24,283 | 28.3 % | 8.2 % | 8.6 % (238) |
| 10 to 25 % | 35,550 | 41.4 % | 23.3 % | 32.5 % (120) |
| 25 to 50 % | 8,922 | 10.4 % | 29.3 % | 29.5 % (197) |
| 50 % and more | 17,139 | 20.0 % | 71.0 % | 62.1 % (136) |

Cross-validated (five folds by entry): 28.2 % of the audited records estimated with an error, 29.1 % found; for the
occurrence 13.7 % against 13.8 %; weighted AUC 0.72. Over the graph the estimate expects 26,230 records (30.5 %)
with a wrong field, 13,123 (15.3 %) with a wrong occurrence, 20.5 % wrong coordinates.

Share of the field wrong in the audit, per status (audited records):

| Field | ok | c1 | c2 | both |
|---|---|---|---|---|
| species | 4 % (654) | 17 % (26) | 11 % (10) | – |
| count | 2 % (636) | 12 % (14) | 23 % (18) | 45 % (14) |
| date | 2 % (604) | 25 % (1) | 54 % (69) | 73 % (10) |
| place | 6 % (605) | 13 % (7) | 73 % (24) | 42 % (6) |
| observer | 5 % (594) | 16 % (5) | 29 % (68) | 18 % (4) |
| record type | 0 % (627) | – | 20 % (43) | 3 % (17) |
| record exists | 0 % (659) | 0 % (2) | 0 % (17) | 36 % (13) |
| coordinates | rev 12 % (366), gaz 66 % (42), gaz-c1 79 % (11) | | | |

Statuses over the graph: the blind check reads the date differently for 8,467 records, the observer for 7,702, the
record type for 6,236, the place for 3,890, the count for 3,452. Both checks doubt a field and propose the same
value in 3,115 fields (record type 1,066, place 758, observer 570, date 325, count 230, species 166).

Thresholds of the filter (estimate): under 50 % 68,755 records (20.3 % expected wrong), under 25 % 59,833
(17.9 %), under 10 % 24,283 (8.3 %); occurrence measure under 10 % 55,124 records (5.8 % expected wrong in
species, count, date); place under 5 % 27,633 (2.8 %); coordinates under 10 % 17,757 (6.0 %). For comparison, the
tiers as found in the audit: core 61,304 (22.2 %, occurrence 7.2 %), strict core 29,066 (9.5 %, 3.6 %).

The estimate is less exact in the second level (records estimated at 10 to 25 % were wrong in 32.5 % of the
audited ones) and conservative in the fourth (62.1 % against 71.0 %).

## Limits

- The reference is the model audit of 3 October, not a human one. Its 691 records in this export are both the
  calibration and the test; the test is cross-validated (five folds by entry), but the audit was also used to
  design the tiers, and the risk groups come from those tiers.
- The blind check is a Gemini model like the record check. Where both read a passage the same wrong way, both
  accept the error; the audit measures how often that happens (the residual rate of `ok`), it does not remove it.
- The estimate is a probability for a group of records like this one, not a verdict on the record. A record at
  8 % can be wrong; summed over a selection, the probabilities give the expected number of errors in it.
- Fields the audit hardly saw in a status keep the coarser rate; `both` and `c2` rest on few audited records
  for some fields (see the table above).

## Reproduce

```
X=data/exports/kg_exports_2026-10-05_attribution; I=data/cache/graph_check/in
R="G:/My Drive/HistOrniGraph_Final_Graph_NoVal/machine_review"
python tools/validation_ui/machine_review/blind_check.py $I/payload_final.b64 $I/triples_final.pkl \
    --out data/cache/blind_check_r1 --dwca $X/dwca --budget 80
python tools/validation_ui/machine_review/blind_compare.py $I/triples_final.pkl \
    --work data/cache/blind_check_r1/blind_check --dwca $X/dwca
python tools/validation_ui/graph_check/record_quality.py --dwca $X/dwca \
    --blind data/cache/blind_check_r1/blind_check/blind_checks.csv --record-check "$R/record_checks.csv" \
    --tiers "$R/record_tiers.csv" --audited-dwca data/exports/kg_exports_2026-10-01_checked/dwca \
    --before-dwca data/exports/kg_exports_2026-10-04_text/dwca --out data/cache/graph_check/quality
python tools/validation_ui/graph_check/build_review.py ... --quality data/cache/graph_check/quality \
    --out data/cache/graph_check/review.json
```

The answers of the blind check are cached (`data/cache/blind_check_v1`, Drive
`HistOrniGraph_output/blind_check_cache_v1`); a re-run costs nothing for unchanged entries.
