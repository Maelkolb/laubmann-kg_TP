/* Graph-Prüfung — work list (queues, levels), entry head, annotation layer of the subgraph, ghost nodes,
   the entry text with reading corrections, the review overview. The records table is in gc_table.js. */

// ------------------------------------------------------------------ work list
const ROW_H = 44;
function queueScore(s, q) { return q === 'risk' ? s.qe : q === 'finding' ? s.find.length + s.miss.length : q === 'auto' ? s.auto.length : q === 'tc' ? s.tc.length : q === 'qa' ? s.qa.length : q === 'ins' ? s.unread * 1000 + s.ins : q === 'img' ? s.img : 0; }
function listRows() {   // entries of the queue and the corpus, filtered by level, volume and text, sorted
  const q = RVU.queue, vol = RVU.vol; const f = $('#efilter').value.trim().toLowerCase(); const out = [];
  for (const r of G.ent) {
    const s = RVS.get(r.n); if (!inQueue(s, q)) continue; if (!levelOk(s)) continue; if (vol !== 'all' && String(r.vol) !== vol) continue;
    if (f && !(r.id + ' ' + r.date + ' ' + (pref(r.n, 'dwc:verbatimEventDate') || '') + ' ' + entryPlaceLabel(r)).toLowerCase().includes(f)) continue;
    out.push(r);
  }
  // gravity first: most open schwer, then mittel, then leicht; Array.sort is stable, equal entries keep the diary order
  // error risk first (the queue "nach Fehlerrisiko" always): the expected number of wrong records among those shown
  if (q === 'risk' || RVU.sort === 'risk') out.sort((a, b) => RVS.get(b.n).qe - RVS.get(a.n).qe);
  else if (RVU.sort === 'score') out.sort((a, b) => { const sa = RVS.get(a.n), sb = RVS.get(b.n); const x = openLevels(sa), y = openLevels(sb); return (y[3] - x[3]) || (y[2] - x[2]) || (y[1] - x[1]) || (queueScore(sb, q) - queueScore(sa, q)); });
  else if (q === 'ins') out.sort((a, b) => (RVS.get(b.n).unread > 0) - (RVS.get(a.n).unread > 0));
  return out;
}
function renderChips() {
  const c = RVU.counts;
  if (EXPLORER) { $('#qchips').innerHTML = xListOptionHtml(); $('#lvchips').innerHTML = ''; return; }
  // explorer build: the queues are filters — the number of entries, nothing "open"
  $('#qchips').innerHTML = queueList().map(q => `<button class="qchip${q === RVU.queue ? ' on' : ''}" data-q="${q}" title="${esc(t('qt_' + q))}"><i class="qd qd-${q}"></i><span class="ql">${t('q_' + q)}</span><span class="qn num">${q === 'done' || EXPLORER ? fmt(c[q].n) : fmt(c[q].open)}</span>${q === 'done' || EXPLORER ? '' : `<span class="qt num">/ ${fmt(c[q].n)}</span>`}</button>`).join('');
  renderLvChips();
}
function renderLvChips() {   // level filter, combinable with the queue: entries with an open item of the chosen level(s)
  const box = $('#lvchips'); if (!box) return; const cnt = [0, 0, 0, 0];
  if (!RVU.notes) { box.innerHTML = ''; return; }
  for (const s of RVS.values()) { if (!inQueue(s, RVU.queue)) continue; const c = openLevels(s); for (const lv of LEVELS) if (c[lv]) cnt[lv]++; }
  box.innerHTML = LEVELS.map(lv => `<button class="lvchip lv${lv}${RVU.lvf.has(lv) ? ' on' : ''}" data-lv="${lv}" title="${esc(t('lvf_chip_t', lvName(lv), fmt(cnt[lv])))}">${lvDot(lv)}${lvName(lv)}<span class="num">${fmt(cnt[lv])}</span></button>`).join('') +
    (RVU.lvf.size ? `<button class="lvchip clr" data-lv="0" title="${esc(t('lvf_clear'))}">×</button>` : '');
}
function listFoot() {
  const c = RVU.counts[RVU.queue] || { n: 0, open: 0 };
  $('#elist-foot').textContent = (EXPLORER ? t('list_foot_x', fmt((RVU.list || []).length)) : t('list_foot', fmt((RVU.list || []).length), RVU.queue === 'done' ? fmt(c.n) : fmt(c.open))) + (corpusOn() ? ', ' + qfName() : '');
}
function rvRenderList(keep) {
  const body = $('#elist-body'); body.dataset.lang = LANG;
  RVU.list = listRows(); RVU.listPos = new Map(RVU.list.map((r, i) => [r.n, i]));
  $('#elist-pad').style.height = RVU.list.length * ROW_H + 'px';
  if (!keep) { const i = RVU.listPos.get(S.e); body.scrollTop = i === undefined ? 0 : rowTop(i, body); }
  drawList(); listFoot();
}
function listRowHtml(r, i) {
  if (EXPLORER) return xListRowHtml(r, i);
  const s = RVS.get(r.n); const chk = isChecked(s.uid); const c = openLevels(s); let b = '';
  if (RVU.notes) for (const lv of LEVELS) if (c[lv]) b += lvPill(lv, fmt(c[lv]), t('bt_lv', fmt(c[lv]), lvName(lv)));
  if (!EXPLORER && !chk && !c[1] && !c[2] && !c[3] && s.lv.some(keyInCorpus)) b += `<span class="bdg off" title="${esc(t('bt_alldone'))}">✓</span>`;
  if (s.ins) b += `<span class="bdg b-ins${s.unread ? '' : ' off'}" title="${esc(t('bt_ins', fmt(s.ins), fmt(s.unread)))}">¶</span>`;
  if (s.img) b += `<span class="bdg b-img" title="${esc(t('bt_img', fmt(s.img)))}">▣</span>`;
  if (chk) b += `<span class="bdg b-ok" title="${t('checked')}">✓</span>`;
  if ((RVU.queue === 'risk' || RVU.sort === 'risk') && s.qe > 0) b += `<span class="bdg b-risk" title="${esc(t('l_risk_t'))}">≈ ${esc(fmtRisk(s.qe))}</span>`;
  const n = corpusOn() ? `<span class="n" title="${esc(t('l_records_corp', fmt(s.qn), fmt(r.nobs), qfName()))}"><b>${fmt(s.qn)}</b> / ${fmt(r.nobs)}</span>` : `<span class="n" title="${t('l_records')}">${r.nobs ? fmt(r.nobs) : ''}</span>`;
  return `<div class="erow${r.n === S.e ? ' on' : ''}${chk ? ' chk' : ''}" data-e="${r.n}" style="top:${i * ROW_H}px"><span class="d">${esc(r.date || pref(r.n, 'dwc:verbatimEventDate') || r.id)}</span>${n}<span class="p">${esc(entryPlaceLabel(r))} <span class="muted mono">${esc(r.id)}</span></span><span class="b">${b}</span></div>`;
}
const fmtRisk = x => (x >= 10 ? fmt(Math.round(x)) : x.toFixed(1).replace('.', LANG === 'de' ? ',' : '.'));
function drawList() {
  const body = $('#elist-body'); const n = RVU.list.length; const top = body.scrollTop, h = body.clientHeight || 600;
  const a = Math.max(0, Math.floor(top / ROW_H) - 8), b = Math.min(n, Math.ceil((top + h) / ROW_H) + 8); let s = '';
  for (let i = a; i < b; i++) s += listRowHtml(RVU.list[i], i);
  $('#elist-pad').innerHTML = s || `<div class="muted" style="padding:12px">${t(RVU.lvf.size ? 'list_empty_lv' : 'list_empty')}</div>`;
}
const rowTop = (i, body) => Math.max(0, Math.round((i * ROW_H - body.clientHeight / 2 + ROW_H) / ROW_H) * ROW_H);   // the selected row in the middle, the list on whole rows
function markList() {
  const body = $('#elist-body'); const i = RVU.listPos ? RVU.listPos.get(S.e) : undefined;
  if (i !== undefined) { const y = i * ROW_H; if (y < body.scrollTop || y + ROW_H > body.scrollTop + body.clientHeight) body.scrollTop = rowTop(i, body); }
  drawList();
}
function renderVolSelect() {
  const sel_ = $('#volsel');
  if (EXPLORER) { xRenderVolSelect(sel_); return; }
  sel_.innerHTML = `<option value="all">${t('vol_all')}</option>` + G.vols.concat(G.entByVol.has(-1) ? [-1] : []).map(v => `<option value="${v}">${esc(volLabel(v).replace(/^Laubmann\s*·\s*/, ''))} · ${esc(pref(v, 'dcterms:temporal') || '')}</option>`).join('');
  sel_.value = RVU.vol;
  $('#qsort').innerHTML = (EXPLORER ? ['score', 'diary'] : ['score', 'risk', 'diary']).map(k => `<option value="${k}"${k === RVU.sort ? ' selected' : ''}>${t('sort_' + k)}</option>`).join('');
  $('#qsort').title = t('sort_t');
}
function stepEntry(d) {
  const list = RVU.list || []; if (!list.length) return; const i = RVU.listPos.get(S.e);
  const j = i === undefined ? 0 : i + d; if (j >= 0 && j < list.length) go(entryHash(list[j].n));
}
function rvQueuePos(e) { const i = RVU.listPos ? RVU.listPos.get(e) : undefined; return { pos: i === undefined ? -1 : i, n: (RVU.list || []).length, queue: RVU.queue }; }
function rvFirstEntry() { if (!RVU.list || !RVU.list.length) RVU.list = listRows(); return (RVU.list[0] || G.ent[0] || {}).n; }
function setQueue(q, open) {
  RVU.queue = q; store('queue', q); renderChips(); rvRenderList();
  if (open && RVU.list.length) { const cur = RVU.listPos.get(S.e); if (cur === undefined || S.view !== 'entry') { const first = RVU.list.find(r => isOpen(RVS.get(r.n), q)) || RVU.list[0]; go(entryHash(first.n)); return; } }
  if (S.view === 'entry') renderEntryHead();
}
function setLevelFilter(lv) {
  if (!lv) RVU.lvf.clear(); else if (RVU.lvf.has(lv)) RVU.lvf.delete(lv); else RVU.lvf.add(lv);
  store('lvf', [...RVU.lvf].join(',')); renderLvChips(); rvRenderList(); if (S.view === 'entry') renderEntryHead();
}
function rvWireList() {
  $('#qchips').addEventListener('click', ev => { const b = ev.target.closest('[data-q]'); if (b) setQueue(b.dataset.q, true); });
  $('#qchips').addEventListener('change', ev => { if (ev.target.id === 'onlyimg') setQueue(ev.target.checked ? 'img' : 'all', false); });
  $('#lvchips').addEventListener('click', ev => { const b = ev.target.closest('[data-lv]'); if (b) setLevelFilter(+b.dataset.lv); });
  $('#volsel').addEventListener('change', ev => { RVU.vol = ev.target.value; rvRenderList(); if (S.view === 'entry') renderEntryHead(); });
  $('#qsort').addEventListener('change', ev => { RVU.sort = ev.target.value; store('qsort', RVU.sort); rvRenderList(); if (S.view === 'entry') renderEntryHead(); });
  $('#efilter').addEventListener('input', debounce(() => { rvRenderList(); if (S.view === 'entry') renderEntryHead(); }, 140));
  $('#elist-body').addEventListener('scroll', () => { if (!drawList.raf) drawList.raf = requestAnimationFrame(() => { drawList.raf = 0; drawList(); }); });
  $('#elist-body').addEventListener('click', ev => { const r = ev.target.closest('.erow'); if (r) go(entryHash(+r.dataset.e)); });
  qBarWire();
  $('#gmore').addEventListener('click', () => panTo(1)); $('#gless').addEventListener('click', () => panTo(-1));
}

