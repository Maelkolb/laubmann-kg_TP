# Validation, linking and merging: the "Abgleich" approach

This note explains how extracted entities (taxa, persons, places, habitats) are
reviewed, linked to authority files and merged, and why the approach changed in
September 2026. The reviewer-facing tool is `tools/validation_ui/` (German UI,
built from one export); the decision files it writes are read by the pipeline
(section `review` in `configs/full_llm.yaml`).

## 1. What was wrong with pairwise merge review

The first validation UI (2026-09-24) asked reviewers to judge pairs
"variant → canonical" (`*_merges.csv`) and, separately, the authority links
(`*_link_review.csv`). A student assistant worked through part of it and
recorded the problems (`Downloads/HistOrniGraph Validierung_Anmerkungen`):

* **The pair is the wrong unit.** For taxa the "merge" is only a consequence of
  the linking: two names become one node when they were linked to the same
  GBIF key. The question a reviewer can actually answer is *which species does
  this name denote*, not *are these two strings the same*. "Trink → Buchfink"
  cannot be answered with yes/no: "Trink" is a misreading, some occurrences may
  be Buchfink, others something else (the scan shows *Triel*).
* **Most errors sit in single mentions, not in names.** "Kameradeneingänge" is
  a misread *Hausrotschwänzchen*, "5 Eis- Gimpel" is *Stare, Gimpel*, one
  "Tirol" is the region and another a misread *Pirol*. A name-level decision
  cannot express that; the old UI had no way to reassign one mention, split one
  into two species, or move a word from the species to the places.
* **Candidates were mostly noise where no authority backed them.** Places
  (1,051 candidates) and habitats (292) were proposed by string similarity
  ≥ 0.9, which pairs different places (Hagenau/Hagnau, Neufinsing/Neufinning).
* **Evidence was incomplete.** Contexts came from a text search (so "Tirol" as
  a region showed up as evidence for the bird), the scan button opened only the
  first page of an entry (30 % of entries run over a page break), and 2,949 of
  6,750 pages had no scan link at all.
* **No priority.** 12,000+ rows, with the risky cases (rare, unattested names)
  mixed among thousands of trivially correct ones.

## 2. The model: entity, name form, mention

| level | taxa | persons | places | habitats |
|---|---|---|---|---|
| **entity** (one graph node) | GBIF taxon (accepted key) | person (Wikidata/GND or local) | place (GeoNames/Wikidata/coordinates or local) | habitat concept (EUNIS class) |
| **name form** (as written) | *Dompfaff*, *Hausrotschwänzchen* | *W. Wüst*, *Dr. Wüst* | *Mainiger See* | *Schilfgürtel* |
| **mention** | one observation | one person mention/observer | one entry place/locality/leg | one observation's habitat |

The reviewer decides **which entity a name form denotes**; all forms with the
same entity are one node. Merging is therefore never judged as a pair. Single
mentions can be decided differently from their form, and misread text is
corrected where it happened (the transcription), not in its consequences.

The UI (version 3, "Laubmann-Abgleich") shows **one entity at a time**: its
authority record on top, below it every name form the diary uses for it, and
under each name its mentions with the line cut from the scan; the page itself
stays open on the right. The same four actions apply on all three levels:
✓ *stimmt*, ↪ *anders* (another entity; for taxa any GBIF taxon, plus
"nicht bestimmbar"; for persons/places "eigene"), ✗ *kein(e) …* (no
taxon/person/place at all, with a reason), ? *unsicher*; ✎ corrects the
reading of a mention's entry. Confirming the entity also confirms its safe
names (attested names, pure spelling variants), so a reviewer only decides the
doubtful ones; relinking a species (↪ on the entity) carries all its
undecided names along. A name whose mentions are decided one by one counts as
decided. An entity is done when the entity and all its names are decided; the
next open entity follows automatically.

**Model second reading.** For doubtful species mentions (class C, rare L/B
names) the line image was sent to Gemini (`tools/validation_ui/second_reading.py`):
what is written there, and which bird is it? The answer appears next to the
mention and is accepted with one key (it sets the reading correction and the
species). On a pilot it found real misreadings (*Lärmkönig* → Zaunkönig,
*Rothalswürger* → Rotkopfwürger, *Flusspieper* → Flußuferläufer), but it can
also be confidently wrong (*Kameradeneingänge* read as "Karmingimpel" at 98 %,
the scan shows *Hausrotschwänzchen*), so it is a suggestion for the reviewer,
never applied automatically.

