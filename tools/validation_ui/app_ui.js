// Laubmann-Abgleich v4 — part 2: tabs, queue, scan panel, line images, mention cards.
const cur = { tab: 'check', type: 'taxon', list: [], shown: 0, sel: null, pos: -1, focus: 'e' };
const ui = { open: new Set(), all: new Set(), panel: null, full: new Set(), mapView: null, word: null, nword: null };

// ---------------------------------------------------------------- items per task
function checkItems(t) { return X[t].ents.filter(e => e.names.length && linked(t, e)); }
function linkItems(t) { return X[t].ents.filter(e => e.names.length && !linked(t, e)); }
function namesItems(t) { return X[t].ents.filter(e => e.names.length && (nameIssues(t, e).risky || nameIssues(t, e).inc)); }
function tabItems(tab, t) {
  if (tab === 'check') return checkItems(t);
  if (tab === 'link') return linkItems(t);
  if (tab === 'names') return namesItems(t);
  if (tab === 'read') return READ;
  if (tab === 'eval') { if (!tabItems.ev) tabItems.ev = P.sample.map((mi, k) => ({ mi, k, key: X.taxon.mkey[mi], ei: P.taxon.men[mi][1] })); return tabItems.ev; }
  if (tab === 'qa') { if (!tabItems.qa) { const ord = ['non_bird', 'low_confidence_taxon', 'date_out_of_span', 'implausible_date', 'date_year_corrected', 'date_from_position', 'date_out_of_coverage', 'nonplace', 'record_type_conflict', 'duplicate_entry', 'volume_reassigned', 'date_corrected', 'no_observations', 'empty'];
    tabItems.qa = P.qa.rows.map((r, i) => ({ r, i, ei: P.qa.ei[i], key: r[0] + '|' + r[2] + '|' + r[4] })).sort((a, b) => (ord.indexOf(a.r[2]) + 99) % 99 - (ord.indexOf(b.r[2]) + 99) % 99 || a.r[0].localeCompare(b.r[0])); } return tabItems.qa; }
  return [];
}
function itemState(tab, t, it) {
  if (tab === 'check' || tab === 'link') return entState(t, it);
  if (tab === 'names') return namesState(t, it);
  if (tab === 'read') return readState(it);
  if (tab === 'eval') { const d = S.ev[it.key]; return d && d.d ? ({ y: 'y', n: 'r', u: 'u' }[d.d]) : ''; }
  if (tab === 'qa') { const d = S.qa[it.key]; return d && d.d ? ({ y: 'y', n: 'r', u: 'u' }[d.d]) : ''; }
  return '';
}
const selKey = it => it.key != null ? it.key : it.t + ':' + it.i;
function tabCount(tab) {
  if (TAB[tab].typed) return TYPES.reduce((a, t) => a + tabItems(tab, t).filter(e => !DONE(itemState(tab, t, e))).length, 0);
  if (tab === 'read') return READ.filter(it => !DONE(itemState('read', 'taxon', it))).length;
  if (tab === 'eval') return tabItems('eval').filter(it => !itemState('eval', 'taxon', it)).length;
  if (tab === 'qa') return tabItems('qa').filter(it => QA_DEFAULT.includes(it.r[2]) && !itemState('qa', 'taxon', it)).length;
  return '';
}
function renderTabs() {
  $('#tabs').innerHTML = TABS.map(t => { const c = tabCount(t.id); return '<button class="tab' + (cur.tab === t.id ? ' on' : '') + '" data-tab="' + t.id + '">' + esc(t.label) + (c !== '' ? '<span class="c">' + fmt(c) + '</span>' : '') + '</button>'; }).join('');
}
$('#tabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) openTab(b.dataset.tab); });

// ---------------------------------------------------------------- queue
const TASK_TEXT = {
  check: ['Verknüpfungen prüfen', 'Ist der Normdatensatz richtig? Gehören alle Namen dazu?'],
  link: ['Verknüpfen', 'Welcher Normdatensatz gehört zu diesem Eintrag? Oder ist es dasselbe wie ein schon verknüpfter?'],
  names: ['Namen zusammenführen', 'Welche geschriebenen Namen gehören zu diesem Eintrag?'],
  read: ['Zweitlesung', 'Zwei Modelle haben die Zeile im Scan gelesen und die Art bestimmt. Wo sie von Transkription oder Graph abweichen: Was stimmt?'],
  eval: ['Stichprobe', 'Zufällige Belege: Ist die Art richtig bestimmt?'], qa: ['Hinweise', 'Automatische Prüfungen bestätigen oder widerlegen.'], log: ['Protokoll', ''],
};
function openTab(tab, keepSel) {
  cur.tab = tab; S.ui.tab = tab; ui.panel = null; renderTabs();
  const T = TAB[tab];
  $('#main').classList.toggle('noscan', T.kind === 'log' || (tab === 'names' ? S.ui.scanNames !== true : S.ui.noscan === true));   // Namen: checkboxes only, the scan stays away unless asked (B)
  $('#qtitle').textContent = TASK_TEXT[tab][0];
  if (T.kind === 'log') { $('#qtypes').style.display = 'none'; $('#qcount').textContent = ''; $('#pbar').innerHTML = ''; $('#pnote').textContent = ''; $('.qctl').style.display = 'none'; $('#qsearch').style.display = 'none'; $('#qlist').innerHTML = '<div class="qmore">Alle Entscheidungen stehen rechts.</div>'; cur.sel = null; renderLog(); return; }
  $('.qctl').style.display = ''; $('#qsearch').style.display = '';
  $('#qtypes').style.display = T.typed ? '' : 'none';
  if (T.typed) { cur.type = S.ui.type[tab] || cur.type || 'taxon'; renderTypes(); }
  const shows = [['open', 'Offen'], ['done', 'Erledigt'], ['u', 'Unsicher'], ['all', 'Alle']];
  $('#qshow').innerHTML = shows.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('');
  $('#qshow').value = S.ui.show[tab] || 'open';
  const sorts = T.typed ? [['n', 'Häufigste zuerst'], ['alpha', 'Alphabetisch']] : tab === 'read' ? [['ag', 'Sicherste Lesung zuerst'], ['kind', 'Nach Art der Abweichung'], ['n', 'Häufigste Namen zuerst']] : [['order', 'Reihenfolge']];
  $('#qsort').innerHTML = sorts.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('');
  $('#qsort').value = S.ui.sort[tab] && sorts.some(s => s[0] === S.ui.sort[tab]) ? S.ui.sort[tab] : sorts[0][0];
  $('#qsearch').value = '';
  buildList();
  const want = keepSel != null ? keepSel : S.ui.sel[tab + ':' + cur.type];
  const pos = want != null ? cur.list.findIndex(it => selKey(it) === want) : -1;
  if (pos < 0 && want != null) { const it = tabItems(tab, cur.type).find(x => selKey(x) === want); if (it) { selectItem(it); return; } }
  selectPos(pos >= 0 ? pos : cur.list.length ? 0 : -1);
}
function renderTypes() {
  $('#qtypes').innerHTML = TYPES.map(t => { const items = tabItems(cur.tab, t); const open = items.filter(e => !DONE(itemState(cur.tab, t, e))).length; return '<button class="' + (cur.type === t ? 'on' : '') + '" data-type="' + t + '">' + esc(TT[t].tab) + '<small>' + fmt(open) + ' offen</small></button>'; }).join('');
}
$('#qtypes').addEventListener('click', e => { const b = e.target.closest('[data-type]'); if (!b) return; cur.type = b.dataset.type; S.ui.type[cur.tab] = cur.type; save(); openTab(cur.tab); });
function buildList() {
  const tab = cur.tab, t = cur.type; const items = tabItems(tab, t); const show = $('#qshow').value; const q = fold($('#qsearch').value.trim());
  let list = items.filter(it => {
    const st = itemState(tab, t, it);
    if (show === 'open' && (tab === 'names' ? st === 'y' || st === 'r' : DONE(st))) return false;
    if (show === 'done' && !DONE(st)) return false;
    if (show === 'u' && st !== 'u') return false;
    if (tab === 'qa' && show === 'open' && !QA_DEFAULT.includes(it.r[2])) return false;
    if (q && !fold(itemText(tab, t, it)).includes(q)) return false;
    return true;
  });
  const sort = $('#qsort').value;
  if (TAB[tab].typed) list = list.slice().sort(sort === 'alpha' ? (a, b) => a.label.localeCompare(b.label, 'de') : (a, b) => b.n - a.n);
  else if (tab === 'read' && sort === 'n') list = list.slice().sort((a, b) => b.n - a.n || b.ag - a.ag);
  else if (tab === 'read' && sort === 'kind') { const o = { species: 0, word: 1, nonbird: 2 }; list = list.slice().sort((a, b) => o[a.kind] - o[b.kind] || a.mis - b.mis || b.ag - a.ag || b.n - a.n); }
  cur.list = list; cur.shown = 0; $('#qlist').innerHTML = ''; $('#qlist').scrollTop = 0; renderMore(); renderProgress();
}
function itemText(tab, t, it) {
  if (TAB[tab].typed) return it.label + ' ' + (t === 'taxon' ? it.e[1] : '') + ' ' + it.names.map(x => x.name).join(' ');
  if (tab === 'read') { const m = P.taxon.men[it.mi]; return writtenOf(it.mi) + ' ' + P.taxon.ent[P.taxon.forms[m[0]][2]][0] + ' ' + E[m[1]][0] + ' ' + READ_KIND[it.kind][0] + ' ' + it.rs.map(r => r.word + ' ' + (r.species || '')).join(' '); }
  if (tab === 'eval') { const m = P.taxon.men[it.mi]; const f = P.taxon.forms[m[0]]; return f[0] + ' ' + P.taxon.ent[f[2]][0] + ' ' + E[m[1]][0]; }
  if (tab === 'qa') return it.r.join(' ');
  return '';
}
function renderProgress() {
  const tab = cur.tab, t = cur.type; let tot = 0, y = 0, n = 0, u = 0;
  for (const it of tabItems(tab, t)) { if (tab === 'qa' && !QA_DEFAULT.includes(it.r[2])) continue; tot++; const st = itemState(tab, t, it); if (st === 'y') y++; else if (st === 'r' || st === 'n') n++; else if (st === 'u') u++; }
  const w = x => (100 * x / Math.max(1, tot)).toFixed(2) + '%';
  $('#pbar').innerHTML = '<i class="y" style="width:' + w(y) + '"></i><i class="n" style="width:' + w(n) + '"></i><i class="u" style="width:' + w(u) + '"></i>';
  $('#pnote').textContent = fmt(y + n) + ' von ' + fmt(tot) + ' erledigt' + (u ? ' · ' + fmt(u) + ' unsicher' : '') + ' — ' + TASK_TEXT[tab][1];
  $('#qcount').textContent = fmt(cur.list.length) + ' in der Liste';
  if (TAB[tab].typed) renderTypes();
}
function qiHtml(pos) {
  const tab = cur.tab, t = cur.type; const it = cur.list[pos]; const st = itemState(tab, t, it); let l1, l2 = '', num = '';
  if (TAB[tab].typed) {
    l1 = esc(it.label) + (t === 'taxon' && it.e[1] ? ' <i class="small muted">' + esc(it.e[1]) + '</i>' : ''); num = fmt(it.n) + '×';
    const iss = nameIssues(t, it);
    if (tab === 'names') l2 = (iss.risky ? '<span class="bd warn">' + iss.risky + ' zu prüfen</span>' : '') + (iss.inc ? '<span class="bd info">' + iss.inc + ' Vorschläge</span>' : '') + '<span class="bd plain">' + it.names.length + ' Namen</span>';
    else l2 = '<span class="bd plain">' + authText(t, it).replace(/<[^>]+>/g, '') + '</span>' + (it.names.length > 1 ? '<span class="bd plain">' + it.names.length + ' Namen</span>' : '') + (t === 'person' && PM[it.i] ? '<span class="bd tip">Modell: ' + esc(PM[it.i][0] === 'none' ? 'keiner' : PM[it.i][0] === 'unclear' ? 'unklar' : PM[it.i][0]) + '</span>' : '');
  } else if (tab === 'read') {
    const m = P.taxon.men[it.mi]; const ce = P.taxon.ent[P.taxon.forms[m[0]][2]];
    l1 = '„' + esc(writtenOf(it.mi)) + '“ <span class="muted small">→ ' + esc(ce[0]) + '</span>';
    const best = it.rs.find(r => r.differs) || it.rs[0];
    l2 = '<span class="bd ' + READ_KIND[it.kind][1] + '">' + READ_KIND[it.kind][0] + '</span><span class="bd ' + (it.ag === 3 ? 'ok' : it.ag === 1 ? 'warn' : 'tip') + '">' + (it.ag === 3 ? 'beide Modelle: „' + esc(it.kind === 'species' ? best.species || best.word : best.word) + '“' : it.ag === 1 ? 'Modelle uneins' : MODEL_DE[best.src] + ': „' + esc(it.kind === 'species' ? best.species || best.word : best.word) + '“') + '</span>' + (it.mis ? '<span class="bd warn" title="Das gelesene Wort steht an anderer Stelle des Eintrags: das Zeilenbild zeigt wohl eine andere Zeile">Zeilenbild verrutscht?</span>' : '') + esc(E[m[1]][3] || E[m[1]][2] || '') + ' · ' + esc(E[m[1]][0]);
    num = sameWord(writtenOf(it.mi), P.taxon.forms[m[0]][0]) ? '<span title="so oft steht dieser Name im Tagebuch">' + fmt(it.n) + '×</span>' : '<span class="muted" title="im Graph unter dem Namen „' + esc(P.taxon.forms[m[0]][0]) + '“">≠ Name</span>';
  } else if (tab === 'eval') { const m = P.taxon.men[it.mi]; const f = P.taxon.forms[m[0]]; l1 = (it.k + 1) + '. ' + esc(f[0]); l2 = esc(E[m[1]][0]) + ' · ' + esc(P.taxon.ent[f[2]][0]); }
  else { const showVal = ['non_bird', 'low_confidence_taxon', 'nonplace'].includes(it.r[2]); l1 = esc((QA_DE[it.r[2]] || [it.r[2]])[0]) + (showVal && it.r[4] ? ': ' + esc(it.r[4]) : ''); l2 = esc(it.r[0]) + ' · ' + (it.r[3] === 'excluded' ? 'entfernt' : 'markiert') + (!showVal && it.r[5] ? ' · ' + esc(it.r[5].slice(0, 70)) : ''); }
  return '<div class="qi' + (pos === cur.pos ? ' on' : '') + '" data-p="' + pos + '"><span class="dot ' + st + '" title="' + esc(STATE_DE[st] || '') + '"></span><div><div class="l1">' + l1 + '</div><div class="l2">' + l2 + '</div></div><div class="num">' + num + '</div></div>';
}
function renderMore() {
  const end = Math.min(cur.list.length, cur.shown + 120); let h = '';
  for (let p = cur.shown; p < end; p++) h += qiHtml(p);
  const m = $('#qlist .qmore'); if (m) m.remove();
  $('#qlist').insertAdjacentHTML('beforeend', h); cur.shown = end;
  if (cur.shown < cur.list.length) $('#qlist').insertAdjacentHTML('beforeend', '<div class="qmore">weitere beim Scrollen …</div>');
  if (!cur.list.length) $('#qlist').innerHTML = '<div class="qmore">Nichts in dieser Auswahl.' + ($('#qshow').value === 'open' ? ' Alles erledigt. 🎉' : '') + '</div>';
}
$('#qlist').addEventListener('scroll', e => { const el = e.target; if (el.scrollTop + el.clientHeight > el.scrollHeight - 300 && cur.shown < cur.list.length) renderMore(); });
$('#qlist').addEventListener('click', e => { const q = e.target.closest('.qi'); if (q) selectPos(+q.dataset.p); });
let qTimer; $('#qsearch').addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(() => { buildList(); selectPos(cur.list.length ? 0 : -1); }, 200); });
$('#qshow').addEventListener('change', () => { S.ui.show[cur.tab] = $('#qshow').value; save(); buildList(); selectPos(cur.list.length ? 0 : -1); });
$('#qsort').addEventListener('change', () => { S.ui.sort[cur.tab] = $('#qsort').value; save(); buildList(); selectPos(cur.list.length ? 0 : -1); });
function refreshQi() { $$('#qlist .qi').forEach(el => { const p = +el.dataset.p; const tmp = document.createElement('div'); tmp.innerHTML = qiHtml(p); el.replaceWith(tmp.firstChild); }); }
function selectPos(pos) {
  cur.pos = pos; $$('#qlist .qi.on').forEach(el => el.classList.remove('on'));
  if (pos < 0 || !cur.list[pos]) { cur.sel = null; $('#work').innerHTML = '<div class="empty">Nichts ausgewählt.</div>'; return; }
  while (pos >= cur.shown && cur.shown < cur.list.length) renderMore();
  const el = $('#qlist .qi[data-p="' + pos + '"]'); if (el) { el.classList.add('on'); el.scrollIntoView({ block: 'nearest' }); }
  selectItem(cur.list[pos], true);
}
function selectItem(it, fromQueue) {
  if (!fromQueue) { const p = cur.list.indexOf(it); cur.pos = p; $$('#qlist .qi.on').forEach(el => el.classList.remove('on')); if (p >= 0) { while (p >= cur.shown && cur.shown < cur.list.length) renderMore(); const el = $('#qlist .qi[data-p="' + p + '"]'); if (el) { el.classList.add('on'); el.scrollIntoView({ block: 'nearest' }); } } }
  cur.sel = it; S.ui.sel[cur.tab + ':' + cur.type] = selKey(it); save();
  ui.open = new Set(); ui.all = new Set(); ui.panel = null; ui.mapView = null; ui.word = null; ui.nword = null; cur.focus = 'e';
  renderWork(true);
}
function nextItem(dir) {
  if (!cur.list.length) return;
  if (dir > 0) { for (let p = (cur.pos ?? -1) + 1; p < cur.list.length; p++) { const st = itemState(cur.tab, cur.type, cur.list[p]); if (!(cur.tab === 'names' ? st === 'y' || st === 'r' : DONE(st))) return selectPos(p); } if (cur.pos < cur.list.length - 1) return selectPos(cur.pos + 1); toast('Ende der Liste'); }
  else if (cur.pos > 0) selectPos(cur.pos - 1);
}
function refresh() { renderTabs(); refreshQi(); if (TAB[cur.tab].kind !== 'log') renderProgress(); if (cur.tab === 'log') renderLog(); else renderWork(false); }

