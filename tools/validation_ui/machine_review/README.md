# Machine review ("Maschinelle Prüfung")

Language-model subagents (Claude Sonnet 5.5, driven from a Claude Code
session) check the graph's entity links and a sample of its records, and the
results are written in the same decision contracts the reviewer UI exports —
so they survive a re-extraction with another ontology or prompt and can be
used by the pipeline, by the reviewer UI, or both. Background:
[`docs/validation.md`](../../../docs/validation.md), section 8.

## What is checked

| check | unit | evidence given to the agent | answer |
|---|---|---|---|
| **species, text** (`prepare_taxa.py` → `taxa/batches`) | every taxon entity (linked to GBIF or not) with all its written names | GBIF record + German names (GBIF/Wikidata), evidence class per name (A/B/C/L), diary passages, the earlier Gemini/Opus readings, incoming merge candidates | is the GBIF link right (`ok`/`wrong`+name/`none`), per written name `same`/`other`/`none`/`unsure` with scientific name, per candidate `belongs` |
| **species, scan** (`prepare_taxa.py` → `sheets/`) | doubtful written names (classes B, C, L): 1–2 line images per name | contact sheets of 8 line crops (orange box = the line), transcription word, context, current taxon, earlier readings | reading of the word, kind, species, confidence, legible |
| **persons** (`prepare_persons.py`) | persons linked to Wikidata or with ≥ 3 mentions | written names, roles, years, passages, Wikidata candidates enriched (dates, occupation, GND), GND candidates from lobid.org (dates, occupation, places, GND→Wikidata cross-reference) | Wikidata item / GND record / none / unclear, whether the automatic link is right |
| **places** (`prepare_places.py`) | places with ≥ 3 mentions | the graph's location + GeoNames/Wikidata record, the header places of the entries that mention it (anchors, with distances), passages, Nominatim candidates for the label and for "label, main anchor" (contextual geocoding) | `ok` / `wrong` (+candidate) / `unlocated_ok` (+candidate) / `unlocatable` (+hint) / `not_a_place` |
| **extraction** (`prepare_entries.py`) | stratified sample of entries (random / poor transcript / third-party reports / long lists / no records) | scan pages, the text the extraction read, every correction of the visual reading, every record the graph holds for the entry with its DwC-A georeference | per observation `ok`/`wrong` (fields + correction)/`spurious`, missing records, entry date/place/kind, a verdict per transcript correction (`right`/`partly`/`wrong`/`unclear`), misread words |
| **habitats** (`prepare_habitats.py`) | every habitat concept | written forms, passages, current EUNIS class and match, the EUNIS list levels 1–3 | `ok` / `other` (+code, match) / `none` / `unsure` |

`merge.py` joins the answers. For every written taxon name it tallies the
independent opinions (text agent, scan agent, Gemini second reading, Opus
third reading, incoming-candidate votes) after resolving each named species
to a GBIF species key (subspecies keys are lifted to the species), and keeps
the majority with its **confidence** and **agreement** (number of sources).
Conflicting confident opinions give `unsure`. Persons get a second source
from the Wikidata ↔ GND cross-reference (`xref`) and the Opus person matching;
places from deterministic checks independent of the agent's judgement:
`nominatim` (an independently geocoded candidate lies at the graph point),
`anchor` (the chosen candidate lies within 30 km of the main header place while
the current point, if any, is more than 50 km away) and `generic` (the label is
a generic noun such as *Feld* or *Weiher*).

## Outputs (`machine_review/`)

| file | contract | use |
|---|---|---|
| `identities_machine.csv` | `review/identities.csv` + `confidence`, `agreement`, `sources` | pipeline (`review.machine` in the config: rows above the thresholds fill the forms no human reviewed; `data/review/identities.csv` always wins), UI import |
| `value_corrections_machine.csv` | `review/value_corrections.csv` + `confidence` | pipeline (`review.machine.value_corrections`), single mentions the scan agent read as another species / not a bird |
| `text_corrections_machine.csv` | `review/text_corrections.csv` | suggestions only (a text correction re-reads the entry live); not wired into the config |
| `readings_machine.json` | `third_reading.json` shape, per mention key | UI: third model column in *Zweitlesung* (`build_payload.py --machine-readings`) |
| `machine_review.json` | verdicts per entity / name / mention, keyed by label and name | UI: box "Maschinelle Prüfung" on every entity, badge per name (`build_payload.py --machine-review`); one click takes the verdict over as the reviewer's decision |
| `graph_checks*.csv` | per observation / missing record / misreading / entry | evaluation of the extraction |
| `report.md` | numbers and findings | |

