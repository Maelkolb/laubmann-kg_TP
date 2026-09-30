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
| **extraction** (`prepare_entries.py`) | stratified sample of entries | scan pages, transcription, every record the graph holds for the entry | per observation `ok`/`wrong` (fields + correction)/`spurious`, missing records, entry date/place/kind, misread words |

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