// ------------------------------------------------------------------ entering an entry, head, tools, legend
function rvEnterEntry(e, changed) {
  if (changed) { EM = null; RVU.form = null; RVU.card = 0; RVU.armed = false; RVU.hints = false; RVU.showOut = false; RVU.enter = !S.sel; S.tab = EXPLORER && S.tab !== 'check' ? 'text' : 'check'; S.propOpen.clear(); PCACHE.clear(); $('#gtip').hidden = true; }   // a new entry starts with its cards
  const m = entryModel(e);
  if (changed) { const items = visibleItems(m); RVU.card = Math.max(0, items.findIndex(it => !itemDecided(it) && it.type !== 'media' && (it.type !== 'ent' || it.lv >= 1))); }   // the gravest open item
  if (!RVU.listPos || $('#elist-body').dataset.lang !== LANG) { renderVolSelect(); renderChips(); rvRenderList(); } else markList();
  scanEnter(m, changed);
}
function rvHeadHtml(e, pos) {
  const m = entryModel(e); const chk = entryDec(m.uid).checked; const c = openByLevel(m); const n = c[1] + c[2] + c[3];
  const hints = c[0] ? `<span class="hh" title="${esc(t('open_hints_t'))}">+ ${esc(t('hints_n', fmt(c[0])))}</span>` : '';
  const state = !RVU.notes ? '' : chk ? `<span class="hstate ok">✓ ${t('checked')}</span>`
    : n ? `<span class="hstate open" title="${esc(t('open_t'))}"><span class="hl">${t('open_lbl')}</span>${LEVELS.filter(lv => c[lv]).map(lv => lvPill(lv, fmt(c[lv]) + ' ' + lvName(lv), t('bt_lv', fmt(c[lv]), lvName(lv)))).join('')}${hints}</span>`
      : `<span class="hstate">${t('no_open')}${hints}</span>`;
  const out = outCount(m);
  const corp = corpusOn() ? `<span class="hcorp" title="${esc(t('head_corp_t'))}">${esc(t('head_corp', qfName(), fmt(m.obs.length - out), fmt(m.obs.length)))}</span>` : '';
  return `<span class="seg" title="${t('mid_t')}"><button data-act="mid-graph" class="${RVU.mid === 'graph' ? 'on' : ''}">${t('mid_graph')}</button><button data-act="mid-table" class="${RVU.mid === 'table' ? 'on' : ''}">${t('mid_table')}</button></span>
    <button class="btn${RVU.scan ? ' on' : ''}" data-act="scan" title="${t('scan_toggle_t')}">${t('scan_btn')}</button>
    <button class="btn" data-copy="${esc(iriOf(e))}" title="${esc(iriOf(e))}">IRI</button>
    <span class="brk"></span><span class="muted hpos">${esc(pos || '')}</span><span class="sp"></span>${state}${corp}`;
}
function setMid(mode) {
  RVU.mid = mode; store('mid', mode); renderEntryHead(); renderTools(); rvRenderTable();
  if (mode === 'graph') fitView();
}
function rvHeadAct(a, el) {
  if (a === 'mid') setMid(RVU.mid === 'graph' ? 'table' : 'graph');
  else if (a === 'mid-graph' || a === 'mid-table') setMid(a.slice(4));
  else if (a === 'scan') scanToggle();
  else if (a === 'addrec') openForm('new', 'add');
  else if (a === 'tflag') { RVU.tflag = !RVU.tflag; renderTools(); rvRenderTable(); }
  else if (a === 'preset-std' || a === 'preset-all') setPreset(a === 'preset-all');
  else if (a === 'showout') { RVU.showOut = !RVU.showOut; renderTools(); renderGraph(false); rvRenderTable(); renderPanel(); }
  else if (a === 'cols') colChooser(el);
  else if (a === 'xlayers') { XT.layers = !XT.layers; renderTools(); }
}
function rvToolsHtml() {
  if (RVU.mid !== 'table') return false;
  const out = EM ? outCount(EM) : 0;
  $('#gtools').innerHTML = (RVU.notes ? `<span class="chip${RVU.tflag ? ' on' : ''}" data-act="tflag"><i style="background:var(--lv3)"></i>${t('t_only_flagged')}</span>` : '') +
    `<button class="zbtn wide" data-act="cols" title="${t('cols_t')}">${t('cols_btn')} ▾</button>${EXPLORER ? '' : `<button class="zbtn wide" data-act="addrec">${t('a_add_rec')}</button>`}` +
    (out ? `<span class="chip outchip${RVU.showOut ? ' on' : ''}" data-act="showout" title="${t('out_t')}"><i></i>${esc(t(RVU.showOut ? 'out_hide' : 'out_show', fmt(out)))}</span>` : '') +
    `<span class="sp"></span><span class="muted">${t('t_hint')}</span>`;
  $('#legend').innerHTML = rvLegendHtml();
  return true;
}
function rvLegendHtml() {   // colour = level, marker = kind; the pill of a record = its estimated error risk
  return (RVU.notes ? markLegendHtml() : '') + `<span class="li" title="${esc(t('lg_q_t'))}">${[1, 2, 3, 4].map(lv => `<span class="qlv ql${lv}">${esc(t('ql_r_' + lv))}</span>`).join('')}${t('lg_q')}</span>` +
    `<span class="li muted" title="${esc(t('lg_click') + ' · ' + t('zoom_hint'))}">ⓘ</span>`;
}
function rvHelpHtml() { if (EXPLORER) return t('help'); return t('help') + `<p>${t('ar_help')}</p><h3>${t('help_q')}</h3><p>${t('help_q_body')}</p>` + (RVU.notes ? `<h3>${t('help_sev')}</h3>` + sevTableHtml() + `<p class="muted" style="font-size:.8rem">${t('sev_note')}</p>` : ''); }
function rvFilterNote(block) {   // node view, class view: the counts follow the reliability filter
  if (!corpusOn()) return ''; const s = esc(t('filter_note', qfName(), fmt(QF.shown), fmt(QF.total)));
  return block ? `<div class="note qfnote">${s}</div>` : ` <span class="qftag">${s}</span>`;
}

