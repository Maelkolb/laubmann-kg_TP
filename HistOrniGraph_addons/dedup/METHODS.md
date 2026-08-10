# Duplicate-page detection — methods & validation

Scope: a layered detector for the HistOrniGraph Laubmann corpus that finds
pages appearing more than once (the same physical journal page captured or
processed repeatedly), plus a quality screen for degenerate transcriptions.
Everything below is measured on a real six-volume sample drawn from the Drive
corpus (vols 01, 06, 15, 22, 29, 34; **1,466 pages, 3,344 regions**),
reconstructed losslessly from `corpus/by_volume/Laubmann_NN.md` via
`md_to_corpus.py`.

## Root cause — why pages duplicate

Four distinct mechanisms, not one. The sample shows all four, and they need
different signals:

**A. Double capture (same run).** A spread is photographed/processed twice, so
it lands under two consecutive `scan` numbers with the *same* detected page
number and near-identical text. Dominant mode in vols 06, 22, 29, 34.
Example: `V34 s41_R` and `V34 s42_R`, both page 49, text similarity 1.00
(only difference: `dezember`/`december` OCR drift).

**B. Cross-run contamination.** The same page images are processed by a second
pipeline run whose region JSONs land in a *different* volume directory. The
`page_id` (batch-UUID + scan + side) is byte-identical across the two volumes,
but the two OCR passes disagree. In the sample, **122 of Vol 15's pages carry
Vol 01's batch UUID** (`900847d2-…`), scans 3–89 — i.e. Vol 01 was
re-processed into the Vol 15 output tree. This alone inflates Vol 15 by ~38%.
This is the mode that most corrupts index↔corpus linking, because the
duplicate is not adjacent — it is in another volume.

**C. Split / unsplit artifact.** A scan is present both as `_L`/`_R` half-pages
*and* as an unsplit whole-scan page (page-id suffix absent, side `""`). The
whole-scan text *contains* the concatenation of the two halves rather than
equalling either. Vol 29 is full of these `_u` (unsplit) captures interleaved
with split pages under the same page number. This is a **containment**
relation, asymmetric — flagging it with a symmetric similarity threshold
alone would miss it.

**D. `_full` insert re-captures.** A handful of pages carry a `_NNNN_full`
suffix — secondary "full view" photographs of insert/slip pages. Low volume
(2–4 per volume) but they duplicate real content.

Page-number OCR drift compounds all of these: the same physical page number is
read as `20.`/`20`, `p 5/58.`/`58`, `3 32.`/`32`, `XXIX`/`XXXIV`. The detector
therefore normalizes the page-number token (last integer run) rather than
trusting the raw string, and never relies on the page number alone.

## The layers

Keying: each region is identified by `page_uid = L{vol:02d}:{page_id}` (the
`page_uid`/`region_uid` scheme; falls back to `page_id` when a UID field is
absent, which is the current corpus state).

1. **Normalization.** Strip `<u>`/markup, de-hyphenate line breaks, collapse
   whitespace, NFC + casefold, map umlauts (`ä→ae`, `ß→ss`). Page text = its
   regions joined in reading order.

2. **Fingerprints.** 5-char shingles → CRC64 set (Jaccard + containment) and a
   128-perm MinHash (`datasketch`) for the global LSH pass.

3. **Candidate generation** (cheap, before any O(n²) comparison):
   - *scan window* ±3 within a volume, including the L/R split of a scan;
   - *page-number collision* within a volume (normalized token);
   - *page-id collision* across volumes (catches mode B directly);
   - *global MinHash-LSH* at Jaccard ≥ 0.45 (catches stragglers, e.g. drifted
     re-scans several scans apart, and cross-volume pairs the id-collision pass
     misses because OCR renamed nothing).

4. **Pair scoring.** `confidence = 0.72·text + 0.28·structural`, where
   `text = 0.5·Levenshtein + 0.2·token_set + 0.3·Jaccard`
   (`rapidfuzz`), and structural adds for same page-number token, identical
   entry-date sequence, shared first/last 40 chars, adjacent scan, and
   cross-volume same-page-id. Containment is detected separately
   (containment ≥ 0.70, Jaccard < 0.60, length ratio < 0.65) and scored on the
   containment coefficient so mode C is not penalized for asymmetry. Pairs with
   a degenerate member have their text score capped (see below).

5. **Clustering.** Union-find over pairs ≥ `cluster_threshold`; each cluster
   gets a suggested keep (non-degenerate > dominant-batch-UUID > more entries >
   more regions > longer text > earlier scan) and the rest as suggested drops.

## Quality screen (the second error type)

