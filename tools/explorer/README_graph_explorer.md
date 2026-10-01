# Graph explorer (ontology 0.7.0)

`build_graph_explorer.py` turns an **exported graph** (the published Turtle) into one self-contained HTML page for browsing the Laubmann knowledge graph entry by entry. It reads the file itself, not the pipeline's in-memory result, so everything the page shows is really in the published graph. Every triple of the file is embedded, and node IRIs are kept and can be copied.

```bash
.venv/Scripts/python.exe tools/explorer/build_graph_explorer.py \
    data/exports/kg_exports_2026-10-01/rdf/laubmann_sample.ttl  out/graph_explorer.html
# options
#   --scans drive            (default) Drive thumbnails by file id, local JPEG as fallback
#   --scans local:<dir>      <dir>/<page id>.jpg relative to the HTML file first, Drive as fallback
#   --local-scans <dir>      fallback dir in drive mode (default: relative path to data/pages_jpg)
#   --drive-map <json>       page id → Drive file id (default configs/drive_scan_files.json)
#   --ontology-dir <dir>     labels + controlled vocabularies (default ontologies/)
```

Requirements: `rdflib` only. The page needs no network, except for scans and OpenStreetMap tiles. Leaflet is inlined from `tools/validation_ui/`. It runs in current Chrome, Edge, Firefox and Safari 16.4+ (it uses `DecompressionStream`).

Files: `build_graph_explorer.py` (builder) · `graph_explorer_template.html` · `graph_explorer.css` · `graph_explorer.js` (app).

| Export | Triples | Build | HTML | Load in browser |
|---|---|---|---|---|
| smoke_2026-10-01 | 10,657 | 0.2 s | 0.4 MB | 0.2 s |
| kg_exports_2026-10-01 (full) | 1,986,310 | 36 s | 14.0 MB | ≈0.7 s, views < 0.1 s |

## What it shows

- **Entry** (`#/e/<entry id>`), the core view:
  - **Left:** the volume's entry list, with a ☰ toggle and ← / → for the previous or next entry.
  - **Middle:** the entry's subgraph, laid out in columns: archive (volume → pages → source/multimodal regions) · entry · records (weather, travel event → legs, observations labelled *taxon · count*) · taxa · places, persons and habitat concepts · authority records.
    - Authority links are drawn by grade: GBIF, EUNIS, GeoNames, Wikidata and GND, with `skos:exactMatch` solid, `closeMatch` dashed and `broadMatch` dotted. There is no `owl:sameAs` in 0.7.0; if it ever appears, it is drawn like exactMatch.
    - Edges carry the ontology's `rdfs:label` (DE/EN). Mention roles (`mentionsCompanion`, `mentionsSource` …) replace the generic `mentionsPerson`.
    - Layers can be toggled: records, taxa, places, persons, habitats, archive, authorities and provenance (run → agent/prompt).
    - Above 30 observations, records are grouped by taxon order. You can also group by family, place, observer or record type, or not at all. Click a group to expand it.
    - Hovering a node highlights its edges. Clicking a node shows all its triples, and double-clicking opens the node view.
  - **Panel tabs:**
    - *Text*: `dwc:fieldNotes` with each observation's `verbatimNotes` marked and clickable, the verbatim date and place, the transcript-check `skos:note`, weather, travel legs, mentioned persons with their roles, and multimodal regions with visible text.
    - *Records*: one sortable row per observation, with taxon, count/min/max/qualifier, sex/stage, behaviour, call, evidence, breeding, record type, place (own locality marked), recordedBy, eventDate and verbatim notes.
    - *Scans*: the entry's pages, including continuation pages reached via its regions.
    - *Node*: all outgoing triples and a summary of the incoming ones. Controlled values show the vocabulary label and the raw notation. External IRIs link out.
- **Node view** (`#/n/<compact IRI>`) for any taxon, place, person, habitat, authority record, page and so on:
  - its triples and a neighbourhood diagram;
  - a Leaflet map: the place itself with its uncertainty radius, or the places of a taxon's or person's observations;
  - per-year and per-month charts;
  - a paginated usage table of every incoming triple (observations and entries), sortable by date and filterable by predicate.
- **Classes** (`#/c/<kind>`): every node of a class with its use count.
- **Overview:**
  - counts per class and predicate;
  - entries per volume and per year (years before 1900 are listed rather than plotted);
  - top taxa, places, persons and habitats;
  - a map of all georeferenced places.

  Everything in it is clickable.
- **Search** (`/`): dates (`1942-04-01`, `1.4.1942`, `4.1942`), places, volumes, ids, taxa (vernacular or scientific), persons, authority ids, and a full-text search of the entry texts.
- **DE / EN toggle:** German is the default. Class and property labels come from the ontology, controlled values from `controlled_vocabularies.ttl`. Standard dwc/dcterms/skos/prov terms carry labels written in the builder (`EXTERNAL_LABELS`).

## Data packing

The builder parses the file into node, predicate and literal tables (with datatype and language) plus the triples sorted by subject as CSR arrays (`sOff`, `tP`, `tO`). It then gzips them and embeds the result as base64. The browser decodes the data once and builds the incoming index, the node kinds (from `rdf:type`, plus `skos:inScheme` for habitat vs authority concepts) and the entry index. Each entry's subgraph is built on demand from the triples.

## Known limitations

- Scans come from Drive thumbnails. They load only for Google accounts that can see HistOrniGraph_output; otherwise the page falls back to the local JPEGs, which exist only on this machine. Multimodal crops appear only once the graph carries `schema:image`.
- Map tiles need network access.
- Source regions have no coordinates in the graph, so the scan cannot highlight a region.
- The layout is column-based and deterministic, not force-directed. Very large entries (up to 396 observations) stay grouped until expanded; expanded, they are tall and you pan through them with scroll, drag or Ctrl+wheel.
- Only one graph file is read. To compare runs, keep using `tools/Laubmann-KG_Explorer.html`.
