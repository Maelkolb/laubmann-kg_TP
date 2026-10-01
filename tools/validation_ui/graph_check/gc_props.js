/* Graph-Prüfung — layer "Eigenschaften": every literal statement of a node as a row inside its box
   (ontology label · value, exactly what the node tab lists), and — with the layer "übrige Aussagen" —
   every node-valued statement that has no edge in the picture ("→ target"). Nothing is hard-coded:
   the rows are the outgoing triples of the node in the graph; PROP_ORDER only sorts them.
   Many records (more than PROP_FULL): one summary line per node, full rows for the selected node
   (and in the tooltip of the hovered one); switch "kompakt / alle" (S.props). */

const PROP_FULL = 12;      // up to this many records every node shows all its rows ("auto")
const PROW = 12;           // row height
const PROPW = { 0: 204, 1: 216, 2: 244, 3: 212, 4: 212, 5: 204 };
const colW = c => (S.layers.props ? PROPW[c] || 224 : COLW[c] || 200);
const PFONT = '9.5px "Segoe UI", system-ui, sans-serif';
const NAME_PREDS = new Set(['rdfs:label', 'skos:prefLabel', 'schema:name']);
const PROP_ORDER = ['dcterms:identifier', 'dwc:eventDate', 'dwc:verbatimEventDate', 'dwc:eventTime', 'lkg:timeOfDay', 'dwc:verbatimLocality', 'lkg:entryKind', 'lkg:datePlausible',
  'dwc:verbatimIdentification', 'dwc:identificationQualifier', 'dwc:individualCount', 'lkg:individualCountMin', 'lkg:individualCountMax', 'lkg:countQualifier', 'dwc:occurrenceStatus',
  'dwc:sex', 'dwc:lifeStage', 'dwc:vitality', 'lkg:breedingEvidence', 'dwc:reproductiveCondition', 'dwc:behavior', 'lkg:movementKind', 'lkg:flightDirection', 'lkg:evidenceKind', 'lkg:callType',
  'lkg:callTranscription', 'lkg:spatialContext', 'lkg:microhabitat', 'lkg:relativeElevation', 'dwc:minimumElevationInMeters', 'dwc:maximumElevationInMeters', 'dwc:habitat', 'lkg:recordType',
  'dwc:basisOfRecord', 'dwc:scientificName', 'dwc:vernacularName', 'dwc:taxonRank', 'dwc:taxonID', 'dwc:kingdom', 'dwc:phylum', 'dwc:class', 'dwc:order', 'dwc:family', 'dwc:genus',
  'lkg:placeKind', 'geo:lat', 'geo:long', 'dwc:decimalLatitude', 'dwc:decimalLongitude', 'dwc:coordinateUncertaintyInMeters', 'dwc:geodeticDatum', 'dwc:georeferenceSources',
  'skos:notation', 'skos:altLabel', 'dwc:associatedReferences', 'dwc:occurrenceRemarks', 'skos:note', 'dcterms:description', 'lkg:verbatimNotes', 'lkg:visibleText', 'dwc:fieldNotes'];
