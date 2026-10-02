/* Laubmann-KG graph validation page ("Graph-Prüfung") — FORK of tools/explorer/graph_explorer.js (ontology 0.7.0).
   Everything the explorer does is kept (overview, node view, classes, search); the entry view is extended by the
   review modules gc_*.js, which follow this file in the SAME function scope (build_graph_check.py concatenates them;
   gc_boot.js closes the scope). Changes against the explorer are marked [GC].
   Original header: Laubmann-KG graph explorer — application script.
   The data is the exported graph itself, packed by tools/explorer/build_graph_explorer.py:
   node / predicate / literal tables plus the triples sorted by subject (CSR arrays).
   Everything shown here is read from those triples; nothing is precomputed by the pipeline. */
(function () {
'use strict';

// ------------------------------------------------------------------ utilities
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
// [GC] one app, two builds: the embedded meta says which. review = Graph-Prüfung (decide, export);
// explorer = Graph-Explorer: the same display, nothing that decides (EXPLORER is respected by every module)
const GC_META = (() => { try { return JSON.parse(document.getElementById('gc-meta').textContent) || {}; } catch (e) { return {}; } })();
const EXPLORER = GC_META.mode === 'explorer';
document.documentElement.dataset.mode = EXPLORER ? 'explorer' : 'review';
const LS_PREFIX = EXPLORER ? 'lkge.' : 'lkgc.';   // the two builds keep their view settings apart
function store(k, v) {
  try { if (v === undefined) return localStorage.getItem(LS_PREFIX + k); localStorage.setItem(LS_PREFIX + k, v); } catch (e) { /* storage unavailable */ }
  return null;
}
const debounce = (f, ms) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => f(...a), ms); }; };
function toast(msg, ms) { const el = $('#toast'); el.textContent = msg; el.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => { el.hidden = true; }, ms || 1800); }
function copyText(s) {
  const fallback = () => { const ta = document.createElement('textarea'); ta.value = s; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { /* ignore */ } ta.remove(); toast(t('copied')); };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(s).then(() => toast(t('copied')), fallback); else fallback();
}
const coll = new Intl.Collator('de', { numeric: true, sensitivity: 'base' });

// ------------------------------------------------------------------ i18n
let LANG = store('lang') === 'en' ? 'en' : 'de';
const UI = {
  de: {
    nav_overview: 'Übersicht', nav_entry: 'Eintrag', nav_classes: 'Klassen',
    search_ph: 'Suche: Datum (1942-04-01 · 1.4.1942), Ort, Band, Text, ID, Art, Person …', filter_ph: 'Einträge des Bands filtern …',
    tab_text: 'Text', tab_records: 'Datensätze', tab_scans: 'Scans', tab_node: 'Knoten',
    loading: 'Graph wird geladen …', decoding: 'Entpacke {0} MB …', indexing: 'Indexiere {0} Tripel …', load_fail: 'Der Graph konnte nicht geladen werden',
    theme_t: 'Hell / dunkel', help_t: 'Hilfe', copied: 'IRI kopiert', copy_iri: 'IRI kopieren',
    triples: 'Tripel', entries: 'Einträge', observations: 'Beobachtungen', nodes: 'Knoten', ontology: 'Ontologie',
    l_records: 'Datensätze', l_taxa: 'Taxa', l_places: 'Orte', l_persons: 'Personen', l_habitats: 'Habitate', l_archive: 'Archiv', l_authorities: 'Normdaten', l_provenance: 'Provenienz',
    group_by: 'Gruppieren', g_auto: 'automatisch (> 30)', g_none: 'nicht gruppieren', g_order: 'nach Ordnung', g_family: 'nach Familie', g_place: 'nach Ort', g_recordedBy: 'nach Beobachter', g_recordType: 'nach Nachweistyp',
    labels: 'Kantenbeschriftung', lb_auto: 'auto', lb_all: 'alle', lb_none: 'keine',
    fit: 'Einpassen', zoom_hint: 'Ziehen = verschieben · Strg+Rad = Zoom · Klick = Details · Doppelklick = Knotenansicht',
    col_archive: 'Archiv', col_regions: 'Quellregionen', col_entry: 'Eintrag', col_records: 'Datensätze', col_taxa: 'Taxa', col_shared: 'Orte · Personen · Habitate', col_auth: 'Normdaten',
    k_habitat: 'Habitatkonzept', k_auth: 'Normdatensatz', k_group: 'Gruppe', k_term: 'Ontologie-Term', k_ext: 'externe IRI', k_other: 'Knoten', k_concept: 'Konzept',
    several: 'mehrere', absent: 'fehlt', unresolved: '(ohne Ordnung)', none_val: '—',
    obs_n: '{0} Beob.', taxa_n: '{0} Taxa', expand_all: 'alle aufklappen', collapse_all: 'alle zuklappen',
    exact: 'exakt', close: 'eng', broad: 'weiter', legend_nodes: 'Knoten', legend_edges: 'Normdaten-Kanten',
    e_part: 'Teil/enthält', e_taxon: 'Taxon', e_place: 'Ort', e_person: 'Person', e_habitat: 'Habitat', e_detail: 'Wetter/Reise', e_prov: 'Provenienz',
    toggle_list: 'Eintragsliste ein/aus', prev: 'voriger Eintrag (←)', next: 'nächster Eintrag (→)', of_vol: '{0} / {1} in {2}',
    date: 'Datum', v_date: 'Datum (wörtlich)', place: 'Ort', v_place: 'Ort (wörtlich)', kind: 'Eintragsart', volume: 'Band', pages: 'Seiten', id: 'Kennung', plausible: 'Datum plausibel',
    transcript_note: 'Transkriptionsprüfung', field_notes: 'Eintragstext (dwc:fieldNotes)', weather: 'Wetter', travel: 'Reise', persons_m: 'Erwähnte Personen', mm_regions: 'Multimodale Regionen',
    visible_text: 'sichtbarer Text', no_text: '(kein Text)', legs: 'Etappen',
    r_taxon: 'Taxon', r_count: 'Anzahl', r_sexstage: 'Geschlecht / Stadium', r_behav: 'Verhalten', r_call: 'Laut', r_evid: 'Belegart', r_breed: 'Brutnachweis', r_type: 'Nachweistyp', r_place: 'Ort', r_by: 'beobachtet von', r_date: 'Datum', r_verb: 'Wortlaut', own_loc: 'eigene Örtlichkeit',
    no_records: 'Dieser Eintrag enthält keine Beobachtungen.', rec_count: '{0} Beobachtungen — Zeile anklicken, um sie im Graph zu zeigen',
    scans_none: 'Für diesen Eintrag ist keine Seite im Graph verknüpft.', scan_fail: 'Scan nicht geladen. Drive-Vorschauen brauchen eine Anmeldung bei Google mit Zugriff auf HistOrniGraph_output; lokal fehlt die Datei {0}.',
    open_drive: 'auf Drive öffnen', open_local: 'lokale Datei', scan_src: 'Quelle',
    statements: 'Aussagen', incoming: 'Eingehende Kanten', open_node: 'Knotenansicht', open_entry: 'Eintrag öffnen', open_ext: 'extern öffnen', show_in_graph: 'im Graph zeigen', more: '… {0} weitere',
    node_hint: 'Einen Knoten im Graph anklicken, um alle seine Tripel zu sehen.', members: 'Mitglieder',
    ov_title: 'Laubmann-Wissensgraph', ov_lead: 'Ornithologische Tagebücher Alfred Laubmanns (Bayern 1917–1965) · Quelle {0} · {1} Tripel · Ontologie {2} · gebaut {3}',
    per_volume: 'Einträge je Band', per_year: 'je Jahr', top_taxa: 'Häufigste Taxa', top_places: 'Häufigste Orte', top_persons: 'Häufigste Personen', top_habitats: 'Häufigste Habitate',
    map_places: 'Georeferenzierte Orte ({0})', classes: 'Klassen', predicates: 'Prädikate', count: 'Anzahl', uses: 'Verwendungen', class_t: 'Klasse', pred_t: 'Prädikat',
    per_year_t: 'je Jahr', per_month_t: 'je Monat', seg_entries: 'Einträge', seg_obs: 'Beobachtungen',
    usage: 'Verwendung im Graph ({0})', neighbourhood: 'Nachbarschaft', map: 'Karte', dist_map: 'Orte der Beobachtungen ({0})',
    all_preds: 'alle Prädikate', filter: 'Filter …', page_n: 'Seite {0} / {1}', record: 'Datensatz', entry: 'Eintrag', pred: 'Prädikat',
    no_coords: 'keine Koordinaten', class_list: '{0} ({1})', label: 'Bezeichnung', detail: 'Detail',
    s_entries: 'Einträge', s_text: 'Volltext', s_taxa: 'Taxa', s_places: 'Orte', s_persons: 'Personen', s_habitats: 'Habitate', s_other: 'Weitere Knoten', s_none: 'Keine Treffer.',
    early_years: '+ {0} vor {2} ({1}), nicht im Diagramm', months: 'Jan,Feb,Mär,Apr,Mai,Jun,Jul,Aug,Sep,Okt,Nov,Dez', no_vol: '(ohne Band)', entry_n: '{0} Einträge',
    help: `<h2>Graph-Explorer · Laubmann-Wissensgraph</h2>
<p>Alles, was hier erscheint, steht so im exportierten Graphen (Ontologie 0.7.0): die Seite enthält sämtliche Tripel der Exportdatei.</p>
<ul>
<li><b>Eintrag</b>: Links die Einträge des Bands, in der Mitte der Teilgraph des Eintrags: <i>Archiv</i> (Band → Seite → Quellregion) · <i>Eintrag</i> · <i>Datensätze</i> (Beobachtungen, Wetter, Reise mit Etappen) · <i>Taxa, Orte, Personen, Habitate</i> · <i>Normdaten</i> (GBIF, EUNIS, GeoNames, Wikidata, GND; durchgezogen = skos:exactMatch, gestrichelt = closeMatch, gepunktet = broadMatch). Ebenen lassen sich oben ein- und ausblenden. Viele Beobachtungen werden nach Ordnung gruppiert; eine Gruppe per Klick aufklappen.</li>
<li>Maus über einem Knoten hebt seine Kanten hervor; Klick zeigt alle Tripel des Knotens (Reiter <i>Knoten</i>), Doppelklick öffnet die Knotenansicht (alle Einträge und Beobachtungen, die ihn verwenden, Normdaten, Karte).</li>
<li>Reiter <i>Text</i>: Eintragstext mit markierten Belegstellen der Beobachtungen (anklickbar), Transkriptionsprüfung, Wetter, Reise, Personen, Regionen. <i>Datensätze</i>: eine Zeile je Beobachtung. <i>Scans</i>: Seitenscans (Google Drive, nur mit Zugriff auf HistOrniGraph_output; sonst lokale Dateien).</li>
<li>Tastatur: ← / → voriger / nächster Eintrag im Band, / Suche.</li>
</ul>`,
  },
  en: {
    nav_overview: 'Overview', nav_entry: 'Entry', nav_classes: 'Classes',
    search_ph: 'Search: date (1942-04-01), place, volume, text, id, taxon, person …', filter_ph: 'Filter entries of this volume …',
    tab_text: 'Text', tab_records: 'Records', tab_scans: 'Scans', tab_node: 'Node',
    loading: 'Loading graph …', decoding: 'Unpacking {0} MB …', indexing: 'Indexing {0} triples …', load_fail: 'The graph could not be loaded',
    theme_t: 'Light / dark', help_t: 'Help', copied: 'IRI copied', copy_iri: 'Copy IRI',
    triples: 'triples', entries: 'entries', observations: 'observations', nodes: 'nodes', ontology: 'ontology',
    l_records: 'Records', l_taxa: 'Taxa', l_places: 'Places', l_persons: 'Persons', l_habitats: 'Habitats', l_archive: 'Archive', l_authorities: 'Authorities', l_provenance: 'Provenance',
    group_by: 'Group', g_auto: 'automatic (> 30)', g_none: 'no grouping', g_order: 'by order', g_family: 'by family', g_place: 'by place', g_recordedBy: 'by observer', g_recordType: 'by record type',
    labels: 'Edge labels', lb_auto: 'auto', lb_all: 'all', lb_none: 'none',
    fit: 'Fit', zoom_hint: 'Drag = pan · Ctrl+wheel = zoom · click = details · double-click = node view',
    col_archive: 'Archive', col_regions: 'Source regions', col_entry: 'Entry', col_records: 'Records', col_taxa: 'Taxa', col_shared: 'Places · persons · habitats', col_auth: 'Authorities',
    k_habitat: 'Habitat concept', k_auth: 'Authority record', k_group: 'Group', k_term: 'Ontology term', k_ext: 'external IRI', k_other: 'Node', k_concept: 'Concept',
    several: 'several', absent: 'absent', unresolved: '(no order)', none_val: '—',
    obs_n: '{0} obs.', taxa_n: '{0} taxa', expand_all: 'expand all', collapse_all: 'collapse all',
    exact: 'exact', close: 'close', broad: 'broad', legend_nodes: 'Nodes', legend_edges: 'Authority links',
    e_part: 'part/contains', e_taxon: 'taxon', e_place: 'place', e_person: 'person', e_habitat: 'habitat', e_detail: 'weather/travel', e_prov: 'provenance',
    toggle_list: 'Show/hide entry list', prev: 'previous entry (←)', next: 'next entry (→)', of_vol: '{0} / {1} in {2}',
    date: 'Date', v_date: 'Verbatim date', place: 'Place', v_place: 'Verbatim locality', kind: 'Entry kind', volume: 'Volume', pages: 'Pages', id: 'Identifier', plausible: 'Date plausible',
    transcript_note: 'Transcript check', field_notes: 'Entry text (dwc:fieldNotes)', weather: 'Weather', travel: 'Travel', persons_m: 'Persons mentioned', mm_regions: 'Multimodal regions',
    visible_text: 'visible text', no_text: '(no text)', legs: 'Legs',
    r_taxon: 'Taxon', r_count: 'Count', r_sexstage: 'Sex / stage', r_behav: 'Behaviour', r_call: 'Call', r_evid: 'Evidence', r_breed: 'Breeding', r_type: 'Record type', r_place: 'Place', r_by: 'Recorded by', r_date: 'Date', r_verb: 'Verbatim', own_loc: 'own locality',
    no_records: 'This entry has no observations.', rec_count: '{0} observations — click a row to show it in the graph',
    scans_none: 'No page is linked to this entry in the graph.', scan_fail: 'Scan not loaded. Drive previews need a Google login with access to HistOrniGraph_output; the local file {0} is missing.',
    open_drive: 'open on Drive', open_local: 'local file', scan_src: 'source',
    statements: 'Statements', incoming: 'Incoming edges', open_node: 'Node view', open_entry: 'Open entry', open_ext: 'open externally', show_in_graph: 'show in graph', more: '… {0} more',
    node_hint: 'Click a node in the graph to see all its triples.', members: 'Members',
    ov_title: 'Laubmann Knowledge Graph', ov_lead: 'Ornithological diaries of Alfred Laubmann (Bavaria 1917–1965) · source {0} · {1} triples · ontology {2} · built {3}',
    per_volume: 'Entries per volume', per_year: 'per year', top_taxa: 'Top taxa', top_places: 'Top places', top_persons: 'Top persons', top_habitats: 'Top habitats',
    map_places: 'Georeferenced places ({0})', classes: 'Classes', predicates: 'Predicates', count: 'Count', uses: 'Uses', class_t: 'Class', pred_t: 'Predicate',
    per_year_t: 'per year', per_month_t: 'per month', seg_entries: 'Entries', seg_obs: 'Observations',
    usage: 'Use in the graph ({0})', neighbourhood: 'Neighbourhood', map: 'Map', dist_map: 'Places of the observations ({0})',
    all_preds: 'all predicates', filter: 'Filter …', page_n: 'page {0} / {1}', record: 'Record', entry: 'Entry', pred: 'Predicate',
    no_coords: 'no coordinates', class_list: '{0} ({1})', label: 'Label', detail: 'Detail',
    s_entries: 'Entries', s_text: 'Full text', s_taxa: 'Taxa', s_places: 'Places', s_persons: 'Persons', s_habitats: 'Habitats', s_other: 'Other nodes', s_none: 'No matches.',
    early_years: '+ {0} before {2} ({1}), not in the chart', months: 'Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec', no_vol: '(no volume)', entry_n: '{0} entries',
    help: `<h2>Graph explorer · Laubmann Knowledge Graph</h2>
<p>Everything shown here is stated in the exported graph (ontology 0.7.0): the page contains every triple of the export file.</p>
<ul>
<li><b>Entry</b>: the volume's entries on the left, the entry's subgraph in the middle: <i>archive</i> (volume → page → source region) · <i>entry</i> · <i>records</i> (observations, weather, travel with legs) · <i>taxa, places, persons, habitats</i> · <i>authorities</i> (GBIF, EUNIS, GeoNames, Wikidata, GND; solid = skos:exactMatch, dashed = closeMatch, dotted = broadMatch). Toggle layers at the top. Many observations are grouped by order; click a group to expand it.</li>
<li>Hovering a node highlights its edges; click shows all triples of the node (tab <i>Node</i>), double-click opens the node view (all entries and observations using it, authority links, map).</li>
<li>Tab <i>Text</i>: entry text with the evidence of each observation marked (clickable), transcript check, weather, travel, persons, regions. <i>Records</i>: one row per observation. <i>Scans</i>: page scans (Google Drive, only with access to HistOrniGraph_output; otherwise local files).</li>
<li>Keyboard: ← / → previous / next entry in the volume, / search.</li>
</ul>`,
  },
};
const t = (k, ...a) => { let s = UI[LANG][k]; if (s == null) s = UI.de[k]; if (s == null) s = k; a.forEach((v, i) => { s = s.split('{' + i + '}').join(v); }); return s; };
const fmtCache = {};
const fmt = n => (fmtCache[LANG] || (fmtCache[LANG] = new Intl.NumberFormat(LANG === 'de' ? 'de-DE' : 'en-GB'))).format(n);

