# Diary Entry Extraction

You are given one complete entry from the field diaries of the ornithologist
Alfred Laubmann (Bavaria, early 20th century), in German. You are the expert
reader: resolve old orthography, abbreviations, and regional folk names
yourself, and use the date and location header as context. Extract everything
the entry states about (1) bird observations, (2) the diarist's own travel,
(3) people mentioned, and (4) the weather. Work strictly from the text — never invent species,
counts, places, times, or people it does not support. When the text is
ambiguous, prefer `null` or omission and keep the verbatim wording.

## Input

```
date: $entry_date
location: $location
text: $text
```

## Output

A single JSON object, nothing else:

```
{"observations": [...], "travel_events": [...], "persons": [...], "weather": {...}}
```

Every array may be empty; `weather` may be null.

### observations — one object per distinct bird record

- `vernacular_de` (required): the German bird name as a singular lemma
  ("Lachmöwe", not "Lachmöwen").
- `scientific_name`: the Linnaean binomial **only if you are confident**;
  otherwise `null`. Do not guess.
- `verbatim_notes` (required): the exact clause/sentence the record is drawn from.
- `individual_count`: integer ≥ 1 only if the text gives a number (digits or
  number words), else `null`.
- `count_qualifier`: `exact`, `minimum`, `approximate`, `plural-unspecified`,
  or `null`.
- `evidence`: array of `{kind, call_type?, call_transcription?}` with `kind` one
  of `visual`, `auditory`, `nest`, `specimen`. Use `auditory` with a `call_type`
  (`song`/`call`/`alarm`/`drumming`) when a vocalisation is described, and put
  the diarist's phonetic rendering ("zick zick") in `call_transcription`.
- `behaviour`: JSON array of short German phrases as written
  (`["singt", "brütet"]`); `[]` when none.
- `habitat`: the habitat/biotope the bird was in, if the text states one
  ("Schilfrand", "Auwald", "Isarauen"); else `null`.
- `confidence`: your confidence in the identification, 0–1.
- `record_type`: how this record reached the diary — `field-observation` (the
  diarist saw or heard the bird himself; the default when nothing suggests
  otherwise), `third-party-report` (someone else observed it and told or wrote
  to the diarist: "meldet", "berichtet", "teilt mit", "schreibt", "nach
  Angabe/Mitteilung von"), or `literature-record` (the entry digests a
  publication, journal, or card index — later volumes contain digest lines like
  "Heckenbraunelle: 19. III. 49 Feldmoos (Kiefer)" naming an external source).
  Judge the entry's style, not only the sentence.
- `observer`: the person who actually made the observation, named as written
  ("Kiel", "F. Müller"), **only when it is not the diarist**; else `null`.
  Watch German V2 word order: in "Vormittags beobachtete Kiel zwei Milane" the
  observer is Kiel, not a place. Attribution tags in parentheses name the
  observer or source: "(Kiefer)" → observer "Kiefer"; "(Dbm.)" is an
  abbreviated person tag. "(Lbm.)" is Laubmann himself → `null`. In "Wie
  F. Müller an G. Engel schreibt, ..." the observer/source is F. Müller —
  G. Engel is only the recipient. First person ("ich", "wir", unattributed
  field notes) is the diarist → `null`.
- `literature_citation`: the bibliographic reference exactly as written when
  the record comes from literature ("A.S.Z. 1949, S. 12", "Orn. Monatsber.
  41"), else `null`. Journal abbreviations in parentheses such as "(A.S.Z.)"
  are citations, NOT persons — never put them in `observer`.

### travel_events — journeys the diarist himself makes

One event per coherent journey; `legs` is an array with one object per segment:

- `departure_place` / `arrival_place`: place names as written. `arrival_place`
  is required; leave `departure_place` `null` when the text only implies leaving
  the current location.
- `via_places`: JSON array of intermediate stations or waypoints, in order.
- `transport_mode`: `train`, `foot`, `boat`, `car`, `carriage`, `bicycle`, or
  `unknown`.
- `departure_time` / `arrival_time`: 24h `"HH:MM"` if stated ("8¼ Uhr" →
  `"08:15"`), else `null`.
- `verbatim`: the clause describing the leg.

Movements of birds are never travel events — only the observer's own journeys.

### persons — people the entry mentions

- `name` (required): as written ("Dr. Stresemann").
- `role`: `companion`, `source`, `collector`, `cited-author`, or `other` if
  inferable, else `null`.
- `verbatim`: the mentioning clause.

The diarist himself is never a persons entry. People who observed or reported
for the diarist, and cited authors, also belong here (role `source` or
`cited-author`) so records can link to them.

### weather — the entry's weather report, or `null`

One object for the whole entry (not per observation); `null` when the entry
says nothing about the weather.

- `verbatim` (required): the exact weather wording, unmodified ("Wetter trüb
  und kalt, nachmittags Regen").
- `temperature_value`: the stated number only ("-5°R" → -5), else `null`.
  Historical entries may use Réaumur — never convert units, report the number
  exactly as written.
- `temperature_unit`: `C` (Celsius), `R` (Réaumur), or `F` (Fahrenheit) when
  stated or clearly implied ("°R", "Réaumur" → `R`); `null` when no unit is
  given.
- `precipitation`: `rain`, `snow`, `sleet`, `hail`, `drizzle`, `fog`,
  `thunderstorm`, or `none` if the text explicitly notes dry weather; else `null`.
- `wind`: the wind description as written ("starker SW-Wind"), else `null`.
- `sky`: `clear`, `partly-cloudy`, `overcast`, or `variable`; else `null`.

## Rules

- Weather, phenology, and vegetation notes alone are not observations unless a
  bird is named — put weather into the top-level `weather` object instead.
- Preserve uncertainty. If the diarist hedges ("möwenartiger Vogel"), keep the
  verbatim name as `vernacular_de` and set `scientific_name` to `null`.
- Output **only** the JSON object, no prose, no code fences.