// ------------------------------------------------------------------ annotation layer of the subgraph
// {cls: 'lv3' | 'lv2' | 'lv1' | 'lv0' | 'dec', lv, mk: marker, tip, strike}
const DEC = (tip, mk, strike) => ({ cls: 'dec', mk: mk || '✓', tip, strike: !!strike });
const OPEN = (it, tip, mk, strike) => ({ cls: 'lv' + it.lv, lv: it.lv, mk: mk || it.mk || '!', tip, strike: !!strike });
function recAnn(m, o) {
  const d = RV.dec[o.key];
  if (d && d.d) return d.d === 'x' ? DEC('tip_dropped', '✓', true) : d.d === 'u' ? DEC('tip_unsure', '?') : DEC('tip_ok');
  if (isChecked(m.uid)) return DEC('tip_checked');
  const it = m.itemByObs.get(o.n); if (!it || !it.lv) return null;
  return OPEN(it, it.mk === 'M' ? 'tip_auto' : it.mk === '?' ? 'tip_munsure' : 'tip_err');
}
function rvAnn(v) {
  const m = EM; if (!m || m.e !== S.e || !RVU.notes) return null;
  if (v.kind === 'obs') { const o = m.byNode.get(v.n); return o ? recAnn(m, o) : null; }
  if (v.kind === 'group') {
    let best = 0, open = 0, dec = 0, n = 0;
    for (const x of v.members) { const o = m.byNode.get(x); const a = o && recAnn(m, o); n++; if (!a) continue; if (a.lv) { open++; best = Math.max(best, a.lv); } else dec++; }
    return open ? { cls: 'lv' + best, lv: best, mk: String(open), tip: 'tip_group_err' } : dec === n && n ? DEC('tip_ok') : null;
  }
  if (v.kind === 'miss' || v.kind === 'gone') {
    const it = m.items.find(x => x.key === v.item) || { lv: 1 }; const d = RV.dec[v.item];
    if (v.kind === 'miss') return d && d.d === 'add' ? DEC('tip_added') : d && d.d === 'no' ? DEC('tip_notadded', '✓', true) : isChecked(m.uid) ? DEC('tip_checked') : OPEN(it, 'tip_missing', '?');
    return d && d.d ? DEC(d.d === 'confirm' ? 'tip_gone_ok' : 'tip_gone_back', '✓', d.d === 'confirm') : OPEN(it, 'tip_gone', '×', true);
  }
  if (v.kind === 'entry') {
    const d = entryDec(m.uid); if (d.checked) return DEC('tip_checked');
    if (d.date || d.kind || d.place || d.hdr) return DEC('tip_ok');
    const it = m.items.find(x => x.type === 'ent'); return it && it.lv ? OPEN(it, 'tip_ent', '!') : null;
  }
  if (v.kind === 'taxon' || v.kind === 'place' || v.kind === 'person' || v.kind === 'habitat') {
    let best = null; const rank = a => (a.cls === 'dec' ? 0.5 : a.lv + 1);
    for (const it of m.items) {
      if (it.type !== 'name' || !it.x.nodes.has(v.n)) continue; const d = RV.dec[it.key];
      const a = d && d.d ? DEC('tip_ok') : isChecked(m.uid) ? DEC('tip_checked') : OPEN(it, it.x.kind === 'changed' ? 'tip_name_changed' : it.x.kind === 'suggest' ? 'tip_name_sugg' : 'tip_name_conf');
      if (!best || rank(a) > rank(best)) best = a;
    }
    return best;
  }
  return null;
}
const rvOutCls = v => (v.kind === 'obs' && corpusOn() && !inCorpus(v.n) ? ' out' : '');
function rvRingSvg(v, an) {   // the ring carries the level; hints (level 0) have a marker only
  if (an.cls === 'lv0') return '';
  return `<rect class="ring ${an.cls}${an.strike ? ' strike' : ''}" x="-4" y="-4" width="${v.w + 8}" height="${v.h + 8}" rx="${Math.min(v.kind === 'obs' || v.kind === 'entry' || v.kind === 'group' ? 9 : 16, ((v.hh || v.h) + 8) / 2)}"/>`;
}
function rvBadgeSvg(v, an) { const w = an.mk.length > 1 ? 11 : 8; return `<g class="abadge ${an.cls}" transform="translate(${v.w - 3},-2)"><rect x="${-w}" y="-8" width="${2 * w}" height="16" rx="8"/><text y="3.6" text-anchor="middle">${esc(an.mk)}</text></g>`; }
function rvTipHtml(v) {
  const an = rvAnn(v); let s = archiveTip(v);
  if (an) s += `<div class="antip ${an.cls}">${an.lv != null ? lvDot(an.lv) + esc(lvName(an.lv)) + SEP : ''}${esc(t(an.tip))}</div>`;
  if (v.kind === 'obs') s += qualLine(v.n);
  if (SUB && SUB.propMode === 'compact' && S.sel !== v.key) s += propsTip(v);
  return s;
}
function rvGhosts(e, add, link, ev, records) {   // what the graph lacks (suggested) or lost (removed), as ghost nodes
  if (!RVU.notes) return;
  const m = entryModel(e);
  m.items.forEach((it, i) => {
    let v = null;
    if (it.type === 'miss' && it.x.kind === 'observation') { const d = RV.dec[it.key]; v = add(-1, 2, { key: 'm:' + i, kind: 'miss', label: ((d && d.rec && d.rec.species_de) || it.x.de || '?') + ' · ' + t('ghost_missing'), sub: (d && d.rec ? d.rec.count : it.x.count) || '', item: it.key }); link(ev, v, 'rv:missing'); }
    else if (it.type === 'qa' && it.q[1] === 'excluded') { v = add(-1, 2, { key: 'x:' + i, kind: 'gone', label: it.q[2] || qaLabel(it.q[0]), sub: qaLabel(it.q[0]), item: it.key }); link(ev, v, 'rv:removed'); }
    else if (it.type === 'name' && it.x.kind === 'removed') { v = add(-1, it.x.section === 'taxa' ? 2 : 4, { key: 'x:' + i, kind: 'gone', label: it.x.form, sub: t('ghost_removed', t('kind_' + KIND_OF_SECTION[it.x.section])), item: it.key }); link(ev, v, 'rv:removed'); }
    if (v && v.col === 2) records.push(v);
  });
}

