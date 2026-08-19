# Habitat → EUNIS classification

You classify habitat labels from the ornithological field diaries of Alfred
Laubmann (Bavaria and the Alps, 1917–1965; occasional journeys to the Bodensee,
the Adriatic and Greece) into the **EUNIS habitat classification (2012)**.
Each label is the habitat exactly as the diarist wrote it, in German, often one
word ("Garten", "Schilf", "Hangwald", "Auwald", "Kiesgrube", "Dachfirst").

## EUNIS classes you may use

Codes and names of the classes down to level 3 (marine A only to level 2):

```
$eunis_list
```

You may also answer with a deeper EUNIS 2012 code (level 4, e.g. `C3.21`
Phragmites beds, `G1.21` riverine ash–alder woodland, `I2.21` … ) when you are
certain it exists and fits — such codes are validated against the full
classification; an unknown code is treated as no answer.

## Task

For every label return the best EUNIS class and how it relates to the label:

- `match`: `exact` — the label means this class (Auwald → G1.2, Schilf → C3.21,
  Hausgarten → I2.2, Kiesgrube → J3.2 "Active opencast mineral extraction
  sites"); `close` — the label is a species of this class or a slightly
  different scope (Hangwald → G1, Fichtenwald → G3.1, Wiese → E2);
  `broad` — the label is more specific than any class or names a feature that
  only falls inside a class (Dachfirst → J1, Futterplatz → I2.2, Isarkies → C3.6);
  `none` — not a habitat (a bird name, a place name, "überall", nonsense).
- `code`: the EUNIS code (or null with `match: none`).
- `confidence`: 0–1 that a Central-European habitat ecologist would accept the
  assignment (1.0 unambiguous; ~0.5 defensible guess).
- `note`: ≤ 12 words, German or English, only when the reading needs one.

Rules: prefer the most specific class the label supports, but never guess
below the evidence (a bare "Wald" is G, not G1.6). Water: C1 standing waters,
C2 running waters, C3 littoral zone / reedbeds; bogs D1–D2, fens D4–D5;
grassland E; heath/scrub F; woodland G (G1 broadleaved deciduous, G2 broadleaved
evergreen, G3 coniferous, G4 mixed, G5 lines of trees, small woods, clearings);
sparsely vegetated H (screes, cliffs, snow, ice); cultivated/gardens I (I1
arable, I2 gardens/parks); buildings, industrial, urban J (J1 buildings, J2
low-density buildings, J3 extractive sites, J4 transport networks, J5
man-made waterbodies, J6 waste); habitat complexes X (X04 raised bog complexes,
X10 bocage …). Alpine: E4 alpine grasslands, F2 arctic/alpine scrub, H2 screes,
H3 cliffs, H4 snow and ice. Output only the JSON.

## Labels

```
$labels
```

Return a JSON object `{"items": [{"label": "...", "code": "...", "match": "...",
"confidence": 0.0, "note": "..."}, ...]}` with exactly one item per label, in
the given order, labels copied verbatim.
