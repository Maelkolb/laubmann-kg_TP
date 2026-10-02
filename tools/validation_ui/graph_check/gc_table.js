/* Graph-Prüfung — records table (middle, toggled with G).
   Columns: the ten editable fields of the corrections contract, the corpus tier, and ONE COLUMN PER
   PREDICATE that any record of the entry carries (literal or node-valued; nothing is hard-coded — the
   list comes from the outgoing triples of the records). Default: every column with a value (or a
   proposal chip) in this entry; the column chooser shows/hides columns, the choice is remembered. */

const T_FIELDS = ['species', 'count', 'locality', 'date', 'observer', 'record_type', 'sex', 'life_stage', 'breeding', 'status'];
// predicates whose value an editable column already shows as it is
const T_COVERED = new Set(['dwc:eventDate', 'dwciri:recordedBy>', 'lkg:recordType', 'dwc:sex', 'dwc:lifeStage', 'lkg:breedingEvidence', 'dwc:occurrenceStatus', 'dwc:verbatimLocality']);
// structural statements go to the far right
const T_LAST = ['lkg:observedTaxon>', 'lkg:hasLocality>', 'lkg:observedAt>', 'dwciri:habitat>', 'dcterms:isPartOf>', 'prov:wasDerivedFrom>', 'prov:wasGeneratedBy>', 'dwc:basisOfRecord', 'rdfs:label', 'rdf:type>'];
// field codes of the checks without an editable column: their chip sits in the column of the predicate
const FLAG_COL = { behav: 'dwc:behavior', behaviour: 'dwc:behavior', call: 'lkg:callType', vocalisation: 'lkg:callType', evidence: 'lkg:evidenceKind', notes: 'lkg:verbatimNotes' };
const TCOLS = { hide: null };
function colPrefs() { if (!TCOLS.hide) { try { TCOLS.hide = JSON.parse(store('tcols') || '{}'); } catch (err) { TCOLS.hide = {}; } } return TCOLS.hide; }
function flagChips(o) {   // {column id: [chip html]} for flagged fields without an editable column
  const out = {}; if (!RVU.notes || (RV.dec[o.key] && RV.dec[o.key].d)) return out;
  for (const c of ['g', 's']) {
    const f = o.rec[c]; if (!f || f.v === 'ok' || !f.v) continue;
    for (const k of f.f || []) {
      if (REC_FIELDS.includes(k) || k === 'georef' || k === 'place' || k === 'co_observers') continue;
      const col = FLAG_COL[k] ? 'p:' + FLAG_COL[k] : 'species'; const fix = (f.fix || {})[k];
      (out[col] || (out[col] = [])).push(`<span class="pchip ro pc-${c}" title="${esc(srcName(c) + ' — ' + (f.why || t('chip_ro')))}">${esc(fieldLabel(k))}${fix ? ' → ' + esc(Array.isArray(fix) ? fix.join(', ') : String(fix)) : ' ?'}</span>`);
    }
  }
  return out;
}
function tableCols(m, rows) {   // every column the entry could show: [{id, f | p, link, label, n}]
  const cols = T_FIELDS.map(f => ({ id: f, f, label: fieldLabel(f), n: 0 })); const by = new Map(cols.map(c => [c.id, c]));
  const tier = { id: 'tier', label: t('col_tier'), n: m.obs.length, title: t('tier_t') }; cols.push(tier);
  const pc = new Map();
  for (const o of m.obs) {
    const seen = new Set();
    for (let i = G.sOff[o.n], e = G.sOff[o.n + 1]; i < e; i++) { const key = G.preds[G.tP[i]] + (G.tO[i] < 0 ? '' : '>'); if (seen.has(key) || T_COVERED.has(key)) continue; seen.add(key); pc.set(key, (pc.get(key) || 0) + 1); }
    const cur = recVals(o.n); for (const f of T_FIELDS) if (f === 'observer' ? cur.observer || cur.co_observers : cur[f]) by.get(f).n++;
    const d = RV.dec[o.key]; if (d && d.vals) for (const f in d.vals) if (by.has(f)) by.get(f).chip = true;
    for (const c of ['g', 's']) { const p = (d && d.d) || !RVU.notes ? null : proposal(o, c); if (!p) continue; for (const f in p.vals) if (by.has(f)) by.get(f).chip = true; for (const f in p.bad) if (by.has(f)) by.get(f).chip = true; if (p.georef) by.get('locality').chip = true; }
    const fc = flagChips(o); for (const id in fc) if (id.startsWith('p:') && !pc.has(id.slice(2))) pc.set(id.slice(2), 0);
  }
  for (const it of RVU.notes ? m.items : []) if (it.type === 'miss' && it.x.kind === 'observation') for (const f of ['count', 'locality', 'date', 'observer']) if (({ count: it.x.count, locality: it.x.loc, date: it.x.date, observer: it.x.obs })[f]) by.get(f).chip = true;
  const rank = k => { const l = T_LAST.indexOf(k); if (l >= 0) return 1000 + l; const base = k.replace(/>$/, ''); return (PROP_RANK.has(base) ? PROP_RANK.get(base) : 400) + (k.endsWith('>') ? 300 : 0); };
  const keys = [...pc.keys()].sort((a, b) => rank(a) - rank(b) || coll.compare(pl(a.replace(/>$/, '')), pl(b.replace(/>$/, ''))));
  for (const k of keys) { const link = k.endsWith('>'); const p = link ? k.slice(0, -1) : k; cols.push({ id: 'p:' + k, p, link, label: pl(p) + (link ? ' →' : ''), n: pc.get(k), title: p + (link ? ' (' + t('col_link') + ')' : '') }); }
  const hide = colPrefs();
  for (const c of cols) { c.def = c.id === 'species' || c.n > 0 || !!c.chip || (c.id.startsWith('p:') && c.n === 0); c.on = c.id === 'species' ? true : c.id in hide ? !hide[c.id] : c.def; }
  return cols;
}
function predCell(o, c) {   // the values of one predicate of a record
  const vals = [];
  for (let i = G.sOff[o.n], e = G.sOff[o.n + 1]; i < e; i++) {
    if (G.preds[G.tP[i]] !== c.p) continue; const x = G.tO[i]; if ((x >= 0) !== c.link) continue;
    const v = x < 0 ? cv(c.p, G.lits[-x - 1]) : kindOf(x) === 'term' || kindOf(x) === 'scheme' ? clsLabel(G.nodes[x]) : label(x); if (!vals.includes(v)) vals.push(v);
  }
  return vals.join(' · ');
}
function tdCell(o, f, cur, d, ps) {
  const curv = f === 'observer' ? [cur.observer, cur.co_observers].filter(Boolean).join('; ') : cur[f];
  const hv = d && d.vals ? (f === 'observer' && ('observer' in d.vals || 'co_observers' in d.vals) ? ['observer' in d.vals ? d.vals.observer : cur.observer, 'co_observers' in d.vals ? d.vals.co_observers : cur.co_observers].filter(x => x && !CLEAR.has(x)).join('; ') || t('v_cleared') : f in d.vals ? showVal(f, d.vals[f]) : null) : null;
  let s = '', chips = ''; const acc = (k, src) => (EXPLORER ? '' : ` data-acc="${k}|${src}"`); const tip = (src, k) => esc(srcName(src) + (EXPLORER ? '' : ' — ' + t(k)));
  if (hv != null) s = `<span class="was">${esc(showVal(f, curv) || '—')}</span> <span class="hv">${esc(hv)}</span>`;
  else {
    s = esc(showVal(f, curv));
    for (const p of ps) {
      if (f in p.vals || (f === 'observer' && 'co_observers' in p.vals)) { const pv = f === 'observer' ? [p.vals.observer || cur.observer, p.vals.co_observers || ''].filter(Boolean).join('; ') : showVal(f, p.vals[f]);
        s = ''; chips += `<span class="pchip pc-${p.src}"${acc(f, p.src)} title="${tip(p.src, 'chip_accept')}">${esc(showVal(f, curv) || '—')} → ${esc(pv)}</span>`; }
      else if (f in p.bad) { s = ''; chips += `<span class="pchip bad" title="${esc(srcName(p.src) + ' — ' + t('bad_format'))}">${esc(showVal(f, curv) || '—')} → ${esc(p.bad[f])}</span>`; }
      if (f === 'locality' && p.georef) chips += `<span class="pchip geo"${acc('georef', p.src)} title="${tip(p.src, 'geo_chip_t')}">${esc(fieldLabel('georef'))} → ${esc(p.georef)}</span>`;
      if (f === 'species' && p.drop) chips += `<span class="pchip drop"${acc('drop', p.src)} title="${tip(p.src, 'drop_chip_t')}">${t('v_spurious')}?</span>`;
    }
    if (f === 'species' && RVU.notes) for (const a of o.rec.auto || []) if (a[0] === 'value') chips += `<span class="pchip auto" title="${esc(t('src_auto'))}">${esc(a[1])} → ${esc(a[2])}</span>`;
  }
  return [s, chips];
}
function annBadge(an) { return an ? `<span class="tbadge ${an.cls}" title="${esc((an.lv != null ? lvName(an.lv) + ' · ' : '') + t(an.tip))}">${esc(an.mk)}</span>` : ''; }
function rvRenderTable() {
  const box = $('#rtable'); const on = RVU.mid === 'table' && S.view === 'entry'; box.hidden = RVU.mid !== 'table'; $('#gcanvas').hidden = RVU.mid === 'table';
  if (!on || !EM) { closeColChooser(); return; }
  const m = EM; const keep = box.dataset.e === String(m.e) ? [box.scrollTop, box.scrollLeft] : [0, 0];
  let rows = m.obs; if (corpusOn() && !RVU.showOut) rows = rows.filter(o => inCorpus(o.n));
  if (RVU.tflag && RVU.notes) rows = rows.filter(o => (m.itemByObs.get(o.n) || {}).lv >= 1 || RV.dec[o.key]);
  const acts = !EXPLORER;   // the explorer build has no action column and no editable cell
  const selN = S.sel && S.sel[0] === 'n' ? +S.sel.slice(1) : -1;
  const all = tableCols(m, rows); TCOLS.cols = all; const cols = all.filter(c => c.on);
  let s = `<table class="t rt"><thead><tr><th class="c-nr">#</th><th class="c-bd"></th>${cols.map(c => `<th class="${c.f ? 'c-' + c.f : c.id === 'tier' ? 'c-tier' : 'c-p'}" data-col="${esc(c.id)}" title="${esc(c.title || c.label)}">${esc(c.label)}</th>`).join('')}${acts ? '<th class="c-acts"></th>' : ''}</tr></thead><tbody>`;
  rows.forEach(o => {
    const d = RV.dec[o.key]; const cur = recVals(o.n); const ps = (d && d.d) || !RVU.notes ? [] : ['g', 's'].map(c => proposal(o, c)).filter(Boolean); const an = RVU.notes ? recAnn(m, o) : null; const fc = flagChips(o); const out = corpusOn() && !inCorpus(o.n);
    s += `<tr data-o="${o.n}" class="${o.n === selN ? 'on ' : ''}${an ? 'an-' + an.cls : ''}${d && d.d === 'x' ? ' dropped' : ''}${out ? ' out' : ''}"><td class="num muted c-nr">${o.idx < 1e6 ? o.idx + 1 : '?'}</td><td class="c-bd">${annBadge(an)}</td>`;
    for (const c of cols) {
      if (c.f) { const [v, chips] = tdCell(o, c.f, cur, d, ps); s += `<td data-f="${c.f}"${c.f === 'species' ? ' class="c-species"' : ''}>${v}${chips}${(fc[c.id] || []).join('')}</td>`; }
      else if (c.id === 'tier') { const why = tierWhy(o); s += `<td class="c-tier">${tierChip(o)}${why && tierOf(o.n) < 3 ? `<span class="trwhy" title="${esc(why)}">${esc(why)}</span>` : ''}</td>`; }
      else { const v = predCell(o, c); s += `<td class="c-p${c.link ? ' lk' : ''}"${v.length > 34 ? ` title="${esc(v)}"` : ''}><span class="pv">${esc(v)}</span>${(fc['p:' + c.p] || []).join('')}</td>`; }
    }
    s += (acts ? `<td class="racts"><button class="mini" data-ra="ok" title="${t('a_rec_ok')}">✓</button><button class="mini" data-ra="edit" title="${t('a_edit')}">✎</button><button class="mini" data-ra="drop" title="${t('a_drop')}">✕</button></td>` : '') + '</tr>';
  });
  for (const it of RVU.notes ? m.items : []) if (it.type === 'miss' && it.x.kind === 'observation') {
    const d = RV.dec[it.key]; const r = d && d.rec; const x = it.x; const an = rvAnn({ kind: 'miss', item: it.key });
    const val = { species: esc(r ? r.species_de : x.de || '?') + ` <span class="muted">${t('ghost_missing')}</span>`, count: esc(r ? r.count : x.count || ''), locality: esc(r ? r.locality : x.loc || ''), date: esc(r ? r.date : x.date || ''), observer: esc(r ? r.observer : x.obs || ''), record_type: esc(r && r.record_type ? showVal('record_type', r.record_type) : '') };
    s += `<tr class="ghost${d && d.d === 'add' ? ' an-dec' : d && d.d === 'no' ? ' dropped' : ''}" data-item="${esc(it.key)}"><td class="c-nr"></td><td class="c-bd">${annBadge(an)}</td>` +
      cols.map(c => `<td${c.id === 'species' ? ' class="c-species"' : ''}>${c.f ? val[c.f] || '' : c.id === 'tier' && x.src !== 'h' ? `<span class="muted">${esc(srcName(x.src))}</span>` : ''}</td>`).join('') +
      (acts ? `<td class="racts"><button class="mini" data-ra="add" title="${t('a_add')}">+</button></td>` : '') + '</tr>';
  }
  const hidden = all.filter(c => !c.on).length; const outN = outCount(m);
  box.innerHTML = s + `</tbody></table>${rows.length ? '' : `<p class="muted" style="padding:12px">${t(RVU.tflag ? 't_none_flagged' : 'no_records')}</p>`}` +
    `<p class="muted tfoot">${esc(t('t_cols_foot', fmt(cols.length), fmt(all.length)))}${hidden ? ' · ' + esc(t('t_cols_hidden', fmt(hidden))) : ''}${outN && !RVU.showOut ? ' · ' + esc(t('out_cards', fmt(outN), corpusName(RVU.corpus))) : ''}</p>`;
  box.dataset.e = String(m.e); box.scrollTop = keep[0]; box.scrollLeft = keep[1];
  if (TCOLS.open) drawColChooser();
}
// ---- column chooser
function drawColChooser() {
  const pop = $('#colpop'); if (!pop || !TCOLS.cols) return;
  const row = c => `<label class="${c.def ? '' : 'nodef'}" title="${esc(c.title || c.label)}"><input type="checkbox" data-col="${esc(c.id)}"${c.on ? ' checked' : ''}${c.id === 'species' ? ' disabled' : ''}>${esc(c.label)}<span class="num muted">${c.id.startsWith('p:') || c.f ? fmt(c.n) : ''}</span></label>`;
  const a = TCOLS.cols.filter(c => c.f || c.id === 'tier'), b = TCOLS.cols.filter(c => !(c.f || c.id === 'tier'));
  pop.innerHTML = `<div class="cph"><b>${t('cols_title')}</b><span class="sp"></span><button class="mini" data-cp="all">${t('cols_all')}</button><button class="mini" data-cp="def" title="${t('cols_def_t')}">${t('cols_def')}</button><button class="mini" data-cp="close">×</button></div>
    <div class="cpg"><div class="cps">${t('cols_fields')}</div>${a.map(row).join('')}</div><div class="cpg"><div class="cps">${t('cols_preds')}</div>${b.map(row).join('')}</div><div class="cpn muted">${t('cols_note')}</div>`;
}
function closeColChooser() { TCOLS.open = false; const pop = $('#colpop'); if (pop) pop.remove(); }
function colChooser(btn) {
  if (TCOLS.open) { closeColChooser(); return; }
  const pop = document.createElement('div'); pop.id = 'colpop'; $('#gwrap').appendChild(pop); TCOLS.open = true;
  const r = btn.getBoundingClientRect(), w = $('#gwrap').getBoundingClientRect(); pop.style.left = Math.max(8, r.left - w.left) + 'px'; pop.style.top = (r.bottom - w.top + 4) + 'px';
  pop.addEventListener('click', ev => {
    const b = ev.target.closest('[data-cp]'); if (!b) return; const hide = colPrefs();
    if (b.dataset.cp === 'close') { closeColChooser(); return; }
    if (b.dataset.cp === 'def') for (const k of Object.keys(hide)) delete hide[k]; else for (const c of TCOLS.cols) hide[c.id] = false;
    store('tcols', JSON.stringify(hide)); rvRenderTable();
  });
  pop.addEventListener('change', ev => { const c = ev.target.dataset.col; if (!c) return; const hide = colPrefs(); hide[c] = !ev.target.checked; store('tcols', JSON.stringify(hide)); rvRenderTable(); });
  drawColChooser();
}
function recItem(m, o) { return m.items.find(it => it.type === 'rec' && it.o === o) || { type: 'rec', group: 'rec', key: o.key, o, virtual: true }; }
function saveCell(o, f, raw) {   // inline edit of one cell; empty clears, the graph's own value removes the correction
  const m = EM; const cur = recVals(o.n); const d = RV.dec[o.key]; const vals = Object.assign({}, d && d.vals ? d.vals : {});
  const set = (k, v) => { v = String(v).trim(); if (v === (cur[k] || '')) { delete vals[k]; return true; } if (!v) { if (k === 'record_type' || k === 'status') return true; v = '-'; } const ok = fieldCheck(k, v); if (ok == null) return false; vals[k] = ok; return true; };
  let ok = true;
  if (f === 'observer') { const parts = raw.split(/\s*;\s*/).map(x => x.trim()).filter(Boolean); ok = set('observer', parts[0] || '') && set('co_observers', parts.slice(1).join('; ')); }
  else ok = set(f, raw);
  if (!ok) { toast(t('err_format', fieldLabel(f)) + ' — ' + t('hint_' + (f === 'count' ? 'count' : 'date')), 4500); return false; }
  if (!Object.keys(vals).length) { if (d) decide(o.key, null, 'reset'); else rvRenderTable(); return true; }
  decideRec(m, o, 'e', vals, 'edit'); return true;
}
function editCell(td, o, f) {
  if (td.querySelector('input,select')) return;
  if (f === 'species') { openForm(o.key, 'rec'); return; }
  const cur = recVals(o.n); const d = RV.dec[o.key]; const v = k => (d && d.vals && k in d.vals ? (CLEAR.has(d.vals[k]) ? '' : d.vals[k]) : cur[k] || '');
  const voc = FIELD_VOC[f];
  td.innerHTML = voc ? sel(f, v(f), voc[0], voc[1], voc[2] || !cur[f]) : inp(f, f === 'observer' ? [v('observer'), v('co_observers')].filter(Boolean).join('; ') : v(f), f === 'date' ? 'JJJJ-MM-TT' : '');
  const el = td.firstChild; el.focus(); if (el.select) el.select(); let done = false;
  const commit = () => { if (done) return; done = true; if (!saveCell(o, f, el.value)) { done = false; el.classList.add('bad'); el.focus(); } };
  el.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); commit(); } });
  el.addEventListener('change', () => { if (voc) commit(); });
  el.addEventListener('blur', () => { if (!done && el.value !== (f === 'observer' ? [v('observer'), v('co_observers')].filter(Boolean).join('; ') : v(f))) commit(); else if (!done) rvRenderTable(); });
}
function tableClick(ev) {
  const m = EM; if (!m) return; const tr = ev.target.closest('tr[data-o], tr[data-item]'); if (!tr) return;
  if (tr.dataset.item) { const it0 = m.items.find(it => it.key === tr.dataset.item); if (it0 && it0.sec === 'hint') RVU.hints = true; const i = visibleItems(m).findIndex(it => it.key === tr.dataset.item); if (i >= 0) { S.tab = 'check'; RVU.card = i; if (ev.target.closest('[data-ra="add"]') && !EXPLORER) openForm(tr.dataset.item, 'add'); else { renderPanel(); focusCard(i); } } return; }
  const o = m.byNode.get(+tr.dataset.o); if (!o) return;
  if (EXPLORER) { selectKey('n' + o.n, { center: true }); return; }   // a click selects the record; nothing is edited
  const chip = ev.target.closest('.pchip[data-acc]'); const ra = ev.target.closest('[data-ra]'); const td = ev.target.closest('td[data-f]');
  if (ev.target.closest('input,select')) return;
  if (chip) {
    const [f, src] = chip.dataset.acc.split('|'); const p = proposal(o, src); if (!p) return;
    if (f === 'drop') { decideRec(m, o, 'x', null, 'drop'); return; }
    const d = RV.dec[o.key]; const vals = Object.assign({}, d && d.vals ? d.vals : {});
    if (f === 'georef') vals.locality = p.georef; else { vals[f] = p.vals[f]; if (f === 'observer' && p.vals.co_observers) vals.co_observers = p.vals.co_observers; }
    const mp = mergedProposal(o); decideRec(m, o, mp && JSON.stringify(vals) === JSON.stringify(mp.vals) ? 'a' : 'e', vals, 'apply'); return;
  }
  if (ra) { const a = ra.dataset.ra; if (a === 'ok') decideRec(m, o, 'ok', null, 'ok'); else if (a === 'drop') decideRec(m, o, 'x', null, 'drop'); else openForm(o.key, 'rec'); return; }
  if (td && tr.classList.contains('on')) { editCell(td, o, td.dataset.f); return; }
  selectKey('n' + o.n, { center: true });
  if (td) { const td2 = $(`#rtable tr[data-o="${o.n}"] td[data-f="${td.dataset.f}"]`); if (td2) editCell(td2, o, td.dataset.f); }
}