Degenerate transcription — Gemini repetition loops and bleed-through gibberish
from folded ink-slip images — is detected per page from three cheap signals:
dominant-trigram fraction (repetition loop → ≈1.0), zlib compression ratio
(looped text compresses far below prose), and alphabetic-character ratio
(symbol-heavy bleed-through). A degenerate page is flagged in
`quality_report.csv` and its text similarity is capped at 0.45 so a repetition
loop cannot masquerade as a duplicate of another repetition loop.

In the sample: **120 pages flagged** (110 low-alpha, 15 repetition-loop, 11
suspicious-length; overlapping). **102 of the 120 are isolated** — bad OCR that
is *not* a duplicate, i.e. pages to send back for re-transcription, not to
merge. The other 18 are degenerate *and* duplicated (drop-safe once a clean
twin is confirmed).

## Thresholds & error trade-off

Confidence bands, measured on the 334 sample pairs the detector surfaces at
≥ 0.55, adjudicated with a structural proxy (POS = cross-run id match, or
Levenshtein ≥ 0.90, or same page-number + identical entry-date sequence, or
containment ≥ 0.85; the residual is genuinely ambiguous and needs a human):

| threshold | pairs flagged | proxy-precision |
|-----------|---------------|-----------------|
| ≥ 0.90    | 121           | 1.000           |
| ≥ 0.80    | 199           | 0.975           |
| ≥ 0.70    | 245           | 0.886           |
| ≥ 0.55    | 334           | 0.740           |

Recall on the 122 known cross-run positives (mode B, ground-truth by identical
cross-volume page-id): **100% reach the candidate stage; 100% ≥ 0.55, 91.8% ≥
0.80, 77.9% ≥ 0.90.** None are lost before scoring. On a broader
confidently-labelled positive set (186 pairs) recall is 100% ≥ 0.55 and 90.3%
≥ 0.80.

Chosen operating points:
- **`--high-threshold 0.80`** → `suggested_action = drop_duplicates`. At this
  cut precision is ~0.97 and the five near-misses are consecutive travel-diary
  pages sharing a page-number token and a boilerplate itinerary sentence
  ("gehe mit ihr über …hof – …hof") but describing *different* walks — the
  characteristic false positive. They still surface for review; they are not
  silently dropped.
- **`--cluster-threshold 0.55`** → review floor. The 0.55–0.80 band is where
  the two error types trade off: it holds the real containment/split cases and
  heavy-OCR-drift double-captures (recovered as true positives on inspection)
  together with the travel-page false positives. This is deliberately the
  human's band, not the machine's.

**How the two errors trade off.** Raising the drop threshold buys precision at
the cost of leaving more true duplicates in the review queue (more manual
work, no data loss). Lowering it drops more automatically but risks discarding
a distinct page — the worse error for a scholarly edition, since a dropped page
is invisible downstream. The tool is therefore biased toward *review over
deletion*: nothing is dropped without a confirmed decision, `apply_dedup.py`
writes a new corpus and never mutates the input, and every drop is recorded in
`dedup_manifest.{json,csv}` with the page kept in its place and why.

## Effect on corpus inflation (sample)

Applying only the ≥ 0.80 auto-drop suggestions removes **202 of 1,466 pages
(13.8%)**, heavily concentrated in the contaminated volumes:

| vol | pages | auto-drop @0.80 |
|-----|-------|-----------------|
| 01  | 172   | 2 (1.2%)        |
| 06  | 143   | 10 (7.0%)       |
| 15  | 388   | 149 (38.4%)     |
| 22  | 241   | 18 (7.5%)       |
| 29  | 370   | 6 (1.6%)        |
| 34  | 152   | 17 (11.2%)      |

Vol 29's low auto-drop rate is expected: its duplicates are mostly mode-C
containment and heavy-drift `_u` captures that correctly sit in the review
band rather than auto-dropping. After a full apply run, regenerated
`entries.jsonl` falls from 1,803 to 1,458 entries, removing the double-counting
that would otherwise corrupt entry↔index linking and the knowledge graph.

## Limitations

- Text-only by default. The optional `--image-root` perceptual-hash layer
  (`imagehash.phash`, Hamming ≤ 8 confirm / ≥ 24 veto) adjudicates the review
  band directly from the page images and is the recommended next step for the
  0.55–0.80 pairs; it was not exercised here because only the text artifacts
  were pulled from Drive.
- Proxy precision is a structural estimate, not human-adjudicated ground
  truth. The review GUI exists precisely to convert the ~68 ambiguous
  sample pairs into real labels; those labels should feed a threshold
  re-tune before a full 34-volume run.
- Entry-date signals depend on `build_corpus.find_entry_starts`; pages with no
  detected header (indices, plates, inserts) rely on text + page-number
  signals only.