// ------------------------------------------------------------------ entry text with reading corrections
// what the graph holds at a correction's place (review layer tc[12]; older layers: what the reading stage left there),
// and whether the machine layer of the text changed it (tc[13]: the checks' better reading, the scan agent's correction)
const tcNow = c => (c.length > 12 ? c[12] || '' : c[2] ? c[1] : c[0]);
const tcAtNow = (fn, c) => { const cur = tcNow(c); return cur && c[3] >= 0 && fn.substr(c[3], cur.length) === cur ? c[3] : -1; };
const tcMachine = c => !!c[13];
function tcState(m, c, key) {
  const d = RV.dec[key]; if (d && d.d) return d.d === 'accept' ? 'acc' : d.d === 'reject' ? 'rej' : 'edt';
  if (tcMachine(c)) return 'mach';
  if (['markup', 'punctuation', 'case'].includes(c[4]) && !c[5]) return 'minor';
  const vs = [c[6], c[7]]; return vs.includes('wrong') ? 'wrong' : vs.includes('partly') || vs.includes('unclear') ? 'partly' : vs.includes('right') ? 'right' : 'open';
}
function tcTip(c, d) {   // hover text of a correction in the entry text: the checks' verdicts, their better reading, the decision
  const out = [];
  if (c[6]) out.push(srcName('s') + ': ' + t('tcv_' + c[6])); if (c[7]) out.push(srcName('g') + ': ' + t('tcv_' + c[7]));
  if (c[8]) out.push(t('tc_better') + ' „' + c[8] + '“');
  if (d && d.d) out.push(t('mine') + ': ' + t('d_tc_' + (d.how === 'better' ? 'better' : d.d)));
  return out.join('; ');
}
function textSpans(m) {   // {fn, tcAt, obsAt}: which reading correction / record passage covers each character
  const e = m.e; const fn = pref(e, 'dwc:fieldNotes') || ''; const n = fn.length; const tcAt = new Int32Array(n).fill(-1), obsAt = new Int32Array(n).fill(-1);
  (RVU.notes ? m.rv.tc || [] : []).forEach((c, i) => {
    if (TC_FIELD.test(c[0] || '')) return;
    const p = tcAtNow(fn, c); const cur = tcNow(c);
    if (p < 0 || (cur === c[0] && !tcMachine(c))) return;   // the transcription stands here unchanged: nothing to mark
    for (let j = p; j < p + cur.length; j++) if (tcAt[j] < 0) tcAt[j] = i;
  });
  for (const [o, h] of textPos(e)) if (h) for (let j = h[0]; j < h[0] + h[1] && j < n; j++) if (obsAt[j] < 0) obsAt[j] = o;
  return { fn, tcAt, obsAt };
}
const inText = s => esc(s).replace(/&lt;(\/?)u&gt;/g, '<$1u>');
function locateIn(text, old, taken, whole) {   // first occurrence of old outside the taken ranges (whole: as a whole word, whitespace tolerant, as the pipeline locates it)
  const q = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const isWord = ch => !!ch && /[\p{L}\p{N}]/u.test(ch);
  const pats = whole ? [q(old), old.split(/\s+/).filter(Boolean).map(q).join('\\s+')] : [q(old)];
  for (const pat of pats) {
    if (!pat) continue; const re = new RegExp(pat, 'gu'); let hit;
    while ((hit = re.exec(text))) {
      const a = hit.index, b = a + hit[0].length; if (b === a) { re.lastIndex++; continue; }
      if (whole && ((isWord(old[0]) && isWord(text[a - 1])) || (isWord(old[old.length - 1]) && isWord(text[b])))) continue;
      if (!taken.some(([x, y]) => a < y && b > x)) return [a, b];
    }
  }
  return null;
}
function textEdits(m, fn, tcAt) {   // the reviewer's decisions over the graph text, in text order: {a, b, text, tc, key, was, kept, by}
  const out = []; const taken = [];
  if (EXPLORER) return out;
  const marked = []; for (let i = 0; i < fn.length; i++) if (tcAt[i] >= 0 && (i === 0 || tcAt[i - 1] !== tcAt[i])) { let j = i; while (j < fn.length && tcAt[j] === tcAt[i]) j++; marked.push([i, j]); }
  const add = (a, b, text, x) => { if (taken.some(([p, q]) => a < q && b > p)) return; taken.push([a, b]); out.push(Object.assign({ a, b, text }, x)); };
  (m.rv.tc || []).forEach((c, i) => {
    if (TC_FIELD.test(c[0] || '')) return;   // a header field, not the text
    const key = 'tc:' + m.uid + '|' + c[0] + '|' + c[1]; const d = RV.dec[key]; if (!d || !d.d) return;
    const fin = d.d === 'reject' ? c[0] : d.d === 'edit' ? d.final || '' : c[1];
    const cur = tcNow(c); const p = tcAtNow(fn, c);
    if (p >= 0) add(p, p + cur.length, fin, { tc: i, key, was: cur, kept: fin === cur, by: 'mine' });   // where the graph holds this correction
    else if (fin !== c[0]) {   // the graph holds the old text: the pipeline applies the decision where it stands
      const hit = locateIn(fn, c[0], taken.concat(marked), true);
      if (hit) add(hit[0], hit[1], fin, { tc: i, key, was: fn.slice(hit[0], hit[1]), by: 'mine' });
    }
  });
  for (const k of Object.keys(RV.dec)) if (k.startsWith('txt:' + m.uid + '|')) {   // own text corrections: the first occurrence, as the pipeline replaces it
    const d = RV.dec[k]; const hit = d && d.ref ? locateIn(fn, d.ref.old, taken.concat(marked), false) : null;
    if (hit) add(hit[0], hit[1], d.new, { key: k, was: d.ref.old, own: true, by: 'mine' });
  }
  return out.sort((x, y) => x.a - y.a);
}
function editTip(x, c) {
  const was = x.kept ? '' : t('tc_before') + ' „' + x.was.replace(/<\/?u>/g, '') + '“';
  return [was, x.own ? t('txt_own') : c ? tcTip(c, RV.dec[x.key]) : ''].filter(Boolean).join('; ');
}
function originalText(m) {   // the transcription before the reading stage: every correction the graph holds taken back
  const fn = pref(m.e, 'dwc:fieldNotes') || ''; let s = fn;
  const back = (m.rv.tc || []).map(c => [tcAtNow(fn, c), c]).filter(([p, c]) => p >= 0 && tcNow(c) !== c[0] && !TC_FIELD.test(c[0] || '')).sort((x, y) => y[0] - x[0]);
  let end = Infinity;
  for (const [p, c] of back) { const cur = tcNow(c); if (p + cur.length > end) continue; s = s.slice(0, p) + c[0] + s.slice(p + cur.length); end = p; }
  return s;
}
function correctedPlain(m) {   // the corrected text without marks
  const { fn, tcAt } = textSpans(m); let s = '', i = 0;
  for (const x of textEdits(m, fn, tcAt)) { s += fn.slice(i, x.a) + x.text; i = x.b; }
  return s + fn.slice(i);
}
function textHtml(m) {   // the corrected text: the graph text with the machine layer and the reviewer's decisions
  if (EXPLORER) return inText(correctedPlain(m));   // the explorer: the corrected text without marks
  if (RVU.textLayer === 'orig') return inText(originalText(m));
  const { fn, tcAt, obsAt } = textSpans(m); const n = fn.length; const tcs = m.rv.tc || [];
  const edits = textEdits(m, fn, tcAt); let ei = 0; const selN = S.sel && S.sel[0] === 'n' ? +S.sel.slice(1) : -1;
  const isTag = j => fn.charCodeAt(j) === 60 && (fn.startsWith('<u>', j) || fn.startsWith('</u>', j));
  let s = '', i = 0, u = false;
  while (i < n) {
    if (ei < edits.length && edits[ei].a === i) {   // a passage the reviewer decided: the reading that stands
      const x = edits[ei++]; const c = x.tc != null ? tcs[x.tc] : null;
      s += `<span data-s="${i}" class="tci k-${x.by}${u ? ' u' : ''}"${x.tc != null ? ` data-tc="${x.tc}"` : ''} title="${esc(editTip(x, c))}">${inText(x.text)}</span>`;
      for (let j = i; j < x.b; j++) if (isTag(j)) u = fn[j + 1] === 'u';
      i = x.b; continue;
    }
    if (isTag(i)) { u = fn[i + 1] === 'u'; i += u ? 3 : 4; continue; }   // underline markup of the transcription
    const tc = tcAt[i], ob = obsAt[i]; const stop = ei < edits.length ? edits[ei].a : n; let j = i + 1;
    while (j < n && j < stop && tcAt[j] === tc && obsAt[j] === ob && !isTag(j)) j++;
    const cls = []; let attr = '';
    if (tc >= 0) { const c = tcs[tc]; const key = 'tc:' + m.uid + '|' + c[0] + '|' + c[1]; const st = tcState(m, c, key);
      cls.push('tci', tcMachine(c) ? 'k-check' : st === 'wrong' || st === 'partly' ? 'k-contested' : st === 'minor' ? 'k-minor' : 'k-machine'); attr += ` data-tc="${tc}" title="${esc(t('tc_before') + ' „' + c[0].replace(/<\/?u>/g, '') + '“; ' + tcTip(c))}"`; }
    if (ob >= 0) { cls.push('m'); if (ob === selN) cls.push('on'); attr += ` data-obs="${ob}"`; }
    if (u) cls.push('u');
    s += `<span data-s="${i}"${cls.length ? ` class="${cls.join(' ')}"` : ''}${attr}>${esc(fn.slice(i, j))}</span>`;
    i = j;
  }
  return s;
}
function rvTextBlock(e) {
  const m = entryModel(e); const own = Object.keys(RV.dec).filter(k => k.startsWith('txt:' + m.uid + '|'));
  const unloc = (m.rv.tc || []).filter(c => c[2] && c[3] < 0).length;
  const body = textHtml(m); const orig = !EXPLORER && RVU.textLayer === 'orig';
  const ed = EXPLORER ? [] : textEdits(m, textSpans(m).fn, textSpans(m).tcAt);
  const mine = ed.filter(x => x.by === 'mine' && !x.kept).length;
  const check = EXPLORER ? 0 : (m.rv.tc || []).filter(c => tcMachine(c) && tcAtNow(textSpans(m).fn, c) >= 0).length;
  const layer = EXPLORER ? '' : `<span class="seg tlayer" title="${esc(t('tlayer_t'))}"><button data-act="tlayer" data-layer="final" class="${orig ? '' : 'on'}">${t('tlayer_final')}</button><button data-act="tlayer" data-layer="orig" class="${orig ? 'on' : ''}">${t('tlayer_orig')}</button></span>`;
  let s = `<h3 class="sec" style="margin-top:0">${t('field_notes')}<span class="sp"></span>${layer}${EXPLORER || orig ? '' : `<button class="btn" data-act="txtedit" title="${t('txt_edit_t')}">${t('txt_edit')}</button>`}</h3>` +
    (EXPLORER || orig ? '' : `<div class="tlegend"><span class="tci k-machine">${t('tl_corr')}</span><span class="tci k-contested">${t('tl_wrong')}</span><span class="tci k-check">${esc(t('tl_check', fmt(check)))}</span><span class="tci k-mine">${esc(t('tl_mine', fmt(mine)))}</span><span class="m">${t('tl_rec')}</span></div>`) +
    `<div class="fieldnotes" id="fnotes">${body || `<span class="muted">${t('no_text')}</span>`}</div>`;
  if (unloc && !EXPLORER && !orig) s += `<p class="muted gnote">${esc(t('tc_unlocated', fmt(unloc)))}</p>`;
  if (RVU.form && RVU.form.kind === 'txt') s += `<div class="rcard focus">${formHtml(m, { key: 'txt' })}</div>`;
  if (own.length) s += `<h3 class="sec">${t('txt_own')}</h3>` + own.map(k => { const d = RV.dec[k]; return `<div class="tcdiff own"><del>${markup(d.ref.old)}</del><span class="arr">→</span><ins>${markup(d.new)}</ins><span class="link reset" data-act="txtdel" data-key="${esc(k)}">${t('reset')}</span></div>`; }).join('');
  return s;
}
function rvTextWire(body) { const f = $('.rform', body); if (f && RVU.form && !RVU.form.shown) { RVU.form.shown = true; wireForm(f); } }
function textEditStart() {   // the selected passage of the entry text -> form for the reviewer's own reading
  const box = $('#fnotes'); const sl = window.getSelection(); const m = EM;
  if (!box || !sl || sl.isCollapsed || !box.contains(sl.anchorNode) || !box.contains(sl.focusNode)) { toast(t('txt_select'), 3500); return; }
  const off = (node, o) => { const sp = (node.nodeType === 3 ? node.parentNode : node).closest('[data-s]'); if (!sp || sp.tagName === 'DEL') return null; return +sp.dataset.s + (node.nodeType === 3 ? o : 0); };
  const inTc = nd => { const el = nd.nodeType === 3 ? nd.parentNode : nd; return !!(el.closest && el.closest('del, .tci')); };
  if (inTc(sl.anchorNode) || inTc(sl.focusNode)) { toast(t('txt_overlap'), 4500); return; }
  let a = off(sl.anchorNode, sl.anchorOffset), b = off(sl.focusNode, sl.focusOffset); if (a == null || b == null) { toast(t('txt_select'), 3500); return; }
  if (a > b) [a, b] = [b, a];
  const { fn, tcAt } = textSpans(m); while (a < b && /\s/.test(fn[a])) a++; while (b > a && /\s/.test(fn[b - 1])) b--;
  if (b <= a) { toast(t('txt_select'), 3500); return; }
  for (let j = a; j < b; j++) if (tcAt[j] >= 0) { toast(t('txt_overlap'), 4500); return; }
  RVU.form = { key: 'txt', kind: 'txt', old: fn.slice(a, b) }; renderPanel();
}

