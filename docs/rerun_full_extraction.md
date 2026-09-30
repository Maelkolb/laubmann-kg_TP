# Full re-extraction with Gemini (ontology 0.7.0, prompt v4, patched corpus)

Runbook for one unattended run of the whole pipeline — extraction → value
corrections → coverage/QA → harmonisation → linking → entity resolution →
EUNIS → RDF/JSON-LD + SHACL → Darwin Core Archive — on the patched corpus
(9,857 entries). Written for a Claude Code session on Windows that orchestrates
the run (every step is one PowerShell command with literal paths; shell
variables do not survive between tool calls). Prompt `observation_extraction`
v4 is new: every entry is a live Gemini call, except the 76 entries of the
2026-09-30 A/B sample already in the cache.

Model and cost (A/B test 2026-09-30, 68 entries, blind-judged): `gemini-3.8-flash`
(fewer errors than 3.5 Flash, no runaway generations, ~5x cheaper per call) with
explicit context caching of the prompt's instructions. Expected: ~$40 for the
extraction (~9.4M output tokens at $3.75/M, prompt tokens ~95 % cached), a
few dollars for the linking LLMs (3.5 Flash, mostly cached), 1–1.5 h extraction
at concurrency 16, then linking, SHACL (15–30 min) and the archive.

## 1. Repository and environment

```powershell
# the final branch (worktree of the laubmann-kg clone); after the merge: upstream main
cd C:\Users\totom\Projects\laubmann-kg_final
git log --oneline -3                                   # final-0.6: ontology 0.7.0 / prompt v4
.venv\Scripts\python.exe -m pytest -q                  # must be green (293 tests)
```

`.env` holds `GOOGLE_API_KEY=…` (git-ignored). Write it from Bash
(`printf 'GOOGLE_API_KEY=%s\n' KEY > .env`); PowerShell's `>` writes a BOM that
the loader does not read.

## 2. Inputs (Drive `HistOrniGraph_output/`)

| what | Drive | local |
|---|---|---|
| patched corpus | `corpus_2026-09-30_patched/` | `data\corpus_patched\` |
| linking caches (GBIF, Wikidata, Nominatim, GeoNames, taxon + EUNIS LLM) | `linking_cache/` | `data\cache\linking\` |

```powershell
robocopy "G:\My Drive\HistOrniGraph_output\corpus_2026-09-30_patched" data\corpus_patched /E /XF desktop.ini
robocopy "G:\My Drive\HistOrniGraph_output\linking_cache" data\cache\linking /E /XF desktop.ini
```

Check: `data\corpus_patched\boundaries_summary.json` says `"output_entries": 9857,
"lost_entries": 0`; `multimodal_regions.jsonl` has 1,674 lines.

## 3. Config

`configs/full_llm.yaml` is used as is: extraction cache `data/cache/llm_v4`,
linking LLM caches `data/cache/linking/llm` and `…/llm_habitats` (these stay on
3.5 Flash so the Drive answers apply), review CSVs of the run in
`<output-dir>/review` (never `data/review`, which holds the decisions the run
reads). The machine review (`review.machine`, 2026-09-30) fills name forms and
links nobody reviewed by hand (confidence ≥ 0.9, two agreeing sources; graded
`closeMatch`); human decisions exported from the review page go to
`data/review/identities.csv` and always win.

## 4. Smoke test, then the full run

```powershell
# 16 entries (reports, digests, split days, register cut, travel); cache hits, ~1 min
.venv\Scripts\laubmann-kg.exe export-all --config configs/local_smoke.yaml --input-dir data/corpus_patched --output-dir data/exports/smoke_2026-10-01
# expect: 16 entries, 0 failed, "SUMMARY: 0 Violation(s)", DwC-A written;
# L25-e0072a / L17-e0242a are reports by E. Riggel / A. Müller (third-party-report)
```

Start the full run as its own process (a Bash/PowerShell tool call is stopped
after 2 h; this one survives the session). Logging goes to stderr, the SHACL
report to stdout:

```powershell
New-Item -ItemType Directory -Force data\exports | Out-Null
Start-Process -FilePath .venv\Scripts\laubmann-kg.exe -WorkingDirectory C:\Users\totom\Projects\laubmann-kg_final -WindowStyle Hidden `
  -ArgumentList 'export-all','--config','configs/full_llm.yaml','--input-dir','data/corpus_patched','--output-dir','data/exports/kg_exports_2026-10-01' `
  -RedirectStandardError data\exports\kg_exports_2026-10-01.log -RedirectStandardOutput data\exports\kg_exports_2026-10-01.out