## 3. Evidence and priority

Each taxon name form gets an evidence class from authority data:

* **A – attested**: the form is a German name of the linked taxon in GBIF or
  Wikidata (historical names included: *Dompfaff*, *Schwarzdrossel*,
  *Weidenlaubvogel*); **B – variant**: spelling or compound variant of such a
  name (*Lachmöve*, *Hausamsel*); **C – unattested**; **L – not linked**.

On the 40 pair decisions the assistant had made, the classes separate well:
A 5 yes / 1 no (the "no" was a correct name with one misread mention), B 9 yes /
1 no (a policy question), C 7 yes / 12 no / 5 unsure. On the 2026-08-19 export:

| class | forms | observations |
|---|---|---|
| A attested | 735 | 70,261 (94 %) |
| B variant | 198 | 740 |
| C unattested | 728 (553 single mentions) | 1,868 |
| L not linked | 591 | 1,715 |

So the review targets ~1,500 forms (C, L, B) with ~4,300 observations,
ordered by frequency, instead of 12,000 mixed rows. The accuracy of the
remaining 94 % is measured, not reviewed exhaustively: the UI draws a
stratified random sample of 403 taxon mentions (task *Stichprobe*) and reports
the share correctly identified with a 95 % Wilson interval (for the paper's
"taxon-linking accuracy"). Persons, places and habitats have analogous classes
(variant merged by a rule, linked, unlinked, to review).

Every mention is shown with a **line image** cut from the scan (page region
box from the PAGE-XML, line index from the transcription; 95.6 % of taxon
mentions are located) and the entry text around it; the scan viewer pages
through all pages the entry spans and its neighbours.

## 3a. The four tasks of the UI (v4, 2026-09-29)

The review unit is the **entity** (one authority record) with its written
names and passages; decisions are still stored on the written name and the
passage, so they survive a re-extraction with the final ontology. The page
has one tab per task, each with a stable list (no automatic advancing unless
switched on) and fixed-width counters:

| task | items | decision |
|---|---|---|
| **Prüfen** | entities that already carry an authority record | is the record right (`Y`/`A`/`N`/`U`); below it every written name with a checkbox – unticking asks where the name belongs instead |
| **Verknüpfen** | entities without a record | GBIF/Wikidata/GND/OSM/GeoNames/EUNIS search, map click, or "ist dasselbe wie …" an existing entity (all names move there) |
| **Namen** | entities with unsafe names or likely missing ones | tick incoming candidates (`merge_candidates.py`: same German name, compound stem, surname + initials, containment, edit ratio; candidates ruled out by authority records – attested names of another linked species, persons with another Wikidata item, places > 25 km apart – are not offered), search any name of the graph, confirm the group |
| **Lesefehler** | mentions where the model readings disagree with the transcription | transcription right (`Y`), accept a model reading (`1`/`2`: word + species), type the word (`E`), other species (`A`), not a bird (`N`) |

**Model readings.** Gemini 3.5 Flash read the line image of every doubtful
species mention (2,587); the 1,176 mentions where it disagrees with the
transcription were read again from contact sheets by Claude Opus 5.5
subagents (`third_reading_sheets.py`, `model_answers_merge.py`). The page shows
both readings with an agreement badge; the reviewer decides at the image, and
nothing is applied automatically. In the pilots the second model caught
readings both the transcription and Gemini had wrong (*Trauerseeschwalbe*,
*Seeregenpfeifer*, *Rothalsgans*) and marked misaligned or illegible crops.
For persons, Opus subagents matched the 313 persons with Wikidata candidates
and ≥ 2 mentions against the candidates enriched with dates, GND and
occupation (`person_batches.py`): a conservative decision (candidate / none /
unclear) with a reason, shown above the candidates; 312 answers, most of them
"none" for the short forms.

## 4. Decision files and how the pipeline uses them

The UI exports a ZIP whose `review/` files go to `data/review/`:

| file | level | read by |
|---|---|---|
| `identities.csv` | name form (`same`/`own`/`none`/`mentions`/`unsure`) and entity link (`link`/`nolink`) | `review/identities.py`: linking (taxa, persons, places, habitats) and resolution (persons, places, habitats) |
| `value_corrections.csv` | one mention (`replace`/`drop`, `occurrence`) | `normalization/corrections.py`, right after extraction |
| `text_corrections.csv` | the transcription of one entry | `review/readings.py`, **before** extraction |
| `evaluation_taxa.csv` | random sample judgements | evaluation only |
| `qa_flags.csv` | QA flag judgements | not read yet |