// ------------------------------------------------------------------ overview, progress
function layerStats() {
  if (R._stats) return R._stats; const st = { ent: G.ent.length, rec: 0, entG: 0, entS: 0, recG: 0, recS: 0, flagG: 0, flagS: 0, miss: 0, tc: 0, tcRel: 0, names: 0, namesChanged: 0 };
  for (const r of G.ent) { const rv = R.entries[r.id]; st.rec += r.nobs; if (!rv) continue; if ((rv.chk || '').includes('g')) st.entG++; if ((rv.chk || '').includes('s')) st.entS++;
    for (const k in rv.rec || {}) { const x = rv.rec[k]; if (x.g) { st.recG++; if (x.g.v === 'wrong' || x.g.v === 'spurious') st.flagG++; } if (x.s) { st.recS++; if (x.s.v === 'wrong' || x.s.v === 'spurious') st.flagS++; } }
    st.miss += (rv.miss || []).filter(x => x.kind === 'observation').length; for (const c of rv.tc || []) { st.tc++; if (c[2] && c[5]) st.tcRel++; } }
  for (const k in R.names) { const kd = nameKind(k, R.names[k]); if (kd !== 'same') st.names++; if (kd === 'changed' || kd === 'removed') st.namesChanged++; }
  R._stats = st; return st;
}
function progressStats() {
  const p = { checked: 0, ok: 0, corrected: 0, dropped: 0, added: 0, unsure: 0, names: 0, tc: 0, qa: 0, total: 0 };
  for (const k in RV.dec) { const d = RV.dec[k]; const ty = k.slice(0, k.indexOf(':'));
    if (ty === 'entry') { if (d.checked) { p.checked++; p.ok += implOf(d).length; } if (d.date || d.kind || d.place || d.hdr) p.total++; continue; }
    if (!d.d) continue; p.total++;
    if (ty === 'rec') { if (d.d === 'ok') p.ok++; else if (d.d === 'a' || d.d === 'e') p.corrected++; else if (d.d === 'x') p.dropped++; else p.unsure++; }
    else if (ty === 'miss') { if (d.d === 'add') p.added++; } else if (ty === 'name') p.names++; else if (ty === 'tc') p.tc++; else if (ty === 'qa') p.qa++; }
  return p;
}
function rvProgress() { const el = $('#rvprog'); if (!el) return; const p = progressStats(); el.textContent = t('prog', fmt(p.checked), fmt(p.total)); el.title = t('prog_t'); }
function rvSavedLabel() { const el = $('#savedlbl'); if (!el) return; el.textContent = lastSaved ? t(fileHandle ? 'saved_file' : 'saved_browser', lastSaved.toTimeString().slice(0, 5)) : ''; el.title = t('saved_t'); }
function precisionTable() {
  const rows = auditRows(); const g = new Map();
  for (const r of rows) { if (!r.agreed) continue; const k = r.source + '|' + r.kind; if (!g.has(k)) g.set(k, { source: r.source, kind: r.kind, yes: 0, partly: 0, no: 0 }); g.get(k)[r.agreed]++; }
  const list = [...g.values()].sort((a, b) => coll.compare(a.source, b.source) || coll.compare(a.kind, b.kind));
  if (!list.length) return `<p class="muted">${t('prec_none')}</p>`;
  return `<table class="t prec"><tr><th>${t('prec_source')}</th><th>${t('prec_kind')}</th><th class="r">${t('prec_yes')}</th><th class="r">${t('prec_partly')}</th><th class="r">${t('prec_no')}</th><th class="r">${t('prec_share')}</th><th></th></tr>` +
    list.map(x => { const n = x.yes + x.partly + x.no; const sh = n ? x.yes / n : 0;
      return `<tr><td>${esc(t('as_' + x.source))}</td><td>${esc(t('ak_' + x.kind))}</td><td class="num r">${fmt(x.yes)}</td><td class="num r">${fmt(x.partly)}</td><td class="num r">${fmt(x.no)}</td><td class="num r">${(100 * sh).toFixed(0)} %</td><td><div class="meter" title="${fmt(x.yes)} / ${fmt(n)}"><i style="width:${(100 * x.yes / n).toFixed(1)}%" class="mt-yes"></i><i style="width:${(100 * x.partly / n).toFixed(1)}%" class="mt-partly"></i><i style="width:${(100 * x.no / n).toFixed(1)}%" class="mt-no"></i></div></td></tr>`; }).join('') + '</table>';
}
const LV_KINDS = ['rec', 'auto', 'miss', 'ent', 'name', 'tc', 'qa', 'ins'];
function levelTableHtml() {   // open items per level and per kind (entries the filter shows, decided items no longer count)
  const tot = levelTotals(); const sum = [0, 0, 0, 0];
  const row = (lab, c, cls) => `<tr${cls ? ` class="${cls}"` : ''}><td>${lab}</td>${LEVELS.map(lv => `<td class="num r">${c[lv] ? fmt(c[lv]) : '<span class="muted">–</span>'}</td>`).join('')}<td class="num r">${fmt(c[1] + c[2] + c[3])}</td></tr>`;
  let s = `<table class="t covt lvt"><tr><th>${t('lvt_kind')}</th>${LEVELS.map(lv => `<th class="r">${lvDot(lv)}${lvName(lv)}</th>`).join('')}<th class="r">${t('lvt_sum')}</th></tr>`;
  for (const k of LV_KINDS) { const c = tot[k] || [0, 0, 0, 0]; for (const lv of LEVELS) sum[lv] += c[lv]; s += row(esc(t('lvk_' + k)), c); }
  const ents = [0, 0, 0, 0]; for (const x of RVS.values()) { if (!entryInCorpus(x)) continue; const c = openLevels(x); for (const lv of LEVELS) if (c[lv]) ents[lv]++; }
  s += row(`<b>${t('lvt_sum')}</b>`, sum, 'tot') + `<tr class="ents"><td>${t('lvt_entries')}</td>${LEVELS.map(lv => `<td class="num r">${fmt(ents[lv])}</td>`).join('')}<td></td></tr></table>`;
  const mx = Math.max(1, sum[1] + sum[2] + sum[3]);
  s += `<div class="meter lvmeter" title="${LEVELS.map(lv => lvName(lv) + ' ' + fmt(sum[lv])).join(' · ')}">${LEVELS.map(lv => `<i class="lv${lv}" style="width:${(100 * sum[lv] / mx).toFixed(1)}%"></i>`).join('')}</div>`;
  return s;
}
function rvRenderOverview() {
  const box = $('#rv-ov'); if (!box) return;
  if (EXPLORER) { xRenderOverview(box); return; } const c = countQueues(); const st = layerStats(); const p = progressStats(); const meta = R.meta || {};
  const pct = (a, b) => (b ? (100 * a / b).toFixed(1).replace('.', LANG === 'de' ? ',' : '.') + ' %' : '–');
  // explorer build: the queues are filters (entries), there is no progress and no precision of decisions
  const tile = q => `<div class="tile qtile" data-queue="${q}"><div class="v num">${fmt(q === 'done' || EXPLORER ? c[q].n : c[q].open)}</div><div class="l"><i class="qd qd-${q}"></i>${t('q_' + q)}</div><div class="s">${EXPLORER ? esc(t('ov_entries')) : q === 'done' ? esc(t('ov_done_of', fmt(c.all.n))) : esc(t('ov_open_of', fmt(c[q].n)))}</div></div>`;
  const meter = (a, b, cls) => `<div class="meter"><i style="width:${b ? (100 * a / b).toFixed(1) : 0}%" class="${cls}"></i></div>`;
  const cov = (lab, a, b) => `<tr><td>${esc(lab)}</td><td class="num r">${fmt(a)}</td><td class="num r muted">/ ${fmt(b)}</td><td class="num r">${pct(a, b)}</td><td style="width:34%">${meter(a, b, 'mt-cov')}</td></tr>`;
  const cardLv = `<div class="card"><h3>${t('ov_lv')}</h3><p class="muted cardlead">${t('ov_lv_lead')}</p>${RVU.notes ? levelTableHtml() : ''}</div>`;
  const cardCorp = `<div class="card qcard"><h3>${t('ov_q')}</h3>${qualityCardHtml()}</div>`;
  const cardCov = `<div class="card"><h3>${t('ov_cov')}</h3><table class="t covt">
        ${cov(t('ov_cov_entG'), st.entG, st.ent)}${cov(t('ov_cov_entS'), st.entS, st.ent)}${cov(t('ov_cov_recG'), st.recG, st.rec)}${cov(t('ov_cov_recS'), st.recS, st.rec)}
        ${cov(t('ov_cov_flagG'), st.flagG, st.recG)}${cov(t('ov_cov_flagS'), st.flagS, st.recS)}</table>
        <p class="muted" style="margin:8px 0 0;font-size:.8rem">${esc(t('ov_cov_more', fmt(st.miss), fmt(st.tcRel), fmt(st.tc), fmt(st.namesChanged), fmt(st.names)))}</p></div>`;
  const cardProg = `<div class="card"><h3>${t('ov_prog')}</h3><table class="t covt">
        ${cov(t('ov_p_checked'), p.checked, st.ent)}${cov(t('ov_p_ok'), p.ok, st.rec)}${cov(t('ov_p_corr'), p.corrected, st.rec)}${cov(t('ov_p_drop'), p.dropped, st.rec)}</table>
        <p class="muted" style="margin:8px 0 0;font-size:.8rem">${esc(t('ov_p_more', fmt(p.added), fmt(p.names), fmt(p.tc), fmt(p.qa), fmt(p.unsure)))}</p></div>`;
  const cardHow = `<div class="card howto"><h3>${t('ov_how')}</h3>${t('ov_how_body')}</div>`;
  const cardPrec = `<div class="card"><h3>${t('ov_prec')}</h3><p class="muted cardlead">${t('ov_prec_lead')}</p>${EXPLORER ? '' : precisionTable()}</div>`;
  const cardSev = `<details class="card sevcard" style="margin-top:16px"${store('sevopen') === '1' ? ' open' : ''}><summary><h3>${t('ov_sev')}</h3><span class="muted">${t('ov_sev_lead')}</span></summary>${sevTableHtml()}<p class="muted" style="margin:8px 0 0;font-size:.8rem">${t('sev_note')}</p></details>`;
  const grid = (a, b, top) => `<div class="grid2"${top ? '' : ' style="margin-top:16px"'}>${a}${b}</div>`;
  const cards = !EXPLORER ? grid(cardLv, cardCorp, true) + grid(cardCov, cardProg) + grid(cardHow, cardPrec) + cardSev
    : RVU.notes ? grid(cardLv, cardCorp, true) + grid(cardCov, cardHow) + cardSev
      : grid(cardCorp, cardHow, true);
  box.innerHTML = `<div class="page" style="padding-bottom:8px">
    <h2>${t('ov_rv_title')}</h2>
    <p class="lead">${esc(t('ov_rv_lead', G.meta.sourcePath || G.meta.source, meta.export || '?', meta.built || '?', (G.meta.built || '').slice(0, 16).replace('T', ' ')))}</p>
    <div class="note">${t('ov_note')}</div>
    ${rvFilterNote(true)}
    <div class="tiles qtiles">${queueList().map(tile).join('')}</div>
    ${cards}
    <h2 style="margin-top:26px">${t('ov_graph')}${rvFilterNote()}</h2></div>`;
  box.onclick = ev => {
    const q = ev.target.closest('[data-queue]'); if (q) { setQueue(q.dataset.queue, true); return; }
  };
  const det = $('.sevcard', box); if (det) det.addEventListener('toggle', () => store('sevopen', det.open ? '1' : '0'));
}
const countsSoon = debounce(() => { countQueues(); renderChips(); listFoot(); }, 250);
function rvRefresh() {   // after every decision
  if (S.view === 'entry' && EM) { renderGraph(true); rvRenderTable(); renderPanel(); renderEntryHead(); drawList(); }
  rvProgress(); countsSoon();
  if (S.view === 'overview') rvRenderOverview();
}
function rvApplyStatic() { if ($('#who')) $('#who').value = RV.who || ''; rvProgress(); rvSavedLabel(); renderQBar(); }
function rvLangChanged() { $('#elist-body').dataset.lang = ''; PCACHE.clear(); renderQBar(); if (S.view === 'entry' && EM) scanBar(); if (RVU.listPos) { renderVolSelect(); renderChips(); rvRenderList(true); } }
function rvResize() { drawList(); if (RVU.scan) scanFit(SC.mode); }
