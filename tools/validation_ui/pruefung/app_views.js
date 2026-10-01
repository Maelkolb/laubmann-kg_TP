// ---------------------------------------------------------------- tabs, queue list, refresh
let cur = { tab: 'home', i: -1 };
function tabCountItems(id) { return id === 'extract' ? QUEUES.extract.concat(QUEUES.text) : QUEUES[id] || []; }
function renderTabs() {
  let lastPart = '';
  $('#tabs').innerHTML = TABS.map(x => {
    let c = '', sep = '';
    if (x.part && x.part !== lastPart) { sep = '<span class="tabsep" title="' + esc(t('part.' + x.part + '.tip')) + '">' + x.part + '</span>'; lastPart = x.part; }
    if (x.id !== 'home' && x.id !== 'log') { const p = progress(tabCountItems(x.id)); c = '<span class="c' + (p.done === p.n ? ' done' : '') + '" title="' + t('q.done', p.done, p.n) + '">' + fmt(p.n - p.done) + '</span>'; }
    return sep + '<button class="tab' + (cur.tab === x.id ? ' on' : '') + '" data-tab="' + x.id + '">' + tabLabel(x.id) + c + '</button>';
  }).join('');
  $('#btnSearch').textContent = t('hdr.search'); $('#btnSearch').title = t('hdr.searchTip'); $('#btnUndo').title = t('hdr.undo'); $('#btnExport').textContent = t('hdr.export'); $('#btnHelp').title = t('hdr.help'); $('#btnTheme').title = t('hdr.theme'); $('#btnList').title = t('hdr.list');
  $('#btnLang').textContent = LANG === 'en' ? 'DE' : 'EN';
  const onTab = $('#tabs .tab.on'); if (onTab && onTab.scrollIntoView) onTab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  $('#scanzoom').textContent = t('scan.zoom'); $('#scanprev').title = t('scan.prev'); $('#scannext').title = t('scan.next'); $('#scanclose').title = t('scan.close');
}
function openTab(tab, i) {
  cur.tab = tab; S.ui.tab = tab;
  const selI = S.ui.sel[tab] != null && KEY2I.has(S.ui.sel[tab]) ? KEY2I.get(S.ui.sel[tab]) : -1;
  if (i != null) cur.i = i; else cur.i = selI;
  if (tab in FILTERS) {
    if (i != null && ITEMS[i] && !filtered(tab).includes(ITEMS[i]) && tabItems(tab).includes(ITEMS[i])) { S.ui.filt[tab] = {}; S.ui.q[tab] = ''; }
    const items = filtered(tab); if (cur.i < 0 || !items.includes(ITEMS[cur.i])) cur.i = (items.find(it => !isDone(it)) || items[0] || { i: -1 }).i;
  }
  S.ui.sel[tab] = ITEMS[cur.i] ? ITEMS[cur.i].key : null; save();
  refresh(true);
}
function refresh(scroll) {
  renderTabs();
  const main = $('#main');
  main.classList.toggle('nolist', cur.tab === 'home' || cur.tab === 'log');
  if (cur.tab === 'home') { renderHome(); main.classList.add('noscan'); return; }
  if (cur.tab === 'log') { renderLog(); main.classList.add('noscan'); return; }
  renderQueue(scroll);
  const it = ITEMS[cur.i];
  if (!it) { $('#work').innerHTML = '<div class="empty">' + t('empty') + '</div>'; main.classList.add('noscan'); return; }
  renderCard(it);
}
const LIST_STEP = 120;
function modeChips(tab) {
  const M = { extract: [['entries', 'q.entries', QUEUES.extract.length], ['text', 'q.readings', QUEUES.text.length]],
    sample: [['sample', 'q.sampleMode', QUEUES.sample.length], ['all', 'q.all', QUEUES.sample.length + QUEUES.rest.length]],
    tc: [['sample', 'q.tcSample', QUEUES.tcSample.length], ['review', 'q.tcReview', QUEUES.tcReview.length], ['all', 'q.tcAll', QUEUES.tc.length]] }[tab];
  if (!M) return '';
  const def = { extract: 'entries', sample: 'sample', tc: 'sample' }[tab];
  return '<div class="chips">' + M.map(([m, l, n]) => '<button class="chip' + ((S.ui.mode[tab] || def) === m ? ' on' : '') + '" data-mode="' + m + '">' + t(l) + '<small>' + fmt(n) + '</small></button>').join('') + '</div>';
}
function renderQueue(scroll) {
  const tab = cur.tab; const items = filtered(tab); const p = progress(tabItems(tab)); const f = S.ui.filt[tab] || {};
  let h = '<div class="qhead"><div class="qtitle">' + tabLabel(tab) + '<span>' + t('q.inlist', fmt(items.length)) + '</span></div><div class="qhint">' + esc(t('hint.' + tab)) + '</div>';
  h += modeChips(tab);
  for (const [key, opts0] of (FILTERS[tab] || [])) {
    const opts = filterOpts(tab, key, opts0);
    h += '<div class="chips">' + opts.map(([v, l, fn]) => { const n = tabItems(tab).filter(fn).length; if (!n && key !== 'state') return ''; return '<button class="chip' + (f[key] === v ? ' on' : '') + '" data-f="' + key + '" data-v="' + esc(v) + '">' + esc(tab === 'qa' && key === 'reason' ? qaLabel(v) : t(l)) + '<small>' + fmt(n) + '</small></button>'; }).join('') + '</div>';
  }
  h += pbarHtml(p);
  h += '<div class="pnote"><span>' + t('q.done', fmt(p.done), fmt(p.n)) + '</span><span>' + t('q.left', timeLeft(tabItems(tab), tab === 'extract' ? (S.ui.mode.extract === 'text' ? 'text' : 'extract') : tab)) + '</span></div>';
  h += '<input class="qsearch" id="qsearch" placeholder="' + esc(t('q.search')) + '" value="' + esc(S.ui.q[tab] || '') + '"></div>';
  const show = S.ui.show[tab] || LIST_STEP;
  h += '<div class="qlist" id="qlist">' + items.slice(0, show).map(rowHtml).join('');
  if (items.length > show) h += '<div class="qmore" data-more="1">' + t('q.more', fmt(items.length - show)) + '</div>';
  h += '</div>';
  $('#queue').innerHTML = h;
  if (scroll) { const on = $('#qlist .qi.on'); if (on) on.scrollIntoView({ block: 'nearest' }); }
}
const pbarHtml = p => '<div class="pbar"><i class="a" style="width:' + (100 * p.a / (p.n || 1)) + '%"></i><i class="o" style="width:' + (100 * p.o / (p.n || 1)) + '%"></i><i class="r" style="width:' + (100 * p.r / (p.n || 1)) + '%"></i><i class="u" style="width:' + (100 * p.u / (p.n || 1)) + '%"></i></div>';
const short = (s, n) => { s = stripTags(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
function rowHtml(it) {
  const d = dec(it); const cls = d && d.d ? CLS[d.d] || 'o' : (subCount(it) ? 'p' : '');
  let l1, l2, nm = '';
  if (it.t === 'entry') { const e = E[it.ei]; l1 = esc(it.id) + '<i>' + dateDE(it.date) + '</i>'; l2 = esc(e[6]) + ' · ' + it.n_obs + ' ' + t('row.obs') + ' · <span class="bd no">' + t('row.wrong', it.wrong + it.spurious) + '</span>' + (it.missing ? '<span class="bd unk">' + t('row.missing', it.missing) + '</span>' : '') + roundChip(it) + (it.stale ? '<span class="bd unk">' + t('row.stale') + '</span>' : ''); }
  else if (it.t === 'text') { l1 = '„' + esc(it.label) + '“ → „' + esc(it.prop.value) + '“'; l2 = esc(E[it.ei][0]) + ' · ' + esc(STR['for.' + it.for] ? t('for.' + it.for) : it.for) + roundChip(it) + (it.found ? '' : ' · <span class="bd unk">' + t('row.textNotFound') + '</span>'); }
  else if (it.t === 'mention') { l1 = '„' + esc(it.label) + '“ ' + (it.prop.action === 'drop' ? '✗' : '→ ' + esc(it.prop.value)); l2 = esc(E[it.ei][0]) + ' · ' + sourceIcons(it.src) + ' ' + pct(it.conf) + roundChip(it) + (it.stale ? '<span class="bd unk">' + t('row.stale') + '</span>' : ''); nm = it.auto ? '<b title="' + t('row.autoTip') + '">' + t('row.auto') + '</b>' : ''; }
  else if (it.t === 'tc') { l1 = '„' + esc(short(it.label, 50)) + '“ → „' + esc(short(it.new, 50)) + '“'; l2 = esc(E[it.ei][0]) + ' <span class="bd plain">' + t('tck.' + it.k) + '</span>' + (it.applied === 'y' ? '' : '<span class="bd unk">' + t('tc.notApplied') + '</span>') + (it.m ? '<span class="bd ' + ({ right: 'ok', partly: 'unk', wrong: 'no', unclear: 'unk' }[it.m.v] || 'plain') + '">R' + it.m.r + ': ' + t('tcm.' + it.m.v) + '</span>' : '') + (it.stratum ? '<span class="bd plain">' + t('chip.tcSample') + '</span>' : ''); }
  else if (it.t === 'qa') { l1 = esc(qaLabel(it.k)) + (it.label ? '<i>' + esc(short(it.label, 60)) + '</i>' : ''); l2 = esc(it.id) + ' · ' + esc(short(it.detail, 110)); }
  else if (it.t === 'habitat' && it.q !== 'habitat') { l1 = esc(it.label); l2 = '<span class="bd ' + catClass(it) + '">' + esc(CAT(it.k)) + '</span>' + sourceIcons(it.src) + roundChip(it) + (it.prop && it.prop.code ? '→ ' + esc(it.prop.code) : it.cur ? ' ' + esc(it.cur.code) : ''); nm = fmt(it.n) + '×' + (it.auto && it.q === 'change' ? '<b title="' + t('row.autoTip') + '">' + t('row.auto') + '</b>' : ''); }
  else if (it.t === 'habitat') { l1 = esc(it.label); l2 = it.cur ? '<span class="bd ok">' + esc(it.cur.code) + '</span> ' + esc(short(it.cur.label, 70)) : '<span class="bd unk">' + t('hab.none') + '</span>' + (it.sug && it.sug.code ? ' → ' + esc(it.sug.code) : ''); nm = fmt(it.n) + '×'; }
  else {
    l1 = esc(it.label) + (it.sci && it.t !== 'person' && it.t !== 'place' ? '<i>' + esc(it.sci) + '</i>' : '');
    const cat = '<span class="bd ' + catClass(it) + '">' + esc(it.q === 'unchecked' ? t('cat.u.' + it.k) : CAT(it.k)) + '</span>';
    const to = it.prop && it.t !== 'place' ? (it.prop.de || it.prop.sci ? '→ ' + esc(it.prop.de || it.prop.sci) : it.prop.qid ? '→ ' + esc(it.prop.qid) : '') : it.prop && it.t === 'place' && it.prop.lat != null ? '→ ' + (lc(it.prop.name.split(',')[0]) === lc(it.label) ? esc(it.prop.name.split(',').slice(1, 3).join(',').trim()) : esc(it.prop.name.split(',')[0])) : '';
    l2 = cat + (it.q === 'unchecked' ? '' : sourceIcons(it.src) + roundChip(it)) + esc(to);
    nm = fmt(it.n) + '×' + (it.auto && it.q === 'change' ? '<b title="' + t('row.autoTip') + '">' + t('row.auto') + '</b>' : '');
  }
  return '<div class="qi' + (it.i === cur.i ? ' on' : '') + '" data-i="' + it.i + '"><span class="dot ' + cls + '"></span><div><div class="l1">' + l1 + '</div><div class="l2">' + l2 + '</div></div><div class="num">' + nm + '</div></div>';
}
function catClass(it) { if (it.q === 'unchecked') return it.k === 'linked' ? 'acc' : 'unk'; if (it.q === 'open') return 'unk'; if (it.q === 'sample' || it.q === 'rest') return 'ok'; return it.k === 'none' || it.k === 'name-none' || it.k === 'not_a_place' || it.k === 'h-none' || it.k.startsWith('nolink') || it.k === 'unsure-remove' || it.k === 'value-drop' ? 'no' : 'mach'; }

// ---------------------------------------------------------------- home: task list in the recommended order
function homeTasks() {
  const ch = QUEUES.change; const cum = (() => { const l = ch.filter(it => !it.auto); const tot = l.reduce((a, it) => a + it.n, 0) || 1; let acc = 0, k = 0; for (const it of l) { acc += it.n; k++; if (acc >= 0.8 * tot) break; } return k; })();
  const A = [
    { q: 'change', f: { auto: 'auto' }, h: t('task.1'), p: t('task.1.p'), items: ch.filter(it => it.auto) },
    { q: 'sample', mode: 'sample', h: t('task.3'), p: t('task.3.p', QUEUES.sample.length, fmt(QUEUES.rest.length)), items: QUEUES.sample },
    { q: 'tc', mode: 'sample', h: t('task.tc1'), p: t('task.tc1.p', fmt(STATS.tc.total || 0), fmt(STATS.tc.entries || 0)), items: QUEUES.tcSample },
    { q: 'tc', mode: 'review', h: t('task.tc2'), p: t('task.tc2.p', fmt((STATS.tc.review || {})['not-applied'] || 0), fmt(((STATS.tc.review || {})['m-wrong'] || 0) + ((STATS.tc.review || {})['m-unclear'] || 0))), items: QUEUES.tcReview },
    { q: 'change', f: { auto: 'prop' }, h: t('task.2'), p: t('task.2.p', fmt(cum)), items: ch.filter(it => !it.auto) },
    { q: 'open', h: t('task.4'), p: t('task.4.p', fmt(QUEUES.open.filter(it => it.k === 'unlocatable').length)), items: QUEUES.open },
    { q: 'extract', mode: 'entries', h: t('task.5'), p: t('task.5.p', QUEUES.extract.length, QUEUES.text.length), items: QUEUES.extract.concat(QUEUES.text), opt: true },
  ];
  const un = QUEUES.unchecked;
  const B = [
    { q: 'qa', h: t('task.qa'), p: t('task.qa.p', fmt(new Set(QUEUES.qa.map(it => it.k)).size)), items: QUEUES.qa },
    { q: 'habitat', h: t('task.hab'), p: t('task.hab.p', fmt(QUEUES.habitat.filter(it => it.k === 'unlinked').length)), items: QUEUES.habitat },
    { q: 'unchecked', f: { link: 'linked' }, h: t('task.un1'), p: t('task.un1.p'), items: un.filter(it => it.k === 'linked') },
    { q: 'unchecked', f: { link: 'unlinked', many: 'm3' }, h: t('task.un2'), p: t('task.un2.p'), items: un.filter(it => it.k === 'unlinked' && it.n >= 3) },
    { q: 'unchecked', f: { link: 'unlinked', many: 'm1' }, h: t('task.un3'), p: t('task.un3.p'), items: un.filter(it => it.k === 'unlinked' && it.n < 3), opt: true },
  ];
  return [A.filter(x => x.items.length), B.filter(x => x.items.length)];
}
function taskHtml(x, k) {
  const p = progress(x.items);
  return '<div class="task' + (x.opt ? ' opt' : '') + '" data-task="' + x.q + '" data-mode="' + (x.mode || '') + '" data-f=\'' + esc(JSON.stringify(x.f || {})) + '\'><div class="no">' + (k + 1) + '</div><div><h3>' + x.h + ' <span class="muted" style="font-weight:400;font-size:13px">' + fmt(x.items.length) + '</span></h3><p>' + x.p + '</p>' + pbarHtml(p) + '<div class="prog">' + t('task.prog', fmt(p.done), fmt(p.n), timeLeft(x.items, x.q)) + '</div></div><button class="nbtn primary">' + t('task.open') + '</button></div>';
}
function legacyFound() {
  const out = [];
  try { const o = JSON.parse(localStorage.getItem(LS_OLD.pruefung) || 'null'); const n = o && o.dec ? Object.keys(o.dec).length : 0; if (n && D.LEGACY) out.push(['pruefung', n]); } catch (e) { }
  try { const o = JSON.parse(localStorage.getItem(LS_OLD.abgleich) || 'null'); let n = 0; if (o) { for (const k of ['id', 'men', 'ent', 'grp']) for (const t0 in (o[k] || {})) n += Object.keys(o[k][t0] || {}).length; n += (o.text || []).length + Object.keys(o.qa || {}).length + Object.keys(o.ev || {}).length; } if (n) out.push(['abgleich', n]); } catch (e) { }
  return out.filter(([k]) => !(S.ui.imported || {})[k]);
}
function renderHome() {
  const st = STATS.machine; const c = st.checked; const th = D.thresholds; const r2 = STATS.round2 || {};
  const bar = segs => { const tot = segs.reduce((a, s) => a + s[1], 0) || 1; return '<div class="vbar">' + segs.map(s => '<i class="' + s[2] + '" style="width:' + (100 * s[1] / tot) + '%" title="' + s[0] + ': ' + fmt(s[1]) + '"></i>').join('') + '</div><div class="vleg">' + segs.map(s => '<span><i class="' + s[2] + '"></i>' + s[0] + ' ' + fmt(s[1]) + '</span>').join('') + '</div>'; };
  const M = it => it.q !== 'unchecked';
  const tx = ITEMS.filter(it => it.t === 'taxon' && M(it));
  const ta = r2.taxa_a || {}, ps = r2.place_scan || {};
  const cards = [
    { h: t('home.taxa'), n: t('home.taxa.n', fmt(c.taxon), fmt(c.taxon_total)), how: sourceChips(['text', 'scan', 'gemini', 'opus', 'gbif']),
      what: ta.n ? t('home.taxa.what2', fmt(c.scan_mentions), fmt(ta.n), fmt(ta.agree), fmt(ta.legible), pct(ta.agree / (ta.legible || 1)), fmt(ta.disagree || 0)) : t('home.taxa.what', fmt(c.scan_mentions)),
      bar: bar([[t('bar.linkOk'), tx.filter(it => it.k === 'ok').length, 'c-ok'], [t('bar.change'), tx.filter(it => it.q === 'change' && it.k !== 'none').length, 'c-ch'], [t('bar.notBird'), tx.filter(it => it.k === 'none').length, 'c-none'], [t('bar.unsure'), tx.filter(it => it.q === 'open').length, 'c-open']]) },
    { h: t('home.persons'), n: t('home.persons.n', fmt(c.person), fmt(c.person_total)), how: sourceChips(['text', 'xref']), what: t('home.persons.what'),
      bar: bar([[t('bar.linkOk'), ITEMS.filter(it => it.t === 'person' && it.k === 'link-confirm').length, 'c-ok'], [t('bar.change'), ITEMS.filter(it => it.t === 'person' && it.q === 'change').length, 'c-ch'], [t('bar.unsure'), ITEMS.filter(it => it.t === 'person' && it.q === 'open').length, 'c-open']]) },
    { h: t('home.places'), n: t('home.places.n', fmt(c.place), fmt(c.place_total)), how: sourceChips(['text', 'nominatim', 'anchor'].concat(ps.items ? ['scan'] : [])),
      what: ps.items ? t('home.places.what2', fmt(ps.items), fmt(ps.located || 0), fmt(ps.not_a_place || 0), fmt(ps.still_open || 0), fmt(ps.illegible || 0)) : t('home.places.what'),
      bar: bar([[t('bar.locOk'), ITEMS.filter(it => it.t === 'place' && M(it) && it.k === 'ok').length, 'c-ok'], [t('bar.change'), ITEMS.filter(it => it.t === 'place' && it.q === 'change').length, 'c-ch'], [t('bar.openNoCand'), ITEMS.filter(it => it.t === 'place' && it.q === 'open').length, 'c-open']]) },
    { h: t('home.entries'), n: t('home.entries.n', c.entries, fmt(c.entries_total), fmt(c.obs)), how: sourceChips(['entry-check']),
      what: t('home.entries.what', c.value_corr, c.text_corr),
      bar: bar([[t('bar.ok'), c.obs_ok, 'c-ok'], [t('bar.wrong'), c.obs_wrong, 'c-none'], [t('bar.spurious'), c.obs_spurious, 'c-ch'], [t('bar.unsure'), c.obs_unsure, 'c-open']]) + '<div class="small muted" style="margin-top:4px">' + t('home.entries.missing', fmt(c.obs_missing)) + '</div>' },
  ];
  const tcs = STATS.tc || {};
  if (tcs.total) cards.push({ h: t('home.tc'), n: t('home.tc.n', fmt(tcs.total), fmt(tcs.entries)), how: sourceChips(['scan']), what: t('home.tc.what', fmt((tcs.applied || {}).n || 0), fmt(Object.values(tcs.machine || {}).reduce((a, b) => a + b, 0))),
    bar: bar(TC_KINDS.map((k, j) => [t('tck.' + k), (tcs.kind || {})[k] || 0, ['c-ok', 'c-ch', 'c-open', 'c-none', 'c-k5', 'c-k6'][j]])) });
  const [A, B] = homeTasks();
  let h = '<div class="wrap wide home"><h1>' + t('home.title') + '</h1><p class="lead">' + esc(t('home.lead', D.export || '')) + '</p>';
  h += '<div class="row" style="margin-top:10px"><label>' + t('home.name') + ': <input type="text" id="who" value="' + esc(S.who) + '" placeholder="AB" style="border:1px solid var(--line2);border-radius:6px;padding:4px 8px;background:var(--panel);color:var(--ink);width:120px"></label><button class="nbtn" id="btnImport">' + t('home.load') + '</button><span class="small muted">' + t('home.stored') + '</span></div>';
  const lf = legacyFound(); if (lf.length) h += '<div class="banner">' + t('home.legacyFound') + ' ' + lf.map(([k, n]) => '<button class="nbtn primary" data-legacy="' + k + '">' + t('home.legacy.' + k, fmt(n)) + '</button>').join(' ') + '</div>';
  h += '<h2 class="part">' + t('part.A') + '</h2><p class="small muted" style="max-width:820px">' + t('part.A.p') + '</p>';
  h += '<div class="rounds">' + (D.rounds || []).map(r => '<span class="bd rnd big">R' + r.n + '</span> <span class="small">' + esc([r.model, (r.built || '').slice(0, 10), t('rnd.graph', r.graph || '?')].filter(Boolean).join(' · ')) + '</span>').join('<br>') + '</div>';
  h += '<div class="tasks">' + A.map((x, k) => taskHtml(x, k)).join('') + '</div>';
  h += '<h2 class="part">' + t('part.B') + '</h2><p class="small muted" style="max-width:820px">' + t('part.B.p') + '</p>';
  h += '<div class="tasks">' + B.map((x, k) => taskHtml(x, A.length + k)).join('') + '</div>';
  h += '<div class="small muted" style="margin-top:10px">' + t('home.keys') + '</div>';
  h += '<h2 style="font-size:17px;margin:26px 0 4px">' + t('home.h.checked') + '</h2><div class="grid4">' + cards.map(cd => '<div class="hc"><h3>' + cd.h + '</h3><div class="n">' + cd.n + '</div><div style="margin:6px 0 2px">' + cd.how + '</div><div class="small muted">' + cd.what + '</div>' + cd.bar + '</div>').join('') + '</div>';
  h += '<div class="legend" style="margin-top:12px"><span>' + sourceChips(['text']) + '</span><span>' + t('leg.text') + '</span><span>' + sourceChips(['scan']) + '</span><span>' + t('leg.scan') + '</span><span>' + sourceChips(['nominatim']) + '</span><span>' + t('leg.auth') + '</span><span><span class="bd auto">' + t('chip.auto') + '</span></span><span>' + t('leg.auto', num(th.conf), th.agree) + '</span></div>';
  h += sampleStatsHtml() + tcStatsHtml();
  h += '</div>';
  $('#work').innerHTML = h;
}
function wilson(k, n) { if (!n) return null; const z = 1.96, p = k / n; const d = 1 + z * z / n; const c = (p + z * z / (2 * n)) / d; const w = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [Math.max(0, c - w), Math.min(1, c + w)]; }
const stratumLabel = id => STR['strat.' + id] ? t('strat.' + id) : id;
function sampleStatsHtml() {
  const rows = STATS.sample.map(s => { const its = QUEUES.sample.filter(it => it.stratum === s.id); let k = 0, n = 0; for (const it of its) { const d = dec(it); if (!d || !d.d || d.d === 'u') continue; n++; if (d.d === 'a' || d.d === 'y') k++; } const ci = wilson(k, n); return '<tr><td>' + esc(stratumLabel(s.id)) + '</td><td class="mono">' + s.n + ' / ' + fmt(s.pool) + '</td><td class="mono">' + n + '</td><td class="mono">' + (n ? pct(k / n) : '–') + '</td><td class="mono muted">' + (ci ? pct(ci[0]) + ' – ' + pct(ci[1]) : '') + '</td></tr>'; });
  return '<h2 style="font-size:17px;margin:22px 0 4px">' + t('home.h.prec') + '</h2><table class="tbl" style="max-width:820px"><tr><th>' + t('prec.h.stratum') + '</th><th>' + t('prec.h.n') + '</th><th>' + t('prec.h.judged') + '</th><th>' + t('prec.h.right') + '</th><th>' + t('prec.h.ci') + '</th></tr>' + rows.join('') + '</table>';
}
function tcStatsHtml() {
  const tcs = STATS.tc || {}; const pool = tcs.pool || {}; if (!Object.keys(pool).length) return '';
  let totPool = 0, estRight = 0, covered = 0, mAgree = 0, mBoth = 0;
  const rows = Object.keys(pool).sort((a, b) => TC_KINDS.indexOf(a.split('-')[0]) - TC_KINDS.indexOf(b.split('-')[0]) || a.localeCompare(b)).map(sid => {
    const its = QUEUES.tcSample.filter(it => it.stratum === sid); let a = 0, r = 0, e = 0;
    for (const it of its) { const d = dec(it); if (!d || !d.d) continue; if (d.d === 'a') a++; else if (d.d === 'r') r++; else if (d.d === 'e') e++; }
    const n = a + r + e; const ci = wilson(a, n); totPool += pool[sid]; if (n) { estRight += pool[sid] * a / n; covered += pool[sid]; }
    const [kind, ap] = sid.split('-');
    return '<tr><td>' + esc(t('tck.' + kind)) + ' · ' + (ap === 'y' ? t('tc.applied') : t('tc.notApplied')) + '</td><td class="mono">' + its.length + ' / ' + fmt(pool[sid]) + '</td><td class="mono">' + n + '</td><td class="mono">' + (n ? pct(a / n) : '–') + '</td><td class="mono muted">' + (ci ? pct(ci[0]) + ' – ' + pct(ci[1]) : '') + '</td><td class="mono">' + (n ? pct(e / n) : '–') + '</td><td class="mono">' + (n ? pct(r / n) : '–') + '</td></tr>';
  });
  for (const it of QUEUES.tc) { if (!it.m) continue; const d = dec(it); if (!d || !d.d || d.d === 'u' || !['right', 'partly', 'wrong'].includes(it.m.v)) continue; mBoth++; if ({ right: 'a', partly: 'e', wrong: 'r' }[it.m.v] === d.d) mAgree++; }
  return '<h2 style="font-size:17px;margin:22px 0 4px">' + t('home.h.tcPrec') + '</h2><p class="small muted" style="max-width:820px">' + t('home.tcPrec.p') + '</p><table class="tbl" style="max-width:820px"><tr><th>' + t('prec.h.stratum') + '</th><th>' + t('prec.h.n') + '</th><th>' + t('prec.h.judged') + '</th><th>' + t('prec.h.tcRight') + '</th><th>' + t('prec.h.ci') + '</th><th>' + t('prec.h.tcPartly') + '</th><th>' + t('prec.h.tcWrong') + '</th></tr>' + rows.join('')
    + '<tr><td><b>' + t('prec.h.weighted') + '</b></td><td class="mono">' + fmt(totPool) + '</td><td></td><td class="mono"><b>' + (covered ? pct(estRight / covered) : '–') + '</b></td><td class="muted small" colspan="3">' + (covered ? t('prec.covered', pct(covered / (totPool || 1))) : '') + '</td></tr></table>'
    + (mBoth ? '<p class="small muted">' + t('home.tcMachine', mAgree, mBoth) + '</p>' : '');
}

// ---------------------------------------------------------------- log
function renderLog() {
  const Q = ['change', 'sample', 'open', 'tc', 'extract', 'text', 'unchecked', 'habitat', 'qa', 'rest'];
  const p = Object.fromEntries(Q.map(q => [q, progress(QUEUES[q] || [])]));
  const orphanDec = Object.keys(S.dec).filter(k => !KEY2I.has(k)).length;
  const inItems = { names: new Set(), mens: new Set() };
  for (const it of ITEMS) { const tt = ttOf(it); for (const fi of it.forms || []) inItems.names.add(tt + '|' + nameKey(tt, fi)); }
  let nNames = 0, nMens = 0; for (const t0 of TYPES) { nNames += Object.keys(S.names[t0]).length; nMens += Object.keys(S.mens[t0]).length; }
  let h = '<div class="wrap wide"><h1 style="font-size:22px;margin:6px 0">' + t('log.title') + '</h1><div class="stats">' + Q.filter(q => p[q].n).map(q => '<div class="stat"><div class="n">' + fmt(p[q].done) + ' <span class="muted" style="font-size:13px">/ ' + fmt(p[q].n) + '</span></div><div class="l">' + t('log.' + q) + '</div></div>').join('')
    + '<div class="stat"><div class="n">' + fmt(nNames) + ' · ' + fmt(nMens) + '</div><div class="l">' + t('log.subs') + '</div></div>'
    + (orphanDec || S.text.length || Object.keys(S.ev).length ? '<div class="stat"><div class="n">' + fmt(orphanDec) + ' · ' + fmt(S.text.length) + ' · ' + fmt(Object.keys(S.ev).length) + '</div><div class="l">' + t('log.orphans') + '</div></div>' : '') + '</div>';
  h += sampleStatsHtml() + tcStatsHtml();
  h += '<h2 style="font-size:17px;margin:22px 0 4px">' + t('log.all') + ' <span class="muted small">(' + t('log.allTip') + ')</span></h2>';
  if (!S.log.length) h += '<div class="card"><div class="cb muted">' + t('log.none') + '</div></div>';
  else h += '<table class="tbl">' + S.log.slice(0, 600).map((l, j) => { const i = KEY2I.has(l.k) ? KEY2I.get(l.k) : -1; const it = ITEMS[i]; return '<tr><td class="mono muted">' + esc((l.t || '').slice(0, 16).replace('T', ' ')) + '</td><td>' + esc(l.by || '') + '</td><td>' + esc(it ? TYPE(it.t) : '') + '</td><td>' + (it ? '<a href="#" data-goto="' + it.i + '">' + esc(short(it.label || it.id, 80)) + '</a>' : '<span class="muted mono">' + esc(l.k || '') + '</span>') + '</td><td>' + esc(l.lab) + '</td><td>' + (it && dec(it) ? '<button class="nbtn" data-rm="' + it.i + '" title="' + t('log.rm') + '">✕</button>' : '') + '</td></tr>'; }).join('') + '</table>';
  $('#work').innerHTML = h + '</div>';
}

// ---------------------------------------------------------------- cards
function renderCard(it) {
  const items = filtered(cur.tab); const pos = items.indexOf(it);
  const nextOpen = items.slice(pos + 1).find(x => !isDone(x)) || items.slice(0, pos).find(x => !isDone(x));
  let h = '<div class="wrap' + (it.t === 'entry' ? ' wide' : '') + '"><div class="crumb"><span>' + t('crumb', tabLabel(cur.tab), esc(TYPE(it.t)), pos + 1, fmt(items.length)) + '</span>'
    + '<span class="nav"><button class="nbtn" data-nav="prev"' + (pos <= 0 ? ' disabled' : '') + '>' + t('nav.prev') + '</button><button class="nbtn" data-nav="next"' + (pos >= items.length - 1 ? ' disabled' : '') + '>' + t('nav.next') + '</button>'
    + '<button class="nbtn primary" data-nav="nextopen"' + (!nextOpen ? ' disabled' : '') + '>' + t('nav.nextopen') + '</button></span></div>';
  const R = { taxon: cardTaxon, form: cardForm, person: cardPerson, place: cardPlace, mention: cardMention, text: cardText, entry: cardEntry, tc: cardTc, qa: cardQa, habitat: cardHabitat }[it.t];
  h += '<div class="card"><div class="cb">' + R(it) + '</div></div>';
  h += '<div class="kbdrow"><label><input type="checkbox" id="adv"' + (S.ui.adv ? ' checked' : '') + '> ' + t('adv') + '</label></div></div>';
  const w = $('#work'); w.innerHTML = h; w.scrollTop = 0;
  wireSnips(w);
  if (it.t === 'place') setTimeout(() => initMap(it), 30);
  const e = entryOf(it) || (it.ev && it.ev.length && MEN[menType(it)][it.ev[0]] ? E[MEN[menType(it)][it.ev[0]][1]] : null);
  const m0 = it.t !== 'entry' && it.ev && it.ev.length ? MEN[menType(it)][it.ev[0]] : null;
  const hl = it.t === 'tc' ? it.hl : m0 && Array.isArray(m0[4]) ? m0[4] : null;
  if (e && S.ui.scan !== false) showScan(null, e, hl); else $('#main').classList.add('noscan');
}
const menType = it => it.t === 'form' || it.t === 'mention' ? 'taxon' : it.t;

function headHtml(it, title, sub) {
  const catTxt = it.q === 'unchecked' ? t('cat.u.' + it.k) : CAT(it.k);
  const chips = '<span class="bd ' + catClass(it) + ' big">' + esc(catTxt) + '</span>' + (it.q === 'unchecked' ? '<span class="bd plain big" title="' + esc(t('chip.uncheckedTip')) + '">' + t('chip.unchecked') + '</span>' : '')
    + (it.q === 'change' ? (it.auto ? '<span class="bd auto big" title="' + esc(t('chip.autoTip', num(D.thresholds.conf), D.thresholds.agree)) + '">' + t('chip.auto') + '</span>' : '<span class="bd plain big" title="' + esc(t('chip.propTip')) + '">' + t('chip.prop') + '</span>') : '')
    + (it.stratum && it.q === 'sample' ? '<span class="bd plain big">' + t('chip.sample', esc(stratumLabel(it.stratum))) + '</span>' : '') + (it.stale ? '<span class="bd unk big" title="' + esc(t('chip.staleTip')) + '">' + t('row.stale') + '</span>' : '');
  return '<div class="row" style="margin-bottom:6px">' + chips + roundChip(it, true) + '<span class="sp"></span><span class="muted small">' + (it.n === 1 ? t('n.passage') : t('n.passages', fmt(it.n))) + '</span></div><h1 class="t">' + title + '</h1>' + (sub ? '<p class="sub">' + sub + '</p>' : '');
}
function machineHtml(it, verdict) {
  if (it.q === 'unchecked') return '';
  const meter = '<span class="meter" title="' + t('m.confTip') + '"><i style="width:' + Math.round(100 * (it.conf || 0)) + '%"></i></span>' + pct(it.conf);
  const rows = (it.rows || []).map(ri => ROWS[ri]).filter(Boolean);
  const auto = rows.filter(r => +r.confidence >= D.thresholds.conf && +r.agreement >= D.thresholds.agree).length;
  const ns = it.agree || 1;
  const prev = (it.prev || []).map(p => 'R' + p.r + ': ' + CAT(p.k) + (p.conf != null ? ' · ' + pct(p.conf) : '')).join(' · ');
  return '<div class="mach"><div class="mh"><b>' + t('m.machine') + ' ' + roundChip(it) + ':</b> ' + verdict + ' · ' + meter + ' · ' + t(ns === 1 ? 'm.source' : 'm.sources', ns) + ' ' + sourceChips(it.src) + '</div>'
    + (it.reason ? '<div class="reason">„' + esc(it.reason) + '“</div>' : '') + (it.note ? '<div class="small muted">' + esc(it.note) + '</div>' : '')
    + (rows.length ? '<div class="pipe">' + t('m.rows', rows.length) + (auto ? '<b>' + t('m.rowsAuto', auto) + '</b>' : t('m.rowsNone')) + '</div>' : '')
    + (prev ? '<div class="pipe">' + t('m.prev', esc(prev)) + '</div>' : '') + '</div>';
}
function nowHtml(it) {
  const n = it.now; if (!n) return '';
  let what = '', rel = '';
  if (it.t === 'taxon' || it.t === 'form') { what = esc(n.label) + (n.sci ? ' <i>' + esc(n.sci) + '</i>' : '') + (n.key ? ' <span class="mono muted">' + esc(n.key) + '</span>' : ' · ' + t('box.nolink')); rel = it.prop && it.prop.key && n.key === it.prop.key ? 'prop' : it.cur && n.key === it.cur.key ? 'cur' : (!it.prop && !(it.cur && it.cur.key) && !n.key) ? 'cur' : 'other'; }
  else if (it.t === 'person') { what = esc(n.label) + ' · ' + (n.qid || n.gnd ? esc([n.qid, n.gnd ? 'GND ' + n.gnd : ''].filter(Boolean).join(' ')) : t('box.nolink')); rel = it.prop && (it.prop.qid || null) === (n.qid || null) ? 'prop' : (it.cur.qid || null) === (n.qid || null) ? 'cur' : 'other'; }
  else if (it.t === 'habitat') { what = esc(n.label) + ' · ' + (n.code ? esc(n.code) : t('hab.none')); rel = it.prop && it.prop.code && n.code === it.prop.code ? 'prop' : (it.cur ? it.cur.code : null) === (n.code || null) ? 'cur' : 'other'; }
  else if (it.t === 'place') { what = esc(n.label) + ' · ' + (n.lat != null ? (+n.lat).toFixed(4) + ', ' + (+n.lon).toFixed(4) : t('box.noloc')); const near = (a, b) => a && b && a.lat != null && b.lat != null && Math.abs(a.lat - b.lat) < 0.02 && Math.abs(a.lon - b.lon) < 0.03; rel = near(n, it.prop) ? 'prop' : near(n, it.cur) || (n.lat == null && it.cur.lat == null) ? 'cur' : 'other'; }
  return '<div class="nowline">' + t('now.h', esc(D.export || '')) + ' ' + what + ' <span class="bd ' + ({ prop: 'mach', cur: 'plain', other: 'unk' })[rel] + '">' + t('now.' + rel) + '</span>' + (n.mixed ? ' <span class="bd unk">' + t('now.mixed') + '</span>' : '') + '</div>';
}
function evidenceHtml(it, mis, tt, opts) {
  opts = opts || {}; const list = (mis || []).map(mi => menHtml(it, tt, mi, opts.focus)).filter(Boolean).join('');
  if (!list) return '';
  return '<div class="sec"><h3>' + t('sec.passages') + '</h3><span class="lb">' + t(tt === 'habitat' ? 'sec.passagesTipH' : 'sec.passagesTip', mis.length < it.n ? t('sec.of', mis.length, fmt(it.n)) : '') + '</span></div>' + list;
}
function menHtml(it, tt, mi, focusForms) {
  const m = MEN[tt][mi]; if (!m) return ''; const e = E[m[1]]; if (!e) return ''; const f = FORMS[tt][m[0]] || ['?', 0, 0, ''];
  const rd = [];
  if (tt === 'taxon') { for (const [k, lab] of [['s', 'rd.sonnet'], ['g', 'rd.gemini'], ['o', 'rd.opus']]) { const a = SUG[k][mi]; if (a) rd.push('<b>' + t(lab) + ':</b> „' + esc(a[0]) + '“' + (a[2] === 'bird' && (a[3] || a[4]) ? ' → ' + esc(a[3] || '') + (a[4] ? ' <i>' + esc(a[4]) + '</i>' : '') : a[2] && a[2] !== 'bird' ? ' → ' + esc(a[2]) : '') + (a[5] ? ' · ' + pct(a[5]) : '') + (a[6] ? ' <span class="muted">' + esc(a[6]) + '</span>' : '')); } }
  const hi = focusForms && focusForms.includes(m[0]);
  const sub = tt === 'habitat' ? null : subOf(it, 'mens', menKey(tt, mi));
  const MB = [['o', t('men.o.' + tt), t('men.oTip')], ['n', t('men.n.' + tt), t('men.nTip')]];
  const own = sub ? '<span class="bd ' + (sub.d === 'n' ? 'no' : 'alt') + '">' + t('men.you') + (sub.d === 'n' ? t('men.dropped') : '→ ' + esc(targetLabel(sub.target))) + '</span>' : '';
  const mini = tt === 'habitat' ? '' : '<span class="mini">' + MB.map(([v, l, tip]) => '<button class="mb ' + v + (sub && sub.d === v ? ' on' : '') + '" data-men="' + mi + '" data-v="' + v + '" title="' + esc(tip) + '">' + l + '</button>').join('') + '</span>';
  return '<div class="men"' + (hi ? ' style="border-color:var(--unk)"' : '') + '><div class="mh"><b>' + esc(f[0]) + '</b>' + (m[5] ? '<span class="bd plain">' + esc(m[5]) + '</span>' : '') + '<span class="muted">' + esc(e[3] || dateDE(e[2])) + (e[6] ? ' · ' + esc(e[6]) : '') + '</span><span class="sp"></span>' + own + '<a href="#" class="small" data-scan="' + m[1] + '" data-mi="' + mi + '" data-t="' + tt + '">' + esc(e[0]) + ' · ' + t('men.page') + '</a>' + mini + '</div>'
    + snipHtml(m[4], 0.9) + '<div class="kw" data-scan="' + m[1] + '" data-mi="' + mi + '" data-t="' + tt + '">' + excerpt(e[7], m[2], m[3]) + '</div>' + (rd.length ? '<div class="rd">' + rd.join('<br>') + '</div>' : '') + '</div>';
}
function excerpt(text, s, e, ctx) {
  ctx = ctx || 180; if (s < 0) return esc(text.slice(0, 2 * ctx)) + (text.length > 2 * ctx ? ' …' : '');
  let a = Math.max(0, s - ctx), b = Math.min(text.length, e + ctx);
  if (a > 0) { const sp = text.indexOf(' ', a); if (sp > 0 && sp < s) a = sp + 1; }
  if (b < text.length) { const sp = text.lastIndexOf(' ', b); if (sp > e) b = sp; }
  return (a > 0 ? '… ' : '') + esc(text.slice(a, s)) + '<mark>' + esc(text.slice(s, e)) + '</mark>' + esc(text.slice(e, b)) + (b < text.length ? ' …' : '');
}
function namesHtml(it, forms, badges, opts) {
  opts = opts || {}; const tt = ttOf(it);
  const MB = tt === 'taxon' ? [['y', '✓', t('nm.tip.y')], ['o', '↪', t('nm.tip.o')], ['k', '✗', t('nm.tip.k')], ['u', '?', t('nm.tip.u')]] : [['y', '✓', t('nm.tip.y.' + tt)], ['x', '✗', t('nm.tip.x.' + tt)]];
  return '<div class="names">' + forms.map(fi => { const f = (FORMS[tt] || {})[fi]; if (!f) return ''; const b = badges && badges[fi]; const focus = opts.focus && opts.focus.includes(fi); const moved = opts.moved && opts.moved.includes(fi);
    const sub = subOf(it, 'names', lc(f[0])); const st = nameState(it, fi);
    const bd = b ? '<span class="bd ' + (b.d === 'same' ? 'ok' : b.d === 'none' ? 'no' : 'unk') + '" title="' + esc(b.n) + '">' + t('m.machine') + ': ' + (b.d === 'same' ? (moved ? '→ ' + esc(b.de || b.sci) : t('nm.m.same')) : b.d === 'none' ? t('nm.m.none') : t('nm.m.unsure')) + ' · ' + pct(b.c) + '</span>' + sourceIcons(b.s) : (tt === 'taxon' && it.q !== 'unchecked' ? '<span class="bd plain">' + t('nm.check') + '</span>' : '');
    const own = sub ? '<span class="bd ' + ({ y: 'ok', o: 'alt', k: 'no', x: 'no', u: 'unk' })[sub.d] + '">' + t('nm.you') + (sub.d === 'o' ? '→ ' + esc(targetLabel(sub.target)) : t('nm.you.' + sub.d)) + '</span>' : '';
    const mini = moved ? '' : '<span class="mini">' + MB.map(([v, l, tip]) => '<button class="mb ' + v + (sub && sub.d === v ? ' on' : !sub && st === v ? ' soft' : '') + '" data-name="' + fi + '" data-v="' + v + '" title="' + esc(tip) + '">' + l + '</button>').join('') + '</span>';
    const cnt = (it.names || []).find(n => lc(n[0]) === lc(f[0]));
    return '<div class="nm' + (focus ? ' focus' : '') + (moved ? ' moved' : '') + '"><span class="nn">' + esc(f[0]) + '</span><span class="ct">' + fmt(cnt ? cnt[1] : f[1]) + '×</span>' + (f[3] && tt === 'taxon' ? '<span class="bd plain" title="' + esc(t('nm.clsTip')) + '">' + esc(f[3]) + '</span>' : '') + bd + own + '<span class="why">' + esc(b ? b.n : '') + '</span>' + mini + '</div>'; }).join('') + '</div>';
}
function decisionHtml(it) {
  const d = dec(it); if (!d || (!d.d && !subCount(it))) return '';
  const cls = d.d ? ({ a: 'a', y: 'y', r: 'r', k: 'k', o: 'o', e: 'o', u: 'u' }[d.d] || 'o') : 'o';
  return '<div class="state ' + cls + '"><b>' + (d.d ? t('d.decided') : '') + esc(decLabel(it, d)) + '</b><span class="muted small">' + esc(d.by || '') + ' ' + esc((d.t || '').slice(0, 16).replace('T', ' ')) + '</span><input type="text" id="note" placeholder="' + t('st.note') + '" value="' + esc(d.note || '') + '"><button class="lbtn" data-clear="1">' + t('st.clear') + '</button></div>';
}
function actionsHtml(it) {
  const d = dec(it) || {}; const on = k => d.d === k ? ' on' : '';
  const B = (k, label, key) => '<button class="btn ' + k + on(k) + '" data-act="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  let q = '', btns = '', hint = '';
  if (it.q === 'change') { q = t('q.change'); btns = B('a', t('b.accept'), 'J') + B('r', t('b.reject'), 'N') + B('o', t('b.other'), 'A') + B('u', t('b.unsure'), 'U'); }
  else if (it.q === 'sample' || it.q === 'rest') { q = t('q.sample'); btns = B('a', t('b.yes'), 'J') + B('r', t('b.no'), 'N') + B('o', t('b.correctIs'), 'A') + B('u', t('b.unsure'), 'U'); hint = t('hint.sampleNo'); }
  else if (it.t === 'habitat' && (it.q === 'habitat' || it.q === 'open')) {
    q = it.cur ? t('q.habOk') : t('q.habWhich'); btns = (it.cur ? B('y', t('b.habOk'), 'J') : '') + B('o', t('b.habOther'), 'A') + B('k', t('b.habNone'), 'N') + B('u', t('b.unsure'), 'U');
    if (it.sug && it.sug.code && (!it.cur || it.sug.code !== it.cur.code) && EUNIS.has(it.sug.code)) btns += '<button class="btn sm" data-hsug="1">' + t('b.habSug', esc(it.sug.code)) + '</button>';
  }
  else if (it.q === 'open' || it.q === 'unchecked') {
    if (it.t === 'taxon' && it.k === 'name-unsure') { q = t('q.nameUnsure', esc(it.label)); btns = B('y', t('b.belong'), 'J') + B('o', t('b.otherSpecies'), 'A') + B('k', t('b.notBird'), 'N') + B('u', t('b.unsure'), 'U'); }
    else if (it.t === 'taxon') { q = it.cur ? t('q.taxonOk') : t('q.taxonWhich'); btns = (it.cur ? B('y', t('b.speciesOk'), 'J') : '') + B('o', it.cur ? t('b.otherSpecies') : t('b.chooseSpecies'), 'A') + B('k', t('b.notBird'), 'N') + B('u', t('b.unsure'), 'U'); }
    else if (it.t === 'person') { q = it.cur.qid || it.cur.gnd ? t('q.personOk') : t('q.personWho'); btns = (it.cur.qid || it.cur.gnd ? B('y', t('b.linkOk'), 'J') : '') + B('o', t('b.chooseCand'), 'A') + B('k', t('b.noLink'), 'N') + B('u', t('b.unsure'), 'U'); }
    else if (it.t === 'place') { q = it.cur.lat != null ? t('q.placeOk') : t('q.placeWhere'); btns = (it.cur.lat != null ? B('y', t('b.locOk'), 'J') : '') + B('o', t('b.setLoc'), 'A') + B('k', t('b.notPlace'), 'N') + B('u', t('b.unsureNoLoc'), 'U'); }
  }
  else if (it.q === 'text') { q = t('q.text') + ' <small>' + t('q.textTip') + '</small>'; btns = B('a', t('b.accept'), 'J') + B('r', t('b.reject'), 'N') + B('o', t('b.readOther'), 'A') + B('u', t('b.unsure'), 'U'); }
  else if (it.q === 'extract') { q = t('q.entry') + ' <small>' + t('q.entryTip') + '</small>'; btns = B('a', t('b.findingOk'), 'J') + B('r', t('b.findingWrong'), 'N') + B('u', t('b.unsure'), 'U'); }
  else if (it.q === 'tc') { q = t('q.tc') + ' <small>' + t('q.tcTip') + '</small>'; btns = B('a', t('b.tcAccept'), 'J') + B('r', t('b.tcReject'), 'N') + B('e', t('b.tcEdit'), 'E') + B('u', t('b.unsure'), 'U'); }
  else if (it.q === 'qa') { q = t('q.qa'); btns = B('a', t('b.qaConfirm'), 'J') + B('r', t('b.qaFalse'), 'N') + B('o', t('b.qaFix'), 'A') + B('u', t('b.unsure'), 'U'); hint = t('hint.qaU'); }
  return '<div class="q">' + q + '</div><div class="acts">' + btns + '</div>' + (hint ? '<div class="hint">' + hint + '</div>' : '') + '<div id="other"></div>' + decisionHtml(it);
}

// ----- taxon entity
function taxonBox(cur0, cls, head) {
  if (!cur0 || (!cur0.key && !cur0.sci)) return '<div class="box gone ' + cls + '"><div class="bh">' + head + '</div><div class="bv muted">' + t('box.nolink') + '</div></div>';
  return '<div class="box ' + cls + '"><div class="bh">' + head + '</div><div class="bv">' + esc(cur0.de && !Array.isArray(cur0.de) ? cur0.de : cur0.label || '') + (cur0.sci ? ' <i>' + esc(cur0.sci) + '</i>' : '') + '</div><div class="bd2">' + [cur0.rank, cur0.family, cur0.key ? '<a href="https://www.gbif.org/species/' + esc(cur0.key) + '" target="_blank" rel="noopener">' + t('lbl.gbif', esc(cur0.key)) + '</a>' : ''].filter(Boolean).join(' · ') + '</div></div>';
}
function cardTaxon(it) {
  let h = headHtml(it, esc(it.label) + (it.sci ? ' <i>' + esc(it.sci) + '</i>' : ''), (it.forms.length === 1 ? t('n.name') : t('n.names', it.forms.length)) + (it.llm ? ' · ' + t('card.llm', esc(it.llm)) : ''));
  const verdict = t('v.taxon.' + it.k);
  const curHead = it.now ? t('box.before') : t('box.current');
  if (it.q === 'unchecked') h += '<div class="diff2">' + taxonBox(it.cur && Object.assign({ label: it.label }, it.cur), '', t('box.inGraph')) + '</div>';
  else if (it.k === 'ok' || it.k === 'name-unsure') h += '<div class="diff2"><div class="box"><div class="bh">' + t('box.confirmed') + '</div><div class="bv">' + esc(it.label) + ' <i>' + esc(it.sci) + '</i></div><div class="bd2">' + [it.cur.rank, it.cur.family, '<a href="https://www.gbif.org/species/' + esc(it.cur.key) + '" target="_blank" rel="noopener">' + t('lbl.gbif', esc(it.cur.key)) + '</a>', it.cur.de && it.cur.de.length ? t('box.deNames', esc(it.cur.de.slice(0, 6).join(', '))) : ''].filter(Boolean).join(' · ') + '</div></div></div>';
  else h += '<div class="diff2">' + taxonBox(it.cur && Object.assign({ label: it.label }, it.cur, { de: '' }), '', curHead) + '<div class="arrow">→</div>' + (it.k === 'none' ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('box.notaxon') + '</div><div class="bd2">' + t('box.notaxonTip') + '</div></div>' : it.k === 'unsure' ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv muted">' + t('box.decide') + '</div></div>' : taxonBox(it.prop, 'prop', t('box.proposal'))) + '</div>';
  h += nowHtml(it) + machineHtml(it, verdict);
  h += '<div class="sec"><h3>' + t('sec.names') + '</h3><span class="lb">' + (it.k === 'name-unsure' ? t('sec.namesUnsure') : t('sec.namesTip')) + '</span></div>' + namesHtml(it, it.forms.slice(0, 40), it.badges, { focus: it.focus || it.doubt, moved: it.moved, mini: true }) + (it.forms.length > 40 ? '<div class="muted small">' + t('sec.moreNames', it.forms.length - 40) + '</div>' : '');
  h += evidenceHtml(it, it.ev, 'taxon', { focus: it.focus || it.doubt });
  return h + actionsHtml(it);
}
function cardForm(it) {
  let h = headHtml(it, '„' + esc(it.label) + '“', t('card.formSub', '<b>' + esc(it.cur.label) + '</b> <i>' + esc(it.cur.sci || '') + '</i>') + (it.cls ? ' · ' + t('card.class', esc(it.cls)) : ''));
  h += '<div class="diff2">' + taxonBox(Object.assign({}, it.cur), '', t('box.nameTo')) + '<div class="arrow">→</div>' + (it.k === 'name-none' ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('box.notbird') + '</div><div class="bd2">' + t('box.remove') + '</div></div>' : taxonBox(it.prop, 'prop', t('box.nameToProp'))) + '</div>';
  h += nowHtml(it) + machineHtml(it, it.k === 'name-none' ? t('v.form.none') : t('v.form.moved'));
  h += evidenceHtml(it, it.ev, 'taxon');
  return h + actionsHtml(it);
}
// ----- person
function personBox(qid, gnd, cands, cls, head) {
  if (!qid && !gnd) return '<div class="box gone ' + cls + '"><div class="bh">' + head + '</div><div class="bv muted">' + t('box.nolink') + '</div></div>';
  const c = (cands || []).find(x => x.qid === qid);
  return '<div class="box ' + cls + '"><div class="bh">' + head + '</div><div class="bv">' + esc(c ? c.label : qid || '') + (c && (c.born || c.died) ? ' <i>(' + esc(c.born || '?') + '–' + esc(c.died || '?') + ')</i>' : '') + '</div><div class="bd2">' + [c ? esc(c.desc) : '', qid ? '<a href="https://www.wikidata.org/wiki/' + esc(qid) + '" target="_blank" rel="noopener">' + esc(qid) + ' ↗</a>' : '', gnd ? '<a href="https://d-nb.info/gnd/' + esc(gnd) + '" target="_blank" rel="noopener">GND ' + esc(gnd) + ' ↗</a>' : ''].filter(Boolean).join(' · ') + '</div></div>';
}
function cardPerson(it) {
  let h = headHtml(it, esc(it.label), (it.years ? t('card.mentions', esc(it.years)) + ' · ' : '') + Object.entries(it.roles || {}).map(([r, n]) => esc(r) + ' ' + n).join(', '));
  const verdict = t('v.person.' + it.k);
  if (it.q === 'sample' || it.q === 'rest' || it.q === 'unchecked' || it.k === 'unsure-haslink' || it.k === 'unsure') h += '<div class="diff2">' + personBox(it.cur.qid, it.cur.gnd, it.cands, '', it.cur.qid && it.k === 'link-confirm' ? t('box.confirmed') : t('box.inGraph')) + (it.prop && it.prop.gnd && !it.cur.gnd ? '<div class="arrow">+</div><div class="box prop"><div class="bh">' + t('box.addition') + '</div><div class="bv">GND ' + esc(it.prop.gnd) + '</div></div>' : '') + '</div>';
  else h += '<div class="diff2">' + personBox(it.cur.qid, it.cur.gnd, it.cands, '', it.now ? t('box.before') : t('box.current')) + '<div class="arrow">→</div>' + (it.prop && it.prop.qid ? personBox(it.prop.qid, it.prop.gnd, it.cands, 'prop', t('box.proposal')) : '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('box.nolink') + '</div></div>') + '</div>';
  h += nowHtml(it) + machineHtml(it, verdict);
  if (it.opus) h += '<div class="mach" style="border-color:var(--alt);background:var(--alt-soft)"><div class="mh"><b style="color:var(--alt)">' + t('m.earlier') + ':</b> ' + esc(it.opus[0] === 'none' ? t('m.nolink') : it.opus[0] === 'unclear' ? t('m.unclear') : it.opus[0]) + ' · ' + pct(it.opus[1]) + '</div><div class="reason">„' + esc(it.opus[2]) + '“</div></div>';
  h += '<div class="sec"><h3>' + t('sec.names') + '</h3><span class="lb">' + t('sec.names.person') + '</span></div>' + namesHtml(it, it.forms.slice().sort((a, b) => FORMS.person[b][1] - FORMS.person[a][1]).slice(0, 25), null, { mini: true }) + (it.forms.length > 25 ? '<div class="muted small">' + t('sec.moreNames', it.forms.length - 25) + '</div>' : '');
  if ((it.cands || []).length || (it.gcands || []).length) {
    h += '<div class="sec"><h3>' + t('sec.cands') + '</h3><span class="lb">' + t('sec.candsTip') + '</span></div><div class="cands">'
      + it.cands.slice(0, 8).map((c, k) => '<div class="cand' + (it.prop && c.qid === it.prop.qid ? ' on' : '') + (c.qid === it.cur.qid ? ' cur' : '') + '" data-cand="' + k + '"><span class="k">' + (k + 1) + '</span><div><div class="cl">' + esc(c.label) + (c.born || c.died ? ' <span class="muted">(' + esc(c.born || '?') + '–' + esc(c.died || '?') + ')</span>' : '') + (c.human === false ? ' <span class="bd no">' + t('lbl.human') + '</span>' : '') + '</div><div class="cd">' + esc(c.desc) + (c.gnd ? ' · GND ' + esc(c.gnd) : '') + '</div></div><span class="ci"><a href="https://www.wikidata.org/wiki/' + esc(c.qid) + '" target="_blank" rel="noopener">' + esc(c.qid) + '</a></span></div>').join('')
      + (it.gcands || []).slice(0, 6).map((c, k) => '<div class="cand' + (it.prop && c.gnd === it.prop.gnd ? ' on' : '') + '" data-gcand="' + k + '"><span class="k">G</span><div><div class="cl">' + esc(c.name) + (c.born || c.died ? ' <span class="muted">(' + esc(c.born || '?') + '–' + esc(c.died || '?') + ')</span>' : '') + '</div><div class="cd">' + esc([c.occ, c.places].filter(Boolean).join(' · ')) + (c.wd ? ' · Wikidata ' + esc(c.wd) : '') + '</div></div><span class="ci"><a href="https://d-nb.info/gnd/' + esc(c.gnd) + '" target="_blank" rel="noopener">GND ' + esc(c.gnd) + '</a></span></div>').join('') + '</div>';
  }
  h += evidenceHtml(it, it.ev, 'person');
  return h + actionsHtml(it);
}
// ----- place
function placeBox(p, cls, head) {
  if (!p || p.lat == null) return '<div class="box gone ' + cls + '"><div class="bh">' + head + '</div><div class="bv muted">' + t('box.noloc') + '</div></div>';
  return '<div class="box ' + cls + '"><div class="bh">' + head + '</div><div class="bv">' + esc(p.name || p.gname || '') + (p.type ? ' <i>' + esc(p.type === 'Bildlesung' ? t('box.scanType') : p.type) + '</i>' : '') + '</div><div class="bd2">' + [(+p.lat).toFixed(4) + ', ' + (+p.lon).toFixed(4), p.unc ? '± ' + fmt(p.unc) + ' m' : '', p.gn ? '<a href="https://www.geonames.org/' + esc(p.gn) + '" target="_blank" rel="noopener">GeoNames ' + esc(p.gn) + ' ↗</a>' : '', p.qid ? '<a href="https://www.wikidata.org/wiki/' + esc(p.qid) + '" target="_blank" rel="noopener">' + esc(p.qid) + ' ↗</a>' : '', p.osm ? '<a href="https://www.openstreetmap.org/' + esc(p.osm) + '" target="_blank" rel="noopener">OSM ↗</a>' : '', p.km != null ? t('box.kmAnchor', esc(p.km)) : '', p.src ? esc(p.src) : ''].filter(Boolean).join(' · ') + '</div></div>';
}
function cardPlace(it) {
  const g = it.graph || {};
  const curP = it.cur.lat != null ? Object.assign({ gname: g.geonames_name ? g.geonames_name + (g.feature ? ' (' + g.feature + (g.country ? ', ' + g.country : '') + ')' : '') : '', name: '' }, it.cur, { src: g.source ? g.source + (g.linking_note ? ' — ' + g.linking_note : '') : it.cur.src || '' }) : null;
  let h = headHtml(it, esc(it.label), [it.cur.kind ? esc(it.cur.kind) : '', Object.entries(it.roles || {}).map(([r, n]) => esc(r) + ' ' + n).join(', '), it.anchors && it.anchors.length ? t('card.anchors', it.anchors.map(a => esc(a.place) + ' (' + a.n + (a.km != null ? ', ' + a.km + ' km' : '') + ')').join(', ')) : ''].filter(Boolean).join(' · '));
  const verdict = t('v.place.' + it.k);
  if (it.q === 'change') h += '<div class="diff2">' + placeBox(curP, '', it.now ? t('box.before') : t('box.current')) + '<div class="arrow">→</div>' + (it.k === 'not_a_place' ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('box.notplace') + '</div><div class="bd2">' + t('box.remove') + '</div></div>' : placeBox(it.prop, 'prop', t('box.proposal'))) + '</div>';
  else h += '<div class="diff2">' + placeBox(curP, '', it.k === 'ok' ? t('box.confirmed') : t('box.inGraph')) + (it.hint ? '<div class="arrow">?</div><div class="box prop gone"><div class="bh">' + t('box.hint') + '</div><div class="bv" style="font-weight:500;font-size:14px">' + esc(it.hint) + '</div>' + (it.hint_ll ? '<div class="bd2">' + t('box.hintCoords', it.hint_ll[0], it.hint_ll[1]) + '</div>' : '') + '</div>' : '') + '</div>';
  h += nowHtml(it) + machineHtml(it, verdict);
  if (it.scan && it.scan.length) h += '<div class="mach" style="border-color:var(--scan);background:var(--scan-soft)"><div class="mh"><b style="color:var(--scan)">' + t('m.scan') + ':</b> ' + sourceChips(['scan']) + '</div>' + it.scan.map(r => '<div>' + (r.legible ? '„' + esc(r.reading) + '“' + (r.same === false ? ' <span class="bd unk">' + t('m.transcription', esc(r.written)) + '</span>' : '') + (r.is_place === false ? ' → <b>' + t('m.notplace') + '</b>' : r.place ? ' → <b>' + esc(r.place) + '</b>' + (r.region ? ' <span class="muted">(' + esc(r.region) + ')</span>' : '') : '') + (r.lat != null ? ' · ' + (+r.lat).toFixed(4) + ', ' + (+r.lon).toFixed(4) + (r.unc ? ' ± ' + fmt(r.unc) + ' m' : '') : '') + ' · ' + pct(r.conf) : '<span class="muted">' + t('m.illegible') + '</span>') + (r.note ? ' <span class="muted">' + esc(r.note) + '</span>' : '') + ' <span class="muted small">(' + esc(r.entry) + ')</span></div>').join('') + '</div>';
  h += '<div id="map"></div><div class="maplegend"><span><i style="background:#c0392b"></i>' + t('map.cur') + '</span><span><i style="background:#0e6a70"></i>' + t('map.prop') + '</span><span><i style="background:#2f5f9a"></i>' + t('map.cand') + '</span><span><i style="background:#888"></i>' + t('map.anchor') + '</span><span><i style="background:#b35a1a"></i>' + t('map.scan') + '</span><span><i style="background:#e67e22"></i>' + t('map.own') + ' <span class="muted">(' + t('map.ownTip') + ')</span></span></div>';
  if (it.forms.length > 1) h += '<div class="sec"><h3>' + t('sec.names') + '</h3><span class="lb">' + t('sec.names.place') + '</span></div>' + namesHtml(it, it.forms.slice().sort((a, b) => FORMS.place[b][1] - FORMS.place[a][1]).slice(0, 25), null, { mini: true });
  h += evidenceHtml(it, it.ev, 'place');
  return h + actionsHtml(it);
}
// ----- habitat (EUNIS)
const EUNIS_URL = code => 'https://biodiversity.europa.eu/resources/search-habitat/eunis-habitat-types-hierarchical-view-2012?searchTerm=' + encodeURIComponent(code);
function eunisBox(x, cls, head) {
  if (!x || !x.code) return '<div class="box gone ' + cls + '"><div class="bh">' + head + '</div><div class="bv muted">' + t('hab.none') + '</div></div>';
  const ex = EUNIS.get(x.code) || [];
  return '<div class="box ' + cls + '"><div class="bh">' + head + '</div><div class="bv">' + esc(x.code) + ' <span style="font-weight:500">' + esc(x.label || ex[1] || '') + '</span></div><div class="bd2">' + [x.match ? t('hab.match', esc(x.match)) : '', ex[2] ? t('hab.level', ex[2]) : '', ex[3] ? t('hab.parent', esc(ex[3] + ' ' + ((EUNIS.get(ex[3]) || [])[1] || ''))) : '', x.conf ? t('hab.conf', esc(x.conf)) : '', '<a href="' + EUNIS_URL(x.code) + '" target="_blank" rel="noopener">BISE ↗</a>'].filter(Boolean).join(' · ') + '</div></div>';
}
function cardHabitat(it) {
  let h = headHtml(it, esc(it.label), it.forms.length === 1 ? t('n.name') : t('n.names', it.forms.length));
  const s = it.sug && it.sug.code && (!it.cur || it.sug.code !== it.cur.code) ? it.sug : null;
  if (it.q === 'change') h += '<div class="diff2">' + eunisBox(it.cur, '', it.now ? t('box.before') : t('box.current')) + '<div class="arrow">→</div>' + (it.prop && it.prop.none ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('hab.notHab') + '</div><div class="bd2">' + t('box.remove') + '</div></div>' : eunisBox(it.prop, 'prop', t('box.proposal'))) + '</div>';
  else h += '<div class="diff2">' + eunisBox(it.cur, '', it.k === 'h-ok' ? t('box.confirmed') : t('box.inGraph')) + (s ? '<div class="arrow">?</div>' + eunisBox(s, 'prop', t('hab.sug')) : '') + '</div>';
  if (it.q !== 'habitat') h += nowHtml(it) + machineHtml(it, t('v.habitat.' + it.k));
  if (it.sug && it.sug.note) h += '<div class="hint">' + t('hab.note', esc(it.sug.note)) + '</div>';
  h += '<div class="sec"><h3>' + t('sec.names') + '</h3><span class="lb">' + t('sec.names.habitat') + '</span></div>' + namesHtml(it, it.forms.slice(0, 25), null, { mini: true });
  h += evidenceHtml(it, it.ev, 'habitat');
  return h + actionsHtml(it);
}
// ----- mention / text / entry
function cardMention(it) {
  const e = E[it.ei];
  let h = headHtml(it, '„' + esc(it.label) + '“ · ' + esc(e[0]), esc(e[3] || dateDE(e[2])) + (e[6] ? ' · ' + esc(e[6]) : '') + ' · ' + t('card.single'));
  h += '<div class="diff2"><div class="box"><div class="bh">' + t('box.current') + '</div><div class="bv">' + esc(it.label) + '</div></div><div class="arrow">→</div>' + (it.prop.action === 'drop' ? '<div class="box prop gone"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + t('box.drop') + '</div></div>' : '<div class="box prop"><div class="bh">' + t('box.proposal') + '</div><div class="bv">' + esc(it.prop.value) + (it.prop.sci ? ' <i>' + esc(it.prop.sci) + '</i>' : '') + '</div><div class="bd2">' + (it.prop.key ? '<a href="https://www.gbif.org/species/' + esc(it.prop.key) + '" target="_blank" rel="noopener">' + t('lbl.gbif', esc(it.prop.key)) + '</a>' : '') + '</div></div>') + '</div>';
  h += machineHtml(it, it.prop.action === 'drop' ? t('v.mention.drop') : t('v.mention.replace'));
  if (it.stale) h += '<div class="hint">' + t('chip.staleTip') + '</div>';
  h += it.ev.length ? evidenceHtml(it, it.ev, 'taxon') : '<div class="sec"><h3>' + t('sec.entry') + '</h3></div><div class="men"><div class="kw" data-scan="' + it.ei + '">' + hlWord(e[7], it.label) + '</div></div>';
  return h + actionsHtml(it);
}
function hlWord(text, word) { const i = word ? text.toLowerCase().indexOf(word.toLowerCase()) : -1; if (i < 0) return esc(text.slice(0, 400)) + (text.length > 400 ? ' …' : ''); return excerpt(text, i, i + word.length, 220); }
function cardText(it) {
  const e = E[it.ei];
  let h = headHtml(it, '„' + esc(it.label) + '“ → „' + esc(it.prop.value) + '“', esc(e[0]) + ' · ' + esc(e[3] || dateDE(e[2])) + (e[6] ? ' · ' + esc(e[6]) : '') + ' · ' + t('card.concerns', esc(STR['for.' + it.for] ? t('for.' + it.for) : it.for)));
  h += machineHtml(it, t('v.text') + (it.found ? '' : ' · <b>' + t('card.notInText') + '</b>'));
  h += '<div class="sec"><h3>' + t('sec.entry') + '</h3><span class="lb">' + t('sec.entryTip') + '</span></div><div class="men"><div class="kw" data-scan="' + it.ei + '">' + hlWord(e[7], it.label) + '</div></div>';
  return h + actionsHtml(it);
}
function cardEntry(it) {
  const e = E[it.ei]; const d = dec(it) || {}; const ov = d.obs || {}; const om = d.miss || {}; const eff = d.d === 'a' ? 'y' : d.d === 'r' ? 'n' : d.d === 'u' ? 'u' : '';
  const mini = (kind, key, c0) => '<span class="mini">' + [['y', '✓'], ['n', '✗'], ['u', '?']].map(([v, l]) => '<button class="mb ' + v + (c0 && c0.d === v ? ' on' : !c0 && eff === v ? ' soft' : '') + '" data-' + kind + '="' + esc(key) + '" data-v="' + v + '" title="' + esc(t('obs.tip.' + v)) + '">' + l + '</button>').join('') + '</span>';
  const ok = b => b ? '✓' : '✗';
  let h = '<div class="row" style="margin-bottom:6px"><span class="bd mach big">' + t('cat.entry') + '</span><span class="bd ' + (it.wrong + it.spurious ? 'no' : 'ok') + ' big">' + t('entry.counts', it.ok, it.wrong, it.spurious, it.unsure) + '</span>' + (it.missing ? '<span class="bd unk big">' + t('entry.missing', it.missing) + '</span>' : '') + (it.legible ? '' : '<span class="bd unk big">' + t('entry.illegible') + '</span>') + roundChip(it, true) + '</div>';
  h += '<h1 class="t">' + esc(e[0]) + ' <i>' + esc(e[3] || dateDE(e[2])) + '</i></h1><p class="sub">' + esc(e[6]) + ' · ' + t('entry.vol', it.vol) + ' · ' + esc(e[4]) + ' · ' + t('entry.fields', ok(it.date_ok), ok(it.place_ok), ok(it.kind_ok)) + (e[8] && e[8].length > 1 ? ' · ' + t('entry.pages', e[8].length) : '') + '</p>';
  h += '<div class="mach"><div class="mh"><b>' + t('entry.finding') + ' ' + roundChip(it) + ':</b> ' + sourceChips(['entry-check']) + '</div><div class="reason">' + esc(it.summary) + '</div></div>';
  if (it.stale) h += '<div class="nowline"><span class="bd unk">' + t('row.stale') + '</span> ' + t('entry.stale', esc(D.export || '')) + (it.now_obs && it.now_obs.length ? '<div class="small muted" style="margin-top:3px">' + esc(it.now_obs.join(' · ')) + '</div>' : '') + '</div>';
  const okey = o => lc(o.written) + '|' + (o.occ || 0);
  h += '<div class="sec"><h3>' + t('sec.obs') + '</h3><span class="lb">' + t('sec.obsTip') + '</span></div><table class="tbl"><tr><th>#</th><th>' + t('obs.h.written') + '</th><th>' + t('obs.h.taxon') + '</th><th>' + t('obs.h.count') + '</th><th>' + t('obs.h.loc') + '</th><th>' + t('obs.h.verdict') + '</th><th>' + t('obs.h.reason') + '</th><th>' + t('obs.h.you') + '</th></tr>'
    + it.obs.map(o => '<tr class="' + o.v + '"><td class="mono muted">' + o.i + '</td><td><b>' + esc(o.written) + '</b></td><td>' + esc(o.taxon) + ' <i class="muted">' + esc(o.sci) + '</i></td><td class="mono">' + esc(o.count || (o.cq || '')) + '</td><td class="small">' + esc([o.locality, o.observer].filter(Boolean).join(' · ')) + '</td><td><span class="bd ' + ({ ok: 'ok', wrong: 'no', spurious: 'alt', unsure: 'unk' })[o.v] + '">' + (o.v === 'wrong' ? t('obs.wrong', o.fields.join(', ')) : t('obs.' + o.v)) + '</span></td><td class="small">' + esc(o.reason) + (o.corr ? '<div class="mono" style="margin-top:2px">' + esc(Object.entries(o.corr).filter(([k, v]) => v).map(([k, v]) => k + ': ' + v).join(' · ')) + '</div>' : '') + '</td><td>' + mini('obs', okey(o), ov[okey(o)]) + '</td></tr>').join('') + '</table>';
  const mkey = m => lc(m.text).trim();
  if (it.miss.length) h += '<div class="sec"><h3>' + t('sec.missing') + '</h3><span class="lb">' + t('sec.missingTip') + '</span></div><table class="tbl"><tr><th>' + t('miss.h.kind') + '</th><th>' + t('miss.h.text') + '</th><th>' + t('miss.h.sp') + '</th><th>' + t('miss.h.note') + '</th><th>' + t('obs.h.you') + '</th></tr>' + it.miss.map(m => '<tr><td>' + esc(m.kind) + '</td><td class="small">' + esc(m.text) + '</td><td>' + esc([m.de, m.sci ? '(' + m.sci + ')' : '', m.count].filter(Boolean).join(' ')) + '</td><td class="small muted">' + esc(m.note) + '</td><td>' + mini('miss', mkey(m), om[mkey(m)]) + '</td></tr>').join('') + '</table>';
  if (it.misread.length) h += '<div class="sec"><h3>' + t('sec.misread') + '</h3><span class="lb">' + t('sec.misreadTip') + '</span></div><div class="row">' + it.misread.map(m => '<span class="bd plain">„' + esc(m.old) + '“ → „' + esc(m.new) + '“ <span class="muted">' + esc(m.for) + '</span></span>').join('') + '</div>';
  h += '<div class="hint">' + t('entry.hint') + '</div>';
  h += '<div class="sec"><h3>' + t('sec.transcription') + '</h3><span class="lb">' + t('sec.entryTip') + '</span></div><div class="men"><div class="kw" data-scan="' + it.ei + '">' + esc(e[7]) + '</div></div>';
  return h + actionsHtml(it);
}
// ----- transcript correction
function wordDiff(a, b) {
  const A = stripTags(a).split(/(\s+)/).filter(x => x !== ''), B = stripTags(b).split(/(\s+)/).filter(x => x !== '');
  const n = A.length, m = B.length; if (n * m > 250000) return [esc(stripTags(a)), esc(stripTags(b))];
  const L = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, ha = '', hb = '';
  while (i < n || j < m) {
    if (i < n && j < m && A[i] === B[j]) { ha += esc(A[i]); hb += esc(B[j]); i++; j++; }
    else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) { hb += /^\s+$/.test(B[j]) ? B[j] : '<ins class="df">' + esc(B[j]) + '</ins>'; j++; }
    else { ha += /^\s+$/.test(A[i]) ? A[i] : '<del class="df">' + esc(A[i]) + '</del>'; i++; }
  }
  return [ha || '<span class="muted">' + t('tc.empty') + '</span>', hb || '<span class="muted">' + t('tc.empty') + '</span>'];
}
function cardTc(it) {
  const e = E[it.ei]; const [ha, hb] = wordDiff(it.label, it.new);
  const chips = '<span class="bd mach big">' + t('tck.' + it.k) + '</span>' + (it.applied === 'y' ? '<span class="bd plain big" title="' + esc(t('tc.appliedTip')) + '">' + t('tc.applied') + '</span>' : '<span class="bd unk big" title="' + esc(t('tc.notAppliedTip')) + '">' + t('tc.notApplied') + '</span>')
    + (it.stratum ? '<span class="bd plain big">' + t('chip.tcSample') + '</span>' : '') + (it.rev || []).filter(r => r !== 'not-applied').map(r => '<span class="bd no big">' + t('tcr.' + r) + '</span>').join('');
  let h = '<div class="row" style="margin-bottom:6px">' + chips + '<span class="sp"></span><span class="muted small">' + t('tc.nrec', fmt(it.nrec)) + (it.others ? ' · ' + t('tc.others', fmt(it.others)) : '') + '</span></div>';
  h += '<h1 class="t">' + esc(e[0]) + ' <i>' + esc(e[3] || dateDE(e[2])) + '</i></h1><p class="sub">' + esc(e[6] || '') + ' · ' + t('entry.vol', e[5]) + (it.note ? ' · ' + esc(it.note) : '') + '</p>';
  h += '<div class="diff2 tcdiff"><div class="box' + (it.applied === 'y' ? '' : ' intext') + '"><div class="bh">' + t('tc.old') + (it.applied === 'y' ? '' : ' · ' + t('tc.inText')) + '</div><div class="bv tcv">' + ha + '</div></div><div class="arrow">→</div><div class="box prop' + (it.applied === 'y' ? ' intext' : '') + '"><div class="bh">' + t('tc.new', esc(it.by0 || 'Gemini')) + (it.applied === 'y' ? ' · ' + t('tc.inText') : '') + '</div><div class="bv tcv">' + hb + '</div></div></div>';
  if (it.m) h += '<div class="mach"><div class="mh"><b>' + t('m.machine') + ' R' + it.m.r + ':</b> <span class="bd ' + ({ right: 'ok', partly: 'unk', wrong: 'no', unclear: 'unk' }[it.m.v] || 'plain') + '">' + t('tcm.' + it.m.v) + '</span>' + (it.m.better ? ' · ' + t('tc.better') + ' „<b>' + esc(it.m.better) + '</b>“' : '') + '</div>' + (it.m.reason ? '<div class="reason">„' + esc(it.m.reason) + '“</div>' : '') + '</div>';
  if (it.hl) h += '<div class="sec"><h3>' + t('tc.where') + '</h3><span class="lb">' + t('tc.whereTip') + '</span></div><div class="men">' + snipHtml(it.hl, 1.2) + '</div>';
  const ctx = it.tpos && it.tpos[0] >= 0 ? excerpt(e[7], it.tpos[0], it.tpos[1], 320) : '<span class="bd unk">' + t('tc.notFound') + '</span> ' + esc(e[7].slice(0, 600)) + (e[7].length > 600 ? ' …' : '');
  h += '<div class="sec"><h3>' + t('tc.context') + '</h3><span class="lb">' + t(it.applied === 'y' ? 'tc.contextTipY' : 'tc.contextTipN') + '</span></div><div class="men"><div class="kw" data-scan="' + it.ei + '">' + ctx + '</div></div>';
  return h + actionsHtml(it);
}
// ----- QA flag
function cardQa(it) {
  const e = entryOf(it);
  let h = '<div class="row" style="margin-bottom:6px"><span class="bd unk big">' + esc(qaLabel(it.k)) + '</span><span class="bd plain big">' + esc(it.action) + '</span><span class="sp"></span><span class="muted small mono">' + esc(it.k) + '</span></div>';
  h += '<h1 class="t">' + esc(qaLabel(it.k)) + (it.label ? ' <i>' + esc(stripTags(it.label)) + '</i>' : '') + '</h1><p class="sub">' + esc(it.id) + (e ? ' · ' + esc(e[3] || dateDE(e[2])) + (e[6] ? ' · ' + esc(e[6]) : '') : '') + '</p>';
  h += '<div class="mach" style="border-color:var(--unk);background:var(--unk-soft)"><div class="mh"><b style="color:var(--unk)">' + t('qa.what') + ':</b> ' + esc(STR['qad.' + it.k] ? t('qad.' + it.k) : '') + '</div><div class="reason">' + esc(it.detail) + '</div><div class="pipe">' + t('qa.action.' + (it.action === 'excluded' ? 'excluded' : 'flagged')) + '</div></div>';
  if (e) { const v = stripTags((it.label || '').split('->')[0]).trim(); h += '<div class="sec"><h3>' + t('sec.entry') + '</h3><span class="lb">' + t('sec.entryTip') + '</span></div><div class="men"><div class="kw" data-scan="' + it.ei + '">' + (v.length >= 3 ? hlWord(e[7], v) : esc(e[7].slice(0, 900)) + (e[7].length > 900 ? ' …' : '')) + '</div></div>'; }
  else h += '<div class="hint">' + t('qa.noEntry') + '</div>';
  return h + actionsHtml(it);
}