```

Watch it:

```powershell
Get-Content data\exports\kg_exports_2026-10-01.log -Tail 5            # "[i/9857] L..-e.... -> n observations"
.venv\Scripts\python.exe tools\llm_cost.py data\cache\llm_v4            # calls, tokens, USD so far
Get-Process laubmann-kg -ErrorAction SilentlyContinue                    # still running?
```

Re-running the same command after an interruption continues from the caches
(answers truncated at the token cap or failed are never cached and are retried).
On HTTP 429 lower `extraction.concurrency`.

Cheaper alternative (half price, asynchronous, turnaround typically minutes to
a few hours): fill the cache through the Gemini Batch API, then run the same
`export-all` (pure cache replay):

```powershell
.venv\Scripts\python.exe tools\batch_extract.py prepare --config configs/full_llm.yaml --input-dir data/corpus_patched --work data\batch\2026-10-01
.venv\Scripts\python.exe tools\batch_extract.py submit  --work data\batch\2026-10-01
.venv\Scripts\python.exe tools\batch_extract.py status  --work data\batch\2026-10-01   # until JOB_STATE_SUCCEEDED
.venv\Scripts\python.exe tools\batch_extract.py collect --config configs/full_llm.yaml --work data\batch\2026-10-01
```

## 5. Checks

- log: `pipeline: 9857 entries (<k> empty, 0 failed)`; `harmonize:` and
  `linking:` summaries; QA flags in `review/qa_flags.csv` (watch
  `truncated_output`, `literature_without_citation`, `absent_with_count`)
- stdout: `SUMMARY: 0 Violation(s)`; warnings are mostly entries without records
- DwC-A: `dwca/` with event, occurrence, measurementorfact (multimedia only once
  the crops are hosted), validator without problems
- `rdf/laubmann_sample.ttl`: no `owl:sameAs`, no `lkg:Vocalisation`, no
  `lkg:observationRadiusMeters`, about 1,625 `lkg:MultimodalRegion`
- cost: `tools\llm_cost.py data\cache\llm_v4` (and `data\cache\linking\llm*`)

## 6. Afterwards

```powershell
robocopy data\exports\kg_exports_2026-10-01 "G:\My Drive\HistOrniGraph_output\kg_exports_2026-10-01" /E
robocopy data\cache\llm_v4 "G:\My Drive\HistOrniGraph_output\llm_cache_v4" /E
robocopy data\cache\linking "G:\My Drive\HistOrniGraph_output\linking_cache" /E /XO
```

Place labels that are new in this run are georeferenced from GeoNames only
(the pipeline never calls Nominatim live). To add OpenStreetMap points, pre-warm
the Nominatim cache for them (`tools/prewarm_nominatim.py`, 1 request/1.1 s)
and re-run `export-all` — a cache replay, no Gemini cost.

The cache makes the run reproducible: Gemini does not answer identically twice,
but every later `export-all` with the same prompt replays these answers. Once the
region crops are hosted, set `multimodal.image_base_url` and re-run `export-all`
— only the graph and the archive are rewritten. Validation (the review page) is
then rebuilt on this export (tools/validation_ui, REBUILD.md on Drive).
