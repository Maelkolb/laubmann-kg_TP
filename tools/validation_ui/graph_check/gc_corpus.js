/* Graph-Prüfung — corpus filter: vollständig / Kern / strenger Kern / strenger Kern mit Koordinaten.
   Every record carries a tier (review layer `t`, reasons `tw`): 0 outside the core, 1 core, 2 strict core,
   3 strict core with coordinates. The selector in the header chooses the lowest tier that is shown
   (RVU.corpus = 0 … 3). It is a VIEW: graphs, table, work list, queue counts, node views, class view and
   overview count only the records of the chosen corpus; decisions and exports are not affected. */

const CORP = { info: false, tier: null, n: [0, 0, 0, 0], ent: [0, 0, 0, 0], taxa: [0, 0, 0, 0], why: {} };
function corpusIndex() {   // tier of every observation node, counts per corpus, reasons
  const tier = new Int8Array(G.nodes.length).fill(-1); const taxa = [new Set(), new Set(), new Set(), new Set()]; const why = {};
  CORP.n = [0, 0, 0, 0]; CORP.ent = [0, 0, 0, 0];
  for (const r of G.ent) {
    const rv = R.entries[r.id] || {}; const s = RVS.get(r.n); const nc = [0, 0, 0, 0]; const flat = R.obs[r.id] || [];
    for (let i = 0; i < flat.length; i += 3) {
      const n = flat[i]; const rec = (rv.rec || {})[flat[i + 1]]; const tr = rec && rec.t != null ? rec.t : 0; tier[n] = tr; const tx = node1(n, 'lkg:observedTaxon');
      for (let c = 0; c <= tr; c++) { nc[c]++; if (tx >= 0) taxa[c].add(tx); }
      for (const w of (rec && rec.tw) || []) why[w] = (why[w] || 0) + 1;
    }
    s.nc = nc; for (let c = 0; c < 4; c++) { CORP.n[c] += nc[c]; if (c === 0 || nc[c]) CORP.ent[c]++; }
  }
  CORP.tier = tier; CORP.taxa = taxa.map(x => x.size); CORP.why = why;
}
function recOfNode(n) {   // the review-layer record of an observation node
  const e = entryOf(n); if (e < 0) return null; const r = entryRec(e); const flat = R.obs[r.id] || [];
  for (let i = 0; i < flat.length; i += 3) if (flat[i] === n) return ((R.entries[r.id] || {}).rec || {})[flat[i + 1]] || null;
  return null;
}
const corpusOn = () => RVU.corpus > 0;
const tierOf = n => (CORP.tier ? CORP.tier[n] : -1);
const inCorpus = n => RVU.corpus === 0 || CORP.tier[n] >= RVU.corpus;
const entryInCorpus = s => RVU.corpus === 0 || !!(s.nc && s.nc[RVU.corpus] > 0);
const corpusName = c => t('corp_' + c);
const tierName = tr => t('tier_' + tr);
const whyText = code => { const k = 'tw_' + code; return UI[LANG][k] || UI.de[k] || code; };
function tierWhy(o) { const tw = (o.rec && o.rec.tw) || []; return tw.map(whyText).join('; '); }   // why the record is not in the next tier, in words
function tierChip(o) { const tr = tierOf(o.n); if (tr < 0) return ''; const why = tierWhy(o); return `<span class="trc tr${tr}" title="${esc(t('tier_t') + (why ? ' — ' + why : ''))}">${esc(tierName(tr))}</span>`; }
function tierLine(o) {   // chip + reason, for cards and tooltips
  const tr = tierOf(o.n); if (tr < 0) return ''; const why = tierWhy(o);
  return `<div class="trline">${tierChip(o)}${tr < 3 && why ? `<span class="trwhy">${esc(t(tr === 0 ? 'tier_out_why' : 'tier_next_why', tierName(Math.min(3, tr + 1))))} ${esc(why)}</span>` : ''}</div>`;
}
// ---- what belongs to an entry or to a used node follows it
const ENTRY_PARTS = new Set(['weather', 'travel', 'leg', 'region', 'mmregion']);
const OWNED = new Set([...ENTRY_PARTS, 'page', 'volume', 'geom', 'auth']);
const OWNERS = new Map();
function ownersOf(n, k) {
  let o = OWNERS.get(n); if (o) return o;
  if (k === 'region' || k === 'mmregion') o = regionEntries(n);
  else if (k === 'page') o = pageEntries(n);
  else if (k === 'volume') o = (G.entByVol.get(n) || []).map(i => G.ent[i].n);
  else if (k === 'geom') o = incoming(n, 'gsp:hasGeometry');
  else if (k === 'auth') o = uniq([].concat(...MATCH.concat(['owl:sameAs']).map(p => incoming(n, p))));
  else { const e = entryOf(n); o = e >= 0 ? [e] : []; }
  OWNERS.set(n, o); return o;
}
const ownerOk = x => (G.kind[x] === KI.entry ? rvSrcOk(x) : rvUses(x) > 0);
// ---- hooks of the forked explorer code
const rvObsShown = o => inCorpus(o) || RVU.showOut;
function rvSrcOk(s) {   // under a filter: records of the corpus, entries with a record in it, and what belongs to such an entry
  if (!corpusOn()) return true;
  const k = G.kind[s];
  if (k === KI.obs) return inCorpus(s);
  if (k === KI.entry) { const x = RVS.get(s); return !!x && entryInCorpus(x); }
  if (ENTRY_PARTS.has(KIND_LIST[k])) return ownersOf(s, KIND_LIST[k]).some(rvSrcOk);
  return true;
}
function rvInCount(n, name) { if (!corpusOn()) return inCount(n, name); const p = PI(name); if (p < 0) return 0; let c = 0; for (let i = G.inOff[n], e = G.inOff[n + 1]; i < e; i++) if (G.inP[i] === p && rvSrcOk(G.inS[i])) c++; return c; }
function rvUses(n) { if (!corpusOn()) return G.inOff[n + 1] - G.inOff[n]; let c = 0; for (let i = G.inOff[n], e = G.inOff[n + 1]; i < e; i++) if (rvSrcOk(G.inS[i])) c++; return c; }
function rvClassOk(n, k) {
  if (!corpusOn()) return true;
  if (k === 'obs' || k === 'entry') return rvSrcOk(n);
  if (k === 'taxon' || k === 'place' || k === 'person' || k === 'habitat') return rvUses(n) > 0;
  if (OWNED.has(k)) return ownersOf(n, k).some(ownerOk);
  return true;
}
function rvEntryCount(r) {   // "5 von 8 Beobachtungen" under a filter
  const s = RVS.get(r.n); return corpusOn() && s && s.nc ? t('obs_of', fmt(s.nc[RVU.corpus]), fmt(r.nobs)) : fmt(r.nobs) + ' ' + t('observations');
}
function outCount(m) { return corpusOn() ? m.obs.filter(o => !inCorpus(o.n)).length : 0; }
// ---- selector, switching
function renderCorpusBar() {   // the corpus filter: an always visible segmented control under the header, in every view
  const bar = $('#corpbar'); if (!bar) return; const c = RVU.corpus;
  const seg = [0, 1, 2, 3].map(k => `<button type="button" class="cb${k === c ? ' on' : ''}" data-corpus="${k}" aria-pressed="${k === c}" title="${esc(t('corp_def_' + k))}"><span class="cbn">${esc(t('corp_b_' + k))}</span><span class="cbc num">${fmt(CORP.n[k])}</span></button>`).join('');
  const note = corpusOn() ? t('corp_active', corpusName(c), fmt(CORP.n[c]), fmt(CORP.n[0]), fmt(CORP.ent[c]), fmt(CORP.ent[0])) : t('corp_view');
  bar.classList.toggle('active', corpusOn());
  bar.innerHTML = `<span class="cbl" title="${esc(t('corp_t'))}">${t('corp_label')}</span><span class="cseg" role="group" aria-label="${esc(t('corp_label'))}">${seg}</span>` +
    `<button type="button" class="cinfo${CORP.info ? ' on' : ''}" data-act="corpus-info" aria-expanded="${CORP.info ? 'true' : 'false'}" title="${esc(t('corp_info_t'))}">ⓘ</button>` +
    `<span class="cnote" title="${esc(note)}">${esc(note)}</span>` +
    (corpusOn() ? `<button type="button" class="btn" data-act="corpus-off">${t('corp_off')}</button>` : '') +
    (EXPLORER ? `<label class="cnotes${RVU.notes ? ' on' : ''}" title="${esc(t('notes_t'))}"><input type="checkbox" id="notesw"${RVU.notes ? ' checked' : ''}>${t('notes_on')}</label>` : '') +
    (CORP.info ? `<div id="corpinfo" role="note"><b>${t('corp_info_h')}</b><dl>${[0, 1, 2, 3].map(k => `<dt>${esc(t('corp_b_' + k))} <span class="num muted">${fmt(CORP.n[k])}</span></dt><dd>${esc(t('corp_def_' + k))}</dd>`).join('')}</dl><p class="muted">${esc(t('corp_info_view'))}</p></div>` : '');
  document.documentElement.classList.toggle('corpus-on', corpusOn());
}
function corpusBarWire() {
  const bar = $('#corpbar');
  bar.addEventListener('click', ev => {
    ev.gcCorpusBar = true;   // the bar is redrawn below: the target leaves the document before the click reaches it
    const b = ev.target.closest('[data-corpus]'); if (b) { CORP.info = false; setCorpus(b.dataset.corpus); return; }
    const a = ev.target.closest('[data-act]'); if (!a) return;
    if (a.dataset.act === 'corpus-off') setCorpus(0);
    else if (a.dataset.act === 'corpus-info') { CORP.info = !CORP.info; renderCorpusBar(); }
  });
  bar.addEventListener('change', ev => { if (ev.target.id === 'notesw') setNotes(ev.target.checked); });
  document.addEventListener('click', ev => { if (CORP.info && !ev.gcCorpusBar) { CORP.info = false; renderCorpusBar(); } });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && CORP.info) { CORP.info = false; renderCorpusBar(); } });
}
function setNotes(on) {   // explorer build: "Prüfhinweise zeigen" — off = the graph as it is, without findings, changes, ghost nodes
  if (!EXPLORER) return;
  RVU.notes = !!on; store('notes', on ? '1' : '0'); LVC.clear();
  if (!queueList().includes(RVU.queue)) { RVU.queue = 'all'; store('queue', 'all'); }
  countQueues(); renderCorpusBar(); renderChips(); rvRenderList();
  if (S.view === 'entry') EM = null;
  route(); rvResize(); if (S.view === 'entry') fitView();
}
function setCorpus(c) {
  RVU.corpus = clamp(+c || 0, 0, 3); store('corpus', String(RVU.corpus)); RVU.showOut = false;
  G.stats = null; NV.rows = null; CV.rows = null; LVC.clear(); const ov = $('#x-ov'); if (ov) ov.dataset.lang = '';
  countQueues(); renderCorpusBar(); renderChips(); rvRenderList();
  if (S.view === 'entry') EM = null;   // the model keeps no corpus state, but the cards and the head do
  route(); rvResize(); if (S.view === 'entry') fitView();
  // a selected record that the corpus hides is no longer highlighted on the scan
  if (S.view === 'entry' && S.sel && S.sel[0] === 'n' && kindOf(+S.sel.slice(1)) === 'obs' && !inCorpus(+S.sel.slice(1)) && !RVU.showOut) selectKey(null);
}
// ---- overview
function corpusTableHtml() {
  const pct = (a, b) => (b ? (100 * a / b).toFixed(1).replace('.', LANG === 'de' ? ',' : '.') + ' %' : '–');
  let s = `<table class="t covt"><tr><th>${t('corp_h')}</th><th class="r">${t('corp_h_rec')}</th><th class="r"></th><th class="r">${t('corp_h_ent')}</th><th class="r">${t('corp_h_taxa')}</th></tr>` +
    [0, 1, 2, 3].map(c => `<tr class="click${c === RVU.corpus ? ' on' : ''}" data-corpus="${c}"><td>${c === RVU.corpus ? '● ' : ''}${esc(corpusName(c))}</td><td class="num r">${fmt(CORP.n[c])}</td><td class="num r muted">${pct(CORP.n[c], CORP.n[0])}</td><td class="num r">${fmt(c === 0 ? G.ent.filter(r => r.nobs > 0).length : CORP.ent[c])}</td><td class="num r">${fmt(CORP.taxa[c])}</td></tr>`).join('') + '</table>';
  const order = ['spurious', 'flagged', 'unchecked', 'duplicate', 'no-taxon', 'list', 'literature-date', 'entry-checks', 'ungrounded', 'long-entry', 'flagged-attribution', 'flagged-place', 'flagged-georef', 'attribution', 'identification', 'count', 'absence', 'reading', 'entry', 'entry-place', 'no-coords', 'georef-unconfirmed', 'place-doubt'];
  const from = { 'spurious': 0, 'flagged': 0, 'unchecked': 0, 'duplicate': 0, 'no-taxon': 0, 'list': 0, 'literature-date': 0, 'entry-checks': 0, 'ungrounded': 0, 'long-entry': 0, 'flagged-attribution': 1, 'flagged-place': 1, 'flagged-georef': 1, 'attribution': 1, 'identification': 1, 'count': 1, 'absence': 1, 'reading': 1, 'entry': 1, 'entry-place': 1, 'no-coords': 2, 'georef-unconfirmed': 2, 'place-doubt': 2 };
  const codes = order.filter(k => CORP.why[k]).concat(Object.keys(CORP.why).filter(k => !order.includes(k)));
  s += `<h3 style="margin-top:14px">${t('corp_why_h')}</h3><table class="t covt"><tr><th>${t('corp_why_reason')}</th><th>${t('corp_why_keeps')}</th><th class="r">${t('corp_h_rec')}</th></tr>` +
    codes.map(k => `<tr><td>${esc(whyText(k))}</td><td class="muted">${esc(tierName(Math.min(3, (from[k] == null ? 0 : from[k]) + 1)))}</td><td class="num r">${fmt(CORP.why[k])}</td></tr>`).join('') + '</table>';
  return s;
}