Order in `run_pipeline`: readings → extraction (corrected entries miss the LLM
cache and are read again, so species, counts, places and dates follow from the
corrected text) → mention corrections → name-level removals (`none`) →
coverage/QA → linking (reviewed identities first, then the rules) →
resolution (rule merges, then reviewed `same`/`own` override them; a reviewed
link on any name of a person cluster beats links inherited from variants) →
habitat linking. Reviewed rows are keyed by the written form, so they survive
re-extraction; rule-based merges still handle every form nobody reviewed. The
machine-adjudicated `*_merges.csv` baselines of 2026-08-19 stay the prior for
unreviewed forms.

## 5. Guidelines (also in the UI help)

* Merge = same biological species, not same word. Historical and regional
  names (*Dompfaff* = Gimpel, *Schwarzdrossel* = Amsel, *Hausamsel*) are the
  species; the written name stays in `dwc:verbatimIdentification`.
* Qualifiers: a plumage word (*Schwarzamsel*) keeps the species; a word naming
  a subspecies or form (*Trauerbachstelze*) is linked to that taxon. Frequency
  does not decide identity, only review priority.
* Misreadings are never synonyms: correct the reading (✎) or mark the form as
  *kein Vogel – Lesefehler*; if its mentions differ, decide them one by one.
* Nest, egg, feather of a species count as evidence of that species.
* Genus/family names (*Möwe*, *Ente*) are linked to the genus/family, not to a
  species.
* Persons: initials and surnames only with unambiguous context; gendered forms
  (*Frau/Frl. X*) are different persons. Places: similar spelling is not the
  same place; micro-toponyms get an approximate point with a stated uncertainty.

## 6. Findings in the 2026-08-19 export (fixed in the pipeline)

* **3,075 observations pointed to a linked taxon without `dwc:scientificName`**
  (45 taxa, e.g. Rohrweihe, Baumfalke, Steinkauz; 2,629 DwC-A occurrences with
  `taxonID` but no `scientificName`). Cause: `link_taxa` matched one scientific
  name per vernacular but copied only the GBIF key to all its observations;
  where the model had left the name empty, the node could be emitted without
  it. Fixed: every observation of a linked name gets the matched name.
* **Walter Wüst was linked to the wrong person**: `owl:sameAs wd:Q71631`
  (Walther Wüst, Indo-Europeanist) instead of Q2546836 (the ornithologist);
  *Frl. W. Wüst* carried the same link. Cause: "W. Wüst" matched an alias of
  Q71631 exactly once and was auto-linked, and the cluster inherited the link
  from the variant. Fixed: abbreviated given names never auto-link (like bare
  surnames), and reviewed links take precedence over inherited ones.
* **Frequent places without coordinates**: *Englischer Garten* (446 mentions),
  *Botanischer Garten*, *Karolingerstraße*, *Süddamm*, *Harlachinger Berg*,
  *Ismaninger Teichgebiet* … — the top 100 unlinked place names carry 3,509
  mentions. Generic words (*Forst*, *See*, *Park*, *Damm*) are extracted as
  places. The place queue shows them first.
* Frequent unlinked species: *Weidenmeise* (324), *Berglaubsänger* (140),
  *Wiesenweihe* (65), *Lachseeschwalbe* (30).

## 7. Open points

* A full re-export needs a live re-extraction: the extraction prompt changed
  with ontology 0.5.0 (2026-09-15), so the 08-19 LLM cache no longer matches.
* Contextual geocoding (query micro-toponyms with the entry's settlement:
  "Süddamm, Ismaning") and a parent-place relation for localities would link
  most of the frequent unlinked places automatically.
* Line boxes come from the region box divided by the line count, which goes
  wrong on two-column species lists: the model readings then describe another
  line. The UI flags those ("Zeilenbild verrutscht?", the word the model read
  stands elsewhere in the entry); PAGE-XML line coordinates would fix it.
* The register volume (Vol. 35) could serve as Laubmann's own nomenclature, but
  its transcription is too garbled for that today (headwords like
  "Reichsrückungsrecht").
* The graph links an entry only to its first page (`dcterms:isPartOf`); the
  page span computed for the UI (corpus stream offsets) could be emitted as
  well.
