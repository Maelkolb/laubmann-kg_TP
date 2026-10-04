# Audit of bird records extracted from Alfred Laubmann's field diaries (Bavaria, 1917–1965)

You check, against the page scans, whether records that a language model extracted from the diary are right.
Your answers are the reference against which automatic quality checks will be calibrated, so be careful and
honest: say "unclear" when you cannot decide, never guess.

## Input

Your batch file (path in your task) holds entries. Each entry has

- `entry_id`, `entry_date`, `entry_place`: the diary entry as the pipeline dated and placed it,
- `scan_crops`: JPEG crops of the page scan(s) showing the entry (open each with the Read tool; the handwriting is
  German, Latin cursive; typed carbon copies and newspaper clippings are pasted in some entries),
- `transcription`: the machine transcription of the entry, already corrected once against the scan
  (`<u>` = underlined in the diary),
- `records`: the extracted records to check. Only check these records, not other birds of the entry.

Each record says: `written_name` (the name as the diary writes it), `taxon_de` / `taxon_sci` / `rank` (the taxon it
was linked to), `count` (+ `count_range`, `count_qualifier`), `status` (present / absent = "the bird was looked for and
not there"), `date` (date of the observation; an interval "start/end" for multi-day entries), `locality` (+
`locality_as_written`), `coordinates` (+ uncertainty in metres), `observer`, `record_type`, `basis`, optional `sex`,
`life_stage`, `breeding`, `identification_qualifier` (the diarist's own hedge such as "wohl", "?"), and `passage`
(the sentence the model took the record from).

## How to check

Read the transcription, then look at the scan for the words that matter for each record: the bird name, the numbers,
the place names, the dates, the names of people. The transcription can be wrong; the scan decides.

For every record judge each field:

- **species**: `right` if the diary means this bird and the linked taxon is that bird. Old or regional names are
  right when they mean the same species (Grünling = Grünfink, Rotkehlchen, Gimpel = Dompfaff, Fischreiher =
  Graureiher, Weidenlaubvogel = Zilpzalp, Steinkauz …). A group name in the diary ("Möwen", "Enten") linked to the
  matching genus or family is right. `wrong` if the name is misread (the scan shows another bird), the linked taxon
  is another species, or a species is given where the diary only names a group.
- **count**: the number of individuals the passage gives for this bird at this place and date. "1 + 1" = 2,
  "ein Paar" / "♂♀" = 2, "5 ♂♂ 3 ♀♀" = 8, a range "6–8" = 6 with range 6–8, "50 Paare" = 100 is acceptable. If the
  diary gives no number ("einige", "viele", "ein Flug") the count must be empty; a count where the diary has none is
  `wrong`. Absences: empty or 0 is right. Use `n/a` when no count is given and none is in the text.
- **date**: the day of the observation. A record the entry quotes from an earlier day or year ("am 6. IV. hörte
  …", "nach Jäckel 1855 …") must carry that date; otherwise the entry date. `wrong` if the day, month or year is not
  what the diary says (a multi-day interval that contains the day is right).
- **locality**: the place of THIS observation: the specific site the passage names, otherwise the entry's place.
  Spelling and modern standard names are fine. A broader place that contains the named site is acceptable. `wrong`
  if it is another place than the text means, or a word that is not a place.
- **georef** (only when `coordinates` are given): do the coordinates lie at the place the text means (allow the
  stated uncertainty, or the extent of the village, lake or area)? Use your knowledge of Bavarian and European
  geography. `right`, `wrong`, or `cannot_tell` (micro-toponyms you do not know).
- **observer**: who saw or heard the bird: Alfred Laubmann (the diarist, "ich", "wir") for his own observations,
  otherwise the person who reported it; for a literature record the cited author or empty. Name variants and
  missing first names are fine. `wrong` if another person is named in the text, or the diarist is credited with
  someone else's report, or vice versa.
- **record_type**: `field-observation` = the diarist (with or without companions) observed it; `third-party-report`
  = someone else told or wrote him; `literature-record` = taken from a publication, newspaper, catalogue or
  collection list.
- **status**: present or absent (absent only when the text says the bird was NOT there / not seen / missing).
- **other**: sex, life stage, breeding, if given: `wrong` only when the text clearly contradicts them, else `right`.

Then the record **verdict**:

- `ok`: every field above is right (or n/a). Georef does not affect the verdict, you judge it separately.
- `wrong`: at least one field is wrong. Put the right value of each wrong field into `correct`.
- `spurious`: the entry contains no such record: the bird is not mentioned, or only as a comparison, an example, a
  name in a title, a species of a list heading without observation, or the record duplicates another record of the
  same observation.
- `unclear`: you cannot decide even with the scan (illegible, crop missing the passage).

Per entry also judge: `entry_date_ok` (the header date on the scan is `entry_date`; true / false / null if
unreadable), `entry_place_ok` (the entry's place is `entry_place`), `boundary_ok` (the transcription is exactly this
entry: it does not contain another dated day's text and does not miss the beginning), and `transcription_quality`
of the passages you checked (`good` = no errors that matter, `minor` = small errors not affecting names or numbers,
`poor` = errors in bird names, numbers or places).

## Output

Write one JSON file, UTF-8, exactly this shape, to the answer path given in your task (use the Write tool; do not
put helper scripts or files anywhere else):

```json
{"batch": 7, "entries": [
  {"entry_id": "L12-e0034", "entry_date_ok": true, "entry_place_ok": true, "boundary_ok": true,
   "transcription_quality": "minor", "note": "",
   "records": [
     {"record_id": "obs_1a2b3c4d5e6f", "verdict": "wrong",
      "species": "right", "count": "wrong", "date": "right", "locality": "right", "georef": "right",
      "observer": "right", "record_type": "right", "status": "right", "other": "right",
      "correct": {"count": "3"}, "evidence": "scan: '3 Gimpel am Futterhaus'", "confidence": 0.9}
   ]}
]}
```

Every record of the batch must appear exactly once with its `record_id`. `evidence` is a short quote of what the
scan or transcription says (max. 20 words). `confidence` is how sure you are of the verdict (0–1). Keep notes short.
