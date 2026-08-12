# Diary Entry Extraction

You are given one complete entry from the field diaries of the ornithologist
Adolf Laubmann (Bavaria, early 20th century), in German. You are the expert
reader: resolve old orthography, abbreviations, and regional folk names
yourself, and use the date and location header as context. Extract everything
the entry states about (1) bird observations, (2) the diarist's own travel,
and (3) people mentioned. Work strictly from the text — never invent species,
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
{"observations": [...], "travel_events": [...], "persons": [...]}
```

Every array may be empty.

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

The diarist himself is never a persons entry.

## Rules

- Weather, phenology, and vegetation notes alone are not observations unless a
  bird is named.
- Preserve uncertainty. If the diarist hedges ("möwenartiger Vogel"), keep the
  verbatim name as `vernacular_de` and set `scientific_name` to `null`.
- Output **only** the JSON object, no prose, no code fences.