// ------------------------------------------------------------------ kinds
const KIND_LIST = ['other', 'entry', 'obs', 'weather', 'travel', 'leg', 'taxon', 'place', 'person', 'habitat', 'auth',
  'volume', 'page', 'region', 'mmregion', 'run', 'agent', 'prompt', 'geom', 'scheme', 'concept', 'term', 'ext'];
const KI = Object.fromEntries(KIND_LIST.map((k, i) => [k, i]));
const CLASS_KIND = [ // priority order: first match wins for nodes with several types
  ['lkg:DiaryEntry', 'entry'], ['lkg:Observation', 'obs'], ['lkg:WeatherReport', 'weather'], ['lkg:TravelLeg', 'leg'], ['lkg:TravelEvent', 'travel'],
  ['lkg:Taxon', 'taxon'], ['lkg:Place', 'place'], ['lkg:Person', 'person'], ['lkg:MultimodalRegion', 'mmregion'], ['lkg:SourceRegion', 'region'],
  ['lkg:DiaryPage', 'page'], ['lkg:DiaryVolume', 'volume'], ['prov:Activity', 'run'], ['prov:SoftwareAgent', 'agent'], ['prov:Entity', 'prompt'],
  ['gsp:Geometry', 'geom'], ['skos:ConceptScheme', 'scheme'], ['skos:Concept', 'concept'],
];
const KIND_CLASS = Object.fromEntries(CLASS_KIND.map(([c, k]) => [k, c]));
const KIND_COLOR = { entry: 'entry', obs: 'rec', group: 'rec', ghead: 'rec', weather: 'detail', travel: 'detail', leg: 'detail', taxon: 'taxon', place: 'place', geom: 'place',
  person: 'person', habitat: 'habitat', auth: 'auth', miss: 'other', gone: 'other', volume: 'archive', page: 'archive', region: 'archive', mmregion: 'archive', run: 'prov', agent: 'prov', prompt: 'prov' };
const kc = k => KIND_COLOR[k] || 'other';
const SHARED = new Set(['taxon', 'place', 'person', 'habitat', 'auth', 'volume', 'page', 'concept', 'scheme', 'run', 'agent', 'prompt', 'region', 'mmregion', 'geom', 'term', 'ext', 'other']);
const LAYERS = [['records', 'rec'], ['taxa', 'taxon'], ['places', 'place'], ['persons', 'person'], ['habitats', 'habitat'], ['archive', 'archive'], ['authorities', 'auth'], ['provenance', 'prov'], ['props', 'props'], ['links', 'other']];   // [GC] properties (literal rows), other statements
const MATCH = ['skos:exactMatch', 'skos:closeMatch', 'skos:broadMatch'];
const PLACE_PREDS = ['lkg:observedAt', 'lkg:hasLocality', 'lkg:entryPlace', 'lkg:departurePlace', 'lkg:arrivalPlace', 'lkg:viaPlace'];
const OBS_KNOWN = new Set(['rdf:type', 'dcterms:isPartOf', 'prov:wasDerivedFrom', 'prov:wasGeneratedBy', 'lkg:observedTaxon', 'lkg:observedAt', 'lkg:hasLocality', 'dwciri:recordedBy', 'dwciri:habitat']);
const ENTRY_KNOWN = new Set(['rdf:type', 'dcterms:isPartOf', 'lkg:hasSourceRegion', 'lkg:hasMultimodalRegion', 'lkg:containsObservation', 'lkg:containsTravelEvent', 'lkg:hasWeather', 'lkg:entryPlace']);

// ------------------------------------------------------------------ graph store
const G = {};
window.LKGX = { G };

function decodeB64(b64) {
  if (typeof Uint8Array.fromBase64 === 'function') return Uint8Array.fromBase64(b64);
  const bin = atob(b64); const n = bin.length; const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = bin.charCodeAt(i);
  return out;
}
async function loadData() {
  const el = document.getElementById('kg-data');
  const b64 = el.textContent.trim(); el.textContent = ''; el.remove();
  $('#loadmsg').textContent = t('decoding', (b64.length * 0.75 / 1048576).toFixed(1));
  await new Promise(r => setTimeout(r, 0));
  const bytes = decodeB64(b64);
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buf = await new Response(stream).arrayBuffer();
  const L = new DataView(buf).getUint32(0, true);
  const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, L)));
  const TA = { u8: Uint8Array, u16: Uint16Array, u32: Uint32Array, i32: Int32Array };
  const A = {};
  for (const a of meta.arrays) A[a.name] = new TA[a.type](buf, a.offset, a.length);
  return { meta, A };
}

function buildIndex(meta, A) {
  Object.assign(G, { meta, nodes: meta.nodes, preds: meta.preds, lits: meta.lits, dts: meta.dts, langs: meta.langs,
    sOff: A.sOff, tP: A.tP, tO: A.tO, litDt: A.litDt, litLang: A.litLang });
  const nN = G.nodes.length; const { sOff, tP, tO } = G;
  G.N = new Map(); for (let i = 0; i < nN; i++) G.N.set(G.nodes[i], i);
  G.P = Object.create(null); G.preds.forEach((p, i) => { G.P[p] = i; });
  // incoming edges (CSR)
  const inOff = new Uint32Array(nN + 1);
  for (let i = 0; i < tO.length; i++) { const o = tO[i]; if (o >= 0) inOff[o + 1]++; }
  for (let i = 0; i < nN; i++) inOff[i + 1] += inOff[i];
  const cur = inOff.slice(0, nN); const inS = new Uint32Array(inOff[nN]); const inP = new Uint16Array(inOff[nN]);
  for (let s = 0; s < nN; s++) for (let i = sOff[s], e = sOff[s + 1]; i < e; i++) { const o = tO[i]; if (o >= 0) { const k = cur[o]++; inS[k] = s; inP[k] = tP[i]; } }
  Object.assign(G, { inOff, inS, inP });
  // kinds from rdf:type (+ skos:inScheme for concepts)
  const pType = PI('rdf:type'), pScheme = PI('skos:inScheme');
  const clsKind = new Map(); CLASS_KIND.forEach(([c, k], prio) => { const i = G.N.get(c); if (i !== undefined) clsKind.set(i, [k, prio]); });
  const habScheme = G.N.get('lkg:habitatScheme');
  const authSchemes = new Set(); for (let i = 0; i < nN; i++) if (G.nodes[i].startsWith('lkg:authority_')) authSchemes.add(i);
  const kind = new Uint8Array(nN);
  const ontNs = /^(lkg|dwc|dwciri|dcterms|dcmitype|rdf|rdfs|xsd|owl|skos|prov|geo|gsp|schema|rico):/;
  for (let s = 0; s < nN; s++) {
    let best = -1, prio = 1e9;
    for (let i = sOff[s], e = sOff[s + 1]; i < e; i++) {
      if (tP[i] === pType) { const ck = clsKind.get(tO[i]); if (ck && ck[1] < prio) { prio = ck[1]; best = KI[ck[0]]; } }
    }
    if (best === KI.concept) {
      for (let i = sOff[s], e = sOff[s + 1]; i < e; i++) if (tP[i] === pScheme) {
        if (tO[i] === habScheme) best = KI.habitat; else if (authSchemes.has(tO[i])) best = KI.auth;
      }
    }
    if (best < 0) { const c = G.nodes[s]; best = ontNs.test(c) ? KI.term : c.startsWith('data:') || c.startsWith('_:') ? KI.other : KI.ext; }
    kind[s] = best;
  }
  // untyped targets of the SKOS mapping properties are authority records too
  for (const m of MATCH) { const p = PI(m); if (p < 0) continue; for (let i = 0; i < tO.length; i++) if (tP[i] === p && tO[i] >= 0 && kind[tO[i]] === KI.ext) kind[tO[i]] = KI.auth; }
  G.kind = kind;
  buildEntries();
}