// ---------------------------------------------------------------- text, line images, scan
function highlight(text, s, e) { return esc(text.slice(0, s)) + '<mark>' + esc(text.slice(s, e)) + '</mark>' + esc(text.slice(e)); }
function kwic(text, s, e, full) {
  if (!text) return '<span class="muted">(kein Text)</span>';
  if (s < 0) return esc(full ? text : text.slice(0, 380)) + (!full && text.length > 380 ? ' …' : '');
  if (full || text.length <= 460) return highlight(text, s, e);
  let a = Math.max(0, s - 200), b = Math.min(text.length, e + 200);
  if (a > 0) { const sp = text.indexOf(' ', a); if (sp > 0 && sp < s) a = sp + 1; }
  if (b < text.length) { const sp = text.lastIndexOf(' ', b); if (sp > e) b = sp; }
  return (a > 0 ? '… ' : '') + highlight(text.slice(a, b), s - a, e - a) + (b < text.length ? ' …' : '');
}
const thumb = id => 'https://drive.google.com/thumbnail?id=' + id + '&sz=w2000';
function pageLabel(p) { const g = PG[p]; return 'Band ' + g[1] + ', Scan ' + g[2] + (g[3] === 'L' ? ' links' : g[3] === 'R' ? ' rechts' : '') + (g[4] ? ' (S. ' + g[4].replace(/\.$/, '') + ')' : ''); }
// loc = [page, x0, y0, x1, y1, approximate?, word start, word end (fractions of the line)]
function snipHtml(loc, ctx, cls) {
  if (!Array.isArray(loc) || loc.length < 5) return '';
  const [p, x0, y0, x1, y1] = loc; const u = loc.length > 5 ? loc[5] : 1; const g = PG[p]; if (!DRIVE[g[0]] || !g[5]) return '';
  const lh = Math.max(24, (y1 - y0) / Math.max(1, Math.round((y1 - y0) / 60))); const c = (ctx || 0.9) * (u ? 2.4 : 1);   // an estimated line gets more context
  const top = Math.max(0, Math.round(y0 - lh * c)), bot = Math.min(g[6], Math.round(y1 + lh * c));
  const fx = loc.length > 7 ? loc[6] + ',' + loc[7] : '';
  return '<div class="snip' + (cls ? ' ' + cls : '') + (u ? ' approx' : '') + '" data-p="' + p + '" data-b="' + x0 + ',' + top + ',' + x1 + ',' + bot + '" data-hl="' + y0 + ',' + y1 + '" data-fx="' + fx + '" title="' + (u ? 'ungefähre Zeile (aus der Regionsbox geschätzt) — Seite rechts anzeigen' : 'Seite rechts anzeigen') + '"></div>';
}
const snipObs = 'IntersectionObserver' in window ? new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { fillSnip(e.target); snipObs.unobserve(e.target); } }, { rootMargin: '400px' }) : null;
function fillSnip(el) {
  if (el.dataset.done) return; el.dataset.done = 1;
  const g = PG[+el.dataset.p]; const [x0, top, x1, bot] = el.dataset.b.split(',').map(Number); const [h0, h1] = el.dataset.hl.split(',').map(Number);
  const W = el.clientWidth || 700; const s = W / (x1 - x0);
  el.style.height = Math.round((bot - top) * s) + 'px';
  const img = new Image(); img.alt = ''; img.style.width = Math.round(g[5] * s) + 'px'; img.style.left = Math.round(-x0 * s) + 'px'; img.style.top = Math.round(-top * s) + 'px';
  img.onerror = () => { el.classList.add('fail'); el.innerHTML = 'Zeilenbild nicht geladen: im Browser bei Google anmelden (Konto mit Zugriff auf HistOrniGraph_output).'; el.style.height = 'auto'; };
  img.src = thumb(DRIVE[g[0]]);
  const band = document.createElement('i'); band.style.top = Math.round((h0 - top) * s) + 'px'; band.style.height = Math.round((h1 - h0) * s) + 'px';
  el.appendChild(img); el.appendChild(band);
  if (el.dataset.fx) { const [f0, f1] = el.dataset.fx.split(',').map(Number); const seg = document.createElement('i'); seg.className = 'seg'; seg.style.top = band.style.top; seg.style.height = band.style.height; seg.style.left = Math.round(f0 * (x1 - x0) * s) + 'px'; seg.style.width = Math.max(8, Math.round((f1 - f0) * (x1 - x0) * s)) + 'px'; el.appendChild(seg); }
  if (el.classList.contains('approx')) { const lab = document.createElement('span'); lab.className = 'approxlab'; lab.textContent = 'ungefähre Zeile'; el.appendChild(lab); }
}
function wireSnips(root) { $$('.snip:not([data-done])', root).forEach(el => snipObs ? snipObs.observe(el) : fillSnip(el)); }
const scan = { ei: -1, p: -1, hl: null, zoom: 0 };
function showScan(ei, p, hl) {
  if (ei == null || ei < 0) return;
  const pages = E[ei][8]; scan.ei = ei; scan.p = p != null ? p : (pages[0] ?? -1); scan.hl = hl || null;
  if (scan.p < 0) { $('#scanbody').innerHTML = '<div class="msg">Für diesen Eintrag ist keine Seite bekannt.</div>'; return; }
  renderScan();
}
function renderScan() {
  const p = scan.p; const g = PG[p]; const e = E[scan.ei]; const pages = e[8]; const k = pages.indexOf(p);
  $('#scantitle').innerHTML = esc(pageLabel(p)) + ' <span>· ' + esc(e[0]) + (k >= 0 ? (pages.length > 1 ? ' · Seite ' + (k + 1) + '/' + pages.length + ' des Eintrags' : '') : ' · Nachbarseite') + '</span>';
  $('#scanpages').innerHTML = pages.length > 1 ? pages.map((q, j) => '<button class="lbtn' + (q === p ? ' on' : '') + '" data-sp="' + q + '">' + (j + 1) + '</button>').join('') : '';
  $('#scanprev').disabled = !(p > 0 && PG[p - 1][1] === g[1]); $('#scannext').disabled = !(p + 1 < PG.length && PG[p + 1][1] === g[1]);
  const id = DRIVE[g[0]]; $('#scanopen').href = id ? 'https://drive.google.com/file/d/' + id + '/view' : '#';
  const body = $('#scanbody');
  if (!id) { body.innerHTML = '<div class="msg">Für diese Seite ist kein Scan hinterlegt.</div>'; return; }
  body.innerHTML = '<div class="msg">Scan wird geladen …</div>';
  const wrap = document.createElement('div'); wrap.className = 'scanwrap' + (scan.zoom ? ' z' + scan.zoom : '');
  const img = new Image(); img.alt = 'Scan';
  img.onload = () => {
    if (scan.p !== p) return;
    body.innerHTML = ''; wrap.appendChild(img); body.appendChild(wrap);
    const hl = scan.hl && scan.hl[0] === p ? scan.hl : null;
    if (hl && g[5]) { const s = img.clientWidth / g[5]; const b = document.createElement('i'); b.className = 'hlbox' + (hl.length > 5 && hl[5] ? ' approx' : '');
      Object.assign(b.style, { left: (hl[1] * s - 3) + 'px', top: (hl[2] * s - 5) + 'px', width: ((hl[3] - hl[1]) * s + 6) + 'px', height: ((hl[4] - hl[2]) * s + 10) + 'px' }); wrap.appendChild(b);
      if (hl.length > 7) { const seg = document.createElement('i'); seg.className = 'hlseg'; Object.assign(seg.style, { left: ((hl[1] + hl[6] * (hl[3] - hl[1])) * s - 2) + 'px', top: (hl[2] * s - 5) + 'px', width: Math.max(10, (hl[7] - hl[6]) * (hl[3] - hl[1]) * s + 4) + 'px', height: ((hl[4] - hl[2]) * s + 10) + 'px' }); wrap.appendChild(seg); }
      body.scrollTop = Math.max(0, hl[2] * s - body.clientHeight / 3); body.scrollLeft = Math.max(0, hl[1] * s - 20); }
  };
  img.onerror = () => { body.innerHTML = '<div class="msg">Das Bild konnte nicht geladen werden. Bitte im Browser bei Google angemeldet sein (Konto mit Zugriff auf HistOrniGraph_output) oder „Drive ↗“.</div>'; };
  img.src = thumb(id);
}
$('#scanprev').onclick = () => { if (scan.p > 0) { scan.p--; renderScan(); } };
$('#scannext').onclick = () => { if (scan.p + 1 < PG.length) { scan.p++; renderScan(); } };
$('#scanzoom').onclick = () => { if (scan.p < 0) return; scan.zoom = (scan.zoom + 1) % 3; renderScan(); };
$('#scanhide').onclick = () => { S.ui.noscan = true; $('#main').classList.add('noscan'); save(); };
$('#scanpages').addEventListener('click', e => { const b = e.target.closest('[data-sp]'); if (b) { scan.p = +b.dataset.sp; renderScan(); } });
function initGrip() {
  if (S.ui.scanw) document.documentElement.style.setProperty('--scanw', S.ui.scanw + 'px');
  let drag = false; $('#grip').addEventListener('mousedown', e => { drag = true; e.preventDefault(); document.body.style.cursor = 'col-resize'; });
  window.addEventListener('mousemove', e => { if (!drag) return; const w = Math.max(320, Math.min(window.innerWidth - 700, window.innerWidth - e.clientX)); document.documentElement.style.setProperty('--scanw', w + 'px'); S.ui.scanw = w; });
  window.addEventListener('mouseup', () => { if (drag) { drag = false; document.body.style.cursor = ''; save(); } });
}
function scanFor(t, mi) { const m = P[t].men[mi]; const loc = m[4]; showScan(m[1], Array.isArray(loc) ? loc[0] : null, Array.isArray(loc) && loc.length === 5 ? loc : null); }