const PROP_RANK = new Map(PROP_ORDER.map((p, i) => [p, i]));
function measure(s, font) { measureCtx.font = font || PFONT; return measureCtx.measureText(s).width; }
const PCACHE = new Map();   // literal rows per node (cleared with the entry and the language)
function nodeProps(v, drawn) {   // [{p, k: label, v: text, link}] of a vertex
  const n = v.n; if (n < 0 || v.kind === 'group' || v.kind === 'ghead') return [];
  if (!drawn && PCACHE.has(v.key)) return PCACHE.get(v.key);
  const shown = new Set([nodeText(v), nodeSub(v), label(n)].filter(Boolean)); const by = new Map();
  const push = (p, text, link) => { let a = by.get(p + (link ? '>' : '')); if (!a) { a = { p, link, vals: [] }; by.set(p + (link ? '>' : ''), a); } if (!a.vals.includes(text)) a.vals.push(text); };
  for (let i = G.sOff[n], e = G.sOff[n + 1]; i < e; i++) {
    const p = G.preds[G.tP[i]], o = G.tO[i];
    if (o < 0) push(p, cv(p, G.lits[-o - 1]), false);
    else if (drawn && !drawn.has(v.key + '|n' + o + '|' + p)) push(p, kindOf(o) === 'term' || kindOf(o) === 'scheme' ? clsLabel(G.nodes[o]) : kindOf(o) === 'auth' ? authId(o) : label(o), true);
  }
  const out = [];
  for (const a of by.values()) {
    // the title of the node is not repeated as a row (records and entries: their label only with "übrige Aussagen")
    if (!a.link && NAME_PREDS.has(a.p) && (a.vals.every(x => shown.has(x)) || ((v.kind === 'obs' || v.kind === 'entry') && !drawn))) continue;
    if (!a.link && a.vals.length === 1 && a.p === 'dwc:scientificName' && shown.has(a.vals[0])) continue;
    out.push({ p: a.p, k: pl(a.p), v: (a.link ? '→ ' : '') + a.vals.join(' · '), link: a.link });
  }
  out.sort((x, y) => (x.link - y.link) || ((PROP_RANK.has(x.p) ? PROP_RANK.get(x.p) : 500) - (PROP_RANK.has(y.p) ? PROP_RANK.get(y.p) : 500)) || coll.compare(x.k, y.k));
  if (!drawn) PCACHE.set(v.key, out);
  return out;
}
function propMode(sub) {
  if (S.props === 'all' || S.props === 'compact') return S.props;
  let n = 0; for (const v of sub.V.values()) if (v.col === 2 && v.n >= 0) n++;
  return n > PROP_FULL ? 'compact' : 'all';
}
function wrapText(s, w, max) {   // greedy word wrap into at most `max` lines of width w
  const words = s.replace(/\s+/g, ' ').split(' '); const lines = []; let cur = '';
  for (const wd of words) { const nx = cur ? cur + ' ' + wd : wd; if (measure(nx) <= w || !cur) cur = nx; else { lines.push(cur); cur = wd; if (lines.length === max) break; } }
  if (lines.length < max && cur) lines.push(cur); else if (lines.length === max) lines[max - 1] = fitText(lines[max - 1] + ' …', w, PFONT);
  return lines.map(l => (measure(l) > w ? fitText(l, w, PFONT) : l));
}
function propLines(v, props, expand) {
  const W = v.w - 16; const lines = [];
  for (const r of props) {
    const key = fitText(r.k, W * 0.46, PFONT); const kw = measure(key) + 5; const vw = W - kw; const cls = r.link ? ' plink' : '';
    if (measure(r.v) <= vw) { lines.push({ k: key, kx: kw, v: r.v, cls }); continue; }
    if (!expand) { lines.push({ k: key, kx: kw, v: fitText(r.v, vw, PFONT), cls, more: true }); continue; }
    lines.push({ k: key, kx: kw, v: '', cls });
    for (const l of wrapText(r.v, W - 8, 14)) lines.push({ k: '', kx: 8, v: l, cls: cls + ' pcont' });
  }
  return lines;
}
function tierRow(v) {   // not a statement of the graph: the corpus tier of the record, in words
  if (v.kind !== 'obs' || !EM) return null; const o = EM.byNode.get(v.n); const tr = tierOf(v.n); if (!o || tr < 0) return null;
  const why = tierWhy(o); const key = t('tier_k'); return { k: key, kx: measure(key) + 5, v: fitText(tierName(tr) + (why && tr < 3 ? ' — ' + why : ''), v.w - 16 - measure(key) - 5, PFONT), cls: ' ptier tr' + tr };
}
function rvPropsLayout(sub, all) {   // called by layoutSub after the header heights are set
  for (const v of all) { v.hh = v.h; v.rows = null; }
  if (!S.layers.props) return;
  const mode = propMode(sub); sub.propMode = mode; const drawn = S.layers.links ? new Set(sub.E.map(ed => ed.a.key + '|' + ed.b.key + '|' + ed.p)) : null;
  for (const v of all) {
    const props = nodeProps(v, drawn); const tr = tierRow(v); if (!props.length && !tr) continue;
    const open = mode === 'all' || S.sel === v.key;
    if (open) v.rows = (tr ? [tr] : []).concat(propLines(v, props, S.propOpen.has(v.key)));
    else v.rows = [{ k: '', kx: 0, v: fitText(props.filter(r => !r.link && r.v.length < 60).map(r => r.v).join(' · ') || '…', v.w - 16, PFONT), cls: ' psum' }];
    v.props = props; v.h = v.hh + 3 + v.rows.length * PROW + 5;
  }
}
function propsSelSync() {   // compact mode: redraw so that the selected node shows its rows; its header keeps its place on the screen
  if (!S.layers.props || !SUB || SUB.propMode !== 'compact' || SUB.selDrawn === S.sel || S.view !== 'entry') return;
  const v0 = S.sel ? SUB.V.get(S.sel) : null; const y0 = v0 ? Z.y + v0.y * Z.k : null;
  $('#gtip').hidden = true; renderGraph(true);
  const v1 = S.sel ? SUB.V.get(S.sel) : null; if (v1 && y0 != null) { Z.y = y0 - v1.y * Z.k; applyZ(); }
}
function rvPropsSvg(v) {
  if (!v.rows) return ''; let s = `<line class="psep" x1="7" x2="${v.w - 7}" y1="${v.hh + 0.5}" y2="${v.hh + 0.5}"/>`;
  v.rows.forEach((r, i) => {
    const y = v.hh + 3 + (i + 1) * PROW - 2;
    s += `<text class="pr${r.cls || ''}" y="${y}">${r.k ? `<tspan class="pk" x="8">${esc(r.k)}</tspan>` : ''}<tspan x="${(8 + r.kx).toFixed(1)}">${esc(r.v)}</tspan></text>`;
    if (r.more) s += `<rect class="pmore" x="4" y="${y - PROW + 2}" width="${v.w - 8}" height="${PROW}"><title>${esc(t('prop_more'))}</title></rect>`;
  });
  return s;
}
function rvTierSvg(v) {   // tier of a record as a small pill in its header
  if (v.kind !== 'obs') return ''; const tr = tierOf(v.n); if (tr < 0) return '';
  return `<g class="tpill tr${tr}" transform="translate(${v.w - 22},${Math.min(13, (v.hh || v.h) / 2)})"><rect x="-8" y="-6.5" width="17" height="13" rx="6.5"/><text y="3.3" text-anchor="middle">K${tr}</text></g>`;
}
function propsTip(v) {   // all rows of a node for the tooltip (compact mode, truncated values)
  if (!S.layers.props || !v.props || !v.props.length) return '';
  return '<table class="tipprops">' + v.props.slice(0, 26).map(r => `<tr><td>${esc(r.k)}</td><td>${esc(r.v.length > 220 ? r.v.slice(0, 220) + ' …' : r.v)}</td></tr>`).join('') + (v.props.length > 26 ? `<tr><td colspan="2">${esc(t('more', fmt(v.props.length - 26)))}</td></tr>` : '') + '</table>';
}
// ---- presets and tools of the graph
const LAYER_STD = { records: true, taxa: true, places: true, persons: true, habitats: true, archive: false, authorities: false, provenance: false, props: true, links: false };
function setPreset(all) {
  for (const k of Object.keys(LAYER_STD)) S.layers[k] = all ? true : LAYER_STD[k];
  store('layers', JSON.stringify(S.layers)); renderTools(); renderGraph(false);
}
const isPreset = all => Object.keys(LAYER_STD).every(k => !!S.layers[k] === (all ? true : LAYER_STD[k]));
function rvPanHint() {   // the graph is wider than the canvas: say which columns are off-screen, a click pans there
  const more = $('#gmore'), less = $('#gless'); if (!more || !less) return;
  if (!SUB || !SUB.colX || RVU.mid === 'table' || S.view !== 'entry') { more.hidden = less.hidden = true; return; }
  const W = $('#gcanvas').clientWidth; const heads = { 0: t('col_archive'), 1: t('col_entry'), 2: t('col_records'), 3: t('col_taxa'), 4: t('col_shared'), 5: t('col_auth') };
  const right = SUB.used.filter(c => Z.x + (SUB.colX[c] + colW(c) * 0.5) * Z.k > W), left = SUB.used.filter(c => Z.x + (SUB.colX[c] + colW(c) * 0.5) * Z.k < 0);
  more.hidden = !right.length; less.hidden = !left.length;
  if (right.length) { more.textContent = right.map(c => heads[c]).join(' · ') + ' ▸'; more.title = t('pan_more', right.map(c => heads[c]).join(', ')) + ' — ' + t('pan_t'); }
  if (left.length) { less.textContent = '◂ ' + left.map(c => heads[c]).join(' · '); less.title = t('pan_less', left.map(c => heads[c]).join(', ')) + ' — ' + t('pan_t'); }
}
function panTo(dir) {   // one canvas width to the right / left, not beyond the graph
  if (!SUB) return; const W = $('#gcanvas').clientWidth; const min = Math.min(8, W - SUB.width * Z.k - 8);
  Z.x = clamp(Z.x - dir * W * 0.7, min, 8); applyZ();
}
function rvGraphTools() {   // presets, mode of the properties layer, records outside the corpus
  const out = EM ? outCount(EM) : 0;
  return `<span class="seg" title="${t('preset_t')}"><button data-act="preset-std" class="${isPreset(false) ? 'on' : ''}">${t('preset_std')}</button><button data-act="preset-all" class="${isPreset(true) ? 'on' : ''}">${t('preset_all')}</button></span>` +
    (S.layers.props ? `<select id="propsel" title="${t('props_t')}">${['auto', 'compact', 'all'].map(k => `<option value="${k}"${k === S.props ? ' selected' : ''}>${t('props_short')}: ${t('pm_' + k)}</option>`).join('')}</select>` : '') +
    (out ? `<span class="chip outchip${RVU.showOut ? ' on' : ''}" data-act="showout" title="${t('out_t')}"><i></i>${esc(t(RVU.showOut ? 'out_hide' : 'out_show', fmt(out)))}</span>` : '');
}
