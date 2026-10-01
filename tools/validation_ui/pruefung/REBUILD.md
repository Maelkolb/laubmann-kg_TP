# Rebuilding the review page on a new export

History: `Laubmann_Pruefung.html` (2026-09-30, Drive `Laubmann_KG_Maschinenpruefung_2026-09-30/Laubmann_Pruefung`)
signed off the machine review of the 2026-08-19 graph. This folder is its successor,
`Laubmann_Validierung.html`: one page with (a) the sign-off of the machine-checked data over all
machine rounds and (b) the review of everything else (not checked entities, habitats, QA flags),
plus the transcript corrections of the visual reading. Usage, contracts, build: `README.md`.

## 1. Payload of the graph (tools/validation_ui, see its README)

    python tools/validation_ui/load.py <export>/rdf/laubmann_sample.ttl triples.pkl
    # pages_geometry.json and the line profiles depend on corpus + scans only -> reuse
    #   (Drive: HistOrniGraph_output/validation_ui_2026-09-29/build/pages_geometry.json)
    python tools/validation_ui/build_payload.py <export>/review --triples triples.pkl --corpus <corpus_dir> \
        --geometry pages_geometry.json --vernaculars vernaculars.json --built <date> \
        --second-reading second_reading.json --third-reading third_reading.json --person-matches person_matches.json \
        --machine-readings <r3>/readings_machine.json --out payload.b64
    # readings are keyed by entry_uid|name|occurrence and by label, so earlier files still apply

## 2. Machine rounds

- r1 (`machine_review/`, night 29/30 Sept) and r2 (`machine_review2/`, afternoon 30 Sept) ran on the
  2026-08-19 graph: pass them as `DIR@<Laubmann_Abgleich.html or its payload>` so their verdicts are read
  against that graph ("before" state) and shown with the evidence of the new graph. Their machine rows
  above the thresholds are already applied in a graph built with `review.machine` enabled; the page
  shows that ("now in graph: = proposal, already applied") and still asks for the sign-off.
- r3 on the final graph: same files as r1 (`tools/validation_ui/machine_review/merge.py`) plus
  `transcript_checks.csv`. No `@`. Missing files or folders are skipped.
- `round2_prepare.py` / `merge_round2.py`: the second visual round (kept for reference).

## 3. This page

    python build_data.py --payload payload.b64 --machine <r1>@<graph0819> <r2>@<graph0819> <r3> \
        --arbeit <arbeit> <arbeit2> [<arbeit3>] --review <export>/review --dwca <export>/dwca \
        --legacy-pruefung Laubmann_Pruefung.html --out data
    python assemble.py --data data Laubmann_Validierung.html
    tests/: smoke.py, interaction_export.py (+ loaders_check.py), import_progress.py, lang_switch.py, rounds_check.py

## Open

- record fields (count, locality, date, observer …) now have a pipeline consumer
  (`normalization/observation_corrections.py`, one row per field: `field`, `new_value`). This
  page's `observation_corrections.csv` (machine verdict + agree/disagree per record) is an audit
  file in another layout and is NOT read by it; field corrections are made in the graph page
  (`tools/validation_ui/graph_check/`), which exports the consumer's contract
- r3 transcript checks "partly" with a better text are shown only when they fall into the sample