// ---------------------------------------------------------------- mention cards
function pickSpread(ids, k) {
  const s = ids.slice().sort((a, b) => (E[a[1]][2] || '9999').localeCompare(E[b[1]][2] || '9999') || a[0] - b[0]);
  if (s.length <= k) return s;
  return Array.from({ length: k }, (_, j) => s[Math.round(j * (s.length - 1) / (k - 1))]);
}
function entryHead(ei) {
  const e = E[ei]; const pages = e[8];
  return '<b>' + esc(e[3] || e[2] || 'ohne Datum') + '</b>' + (e[6] ? '<span>' + esc(e[6]) + '</span>' : '') + '<span class="muted">' + esc(e[0]) + ' · ' + esc(pages.length ? pageLabel(pages[0]) : 'Band ' + e[5]) + (pages.length > 1 ? ' +' + (pages.length - 1) + ' S.' : '') + (e[4] && e[4] !== 'field-day' ? ' · ' + esc(KIND_DE[e[4]] || e[4]) : '') + '</span>';
}
function reasonLabel(t, r) { return ((TT[t] || TT.taxon).not.find(x => x[0] === r) || [r, r])[1]; }
function decLine(t, d) {
  if (!d || !d.d) return '';
  const tg = d.target ? ' → <b>' + esc(d.target.label || d.target.code || '') + '</b>' + (d.target.sci ? ' <i>' + esc(d.target.sci) + '</i>' : '') : '';
  const txt = { y: '✓ stimmt', r: '↪ anders zugeordnet', n: '✗ kein(e) ' + TT[t].one + (d.reason ? ' (' + esc(reasonLabel(t, d.reason)) + ')' : ''), u: '? unsicher', o: '↪ eigene ' + TT[t].one, x: '↪ nicht bestimmbar' }[d.d] || d.d;
  return txt + tg + (d.note ? ' · ' + esc(d.note) : '');
}
function menHtml(t, mi, opts) {
  opts = opts || {};
  const m = P[t].men[mi]; const ei = m[1]; const e = E[ei]; const key = X[t].mkey[mi]; const d = S.men[t][key]; const rd = menReading(t, mi);
  const b = (k, sym, title) => '<button class="mb ' + k + (d && d.d === k ? ' on' : '') + '" data-ma="' + k + '" title="' + title + '">' + sym + '</button>';
  const acts = opts.noActs ? '<span class="mini"><button class="mb" data-ma="e" title="Lesung korrigieren (E)">✎</button></span>' : '<span class="mini">' + b('y', '✓', 'Beleg stimmt') + (t === 'habitat' ? '' : b('r', '↪', 'Beleg gehört zu einem anderen Eintrag')) + b('n', '✗', 'Kein(e) ' + TT[t].one) + '<button class="mb" data-ma="e" title="Lesung korrigieren: was steht im Scan?">✎</button></span>';
  const role = m[5] ? '<span class="bd plain">' + esc(m[5]) + '</span>' : '';
  const note = (d && d.d ? '<div class="note ' + (d.d === 'o' || d.d === 'x' ? 'r' : d.d) + '">Beleg: ' + decLine(t, d) + ' <button class="lbtn" data-mclear="1">zurücksetzen</button></div>' : '')
    + (rd ? '<div class="note t">✎ Lesung korrigiert: „' + esc(rd.old) + '“ → „<b>' + esc(rd.new) + '</b>“' + (rd.note ? ' <span class="muted">(' + esc(rd.note) + ')</span>' : '') + '</div>' : '');
  const full = ui.full.has(t + mi);
  return '<div class="men" data-t="' + t + '" data-mi="' + mi + '" data-ei="' + ei + '"><div class="mh">' + entryHead(ei) + role + '<span class="sp"></span>' + acts + '</div>'
    + snipHtml(m[4]) + '<div class="kw">' + kwic(e[7], m[2], m[3], full) + (e[7] && e[7].length > 460 ? '<button class="more" data-full="' + mi + '">' + (full ? 'weniger' : 'ganzer Eintrag') + '</button>' : '') + '</div>'
    + note + (ui.panel && ui.panel.scope === 'm:' + mi ? panelHtml(t, ui.panel) : '') + '</div>';
}