Nothing is applied to the graph by the machine review itself. The pipeline
takes machine rows only above `review.machine.min_confidence` (0.9) with
`min_agreement` (2) independent sources, and only where no human decision
exists for the same written name; the UI shows every verdict and lets the
reviewer accept or overrule it.

## Round 3 on the final graph (2026-10-01)

Later rounds check only what earlier rounds did not see (`--known machine_review.json …` on
prepare_taxa/persons/places: names judged before are skipped; `--max-mentions` splits the
long tail of places). Every name batch also goes to Gemini (`gemini_verify.py`, same
INSTRUCTIONS.md and batch, answers in `<check>/answers_gemini/`); an agreeing Gemini answer is
one more independent source in `merge.py`, a disagreeing one lowers the confidence; batches no
Claude agent answered fall back to Gemini's answer as the single (never auto-applied) verdict.
`research_persons.py` searches Wikidata by surname for persons the first pass left without a
candidate (initial + surname, titles). `combine_rounds.py --rounds r1 r3 … --out data/review/machine`
writes the one identities/value-corrections file the pipeline reads (later round wins per name).

## Round 4: record check of every entry (2026-10-01)

The entry dossiers reach 115 entries. `record_check.py` gives the same material of EVERY entry to
Gemini (3.8 Flash, one call per entry: page scans at high resolution, the transcription the
extraction read, the reading corrections, every record of the graph with count range, locality,
georeference, record type, observers, own date): records that are right by index, for the others
the wrong fields, the right values and the words of the page that show it; missing records; entry
date, place and kind; the reading corrections that are not right. Answers per entry in
`<workdir>/record_check/answers/`, merged to `record_checks.csv` (the `graph_checks.csv` contract
plus `quote`, `quote_in_text`), `record_checks_missing.csv`, `record_checks_entries.csv`,
`transcript_checks_gemini.csv`. Resumable (LLM cache `data/cache/record_check_v1`, `--budget`).

On the 115 entries both checks saw, Gemini flags 129 records and the Claude agents 197; 87 are
flagged by both (67 % of Gemini's flags, 44 % of Claude's). Agreement by field: record type 24 of
25, georeference 32 of 38, locality 28 of 38, species 6 of 12, count 3 of 12. A single check is
therefore a pointer for the reviewer, not a correction. `record_check_combine.py` writes all
findings in the pipeline contracts (`observation_corrections_machine.csv`, rows added to
`value_corrections_machine.csv`) with `confidence`, `agreement`, `sources`; the pipeline applies a
row only when two checks propose the same value for the same field (`review.machine`,
`min_agreement`). `--trust FIELD[:MIN_CONFIDENCE[:quote]]` releases a whole class of Gemini
findings once a reviewer has checked a sample of it in the graph validation page.

Medium thinking finds more of what the agents flag (59 % instead of 44 %) but flags twice as many
records, agrees less often (49 %) and costs 4.5 times as much; the run used `low`.

## Running

```bash
W=<workdir>
python tools/validation_ui/machine_review/prepare_taxa.py payload.b64 --out $W --pages "<HistOrniGraph_output>" \
    --second-reading second_reading.json --third-reading third_reading.json
python tools/validation_ui/machine_review/prepare_persons.py payload.b64 <export>/review/person_link_review.csv --out $W
python tools/validation_ui/machine_review/prepare_places.py payload.b64 <export>/review/place_link_review.csv --out $W \
    --nominatim-cache "<linking_cache>/nominatim_cache.json"
python tools/validation_ui/machine_review/prepare_entries.py payload.b64 triples.pkl --out $W --pages "<HistOrniGraph_output>" --n 60
#   one subagent per batch / 3 sheets / 2 dossiers: "Read the instructions in $W/<check>/INSTRUCTIONS.md and process <n>"
python tools/validation_ui/machine_review/merge.py payload.b64 --work $W --out $W/machine_review \
    --second-reading second_reading.json --third-reading third_reading.json --person-matches person_matches.json
python tools/validation_ui/build_payload.py … --machine-review $W/machine_review/machine_review.json \
    --machine-readings $W/machine_review/readings_machine.json --out payload.b64
```

Each `INSTRUCTIONS.md` is written by the prepare script with absolute paths;
the agents read it, read their batch (and sheet image), and write one JSON
answer file. `merge.py` reports missing or unparseable answer files so single
batches can be re-run.
