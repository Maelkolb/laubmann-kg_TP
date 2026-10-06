/* Graph-Prüfung — reliability filter and the estimated quality of every record.
   Every record of the review layer carries `q` (build_review.py --quality, record_quality.py): p = estimated
   probability that a field is wrong, po the occurrence (exists, species, count, date), pc the coordinates,
   pf per field, s status per field, x the blind check's own reading, lv level 1..4.
   The bar under the header chooses a measure (RVU.qm) and a threshold (RVU.qt: 0 all, 1 < 50 %, 2 < 25 %,
   3 < 10 %). It is a VIEW: graphs, table, work list, queue counts, node views, class view and overview show
   only the records that pass; decisions and exports are not affected. */

const Q_FIELDS = ['exists', 'species', 'count', 'date', 'place', 'observer', 'record_type'];
const Q_XKEY = ['ex', 'sp', 'n', 'd', 'pl', 'ob', 'ty'];
const Q_MEASURES = ['p', 'po', 'pl', 'ob', 'pc'];
const Q_BOUND = [Infinity, 0.5, 0.25, 0.10];
const Q_STATUS = ['ok', 'one', 'c1', 'c2', 'both', 'na'];
const Q_COORDS = ['rev', 'gaz', 'rev-c1', 'gaz-c1', 'none'];
const QF = { val: {}, lv: null, on: null, rec: new Map(), nodes: [], ents: [], cnt: {}, total: 0, shown: 0, est: 0, has: 0, ents_on: 0 };

function qfIndex() {   // value of every measure per record node, counts per measure and threshold
  const N = G.nodes.length; QF.lv = new Int8Array(N); QF.on = new Uint8Array(N); QF.rec.clear(); QF.nodes = []; QF.ents = [];
  for (const m of Q_MEASURES) QF.val[m] = new Float64Array(N).fill(NaN);
  G.ent.forEach((r, ei) => {
    const rv = R.entries[r.id] || {}; const flat = R.obs[r.id] || [];
    for (let i = 0; i < flat.length; i += 3) {
      const n = flat[i]; const rec = (rv.rec || {})[flat[i + 1]]; QF.nodes.push(n); QF.ents.push(ei);
      if (!rec) continue; QF.rec.set(n, rec); const q = rec.q; if (!q) continue;
      QF.val.p[n] = q.p; QF.val.po[n] = q.po; QF.val.pc[n] = q.pc == null ? NaN : q.pc;
      const pf = q.pf || []; QF.val.pl[n] = pf[4] == null ? NaN : pf[4]; QF.val.ob[n] = pf[5] == null ? NaN : pf[5];
      QF.lv[n] = q.lv || qLevelOf(q.p);
    }
  });
  QF.total = QF.nodes.length;
  for (const m of Q_MEASURES) QF.cnt[m] = [0, 1, 2, 3].map(k => { let c = 0; for (const n of QF.nodes) if (qPass(m, k, n)) c++; return c; });
  qfApply();
}
const qLevelOf = p => (p < 0.10 ? 1 : p < 0.25 ? 2 : p < 0.5 ? 3 : 4);
function qPass(m, k, n) {   // the whole record uses its level (computed on the unrounded estimate), the others their probability
  if (!k) return true;
  if (m === 'p') return QF.lv[n] >= 1 && QF.lv[n] <= 4 - k;
  const v = QF.val[m][n]; return v === v && v < Q_BOUND[k];
}
function qfApply() {   // the records of the current filter, per entry (shown records, sum of p) and in total (estimate of the chosen measure)
  const m = RVU.qm, k = RVU.qt, val = QF.val[m]; QF.on.fill(0); QF.shown = 0; QF.est = 0; QF.has = 0; QF.ents_on = 0;
  for (const s of RVS.values()) { s.qn = 0; s.qe = 0; }
  for (let i = 0; i < QF.nodes.length; i++) {
    const n = QF.nodes[i]; if (!qPass(m, k, n)) continue;
    QF.on[n] = 1; QF.shown++; const s = RVS.get(G.ent[QF.ents[i]].n); s.qn++;
    const p = QF.val.p[n]; if (p === p) s.qe += p;
    const v = val[n]; if (v === v) { QF.est += v; QF.has++; }
  }
  for (const s of RVS.values()) if (s.qn) QF.ents_on++;
}
const corpusOn = () => RVU.qt > 0;
const inCorpus = n => RVU.qt === 0 || QF.on[n] === 1;
const entryInCorpus = s => RVU.qt === 0 || s.qn > 0;
const qfKey = () => (RVU.qt ? RVU.qm + RVU.qt : '0');
const qfName = () => t('qf_ms_' + RVU.qm) + ' ' + t('qf_b_' + RVU.qt);
const qOf = n => { const r = QF.rec.get(n); return r && r.q ? r.q : null; };
const qPct = (p, d) => (p == null || p !== p ? '–' : (100 * p).toFixed(d == null ? 0 : d).replace('.', LANG === 'de' ? ',' : '.') + ' %');

