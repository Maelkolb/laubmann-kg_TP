# Full re-extraction with Gemini (ontology 0.6.0, patched corpus)

Runbook for one unattended run of the whole pipeline — extraction → value
corrections → coverage/QA → linking → entity resolution → EUNIS → RDF/JSON-LD
+ SHACL → Darwin Core Archive — on the patched corpus (9,857 entries). Written
for a Claude Code session that orchestrates the run; every step is a shell
command. Prompt `observation_extraction` v3 is new, so every entry is a live
Gemini call (~9,900 calls; the old LLM caches do not apply).

## 1. Repository and environment

```bash
git clone https://github.com/desyLoyz/laubmann-kg.git && cd laubmann-kg   # or: git pull --ff-only
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,llm]"
echo "GOOGLE_API_KEY=<key>" > .env          # read by the CLI; .env is gitignored
.venv/bin/python -m pytest -q               # must be green before a long run
```

## 2. Inputs (Drive `HistOrniGraph_output/`, e.g. via `rclone copy gdrive:HistOrniGraph_output/<dir> <dest>`)

| what | Drive | local |
|---|---|---|
| patched corpus (preferred: ready to use) | `corpus_2026-09-30_patched/` | `data/corpus_patched/` |
| linking caches (GBIF, Wikidata, Nominatim, GeoNames, EUNIS LLM) | `linking_cache/` | `data/cache/linking/` |

Check the corpus: `data/corpus_patched/boundaries_summary.json` says
`"output_entries": 9857, "lost_entries": 0`; `multimodal_regions.jsonl` has
1,674 lines (1,626 with an `entry_uid`).

If the patched corpus is not on Drive, rebuild it (deterministic, seconds) from
`corpus_2026-07-21_dedup/` → `data/corpus_dedup/`, `corpus_2026-07-21/entries.csv`
→ `data/corpus_2026-07-21/entries.csv` and the multimodal catalogue v2
(`multimodal_v2_images.jsonl`, `text_inserts_v2.jsonl`, Drive
`multimodal_catalogue_v2_2026-08-18/`):

```bash
.venv/bin/python HistOrniGraph_addons/dedup/apply_entry_boundaries.py --corpus-dir data/corpus_dedup \
    --boundaries data/corpus_patches/entry_boundaries.csv --mask data/corpus_patches/masked_regions.csv \
    --out-dir data/corpus_patched
.venv/bin/python HistOrniGraph_addons/build_multimodal_regions.py --corpus-dir data/corpus_patched \
    --catalogue-dir <multimodal_catalogue_v2_2026-08-18> --reading-order data/corpus_dedup/multimodal_clean.md \
    --insert-decisions data/corpus_patches/text_insert_decisions.csv \
    --duplicates data/corpus_patches/multimodal_duplicates.csv \
    --catalogue-entries data/corpus_2026-07-21/entries.csv \
    --out data/corpus_patched/multimodal_regions.jsonl
```

## 3. Run config

Do not edit `configs/full_llm.yaml` in place; write a local copy that points
the LLM cache somewhere persistent (an interrupted run resumes from it), the
two LLM caches of the linking stage at their copies from Drive (folk-name
proposer `llm/`, EUNIS classifier `llm_habitats/`; the config's defaults are
other folders, and every miss is a new Gemini call) and the review output into
the export folder — the default `data/review` holds the tracked decision files
that `reviewed_csv` reads.

```bash
TAG=2026-10-01                                  # one tag per run
OUT=data/exports/kg_exports_$TAG
.venv/bin/python - <<EOF
import yaml
c = yaml.safe_load(open("configs/full_llm.yaml"))
c["extraction"]["cache_dir"] = "data/cache/llm_v3"
c["linking"]["taxa"]["llm"]["cache_dir"] = "data/cache/linking/llm"
c["linking"]["habitats"]["llm"]["cache_dir"] = "data/cache/linking/llm_habitats"
c["linking"]["review_dir"] = "$OUT/review"
c["resolution"]["review_dir"] = "$OUT/review"
yaml.safe_dump(c, open("configs/local_full.yaml", "w"), sort_keys=False, allow_unicode=True)
EOF
```

## 4. Smoke test, then the full run

```bash
# the 16 entries of the A/B test (reports, digests, split days, register cut, travel)
.venv/bin/python - <<'EOF'
import yaml
c = yaml.safe_load(open("configs/local_full.yaml"))
c["sample"] = {"volume": None, "entry_ids": ["L01-e0196", "L02-e0113", "L06-e0020", "L01-e0140", "L01-e0140a",
    "L01-e0140b", "L05-e0216", "L14-e0035", "L14-e0035a", "L07-e0008", "L07-e0008a", "L04-e0057",
    "L25-e0072", "L25-e0072a", "L17-e0242", "L17-e0242a"]}
yaml.safe_dump(c, open("configs/local_smoke.yaml", "w"), sort_keys=False, allow_unicode=True)
EOF
.venv/bin/laubmann-kg export-all --config configs/local_smoke.yaml --input-dir data/corpus_patched \
    --output-dir data/exports/smoke_$TAG
# expect: 16 entries, 0 failed, SHACL 0 violations, DwC-A valid; L25-e0072a and L17-e0242a
# are correspondence with third-party records by E. Riggel / Adolf Müller

nohup .venv/bin/laubmann-kg export-all --config configs/local_full.yaml --input-dir data/corpus_patched \
    --output-dir $OUT > $OUT.log 2>&1 &
```

Extraction runs at `concurrency: 8` (lower to 4 on HTTP 429); expect a few
hours for ~9,900 calls, then linking (mostly cached), resolution, EUNIS
classification and SHACL (15–30 min on the full graph). Re-running the same
command after an interruption continues from the caches.

## 5. Checks

- log: `pipeline: <n> entries (<k> empty, 0 failed)`; any `failed` entry is
  retried by simply re-running (truncated or failed answers are never cached)
- `SHACL … 0 Violation(s)`; warnings are mostly entries without records
- DwC-A summary `'valid': True, 'problems': []`
- `$OUT/rdf/laubmann_sample.ttl`: no `owl:sameAs`, no `lkg:Vocalisation`, about
  1,625 `lkg:MultimodalRegion`
- `$OUT/review/`: qa_flags.csv and the link/merge review CSVs for adjudication

Afterwards copy `$OUT` and `data/cache/llm_v3/` to Drive (`kg_exports_<tag>/`,
`llm_cache_v3/`) and load the Turtle into Fuseki. The cache is what makes the
run reproducible: Gemini does not answer identically twice, but every later
`export-all` with the same prompt replays these answers. Once the region crops are hosted, set `multimodal.image_base_url` and
re-run `export-all` — the Gemini answers come from the cache, only the graph
and the archive are rewritten.
