# Observation Extraction

You extract ornithological observations from a single German diary entry written
by the ornithologist Adolf Laubmann (early 20th century). Work only from the
text; never invent species, counts, or places that are not supported by it.

## Input

- `entry_date`: ISO date of the entry (context only).
- `location`: the entry's stated locality (context only).
- `text`: the entry body (`text_clean`).

```
date: $entry_date
location: $location
text: $text
```

## Task

Return a JSON array of observation objects. Emit one object per distinct bird
mention. Each object conforms to `schemas/observation.schema.json`:

- `vernacular_de` (required): the German bird name as a lemma
  (e.g. "Lachmöwe", not "Lachmöwen").
- `scientific_name`: the Linnaean binomial **only if you are confident**;
  otherwise `null`. Do not guess.
- `verbatim_notes` (required): the clause/sentence the observation is drawn from.
- `individual_count`: integer ≥ 1 only if an explicit number is given, else `null`.
- `count_qualifier`: one of `exact`, `minimum`, `approximate`,
  `plural-unspecified`, or `null`.
- `evidence`: array of `{kind, call_type?, call_transcription?}` where `kind` is
  `visual`, `auditory`, `nest`, or `specimen`. Use `auditory` with a `call_type`
  (`song`/`call`/`alarm`/`drumming`) when a vocalisation is described.
- `behaviour`: array of short German behaviour phrases (e.g. "brütet").
- `confidence`: your confidence in the identification, 0–1.

## Rules

- Weather, phenology, and travel notes are not observations unless a bird is named.
- Preserve uncertainty. If the diarist hedges ("möwenartiger Vogel"), keep the
  verbatim name and set `scientific_name` to `null`.
- Output **only** the JSON array, no prose.