// ---- the quality of one record: level chip, error risk, one badge per field
const Q_CLS = { ok: 'ok', one: 'one', c1: 'warn', c2: 'warn', both: 'bad', na: 'na' };
const qCoordCls = s => (s === 'rev' ? 'ok' : s === 'gaz-c1' ? 'bad' : s === 'none' || !s ? 'na' : 'warn');
function qCoordText(s) { if (!s || s === 'none') return t('qs_none'); const base = t('qs_' + s.replace('-c1', '')); return s.endsWith('-c1') ? base + '; ' + t('qs_flagged') : base; }
function qBadges(q, onlyDoubt) {
  const s = q.s || [], pf = q.pf || [], x = q.x || {}; let out = '';
  Q_FIELDS.forEach((f, i) => {
    const st = s[i] || 'na'; const cls = Q_CLS[st] || 'na';
    if (f === 'exists' && st === 'ok') return; if (onlyDoubt && cls !== 'warn' && cls !== 'bad') return;
    const tip = [t('qn_' + f) + ': ' + t('qs_' + st), t('ql_pf', qPct(pf[i], pf[i] < 0.1 ? 1 : 0)), x[Q_XKEY[i]] != null ? t('ql_x', String(x[Q_XKEY[i]])) : ''].filter(Boolean).join('\n');
    out += `<span class="qbg q-${cls}" data-f="${f}" title="${esc(tip)}">${esc(t('qn_' + f))}</span>`;
  });
  const cs = s[7] || 'none'; const cc = qCoordCls(cs);
  if (!onlyDoubt || cc === 'warn' || cc === 'bad') {
    const tip = [t('qn_coords') + ': ' + qCoordText(cs), q.pc != null ? t('ql_pf', qPct(q.pc)) : ''].filter(Boolean).join('\n');
    out += `<span class="qbg q-${cc}" data-f="coords" title="${esc(tip)}">${esc(t('qn_coords'))}</span>`;
  }
  return out;
}
function qChip(q, text) { const lv = q.lv || qLevelOf(q.p); return `<span class="qlv ql${lv}" title="${esc(t('ql_t_' + lv))}">${esc(text || t('ql_' + lv))}</span>`; }
function qualLine(n) {   // for cards, tooltips and the node view of a record
  const q = qOf(n); if (!q) return '';
  return `<div class="qline">${qChip(q)}<span class="qrisk">${esc(t('ql_risk', qPct(q.p)))}</span><span class="qbgs">${qBadges(q)}</span></div>`;
}
function qualCell(n) {   // the table: risk chip and the fields in doubt
  const q = qOf(n); if (!q) return '';
  return qChip(q, qPct(q.p)) + qBadges(q, true);
}
function qualRow(v) {   // property row of a record node: not a statement of the graph
  if (v.kind !== 'obs') return null; const q = qOf(v.n); if (!q) return null;
  const doubt = Q_FIELDS.map((f, i) => (Q_CLS[(q.s || [])[i]] === 'warn' || Q_CLS[(q.s || [])[i]] === 'bad' ? t('qn_' + f) : '')).filter(Boolean);
  if (qCoordCls((q.s || [])[7]) === 'bad' || ((q.s || [])[7] || '').endsWith('-c1')) doubt.push(t('qn_coords'));
  const key = t('ql_k'); const val = t('ql_risk_s', qPct(q.p)) + (doubt.length ? ', ' + t('ql_doubt', doubt.join(', ')) : '');
  return { k: key, kx: measure(key) + 5, v: fitText(val, v.w - 16 - measure(key) - 5, PFONT), cls: ' pq ql' + (q.lv || qLevelOf(q.p)) };
}
function rvQualSvg(v) {   // error risk of a record as a small pill in its header
  if (v.kind !== 'obs') return ''; const q = qOf(v.n); if (!q) return '';
  return `<g class="qpill ql${q.lv || qLevelOf(q.p)}" transform="translate(${v.w - 22},${Math.min(13, (v.hh || v.h) / 2)})"><rect x="-11" y="-6.5" width="22" height="13" rx="6.5"/><text y="3.1" text-anchor="middle">${Math.round(100 * q.p)}%</text></g>`;
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
function rvSrcOk(s) {   // under a filter: records that pass, entries with such a record, and what belongs to such an entry
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
  const s = RVS.get(r.n); return corpusOn() && s ? t('obs_of', fmt(s.qn), fmt(r.nobs)) : fmt(r.nobs) + ' ' + t('observations');
}
function outCount(m) { return corpusOn() ? m.obs.filter(o => !inCorpus(o.n)).length : 0; }
// ---- the bar: measure, threshold, live estimate
function qfLine() {   // "n of N records shown, of these about k wrong (x %)" for the chosen measure
  const m = RVU.qm; let s = t('qf_shown', fmt(QF.shown), fmt(QF.total));
  if (m === 'pc' && QF.has < QF.shown) s += ', ' + t('qf_with_coords', fmt(QF.has));
  return s + ', ' + t('qf_est_' + m, fmt(Math.round(QF.est)), qPct(QF.has ? QF.est / QF.has : NaN, 1));
}
function renderQBar() {   // always visible under the header, in every view
  const bar = $('#qbar'); if (!bar) return; const m = RVU.qm, k = RVU.qt;
  const sel = `<select id="qmsel" aria-label="${esc(t('qf_m_t'))}" title="${esc(t('qf_m_t'))}">${Q_MEASURES.map(x => `<option value="${x}"${x === m ? ' selected' : ''}>${esc(t('qf_m_' + x))}</option>`).join('')}</select>`;
  const seg = [0, 1, 2, 3].map(i => `<button type="button" class="qb${i === k ? ' on' : ''}" data-qt="${i}" aria-pressed="${i === k}" title="${esc(i ? t('qf_bt', t('qf_b_' + i).replace('< ', ''), t('qf_ms_' + m)) + (m === 'pc' ? t('qf_bt_pc') : '') : t('qf_bt_0'))}"><span class="qbn">${esc(t('qf_b_' + i))}</span><span class="qbc num">${fmt(QF.cnt[m][i])}</span></button>`).join('');
  bar.classList.toggle('active', corpusOn());
  bar.innerHTML = `<span class="qbl" title="${esc(t('qf_label_t'))}">${t('qf_label')}</span>${sel}<span class="qseg" role="group" aria-label="${esc(t('qf_label'))}">${seg}</span>` +
    `<span class="qest" title="${esc(t('qf_est_t'))}">${esc(qfLine())}</span>`;
}
function qBarWire() {
  const bar = $('#qbar');
  bar.addEventListener('click', ev => { const b = ev.target.closest('[data-qt]'); if (b) setQFilter(null, +b.dataset.qt); });
  bar.addEventListener('change', ev => { if (ev.target.id === 'notesw') setNotes(ev.target.checked); else if (ev.target.id === 'qmsel') setQFilter(ev.target.value, null); });
}
function setNotes(on) {   // explorer build: "Prüfhinweise zeigen" — off = the graph as it is, without findings, changes, ghost nodes
  if (!EXPLORER) return;
  RVU.notes = !!on; store('notes', on ? '1' : '0'); LVC.clear();
  if (!queueList().includes(RVU.queue)) { RVU.queue = 'all'; store('queue', 'all'); }
  countQueues(); renderQBar(); renderChips(); rvRenderList();
  if (S.view === 'entry') EM = null;
  route(); rvResize(); if (S.view === 'entry') fitView();
}
function setQFilter(m, k) {
  const before = qfKey();
  if (m != null && Q_MEASURES.includes(m)) RVU.qm = m;
  if (k != null) RVU.qt = clamp(+k || 0, 0, 3);
  store('qm', RVU.qm); store('qt', String(RVU.qt)); qfApply();
  if (qfKey() === before && !corpusOn()) { renderQBar(); return; }   // a new measure without a threshold changes the estimate only
  RVU.showOut = false; G.stats = null; NV.rows = null; CV.rows = null; LVC.clear(); const ov = $('#x-ov'); if (ov) ov.dataset.lang = '';
  countQueues(); renderQBar(); renderChips(); rvRenderList();
  if (S.view === 'entry') EM = null;   // the model keeps no filter state, but the cards and the head do
  route(); rvResize(); if (S.view === 'entry') fitView();
  // a selected record that the filter hides is no longer highlighted on the scan
  if (S.view === 'entry' && S.sel && S.sel[0] === 'n' && kindOf(+S.sel.slice(1)) === 'obs' && !inCorpus(+S.sel.slice(1)) && !RVU.showOut) selectKey(null);
}
// ---- overview: levels, status per field, audited error per status
function qualityCardHtml() {
  const qm = (R.meta || {}).quality || {}; const lvN = [0, 0, 0, 0, 0], lvE = [0, 0, 0, 0, 0];
  const st = Q_FIELDS.map(() => ({})); const cs = {};
  for (const n of QF.nodes) {
    if (!inCorpus(n)) continue; const q = qOf(n); if (!q) continue; const lv = q.lv || qLevelOf(q.p); lvN[lv]++; lvE[lv] += q.p;
    Q_FIELDS.forEach((f, i) => { const s = (q.s || [])[i] || 'na'; st[i][s] = (st[i][s] || 0) + 1; });
    const c = (q.s || [])[7] || 'none'; cs[c] = (cs[c] || 0) + 1;
  }
  const tot = lvN.reduce((a, b) => a + b, 0), totE = lvE.reduce((a, b) => a + b, 0);
  const share = (a, b) => (b ? qPct(a / b, 1) : '–');
  let s = `<table class="t covt qlt"><tr><th>${t('ovq_level')}</th><th class="r">${t('ovq_rec')}</th><th class="r">${t('ovq_share')}</th><th class="r">${t('ovq_exp')}</th></tr>` +
    [1, 2, 3, 4].map(lv => `<tr><td><span class="qlv ql${lv}">${esc(t('ql_' + lv))}</span> <span class="muted">${esc(t('ql_r_' + lv))}</span></td><td class="num r">${fmt(lvN[lv])}</td><td class="num r muted">${share(lvN[lv], tot)}</td><td class="num r">${fmt(Math.round(lvE[lv]))} <span class="muted">${share(lvE[lv], lvN[lv])}</span></td></tr>`).join('') +
    `<tr class="tot"><td>${t('lvt_sum')}</td><td class="num r">${fmt(tot)}</td><td class="num r muted"></td><td class="num r">${fmt(Math.round(totE))} <span class="muted">${share(totE, tot)}</span></td></tr></table>`;
  const aud = qm['audited error % per status'] || {};
  const audCell = (f, k) => { const a = (aud[f] || {})[k]; return a ? `<td class="num r${a.audited < 5 ? ' muted' : ''}" title="${esc(t('ovq_aud_n', fmt(a.audited)))}">${qPct(a['error %'] / 100, a['error %'] < 10 ? 1 : 0)}</td>` : `<td class="num r muted">–</td>`; };
  const head = keys => keys.map(k => `<th class="r" title="${esc(t('qs_' + k.replace('-c1', '')) + (k.endsWith('-c1') ? '; ' + t('qs_flagged') : ''))}">${esc(t('ovq_s_' + k.replace('-', '_')))}</th>`).join('');
  s += `<h3 class="qh">${t('ovq_status')}</h3><table class="t covt qst"><tr><th>${t('ovq_field')}</th>${head(Q_STATUS)}</tr>` +
    Q_FIELDS.map((f, i) => `<tr><td>${esc(t('qn_' + f))}</td>${Q_STATUS.map(k => `<td class="num r"><span class="qdot q-${Q_CLS[k]}"></span>${st[i][k] ? fmt(st[i][k]) : '<span class="muted">–</span>'}</td>`).join('')}</tr>`).join('') + '</table>';
  s += `<h3 class="qh">${t('ovq_audit')}</h3><table class="t covt qst"><tr><th>${t('ovq_field')}</th>${head(Q_STATUS)}</tr>` +
    Q_FIELDS.map(f => `<tr><td>${esc(t('qn_' + f))}</td>${Q_STATUS.map(k => audCell(f, k)).join('')}</tr>`).join('') + '</table>';
  s += `<h3 class="qh">${t('qn_coords')}</h3><table class="t covt qst"><tr><th></th>${head(Q_COORDS)}</tr>` +
    `<tr><td>${t('ovq_rec')}</td>${Q_COORDS.map(k => `<td class="num r"><span class="qdot q-${qCoordCls(k)}"></span>${cs[k] ? fmt(cs[k]) : '<span class="muted">–</span>'}</td>`).join('')}</tr>` +
    `<tr><td>${t('ovq_audit_s')}</td>${Q_COORDS.map(k => (k === 'none' ? '<td class="num r muted">–</td>' : audCell('coords', k))).join('')}</tr></table>`;
  const cal = qm['cross-validated calibration'] || {};
  const how = `<p class="muted qhow">${esc(t('ovq_how', fmt(qm['audit records used'] || 0)))}${cal['any: predicted'] != null ? ' ' + esc(t('ovq_cal', qPct(cal['any: predicted'] / 100, 1), qPct(cal['any: observed'] / 100, 1))) : ''}</p>`;
  return how + s;
}