const PI = name => { const p = G.P[name]; return p === undefined ? -1 : p; };
function objs(n, name) { const p = PI(name), r = []; if (p < 0) return r; const { sOff, tP, tO } = G; for (let i = sOff[n], e = sOff[n + 1]; i < e; i++) if (tP[i] === p) r.push(tO[i]); return r; }
const nodeObjs = (n, name) => objs(n, name).filter(o => o >= 0);
function node1(n, name) { const p = PI(name); if (p < 0) return -1; const { sOff, tP, tO } = G; for (let i = sOff[n], e = sOff[n + 1]; i < e; i++) if (tP[i] === p && tO[i] >= 0) return tO[i]; return -1; }
const litsOf = (n, name) => objs(n, name).filter(o => o < 0).map(o => G.lits[-o - 1]);
function pref(n, name) { // literal value, preferring the UI language, then untagged, then German
  const p = PI(name); if (p < 0 || n < 0) return null; const { sOff, tP, tO } = G; let best = null, bs = -1;
  for (let i = sOff[n], e = sOff[n + 1]; i < e; i++) if (tP[i] === p && tO[i] < 0) {
    const l = -tO[i] - 1; const lg = G.langs[G.litLang[l]]; const sc = lg === LANG ? 3 : lg === '' ? 2 : lg === 'de' ? 1 : 0;
    if (sc > bs) { bs = sc; best = G.lits[l]; }
  }
  return best;
}
function incoming(n, name) { const p = PI(name), r = []; if (p < 0) return r; const { inOff, inS, inP } = G; for (let i = inOff[n], e = inOff[n + 1]; i < e; i++) if (inP[i] === p) r.push(inS[i]); return r; }
function inCount(n, name) { const p = PI(name); if (p < 0) return 0; const { inOff, inP } = G; let c = 0; for (let i = inOff[n], e = inOff[n + 1]; i < e; i++) if (inP[i] === p) c++; return c; }
const kindOf = n => (n < 0 ? 'other' : KIND_LIST[G.kind[n]]);
const isKind = (n, k) => n >= 0 && G.kind[n] === KI[k];
const uniq = a => Array.from(new Set(a));
function full(c) { if (c.startsWith('_:')) return c; const i = c.indexOf(':'); if (i > 0) { const ns = G.meta.prefixes[c.slice(0, i)]; if (ns) return ns + c.slice(i + 1); } return c; }
const iriOf = n => full(G.nodes[n]);
function localName(n) { const c = G.nodes[n]; const m = /([^:#/]+)\/?$/.exec(c); return m ? m[1] : c; }
function subPropOf(p, sup) { let q = p; for (let i = 0; i < 8 && q; i++) { if (q === sup) return true; q = G.meta.subProp[q]; } return false; }

// ------------------------------------------------------------------ labels
const pl = p => { if (p.startsWith('rv:')) return t('e_' + p.slice(3)); const l = G.meta.labels[p]; return l ? (l[LANG] || l.en || l.de) : p; };
const clsLabel = c => { const l = G.meta.labels[c]; return l ? (l[LANG] || l.en || l.de) : c; };
function kindLabel(k) {
  if (k === 'habitat') return t('k_habitat'); if (k === 'auth') return t('k_auth'); if (k === 'group' || k === 'ghead') return t('k_group');
  if (k === 'miss') return t('k_miss'); if (k === 'gone') return t('k_gone');   // [GC] ghost nodes
  if (k === 'term') return t('k_term'); if (k === 'ext') return t('k_ext'); if (k === 'other') return t('k_other'); if (k === 'concept') return t('k_concept');
  return KIND_CLASS[k] ? clsLabel(KIND_CLASS[k]) : k;
}
function cv(p, v) { const m = G.meta.vocab[p]; const e = m && m[v]; return e ? (e[LANG] || e.en || v) : v; }
const LC = { de: new Map(), en: new Map() };
function label(n) { if (n < 0) return ''; const m = LC[LANG]; let s = m.get(n); if (s === undefined) { s = computeLabel(n); m.set(n, s); } return s; }
function computeLabel(n) {
  const k = kindOf(n);
  if (k === 'obs') { const tx = node1(n, 'lkg:observedTaxon'); const c = countStr(n); return (tx >= 0 ? label(tx) : (pref(n, 'rdfs:label') || localName(n))) + (c ? ' · ' + c : ''); }
  if (k === 'leg') return legLabel(n);
  if (k === 'auth') return pref(n, 'skos:prefLabel') || pref(n, 'rdfs:label') || authId(n);
  if (k === 'geom') return pref(n, 'gsp:asWKT') || localName(n);
  return pref(n, 'rdfs:label') || pref(n, 'skos:prefLabel') || pref(n, 'schema:name') || pref(n, 'dcterms:identifier') || pref(n, 'skos:notation') || localName(n);
}
const AUTH_BY_PREFIX = { gbif: 'GBIF', wd: 'Wikidata', gn: 'GeoNames', eunis: 'EUNIS', gnd: 'GND' };
function schemeName(n) {
  const s = node1(n, 'skos:inScheme');
  if (s >= 0) { const m = G.meta.schemes[G.nodes[s]]; return (m && m.notation) || pref(s, 'skos:notation') || pref(s, 'skos:prefLabel') || localName(s); }
  const c = G.nodes[n]; const p = c.slice(0, c.indexOf(':')); return AUTH_BY_PREFIX[p] || '';
}
function authId(n) { const no = pref(n, 'skos:notation') || localName(n); const sch = schemeName(n); return sch ? sch + ' ' + no : no; }
function countStr(n) {
  if (pref(n, 'dwc:occurrenceStatus') === 'absent') return t('absent');
  const c = pref(n, 'dwc:individualCount'), mn = pref(n, 'lkg:individualCountMin'), mx = pref(n, 'lkg:individualCountMax'), q = pref(n, 'lkg:countQualifier');
  if (mn != null && mx != null) return mn + '–' + mx;
  if (c != null) return ({ minimum: '≥', maximum: '≤', approximate: '≈' }[q] || '') + c;
  if (mn != null) return '≥' + mn; if (mx != null) return '≤' + mx;
  if (q === 'plural-unspecified') return t('several');
  return '';
}
function legLabel(n) {
  const d = node1(n, 'lkg:departurePlace'), a = node1(n, 'lkg:arrivalPlace'); const via = nodeObjs(n, 'lkg:viaPlace');
  return (d >= 0 ? label(d) + ' ' : '') + '→ ' + (via.length ? via.map(label).join(' → ') + ' → ' : '') + (a >= 0 ? label(a) : '?');
}
function coords(n) {
  let la = parseFloat(pref(n, 'geo:lat') || pref(n, 'dwc:decimalLatitude')), lo = parseFloat(pref(n, 'geo:long') || pref(n, 'dwc:decimalLongitude'));
  if (!(isFinite(la) && isFinite(lo))) {
    const geo = node1(n, 'gsp:hasGeometry'); const w = pref(geo >= 0 ? geo : n, 'gsp:asWKT');
    const m = w && /POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)/i.exec(w); if (m) { lo = parseFloat(m[1]); la = parseFloat(m[2]); }
  }
  return isFinite(la) && isFinite(lo) ? [la, lo] : null;
}
function extUrl(n) {
  const iri = iriOf(n);
  if (!/^https?:\/\//.test(iri) || iri.startsWith(G.meta.prefixes.data) || iri.startsWith(G.meta.prefixes.lkg)) return null;
  let m;
  if ((m = /^https?:\/\/www\.wikidata\.org\/entity\/(Q\d+)$/.exec(iri))) return 'https://www.wikidata.org/wiki/' + m[1];
  if ((m = /^https?:\/\/sws\.geonames\.org\/(\d+)\/?$/.exec(iri))) return 'https://www.geonames.org/' + m[1];
  if (iri.startsWith(G.meta.prefixes.eunis)) { const sa = nodeObjs(n, 'rdfs:seeAlso').map(iriOf).find(u => u.includes('eionet')); if (sa) return sa; }
  return iri;
}

// ------------------------------------------------------------------ entries index
function buildEntries() {
  const nN = G.nodes.length; const ents = []; const vols = [];
  for (let n = 0; n < nN; n++) { if (G.kind[n] === KI.entry) ents.push(n); else if (G.kind[n] === KI.volume) vols.push(n); }
  vols.sort((a, b) => coll.compare(G.nodes[a], G.nodes[b]));
  const volRank = new Map(vols.map((v, i) => [v, i]));
  G.vols = vols;
  const pageOf = e => {
    const direct = nodeObjs(e, 'dcterms:isPartOf').filter(p => isKind(p, 'page'));
    if (direct.length) return direct[0];
    for (const r of nodeObjs(e, 'lkg:hasSourceRegion').concat(nodeObjs(e, 'lkg:hasMultimodalRegion'))) { const p = nodeObjs(r, 'dcterms:isPartOf').find(x => isKind(x, 'page')); if (p !== undefined) return p; }
    return -1;
  };
  G.ent = ents.map(n => {
    const page = pageOf(n); const vol = page >= 0 ? nodeObjs(page, 'dcterms:isPartOf').find(x => isKind(x, 'volume')) : undefined;
    return { n, id: pref(n, 'dcterms:identifier') || localName(n), date: pref(n, 'dwc:eventDate') || '', page, vol: vol === undefined ? -1 : vol,
      place: node1(n, 'lkg:entryPlace'), nobs: objs(n, 'lkg:containsObservation').length };
  });
  G.ent.sort((a, b) => ((a.vol < 0 ? 1e9 : volRank.get(a.vol)) - (b.vol < 0 ? 1e9 : volRank.get(b.vol))) || coll.compare(a.id, b.id));
  G.entPos = new Map(); G.entById = new Map(); G.entByVol = new Map(); G.idDup = new Set();
  G.ent.forEach((r, i) => {
    G.entPos.set(r.n, i); if (G.entById.has(r.id)) G.idDup.add(r.id); G.entById.set(r.id, r.n);
    if (!G.entByVol.has(r.vol)) G.entByVol.set(r.vol, []); G.entByVol.get(r.vol).push(i);
  });
}
function entryOf(n) { // the DiaryEntry a record belongs to
  if (n < 0) return -1; if (isKind(n, 'entry')) return n;
  for (let d = 0, x = n; d < 4 && x >= 0; d++) {
    const up = nodeObjs(x, 'dcterms:isPartOf').concat(nodeObjs(x, 'prov:wasDerivedFrom'));
    const e = up.find(u => isKind(u, 'entry')); if (e !== undefined) return e;
    x = up.length ? up[0] : -1;
  }
  return -1;
}
const entryRec = n => G.ent[G.entPos.get(n)];
const volLabel = v => (v < 0 ? t('no_vol') : label(v));
const entryPlaceLabel = r => (r.place >= 0 ? label(r.place) : (pref(r.n, 'dwc:verbatimLocality') || ''));

// ------------------------------------------------------------------ state + routing
const S = {
  view: 'overview', e: -1, sel: null, tab: store('tab') || 'check', group: store('group') || 'auto', labels: store('labels') || 'none',   // [GC] defaults
  layers: Object.assign({ records: true, taxa: true, places: true, persons: true, habitats: true, archive: false, authorities: false, provenance: false, props: true, links: false }, (() => { try { return JSON.parse(store('layers') || '{}'); } catch (e) { return {}; } })()),
  expanded: new Set(), vol: null, recSort: ['pos', 1], lastEntry: -1, props: store('props') || 'auto', propOpen: new Set(),   // [GC] mode of the properties layer
  list: store('list') ? store('list') === '1' : window.innerWidth >= 1200,
};
window.LKGX.S = S;
function go(h) { if (location.hash === '#' + h) route(); else location.hash = h; }
function setHashQuiet(h) { history.replaceState(null, '', '#' + h); }
function entryHash(e, selKey) {
  const r = entryRec(e); let h = '/e/' + encodeURIComponent(r && !G.idDup.has(r.id) ? r.id : G.nodes[e]);
  if (selKey && selKey.startsWith('n')) h += '/' + G.nodes[+selKey.slice(1)];
  return h;
}
function route() {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  const parts = h.split('/');
  $('#qres').hidden = true;
  if (parts[0] === 'e') {
    let e = G.entById.get(parts[1]); if (e === undefined) e = G.N.get(parts[1]);
    if (e === undefined || !isKind(e, 'entry')) { toast('?'); return go('/'); }
    const sel = parts.length > 2 ? G.N.get(parts.slice(2).join('/')) : undefined;
    return showEntry(e, sel === undefined ? null : 'n' + sel);
  }
  if (parts[0] === 'n') {
    const n = G.N.get(parts.slice(1).join('/'));
    if (n === undefined) return go('/');
    if (isKind(n, 'entry')) return showEntry(n, null);
    return showNode(n);
  }
  if (parts[0] === 'c') return showClass(parts[1] || 'taxon');
  return showOverview();
}
function setView(v) {
  S.view = v;
  $$('.view').forEach(x => x.classList.toggle('on', x.id === 'v-' + v));
  $$('#nav button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.nav === (v === 'class' ? 'classes' : v))));
}

// ------------------------------------------------------------------ static texts
function applyStatic() {
  document.documentElement.lang = LANG;
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  $('#btn-lang').textContent = LANG === 'de' ? 'EN' : 'DE';
  $('#apptitle').textContent = t('app_title'); document.title = t('app_title');
  rvApplyStatic();   // [GC]
}

// ------------------------------------------------------------------ small chart helpers
function barList(items, color, max) {
  const m = max || Math.max(1, ...items.map(x => x.v));
  return '<div class="bars">' + items.map(x => `<div class="row" data-go="${esc(x.go)}" title="${esc(x.title || x.l)}: ${fmt(x.v)}"><span class="lab">${esc(x.l)}</span><span><div class="bar" style="width:${(100 * x.v / m).toFixed(1)}%;background:var(--c-${color})"></div></span><span class="val">${fmt(x.v)}</span></div>`).join('') + '</div>';
}
const YEAR_FLOOR = 1900;
function yearSpan(maps) { // [first, last] year for the axis + note on earlier years
  const ys = new Set(); for (const m of maps) for (const y of m.keys()) ys.add(y);
  const all = [...ys].sort((a, b) => a - b); if (!all.length) return { y0: 0, y1: -1, note: '' };
  const early = all.filter(y => y < YEAR_FLOOR); const inRange = all.filter(y => y >= YEAR_FLOOR);
  const y0 = inRange.length ? inRange[0] : all[0], y1 = all[all.length - 1];
  let note = '';
  if (early.length && inRange.length) { const n = early.reduce((s_, y) => s_ + (maps[0].get(y) || 0), 0); note = t('early_years', fmt(n), early[0] + (early.length > 1 ? '–' + early[early.length - 1] : ''), YEAR_FLOOR); }
  return { y0, y1, note };
}
function niceMax(v) { if (v <= 5) return 5; const p = Math.pow(10, Math.floor(Math.log10(v))); for (const f of [1, 2, 2.5, 5, 10]) if (f * p >= v) return f * p; return v; }
function colChart(items, color, opts = {}) { // items [{l, v, go, title}]
  const W = 600, H = 170, padL = 34, padB = 20, n = items.length; if (!n) return '';
  const mx = niceMax(Math.max(1, ...items.map(x => x.v))); const bw = (W - padL) / n; const gap = Math.min(2, bw * 0.2);
  let s = `<svg viewBox="0 0 ${W} ${H + 6}" role="img">`;
  for (let g = 0; g <= 2; g++) { const y = (H - padB) * (1 - g / 2); s += `<line class="${g ? 'grid' : 'base'}" x1="${padL}" x2="${W}" y1="${y}" y2="${y}"/><text class="ax" x="${padL - 4}" y="${y + 3}" text-anchor="end">${fmt(mx * g / 2)}</text>`; }
  const every = opts.every || Math.ceil(n / 12);
  items.forEach((x, i) => {
    const h = (H - padB) * x.v / mx; const xx = padL + i * bw + gap / 2;
    s += `<rect class="bar" x="${xx.toFixed(1)}" y="${(H - padB - h).toFixed(1)}" width="${Math.max(1, bw - gap).toFixed(1)}" height="${Math.max(0, h).toFixed(1)}" rx="${Math.min(3, bw / 4).toFixed(1)}" fill="var(--c-${color})"${x.go ? ` data-go="${esc(x.go)}"` : ''}><title>${esc(x.title || x.l)}: ${fmt(x.v)}</title></rect>`;
    if (i % every === 0) s += `<text class="ax" x="${(xx + (bw - gap) / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(x.l)}</text>`;
  });
  return s + '</svg>';
}

// ------------------------------------------------------------------ Leaflet
function makeMap(el, pts, opts = {}) { // pts [{la, lo, r, label, go}]
  if (typeof L === 'undefined') { el.textContent = 'Leaflet missing'; return null; }
  if (el._map) { el._map.remove(); el._map = null; }
  const map = L.map(el, { scrollWheelZoom: false, preferCanvas: true });
  // [GC] tile.openstreetmap.org answers 403 to pages opened from file:// (no Referer); the Esri services do not need one
  const esri = s => 'https://server.arcgisonline.com/ArcGIS/rest/services/' + s + '/MapServer/tile/{z}/{y}/{x}';
  const base = { Topo: L.tileLayer(esri('World_Topo_Map'), { maxZoom: 18, attribution: 'Tiles © Esri' }), 'Straßen': L.tileLayer(esri('World_Street_Map'), { maxZoom: 18, attribution: 'Tiles © Esri, HERE, Garmin, OpenStreetMap' }), Luftbild: L.tileLayer(esri('World_Imagery'), { maxZoom: 18, attribution: 'Tiles © Esri, Maxar' }) };
  base.Topo.addTo(map); L.control.layers(base, null, { collapsed: false }).addTo(map);
  const color = getComputedStyle(document.documentElement).getPropertyValue('--c-place').trim() || '#2a78d6';
  const layer = L.featureGroup();
  for (const p of pts) {
    const mk = L.circleMarker([p.la, p.lo], { radius: p.r || 5, color, weight: 1, fillColor: color, fillOpacity: 0.45 });
    mk.bindTooltip(esc(p.label));
    if (p.go) mk.on('click', () => go(p.go));
    mk.addTo(layer);
    if (opts.unc && p.unc) L.circle([p.la, p.lo], { radius: p.unc, color, weight: 1, fillOpacity: 0.06, dashArray: '4 4' }).addTo(layer);
  }
  layer.addTo(map);
  el._map = map;
  const fitIt = () => { map.invalidateSize(); if (pts.length === 1) map.setView([pts[0].la, pts[0].lo], opts.zoom || 11); else if (pts.length) map.fitBounds(layer.getBounds().pad(0.08), { maxZoom: 12 }); else map.setView([48.3, 11.4], 7); };
  fitIt(); setTimeout(fitIt, 60);
  return map;
}

// ------------------------------------------------------------------ overview
function stats() {   // [GC] counts follow the corpus filter (rvSrcOk, rvInCount)
  if (G.stats) return G.stats;
  const filt = corpusOn();
  const nN = G.nodes.length; const kcnt = new Uint32Array(KIND_LIST.length); for (let n = 0; n < nN; n++) kcnt[G.kind[n]]++;
  const pc = new Uint32Array(G.preds.length); for (let i = 0; i < G.tP.length; i++) pc[G.tP[i]]++;
  const classCount = new Map(); const pType = PI('rdf:type');
  if (pType >= 0) for (let i = 0; i < G.tP.length; i++) if (G.tP[i] === pType) { const o = G.tO[i]; classCount.set(o, (classCount.get(o) || 0) + 1); }
  const yE = new Map(), yO = new Map();
  const ents = filt ? G.ent.filter(r => rvSrcOk(r.n)) : G.ent;
  for (const r of ents) { const y = +r.date.slice(0, 4); if (y) yE.set(y, (yE.get(y) || 0) + 1); }
  const byKind = k => { const r = []; for (let n = 0; n < nN; n++) if (G.kind[n] === KI[k]) r.push(n); return r; };
  const obsNodes = filt ? byKind('obs').filter(rvSrcOk) : byKind('obs');
  for (const o of obsNodes) { const d = pref(o, 'dwc:eventDate'); const y = d ? +d.slice(0, 4) : 0; if (y) yO.set(y, (yO.get(y) || 0) + 1); }
  const uses = (n, preds) => preds.reduce((s, p) => s + rvInCount(n, p), 0);
  const mentionPreds = G.preds.filter(p => subPropOf(p, 'lkg:mentionsPerson'));
  const top = (k, preds) => byKind(k).map(n => ({ n, v: uses(n, preds) })).filter(x => x.v > 0).sort((a, b) => b.v - a.v);
  const places = byKind('place');
  const geo = []; for (const p of places) { const c = coords(p); if (c) { const v = uses(p, PLACE_PREDS); if (!filt || v > 0) geo.push({ n: p, c, v }); } }
  G.stats = { kc: kcnt, pc, classCount, yE, yO, obsCount: obsNodes.length, taxa: top('taxon', ['lkg:observedTaxon']), places: top('place', PLACE_PREDS),
    persons: top('person', ['dwciri:recordedBy'].concat(mentionPreds.filter(p => p === 'lkg:mentionsPerson'))), habitats: top('habitat', ['dwciri:habitat']), geo, nPlaces: places.length };
  kcnt[KI.entry] = ents.length; kcnt[KI.obs] = obsNodes.length;
  if (filt) { for (const k of ['taxon', 'place', 'person', 'habitat']) kcnt[KI[k]] = byKind(k).filter(n => rvUses(n) > 0).length; G.stats.nPlaces = kcnt[KI.place]; }
  return G.stats;
}
function showOverview() {
  setView('overview');
  rvRenderOverview();   // [GC] the review overview stands above the explorer's
  const v = $('#x-ov');
  if (v.dataset.lang === LANG && v.dataset.theme === document.documentElement.dataset.theme && v.dataset.corpus === String(RVU.corpus)) { const m = $('#ov-map'); if (m && m._map) setTimeout(() => m._map.invalidateSize(), 30); return; }
  v.dataset.lang = LANG; v.dataset.theme = document.documentElement.dataset.theme; v.dataset.corpus = String(RVU.corpus);
  const st = stats();
  const tile = (val, lab, h) => `<div class="tile"${h ? ` data-go="${h}"` : ' style="cursor:default"'}><div class="v num">${fmt(val)}</div><div class="l">${esc(lab)}</div></div>`;
  const built = (G.meta.built || '').slice(0, 16).replace('T', ' ');
  const volItems = G.vols.map(vn => { const ids = (G.entByVol.get(vn) || []).filter(i => rvSrcOk(G.ent[i].n)); return { l: label(vn).replace(/^Laubmann\s*·\s*/, ''), title: label(vn) + ' · ' + (pref(vn, 'dcterms:temporal') || ''), v: ids.length, go: ids.length ? entryHash(G.ent[ids[0]].n) : '/n/' + G.nodes[vn] }; });
  const span = yearSpan([st.yE, st.yO]); const y0 = span.y0, y1 = span.y1;
  const yearNote = which => { const m = which === 'obs' ? st.yO : st.yE; const sp = yearSpan([m]); return sp.note ? `<div class="muted" style="font-size:.74rem">${esc(sp.note)}</div>` : ''; };
  const yearItems = which => { const m = which === 'obs' ? st.yO : st.yE; const r = []; if (y0) for (let y = y0; y <= y1; y++) { const first = G.ent.find(x => x.date.startsWith(String(y))); r.push({ l: String(y), v: m.get(y) || 0, go: first ? entryHash(first.n) : '' }); } return r; };
  const topItems = (arr, k) => arr.slice(0, 15).map(x => ({ l: label(x.n), v: x.v, go: '/n/' + G.nodes[x.n], title: label(x.n) + (k === 'taxon' ? ' · ' + (pref(x.n, 'dwc:scientificName') || '') : '') }));
  const kindRows = KIND_LIST.map((k, i) => ({ k, c: st.kc[i] })).filter(x => x.c && !['term', 'ext', 'other', 'scheme'].includes(x.k));
  const classRows = [...st.classCount.entries()].sort((a, b) => b[1] - a[1]);
  const predRows = G.preds.map((p, i) => ({ p, c: st.pc[i] })).sort((a, b) => b.c - a.c);
  v.innerHTML = `<div class="page">
    <h2>${t('ov_title')}</h2>
    <p class="lead">${esc(t('ov_lead', G.meta.sourcePath || G.meta.source, fmt(G.meta.triples), G.meta.ontologyVersion || '?', built))}</p>
    <div class="tiles">
      ${tile(st.kc[KI.entry], kindLabel('entry'), G.ent.length ? entryHash(G.ent[0].n) : '/')}
      ${tile(st.kc[KI.obs], kindLabel('obs'), '/c/obs')}
      ${tile(st.kc[KI.taxon], kindLabel('taxon'), '/c/taxon')}
      ${tile(st.kc[KI.place], kindLabel('place'), '/c/place')}
      ${tile(st.kc[KI.person], kindLabel('person'), '/c/person')}
      ${tile(st.kc[KI.habitat], kindLabel('habitat'), '/c/habitat')}
      ${tile(st.kc[KI.auth], kindLabel('auth'), '/c/auth')}
      ${tile(G.vols.length, kindLabel('volume'), '/c/volume')}
      ${tile(st.kc[KI.page], kindLabel('page'), '/c/page')}
      ${tile(G.meta.triples, t('triples'), '')}
    </div>
    <div class="grid2">
      <div class="card"><h3>${t('per_volume')}</h3>${barList(volItems, 'archive')}</div>
      <div class="card"><h3>${t('per_year')}<span class="sp"></span><span class="seg" id="ov-yseg"><button data-w="entries" class="on">${t('seg_entries')}</button><button data-w="obs">${t('seg_obs')}</button></span></h3><div class="cols" id="ov-year">${colChart(yearItems('entries'), 'entry')}${yearNote('entries')}</div>
        <h3 style="margin-top:18px">${t('map_places', fmt(st.geo.length) + ' / ' + fmt(st.nPlaces))}</h3><div class="map" id="ov-map"></div></div>
    </div>
    <div class="grid2" style="margin-top:16px">
      <div class="card"><h3>${t('top_taxa')}</h3>${barList(topItems(st.taxa, 'taxon'), 'taxon')}</div>
      <div class="card"><h3>${t('top_places')}</h3>${barList(topItems(st.places), 'place')}</div>
      <div class="card"><h3>${t('top_persons')}</h3>${barList(topItems(st.persons), 'person')}</div>
      <div class="card"><h3>${t('top_habitats')}</h3>${barList(topItems(st.habitats), 'habitat')}</div>
    </div>
    <div class="grid2" style="margin-top:16px">
      <div class="card"><h3>${t('classes')}</h3><table class="t">
        <tr><th>${t('class_t')}</th><th>IRI</th><th style="text-align:right">${t('count')}</th></tr>
        ${kindRows.map(x => `<tr class="click" data-go="/c/${x.k}"><td><span class="kbadge k-c-${kc(x.k)}">${esc(kindLabel(x.k))}</span></td><td class="iri">${esc(KIND_CLASS[x.k] || (x.k === 'habitat' ? 'skos:Concept ∈ lkg:habitatScheme' : x.k === 'auth' ? 'skos:Concept ∈ lkg:authority_*' : ''))}</td><td class="num" style="text-align:right">${fmt(x.c)}</td></tr>`).join('')}
      </table>
      <details style="margin-top:10px"><summary class="link">rdf:type (${classRows.length})</summary><table class="t">${classRows.map(([c, k]) => `<tr><td>${esc(clsLabel(G.nodes[c]))}</td><td class="iri">${esc(G.nodes[c])}</td><td class="num" style="text-align:right">${fmt(k)}</td></tr>`).join('')}</table></details></div>
      <div class="card"><h3>${t('predicates')} (${predRows.length})</h3><div style="max-height:420px;overflow:auto"><table class="t">
        <tr><th>${t('pred_t')}</th><th>IRI</th><th style="text-align:right">${t('count')}</th></tr>
        ${predRows.map(x => `<tr title="${esc(G.meta.defs[x.p] || '')}"><td>${esc(pl(x.p))}</td><td class="iri">${esc(x.p)}</td><td class="num" style="text-align:right">${fmt(x.c)}</td></tr>`).join('')}
      </table></div></div>
    </div>
  </div>`;
  $('#ov-yseg').addEventListener('click', ev => {
    const b = ev.target.closest('button'); if (!b) return;
    $$('#ov-yseg button').forEach(x => x.classList.toggle('on', x === b));
    $('#ov-year').innerHTML = colChart(yearItems(b.dataset.w), b.dataset.w === 'obs' ? 'rec' : 'entry') + yearNote(b.dataset.w);
  });
  const mx = Math.max(1, ...st.geo.map(g => g.v));
  makeMap($('#ov-map'), st.geo.map(g => ({ la: g.c[0], lo: g.c[1], r: 3 + 11 * Math.sqrt(g.v / mx), label: `${label(g.n)} · ${fmt(g.v)}`, go: '/n/' + G.nodes[g.n] })));
}

// ------------------------------------------------------------------ entry view
function showEntry(e, selKey) {
  setView('entry');
  const changed = S.e !== e;
  if (changed) { S.e = e; S.expanded = new Set(); S.lastEntry = e; }
  S.sel = selKey || (changed ? null : S.sel);
  rvEnterEntry(e, changed);          // [GC] entry model, work list, scan pane
  renderEntryHead();
  renderTools();
  renderGraph(!changed);
  if (S.sel && SUB && !SUB.V.has(S.sel)) revealNode(S.sel);
  if (S.sel && selKey) { centerOn(S.sel); rvOnSelect(S.sel, { fromRoute: true }); }
  rvRenderTable();                   // [GC] the records table replaces the graph when toggled
  renderPanel();
}
// [GC] renderVolSelect, renderEntryList, markEntryList and stepEntry of the explorer are replaced by the work list (gc_views.js)
function renderEntryHead() {   // [GC] position in the queue, graph/table toggle, checked state
  const e = S.e, r = entryRec(e); const q = rvQueuePos(e);
  $('#ehead').innerHTML = `<button class="btn" data-act="list" title="${t('toggle_list')}">☰</button><span class="navb"><button class="btn" data-act="prev" title="${t('prev')}" ${q.pos === 0 ? 'disabled' : ''}>◀</button><button class="btn" data-act="next" title="${t('next')}" ${q.pos >= q.n - 1 ? 'disabled' : ''}>▶</button></span>
    <span class="t" title="${esc(label(e))}">${esc(label(e))}</span><span class="muted mono" style="font-size:.78rem">${esc(r.id)}</span>
    ${rvHeadHtml(e, q.pos >= 0 ? t('of_queue', fmt(q.pos + 1), fmt(q.n), t('q_' + q.queue)) : volLabel(r.vol))}`;
}
function renderTools() {
  if (rvToolsHtml()) return;   // [GC] the records table has its own tool row
  const g = S.group;
  $('#gtools').innerHTML = LAYERS.map(([l, c]) => `<span class="chip ${S.layers[l] ? 'on' : ''}" data-layer="${l}"><i style="background:var(--c-${c})"></i>${t('l_' + l)}</span>`).join('') +
    `<select id="grpsel" title="${t('group_by')}">${['auto', 'none', 'order', 'family', 'place', 'recordedBy', 'recordType'].map(k => `<option value="${k}" ${k === g ? 'selected' : ''}>${t('grp_short')}: ${t('g_' + k)}</option>`).join('')}</select>
     <button class="zbtn" data-act="expand" title="${t('expand_all')}">▾▾</button><button class="zbtn" data-act="collapse" title="${t('collapse_all')}">▸▸</button>
     <select id="lblsel" title="${t('labels')}">${['auto', 'all', 'none'].map(k => `<option value="${k}" ${k === S.labels ? 'selected' : ''}>${t('labels_short')}: ${t('lb_' + k)}</option>`).join('')}</select>
     ${rvGraphTools()}<span class="sp"></span>
     <button class="zbtn" data-act="zout" title="−">−</button><button class="zbtn" data-act="zin" title="+">+</button><button class="zbtn" data-act="fit" title="${t('fit')}">⤢</button>`;   // [GC] compact: the middle column is narrow
  // [GC] the legend explains the annotation layer; node colours are on the layer chips above
  $('#legend').innerHTML = rvLegendHtml() + (S.layers.authorities ? `<span style="margin-left:8px">${t('legend_edges')}:</span>` +
    [['exact', 'c-exact'], ['close', 'c-close'], ['broad', 'c-broad']].map(([k, c]) => `<span class="li"><svg width="26" height="8"><path class="edge ${c}" d="M1,4 L25,4"/></svg>${t(k)}</span>`).join('') : '');
}

// ---- subgraph model
let SUB = null;
const COLW = { 0: 150, 1: 164, 2: 176, 3: 154, 4: 160, 5: 160 };   // [GC] a little narrower: the graph shares the width with the scan
const NGAP = 7; const colGap = () => (S.labels === 'none' ? 46 : 80);   // [GC] narrower columns without edge labels
function textPos(e) { // position of each observation's verbatim notes in the entry text
  if (textPos.e === e) return textPos.m;
  const fn = pref(e, 'dwc:fieldNotes') || ''; const m = new Map();
  for (const o of nodeObjs(e, 'lkg:containsObservation')) {
    const vn = (pref(o, 'lkg:verbatimNotes') || '').trim(); let hit = null;
    if (vn) {
      let i = fn.indexOf(vn); if (i >= 0) hit = [i, vn.length];
      else for (const len of [40, 24, 14]) if (vn.length > len) { i = fn.indexOf(vn.slice(0, len)); if (i >= 0) { hit = [i, len]; break; } }
    }
    m.set(o, hit);
  }
  textPos.e = e; textPos.m = m; return m;
}
function obsOfEntry(e) {
  const obs = uniq(nodeObjs(e, 'lkg:containsObservation').concat(incoming(e, 'dcterms:isPartOf').filter(x => isKind(x, 'obs')))).filter(rvObsShown);   // [GC] corpus filter
  const tp = textPos(e);
  return obs.map(o => ({ o, p: tp.get(o) ? tp.get(o)[0] : 1e9, l: label(o) })).sort((a, b) => a.p - b.p || coll.compare(a.l, b.l)).map(x => x.o);
}
function groupKey(o, mode) {
  const tx = node1(o, 'lkg:observedTaxon');
  if (mode === 'order') return tx >= 0 ? (pref(tx, 'dwc:order') || (pref(tx, 'dwc:class') ? pref(tx, 'dwc:class') : t('unresolved'))) : t('unresolved');
  if (mode === 'family') return tx >= 0 ? (pref(tx, 'dwc:family') || pref(tx, 'dwc:order') || t('unresolved')) : t('unresolved');
  if (mode === 'place') { const p = node1(o, 'lkg:hasLocality'); const q = p >= 0 ? p : node1(o, 'lkg:observedAt'); return q >= 0 ? label(q) : t('none_val'); }
  if (mode === 'recordedBy') return nodeObjs(o, 'dwciri:recordedBy').map(label).join(' | ') || t('none_val');
  if (mode === 'recordType') return cv('lkg:recordType', pref(o, 'lkg:recordType') || '') || t('none_val');
  return '';
}
function buildSub(e) {
  const on = l => S.layers[l];
  const V = new Map(), E = new Map();
  const add = (n, col, o) => { const key = (o && o.key) || 'n' + n; let v = V.get(key); if (!v) { v = Object.assign({ key, n, kind: kindOf(n), col, ord: V.size }, o || {}); V.set(key, v); } return v; };
  const pairs = new Set();
  const link = (a, b, p, cnt) => { if (!a || !b || a === b) return; pairs.add(a.key + '|' + b.key); pairs.add(b.key + '|' + a.key); const k = a.key + '|' + b.key + '|' + p; const x = E.get(k); if (x) x.count += cnt || 1; else E.set(k, { a, b, p, count: cnt || 1 }); };
  const ev = add(e, 1);
  // records column (col 2) is added first so that its insertion order is its vertical order
  const records = [];
  if (on('records')) {
    const weather = uniq(nodeObjs(e, 'lkg:hasWeather').concat(incoming(e, 'dcterms:isPartOf').filter(x => isKind(x, 'weather'))));
    const travel = uniq(nodeObjs(e, 'lkg:containsTravelEvent').concat(incoming(e, 'dcterms:isPartOf').filter(x => isKind(x, 'travel'))));
    for (const w of weather) { const wv = add(w, 2); link(ev, wv, objs(e, 'lkg:hasWeather').includes(w) ? 'lkg:hasWeather' : 'dcterms:hasPart'); records.push(wv); }
    for (const tr of travel) {
      const tv = add(tr, 2); link(ev, tv, 'lkg:containsTravelEvent'); records.push(tv);
      for (const leg of nodeObjs(tr, 'lkg:hasLeg')) {
        const lv = add(leg, 2); link(tv, lv, 'lkg:hasLeg'); records.push(lv);
        if (on('places')) for (const p of ['lkg:departurePlace', 'lkg:viaPlace', 'lkg:arrivalPlace']) for (const pl_ of nodeObjs(leg, p)) link(lv, add(pl_, 4), p);
      }
    }
    const obs = obsOfEntry(e);
    const mode = S.group === 'auto' ? (obs.length > 30 ? 'order' : 'none') : S.group;
    const groups = new Map();
    if (mode !== 'none') for (const o of obs) { const k = groupKey(o, mode); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(o); }
    const srcOf = new Map();
    const placeObs = o => { const v = add(o, 2); srcOf.set(o, v); records.push(v); link(ev, v, 'lkg:containsObservation'); };
    if (mode === 'none') obs.forEach(placeObs);
    else for (const [k, members] of groups) {
      if (members.length === 1) { placeObs(members[0]); continue; }
      const gkey = mode + ':' + k;
      if (S.expanded.has(gkey)) {
        records.push(add(-1, 2, { key: 'h:' + gkey, kind: 'ghead', gkey, label: k, members }));
        members.forEach(placeObs);
      } else {
        const gv = add(-1, 2, { key: 'g:' + gkey, kind: 'group', gkey, label: k, members });
        records.push(gv); link(ev, gv, 'lkg:containsObservation', members.length);
        members.forEach(o => srcOf.set(o, gv));
      }
    }
    for (const o of obs) {
      const src = srcOf.get(o); const collapsed = src.kind === 'group';
      if (on('taxa') && !collapsed) for (const x of nodeObjs(o, 'lkg:observedTaxon')) link(src, add(x, 3), 'lkg:observedTaxon');
      if (on('places')) for (const p of ['lkg:observedAt', 'lkg:hasLocality']) for (const x of nodeObjs(o, p)) link(src, add(x, 4), p);
      if (on('persons')) for (const x of nodeObjs(o, 'dwciri:recordedBy')) link(src, add(x, 4), 'dwciri:recordedBy');
      if (on('habitats')) for (const x of nodeObjs(o, 'dwciri:habitat')) link(src, add(x, 4), 'dwciri:habitat');
      // any further node-valued statement of the observation
      for (let i = G.sOff[o], end = G.sOff[o + 1]; i < end; i++) {
        const p = G.preds[G.tP[i]], x = G.tO[i];
        if (x < 0 || OBS_KNOWN.has(p) || p.startsWith('prov:')) continue;
        const k = kindOf(x); if ((k === 'taxon' && (!on('taxa') || collapsed)) || (k === 'place' && !on('places')) || (k === 'person' && !on('persons')) || (k === 'habitat' && !on('habitats'))) continue;
        link(src, add(x, k === 'taxon' ? 3 : 4), p);
      }
    }
    rvGhosts(e, add, link, ev, records);   // [GC] missing records and removed mentions as ghost nodes
    if (on('provenance')) {
      for (const v of records) {
        const nodes = v.kind === 'group' ? v.members : v.kind === 'ghead' || v.n < 0 ? [] : [v.n];
        for (const n of nodes) {
          for (const run of nodeObjs(n, 'prov:wasGeneratedBy')) link(v, add(run, 1, { bottom: true }), 'prov:wasGeneratedBy');
          for (const d of nodeObjs(n, 'prov:wasDerivedFrom')) if (d === e && !pairs.has(v.key + '|' + ev.key) && v.kind !== 'leg') link(v, ev, 'prov:wasDerivedFrom');
        }
      }
    }
  }
  // entry-level statements
  if (on('places')) for (const x of nodeObjs(e, 'lkg:entryPlace')) link(ev, add(x, 4), 'lkg:entryPlace');
  if (on('persons')) {
    const byPerson = new Map();
    for (let i = G.sOff[e], end = G.sOff[e + 1]; i < end; i++) {
      const p = G.preds[G.tP[i]], x = G.tO[i];
      if (x >= 0 && (subPropOf(p, 'lkg:mentionsPerson') || p === 'schema:mentions')) { if (!byPerson.has(x)) byPerson.set(x, new Set()); byPerson.get(x).add(p); }
    }
    for (const [x, ps] of byPerson) { const specific = [...ps].filter(p => p !== 'lkg:mentionsPerson' && p !== 'schema:mentions'); for (const p of (specific.length ? specific : [...ps])) link(ev, add(x, 4), p); }
  }
  for (let i = G.sOff[e], end = G.sOff[e + 1]; i < end; i++) { // further node-valued statements of the entry
    const p = G.preds[G.tP[i]], x = G.tO[i];
    if (x < 0 || ENTRY_KNOWN.has(p) || subPropOf(p, 'lkg:mentionsPerson') || p === 'schema:mentions' || p.startsWith('prov:')) continue;
    const k = kindOf(x); if ((k === 'place' && !on('places')) || (k === 'person' && !on('persons'))) continue;
    link(ev, add(x, k === 'taxon' ? 3 : 4), p);
  }
  // archive: entry → regions → pages → volume
  if (on('archive')) {
    const mm = new Set(nodeObjs(e, 'lkg:hasMultimodalRegion'));
    const regs = uniq(nodeObjs(e, 'lkg:hasSourceRegion').concat([...mm]));
    const pageLabel = n => pref(n, 'dcterms:identifier') || label(n);
    const regInfo = regs.map(r => ({ r, pg: nodeObjs(r, 'dcterms:isPartOf').find(x => isKind(x, 'page')) }));
    regInfo.sort((a, b) => coll.compare(a.pg !== undefined ? pageLabel(a.pg) : '~', b.pg !== undefined ? pageLabel(b.pg) : '~') || coll.compare(label(a.r), label(b.r)));
    const pages = uniq(nodeObjs(e, 'dcterms:isPartOf').filter(x => isKind(x, 'page')).concat(regInfo.map(x => x.pg).filter(x => x !== undefined)));
    pages.sort((a, b) => coll.compare(pageLabel(a), pageLabel(b)));
    const vols = uniq([].concat(...pages.map(pg => nodeObjs(pg, 'dcterms:isPartOf').filter(x => isKind(x, 'volume')))));
    for (const v of vols) add(v, 0);
    for (const pg of pages) { add(pg, 0); for (const ri of regInfo) if (ri.pg === pg) add(ri.r, 0); }
    for (const { r, pg } of regInfo) { const rv = add(r, 0); link(ev, rv, mm.has(r) ? 'lkg:hasMultimodalRegion' : 'lkg:hasSourceRegion'); if (pg !== undefined) link(rv, add(pg, 0), 'dcterms:isPartOf'); }
    for (const pg of nodeObjs(e, 'dcterms:isPartOf').filter(x => isKind(x, 'page'))) link(ev, add(pg, 0), 'dcterms:isPartOf');
    for (const pg of pages) for (const v of nodeObjs(pg, 'dcterms:isPartOf').filter(x => isKind(x, 'volume'))) link(add(pg, 0), add(v, 0), 'dcterms:isPartOf');
  }
  // authorities of the shared nodes
  if (on('authorities')) for (const v of [...V.values()]) if ((v.col === 3 || v.col === 4) && v.n >= 0) for (const p of MATCH.concat(['owl:sameAs'])) for (const x of nodeObjs(v.n, p)) link(v, add(x, 5), p);
  if (on('provenance')) for (const v of [...V.values()]) if (v.kind === 'run') {
    for (const x of nodeObjs(v.n, 'prov:wasAssociatedWith')) link(v, add(x, 1, { bottom: true }), 'prov:wasAssociatedWith');
    for (const x of nodeObjs(v.n, 'prov:used')) link(v, add(x, 1, { bottom: true }), 'prov:used');
  }
  return { V, E: [...E.values()], e };
}
function nodeText(v) {
  if (v.kind === 'miss' || v.kind === 'gone') return v.label;   // [GC]
  if (v.kind === 'group') return `▸ ${v.label} · ${t('obs_n', v.members.length)}`;
  if (v.kind === 'ghead') return `▾ ${v.label} · ${t('obs_n', v.members.length)}`;
  if (v.kind === 'auth') { const pl_ = pref(v.n, 'skos:prefLabel') || pref(v.n, 'rdfs:label'); return pl_ || authId(v.n); }
  if (v.kind === 'page') { const i = pref(v.n, 'dcterms:identifier') || ''; const side = /_([LR])$/.exec(i); return (label(v.n).replace(/\s*\([^)]*\)\s*$/, '') || i) + (side ? ' ' + side[1] : ''); }
  return label(v.n);
}
function nodeSub(v) {
  if (v.kind === 'miss' || v.kind === 'gone') return v.sub || '';   // [GC]
  if (v.kind === 'entry') { const r = entryRec(v.n); return `${r.id} · ${rvEntryCount(r)}`; }   // [GC] "n von m" under a corpus filter
  if (v.kind === 'auth') return (pref(v.n, 'skos:prefLabel') || pref(v.n, 'rdfs:label')) ? authId(v.n) : schemeName(v.n);
  if (v.kind === 'taxon') return pref(v.n, 'dwc:scientificName') || '';
  if (v.kind === 'group') { const tx = uniq(v.members.map(o => node1(o, 'lkg:observedTaxon'))).length; return t('taxa_n', tx); }
  return '';
}
function layoutSub(sub) {
  const { V, E } = sub; const all = [...V.values()];
  const nb = new Map(all.map(v => [v.key, []]));
  for (const ed of E) { nb.get(ed.a.key).push(ed.b); nb.get(ed.b.key).push(ed.a); }
  for (const v of all) {
    v.w = colW(v.col);   // [GC]
    v.h = v.kind === 'entry' ? 50 : v.kind === 'group' ? 36 : v.kind === 'ghead' ? 22 : (v.kind === 'taxon' || v.kind === 'auth') ? 34 : 26;
    if (v.kind === 'taxon' && !nodeSub(v)) v.h = 26;
    if (v.kind === 'auth' && !(pref(v.n, 'skos:prefLabel') || pref(v.n, 'rdfs:label'))) v.h = 26;
    if ((v.kind === 'miss' || v.kind === 'gone') && v.sub) v.h = 34;   // [GC]
  }
  rvPropsLayout(sub, all);   // [GC] rows of literal statements inside the node boxes (v.rows, v.hh = header height, v.h)
  const cols = new Map(); for (const v of all) { if (!cols.has(v.col)) cols.set(v.col, []); cols.get(v.col).push(v); }
  const stack = (list, y0) => { let y = y0; for (const v of list) { v.y = y; y += v.h + NGAP; } return y - NGAP; };
  const center = v => v.y + (v.hh || v.h) / 2;   // [GC] edges meet the header of a node
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  // col 2: records in insertion order
  const c2 = (cols.get(2) || []).sort((a, b) => a.ord - b.ord);
  let y2end = stack(c2, 0);
  const ev = V.get('n' + sub.e);
  const mid2 = c2.length ? (c2[0].y + y2end) / 2 : 0;
  ev.y = S.layers.props && c2.length ? c2[0].y : mid2 - ev.h / 2;   // [GC] with property rows the entry stands at the top, next to its first record
  // col 1: entry, then provenance nodes below
  const c1rest = (cols.get(1) || []).filter(v => v !== ev);
  stack(c1rest, Math.max(ev.y + ev.h + 60, y2end - c1rest.length * (26 + NGAP)));
  // barycentre placement with overlap removal
  const place = (list, ref) => {
    for (const v of list) { const ys = nb.get(v.key).filter(ref).map(center); v.bary = ys.length ? mean(ys) : center(ev); }
    list.sort((a, b) => a.bary - b.bary || a.ord - b.ord);
    let y = -Infinity; for (const v of list) { v.y = Math.max(v.bary - (v.hh || v.h) / 2, y); y = v.y + v.h + NGAP; }   // [GC] header at the barycentre
    if (list.length) { const d = mean(list.map(v => center(v) - v.bary)); for (const v of list) v.y -= d; }
  };
  const c0 = (cols.get(0) || []).sort((a, b) => a.ord - b.ord);
  if (c0.length) { const h = c0.reduce((s_, v) => s_ + v.h + NGAP, -NGAP); stack(c0, center(ev) - h / 2); }
  place(cols.get(3) || [], w => w.col === 2);
  place(cols.get(4) || [], w => w.col < 4);
  place(cols.get(5) || [], w => w.col === 3 || w.col === 4);
  // x positions: only the columns in use
  const used = [...cols.keys()].sort((a, b) => a - b); let x = used[0] === 0 ? 70 : 24; const colX = {};
  for (const c of used) { colX[c] = x; x += colW(c) + colGap(); }
  for (const v of all) v.x = colX[v.col];
  const minY = Math.min(...all.map(v => v.y)); for (const v of all) v.y += 46 - minY;
  sub.width = x - colGap() + 30; sub.height = Math.max(...all.map(v => v.y + v.h)) + 40; sub.colX = colX; sub.used = used; sub.nb = nb;
}
const EDGE_CLS = p => {
  if (p === 'rv:missing' || p === 'rv:removed') return 'ghost';   // [GC]
  if (p === 'skos:exactMatch' || p === 'owl:sameAs') return 'exact'; if (p === 'skos:closeMatch') return 'close'; if (p === 'skos:broadMatch') return 'broad';
  if (p === 'lkg:observedTaxon' || p === 'dwciri:toTaxon') return 'taxon';
  if (PLACE_PREDS.includes(p)) return 'place';
  if (p === 'dwciri:recordedBy' || subPropOf(p, 'lkg:mentionsPerson') || p === 'schema:mentions') return 'person';
  if (p === 'dwciri:habitat') return 'habitat';
  if (p === 'lkg:hasWeather' || p === 'lkg:containsTravelEvent' || p === 'lkg:hasLeg') return 'detail';
  if (p === 'lkg:hasSourceRegion' || p === 'lkg:hasMultimodalRegion' || p === 'dcterms:isPartOf') return 'archive';
  if (p === 'lkg:containsObservation' || p === 'dcterms:hasPart') return 'part';
  if (p.startsWith('prov:')) return 'prov';
  return 'other';
};
const ARROW = c => (c === 'exact' || c === 'close' || c === 'broad' ? 'auth' : c);
const measureCtx = document.createElement('canvas').getContext('2d');
function fitText(s, w, font) {
  measureCtx.font = font || '11.5px "Segoe UI", system-ui, sans-serif';
  if (measureCtx.measureText(s).width <= w) return s;
  let lo = 0, hi = s.length; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (measureCtx.measureText(s.slice(0, m) + '…').width <= w) lo = m; else hi = m - 1; }
  return s.slice(0, lo) + '…';
}
function edgeGeom(a, b) {
  const y1 = a.y + (a.hh || a.h) / 2, y2 = b.y + (b.hh || b.h) / 2;   // [GC]
  if (a.col === b.col) {
    const x = a.x, d = 26 + Math.min(70, Math.abs(y2 - y1) * 0.22);
    return { d: `M${x},${y1} C${x - d},${y1} ${x - d},${y2} ${x},${y2 + (y2 > y1 ? -3 : 3)}`, mx: x - d * 0.75, my: (y1 + y2) / 2 };
  }
  const fwd = b.col > a.col; const x1 = fwd ? a.x + a.w : a.x, x2 = fwd ? b.x : b.x + b.w;
  const dx = Math.max(40, Math.abs(x2 - x1) * 0.45) * (fwd ? 1 : -1);
  return { d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
}
function renderGraph(keepView) {
  const sub = buildSub(S.e); layoutSub(sub); SUB = sub;
  const svg = $('#gsvg'); const { V, E } = sub;
  const allE = E.map((ed, i) => Object.assign(ed, { i, cls: EDGE_CLS(ed.p), g: edgeGeom(ed.a, ed.b) }));
  const fanIn = new Map(); for (const ed of allE) if (ed.a.col === 2) fanIn.set(ed.b.key, (fanIn.get(ed.b.key) || 0) + 1);
  // which edge labels to show
  const showAll = S.labels === 'all' || (S.labels === 'auto' && allE.length <= 45);
  const shown = new Set();
  if (S.labels !== 'none') {
    if (showAll) allE.forEach(ed => shown.add(ed.i));
    else {
      const byP = new Map(); for (const ed of allE) { if (!byP.has(ed.p)) byP.set(ed.p, []); byP.get(ed.p).push(ed); }
      for (const [, list] of byP) { list.sort((a, b) => a.g.my - b.g.my); let last = -1e9; for (const ed of list) if (ed.g.my - last > 300) { shown.add(ed.i); last = ed.g.my; } }
    }
  }
  const heads = { 0: t('col_archive'), 1: t('col_entry'), 2: t('col_records'), 3: t('col_taxa'), 4: t('col_shared'), 5: t('col_auth') };
  let s = '<defs>' + ['part', 'taxon', 'place', 'person', 'habitat', 'detail', 'archive', 'auth', 'prov', 'other', 'ghost'].map(c => `<marker id="ar-${c}" viewBox="0 0 8 8" refX="7.2" refY="4" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0.6 L8,4 L0,7.4 z" class="arrow-${c}"/></marker>`).join('') + '</defs>';
  s += '<g id="vp">';
  s += sub.used.map(c => `<text class="colhead" x="${sub.colX[c]}" y="22">${esc(heads[c] || '')}</text>`).join('');
  s += '<g>' + allE.map(ed => `<path class="edge c-${ed.cls}${ed.a.col === 2 && ed.b.col === 4 && fanIn.get(ed.b.key) > 8 ? ' fan' : ''}" data-i="${ed.i}" d="${ed.g.d}" marker-end="url(#ar-${ARROW(ed.cls)})"${ed.count > 1 ? ` style="stroke-width:${(1.2 + Math.log2(ed.count) * 0.9).toFixed(1)}"` : ''}/>`).join('') + '</g>';
  s += '<g>' + allE.map(ed => `<text class="elbl${shown.has(ed.i) ? '' : ' hide'}" data-i="${ed.i}" x="${ed.g.mx.toFixed(1)}" y="${(ed.g.my - 3).toFixed(1)}" text-anchor="middle">${esc(pl(ed.p) + (ed.count > 1 ? ' ×' + ed.count : ''))}</text>`).join('') + '</g>';
  s += '<g>';
  for (const v of V.values()) {
    const an = rvAnn(v);   // [GC] annotation layer: what is not yet confirmed by a human (colour = level, marker = kind)
    const cls = `nd k-${v.kind}${S.sel === v.key ? ' sel' : ''}${an ? ' an an-' + an.cls + (an.strike ? ' an-gone' : '') : ''}${rvOutCls(v)}`;
    let inner = an ? rvRingSvg(v, an) : '';
    if (v.kind === 'group') inner += `<rect class="shadow" x="4" y="4" width="${v.w}" height="${v.h}" rx="7"/>`;
    const hh = v.hh || v.h;   // [GC] header height: below it the rows of the properties layer
    const rx = v.kind === 'taxon' || v.kind === 'place' || v.kind === 'person' || v.kind === 'habitat' ? 13 : 6;
    inner += `<rect class="b" width="${v.w}" height="${v.h}" rx="${Math.min(rx, hh / 2)}"${v.kind === 'entry' || v.kind === 'miss' || v.kind === 'gone' ? '' : ` style="stroke:var(--c-${kc(v.kind)})"`}/>`;
    const sub_ = nodeSub(v); const main = nodeText(v);
    const tx = v.kind === 'entry' ? 12 : 20; const tw = v.w - tx - 8 - (v.kind === 'obs' ? 24 : 0);   // room for the tier pill of a record
    if (v.kind !== 'entry') inner += `<circle class="dot" cx="10" cy="${sub_ ? 12 : hh / 2}" r="3.6" fill="var(--c-${kc(v.kind)})"/>`;
    if (v.kind === 'entry') {
      const r = entryRec(v.n);
      inner += `<text x="${tx}" y="20">${esc(fitText((r.date || '') + ' · ' + entryPlaceLabel(r), v.w - 22, '600 11.5px "Segoe UI", system-ui, sans-serif'))}</text><text class="s" x="${tx}" y="38">${esc(fitText(sub_, v.w - 22, '9.5px "Segoe UI", sans-serif'))}</text>`;
    } else if (sub_ && hh >= 30) {
      inner += `<text x="${tx}" y="15">${esc(fitText(main, tw))}</text><text class="s" x="${tx}" y="${hh - 7}">${esc(fitText(sub_, tw, '9.5px "Segoe UI", sans-serif'))}</text>`;
    } else inner += `<text x="${tx}" y="${hh / 2 + 4}">${esc(fitText(main, tw))}</text>`;
    inner += rvThumbSvg(v) + rvPropsSvg(v) + rvTierSvg(v);
    s += `<g class="${cls}" data-key="${esc(v.key)}" transform="translate(${v.x},${v.y})">${inner}${an ? rvBadgeSvg(v, an) : ''}</g>`;
  }
  s += '</g></g>';
  svg.innerHTML = s;
  svg.classList.remove('dim');
  SUB.edgeEls = $$('path.edge', svg); SUB.lblEls = $$('text.elbl', svg);
  SUB.nodeEls = new Map($$('.nd', svg).map(g => [g.dataset.key, g]));
  SUB.selDrawn = S.sel;   // [GC]
  SUB.adj = new Map(); allE.forEach(ed => { for (const k of [ed.a.key, ed.b.key]) { if (!SUB.adj.has(k)) SUB.adj.set(k, []); SUB.adj.get(k).push(ed); } });
  if (!keepView) fitView(); else applyZ();
}
// ---- pan / zoom
const Z = { k: 1, x: 0, y: 0 };
function applyZ() { const vp = $('#vp'); if (vp) vp.setAttribute('transform', `translate(${Z.x.toFixed(1)},${Z.y.toFixed(1)}) scale(${Z.k.toFixed(4)})`); rvPanHint(); thumbsSoon(); }   // [GC]
function fitView(whole) {   // [GC] whole = the ⤢ button: the complete width, however small
  if (!SUB) return; const c = $('#gcanvas'); const W = c.clientWidth || 800, H = c.clientHeight || 600;
  let k = Math.min(W / SUB.width, H / SUB.height, 1.1);
  if (k < 0.62) k = clamp(Math.min(W / SUB.width, 1), 0.45, 1);
  if (S.layers.props) k = whole === true ? clamp(Math.min(W / SUB.width, 1.1), 0.3, 1.1) : Math.max(k, Math.min(1, 0.8));   // [GC] property rows stay legible; pan for the rest
  Z.k = k; Z.x = Math.max(8, (W - SUB.width * k) / 2);
  if (SUB.height * k <= H) Z.y = (H - SUB.height * k) / 2;
  else if (S.layers.props) Z.y = 6;
  else { const ev = SUB.V.get('n' + S.e); Z.y = Math.min(10, H / 2 - (ev.y + ev.h / 2) * k); }
  applyZ();
}
function zoomAt(mx, my, f) { const k2 = clamp(Z.k * f, 0.12, 3); Z.x = mx - (mx - Z.x) * k2 / Z.k; Z.y = my - (my - Z.y) * k2 / Z.k; Z.k = k2; applyZ(); }
function centerOn(key) {
  if (!SUB) return; const v = SUB.V.get(key); if (!v) return; const c = $('#gcanvas');
  const W = c.clientWidth, H = c.clientHeight; const px = Z.x + (v.x + v.w / 2) * Z.k, py = Z.y + (v.y + v.h / 2) * Z.k;
  if (px < 40 || px > W - 40 || py < 40 || py > H - 40) { Z.x = W / 2 - (v.x + v.w / 2) * Z.k; Z.y = H / 2 - (v.y + v.h / 2) * Z.k; applyZ(); }
}
function revealNode(key) { // expand the group that hides an observation
  if (!key.startsWith('n')) return; const n = +key.slice(1); if (!isKind(n, 'obs')) return;
  for (const v of SUB.V.values()) if (v.kind === 'group' && v.members.includes(n)) { S.expanded.add(v.gkey); renderGraph(true); return; }
}
function highlight(key) {
  const svg = $('#gsvg'); if (!SUB) return;
  if (!key) { svg.classList.remove('dim'); $$('.hl', svg).forEach(x => x.classList.remove('hl')); return; }
  svg.classList.add('dim');
  const el = SUB.nodeEls.get(key); if (el) el.classList.add('hl');
  const eds = SUB.adj.get(key) || [];
  for (const ed of eds) {
    SUB.edgeEls[ed.i].classList.add('hl'); if (eds.length <= 60) SUB.lblEls[ed.i].classList.add('hl');
    const o = SUB.nodeEls.get(ed.a.key === key ? ed.b.key : ed.a.key); if (o) o.classList.add('hl');
  }
}
function tipHtml(v) {
  let h = `<div class="k">${esc(kindLabel(v.kind))}</div><div>${esc(v.n < 0 ? v.label : label(v.n))}</div>`;
  if (v.kind === 'obs') {
    const bits = [pref(v.n, 'dwc:eventDate'), cv('lkg:recordType', pref(v.n, 'lkg:recordType') || ''), nodeObjs(v.n, 'dwciri:recordedBy').map(label).join(', ')].filter(Boolean);
    const vn = pref(v.n, 'lkg:verbatimNotes'); h += `<div class="muted">${esc(bits.join(' · '))}</div>` + (vn ? `<div style="font-style:italic">„${esc(vn.slice(0, 200))}“</div>` : '');
  } else if (v.kind === 'group') {
    h += `<div class="muted">${esc(uniq(v.members.map(o => label(node1(o, 'lkg:observedTaxon')))).slice(0, 14).join(', '))}${v.members.length > 14 ? ' …' : ''}</div>`;
  } else if (v.n >= 0) {
    const sub = nodeSub(v); if (sub) h += `<div class="muted">${esc(sub)}</div>`;
    h += `<div class="iri">${esc(G.nodes[v.n])}</div>`;
  }
  return h + rvTipHtml(v);   // [GC]
}
function selectKey(key, opts = {}) {
  S.sel = key;
  if (SUB) for (const [k, el] of SUB.nodeEls) el.classList.toggle('sel', k === key);
  setHashQuiet(entryHash(S.e, key));
  if (opts.tab) S.tab = opts.tab;
  rvOnSelect(key, opts);   // [GC] card focus, table row, line on the scan
  propsSelSync();   // [GC] compact properties: the selected node shows its full rows
  renderPanel();
  if (opts.center) centerOn(key);
}

// ---- panel
function renderPanel() {   // [GC] tabs: check (cards), text, node
  if (!['check', 'text', 'node'].includes(S.tab)) S.tab = 'check';
  $$('#ptabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
  const body = $('#pbody'); const e = S.e;
  if (S.tab === 'check') rvRenderCheck(body);
  else if (S.tab === 'text') { const keep = body.dataset.tab === 'text' && body.dataset.e === String(e) ? body.scrollTop : -1; body.innerHTML = panelText(e); rvTextWire(body); const m = $('.fieldnotes .on', body); if (keep >= 0) body.scrollTop = keep; else if (m) m.scrollIntoView({ block: 'center' }); }
  else { const same = body.dataset.tab === 'node' && body.dataset.shown === String(S.sel); body.innerHTML = panelNode(); if (!same) body.scrollTop = 0; }   // [GC] another node starts at its top (crop, label)
  body.dataset.tab = S.tab; body.dataset.e = String(e); body.dataset.shown = String(S.sel);
}
function kv(rows) { return '<div class="kv">' + rows.filter(r => r[1] != null && r[1] !== '').map(([k, v]) => `<div class="k">${esc(k)}</div><div>${v}</div>`).join('') + '</div>'; }
const nlink = n => `<span class="link" data-n="${n}">${esc(label(n))}</span>`;
function panelText(e) {
  const r = entryRec(e); const pages = entryPages(e);
  let s = rvTextBlock(e);   // [GC] entry text first: reading corrections inline, record passages, free text correction
  s += `<h3 class="sec">${esc(kindLabel('entry'))}</h3><div class="iri">${esc(iriOf(e))} <span class="link" data-copy="${esc(iriOf(e))}">⧉</span></div>`;
  s += kv([[t('id'), esc(r.id)], [t('date'), esc(litsOf(e, 'dwc:eventDate').join(' · '))], [t('v_date'), esc(pref(e, 'dwc:verbatimEventDate'))],
    [t('place'), nodeObjs(e, 'lkg:entryPlace').map(nlink).join(', ')], [t('v_place'), esc(pref(e, 'dwc:verbatimLocality'))],
    [t('kind'), esc(litsOf(e, 'lkg:entryKind').map(v => cv('lkg:entryKind', v)).join(', '))], [t('plausible'), esc(litsOf(e, 'lkg:datePlausible').join(', '))],
    [t('volume'), r.vol >= 0 ? nlink(r.vol) + ` <span class="muted">${esc(pref(r.vol, 'dcterms:temporal') || '')}</span>` : ''], [t('pages'), pages.map(nlink).join('<br>')]]);
  for (const note of litsOf(e, 'skos:note')) s += `<div class="note"><b>${t('transcript_note')}:</b> ${esc(note)}</div>`;
  const weather = nodeObjs(e, 'lkg:hasWeather');
  if (weather.length) {
    s += `<h3 class="sec">${t('weather')}</h3>`;
    for (const w of weather) s += kv([[pl('lkg:weatherVerbatim'), esc(pref(w, 'lkg:weatherVerbatim'))], [pl('lkg:skyCondition'), esc(litsOf(w, 'lkg:skyCondition').map(v => cv('lkg:skyCondition', v)).join(', '))],
      [pl('lkg:precipitation'), esc(litsOf(w, 'lkg:precipitation').map(v => cv('lkg:precipitation', v)).join(', '))], [pl('lkg:wind'), esc(litsOf(w, 'lkg:wind').join(', '))],
      [pl('lkg:temperatureValue'), esc(litsOf(w, 'lkg:temperatureValue').join(', ') + (pref(w, 'lkg:temperatureUnit') ? ' ' + cv('lkg:temperatureUnit', pref(w, 'lkg:temperatureUnit')) : ''))], ['', nlink(w)]]);
  }
  const travel = nodeObjs(e, 'lkg:containsTravelEvent');
  if (travel.length) {
    s += `<h3 class="sec">${t('travel')}</h3>`;
    for (const tr of travel) {
      s += `<div style="margin-bottom:6px">${nlink(tr)}</div><table class="t"><tr><th>${t('legs')}</th><th>${pl('lkg:transportMode')}</th><th>${pl('lkg:departureTime')}</th><th>${pl('lkg:arrivalTime')}</th></tr>`;
      for (const leg of nodeObjs(tr, 'lkg:hasLeg')) s += `<tr class="click" data-n="${leg}" title="${esc(pref(leg, 'skos:note') || '')}"><td>${esc(legLabel(leg))}</td><td>${esc(litsOf(leg, 'lkg:transportMode').map(v => cv('lkg:transportMode', v)).join(', '))}</td><td class="num">${esc((pref(leg, 'lkg:departureTime') || '').replace('T', ' ').slice(0, 16))}</td><td class="num">${esc((pref(leg, 'lkg:arrivalTime') || '').replace('T', ' ').slice(0, 16))}</td></tr>`;
      s += '</table>';
    }
  }
  const persons = new Map();
  for (let i = G.sOff[e], end = G.sOff[e + 1]; i < end; i++) { const p = G.preds[G.tP[i]], x = G.tO[i]; if (x >= 0 && subPropOf(p, 'lkg:mentionsPerson')) { if (!persons.has(x)) persons.set(x, new Set()); persons.get(x).add(p); } }
  if (persons.size) {
    s += `<h3 class="sec">${t('persons_m')}</h3>`;
    s += kv([...persons].map(([x, ps]) => { const sp = [...ps].filter(p => p !== 'lkg:mentionsPerson'); return [(sp.length ? sp : [...ps]).map(pl).join(', '), nlink(x)]; }));
  }
  const mm = nodeObjs(e, 'lkg:hasMultimodalRegion');
  if (mm.length) {
    s += `<h3 class="sec">${t('mm_regions')}</h3>`;
    for (const m of mm) {
      const vt = pref(m, 'lkg:visibleText'); const img = nodeObjs(m, 'schema:image').map(iriOf).concat(litsOf(m, 'schema:image'))[0];
      s += `<div style="margin-bottom:10px">${nlink(m)} · ${esc(cv('lkg:regionKind', pref(m, 'lkg:regionKind') || ''))} · <span class="muted">${esc(nodeObjs(m, 'dcterms:type').map(label).join(', '))}</span>
        ${pref(m, 'dcterms:description') ? `<div class="muted" style="font-size:.8rem">${esc(pref(m, 'dcterms:description'))}</div>` : ''}
        ${img ? `<img src="${esc(img)}" alt="" style="max-width:100%;margin-top:4px">` : ''}
        ${vt ? `<details class="vt"><summary>${t('visible_text')} (${fmt(vt.length)})</summary><pre>${esc(vt)}</pre></details>` : ''}
        <div class="iri">${esc(pref(m, 'dcterms:identifier') || '')}</div></div>`;
    }
  }
  return s;
}
function entryPages(e) {
  const pages = nodeObjs(e, 'dcterms:isPartOf').filter(x => isKind(x, 'page'));
  for (const r of nodeObjs(e, 'lkg:hasSourceRegion').concat(nodeObjs(e, 'lkg:hasMultimodalRegion'))) for (const p of nodeObjs(r, 'dcterms:isPartOf')) if (isKind(p, 'page')) pages.push(p);
  const u = uniq(pages); const first = u[0];
  return [first].concat(u.slice(1).sort((a, b) => coll.compare(pref(a, 'dcterms:identifier') || '', pref(b, 'dcterms:identifier') || ''))).filter(x => x !== undefined);
}
// [GC] the explorer's records tab is replaced by the editable records table in the middle (gc_views.js)
function scanSources(pid, size) {   // [GC] size of the Drive thumbnail; --image-base-url first
  const sc = G.meta.scans || {}; const id = sc.drive && sc.drive[pid];
  const dr = id ? 'https://drive.google.com/thumbnail?id=' + encodeURIComponent(id) + '&sz=w' + (size || 1600) : null;
  const lo = sc.local ? sc.local.replace(/\/$/, '') + '/' + encodeURIComponent(pid) + '.jpg' : null;
  const ba = sc.base ? sc.base + '/pages/' + encodeURIComponent(pid) + '.jpg' : null;
  return { list: [ba].concat(sc.mode === 'local' ? [lo, dr] : [dr, lo]).filter(Boolean), view: id ? 'https://drive.google.com/file/d/' + encodeURIComponent(id) + '/view' : null, local: lo, base: ba };
}
// [GC] the explorer's scans tab is replaced by the persistent scan pane (gc_scan.js)
function panelNode() {
  if (!S.sel) return `<p class="muted">${t('node_hint')}</p>` + nodeDetails(S.e, { incomingMax: 6 });
  if (S.sel.startsWith('g:') || S.sel.startsWith('h:')) {
    const v = SUB && SUB.V.get(S.sel); if (!v) return '';
    return `<div><span class="kbadge k-c-rec">${t('k_group')}</span></div><h2 class="nt">${esc(v.label)}</h2><h3 class="sec">${t('members')} (${v.members.length})</h3><table class="t">` +
      v.members.map(o => `<tr class="click" data-sel="${o}"><td>${esc(label(o))}</td><td class="muted">${esc(pref(o, 'lkg:verbatimNotes') || '')}</td></tr>`).join('') + '</table>';
  }
  return nodeDetails(+S.sel.slice(1), { incomingMax: 12 });
}
function valueHtml(p, o) {
  if (o < 0) {
    const l = -o - 1; const v = G.lits[l]; const dt = G.dts[G.litDt[l]], lg = G.langs[G.litLang[l]];
    const voc = G.meta.vocab[p] && G.meta.vocab[p][v];
    const meta = (lg ? `<span class="lit-meta">@${esc(lg)}</span>` : '') + (dt && dt !== 'xsd:string' ? `<span class="lit-meta">${esc(dt)}</span>` : '');
    if (voc) return `${esc(voc[LANG] || voc.en || v)}<span class="cv-raw">${esc(v)}</span>`;
    if (/^https?:\/\//.test(v)) return `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>${meta}`;
    if (v.length > 400) return `<details class="vt"><summary>${esc(v.slice(0, 160))} … (${fmt(v.length)})</summary><pre>${esc(v)}</pre></details>${meta}`;
    return `<span style="white-space:pre-wrap">${esc(v)}</span>${meta}`;
  }
  const k = kindOf(o);
  if (k === 'term' || k === 'scheme') return `<span title="${esc(iriOf(o))}">${esc(G.meta.labels[G.nodes[o]] ? clsLabel(G.nodes[o]) : label(o))}</span> <span class="iri">${esc(G.nodes[o])}</span>`;
  const url = extUrl(o);
  let s = `<span class="link" data-n="${o}">${esc(label(o))}</span> <span class="kbadge k-c-${kc(k)}">${esc(kindLabel(k))}</span>`;
  if (k === 'auth' && authId(o) !== label(o)) s += ` <span class="muted">${esc(authId(o))}</span>`;
  if (url) s += ` <a href="${esc(url)}" target="_blank" rel="noopener" title="${esc(iriOf(o))}">↗</a>`;
  return s;
}
function nodeDetails(n, opts = {}) {
  const k = kindOf(n); const url = extUrl(n);
  let s = `<div><span class="kbadge k-c-${kc(k)}">${esc(kindLabel(k))}</span></div><h2 class="nt">${esc(label(n))}</h2>
    <div class="iri">${esc(iriOf(n))} <span class="link" data-copy="${esc(iriOf(n))}" title="${t('copy_iri')}">⧉</span></div><div class="btnrow">`;
  if (!opts.page && k !== 'entry' && k !== 'obs') s += `<button class="btn" data-go="/n/${esc(G.nodes[n])}">${t('open_node')}</button>`;
  if (opts.page && entryOf(n) >= 0) s += `<button class="btn" data-go="${esc(entryHash(entryOf(n), 'n' + n))}">${t('open_entry')}</button>`;
  if (url) s += `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener">${t('open_ext')} ↗</a>`;
  s += '</div>';
  s += rvNodeExtra(n, opts);   // [GC] the crop of a multimodal region
  // outgoing statements grouped by predicate
  const groups = new Map();
  for (let i = G.sOff[n], end = G.sOff[n + 1]; i < end; i++) { const p = G.preds[G.tP[i]]; if (!groups.has(p)) groups.set(p, []); groups.get(p).push(G.tO[i]); }
  const order = [...groups.keys()].sort((a, b) => (a === 'rdf:type' ? -1 : b === 'rdf:type' ? 1 : 0));
  s += `<h3 class="sec">${t('statements')} (${G.sOff[n + 1] - G.sOff[n]})</h3><table class="t trip">` +
    order.map(p => { const vs = groups.get(p); const cap = 60;
      return `<tr><td title="${esc(p + (G.meta.defs[p] ? ' — ' + G.meta.defs[p] : ''))}">${esc(pl(p))}${vs.length > 1 ? ` <span class="muted">(${fmt(vs.length)})</span>` : ''}</td><td>${vs.slice(0, cap).map(o => valueHtml(p, o)).join('<br>')}${vs.length > cap ? `<br><span class="muted">${t('more', fmt(vs.length - cap))}</span>` : ''}</td></tr>`; }).join('') + '</table>';
  if (opts.incomingMax !== 0) {
    const inc = new Map();
    for (let i = G.inOff[n], end = G.inOff[n + 1]; i < end; i++) { const p = G.preds[G.inP[i]]; if (!inc.has(p)) inc.set(p, []); inc.get(p).push(G.inS[i]); }
    if (inc.size) {
      const mx = opts.incomingMax || 12;
      s += `<h3 class="sec">${t('incoming')} (${fmt(G.inOff[n + 1] - G.inOff[n])})</h3><table class="t trip">` +
        [...inc].map(([p, ss]) => `<tr><td>${esc(pl(p))} <span class="muted">(${fmt(ss.length)})</span></td><td>${ss.slice(0, mx).map(x => `<span class="link" data-n="${x}">${esc(label(x))}</span>`).join(' · ')}${ss.length > mx ? ` <span class="muted">${t('more', fmt(ss.length - mx))}</span>` : ''}</td></tr>`).join('') + '</table>';
    }
  }
  return s;
}

// ------------------------------------------------------------------ node view
const NV = { n: -1, page: 0, sort: ['date', 1], pred: '', q: '' };
function usageRows(n) {
  if (NV.rows && NV.rowsFor === n + LANG + RVU.corpus) return NV.rows;
  const rows = [];
  for (let i = G.inOff[n], end = G.inOff[n + 1]; i < end; i++) {
    const s = G.inS[i], p = G.preds[G.inP[i]]; const k = kindOf(s);
    if (!rvSrcOk(s)) continue;   // [GC] only records and entries of the chosen corpus
    const e = k === 'entry' ? s : entryOf(s); const er = e >= 0 ? entryRec(e) : null;
    let date = '', place = '', count = '';
    if (k === 'obs') { date = pref(s, 'dwc:eventDate') || (er ? er.date : ''); const loc = node1(s, 'lkg:hasLocality'); const at = node1(s, 'lkg:observedAt'); place = label(loc >= 0 ? loc : at); count = countStr(s); }
    else if (er) { date = er.date; place = entryPlaceLabel(er); }
    rows.push({ s, p, k, e, id: er ? er.id : '', date, place, count, lab: label(s) });
  }
  NV.rows = rows; NV.rowsFor = n + LANG + RVU.corpus; return rows;
}
function showNode(n) {
  setView('node');
  if (NV.n !== n) { NV.n = n; NV.page = 0; NV.pred = ''; NV.q = ''; NV.sort = ['date', 1]; NV.rows = null; }
  const v = $('#v-node'); const k = kindOf(n);
  const rows = usageRows(n);
  // observations using this node → places, years, months
  const obsRows = rows.filter(r => r.k === 'obs');
  const yCount = new Map(), mCount = new Array(12).fill(0);
  for (const r of rows) { const y = +String(r.date).slice(0, 4); if (y) yCount.set(y, (yCount.get(y) || 0) + 1); const m = +String(r.date).slice(5, 7); if (m >= 1 && m <= 12 && r.k === 'obs') mCount[m - 1]++; }
  const ySpan = yearSpan([yCount]); const yItems = [];
  for (let y = ySpan.y0; y <= ySpan.y1; y++) yItems.push({ l: String(y), v: yCount.get(y) || 0 });
  const mNames = t('months').split(',');
  let pts = [];
  if (k === 'place') { const c = coords(n); if (c) pts = [{ la: c[0], lo: c[1], r: 7, label: label(n), unc: parseFloat(pref(n, 'dwc:coordinateUncertaintyInMeters')) || 0 }]; }
  else {
    const pc = new Map();
    for (const r of rows) {
      let pls = [];
      if (r.k === 'obs') { const loc = node1(r.s, 'lkg:hasLocality'); const at = node1(r.s, 'lkg:observedAt'); pls = [loc >= 0 ? loc : at]; }
      else if (r.k === 'entry') pls = [node1(r.s, 'lkg:entryPlace')];
      for (const p of pls) if (p >= 0) pc.set(p, (pc.get(p) || 0) + 1);
    }
    const mx = Math.max(1, ...pc.values());
    for (const [p, c] of pc) { const cc = coords(p); if (cc) pts.push({ la: cc[0], lo: cc[1], r: 3 + 10 * Math.sqrt(c / mx), label: `${label(p)} · ${fmt(c)}`, go: '/n/' + G.nodes[p] }); }
  }
  const hasMap = pts.length > 0 && (k === 'place' || rows.length > 0);
  v.innerHTML = `<div class="page"><div class="grid2">
    <div class="card">${rvFilterNote(true)}${nodeDetails(n, { page: true, incomingMax: 0 })}</div>
    <div>
      <div class="card star"><h3>${t('neighbourhood')}</h3>${starSvg(n, rows)}</div>
      ${hasMap ? `<div class="card" style="margin-top:16px"><h3>${k === 'place' ? t('map') : t('dist_map', fmt(pts.length))}</h3><div class="map small" id="nv-map"></div></div>` : ''}
      ${yItems.length > 1 ? `<div class="card cols" style="margin-top:16px"><h3>${t('per_year_t')}</h3>${colChart(yItems, kc(k) === 'other' ? 'rec' : kc(k))}${ySpan.note ? `<div class="muted" style="font-size:.74rem">${esc(ySpan.note)}</div>` : ''}</div>` : ''}
      ${obsRows.length > 1 && k !== 'obs' ? `<div class="card cols" style="margin-top:16px"><h3>${kindLabel('obs')} · ${t('per_month_t')}</h3>${colChart(mCount.map((c, i) => ({ l: mNames[i], v: c })), 'rec', { every: 1 })}</div>` : ''}
    </div></div>
    <div class="card" style="margin-top:16px" id="nv-usage"></div></div>`;
  renderUsage();
  if (hasMap) makeMap($('#nv-map'), pts, { unc: true, zoom: 11 });
}
function starSvg(n, rows) {
  const inc = new Map(); for (const r of rows) inc.set(r.p, (inc.get(r.p) || 0) + 1);
  const out = []; for (let i = G.sOff[n], end = G.sOff[n + 1]; i < end; i++) { const o = G.tO[i]; const p = G.preds[G.tP[i]]; if (o >= 0 && p !== 'rdf:type') out.push([p, o]); }
  const left = [...inc].sort((a, b) => b[1] - a[1]); const right = out.slice(0, 16);
  const lh = 30, rh = 38, W = 720, cw = 170, lw = 190, rw = 230;
  const H = Math.max(left.length * lh, right.length * rh, 40) + 16, cx = W / 2, cy = H / 2;
  const edgeColor = p => { const c = EDGE_CLS(p); return c === 'part' ? 'rec' : (c === 'exact' || c === 'close' || c === 'broad') ? 'auth' : c; };
  let s = `<svg viewBox="0 0 ${W} ${H}" style="max-height:${H}px">`;
  const k = kindOf(n);
  const ly0 = cy - left.length * lh / 2, ry0 = cy - right.length * rh / 2;
  left.forEach(([p, c], i) => {
    const y = ly0 + i * lh + lh / 2;
    s += `<path class="edge c-${EDGE_CLS(p)}" d="M${4 + lw},${y} C${cx - 70},${y} ${cx - cw / 2 - 30},${cy} ${cx - cw / 2},${cy}"/>`;
    s += `<g class="nd" data-filter="${esc(p)}"><rect class="b" x="4" y="${y - 12}" width="${lw}" height="24" rx="6" style="stroke:var(--c-${edgeColor(p)})"/><text x="12" y="${y + 4}">${esc(fitText(`${fmt(c)} × ${pl(p)}`, lw - 16))}</text><title>${esc(p)} — ${esc(t('usage', fmt(c)))}</title></g>`;
  });
  right.forEach(([p, o], i) => {
    const y = ry0 + i * rh + rh / 2; const ok = kindOf(o); const x0 = W - 4 - rw;
    s += `<path class="edge c-${EDGE_CLS(p)}" d="M${cx + cw / 2},${cy} C${cx + cw / 2 + 30},${cy} ${x0 - 50},${y} ${x0},${y}"/>`;
    s += `<g class="nd" data-n="${o}"><rect class="b" x="${x0}" y="${y - 16}" width="${rw}" height="32" rx="6" style="stroke:var(--c-${kc(ok)})"/>` +
      `<text class="s" x="${x0 + 8}" y="${y - 4}">${esc(fitText(pl(p), rw - 16, '9.5px "Segoe UI", sans-serif'))}</text>` +
      `<text x="${x0 + 8}" y="${y + 10}">${esc(fitText((ok === 'auth' ? authId(o) + (label(o) !== authId(o) ? ' · ' + label(o) : '') : label(o)), rw - 16))}</text><title>${esc(pl(p) + ' → ' + iriOf(o))}</title></g>`;
  });
  s += `<g class="nd k-${k}"><rect class="b" x="${cx - cw / 2}" y="${cy - 17}" width="${cw}" height="34" rx="12" style="stroke:var(--c-${kc(k)});stroke-width:2.4"/><text x="${cx}" y="${cy + 4}" text-anchor="middle" style="font-weight:600">${esc(fitText(label(n), cw - 20, '600 11.5px "Segoe UI", sans-serif'))}</text></g>`;
  return s + '</svg>';
}
function renderUsage() {
  const n = NV.n; const box = $('#nv-usage'); if (!box) return;
  let rows = usageRows(n);
  const preds = uniq(rows.map(r => r.p));
  if (NV.pred) rows = rows.filter(r => r.p === NV.pred);
  if (NV.q) { const q = NV.q.toLowerCase(); rows = rows.filter(r => (r.lab + ' ' + r.id + ' ' + r.date + ' ' + r.place).toLowerCase().includes(q)); }
  const [k, dir] = NV.sort;
  rows = rows.slice().sort((a, b) => { const x = a[k] || '', y = b[k] || ''; return (x < y ? -1 : x > y ? 1 : 0) * dir || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0); });
  const per = 50, pages = Math.max(1, Math.ceil(rows.length / per)); NV.page = clamp(NV.page, 0, pages - 1);
  const slice = rows.slice(NV.page * per, NV.page * per + per);
  const th = (c, l) => `<th class="sort" data-usort="${c}">${esc(l)}${k === c ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`;
  box.innerHTML = `<h3>${t('usage', fmt(usageRows(n).length))}</h3>
    <div class="pager"><select id="nv-pred"><option value="">${t('all_preds')}</option>${preds.map(p => `<option value="${esc(p)}" ${p === NV.pred ? 'selected' : ''}>${esc(pl(p))} (${fmt(usageRows(n).filter(r => r.p === p).length)})</option>`).join('')}</select>
      <input id="nv-q" type="search" placeholder="${t('filter')}" value="${esc(NV.q)}">
      <button class="btn" data-upage="-1" ${NV.page <= 0 ? 'disabled' : ''}>◀</button><span>${t('page_n', NV.page + 1, pages)} · ${fmt(rows.length)}</span><button class="btn" data-upage="1" ${NV.page >= pages - 1 ? 'disabled' : ''}>▶</button></div>
    <table class="t"><tr>${th('date', t('date'))}${th('id', t('entry'))}${th('p', t('pred'))}${th('lab', t('record'))}${th('count', t('r_count'))}${th('place', t('place'))}</tr>
    ${slice.map(r => `<tr class="click" data-go="${esc(r.e >= 0 ? entryHash(r.e, r.k === 'entry' ? null : 'n' + r.s) : '/n/' + G.nodes[r.s])}"><td class="num">${esc(r.date)}</td><td class="mono" style="font-size:.76rem">${esc(r.id)}</td><td>${esc(pl(r.p))}</td><td><span class="kbadge k-c-${kc(r.k)}">${esc(kindLabel(r.k))}</span> ${esc(r.lab)}</td><td class="num">${esc(r.count)}</td><td>${esc(r.place)}</td></tr>`).join('')}</table>`;
}

// ------------------------------------------------------------------ class view
const CV = { k: 'taxon', page: 0, sort: ['uses', -1], q: '' };
function showClass(k) {
  setView('class');
  if (CV.k !== k) { CV.k = k; CV.page = 0; CV.q = ''; CV.sort = classMode(k) === 'img' ? ['ord', 1] : ['uses', -1]; CV.rows = null; }   // [GC] images in the order of the archive
  const st = stats();
  const kinds = KIND_LIST.map((x, i) => ({ x, c: st.kc[i] })).filter(r => r.c);
  if (!CV.rows || CV.rowsFor !== k + LANG + RVU.corpus) {
    const rows = []; const ki = KI[k];
    for (let n = 0; n < G.nodes.length; n++) if (G.kind[n] === ki && rvClassOk(n, k)) {   // [GC] corpus filter
      let sub = '';
      if (k === 'taxon') sub = pref(n, 'dwc:scientificName') || ''; else if (k === 'place') { const c = coords(n); sub = c ? c[0].toFixed(4) + ', ' + c[1].toFixed(4) : ''; }
      else if (k === 'auth') sub = authId(n); else if (k === 'entry') sub = pref(n, 'dcterms:identifier') || ''; else if (k === 'obs') sub = pref(n, 'dwc:eventDate') || '';
      else if (k === 'volume') sub = pref(n, 'dcterms:temporal') || '';
      rows.push({ n, lab: label(n), sub, uses: rvUses(n), iri: G.nodes[n], ord: rvClassOrd(n, k) });
    }
    CV.rows = rows; CV.rowsFor = k + LANG + RVU.corpus;
  }
  renderClassTable(kinds);
}
function renderClassTable(kinds) {
  const v = $('#v-class'); const k = CV.k;
  let rows = CV.rows; if (CV.q) { const q = CV.q.toLowerCase(); rows = rows.filter(r => (r.lab + ' ' + r.sub + ' ' + r.iri).toLowerCase().includes(q)); }
  const [sk, dir] = CV.sort; rows = rows.slice().sort((a, b) => (sk === 'uses' ? a.uses - b.uses : coll.compare(String(a[sk]), String(b[sk]))) * dir);
  const per = rvClassPer(k), pages = Math.max(1, Math.ceil(rows.length / per)); CV.page = clamp(CV.page, 0, pages - 1);   // [GC] "Tabelle / Bilder" for classes with images
  const grid = rvClassBody(k, rows.slice(CV.page * per, CV.page * per + per));
  const th = (c, l) => `<th class="sort" data-csort="${c}">${esc(l)}${sk === c ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`;
  const hash = r => (k === 'entry' ? entryHash(r.n) : k === 'obs' && entryOf(r.n) >= 0 ? entryHash(entryOf(r.n), 'n' + r.n) : '/n/' + r.iri);
  v.innerHTML = `<div class="page"><h2>${esc(kindLabel(k))}</h2><p class="lead">${esc(KIND_CLASS[k] || '')}${rvFilterNote()}</p>
    <div class="btnrow">${(kinds || []).filter(x => !['term', 'ext', 'other', 'scheme'].includes(x.x)).map(x => `<button class="btn" data-go="/c/${x.x}" ${x.x === k ? 'style="border-color:var(--accent);font-weight:600"' : ''}>${esc(kindLabel(x.x))} (${fmt(x.c)})</button>`).join('')}</div>
    <div class="pager">${rvClassSwitch(k)}<input id="cv-q" type="search" placeholder="${t('filter')}" value="${esc(CV.q)}"><button class="btn" data-cpage="-1" ${CV.page <= 0 ? 'disabled' : ''}>◀</button><span>${t('page_n', CV.page + 1, pages)} · ${fmt(rows.length)}</span><button class="btn" data-cpage="1" ${CV.page >= pages - 1 ? 'disabled' : ''}>▶</button></div>
    <div class="card">${grid}<table class="t"${grid ? ' hidden' : ''}><tr>${th('lab', t('label'))}${th('sub', t('detail'))}${th('uses', t('uses'))}${th('iri', 'IRI')}</tr>
    ${(grid ? [] : rows.slice(CV.page * per, CV.page * per + per)).map(r => `<tr class="click" data-go="${esc(hash(r))}"><td>${esc(r.lab)}</td><td class="muted">${esc(r.sub)}</td><td class="num">${fmt(r.uses)}</td><td class="iri">${esc(r.iri)}</td></tr>`).join('')}</table></div></div>`;
  CV.kinds = kinds;
}

// ------------------------------------------------------------------ search
let SIDX = null;
function searchIndex() {
  if (SIDX && SIDX.lang === LANG) return SIDX;
  const ent = G.ent.map(r => [r.id, r.date, pref(r.n, 'dwc:verbatimEventDate'), entryPlaceLabel(r), pref(r.n, 'dwc:verbatimLocality'), volLabel(r.vol), label(r.n)].filter(Boolean).join(' | ').toLowerCase());
  const nodes = [];
  const kinds = new Set(['taxon', 'place', 'person', 'habitat', 'auth', 'volume', 'page', 'mmregion']);
  for (let n = 0; n < G.nodes.length; n++) {
    const k = kindOf(n); if (!kinds.has(k)) continue;
    const s = [label(n), ...litsOf(n, 'skos:altLabel'), pref(n, 'dwc:scientificName'), pref(n, 'skos:notation'), pref(n, 'dcterms:identifier'), G.nodes[n]].filter(Boolean).join(' | ').toLowerCase();
    nodes.push([n, k, s]);
  }
  SIDX = { lang: LANG, ent, nodes, text: null };
  return SIDX;
}
function normQuery(q) {
  q = q.trim().toLowerCase(); let m;
  if ((m = /^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/.exec(q))) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  if ((m = /^(\d{1,2})\.\s*(\d{4})$/.exec(q))) return `${m[2]}-${m[1].padStart(2, '0')}`;
  return q;
}
function runSearch(raw) {
  const q = normQuery(raw); if (!q) return null;
  const toks = q.split(/\s+/).filter(Boolean); const X = searchIndex();
  const hit = s => toks.every(tk => s.includes(tk));
  const ents = []; for (let i = 0; i < X.ent.length && ents.length < 40; i++) if (hit(X.ent[i])) ents.push(i);
  const byKind = {}; for (const [n, k, s] of X.nodes) if (hit(s)) { (byKind[k] = byKind[k] || []).push(n); }
  let text = [];
  if (q.length >= 3) {
    if (!X.text) X.text = G.ent.map(r => (pref(r.n, 'dwc:fieldNotes') || '').toLowerCase());
    const seen = new Set(ents);
    for (let i = 0; i < X.text.length && text.length < 40; i++) if (!seen.has(i) && X.text[i].includes(q)) text.push(i);
  }
  return { ents, byKind, text, q };
}
function renderSearch() {
  const box = $('#qres'); const raw = $('#q').value; const r = runSearch(raw);
  if (!r) { box.hidden = true; return; }
  const sec = (title, items) => items.length ? `<h4>${esc(title)}</h4>` + items.join('') : '';
  const entRow = i => { const e = G.ent[i]; return `<div class="r" data-go="${esc(entryHash(e.n))}"><b class="num">${esc(e.date || e.id)}</b> ${esc(entryPlaceLabel(e))}<span class="sub">${esc(e.id)} · ${esc(volLabel(e.vol))}</span></div>`; };
  const textRow = i => { const e = G.ent[i]; const tx = searchIndex().text[i]; const p = tx.indexOf(r.q); const fn = pref(e.n, 'dwc:fieldNotes') || ''; const snip = fn.slice(Math.max(0, p - 40), p + r.q.length + 50);
    return `<div class="r" data-go="${esc(entryHash(e.n))}"><b class="num">${esc(e.date || e.id)}</b><span class="sub" style="max-width:75%">… ${esc(snip)} …</span></div>`; };
  const nodeRows = (k, lim) => (r.byKind[k] || []).map(n => ({ n, u: G.inOff[n + 1] - G.inOff[n] })).sort((a, b) => b.u - a.u).slice(0, lim)
    .map(x => `<div class="r" data-go="/n/${esc(G.nodes[x.n])}">${esc(label(x.n))}<span class="sub">${esc(k === 'taxon' ? pref(x.n, 'dwc:scientificName') || '' : k === 'auth' ? authId(x.n) : '')} · ${fmt(x.u)}</span></div>`);
  const other = ['auth', 'volume', 'page', 'mmregion'].flatMap(k => nodeRows(k, 6));
  const html = sec(t('s_entries'), r.ents.slice(0, 25).map(entRow)) + sec(t('s_taxa'), nodeRows('taxon', 10)) + sec(t('s_places'), nodeRows('place', 10)) + sec(t('s_persons'), nodeRows('person', 10)) +
    sec(t('s_habitats'), nodeRows('habitat', 8)) + sec(t('s_other'), other) + sec(t('s_text'), r.text.slice(0, 25).map(textRow));
  box.innerHTML = html || `<div class="empty">${t('s_none')}</div>`;
  box.hidden = false;
  const first = $('.r', box); if (first) first.classList.add('on');
}

// ------------------------------------------------------------------ events
function wire() {
  document.addEventListener('click', ev => {
    const cp = ev.target.closest('[data-copy]'); if (cp) { copyText(cp.dataset.copy); return; }
    const nav = ev.target.closest('[data-nav]');
    if (nav) { const w = nav.dataset.nav; if (w === 'overview') go('/'); else if (w === 'classes') go('/c/' + (CV.k || 'taxon')); else { const e = S.lastEntry >= 0 ? S.lastEntry : rvFirstEntry(); if (e !== undefined) go(entryHash(e)); } return; }
    const sel = ev.target.closest('[data-sel]');
    if (sel && S.view === 'entry') { const key = 'n' + sel.dataset.sel; if (SUB && !SUB.V.has(key)) revealNode(key); selectKey(key, { center: true }); return; }
    const dn = ev.target.closest('[data-n]');
    if (dn && !ev.target.closest('#gsvg')) {
      const n = +dn.dataset.n; const key = 'n' + n;
      if (S.view === 'entry' && SUB) { if (!SUB.V.has(key)) revealNode(key); if (SUB.V.has(key)) { selectKey(key, { tab: S.tab === 'text' && isKind(n, 'obs') ? 'text' : 'node', center: true }); return; } }
      if (isKind(n, 'entry')) go(entryHash(n)); else if (isKind(n, 'obs') && entryOf(n) >= 0) go(entryHash(entryOf(n), key)); else go('/n/' + G.nodes[n]);
      return;
    }
    const g = ev.target.closest('[data-go]'); if (g && g.dataset.go) { go(g.dataset.go); return; }
    if (!ev.target.closest('#searchbox')) $('#qres').hidden = true;
  });
  // entry view controls
  rvWireList();   // [GC] work list: queues, volume filter, sort, filter, virtual rows
  $('#ehead').addEventListener('click', ev => {
    const b = ev.target.closest('[data-act]'); if (!b) return; const a = b.dataset.act;
    if (a === 'list') { S.list = !S.list; store('list', S.list ? '1' : '0'); $('#v-entry').classList.toggle('nolist', !S.list); fitView(); rvRenderList(); }
    else if (a === 'prev' || a === 'next') stepEntry(a === 'prev' ? -1 : 1);
    else rvHeadAct(a, b);
  });
  $('#gtools').addEventListener('click', ev => {
    const ch = ev.target.closest('.chip[data-layer]'); if (ch) { const l = ch.dataset.layer; S.layers[l] = !S.layers[l]; store('layers', JSON.stringify(S.layers)); renderTools(); renderGraph(false); return; }
    const b = ev.target.closest('[data-act]'); if (!b) return; const c = $('#gcanvas');
    if (b.dataset.act === 'fit') fitView(true);
    else if (b.dataset.act === 'zin') zoomAt(c.clientWidth / 2, c.clientHeight / 2, 1.25);
    else if (b.dataset.act === 'zout') zoomAt(c.clientWidth / 2, c.clientHeight / 2, 0.8);
    else if (b.dataset.act === 'expand') { for (const v of SUB.V.values()) if (v.kind === 'group') S.expanded.add(v.gkey); renderGraph(false); }
    else if (b.dataset.act === 'collapse') { S.expanded.clear(); renderGraph(false); }
    else rvHeadAct(b.dataset.act, b);   // [GC]
  });
  $('#gtools').addEventListener('change', ev => {
    if (ev.target.id === 'grpsel') { S.group = ev.target.value; store('group', S.group); S.expanded.clear(); renderGraph(false); renderPanelIfGroup(); }
    if (ev.target.id === 'lblsel') { S.labels = ev.target.value; store('labels', S.labels); renderGraph(false); }
    if (ev.target.id === 'propsel') { S.props = ev.target.value; store('props', S.props); renderGraph(false); }   // [GC]
  });
  $('#ptabs').addEventListener('click', ev => { const b = ev.target.closest('[data-tab]'); if (!b) return; S.tab = b.dataset.tab; store('tab', S.tab); renderPanel(); });
  // [GC] clicks in the panel are handled in gc_cards.js (rvWire)
  // graph interactions
  const svg = $('#gsvg'), canvas = $('#gcanvas'), tip = $('#gtip');
  let drag = null, moved = false;
  canvas.addEventListener('pointerdown', ev => { if (ev.button !== 0 || ev.target.closest('.nd')) return; drag = { x: ev.clientX, y: ev.clientY, zx: Z.x, zy: Z.y }; moved = false; canvas.classList.add('drag'); canvas.setPointerCapture(ev.pointerId); });
  canvas.addEventListener('pointermove', ev => {
    if (drag) { const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; Z.x = drag.zx + dx; Z.y = drag.zy + dy; applyZ(); return; }
    if (!tip.hidden) { const r = canvas.getBoundingClientRect(); tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 370) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; }
  });
  const endDrag = () => { drag = null; canvas.classList.remove('drag'); };
  canvas.addEventListener('pointerup', endDrag); canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('wheel', ev => {
    ev.preventDefault(); const r = canvas.getBoundingClientRect();
    if (ev.ctrlKey || ev.metaKey) zoomAt(ev.clientX - r.left, ev.clientY - r.top, Math.exp(-ev.deltaY * 0.0022));
    else { Z.x -= ev.shiftKey ? ev.deltaY : ev.deltaX; Z.y -= ev.shiftKey ? 0 : ev.deltaY; applyZ(); }
  }, { passive: false });
  svg.addEventListener('mouseover', ev => {
    const g = ev.target.closest('.nd'); if (!g || !SUB) return; highlight(null); highlight(g.dataset.key);
    const v = SUB.V.get(g.dataset.key); if (v) { tip.innerHTML = tipHtml(v); tip.hidden = false; const r = canvas.getBoundingClientRect(); tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 370) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; }
  });
  svg.addEventListener('mouseout', ev => { const g = ev.target.closest('.nd'); if (g && !(ev.relatedTarget && g.contains(ev.relatedTarget))) { highlight(null); tip.hidden = true; } });
  svg.addEventListener('click', ev => {
    if (moved) { moved = false; return; }
    const g = ev.target.closest('.nd'); if (!g || !SUB) return; const v = SUB.V.get(g.dataset.key); if (!v) return;
    if (v.kind === 'group') { S.expanded.add(v.gkey); renderGraph(true); return; }
    if (v.kind === 'ghead') { S.expanded.delete(v.gkey); renderGraph(true); return; }
    rvNodeClick(v, ev);   // [GC] opens the matching card in the check tab
  });
  svg.addEventListener('dblclick', ev => { const g = ev.target.closest('.nd'); if (!g || !SUB) return; const v = SUB.V.get(g.dataset.key); if (v && v.n >= 0 && SHARED.has(v.kind)) go('/n/' + G.nodes[v.n]); });
  // split
  const split = $('#split'); let sp = null;
  split.addEventListener('pointerdown', ev => { sp = { x: ev.clientX, w: $('#panel').getBoundingClientRect().width }; split.setPointerCapture(ev.pointerId); });
  split.addEventListener('pointermove', ev => { if (!sp) return; const w = clamp(sp.w - (ev.clientX - sp.x), 280, window.innerWidth - 420); $('#v-entry').style.setProperty('--panel-w', w + 'px'); });
  split.addEventListener('pointerup', () => { if (sp) { sp = null; store('panelw', $('#v-entry').style.getPropertyValue('--panel-w')); } });
  const pw = store('panelw'); if (pw) $('#v-entry').style.setProperty('--panel-w', pw);
  $('#v-entry').classList.toggle('nolist', !S.list);
  // node + class views
  $('#v-node').addEventListener('click', ev => {
    const th = ev.target.closest('[data-usort]'); if (th) { const k = th.dataset.usort; NV.sort = [k, NV.sort[0] === k ? -NV.sort[1] : 1]; renderUsage(); return; }
    const pg = ev.target.closest('[data-upage]'); if (pg) { NV.page += +pg.dataset.upage; renderUsage(); return; }
    const f = ev.target.closest('[data-filter]'); if (f) { NV.pred = f.dataset.filter; NV.page = 0; renderUsage(); $('#nv-usage').scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  });
  $('#v-node').addEventListener('change', ev => { if (ev.target.id === 'nv-pred') { NV.pred = ev.target.value; NV.page = 0; renderUsage(); } });
  $('#v-node').addEventListener('input', debounce(ev => { if (ev.target.id === 'nv-q') { NV.q = ev.target.value; NV.page = 0; renderUsage(); const q = $('#nv-q'); q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }, 200));
  $('#v-class').addEventListener('click', ev => {
    if (rvClassAct(ev)) return;   // [GC]
    const th = ev.target.closest('[data-csort]'); if (th) { const k = th.dataset.csort; CV.sort = [k, CV.sort[0] === k ? -CV.sort[1] : (k === 'uses' ? -1 : 1)]; renderClassTable(CV.kinds); return; }
    const pg = ev.target.closest('[data-cpage]'); if (pg) { CV.page += +pg.dataset.cpage; renderClassTable(CV.kinds); }
  });
  $('#v-class').addEventListener('input', debounce(ev => { if (ev.target.id === 'cv-q') { CV.q = ev.target.value; CV.page = 0; renderClassTable(CV.kinds); const q = $('#cv-q'); q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }, 200));
  // search
  const q = $('#q');
  q.addEventListener('input', debounce(renderSearch, 160));
  q.addEventListener('focus', () => { if (q.value.trim()) renderSearch(); });
  q.addEventListener('keydown', ev => {
    const box = $('#qres'); const rows = $$('.r', box); const i = rows.findIndex(r => r.classList.contains('on'));
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { ev.preventDefault(); if (!rows.length) return; const j = clamp(i + (ev.key === 'ArrowDown' ? 1 : -1), 0, rows.length - 1); rows.forEach((r, k) => r.classList.toggle('on', k === j)); rows[j].scrollIntoView({ block: 'nearest' }); }
    else if (ev.key === 'Enter') { renderSearch(); const on = $('.r.on', box) || $('.r', box); if (on) { go(on.dataset.go); box.hidden = true; q.blur(); } }
    else if (ev.key === 'Escape') { box.hidden = true; q.blur(); }
  });
  document.addEventListener('keydown', ev => {
    if (rvKey(ev)) return;   // [GC] J N E X U, arrows, Z, S, G, Enter
    if (ev.target && ev.target.closest && ev.target.closest('input,select,textarea')) return;
    if (ev.key === '/') { ev.preventDefault(); q.focus(); }
    else if (ev.key === 'Escape') { $('#help').hidden = true; if (S.view === 'entry' && S.sel) selectKey(null); }
  });
  // header buttons
  $('#btn-lang').addEventListener('click', () => { LANG = LANG === 'de' ? 'en' : 'de'; store('lang', LANG); SIDX = null; NV.rows = null; CV.rows = null; applyStatic(); rvLangChanged(); if (!$('#help').hidden) $('#help').innerHTML = rvHelpHtml(); route(); });
  $('#btn-theme').addEventListener('click', () => { const d = document.documentElement; d.dataset.theme = d.dataset.theme === 'dark' ? 'light' : 'dark'; store('theme', d.dataset.theme); if (S.view === 'overview') showOverview(); });
  $('#btn-help').addEventListener('click', () => { const h = $('#help'); h.innerHTML = rvHelpHtml(); h.hidden = !h.hidden; });   // [GC] with the table of levels
  $('#help').addEventListener('click', () => { $('#help').hidden = true; });
  $('#apptitle').addEventListener('click', () => go('/'));
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', debounce(() => { if (S.view === 'entry') { fitView(); rvResize(); } }, 200));
}
function renderPanelIfGroup() { if (S.sel && !S.sel.startsWith('n')) { S.sel = null; renderPanel(); } }

// ------------------------------------------------------------------ boot
async function boot() {
  const th = store('theme'); if (th === 'dark' || th === 'light') document.documentElement.dataset.theme = th;
  $('#loadmsg').textContent = t('loading');
  try {
    const t0 = performance.now();
    const { meta, A } = await loadData();
    $('#loadmsg').textContent = t('indexing', fmt(meta.triples));
    await new Promise(r => setTimeout(r, 0));
    const t1 = performance.now();
    buildIndex(meta, A);
    const t2 = performance.now();
    await rvBoot();   // [GC] review layer, stored decisions, queues
    window.LKGX.timing = { decode: Math.round(t1 - t0), index: Math.round(t2 - t1), review: Math.round(performance.now() - t2) };
  } catch (err) {
    $('#loadmsg').textContent = t('load_fail') + ': ' + err; console.error(err); return;
  }
  $('#loading').hidden = true; $('#loading').style.display = 'none'; $('#app').hidden = false;
  applyStatic(); wire(); rvWire();
  route();
  window.LKGX.ready = true;
}
// [GC] boot() is called in gc_boot.js, which also closes the function scope
