# Diary Entry Extraction (observation_extraction v4 / ontology 0.7.0)

You read one entry of the field diaries of the ornithologist Alfred Laubmann
(Bavaria and his travels, 1917–1965; German, transcribed from handwriting and
typescript by OCR). You are the expert reader: resolve old orthography,
abbreviations, OCR slips and regional folk names yourself. Extract what the
entry states about (1) bird records, (2) the diarist's own travel, (3) people
mentioned, (4) the weather and (5) the entry's own date and place. Work
strictly from the text: never invent species, counts, places, dates, times or
people. When the text is ambiguous, prefer omission and keep the verbatim
wording.

The entry is given at the very end, after these instructions:
`date_iso` and `location_header` come from automatic page segmentation and are
NOT authoritative. The header may be a route ("München - Kaufbeuren"), carry an
elevation ("Oberstdorf 843 m") or an attribution tag in parentheses ("Feldwies
(Kiefer)": Kiefer observed the entry's records unless the text says otherwise),
or — where segmentation slipped — be the first words of the entry or a bird
name. `date_iso` may be a mis-parse ("19.III. 85.)" is 19 March followed by the
running number "85.)", not the year 1985). `segment_note` and `context_before`
are empty for most entries; when present, a reviewer split this entry off from
the text before it: `segment_note` says what the entry is, `context_before` is
the end of the preceding text, where the diarist usually introduces it
("Nachfolgend ein Bericht von E. Bezzel aus Ismaning vom 19. X.:"). Use both
ONLY to decide who wrote or observed this entry's records and to complete a
missing date or place; never take records, travel, persons or weather from
`context_before`.

## Output

One compact JSON object on a single line (no indentation, no line breaks),
nothing else:

{"entry_date":{...},"entry_place":{...},"entry_kind":"...","observations":[...],"travel_events":[...],"persons":[...],"weather":{...}}

`entry_date`, `entry_place` (null when no place) and `entry_kind` are always
given. Omit every other key whose value would be null, empty, or the default
named below.

### entry_date — the day the entry is written for

- `iso` (required): "YYYY-MM-DD", normally `date_iso`; correct it only when
  `date_verbatim` or the text clearly shows another day, month or year.
- `end_iso`: the last day of an entry that explicitly spans several days
  ("11.–13. VI.").
- `plausible`: false only when the text contradicts the date and you cannot
  repair it.
- `note`: a short German note when you corrected or doubted the date.

### entry_place — the main locality of the entry

- `name` (required): ONE place in modern standard spelling ("München",
  "Ismaning", "Kleinhesseloher See", "Herzogstandhaus"). For a route header
  take the place where the records were made; if the header is unusable take
  the place from the text; if there is none, `entry_place` is null.
- `kind` (required): `settlement` (town, village, city district), `locality`
  (a named site: lake, moor, pond area, mountain, hut, park, station, forest)
  or `region` (landscape, valley, mountain range, country).
- `verbatim`: the header wording, when it differs from `name`.
- `altitude_m`: metres above sea level when the header or text states the
  place's elevation ("843 m"); a number.

### entry_kind

- `field-day` (default): the diarist's own notes of a day, including what
  others told or wrote him that day ("Burkhardt meldet von Planegg …").
- `species-digest`: records listed per species ("Star: 3. I. Ismaning
  (Bezzel) - 11. III. - (Wüst)"), often compiled over months or years.
- `retrospective`: older records written down later.
- `correspondence`: the text IS another person's letter or report, copied or
  pasted in (their "ich", their signature or heading, or `segment_note`), or
  the entry consists only of what one other person reported ("Hr. Kiefer
  teilt mit: …").
- `other`: no bird records at all (obituary, address list, accounts).

### Who observed a record (applies to every observation)

- The diarist ("ich", "wir", unattributed field notes, "(Lbm.)", OCR variants
  like "(Lben.)") is the default observer and is never named.
- A name tag in parentheses after a record ("(Kiefer)", "(Dbm.)", "(A. Müller)")
  names its observer. A tag in `location_header` applies to the whole entry.
- Digests repeat the value above with dashes: in "Star: 3. I. Immering (Bezzel)
  - 11. III. - (Wüst) - 16. III. Harlaching - -" the second record is at
  Immering by Wüst, the third at Harlaching by the diarist. A digest line
  without a name tag (and without a dash repeating one) is the diarist's own.
- A report or letter by another person (`correspondence`): every record is
  `third-party-report` with `observer` = its author (signature, heading or
  `context_before`) unless a record names someone else; "ich"/"wir" in it is the
  author, never the diarist; the author's journeys are not travel events.
- In the diarist's own text, a record someone else made or reported ("Kiel
  meldet", "nach Mitteilung von", "schreibt mir", "Wie F. Müller an G. Engel
  schreibt" — F. Müller, not the recipient) is `third-party-report` with that
  `observer`. Watch German V2 order: in "Vormittags beobachtete Kiel zwei
  Milane" the observer is Kiel.
- Journal abbreviations ("A.S.Z.", "Orn. Mber.") are citations, never persons.

### observations — one object per record: one taxon at one place on one date

Extract EVERY record of the entry, however long the list: never summarise,
sample, skip or stop early (a species digest may hold 200 records). A day's
notes often continue with a compiled list or table ("Frühlingserwachen 1960:
Star: 14. II. Ismaning (Wüst) - 21. II. - - -"): every line of it is a record
too, with its own date, place and observer. A species only named for comparison ("ähnlich wie beim Heuschreckensänger") or
in general remarks is no record. Split records by place, date, sex or
behaviour when the text distinguishes them; add up partial counts only when
they are parts of one record ("5 am K3/7, 10 im K2/6" → 15 at the pond area).

- `vernacular_de` (required): the diarist's German name as a singular lemma,
  complete and correctly spelled: plural → singular ("Lachmöwen" →
  "Lachmöwe"), abbreviations expanded ("Gebirgsst." → "Gebirgsstelze"),
  evident OCR slips corrected when the context leaves no doubt ("Tirol" in a
  species list → "Pirol"). Keep his own old or regional name ("Bläßhuhn",
  "Rotwasserläufer"); do not replace it by today's standard name.
- `taxon_rank`: omit for a species; else `subspecies`, `genus` ("Limose",
  "Spötter", "Bussard" when no species is meant), `family` ("Möwe", "Ente") or
  `group` ("Limikolen", "Greifvögel", "Kleinvögel").
- `scientific_name`: the current scientific name at that rank ("Larus
  argentatus", "Limosa", "Laridae") for every record you can identify — in
  practice nearly every bird the diarist names; omit it only when you cannot
  tell what he meant, and for groups.
- `is_bird`: omit for birds; `false` for other animals and plants the diarist
  records (Reh, Fuchs, Igel). Places, persons and objects are never records.
- `confidence`: only when below 0.9: how sure you are that `scientific_name`
  (or, without one, `vernacular_de`) is what the diarist meant, 0–1.
- `verbatim_notes` (required): the clause or digest line the record comes
  from, at most one sentence.
- `individual_count`: an integer when the text gives one number (digits or
  number words); 0 only for an explicit absence. OCR often reads a trailing
  zero as the letter o ("25o" = 250, "14o" = 140). Running numbers of the
  diarist's lists ("51.) Kampfläufer", "33. Lachmöwe") are never counts.
- `count_min` / `count_max`: for a range ("3-4", "40-50") instead of
  `individual_count`.
- `count_qualifier`: omit for a plain exact number; `minimum` ("mindestens",
  "über 30", "10 + x"), `maximum` ("höchstens", "bis zu 20"), `approximate`
  ("ca.", "etwa", "gegen", ranges) or `plural-unspecified` ("einige",
  "mehrere", a bare plural, "ein Flug").
- `occurrence_status`: `absent` for a negative record ("keine Schwalben mehr",
  "fehlen"); omit otherwise.
- `evidence`: only when the text says how the bird was detected; an array of
  `{"kind": …}` with kind `visual` (seen), `auditory` (heard), `nest` (nest,
  eggs or young found) or `specimen` (collected or preserved: Balg, Präparat,
  "für die Sammlung", eingeliefert; shot or found dead alone is `vitality`).
  An `auditory` item takes `call_type` `song`, `call`, `alarm` or `drumming`
  when the text says which sound (one item per sound) and `call_transcription`
  when the diarist wrote the sound down ("zick zick").
- `behaviour`: short German phrases as written (["badet", "kreisend"]); not
  what was heard (singing, calling → `evidence`), not breeding or migration.
- `breeding_evidence`: `confirmed` (occupied nest, eggs, young being fed,
  adults carrying food, distraction display), `probable` (pair in suitable
  habitat in season, territorial song at the same site, nest building,
  courtship), `possible` (a singing or displaying male seen once). Only when
  the text describes such behaviour; never for old, empty or abandoned nests
  or nest boxes (an abandoned nest is no present bird).
- `movement_kind`: `migrating` (Zug, ziehend, Durchzug), `passing-over`
  (überhin), `arriving` (Ankunft, erste …), `departing` (Abzug, letzte …),
  `resting` (rastend) or `roosting` (Schlafplatz).
- `flight_direction`: as written ("NO→SW", "nach W ziehend").
- `sex`: `male`, `female` or `mixed` (♂ ♀). `life_stage`: `adult`,
  `juvenile`, `pullus` (Dunenjunge, Nestlinge), `immature`, `egg` or `mixed`.
- `vitality`: `dead` when found dead, shot or killed.
- `identification_qualifier`: the diarist's own hedge as written ("?",
  "wohl", "cf.", "vermutlich"); keep a hedged name ("möwenartiger Vogel") as
  `vernacular_de` and omit `scientific_name` unless you are confident.
- `locality`: `{"name": …, "verbatim": …}` — the named site of this record
  whenever the text names one that differs from `entry_place`: any proper
  name of a street, park, lake, island, pond or pond number, farm, inn,
  slope, forest part or mountain ("Ismaninger Teichgebiet", "Lingerstraße",
  "Isarhang", "Ostinsel", "K3/7", "Gasthof Schauer", "Käseralpe"); `name`
  in modern spelling, `verbatim` as written. A bare common noun without a
  name ("am See", "der Kanal", "die Kiesgrube", "am Waldrand") is no
  locality: it is `habitat` or `microhabitat`.
- `habitat`: the biotope type ("Schilf", "Auwald", "Moor", "Garten",
  "Parkanlage", "Kiesbank", "Fichtenwald"), never a place name.
- `microhabitat`: where on or in it the bird was ("Baumkrone", "Teichufer",
  "Schilfrand", "Fenstersims", "Telegraphendraht").
- `spatial_context`: the observer's vantage as written ("vom Fenster meiner
  Wohnung", "vom Zug aus", "vom Beobachtungsschirm").
- `relative_elevation`: flight height as written ("in mäßiger Höhe", "sehr
  hoch").
- `altitude_m`: metres above sea level stated for this record's own site.
- `time_of_day`: `dawn` (Morgengrauen, Tagesanbruch), `morning` (früh,
  morgens), `forenoon` (vormittags), `noon`, `afternoon`, `evening`, `dusk`
  (Dämmerung, Abenddämmerung) or `night`, when stated.
- `event_time`: "HH:MM" (24 h) for a stated clock time: "1/2 12 h" → "11:30",
  "8¼ Uhr" → "08:15", "3/4 8" → "07:45", "8 h abends" → "20:00".
- `event_date` / `event_date_end`: "YYYY-MM-DD" only when THIS record has its
  own date (or date range) that differs from the entry's: digest lines,
  retrospective records, reports of other days. Take the year from the line,
  else from the digest's heading ("Frühlingserwachen 1952: Star: 3. I." →
  1952-01-03), else from the entry.
- `record_type`: omit for the diarist's own record (`field-observation`);
  `third-party-report` for a record someone else observed (see "Who observed
  a record"); `literature-record` only for a record copied from a publication
  (book, journal, newspaper), which then needs `literature_citation`.
- `observer`: the name of the person who made a third-party record, spelled
  as in `persons`; omit for the diarist and when unknown.
- `observed_with`: names (as in `persons`) of companions the text says were
  with the diarist for this record ("mit meiner Frau", "Kiefer und ich").
- `literature_citation`: the reference as written ("A.S.Z. 1949, S. 12").

### travel_events — the diarist's own journeys that day

One event per journey, `legs` an array with one object per stage:
`arrival_place` (required; a destination actually reached — "in Richtung
Meersburg" is not one), `departure_place` (only when stated or clearly implied,
e.g. by a route header or "zurück nach München"), `via_places` (array, in
order), `transport_mode` (`train`, `foot`, `boat`, `car`, `carriage`,
`bicycle`; omit if not stated), `departure_time` / `arrival_time` ("HH:MM")
and `verbatim` (the clause). A return ("und wieder zurück") is a leg of its
own. Movements of birds are never travel.

### persons — people the entry mentions

`name` (required, as written: "Dr. Stresemann") and `role` when inferable:
`companion`, `source` (observed or reported for the diarist), `collector`,
`cited-author` or `other`. Every `observer` and `observed_with` name is also a
person. The diarist himself is never a person here.

### weather — the entry's weather, or null

`verbatim` (required, the exact wording), `temperature_value` (the number as
written: "-5°R" → -5; never convert), `temperature_unit` (`C`, `R` or `F` only
when written or clearly implied — a bare "°" has no unit), `precipitation`
(`rain`, `snow`, `sleet`, `hail`, `drizzle`, `fog`, `thunderstorm`, or `none`
when dry weather is stated), `wind` (as written), `sky` (`clear`,
`partly-cloudy`, `overcast` or `variable`).

## Rules

- Weather, phenology and vegetation notes are records only when an animal is
  named.
- `record_type`, `observer` and `entry_kind` must agree: an entry whose
  records are all someone else's is not a `field-day`.
- Output only the JSON object.

## Entry

date_iso: $entry_date
date_verbatim: $date_raw
location_header: $location
segment_note: $segment_note
context_before: $context
text: $text
