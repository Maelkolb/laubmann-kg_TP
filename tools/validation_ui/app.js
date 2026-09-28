(async function () {
'use strict';
// HistOrniGraph Validierung v2 — "Abgleich": name form -> entity, with mention-level overrides.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = n => Number(n || 0).toLocaleString('de-DE');
const pct = x => (100 * x).toLocaleString('de-DE', { maximumFractionDigits: 1 }) + ' %';
const LS = 'hog-validation-v2';
const lc = s => String(s || '').toLowerCase();
const fold = s => lc(s).normalize('NFC').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');

// ---------- payload ----------
async function loadPayload() {
  const b64 = $('#data').textContent.trim();
  let bytes;
  try { bytes = await (await fetch('data:application/octet-stream;base64,' + b64)).arrayBuffer(); }
  catch (e) { const bin = atob(b64); bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); }
  const ds = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(ds).text());
}
let P;
try { P = await loadPayload(); }
catch (e) { $('#loading').textContent = 'Die Daten konnten nicht geladen werden. Bitte eine aktuelle Version von Chrome, Edge oder Firefox verwenden. (' + e.message + ')'; return; }
let DRIVE = {};
try { DRIVE = JSON.parse($('#drive').textContent || '{}'); } catch (e) { DRIVE = {}; }
const E = P.E;    // [id, uid, date, vdate, kind, vol, place, text, [page idx], location_raw]
const PG = P.PG;  // [page_id, vol, scan, side, printed number, w, h]
$('#exportname').textContent = P.export;

// ---------- state ----------
let S = { who: '', id: {}, men: {}, ent: {}, text: [], qa: {}, ev: {}, ui: { adv: true } };
try { const raw = localStorage.getItem(LS); if (raw) S = Object.assign(S, JSON.parse(raw)); } catch (e) { }
for (const k of ['id', 'men', 'ent']) for (const t of ['taxon', 'person', 'place', 'habitat']) { S[k] = S[k] || {}; S[k][t] = S[k][t] || {}; }
S.text = S.text || []; S.qa = S.qa || {}; S.ev = S.ev || {}; S.ui = S.ui || { adv: true };
let saveTimer = null;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(LS, JSON.stringify(S)); $('#saved').textContent = 'Lokal gespeichert ' + new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); }
    catch (e) { $('#saved').textContent = 'Speichern im Browser nicht möglich, bitte regelmäßig exportieren'; }
  }, 250);
}
const stampObj = o => Object.assign({}, o, { by: S.who || '', t: new Date().toISOString() });
$('#who').value = S.who || '';
$('#who').addEventListener('input', e => { S.who = e.target.value.trim(); save(); });
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), 2400); }

// ---------- vocabulary ----------
const TYPE = {
  taxon: { title: 'Arten', one: 'Art', desc: 'Welche Art ist mit diesem Namen gemeint?', auth: 'GBIF',
    cls: { C: ['unbelegt', 'Weder ein deutscher Name dieser Art (GBIF, Wikidata) noch eine Schreibvariante davon. Häufig Lesefehler (Kameradeneingang) oder seltene Volksnamen.'],
      L: ['nicht verknüpft', 'Keiner GBIF-Art zugeordnet. Art suchen und zuordnen, wenn sie bestimmbar ist.'],
      B: ['Variante', 'Schreib- oder Wortvariante eines belegten Namens (Lachmöve, Hausamsel, Rauhschwalbe).'],
      A: ['belegter Name', 'Deutscher Name dieser Art laut GBIF oder Wikidata (auch historische Namen wie Dompfaff).'] },
    on: ['C', 'L', 'B'], order: ['C', 'L', 'B', 'A'] },
  person: { title: 'Personen', one: 'Person', desc: 'Wer ist gemeint, und ist es dieselbe Person?', auth: 'Wikidata/GND',
    cls: { V: ['Variante', 'Automatisch einer anderen Namensform zugeordnet (Kurzform, Initiale, Nachname).'],
      K: ['unverknüpft', 'Voller Name, noch ohne Wikidata/GND.'], W: ['verknüpft', 'Mit Wikidata oder GND verknüpft.'],
      E: ['nur ein Namensteil', 'Einzelner Name (meist nur Nachname), keiner Person zugeordnet.'] },
    on: ['V', 'K', 'W'], order: ['V', 'W', 'K', 'E'] },
  place: { title: 'Orte', one: 'Ort', desc: 'Welcher Ort ist gemeint, und wo liegt er?', auth: 'GeoNames/Wikidata',
    cls: { V: ['Variante', 'Einem ähnlich geschriebenen Ort zugeordnet (häufigste Fehlerquelle: zwei verschiedene Orte).'],
      R: ['Georeferenz prüfen', 'Koordinate unsicher, bitte prüfen.'], N: ['ohne Koordinaten', 'Kein Gazetteer-Treffer. Kleinere Örtlichkeiten: ungefähre Lage setzen.'],
      G: ['georeferenziert', 'Automatisch georeferenziert.'] },
    on: ['V', 'R', 'N'], order: ['V', 'R', 'G', 'N'] },
  habitat: { title: 'Lebensräume', one: 'Lebensraum', desc: 'Passt die EUNIS-Klasse zur Bezeichnung?', auth: 'EUNIS',
    cls: { R: ['prüfen', 'Unsichere EUNIS-Zuordnung.'], N: ['keine Klasse', 'Keine EUNIS-Klasse gefunden.'], E: ['EUNIS-Klasse', 'Automatisch einer EUNIS-Klasse zugeordnet.'], V: ['Variante', 'Schreibvariante einer anderen Bezeichnung.'] },
    on: ['R', 'N', 'E'], order: ['R', 'N', 'E', 'V'] },
};
const TYPES = ['taxon', 'person', 'place', 'habitat'];
const NOT_REASONS = {
  taxon: [['misread', 'Lesefehler / kein Name'], ['non-bird', 'anderes Tier oder Pflanze'], ['place', 'eigentlich ein Ortsname'], ['person', 'eigentlich ein Personenname'], ['other', 'sonstiges']],
  person: [['misread', 'Lesefehler / kein Name'], ['place', 'eigentlich ein Ortsname'], ['taxon', 'eigentlich ein Vogelname'], ['other', 'sonstiges (Institution, Zeitschrift …)']],
  place: [['misread', 'Lesefehler / kein Name'], ['taxon', 'eigentlich ein Vogelname'], ['person', 'eigentlich ein Personenname'], ['habitat', 'eigentlich ein Lebensraum, kein Ort'], ['other', 'sonstiges']],
  habitat: [['misread', 'Lesefehler / kein Lebensraum'], ['place', 'eigentlich ein Ortsname'], ['other', 'sonstiges']],
};
const DEC_DE = { y: 'stimmt', r: 'neu zugeordnet', x: 'abgelehnt', n: 'kein Eintrag dieser Art', e: 'Belege einzeln', o: 'eigene Entität', u: 'unsicher' };
const DOT = { y: 'y', r: 'r', x: 'n', n: 'n', e: 'e', o: 'r', u: 'u' };
const KIND_DE = { 'field-day': 'Feldtag', 'species-digest': 'Artenübersicht', 'third-party-report': 'Fremdbericht', other: 'sonstiges' };
const QA_DE = {
  non_bird: ['Kein Vogel', 'Die Beobachtung wurde entfernt, weil das Modell das Tier nicht als Vogel eingestuft hat.'],
  no_observations: ['Keine Vogelbeobachtung', 'Eintrag ohne Vogelnachweis, aber mit Wetter oder Reise.'],
  empty: ['Leerer Eintrag', 'Keine Beobachtung extrahiert. Möglicherweise ein Segmentierungsfehler.'],
  date_corrected: ['Datum korrigiert', 'Das Eintragsdatum wurde geändert.'],
  date_year_corrected: ['Jahr korrigiert', 'Das Jahr wurde aus der Bandabdeckung oder den Nachbareinträgen korrigiert (OCR-Fehler).'],
  date_out_of_coverage: ['Datum außerhalb des Bandes', 'Das Datum liegt außerhalb des Zeitraums, den der Band abdeckt.'],
  low_confidence_taxon: ['Unsichere Art', 'Die Beobachtung wurde entfernt: Artname nicht auflösbar, Konfidenz niedrig.'],
  nonplace: ['Kein Ort', 'Die Kopfzeile enthält laut Modell keinen verwertbaren Ort.'],
  volume_reassigned: ['Band neu zugeordnet', 'Die Seite wurde einem anderen Band zugeordnet.'],
  date_from_position: ['Datum aus Position', 'Das Datum wurde aus der Position im Band erschlossen.'],
  record_type_conflict: ['Beobachtungstyp widersprüchlich', 'Eigene Beobachtung, obwohl Beobachter oder Zitat genannt ist.'],
  duplicate_entry: ['Doppelter Eintrag', 'Eintrag wurde als Dublette entfernt.'],
  date_out_of_span: ['Datum außerhalb der Tagebuchzeit', 'Eintrag entfernt, das Jahr liegt außerhalb von 1917–1965.'],
  implausible_date: ['Ungültiges Datum', 'Eintrag entfernt, das Datum ist ungültig.'],
};

// ---------- model ----------
// items: one per written name (a name assigned to several entities is still one decision)
const M = {};
for (const t of TYPES) {
  const sec = P[t]; const byName = new Map(); const menByForm = sec.forms.map(() => []); const formsByEnt = sec.ent.map(() => []);
  sec.men.forEach((m, i) => menByForm[m[0]].push(i));
  sec.forms.forEach((f, i) => {
    formsByEnt[f[2]].push(i);
    const key = lc(f[0]); let it = byName.get(key);
    if (!it) { it = { key, name: f[0], forms: [], n: 0 }; byName.set(key, it); }
    it.forms.push(i); it.n += f[1];
  });
  for (const it of byName.values()) {
    it.forms.sort((a, b) => sec.forms[b][1] - sec.forms[a][1]);
    it.f = sec.forms[it.forms[0]]; it.name = it.f[0]; it.ent = it.f[2]; it.cls = it.f[3];
    it.men = it.forms.flatMap(f => menByForm[f]);
  }
  // occurrence index of a mention among mentions of the same name in the same entry (stable mention key)
  const occ = new Map(); const mkey = new Array(sec.men.length);
  sec.men.forEach((m, i) => { const name = lc(sec.forms[m[0]][0]); const k = E[m[1]][1] + '|' + name; const n = occ.get(k) || 0; occ.set(k, n + 1); mkey[i] = k + '|' + n; });
  const items = [...byName.values()];
  items.sort((a, b) => b.n - a.n || a.name.localeCompare(b.name, 'de'));
  M[t] = { sec, items, byName, menByForm, formsByEnt, mkey, idx: new Map(items.map((it, i) => [it.key, i])), mByKey: new Map(mkey.map((k, i) => [k, i])), entByLabel: new Map(sec.ent.map((e, i) => [e[0], i])) };
  const tot = sec.men.length; M[t].total = tot;
}
const entLabel = (t, e) => P[t].ent[e][0];
const itemIsCanonical = (t, it) => lc(it.name) === lc(entLabel(t, it.ent));
// status of an item: the form decision, or for canonical persons/places the entity link decision
function itemDec(t, it) {
  const d = S.id[t][it.key];
  if (d && d.d) return d.d;
  if ((t === 'person' || t === 'place') && itemIsCanonical(t, it)) { const a = S.ent[t][entLabel(t, it.ent)]; if (a && a.d) return a.d === 'n' ? 'x' : a.d; }
  return '';
}

// ---------- tasks / sidebar ----------
const TASKS = [
  ...TYPES.map(t => ({ id: t, group: 'Abgleich', title: TYPE[t].title, type: 'form', kind: t })),
  { id: 'eval', group: 'Prüfen', title: 'Stichprobe Arten', type: 'eval', kind: 'taxon' },
  { id: 'qa', group: 'Prüfen', title: 'Qualitätsflags', type: 'qa' },
];
const TBY = Object.fromEntries(TASKS.map(t => [t.id, t]));
S.ui.chips = S.ui.chips || {};
for (const t of TYPES) if (!S.ui.chips[t]) S.ui.chips[t] = TYPE[t].on.slice();

function progress(task) {
  let y = 0, n = 0, u = 0, tot = 0, cov = 0;
  if (task.type === 'form') {
    const m = M[task.kind]; tot = m.items.length;
    for (const it of m.items) { const d = itemDec(task.kind, it); if (!d) continue; if (d === 'u') u++; else { if (d === 'x' || d === 'n') n++; else y++; cov += it.n; } }
    return { y, n, u, done: y + n, tot, cov: cov / Math.max(1, m.total) };
  }
  if (task.type === 'eval') { tot = P.sample.length; for (const i of P.sample) { const d = S.ev[M.taxon.mkey[i]]; if (!d) continue; if (d.d === 'y') y++; else if (d.d === 'n') n++; else if (d.d === 'u') u++; } return { y, n, u, done: y + n, tot }; }
  tot = P.qa.rows.length; for (const k in S.qa) { const d = S.qa[k].d; if (d === 'y') y++; else if (d === 'n') n++; else if (d === 'u') u++; } return { y, n, u, done: y + n, tot };
}
let cur = { task: null, i: -1, list: [], shown: 0 };
function renderSide() {
  let h = '<button class="task' + (cur.task ? '' : ' on') + '" data-t=""><div class="t"><span>Übersicht</span><span></span></div></button>';
  let g = '';
  for (const t of TASKS) {
    if (t.group !== g) { g = t.group; h += '<h4>' + esc(g) + '</h4>'; }
    const p = progress(t); const w = x => (100 * x / Math.max(1, p.tot)).toFixed(2) + '%';
    h += '<button class="task' + (cur.task === t ? ' on' : '') + '" data-t="' + t.id + '"><div class="t"><span>' + esc(t.title) + '</span><span>' + fmt(p.done + p.u) + ' / ' + fmt(p.tot) + '</span></div>'
      + '<div class="bar"><i class="y" style="width:' + w(p.y) + '"></i><i class="n" style="width:' + w(p.n) + '"></i><i class="u" style="width:' + w(p.u) + '"></i></div>'
      + (p.cov != null ? '<div class="cov">' + pct(p.cov) + ' der Belege entschieden</div>' : '') + '</button>';
  }
  const nc = S.text.length + TYPES.reduce((a, t) => a + Object.keys(S.men[t]).length, 0);
  h += '<h4>Ergebnisse</h4><button class="task' + (cur.task && cur.task.id === 'corr' ? ' on' : '') + '" data-t="corr"><div class="t"><span>Korrekturen</span><span>' + fmt(nc) + '</span></div></button>';
  h += '<div class="foot">Export ' + esc(P.export) + '<br>Oberfläche ' + esc(P.built) + '</div>';
  $('#side').innerHTML = h;
}
$('#side').addEventListener('click', e => { const b = e.target.closest('.task'); if (!b) return; if (b.dataset.t === 'corr') return openCorrections(); openTask(b.dataset.t ? TBY[b.dataset.t] : null); });

// ---------- queue ----------
function taskItems(task) {
  if (task.type === 'form') return M[task.kind].items;
  if (task.type === 'eval') return P.sample.map((mi, k) => ({ key: M.taxon.mkey[mi], mi, k }));
  return P.qa.rows.map((r, i) => ({ key: r[0] + '|' + r[2] + '|' + r[4], r, ei: P.qa.ei[i] }));
}
function itemState(task, it) {
  if (task.type === 'form') return itemDec(task.kind, it);
  if (task.type === 'eval') return (S.ev[it.key] || {}).d || '';
  return (S.qa[it.key] || {}).d || '';
}
function openTask(t, keepKey) {
  cur.task = t; S.ui.task = t ? t.id : ''; save(); renderSide(); closeScan();
  if (!t) { $('#qtitle').textContent = 'Übersicht'; $('#qdesc').textContent = 'Aufgabe links auswählen.'; $('#qchips').innerHTML = ''; $('#qlist').innerHTML = ''; $('#qcount').textContent = ''; $('#qsortwrap').style.display = 'none'; renderOverview(); return; }
  $('#qtitle').textContent = t.group + ': ' + t.title;
  $('#qdesc').textContent = t.type === 'form' ? TYPE[t.kind].desc : t.type === 'eval' ? 'Zufällige Belege: Ist die Art richtig bestimmt? Ergibt die Genauigkeit der Artbestimmung.' : 'Hat die automatische Qualitätsprüfung richtig entschieden?';
  $('#qsearch').value = (S.ui.q || {})[t.id] || '';
  $('#qshow').value = (S.ui.show || {})[t.id] || 'open';
  $('#qsortwrap').style.display = t.type === 'form' ? '' : 'none';
  $('#qsort').value = (S.ui.sort || {})[t.id] || 'n';
  t.items = taskItems(t);
  renderChips(); buildList();
  const want = keepKey ?? (S.ui.item || {})[t.id];
  let pos = want != null ? cur.list.findIndex(i => t.items[i].key === want) : -1;
  if (pos < 0) pos = 0;
  select(cur.list.length ? pos : -1);
}
function renderChips() {
  const t = cur.task;
  if (t.type === 'qa') {
    const cats = {}; for (const it of t.items) cats[it.r[2]] = (cats[it.r[2]] || 0) + 1;
    S.ui.qachips = S.ui.qachips || Object.keys(QA_DE).filter(c => !['no_observations', 'empty'].includes(c));
    const on = new Set(S.ui.qachips);
    $('#qchips').innerHTML = Object.keys(cats).sort((a, b) => cats[b] - cats[a]).map(c => '<span class="chip' + (on.has(c) ? ' on' : '') + '" data-c="' + esc(c) + '" title="' + esc((QA_DE[c] || [])[1] || '') + '">' + esc((QA_DE[c] || [c])[0]) + '<b>' + fmt(cats[c]) + '</b></span>').join('');
    return;
  }
  if (t.type !== 'form') { $('#qchips').innerHTML = ''; return; }
  const on = new Set(S.ui.chips[t.kind]); const cats = {}; for (const it of t.items) cats[it.cls] = (cats[it.cls] || 0) + 1;
  $('#qchips').innerHTML = TYPE[t.kind].order.filter(c => cats[c]).map(c => '<span class="chip' + (on.has(c) ? ' on' : '') + '" data-c="' + c + '" title="' + esc(TYPE[t.kind].cls[c][1]) + '">' + esc(TYPE[t.kind].cls[c][0]) + '<b>' + fmt(cats[c]) + '</b></span>').join('');
}
$('#qchips').addEventListener('click', e => {
  const c = e.target.closest('.chip'); if (!c) return; const t = cur.task;
  const arr = t.type === 'qa' ? S.ui.qachips : S.ui.chips[t.kind]; const s = new Set(arr);
  s.has(c.dataset.c) ? s.delete(c.dataset.c) : s.add(c.dataset.c);
  if (t.type === 'qa') S.ui.qachips = [...s]; else S.ui.chips[t.kind] = [...s];
  save(); renderChips(); buildList(); select(cur.list.length ? 0 : -1);
});
function itemText(t, it) {
  if (t.type === 'form') return it.name + ' ' + entLabel(t.kind, it.ent) + ' ' + (t.kind === 'taxon' ? P.taxon.ent[it.ent][1] : '');
  if (t.type === 'eval') { const m = P.taxon.men[it.mi]; return P.taxon.forms[m[0]][0] + ' ' + P.taxon.ent[P.taxon.forms[m[0]][2]][0]; }
  return it.r.join(' ');
}
function buildList() {
  const t = cur.task; const q = fold($('#qsearch').value.trim()); const show = $('#qshow').value;
  const on = t.type === 'form' ? new Set(S.ui.chips[t.kind]) : t.type === 'qa' ? new Set(S.ui.qachips) : null;
  cur.list = [];
  t.items.forEach((it, i) => {
    if (on && t.type === 'form' && !on.has(it.cls)) return;
    if (on && t.type === 'qa' && !on.has(it.r[2])) return;
    if (q && !fold(itemText(t, it)).includes(q)) return;
    const d = itemState(t, it);
    if (show === 'open' && d) return; if (show === 'done' && !(d && d !== 'u')) return; if (show === 'u' && d !== 'u') return;
    cur.list.push(i);
  });
  const sort = t.type === 'form' ? $('#qsort').value : 'n';
  if (t.type === 'form') {
    const ord = TYPE[t.kind].order;
    if (sort === 'alpha') cur.list.sort((a, b) => t.items[a].name.localeCompare(t.items[b].name, 'de'));
    else if (sort === 'ent') cur.list.sort((a, b) => { const A = t.items[a], B = t.items[b]; return entLabel(t.kind, A.ent).localeCompare(entLabel(t.kind, B.ent), 'de') || B.n - A.n; });
    else if (sort === 'cls') cur.list.sort((a, b) => ord.indexOf(t.items[a].cls) - ord.indexOf(t.items[b].cls) || t.items[b].n - t.items[a].n);
  }
  cur.shown = 0; $('#qlist').innerHTML = ''; $('#qlist').scrollTop = 0; renderMore();
  $('#qcount').textContent = fmt(cur.list.length) + ' Einträge';
}
function qiHtml(pos) {
  const t = cur.task; const it = t.items[cur.list[pos]]; const d = itemState(t, it);
  let l1, l2, num = '';
  if (t.type === 'form') {
    const el = entLabel(t.kind, it.ent);
    l1 = esc(it.name); num = fmt(it.n) + '×';
    l2 = (it.name !== el ? '→ ' + esc(el) : '') + (t.kind === 'taxon' && P.taxon.ent[it.ent][1] ? ' <i>' + esc(P.taxon.ent[it.ent][1]) + '</i>' : '')
      + ' <span class="cls cls' + it.cls + '">' + esc(TYPE[t.kind].cls[it.cls][0]) + '</span>';
    const dd = S.id[t.kind][it.key]; if (dd && dd.d === 'r' && dd.target) l2 += ' ⇒ ' + esc(dd.target.label || dd.target.code || '');
  } else if (t.type === 'eval') {
    const m = P.taxon.men[it.mi]; const f = P.taxon.forms[m[0]];
    l1 = (it.k + 1) + '. ' + esc(f[0]); l2 = esc(E[m[1]][0]) + ' · ' + esc(P.taxon.ent[f[2]][0]);
  } else {
    l1 = esc((QA_DE[it.r[2]] || [it.r[2]])[0]) + (it.r[4] ? ': ' + esc(it.r[4]) : ''); l2 = esc(it.r[0]) + ' · ' + (it.r[3] === 'excluded' ? 'entfernt' : 'markiert');
  }
  return '<div class="qi' + (pos === cur.i ? ' on' : '') + '" data-p="' + pos + '"><span class="dot ' + (DOT[d] || d || '') + '"></span><div><div class="l1">' + l1 + '</div><div class="l2">' + l2 + '</div></div><div class="num">' + num + '</div></div>';
}
function renderMore() {
  const end = Math.min(cur.list.length, cur.shown + 150); let h = '';
  for (let p = cur.shown; p < end; p++) h += qiHtml(p);
  $('#qlist').insertAdjacentHTML('beforeend', h); cur.shown = end;
  const m = $('#qlist .qmore'); if (m) m.remove();
  if (cur.shown < cur.list.length) $('#qlist').insertAdjacentHTML('beforeend', '<div class="qmore">weitere werden beim Scrollen geladen …</div>');
  if (!cur.list.length) $('#qlist').innerHTML = '<div class="qmore">Keine Einträge in dieser Auswahl.' + ($('#qshow').value === 'open' ? ' Alles erledigt 🎉' : '') + '</div>';
}
$('#qlist').addEventListener('scroll', e => { const el = e.target; if (el.scrollTop + el.clientHeight > el.scrollHeight - 300 && cur.shown < cur.list.length) renderMore(); });
$('#qlist').addEventListener('click', e => { const q = e.target.closest('.qi'); if (q) select(+q.dataset.p); });
let qTimer; $('#qsearch').addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(() => { S.ui.q = S.ui.q || {}; S.ui.q[cur.task.id] = $('#qsearch').value; save(); buildList(); select(cur.list.length ? 0 : -1); }, 200); });
$('#qshow').addEventListener('change', () => { S.ui.show = S.ui.show || {}; S.ui.show[cur.task.id] = $('#qshow').value; save(); buildList(); select(cur.list.length ? 0 : -1); });
$('#qsort').addEventListener('change', () => { S.ui.sort = S.ui.sort || {}; S.ui.sort[cur.task.id] = $('#qsort').value; save(); buildList(); select(cur.list.length ? 0 : -1); });
function refreshQi(pos) { const el = $('#qlist .qi[data-p="' + pos + '"]'); if (!el) return; const tmp = document.createElement('div'); tmp.innerHTML = qiHtml(pos); el.replaceWith(tmp.firstChild); }
function curItem() { return cur.task && cur.i >= 0 ? cur.task.items[cur.list[cur.i]] : null; }
function select(pos) {
  cur.i = pos; document.querySelectorAll('#qlist .qi.on').forEach(el => el.classList.remove('on'));
  if (pos < 0) { $('#detail').innerHTML = '<div class="empty">Keine Einträge in dieser Auswahl.</div>'; return; }
  while (pos >= cur.shown && cur.shown < cur.list.length) renderMore();
  const el = $('#qlist .qi[data-p="' + pos + '"]'); if (el) { el.classList.add('on'); el.scrollIntoView({ block: 'nearest' }); }
  const it = curItem(); S.ui.item = S.ui.item || {}; S.ui.item[cur.task.id] = it.key; save();
  ui.showAll = false; ui.menPage = 1; ui.panel = null;
  renderDetail(); $('#detail').scrollTop = 0;
}
function step(dir) { if (!cur.task || !cur.list.length) return; const p = Math.max(0, Math.min(cur.list.length - 1, cur.i + dir)); if (p !== cur.i) select(p); }
function nextOpen() {
  const t = cur.task;
  for (let p = cur.i + 1; p < cur.list.length; p++) if (!itemState(t, t.items[cur.list[p]])) return select(p);
  if (cur.i < cur.list.length - 1) return select(cur.i + 1);
  toast('Ende der Liste erreicht');
}
const ui = { showAll: false, menPage: 1, panel: null };

// ---------- text, snippets, scans ----------
function highlight(text, ranges) {
  let out = '', pos = 0;
  for (const [s, e, c] of ranges.slice().sort((a, b) => a[0] - b[0])) { if (s < pos || s < 0) continue; out += esc(text.slice(pos, s)) + '<mark' + (c ? ' class="' + c + '"' : '') + '>' + esc(text.slice(s, e)) + '</mark>'; pos = e; }
  return out + esc(text.slice(pos));
}
function kwic(text, s, e, full) {
  if (!text) return '<span class="muted">(kein Text)</span>';
  if (s < 0) return esc(text.slice(0, full ? undefined : 420)) + (!full && text.length > 420 ? ' …' : '') + '<div class="small muted">Name im Text nicht wiedergefunden.</div>';
  if (full || text.length <= 520) return highlight(text, [[s, e, '']]);
  let a = Math.max(0, s - 230), b = Math.min(text.length, e + 230);
  if (a > 0) { const sp = text.indexOf(' ', a); if (sp > 0 && sp < s) a = sp + 1; }
  if (b < text.length) { const sp = text.lastIndexOf(' ', b); if (sp > e) b = sp; }
  return (a > 0 ? '… ' : '') + highlight(text.slice(a, b), [[s - a, e - a, '']]) + (b < text.length ? ' …' : '');
}
const thumb = id => 'https://drive.google.com/thumbnail?id=' + id + '&sz=w2000';
function pageLabel(p) { const g = PG[p]; return 'Band ' + g[1] + ', Scan ' + g[2] + (g[3] === 'L' ? ' links' : g[3] === 'R' ? ' rechts' : '') + (g[4] ? ' (S. ' + g[4].replace(/\.$/, '') + ')' : ''); }
function snipHtml(loc) {
  if (!Array.isArray(loc) || loc.length < 5) return '';
  const [p, x0, y0, x1, y1] = loc; const g = PG[p]; if (!DRIVE[g[0]] || !g[5]) return '';
  const lh = Math.max(24, (y1 - y0) / Math.max(1, Math.round((y1 - y0) / 60)));
  const top = Math.max(0, Math.round(y0 - lh * 0.9)), bot = Math.min(g[6], Math.round(y1 + lh * 0.9));
  return '<div class="snip" data-p="' + p + '" data-b="' + x0 + ',' + top + ',' + x1 + ',' + bot + '" data-hl="' + y0 + ',' + y1 + '" title="Scan öffnen"></div>';
}
const snipObs = 'IntersectionObserver' in window ? new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { fillSnip(e.target); snipObs.unobserve(e.target); } }, { rootMargin: '300px' }) : null;
function fillSnip(el) {
  if (el.dataset.done) return; el.dataset.done = 1;
  const p = +el.dataset.p; const g = PG[p]; const [x0, top, x1, bot] = el.dataset.b.split(',').map(Number); const [h0, h1] = el.dataset.hl.split(',').map(Number);
  const W = el.clientWidth || 700; const s = W / (x1 - x0);
  el.style.height = Math.round((bot - top) * s) + 'px';
  const img = new Image(); img.alt = ''; img.style.width = Math.round(g[5] * s) + 'px'; img.style.left = Math.round(-x0 * s) + 'px'; img.style.top = Math.round(-top * s) + 'px';
  img.onerror = () => { el.classList.add('fail'); el.innerHTML = '<span>Zeilenbild nicht geladen: im Browser bei Google anmelden (Konto mit Zugriff auf HistOrniGraph_output).</span>'; el.style.height = 'auto'; };
  img.src = thumb(DRIVE[g[0]]);
  const band = document.createElement('i'); band.style.top = Math.round((h0 - top) * s) + 'px'; band.style.height = Math.round((h1 - h0) * s) + 'px';
  el.appendChild(img); el.appendChild(band);
}
function wireSnips(root) { root.querySelectorAll('.snip:not([data-done])').forEach(el => snipObs ? snipObs.observe(el) : fillSnip(el)); }

// scan pane: every page of the entry, plus the neighbouring pages of the volume
const scan = { ei: -1, p: -1, hl: null, zoom: false };
function openScan(ei, p, hl) {
  scan.ei = ei; scan.p = p != null ? p : (E[ei][8][0] ?? -1); scan.hl = hl || null;
  if (scan.p < 0) return toast('Für diesen Eintrag ist keine Seite bekannt');
  $('#scanpane').classList.add('show'); renderScan();
}
function closeScan() { $('#scanpane').classList.remove('show'); }
function renderScan() {
  const p = scan.p; const g = PG[p]; const e = E[scan.ei]; const pages = e[8]; const k = pages.indexOf(p);
  $('#scantitle').innerHTML = esc(pageLabel(p)) + ' <span class="muted">· ' + esc(e[0]) + (k >= 0 ? ' · Seite ' + (k + 1) + ' von ' + pages.length + ' des Eintrags' : ' · Nachbarseite') + '</span>';
  $('#scanpages').innerHTML = pages.map((q, j) => '<button class="lbtn' + (q === p ? ' on' : '') + '" data-sp="' + q + '">' + (j + 1) + '</button>').join('');
  const prev = p > 0 && PG[p - 1][1] === g[1], next = p + 1 < PG.length && PG[p + 1][1] === g[1];
  $('#scanprev').disabled = !prev; $('#scannext').disabled = !next;
  const id = DRIVE[g[0]];
  $('#scanopen').href = id ? 'https://drive.google.com/file/d/' + id + '/view' : '#';
  if (!id) { $('#scanbody').innerHTML = '<div class="msg">Für diese Seite ist kein Scan hinterlegt.</div>'; return; }
  $('#scanbody').innerHTML = '<div class="msg">Scan wird geladen …</div>';
  const wrap = document.createElement('div'); wrap.className = 'scanwrap' + (scan.zoom ? ' z' : '');
  const img = new Image(); img.alt = 'Scan';
  img.onload = () => {
    $('#scanbody').innerHTML = ''; wrap.appendChild(img); $('#scanbody').appendChild(wrap);
    const hl = scan.hl && scan.hl[0] === p ? scan.hl : null;
    if (hl && g[5]) { const s = img.clientWidth / g[5]; const b = document.createElement('i'); b.className = 'hlbox';
      Object.assign(b.style, { left: (hl[1] * s) + 'px', top: (hl[2] * s - 4) + 'px', width: ((hl[3] - hl[1]) * s) + 'px', height: ((hl[4] - hl[2]) * s + 8) + 'px' }); wrap.appendChild(b);
      $('#scanbody').scrollTop = Math.max(0, hl[2] * s - 160); }
  };
  img.onerror = () => { $('#scanbody').innerHTML = '<div class="msg">Das Bild konnte nicht geladen werden. Bitte im Browser bei Google angemeldet sein (Konto mit Zugriff auf den Ordner HistOrniGraph_output) oder „In Drive öffnen“.</div>'; };
  img.src = thumb(id);
}
$('#scanclose').onclick = closeScan;
$('#scanzoom').onclick = () => { scan.zoom = !scan.zoom; renderScan(); };
$('#scanprev').onclick = () => { if (scan.p > 0) { scan.p--; renderScan(); } };
$('#scannext').onclick = () => { if (scan.p + 1 < PG.length) { scan.p++; renderScan(); } };
$('#scanpages').addEventListener('click', e => { const b = e.target.closest('[data-sp]'); if (b) { scan.p = +b.dataset.sp; renderScan(); } });

// ---------- mentions ----------
function pickSpread(ids, k) {
  const s = ids.slice().sort((a, b) => (E[a[1]][2] || '9999').localeCompare(E[b[1]][2] || '9999') || a[0] - b[0]);
  if (s.length <= k) return s;
  return Array.from({ length: k }, (_, j) => s[Math.round(j * (s.length - 1) / (k - 1))]);
}
function menDec(t, mi) { return S.men[t][M[t].mkey[mi]]; }
function entryHead(ei, extra) {
  const e = E[ei]; const pages = e[8];
  return '<b>' + esc(e[3] || e[2] || 'ohne Datum') + '</b>' + (e[2] && e[3] !== e[2] ? '<span class="muted">' + esc(e[2]) + '</span>' : '')
    + (e[6] ? '<span>' + esc(e[6]) + '</span>' : '') + '<span class="sp"></span><span class="muted">' + esc(e[0]) + ' · ' + esc(pages.length ? pageLabel(pages[0]) : 'Band ' + e[5]) + (pages.length > 1 ? ' +' + (pages.length - 1) + ' S.' : '')
    + (e[4] && e[4] !== 'field-day' ? ' · ' + esc(KIND_DE[e[4]] || e[4]) : '') + '</span>' + (extra || '')
    + (pages.length ? '<button class="lbtn" data-scan="' + ei + '">Scan' + (pages.length > 1 ? ' (' + pages.length + ' S.)' : '') + '</button>' : '');
}
function textCorrLines(uid) { return S.text.filter(c => c.entry_uid === uid).map(c => '<div class="pc">✎ Lesung: „' + esc(c.old) + '“ → „<b>' + esc(c.new) + '</b>“' + (c.note ? ' <span class="muted">' + esc(c.note) + '</span>' : '') + ' <button class="lbtn" data-deltext="' + esc(c.id) + '">entfernen</button></div>').join(''); }
function menHtml(t, mi, opts) {
  opts = opts || {};
  const m = P[t].men[mi]; const ei = m[1]; const e = E[ei]; const d = menDec(t, mi); const f = P[t].forms[m[0]];
  const full = ui.fullText === mi;
  const acts = opts.noActs ? '' : '<span class="macts"><button class="mb y' + (d && d.d === 'y' ? ' on' : '') + '" data-md="y" title="Beleg stimmt">✓</button>' + (t === 'habitat' ? '' : '<button class="mb r' + (d && d.d === 'r' ? ' on' : '') + '" data-md="r" title="Beleg anders zuordnen">↪</button>') + '<button class="mb n' + (d && d.d === 'n' ? ' on' : '') + '" data-md="n" title="Kein(e) ' + TYPE[t].one + '">✗</button><button class="mb" data-md="text" title="Lesung korrigieren (was steht im Scan?)">✎</button></span>';
  const dl = d ? '<div class="pc ' + ({ y: 'ok', n: 'no', r: 'r' }[d.d] || '') + '">Beleg: ' + esc(DEC_DE[d.d] || d.d) + (d.target ? ' → <b>' + esc(d.target.label || d.target.code) + '</b>' + (d.target.sci ? ' <i>' + esc(d.target.sci) + '</i>' : '') : '') + (d.reason ? ' (' + esc(reasonLabel(t, d.reason)) + ')' : '') + (d.note ? ' · ' + esc(d.note) : '') + ' <button class="lbtn" data-mclear="1">zurücksetzen</button></div>' : '';
  const other = cur.task && cur.task.type === 'form' && f[2] !== curItem().ent ? '<span class="tag">→ ' + esc(entLabel(t, f[2])) + '</span>' : '';
  const role = m[5] ? '<span class="tag">' + esc(m[5]) + '</span>' : '';
  return '<div class="psg" data-mi="' + mi + '" data-ei="' + ei + '"><div class="ph">' + entryHead(ei, role + other) + acts + '</div>' + dl + textCorrLines(e[1])
    + snipHtml(m[4]) + '<div class="pb">' + kwic(e[7], m[2], m[3], full) + '</div>'
    + '<div class="pn"><button class="more" data-full="' + mi + '">' + (full ? 'Ausschnitt zeigen' : 'ganzen Eintrag zeigen') + '</button></div><div class="mslot"></div></div>';
}
function mentionsBlock(t, it) {
  const all = it.men.map(i => [i, P[t].men[i][1]]);
  const decided = all.filter(([i]) => menDec(t, i));
  let show = ui.showAll ? all.slice().sort((a, b) => (E[a[1]][2] || '').localeCompare(E[b[1]][2] || '')).slice(0, 25 * ui.menPage) : pickSpread(all, 10);
  for (const x of decided) if (!show.some(y => y[0] === x[0])) show.push(x);
  const head = '<div class="ch"><h3>Belege im Tagebuch</h3><span class="small muted">' + fmt(all.length) + (all.length === 1 ? ' Beleg' : ' Belege') + (all.length > show.length && !ui.showAll ? ', ' + show.length + ' über die Jahre verteilt' : '') + (decided.length ? ' · ' + decided.length + ' einzeln entschieden' : '') + '</span>'
    + (all.length > 10 ? '<button class="lbtn" id="menAll">' + (ui.showAll ? 'Auswahl zeigen' : 'alle ' + fmt(all.length) + ' zeigen') + '</button>' : '') + '</div>';
  const more = ui.showAll && show.length < all.length ? '<button class="lbtn" id="menMore">weitere 25</button>' : '';
  return '<div class="card">' + head + '<div class="cb">' + show.map(([i]) => menHtml(t, i)).join('') + more + '</div></div>';
}
function reasonLabel(t, r) { return ((NOT_REASONS[t] || []).find(x => x[0] === r) || [r, r])[1]; }

// ---------- detail: forms ----------
function decisionBar(t, it) {
  const d = S.id[t][it.key] || {};
  const b = (k, label, key, title) => '<button class="dbtn ' + k + (d.d === k ? ' on' : '') + '" data-d="' + k + '"' + (title ? ' title="' + esc(title) + '"' : '') + '>' + label + ' <kbd>' + key + '</kbd></button>';
  const one = TYPE[t].one;
  let h = '<div class="decide">';
  if (t === 'taxon') h += b('y', P.taxon.ent[it.ent][2] ? 'Zuordnung stimmt' : 'Name stimmt, keine GBIF-Art', 'Y') + b('r', 'Andere Art …', 'A') + b('x', 'Falsch, Art offen', 'F', 'Die Zuordnung stimmt nicht, die richtige Art ist aber nicht bestimmbar') + b('n', 'Keine Vogelart …', 'N');
  else if (t === 'habitat') h += b('y', 'Klasse passt', 'Y') + b('r', 'Andere Klasse …', 'A') + b('x', 'Keine Klasse passt', 'F') + b('n', 'Kein Lebensraum …', 'N');
  else {
    if (!itemIsCanonical(t, it)) h += b('y', 'Gehört zu „' + esc(entLabel(t, it.ent)) + '“', 'Y');
    h += b('r', (t === 'person' ? 'Andere Person' : 'Anderer Ort') + ' …', 'A');
    if (!itemIsCanonical(t, it)) h += b('o', t === 'person' ? 'Eigene Person' : 'Eigener Ort', 'O', 'Nicht zusammenführen: eigene ' + one);
    h += b('n', (t === 'person' ? 'Keine Person' : 'Kein Ort') + ' …', 'N');
  }
  h += b('e', 'Belege einzeln', 'E', 'Die Belege meinen Verschiedenes: jeden Beleg einzeln entscheiden') + b('u', 'Unsicher', 'U');
  if (d.d) h += '<button class="dbtn clear" data-d="">Zurücksetzen</button>';
  h += '</div>';
  if (d.d === 'r' && d.target) h += '<div class="fixed">Neu zugeordnet: <b>' + esc(d.target.label || d.target.code) + '</b>' + (d.target.sci ? ' <i>' + esc(d.target.sci) + '</i>' : '') + (d.target.match ? ' (' + esc(d.target.match) + ')' : '') + '</div>';
  if (d.d === 'n' && d.reason) h += '<div class="fixed no">' + esc(reasonLabel(t, d.reason)) + '</div>';
  if (ui.panel === 'r') h += reassignPanel(t, it, 'form');
  if (ui.panel === 'n') h += reasonPanel(t, 'form');
  h += '<textarea class="note" id="note" placeholder="Anmerkung (optional)">' + esc(d.note || '') + '</textarea>'
    + '<div class="status-line">' + (d.d ? 'Entschieden' + (d.by ? ' von ' + esc(d.by) : '') + ' am ' + new Date(d.t).toLocaleString('de-DE') : 'Noch nicht entschieden') + '</div>';
  return h;
}
function reasonPanel(t, scope) {
  return '<div class="fixbox" data-scope="' + scope + '"><h5>Warum?</h5><div class="row">' + NOT_REASONS[t].map(([k, l]) => '<button class="lbtn" data-reason="' + k + '">' + esc(l) + '</button>').join('') + '</div></div>';
}
function reassignPanel(t, it, scope) {
  const ph = { taxon: 'Art suchen: deutscher oder wissenschaftlicher Name', person: 'Person suchen', place: 'Ort suchen', habitat: 'EUNIS-Klasse suchen: Code oder englischer Begriff (reed, forest, C3.2)' }[t];
  return '<div class="fixbox rpanel" data-scope="' + scope + '" data-kind="' + t + '"><h5>' + ({ taxon: 'Andere Art', person: 'Andere Person', place: 'Anderer Ort', habitat: 'Andere EUNIS-Klasse' }[t]) + '</h5><div class="row"><input type="text" class="grow rq" placeholder="' + esc(ph) + '" autocomplete="off">'
    + (t === 'taxon' ? '<button class="lbtn rgbif">in GBIF suchen</button>' : '') + (t === 'habitat' ? '<select class="rmatch" title="exact = gleiche Bedeutung, close = sehr ähnlich, broad = Klasse ist allgemeiner"><option value="exact">exact</option><option value="close" selected>close</option><option value="broad">broad</option></select>' : '')
    + '</div><div class="res rres"></div></div>';
}
function taxonCard(it) {
  const e = P.taxon.ent[it.ent]; const f = it.f;
  const sib = M.taxon.formsByEnt[it.ent].map(i => P.taxon.forms[i]).sort((a, b) => b[1] - a[1]);
  const sibs = sib.map(s => { const d = itemDec('taxon', M.taxon.byName.get(lc(s[0])) || {}); return '<span class="sib' + (lc(s[0]) === it.key ? ' me' : '') + '" data-go="' + esc(lc(s[0])) + '"><span class="dot ' + (DOT[d] || '') + '"></span>' + esc(s[0]) + ' <b>' + fmt(s[1]) + '</b> <span class="cls cls' + s[3] + '">' + esc(TYPE.taxon.cls[s[3]][0]) + '</span></span>'; }).join('');
  const why = f[3] === 'A' ? 'deutscher Name dieser Art' + (f[4] && f[4] !== it.name ? ' („' + esc(f[4]) + '“)' : '') : f[3] === 'B' ? 'Variante von „' + esc(f[4]) + '“' : f[3] === 'C' ? (f[4] ? 'nicht belegt; am ähnlichsten: „' + esc(f[4]) + '“' : 'nicht als Name dieser Art belegt') : 'keine GBIF-Art zugeordnet';
  return '<div class="card"><div class="cb"><div class="q">' + esc(it.name) + '<span class="arrow">→</span>' + (e[2] ? esc(e[0]) + ' <i class="sci">' + esc(e[1]) + '</i>' : '<span class="muted">' + esc(e[0]) + ' (ohne GBIF-Art)</span>') + '</div>'
    + '<div class="qsub">' + fmt(it.n) + (it.n === 1 ? ' Beleg' : ' Belege') + ' · <span class="cls cls' + it.cls + '" title="' + esc(TYPE.taxon.cls[it.cls][1]) + '">' + esc(TYPE.taxon.cls[it.cls][0]) + '</span> ' + why + '</div>'
    + '<dl class="facts">' + (e[2] ? '<dt>GBIF</dt><dd><a href="https://www.gbif.org/species/' + esc(e[2]) + '" target="_blank" rel="noopener"><i>' + esc(e[1]) + '</i> ↗</a> <span class="muted small">' + esc(e[3] || '') + (e[4] ? ' · ' + esc(e[4]) : '') + (e[5] ? ' · ' + esc(e[5]) : '') + (e[6] ? ' · ' + esc(e[6]) : '') + '</span>' + (e[4] === 'HIGHERRANK' ? ' <span class="tag warn">nur übergeordnete Ebene</span>' : '') + '</dd>' : '')
    + (e[9].length ? '<dt>Deutsche Namen</dt><dd class="small">' + e[9].slice(0, 14).map(esc).join(', ') + (e[9].length > 14 ? ' …' : '') + '</dd>' : '')
    + (f[5] ? '<dt>Modell las</dt><dd><i>' + esc(f[5]) + '</i>' + (f[6] ? ' <span class="muted small">(' + esc(f[6]) + ')</span>' : '') + '</dd>' : '')
    + (it.forms.length > 1 ? '<dt>Achtung</dt><dd>Dieser Name ist ' + it.forms.length + ' Arten zugeordnet: ' + it.forms.map(i => esc(P.taxon.ent[P.taxon.forms[i][2]][0]) + ' (' + P.taxon.forms[i][1] + ')').join(', ') + '</dd>' : '')
    + '</dl><div class="subh">Namensformen dieser Art im Tagebuch</div><div class="sibs">' + sibs + '</div>'
    + '</div><div class="cb" style="border-top:1px solid var(--line)">' + decisionBar('taxon', it) + '</div></div>';
}
function personCard(it) {
  const e = P.person.ent[it.ent]; const lab = e[0]; const a = S.ent.person[lab] || {};
  const sibs = M.person.formsByEnt[it.ent].map(i => P.person.forms[i]).sort((x, y) => y[1] - x[1]).map(s => { const d = itemDec('person', M.person.byName.get(lc(s[0])) || {}); return '<span class="sib' + (lc(s[0]) === it.key ? ' me' : '') + '" data-go="' + esc(lc(s[0])) + '"><span class="dot ' + (DOT[d] || '') + '"></span>' + esc(s[0]) + ' <b>' + fmt(s[1]) + '</b>' + (s[4] ? ' <span class="muted small">' + esc(s[4]) + '</span>' : '') + '</span>'; }).join('');
  const cands = new Map(); for (const i of M.person.formsByEnt[it.ent]) for (const c of P.person.forms[i][5] || []) if (!cands.has(c[0])) cands.set(c[0], c);
  if (e[1] && !cands.has(e[1])) cands.set(e[1], [e[1], 'im Graph verknüpft', '']);
  const chosen = a.d === 'y' ? a.qid : (a.d ? null : e[1]);
  let list = [...cands.values()].map((c, k) => '<div class="cand' + (chosen === c[0] ? ' on' : '') + '" data-qid="' + esc(c[0]) + '"><span class="k">' + (k < 9 ? k + 1 : '') + '</span><div><div class="cl">' + esc(c[1]) + '</div><div class="cd">' + esc(c[2] || 'keine Beschreibung') + '</div></div><a class="ci" href="https://www.wikidata.org/wiki/' + esc(c[0]) + '" target="_blank" rel="noopener">' + esc(c[0]) + ' ↗</a></div>').join('');
  if (a.d === 'y' && a.qid && !cands.has(a.qid)) list += '<div class="cand on"><span class="k">+</span><div><div class="cl">' + esc(a.wd_label || a.qid) + '</div><div class="cd">' + esc(a.wd_description || 'selbst gesucht') + '</div></div><a class="ci" href="https://www.wikidata.org/wiki/' + esc(a.qid) + '" target="_blank" rel="noopener">' + esc(a.qid) + ' ↗</a></div>';
  const gnd = a.gnd || (!a.d && e[2]) || '';
  const linkState = a.d === 'y' ? '<span class="tag ok">Verknüpfung bestätigt</span>' : a.d === 'n' ? '<span class="tag no">keine passende Normdatei</span>' : e[1] || e[2] ? '<span class="tag">automatisch verknüpft, ungeprüft</span>' : '<span class="tag warn">noch nicht verknüpft</span>';
  return '<div class="card"><div class="cb"><div class="q">' + esc(it.name) + (it.name !== lab ? '<span class="arrow">→</span>' + esc(lab) : '') + '</div>'
    + '<div class="qsub">' + fmt(it.n) + ' Nennungen · <span class="cls cls' + it.cls + '" title="' + esc(TYPE.person.cls[it.cls][1]) + '">' + esc(TYPE.person.cls[it.cls][0]) + '</span>' + (it.f[4] ? ' Regel: ' + esc(it.f[4]) : '') + '</div>'
    + '<div class="subh">Namensformen dieser Person</div><div class="sibs">' + sibs + '</div>'
    + '</div><div class="cb" style="border-top:1px solid var(--line)">' + decisionBar('person', it) + '</div>'
    + '<div class="cb" style="border-top:1px solid var(--line)"><div class="subh">Normdaten für „' + esc(lab) + '“ ' + linkState + '</div><div class="cands">' + (list || '<div class="muted small">keine Wikidata-Kandidaten</div>') + '</div>'
    + '<div class="subh">GND</div>' + (gnd ? '<div class="cand on"><span class="k">✓</span><div><div class="cl">' + esc(a.gnd_label || gnd) + '</div><div class="cd">' + esc(a.gnd_info || (a.gnd ? '' : 'im Graph')) + '</div></div><span><a class="ci" href="https://d-nb.info/gnd/' + esc(gnd) + '" target="_blank" rel="noopener">' + esc(gnd) + ' ↗</a> <button class="lbtn" id="gndclear">entfernen</button></span></div>' : '<div class="muted small">noch keine GND</div>')
    + '<div class="row" style="margin-top:8px"><button class="lbtn" id="linkok"' + (chosen || gnd ? '' : ' disabled') + '>Verknüpfung bestätigen</button><button class="lbtn" id="linkno">keine passt</button>' + (a.d ? '<button class="lbtn" id="linkreset">zurücksetzen</button>' : '') + '</div>'
    + '<div class="fixbox"><h5>Suchen</h5><div class="row"><input type="text" class="grow" id="wq" value="' + esc(lab.replace(/^(Prof\.|Dr\.|Herr|Frau|Frl\.|Lehrer|Pfarrer|Oberförster|Förster)\s+/g, '')) + '"><button class="lbtn" id="wbtn">Wikidata</button><button class="lbtn" id="gndbtn">GND</button></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" id="wqid" placeholder="QID, z. B. Q12345" style="width:170px"><button class="lbtn" id="wqidbtn">übernehmen</button><input type="text" id="gndid" placeholder="GND-ID oder d-nb.info-Link" style="width:220px"><button class="lbtn" id="gndidbtn">übernehmen</button></div><div id="wres"></div></div></div></div>';
}
function placeCard(it) {
  const e = P.place.ent[it.ent]; const lab = e[0]; const a = S.ent.place[lab] || {}; const fix = a.fix; const lr = it.f[5] || [];
  const sibs = M.place.formsByEnt[it.ent].map(i => P.place.forms[i]).sort((x, y) => y[1] - x[1]).map(s => { const d = itemDec('place', M.place.byName.get(lc(s[0])) || {}); return '<span class="sib' + (lc(s[0]) === it.key ? ' me' : '') + '" data-go="' + esc(lc(s[0])) + '"><span class="dot ' + (DOT[d] || '') + '"></span>' + esc(s[0]) + ' <b>' + fmt(s[1]) + '</b>' + (s[4] ? ' <span class="muted small">' + esc(s[4]) + '</span>' : '') + '</span>'; }).join('');
  const linkState = a.d === 'y' ? '<span class="tag ok">Georeferenz bestätigt</span>' : a.d === 'n' ? '<span class="tag no">falsch / nicht bestimmbar</span>' : e[1] != null ? '<span class="tag">automatisch, ungeprüft</span>' : '<span class="tag warn">ohne Koordinaten</span>';
  return '<div class="card"><div class="cb"><div class="q">' + esc(it.name) + (it.name !== lab ? '<span class="arrow">→</span>' + esc(lab) : '') + '</div>'
    + '<div class="qsub">' + fmt(it.n) + ' Nennungen · <span class="cls cls' + it.cls + '" title="' + esc(TYPE.place.cls[it.cls][1]) + '">' + esc(TYPE.place.cls[it.cls][0]) + '</span>' + (it.f[4] ? ' Regel: ' + esc(it.f[4]) : '') + (e[6] ? ' · Art: ' + esc(e[6]) : '') + '</div>'
    + '<div class="subh">Namensformen dieses Ortes</div><div class="sibs">' + sibs + '</div>'
    + '</div><div class="cb" style="border-top:1px solid var(--line)">' + decisionBar('place', it) + '</div>'
    + '<div class="cb" style="border-top:1px solid var(--line)"><div class="subh">Georeferenz von „' + esc(lab) + '“ ' + linkState + '</div>'
    + '<dl class="facts">' + (e[1] != null ? '<dt>Im Graph</dt><dd>' + e[1] + ', ' + e[2] + (e[3] ? ' (± ' + fmt(e[3]) + ' m)' : '') + (e[7] ? ' · <span class="muted small">' + esc(e[7]) + '</span>' : '') + '</dd>' : '<dt>Im Graph</dt><dd class="muted">keine Koordinate</dd>')
    + (e[4] ? '<dt>GeoNames</dt><dd><a href="https://www.geonames.org/' + esc(e[4]) + '" target="_blank" rel="noopener">' + esc(lr[7] || e[4]) + '</a>' + (lr[11] ? ' · ' + esc(lr[11]) : '') + (lr[8] ? ' · ' + esc(lr[8]) : '') + '</dd>' : '')
    + (e[5] ? '<dt>Wikidata</dt><dd><a href="https://www.wikidata.org/wiki/' + esc(e[5]) + '" target="_blank" rel="noopener">' + esc(e[5]) + '</a></dd>' : '')
    + (lr[3] ? '<dt>Hinweis</dt><dd class="small">' + esc(lr[3]) + '</dd>' : '') + '</dl>'
    + '<div id="map"></div><div class="maplegend"><span><i style="background:#e0542e"></i>im Graph</span><span><i style="background:#1e7a4c"></i>Korrektur</span><span><i style="background:#3a6fb0;opacity:.6"></i>Orte aus denselben Einträgen</span><span>Klick in die Karte setzt einen Punkt</span></div>'
    + '<div class="row" style="margin-top:8px"><button class="lbtn" id="geook"' + (e[1] != null || (fix && fix.lat) ? '' : ' disabled') + '>' + (fix ? 'Korrektur übernehmen' : 'Georeferenz stimmt') + '</button><button class="lbtn" id="geono">falsch / nicht bestimmbar</button>' + (a.d || fix ? '<button class="lbtn" id="georeset">zurücksetzen</button>' : '') + '</div>'
    + (fix ? '<div class="fixed">' + (fix.lat ? fix.lat + ', ' + fix.lon + ' (± ' + fmt(fix.uncertainty_m) + ' m)' : 'Koordinaten wie im Graph') + (fix.geonames_id ? ' · GeoNames ' + esc(fix.geonames_id) : '') + (fix.qid ? ' · ' + esc(fix.qid) : '') + (fix.note ? ' · ' + esc(fix.note) : '') + '</div>' : '')
    + '<div class="fixbox"><h5>Suchen</h5><div class="row"><input type="text" class="grow" id="nq" value="' + esc(lab) + '"><button class="lbtn" id="nbtn">OpenStreetMap</button><button class="lbtn" id="pwbtn">Wikidata</button>'
    + '<a class="lbtn" target="_blank" rel="noopener" href="https://www.geonames.org/search.html?q=' + encodeURIComponent(lab) + '">GeoNames ↗</a></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" id="ll" placeholder="Breite, Länge" style="width:150px"><select id="unc"><option value="100">± 100 m</option><option value="500">± 500 m</option><option value="1000" selected>± 1 km</option><option value="2000">± 2 km</option><option value="5000">± 5 km</option><option value="10000">± 10 km</option></select><button class="lbtn" id="llbtn">setzen</button>'
    + '<input type="text" id="gnid" placeholder="GeoNames-ID oder Link" style="width:170px" value="' + esc((fix && fix.geonames_id) || '') + '"><input type="text" id="pqid" placeholder="Wikidata-QID" style="width:120px" value="' + esc((fix && fix.qid) || '') + '"><button class="lbtn" id="idbtn">IDs übernehmen</button></div><div id="nres"></div></div></div></div>';
}
const EUNIS = new Map(P.eunis.map(e => [e[0], e]));
function habitatCard(it) {
  const e = P.habitat.ent[it.ent]; const lr = it.f[5] || []; const x = EUNIS.get(e[1]);
  return '<div class="card"><div class="cb"><div class="q">' + esc(it.name) + '<span class="arrow">→</span>' + (e[1] ? esc(e[1]) + ' ' + esc((x || [])[1] || lr[4] || '') : '<span class="muted">keine EUNIS-Klasse</span>') + '</div>'
    + '<div class="qsub">' + fmt(it.n) + ' Beobachtungen · <span class="cls cls' + it.cls + '">' + esc(TYPE.habitat.cls[it.cls][0]) + '</span>' + (e[2] ? ' · Übereinstimmung ' + esc(e[2]) : '') + (lr[1] ? ' · Konfidenz ' + esc(lr[1]) : '') + '</div>'
    + '<dl class="facts">' + (lr[2] ? '<dt>Begründung Modell</dt><dd>' + esc(lr[2]) + '</dd>' : '') + (x ? '<dt>Ebene</dt><dd>' + x[2] + (x[3] ? ' (übergeordnet: ' + esc(x[3]) + ' ' + esc((EUNIS.get(x[3]) || [])[1] || '') + ')' : '') + ' · <a href="https://biodiversity.europa.eu/resources/search-habitat/eunis-habitat-types-hierarchical-view-2012?searchTerm=' + encodeURIComponent(e[1]) + '" target="_blank" rel="noopener">BISE ↗</a></dd>' : '')
    + (e[3].length > 1 ? '<dt>Schreibweisen</dt><dd class="small">' + e[3].map(esc).join(', ') + '</dd>' : '') + '</dl>'
    + '</div><div class="cb" style="border-top:1px solid var(--line)">' + decisionBar('habitat', it) + '</div></div>';
}
function frame(inner) {
  const t = cur.task;
  return '<div class="dwrap"><div class="crumb"><span>' + esc(t.group + ' · ' + t.title) + '</span><span>' + fmt(cur.i + 1) + ' von ' + fmt(cur.list.length) + '</span>'
    + '<span class="nav"><button class="nbtn" data-nav="-1" title="Vorheriger (K oder ↑)">↑ zurück</button><button class="nbtn" data-nav="1" title="Nächster (J oder ↓)">weiter ↓</button></span></div>' + inner
    + '<div class="kbdrow">' + (t.type === 'form' ? '<kbd>Y</kbd> stimmt · <kbd>A</kbd> anders zuordnen · <kbd>N</kbd> kein(e) ' + esc(TYPE[t.kind].one) + ' · <kbd>E</kbd> Belege einzeln · <kbd>U</kbd> unsicher' + (t.kind === 'taxon' || t.kind === 'habitat' ? ' · <kbd>F</kbd> falsch/offen' : ' · <kbd>O</kbd> eigene') : '<kbd>Y</kbd> <kbd>N</kbd> <kbd>U</kbd> entscheiden')
    + ' · <kbd>J</kbd>/<kbd>K</kbd> blättern · <kbd>S</kbd> Scan · <kbd>X</kbd> zurücksetzen · <label><input type="checkbox" id="adv"' + (S.ui.adv ? ' checked' : '') + '> nach Entscheidung automatisch weiter</label></div></div>';
}
let map = null;
function renderDetail() {
  const t = cur.task; const it = curItem(); if (!it) return;
  if (map) { map.remove(); map = null; }
  let h;
  if (t.type === 'form') {
    const card = { taxon: taxonCard, person: personCard, place: placeCard, habitat: habitatCard }[t.kind](it);
    h = card + mentionsBlock(t.kind, it);
  } else if (t.type === 'eval') h = evalDetail(it);
  else h = qaDetail(it);
  $('#detail').innerHTML = frame(h);
  wire(t, it); wireSnips($('#detail'));
}

// ---------- evaluation sample ----------
function wilson(k, n) { if (!n) return [0, 0, 0]; const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [p, Math.max(0, c - h), Math.min(1, c + h)]; }
function evalStats() {
  const by = {}; let k = 0, n = 0;
  for (const mi of P.sample) { const d = S.ev[M.taxon.mkey[mi]]; if (!d || (d.d !== 'y' && d.d !== 'n')) continue; const cls = P.taxon.forms[P.taxon.men[mi][0]][3]; by[cls] = by[cls] || [0, 0]; by[cls][1]++; n++; if (d.d === 'y') { k++; by[cls][0]++; } }
  return { k, n, by };
}
function evalStatsHtml() {
  const st = evalStats(); const [p, lo, hi] = wilson(st.k, st.n);
  return '<div class="card"><div class="cb"><div class="subh" style="margin-top:0">Genauigkeit der Artbestimmung (Stichprobe)</div>'
    + (st.n ? '<div class="evbig">' + pct(p) + ' <span class="muted small">95 %-Intervall ' + pct(lo) + ' – ' + pct(hi) + ' · ' + st.k + ' von ' + st.n + ' richtig</span></div>' : '<div class="muted small">Noch keine Belege beurteilt.</div>')
    + '<div class="small muted">' + Object.entries(st.by).map(([c, [a, b]]) => esc(TYPE.taxon.cls[c][0]) + ': ' + a + '/' + b).join(' · ') + '</div></div></div>';
}
function evalDetail(it) {
  const mi = it.mi; const m = P.taxon.men[mi]; const f = P.taxon.forms[m[0]]; const e = P.taxon.ent[f[2]]; const d = S.ev[it.key] || {};
  const b = (k, label, key) => '<button class="dbtn ' + k + (d.d === k ? ' on' : '') + '" data-d="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  return evalStatsHtml() + '<div class="card"><div class="cb"><div class="q">' + esc(f[0]) + '<span class="arrow">→</span>' + (e[2] ? esc(e[0]) + ' <i class="sci">' + esc(e[1]) + '</i>' : '<span class="muted">' + esc(e[0]) + ' (ohne GBIF-Art)</span>') + '</div>'
    + '<div class="qsub">Beleg ' + (it.k + 1) + ' von ' + P.sample.length + ' · Ist an dieser Stelle diese Art gemeint? Im Zweifel Scan ansehen.</div>'
    + '<div class="decide">' + b('y', 'Richtig bestimmt', 'Y') + b('n', 'Falsch', 'N') + b('u', 'Nicht entscheidbar', 'U') + (d.d ? '<button class="dbtn clear" data-d="">Zurücksetzen</button>' : '') + '</div>'
    + (d.d === 'n' ? reassignPanel('taxon', null, 'eval') + (d.target ? '<div class="fixed">Richtig wäre: <b>' + esc(d.target.label) + '</b> <i>' + esc(d.target.sci || '') + '</i></div>' : '') : '')
    + '<textarea class="note" id="note" placeholder="Anmerkung (optional)">' + esc(d.note || '') + '</textarea></div></div>'
    + '<div class="card"><div class="cb">' + menHtml('taxon', mi, { noActs: true }) + '</div></div>';
}

// ---------- QA ----------
function qaDetail(it) {
  const r = it.r; const q = QA_DE[r[2]] || [r[2], '']; const d = S.qa[it.key] || {};
  const b = (k, label, key) => '<button class="dbtn ' + k + (d.d === k ? ' on' : '') + '" data-d="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  const isTaxon = ['non_bird', 'low_confidence_taxon'].includes(r[2]) && r[4];
  const mk = r[1] + '|' + lc(r[4]) + '|0'; const md = isTaxon ? S.men.taxon[mk] : null;
  let ev = '<div class="card"><div class="cb muted">Eintrag nicht mehr im Graph, kein Text verfügbar.</div></div>';
  if (it.ei >= 0) {
    const e = E[it.ei]; const pos = r[4] && !/^\d+$/.test(r[4]) ? (() => { const i = lc(e[7]).indexOf(lc(r[4])); return i >= 0 ? [i, i + r[4].length] : [-1, -1]; })() : [-1, -1];
    ev = '<div class="card"><div class="ch"><h3>Tagebucheintrag</h3></div><div class="cb"><div class="psg" data-ei="' + it.ei + '"><div class="ph">' + entryHead(it.ei) + '</div>' + textCorrLines(e[1]) + '<div class="pb">' + (pos[0] >= 0 ? highlight(e[7], [[pos[0], pos[1], '']]) : esc(e[7])) + '</div><div class="pn"><button class="lbtn" data-textfix="' + it.ei + '">✎ Lesung korrigieren</button></div><div class="mslot"></div></div></div></div>';
  }
  return '<div class="card"><div class="cb"><div class="q">' + esc(q[0]) + (r[4] ? '<span class="arrow">·</span>' + esc(r[4]) : '') + '</div>'
    + '<div class="qsub">' + esc(q[1]) + ' <span class="tag ' + (r[3] === 'excluded' ? 'no' : 'warn') + '">' + (r[3] === 'excluded' ? 'entfernt' : 'nur markiert') + '</span></div>'
    + '<dl class="facts"><dt>Eintrag</dt><dd>' + esc(r[0]) + '</dd><dt>Begründung</dt><dd>' + esc(r[5]) + '</dd></dl>'
    + '</div><div class="cb" style="border-top:1px solid var(--line)"><div class="decide">' + b('y', 'Richtig erkannt', 'Y') + b('n', 'Falsch erkannt', 'N') + b('u', 'Unsicher', 'U') + (d.d ? '<button class="dbtn clear" data-d="">Zurücksetzen</button>' : '') + '</div>'
    + (isTaxon ? '<div class="fixbox"><h5>Richtige Art für „' + esc(r[4]) + '“ in diesem Eintrag</h5>' + (md && md.target ? '<div class="fixed">' + esc(md.target.label) + ' <i>' + esc(md.target.sci || '') + '</i> <button class="lbtn" data-qaunfix="1">verwerfen</button></div>' : '<div class="rpanel" data-scope="qa" data-kind="taxon"><div class="row"><input type="text" class="grow rq" placeholder="Art suchen" autocomplete="off"><button class="lbtn rgbif">in GBIF suchen</button></div><div class="res rres"></div></div>') + '</div>' : '')
    + '<div class="row" style="margin-top:8px"><input type="text" class="grow" id="qacorr" placeholder="Korrektur, falls bekannt (z. B. Datum 1922-07-15)" value="' + esc(d.corr || '') + '"></div>'
    + '<textarea class="note" id="note" placeholder="Anmerkung (optional)">' + esc(d.note || '') + '</textarea></div></div>' + ev;
}

// ---------- overview / corrections ----------
function renderOverview() {
  if (map) { map.remove(); map = null; }
  let h = '<div class="dwrap"><div class="q" style="margin-top:6px">Validierung des Laubmann-Wissensgraphen</div><div class="qsub">Export ' + esc(P.export) + ' · ' + fmt(E.length) + ' Tagebucheinträge · ' + fmt(PG.length) + ' Seiten</div>'
    + '<div class="card"><div class="cb"><p style="margin:0 0 8px">Geprüft wird, <b>welche Art, Person, welcher Ort oder Lebensraum mit einem geschriebenen Namen gemeint ist</b>. Gleiche Zuordnung = ein Knoten im Graph: Zusammenführen ergibt sich daraus, es gibt keine Paare mehr zu vergleichen. Einzelne Belege lassen sich abweichend entscheiden, falsch gelesene Stellen direkt korrigieren.</p>'
    + '<div class="row" style="justify-content:space-between"><span class="small muted">Die Warteschlangen zeigen zuerst die riskanten Namen (unbelegt, nicht verknüpft, Varianten), die häufigsten oben.</span><button class="dbtn" id="ovHelpBtn">Anleitung</button></div></div></div><div class="stats">';
  for (const t of TASKS) {
    const p = progress(t); let sub = '';
    if (t.type === 'form') { const m = M[t.kind]; const risky = m.items.filter(it => TYPE[t.kind].on.includes(it.cls)); sub = fmt(risky.filter(it => !itemDec(t.kind, it)).length) + ' riskante offen · ' + pct(p.cov) + ' der Belege entschieden'; }
    else if (t.type === 'eval') { const st = evalStats(); const [q, lo, hi] = wilson(st.k, st.n); sub = st.n ? 'Genauigkeit ' + pct(q) + ' (' + pct(lo) + '–' + pct(hi) + ')' : 'noch nicht begonnen'; }
    h += '<div class="stat" data-t="' + t.id + '"><div class="l">' + esc(t.group) + '</div><div class="n">' + fmt(p.done + p.u) + ' <span class="muted" style="font-size:14px;font-weight:400">/ ' + fmt(p.tot) + '</span></div><div class="l"><b>' + esc(t.title) + '</b></div><div class="l small muted">' + sub + '</div></div>';
  }
  h += '</div></div>';
  $('#detail').innerHTML = h;
}
$('#detail').addEventListener('click', e => { const st = e.target.closest('.stat'); if (st) return openTask(TBY[st.dataset.t]); if (e.target.id === 'ovHelpBtn') return showHelp(); });
function openCorrections() {
  cur.task = { id: 'corr' }; renderSide(); closeScan();
  $('#qtitle').textContent = 'Korrekturen'; $('#qdesc').textContent = 'Lesungen und einzeln entschiedene Belege.'; $('#qchips').innerHTML = ''; $('#qlist').innerHTML = ''; $('#qcount').textContent = ''; $('#qsortwrap').style.display = 'none';
  let h = '<div class="dwrap"><div class="q">Korrekturen</div><div class="card"><div class="ch"><h3>Lesungen (Transkription)</h3><span class="small muted">Diese Einträge werden bei der nächsten Extraktion mit der korrigierten Lesung neu gelesen.</span></div><div class="cb">';
  h += S.text.length ? '<table class="tbl"><tr><th>Eintrag</th><th>gelesen → richtig</th><th>von</th><th></th></tr>' + S.text.slice().sort((a, b) => (b.t || '').localeCompare(a.t || '')).map(c => '<tr><td>' + esc(c.entry_id) + '</td><td>„' + esc(c.old) + '“ → „<b>' + esc(c.new) + '</b>“' + (c.note ? '<br><span class="muted small">' + esc(c.note) + '</span>' : '') + '</td><td>' + esc(c.by) + '</td><td><button class="lbtn" data-deltext="' + esc(c.id) + '">entfernen</button></td></tr>').join('') + '</table>' : '<p class="muted">Noch keine.</p>';
  h += '</div></div><div class="card"><div class="ch"><h3>Einzeln entschiedene Belege</h3></div><div class="cb">';
  let rows = '';
  for (const t of TYPES) for (const k in S.men[t]) { const d = S.men[t][k]; const [uid, name] = k.split('|'); const ei = E.findIndex(e => e[1] === uid);
    rows += '<tr><td>' + esc(TYPE[t].one) + '</td><td>' + esc(ei >= 0 ? E[ei][0] : uid) + '</td><td>' + esc(name) + ' → ' + esc(DEC_DE[d.d] || d.d) + (d.target ? ': <b>' + esc(d.target.label || d.target.code) + '</b>' : '') + (d.reason ? ' (' + esc(reasonLabel(t, d.reason)) + ')' : '') + '</td><td>' + esc(d.by || '') + '</td><td><button class="lbtn" data-delmen="' + esc(t + '§' + k) + '">entfernen</button></td></tr>'; }
  h += rows ? '<table class="tbl"><tr><th></th><th>Eintrag</th><th>Beleg</th><th>von</th><th></th></tr>' + rows + '</table>' : '<p class="muted">Noch keine.</p>';
  $('#detail').innerHTML = h + '</div></div></div>';
}

// ---------- decisions ----------
function setForm(t, it, obj) {
  if (!obj) delete S.id[t][it.key]; else S.id[t][it.key] = stampObj(obj);
  save(); refreshQi(cur.i); renderSide();
}
function decide(dv) {
  const t = cur.task; const it = curItem(); if (!it) return;
  const note = $('#note') ? $('#note').value.trim() : '';
  if (t.type === 'form') {
    const k = t.kind; const prev = S.id[k][it.key] || {};
    if (dv === 'r') { ui.panel = ui.panel === 'r' ? null : 'r'; renderDetail(); const q = $('#detail .rpanel[data-scope="form"] .rq'); if (q) q.focus(); return; }
    if (dv === 'n') { ui.panel = ui.panel === 'n' ? null : 'n'; renderDetail(); return; }
    if (dv === 'o' && (k === 'taxon' || k === 'habitat' || itemIsCanonical(k, it))) return;
    if (dv === 'x' && (k === 'person' || k === 'place')) return;
    if (dv === 'y' && (k === 'person' || k === 'place') && itemIsCanonical(k, it)) return toast('Kanonischer Name: bitte unten die Normdaten bzw. Georeferenz bestätigen');
    if (!dv) { setForm(k, it, note ? { d: '', note } : null); ui.panel = null; return renderDetail(); }
    setForm(k, it, { d: dv, note }); ui.panel = null;
    if (S.ui.adv && dv !== 'e') nextOpen(); else renderDetail();
    return;
  }
  const store = t.type === 'eval' ? S.ev : S.qa;
  if (!dv) delete store[it.key];
  else { const prev = store[it.key] || {}; const o = Object.assign({}, prev, { d: dv, note }); if ($('#qacorr')) o.corr = $('#qacorr').value.trim(); if (t.type === 'eval') o.cls = P.taxon.forms[P.taxon.men[it.mi][0]][3]; if (dv !== 'n') delete o.target; store[it.key] = stampObj(o); }
  save(); refreshQi(cur.i); renderSide();
  if (dv && S.ui.adv && !(t.type === 'eval' && dv === 'n')) nextOpen(); else renderDetail();
}
function setMention(t, mi, obj) {
  const k = M[t].mkey[mi];
  if (!obj) delete S.men[t][k]; else S.men[t][k] = stampObj(obj);
  save(); renderSide(); renderDetail();
}
function chooseTarget(target, scope) {
  // a target picked in a reassign panel: form, mention (index), evaluation or QA scope
  const t = cur.task; const it = curItem(); scope = scope || 'form';
  if (t.type === 'eval') { const d = S.ev[it.key] || { d: 'n' }; S.ev[it.key] = stampObj(Object.assign({}, d, { d: 'n', target }));
    const k = M.taxon.mkey[it.mi]; S.men.taxon[k] = stampObj({ d: 'r', target, note: 'aus der Stichprobe' }); save(); renderSide(); return renderDetail(); }
  if (t.type === 'qa') { const r = it.r; S.men.taxon[r[1] + '|' + lc(r[4]) + '|0'] = stampObj({ d: 'r', target, written: r[4], note: 'Qualitätsflag ' + r[2] });
    if (!(S.qa[it.key] || {}).d) S.qa[it.key] = stampObj({ d: 'n', note: '' }); save(); renderSide(); return renderDetail(); }
  if (scope === 'form') { setForm(t.kind, it, { d: 'r', target, note: $('#note') ? $('#note').value.trim() : '' }); ui.panel = null; if (S.ui.adv) nextOpen(); else renderDetail(); }
  else setMention(t.kind, +scope, { d: 'r', target });
}
function patchEnt(t, lab, fields) {
  const prev = S.ent[t][lab] || {}; const o = Object.assign({}, prev, fields); for (const k in fields) if (fields[k] == null) delete o[k];
  if (!o.d && !o.fix && !o.qid && !o.gnd) delete S.ent[t][lab]; else S.ent[t][lab] = stampObj(o);
  save(); refreshQi(cur.i); renderSide(); renderDetail();
}

// ---------- search panels ----------
function localTaxa(q) {
  const f = fold(q); if (!f) return [];
  const res = [];
  P.taxon.ent.forEach((e, i) => { if (!e[2]) return; const hay = [e[0], e[1], ...e[9]].map(fold); const hit = hay.some(h => h.includes(f)); if (!hit) return;
    const score = (fold(e[0]) === f || fold(e[1]) === f ? 0 : hay.some(h => h.startsWith(f)) ? 1 : 2); const n = M.taxon.formsByEnt[i].reduce((a, fi) => a + P.taxon.forms[fi][1], 0); res.push([score, -n, i]); });
  return res.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(([, n, i]) => ({ label: P.taxon.ent[i][0], sci: P.taxon.ent[i][1], key: P.taxon.ent[i][2], rank: P.taxon.ent[i][3], n: -n }));
}
function localEnts(t, q) {
  const f = fold(q); if (!f) return [];
  const res = [];
  P[t].ent.forEach((e, i) => { const labs = (t === 'person' ? e[3] : t === 'place' ? e[8] : e[3]) || [e[0]]; const hay = labs.map(fold); if (!hay.some(h => h.includes(f))) return;
    const n = M[t].formsByEnt[i].reduce((a, fi) => a + P[t].forms[fi][1], 0); res.push([fold(e[0]) === f ? 0 : hay.some(h => h.startsWith(f)) ? 1 : 2, -n, i]); });
  return res.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(([, n, i]) => ({ i, label: P[t].ent[i][0], n: -n }));
}
function wirePanel(root) {
  const kind = root.dataset.kind; const q = root.querySelector('.rq');
  q.oninput = () => renderLocalResults(root);
  q.onkeydown = e => { if (e.key === 'Enter' && kind === 'taxon') gbifSearch(root); };
  const g = root.querySelector('.rgbif'); if (g) g.onclick = () => gbifSearch(root);
}
function renderLocalResults(root) {
  const t = root.dataset.kind; const scope = root.dataset.scope; const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim();
  if (t === 'habitat') return eunisFilter(root);
  if (!q) { box.innerHTML = ''; return; }
  if (t === 'taxon') {
    const r = localTaxa(q);
    box.innerHTML = r.length ? r.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.label) + '</b> <i>' + esc(x.sci) + '</i> <small>' + esc(x.rank || '') + ' · ' + fmt(x.n) + ' Belege im Graph</small></div>').join('') : '<div class="r muted">Keine Art im Graph gefunden: „in GBIF suchen“.</div>';
    box.querySelectorAll('.r[data-k]').forEach(el => el.onclick = () => { const x = r[+el.dataset.k]; chooseTarget({ label: x.label, sci: x.sci, key: x.key, rank: x.rank }, scope); });
  } else {
    const r = localEnts(t, q);
    box.innerHTML = r.length ? r.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.label) + '</b> <small>' + fmt(x.n) + ' Nennungen' + (t === 'place' && P.place.ent[x.i][1] != null ? ' · ' + P.place.ent[x.i][1] + ', ' + P.place.ent[x.i][2] : '') + (t === 'person' && P.person.ent[x.i][1] ? ' · ' + P.person.ent[x.i][1] : '') + '</small></div>').join('') : '<div class="r muted">Nichts gefunden.</div>';
    box.querySelectorAll('.r[data-k]').forEach(el => el.onclick = () => chooseTarget({ label: r[+el.dataset.k].label }, scope));
  }
}
async function gbifSearch(root) {
  const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim(); const scope = root.dataset.scope;
  if (!q) return; box.innerHTML = '<div class="r muted">suche in GBIF …</div>';
  try {
    const [m, s] = await Promise.all([
      getJSON('https://api.gbif.org/v1/species/match?verbose=true&class=Aves&name=' + encodeURIComponent(q)).catch(() => ({})),
      getJSON('https://api.gbif.org/v1/species/search?datasetKey=d7dddbf4-2cf0-4f39-9b2a-bb099caae36c&limit=15&q=' + encodeURIComponent(q)).catch(() => ({ results: [] }))]);
    const seen = new Set(); const rows = [];
    const push = x => { const key = x.usageKey || x.key; if (!key || seen.has(key)) return; seen.add(key);
      rows.push({ key, name: x.canonicalName || x.scientificName, rank: x.rank, status: x.status || x.taxonomicStatus, acc: x.acceptedUsageKey || x.acceptedKey, cls: x.class, fam: x.family, vn: (x.vernacularNames || []).filter(v => v.language === 'deu').map(v => v.vernacularName).slice(0, 2).join(', ') }); };
    if (m.usageKey) push(m); (m.alternatives || []).forEach(push); (s.results || []).forEach(push);
    box.innerHTML = rows.length ? rows.map((x, k) => '<div class="r" data-k="' + k + '"><b><i>' + esc(x.name) + '</i></b> <small>' + esc(x.rank || '') + ' · ' + esc(x.status || '') + ' · ' + esc(x.key) + (x.fam ? ' · ' + esc(x.fam) : '') + (x.cls ? ' · ' + esc(x.cls) : '') + '</small>' + (x.vn ? '<br><small>' + esc(x.vn) + '</small>' : '') + '</div>').join('') : '<div class="r muted">Keine Treffer.</div>';
    box.querySelectorAll('.r[data-k]').forEach(el => el.onclick = async () => {
      const x = rows[+el.dataset.k]; let key = x.key, name = x.name, rank = x.rank; const vn = x.vn.split(',')[0];
      if (x.acc && x.acc !== x.key && x.status && x.status !== 'ACCEPTED') { try { const a = await getJSON('https://api.gbif.org/v1/species/' + x.acc); key = a.key; name = a.canonicalName || a.scientificName; rank = a.rank; toast('Synonym: auf akzeptierten Namen ' + name + ' umgestellt'); } catch (e) { } }
      const local = P.taxon.ent.find(e => e[2] === String(key));
      chooseTarget({ label: local ? local[0] : (vn || name), sci: name, key: String(key), rank: lc(rank) }, scope);
    });
  } catch (e) { box.innerHTML = '<div class="r muted">GBIF nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
function eunisFilter(root) {
  const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim().toLowerCase(); const scope = root.dataset.scope; if (!q) { box.innerHTML = ''; return; }
  const res = P.eunis.filter(e => e[0].toLowerCase().startsWith(q) || e[1].toLowerCase().includes(q)).sort((a, b) => a[2] - b[2] || a[0].localeCompare(b[0])).slice(0, 80);
  box.innerHTML = res.length ? res.map(e => '<div class="r" data-c="' + esc(e[0]) + '" style="padding-left:' + (6 + 10 * (e[2] - 1)) + 'px"><b>' + esc(e[0]) + '</b> ' + esc(e[1]) + ' <small>Ebene ' + e[2] + '</small></div>').join('') : '<div class="r muted">Keine Klasse gefunden (Namen sind englisch).</div>';
  const match = root.querySelector('.rmatch');
  box.querySelectorAll('.r[data-c]').forEach(el => el.onclick = () => chooseTarget({ code: el.dataset.c, label: el.dataset.c + ' ' + ((EUNIS.get(el.dataset.c) || [])[1] || ''), match: match ? match.value : 'close' }, scope));
}
async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }
async function wdClaims(qid) { try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims|labels|descriptions&languages=de|en&ids=' + qid); return (j.entities || {})[qid] || {}; } catch (e) { return {}; } }
function claimValue(ent, p) { const c = ((ent.claims || {})[p] || [])[0]; return c && c.mainsnak && c.mainsnak.datavalue ? c.mainsnak.datavalue.value : null; }
const gndId = v => { const m = String(v || '').match(/(?:d-nb\.info\/gnd\/)?([0-9]+-[0-9X]|[0-9]{1,10}[0-9X])\b/); return m ? m[1] : ''; };
function pickPerson(lab, qid, extra) {
  const it = curItem(); const cands = new Map(); for (const i of M.person.formsByEnt[it.ent]) for (const c of P.person.forms[i][5] || []) cands.set(c[0], c);
  const c = cands.get(qid) || [];
  patchEnt('person', lab, Object.assign({ d: 'y', qid, wd_label: c[1] || '', wd_description: c[2] || '' }, extra || {}));
  if (!(S.ent.person[lab] || {}).gnd) wdClaims(qid).then(cl => { const g = claimValue(cl, 'P227'); const d = S.ent.person[lab] || {}; if (!g || d.gnd || d.qid !== qid) return;
    S.ent.person[lab] = stampObj(Object.assign({}, d, { gnd: g, gnd_label: g, gnd_info: 'aus Wikidata übernommen' })); save(); if (curItem() === it) renderDetail(); toast('GND aus Wikidata übernommen'); });
}
async function wikidataSearch(q, lab) {
  const box = $('#wres'); box.innerHTML = '<div class="small muted" style="margin-top:6px">suche …</div>';
  try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&origin=*&language=de&uselang=de&type=item&limit=12&search=' + encodeURIComponent(q)); const res = j.search || [];
    box.innerHTML = res.length ? '<div class="res">' + res.map(x => '<div class="r" data-q="' + esc(x.id) + '" data-l="' + esc(x.label || '') + '" data-dd="' + esc(x.description || '') + '"><b>' + esc(x.label || x.id) + '</b> <small>' + esc(x.id) + '</small><br><small>' + esc(x.description || '') + '</small></div>').join('') + '</div>' : '<div class="small muted">Keine Treffer.</div>';
    box.querySelectorAll('.r').forEach(el => el.onclick = () => pickPerson(lab, el.dataset.q, { wd_label: el.dataset.l, wd_description: el.dataset.dd }));
  } catch (e) { box.innerHTML = '<div class="small muted">Wikidata nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
async function gndSearch(q, lab) {
  const box = $('#wres'); box.innerHTML = '<div class="small muted" style="margin-top:6px">suche …</div>';
  try { const j = await getJSON('https://lobid.org/gnd/search?format=json&size=12&filter=type:Person&q=' + encodeURIComponent(q));
    const res = (j.member || []).map(x => ({ id: x.gndIdentifier, name: x.preferredName, info: [[(x.dateOfBirth || [])[0], (x.dateOfDeath || [])[0]].filter(Boolean).join('–'), (x.professionOrOccupation || []).map(p => p.label).slice(0, 3).join(', '), (x.placeOfActivity || []).map(p => p.label).slice(0, 2).join(', ')].filter(Boolean).join(' · ') }));
    box.innerHTML = res.length ? '<div class="res">' + res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.name) + '</b> <small>GND ' + esc(x.id) + '</small><br><small>' + esc(x.info) + '</small></div>').join('') + '</div>' : '<div class="small muted">Keine Treffer.</div>';
    box.querySelectorAll('.r[data-k]').forEach(el => el.onclick = () => { const x = res[+el.dataset.k]; patchEnt('person', lab, { gnd: x.id, gnd_label: x.name, gnd_info: x.info, d: 'y' }); });
  } catch (e) { box.innerHTML = '<div class="small muted">GND-Suche nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
function setPlaceFix(lab, lat, lon, extra) {
  const unc = (extra && extra.uncertainty_m) || +($('#unc') ? $('#unc').value : 1000);
  patchEnt('place', lab, { fix: Object.assign({ lat: (+lat).toFixed(5), lon: (+lon).toFixed(5), osm: '', note: '', qid: '', geonames_id: '' }, extra || {}, { uncertainty_m: unc }), d: 'y' });
}
async function osmSearch(q, lab) {
  const box = $('#nres'); box.innerHTML = '<div class="small muted" style="margin-top:6px">suche …</div>';
  try { const res = await getJSON('https://nominatim.openstreetmap.org/search?format=jsonv2&extratags=1&limit=10&accept-language=de&q=' + encodeURIComponent(q));
    box.innerHTML = res.length ? '<div class="res">' + res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.name || x.display_name.split(',')[0]) + '</b> <small>' + esc(x.category + '/' + x.type) + '</small><br><small>' + esc(x.display_name) + '</small></div>').join('') + '</div>' : '<div class="small muted">Keine Treffer.</div>';
    box.querySelectorAll('.r').forEach(el => { const x = res[+el.dataset.k];
      el.onmouseenter = () => { if (map) { if (map._hover) map.removeLayer(map._hover); map._hover = L.circleMarker([+x.lat, +x.lon], { radius: 8, color: '#1e7a4c', dashArray: '3', fillOpacity: .2 }).addTo(map); } };
      el.onclick = async () => { const unc = ['city', 'town', 'administrative'].includes(x.type) ? 5000 : ['village', 'suburb'].includes(x.type) ? 2000 : 1000;
        const qid = ((x.extratags || {}).wikidata || '').match(/^Q\d+$/) ? x.extratags.wikidata : ''; const g = qid ? claimValue(await wdClaims(qid), 'P1566') || '' : '';
        setPlaceFix(lab, +x.lat, +x.lon, { osm: x.osm_type + '/' + x.osm_id, note: x.display_name.slice(0, 160), uncertainty_m: unc, qid, geonames_id: g }); }; });
  } catch (e) { box.innerHTML = '<div class="small muted">OpenStreetMap-Suche nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
async function placeWikidataSearch(q, lab) {
  const box = $('#nres'); box.innerHTML = '<div class="small muted" style="margin-top:6px">suche …</div>';
  try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&origin=*&language=de&uselang=de&type=item&limit=12&search=' + encodeURIComponent(q)); const res = j.search || [];
    box.innerHTML = res.length ? '<div class="res">' + res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.label || x.id) + '</b> <small>' + esc(x.id) + '</small><br><small>' + esc(x.description || '') + '</small></div>').join('') + '</div>' : '<div class="small muted">Keine Treffer.</div>';
    box.querySelectorAll('.r[data-k]').forEach(el => el.onclick = async () => { const x = res[+el.dataset.k]; const ent = await wdClaims(x.id); const c = claimValue(ent, 'P625'); const g = claimValue(ent, 'P1566');
      const ids = { qid: x.id, geonames_id: g || '', note: (x.label || '') + (x.description ? ', ' + x.description : '') };
      if (c) setPlaceFix(lab, c.latitude, c.longitude, ids); else { const f = (S.ent.place[lab] || {}).fix || {}; patchEnt('place', lab, { fix: Object.assign({}, f, ids), d: 'y' }); toast('Wikidata-Eintrag ohne Koordinaten'); } });
  } catch (e) { box.innerHTML = '<div class="small muted">Wikidata nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
function initMap(it) {
  if (typeof L === 'undefined') { $('#map').outerHTML = '<div class="muted small">Karte nicht verfügbar.</div>'; return; }
  const e = P.place.ent[it.ent]; const lab = e[0]; const fix = (S.ent.place[lab] || {}).fix;
  map = L.map('map', { zoomSnap: .5 });
  const esri = s => 'https://server.arcgisonline.com/ArcGIS/rest/services/' + s + '/MapServer/tile/{z}/{y}/{x}';
  const street = L.tileLayer(esri('World_Street_Map'), { maxZoom: 19, attribution: 'Tiles © Esri, HERE, Garmin, OpenStreetMap' });
  const topo = L.tileLayer(esri('World_Topo_Map'), { maxZoom: 19, attribution: 'Tiles © Esri' });
  const sat = L.tileLayer(esri('World_Imagery'), { maxZoom: 19, attribution: 'Tiles © Esri, Maxar, Earthstar' });
  const basemaps = { 'Straßenkarte': street, 'Topographie': topo, 'Luftbild': sat };
  (basemaps[S.ui.basemap] || street).addTo(map); L.control.layers(basemaps, null, { position: 'topright' }).addTo(map);
  map.on('baselayerchange', ev => { S.ui.basemap = ev.name; save(); });
  const pts = [];
  // context: places of the same entries
  const entries = new Set(it.men.map(i => P.place.men[i][1])); const ctx = new Map();
  for (const f of M.place.formsByEnt[it.ent]) for (const i of M.place.menByForm[f]) entries.add(P.place.men[i][1]);
  P.place.men.forEach(m => { if (!entries.has(m[1])) return; const en = P.place.forms[m[0]][2]; if (en === it.ent) return; const x = P.place.ent[en]; if (x[1] == null) return; const k = en; ctx.set(k, (ctx.get(k) || 0) + 1); });
  const top = [...ctx.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40); const mx = Math.max(1, ...top.map(x => x[1]));
  for (const [en, n] of top) { const x = P.place.ent[en]; L.circleMarker([x[1], x[2]], { radius: 3 + 9 * Math.sqrt(n / mx), color: '#3a6fb0', weight: 1, fillOpacity: .35 }).bindTooltip(esc(x[0]) + ' (' + n + '× gemeinsam)').addTo(map); pts.push([x[1], x[2]]); }
  if (e[1] != null) { const ll = [e[1], e[2]]; if (+e[3]) L.circle(ll, { radius: +e[3], color: '#e0542e', weight: 1, fillOpacity: .06 }).addTo(map);
    L.circleMarker(ll, { radius: 8, color: '#fff', weight: 2, fillColor: '#e0542e', fillOpacity: 1 }).bindTooltip('im Graph: ' + esc(lab)).addTo(map); pts.push(ll); }
  if (fix && fix.lat) { const ll = [+fix.lat, +fix.lon]; L.circle(ll, { radius: +fix.uncertainty_m || 1000, color: '#1e7a4c', weight: 1, fillOpacity: .08 }).addTo(map);
    L.circleMarker(ll, { radius: 8, color: '#fff', weight: 2, fillColor: '#1e7a4c', fillOpacity: 1 }).bindTooltip('Korrektur').addTo(map); pts.push(ll); }
  if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(.25), { maxZoom: 12 }); else map.setView([48.14, 11.58], 8);
  map.on('click', ev => { L.popup().setLatLng(ev.latlng).setContent('<div style="font-size:13px">' + ev.latlng.lat.toFixed(5) + ', ' + ev.latlng.lng.toFixed(5) + '<br><button class="lbtn" id="popset">als Korrektur setzen</button></div>').openOn(map);
    setTimeout(() => { const b = document.getElementById('popset'); if (b) b.onclick = () => setPlaceFix(lab, ev.latlng.lat, ev.latlng.lng, { note: 'auf der Karte gesetzt' }); }, 0); });
}

// ---------- text corrections (Lesung) ----------
function textForm(ei, s, e) {
  const t = E[ei][7]; let a = s, b = e;
  if (a < 0) { a = 0; b = 0; }
  while (a > 0 && /[\p{L}\p{N}\-]/u.test(t[a - 1]) && s - a < 30) a--;
  while (b < t.length && /[\p{L}\p{N}]/u.test(t[b]) && b - e < 30) b++;
  return '<div class="corrform" data-ei="' + ei + '"><div class="cfh">Lesung korrigieren: was steht im Scan?</div>'
    + '<div class="row"><span class="muted small">gelesen</span><input type="text" class="c-old grow" value="' + esc(t.slice(a, b)) + '"><span>→</span><span class="muted small">richtig</span><input type="text" class="c-new grow" placeholder="z. B. Hausrotschwänzchen"></div>'
    + '<div class="small muted">„gelesen“ muss genau so im Eintragstext stehen (bei Bedarf erweitern, z. B. „5 Eis- Gimpel“ → „Stare, Gimpel“). Der Eintrag wird bei der nächsten Extraktion mit der Korrektur neu gelesen; Art, Anzahl, Datum usw. ergeben sich dann neu.</div>'
    + '<div class="row"><input type="text" class="c-note grow" placeholder="Anmerkung (optional)"><button class="dbtn y c-save">Lesung speichern</button><button class="lbtn c-cancel">abbrechen</button></div></div>';
}
function saveText(form) {
  const ei = +form.dataset.ei; const e = E[ei]; const old = form.querySelector('.c-old').value; const nw = form.querySelector('.c-new').value.trim();
  if (!old.trim() || !nw) return toast('Bitte beide Felder ausfüllen');
  if (!e[7].includes(old)) return toast('„gelesen“ steht so nicht im Eintragstext');
  if (old === nw) return toast('Keine Änderung');
  S.text = S.text.filter(c => !(c.entry_uid === e[1] && c.old === old));
  S.text.push(stampObj({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), entry_uid: e[1], entry_id: e[0], old, new: nw, note: form.querySelector('.c-note').value.trim() }));
  save(); renderSide(); toast('Lesung gespeichert'); renderDetail();
}

// ---------- wiring ----------
function wire(t, it) {
  const D = $('#detail');
  D.querySelectorAll('.dbtn[data-d]').forEach(b => b.onclick = () => decide(b.dataset.d));
  D.querySelectorAll('[data-nav]').forEach(b => b.onclick = () => step(+b.dataset.nav));
  const adv = $('#adv'); if (adv) adv.onchange = () => { S.ui.adv = adv.checked; save(); };
  const note = $('#note');
  if (note) note.oninput = () => { clearTimeout(note.t); note.t = setTimeout(() => {
    const store = t.type === 'form' ? S.id[t.kind] : t.type === 'eval' ? S.ev : S.qa; const prev = store[it.key] || { d: '' };
    const o = Object.assign({}, prev, { note: note.value.trim() }); if (!o.d && !o.note) delete store[it.key]; else store[it.key] = stampObj(o); save(); }, 400); };
  const qc = $('#qacorr'); if (qc) qc.oninput = () => { clearTimeout(qc.t); qc.t = setTimeout(() => { const prev = S.qa[it.key] || { d: '' }; S.qa[it.key] = stampObj(Object.assign({}, prev, { corr: qc.value.trim() })); save(); }, 400); };
  D.querySelectorAll('.rpanel').forEach(wirePanel);
  D.querySelectorAll('[data-reason]').forEach(b => b.onclick = () => { const scope = b.closest('[data-scope]').dataset.scope;
    if (scope === 'form') { setForm(t.kind, it, { d: 'n', reason: b.dataset.reason, note: $('#note') ? $('#note').value.trim() : '' }); ui.panel = null; if (S.ui.adv) nextOpen(); else renderDetail(); }
    else setMention(t.kind, +scope, { d: 'n', reason: b.dataset.reason }); });
  D.querySelectorAll('.sib[data-go]').forEach(s => s.onclick = () => { const k = s.dataset.go; if (k === it.key) return; let pos = cur.list.findIndex(i => t.items[i].key === k);
    if (pos < 0) { $('#qshow').value = 'all'; S.ui.chips[t.kind] = TYPE[t.kind].order.slice(); $('#qsearch').value = ''; renderChips(); buildList(); pos = cur.list.findIndex(i => t.items[i].key === k); } if (pos >= 0) select(pos); });
  const ma = $('#menAll'); if (ma) ma.onclick = () => { ui.showAll = !ui.showAll; ui.menPage = 1; renderDetail(); };
  const mm = $('#menMore'); if (mm) mm.onclick = () => { ui.menPage++; renderDetail(); };
  if (t.type === 'form' && t.kind === 'person') {
    const lab = entLabel('person', it.ent);
    D.querySelectorAll('.cand[data-qid]').forEach(c => c.onclick = ev => { if (ev.target.closest('a')) return; pickPerson(lab, c.dataset.qid); });
    $('#wbtn').onclick = () => wikidataSearch($('#wq').value, lab); $('#wq').onkeydown = ev => { if (ev.key === 'Enter') wikidataSearch($('#wq').value, lab); };
    $('#wqidbtn').onclick = () => { const q = ($('#wqid').value.match(/Q\d+/i) || [''])[0].toUpperCase(); if (!q) return toast('Ungültige QID'); pickPerson(lab, q, { wd_label: q, wd_description: 'von Hand eingetragen' }); };
    $('#gndbtn').onclick = () => gndSearch($('#wq').value, lab);
    $('#gndidbtn').onclick = () => { const g = gndId($('#gndid').value); if (!g) return toast('Ungültige GND-ID'); patchEnt('person', lab, { gnd: g, gnd_label: g, gnd_info: 'von Hand eingetragen', d: 'y' }); };
    const gc = $('#gndclear'); if (gc) gc.onclick = () => patchEnt('person', lab, { gnd: null, gnd_label: null, gnd_info: null });
    $('#linkok').onclick = () => { const e = P.person.ent[it.ent]; const a = S.ent.person[lab] || {}; patchEnt('person', lab, { d: 'y', qid: a.qid || e[1] || null, gnd: a.gnd || e[2] || null }); if (S.ui.adv && itemIsCanonical('person', it)) nextOpen(); };
    $('#linkno').onclick = () => { patchEnt('person', lab, { d: 'n', qid: null, gnd: null, wd_label: null, wd_description: null, gnd_label: null, gnd_info: null }); if (S.ui.adv && itemIsCanonical('person', it)) nextOpen(); };
    const lr = $('#linkreset'); if (lr) lr.onclick = () => { delete S.ent.person[lab]; save(); refreshQi(cur.i); renderSide(); renderDetail(); };
  }
  if (t.type === 'form' && t.kind === 'place') {
    const lab = entLabel('place', it.ent); initMap(it);
    $('#nbtn').onclick = () => osmSearch($('#nq').value, lab); $('#nq').onkeydown = ev => { if (ev.key === 'Enter') osmSearch($('#nq').value, lab); };
    $('#pwbtn').onclick = () => placeWikidataSearch($('#nq').value, lab);
    $('#idbtn').onclick = () => { const g = ($('#gnid').value.match(/\d{3,}/) || [''])[0], q = ($('#pqid').value.match(/Q\d+/i) || [''])[0].toUpperCase(); if (!g && !q) return toast('GeoNames-ID oder QID eintragen');
      const f = (S.ent.place[lab] || {}).fix || {}; patchEnt('place', lab, { fix: Object.assign({}, f, { geonames_id: g, qid: q }), d: 'y' }); };
    $('#llbtn').onclick = () => { const m = $('#ll').value.replace(/,(\d)/g, '.$1').match(/(-?\d+(?:\.\d+)?)[\s;,]+(-?\d+(?:\.\d+)?)/); if (!m) return toast('Format: 48.137, 11.575'); setPlaceFix(lab, +m[1], +m[2], { note: 'von Hand eingetragen' }); };
    $('#geook').onclick = () => { patchEnt('place', lab, { d: 'y' }); if (S.ui.adv && itemIsCanonical('place', it)) nextOpen(); };
    $('#geono').onclick = () => { patchEnt('place', lab, { d: 'n', fix: null }); if (S.ui.adv && itemIsCanonical('place', it)) nextOpen(); };
    const gr = $('#georeset'); if (gr) gr.onclick = () => { delete S.ent.place[lab]; save(); refreshQi(cur.i); renderSide(); renderDetail(); };
  }
  const qu = D.querySelector('[data-qaunfix]'); if (qu) qu.onclick = () => { delete S.men.taxon[it.r[1] + '|' + lc(it.r[4]) + '|0']; save(); renderSide(); renderDetail(); };
}
// delegated clicks inside the detail pane: mentions, scans, text corrections
$('#detail').addEventListener('click', e => {
  const sc = e.target.closest('[data-scan]'); if (sc) { const psg = sc.closest('.psg'); const mi = psg && psg.dataset.mi != null ? +psg.dataset.mi : -1; const t = cur.task && cur.task.type === 'form' ? cur.task.kind : 'taxon';
    const loc = mi >= 0 ? P[t].men[mi][4] : null; return openScan(+sc.dataset.scan, Array.isArray(loc) ? loc[0] : null, Array.isArray(loc) && loc.length === 5 ? loc : null); }
  const sn = e.target.closest('.snip'); if (sn) { const psg = sn.closest('.psg'); const mi = +psg.dataset.mi; const t = cur.task.type === 'form' ? cur.task.kind : 'taxon'; const loc = P[t].men[mi][4]; return openScan(+psg.dataset.ei, loc[0], loc); }
  const fu = e.target.closest('[data-full]'); if (fu) { const mi = +fu.dataset.full; ui.fullText = ui.fullText === mi ? null : mi; const psg = fu.closest('.psg'); const t = cur.task.type === 'form' ? cur.task.kind : 'taxon'; const tmp = document.createElement('div'); tmp.innerHTML = menHtml(t, mi, { noActs: cur.task.type === 'eval' }); psg.replaceWith(tmp.firstChild); wireSnips($('#detail')); return; }
  const md = e.target.closest('[data-md]'); if (md) { const psg = md.closest('.psg'); const mi = +psg.dataset.mi; const t = cur.task.kind; const slot = psg.querySelector('.mslot'); const act = md.dataset.md;
    if (act === 'y') return setMention(t, mi, (menDec(t, mi) || {}).d === 'y' ? null : { d: 'y' });
    if (act === 'text') { const m = P[t].men[mi]; slot.innerHTML = slot.innerHTML ? '' : textForm(m[1], m[2], m[3]); const f = slot.querySelector('.c-new'); if (f) f.focus(); return; }
    if (act === 'r') { if (slot.innerHTML) { slot.innerHTML = ''; return; } slot.innerHTML = reassignPanel(t, null, String(mi)); const root = slot.querySelector('.rpanel'); wirePanel(root); root.querySelector('.rq').focus(); return; }
    if (act === 'n') { if (slot.innerHTML) { slot.innerHTML = ''; return; } slot.innerHTML = reasonPanel(t, String(mi)); slot.querySelectorAll('[data-reason]').forEach(b => b.onclick = () => setMention(t, mi, { d: 'n', reason: b.dataset.reason })); return; } }
  const mc = e.target.closest('[data-mclear]'); if (mc) { const mi = +mc.closest('.psg').dataset.mi; return setMention(cur.task.kind, mi, null); }
  const tf = e.target.closest('[data-textfix]'); if (tf) { const psg = tf.closest('.psg'); const slot = psg.querySelector('.mslot'); slot.innerHTML = slot.innerHTML ? '' : textForm(+tf.dataset.textfix, -1, -1); return; }
  if (e.target.closest('.c-save')) return saveText(e.target.closest('.corrform'));
  if (e.target.closest('.c-cancel')) { e.target.closest('.corrform').remove(); return; }
  const dt = e.target.closest('[data-deltext]'); if (dt) { if (!confirm('Lesung entfernen?')) return; S.text = S.text.filter(c => c.id !== dt.dataset.deltext); save(); renderSide(); return cur.task && cur.task.id === 'corr' ? openCorrections() : renderDetail(); }
  const dm = e.target.closest('[data-delmen]'); if (dm) { const [t, k] = dm.dataset.delmen.split('§'); delete S.men[t][k]; save(); renderSide(); return openCorrections(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.closest && e.target.closest('.corrform') && e.target.tagName === 'INPUT') { e.preventDefault(); saveText(e.target.closest('.corrform')); } });

// ---------- keyboard ----------
document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase();
  if (e.key === 'Escape') { if ($('#scanpane').classList.contains('show')) closeScan(); document.querySelectorAll('.ov.show').forEach(o => o.classList.remove('show')); if (tag === 'input' || tag === 'textarea') e.target.blur(); if (ui.panel) { ui.panel = null; renderDetail(); } return; }
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.ctrlKey || e.metaKey || e.altKey) return;
  if ($('#scanpane').classList.contains('show') && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); (e.key === 'ArrowLeft' ? $('#scanprev') : $('#scannext')).click(); return; }
  if (!cur.task || !cur.task.items) return;
  const k = e.key.toLowerCase();
  if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); step(1); }
  else if (k === 'k' || e.key === 'ArrowUp') { e.preventDefault(); step(-1); }
  else if (k === 's') { const b = $('#detail [data-scan]'); if (b) b.click(); }
  else if (k === 'x') decide('');
  else if (e.key === '/') { e.preventDefault(); $('#qsearch').focus(); }
  else if (cur.task.type === 'form') { const map2 = { y: 'y', a: 'r', n: 'n', e: 'e', u: 'u', f: 'x', o: 'o' }; if (map2[k]) { e.preventDefault(); decide(map2[k]); }
    else if (/^[1-9]$/.test(e.key) && cur.task.kind === 'person') { const c = $('#detail .cand[data-qid]:nth-child(' + e.key + ')'); if (c) c.click(); } }
  else if (['y', 'n', 'u'].includes(k)) decide(k);
});

// ---------- export ----------
const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.map(csvCell).join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const SECTION = { taxon: 'taxa', person: 'persons', place: 'places', habitat: 'habitats' };
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
function exportIdentities() {
  const rows = [];
  const base = (t, name, d) => ({ section: SECTION[t], name_form: name, note: d.note || '', reviewed_by: d.by || 'student', reviewed_at: d.t || '' });
  for (const t of TYPES) {
    const m = M[t];
    for (const key in S.id[t]) {
      const d = S.id[t][key]; if (!d.d) continue; const it = m.byName.get(key); const name = it ? it.name : key; const r = base(t, name, d);
      const ent = it ? P[t].ent[it.ent] : null;
      if (t === 'taxon') {
        if (d.d === 'y') Object.assign(r, ent && ent[2] ? { decision: 'same', target: ent[0], authority: 'gbif:' + ent[2], scientific_name: ent[1], rank: ent[3] } : { decision: 'own', target: name });
        else if (d.d === 'r') Object.assign(r, { decision: 'same', target: d.target.label, authority: d.target.key ? 'gbif:' + d.target.key : '', scientific_name: d.target.sci || '', rank: d.target.rank || '' });
        else if (d.d === 'x') Object.assign(r, { decision: 'own', target: name, reason: 'rejected' });
      } else if (t === 'habitat') {
        if (d.d === 'y') Object.assign(r, ent && ent[1] ? { decision: 'link', target: name, authority: 'eunis:' + ent[1], eunis_match: ent[2] } : { decision: 'nolink', target: name });
        else if (d.d === 'r') Object.assign(r, { decision: 'link', target: name, authority: 'eunis:' + d.target.code, eunis_match: d.target.match || 'close' });
        else if (d.d === 'x') Object.assign(r, { decision: 'nolink', target: name });
      } else {
        if (d.d === 'y') Object.assign(r, { decision: 'same', target: ent ? ent[0] : name });
        else if (d.d === 'r') Object.assign(r, { decision: 'same', target: d.target.label });
        else if (d.d === 'o') Object.assign(r, { decision: 'own', target: name });
      }
      if (d.d === 'n') Object.assign(r, { decision: 'none', reason: d.reason || '' });
      else if (d.d === 'e') r.decision = 'mentions';
      else if (d.d === 'u') r.decision = 'unsure';
      if (r.decision) rows.push(r);
    }
  }
  for (const lab in S.ent.person) { const a = S.ent.person[lab]; if (!a.d) continue; const r = base('person', lab, a);
    rows.push(Object.assign(r, a.d === 'y' ? { decision: 'link', target: lab, authority: [a.qid ? 'wd:' + a.qid : '', a.gnd ? 'gnd:' + a.gnd : ''].filter(Boolean).join(' ') } : { decision: 'nolink', target: lab })); }
  for (const lab in S.ent.place) { const a = S.ent.place[lab]; if (!a.d) continue; const r = base('place', lab, a); const f = a.fix || {};
    const ei = M.place.entByLabel.get(lab); const ent = ei != null ? P.place.ent[ei] : null;
    if (a.d === 'y') rows.push(Object.assign(r, { decision: 'link', target: lab, authority: [f.geonames_id || (!f.lat && ent && ent[4]) ? 'gn:' + (f.geonames_id || ent[4]) : '', f.qid || (!f.lat && ent && ent[5]) ? 'wd:' + (f.qid || ent[5]) : '', f.osm ? 'osm:' + f.osm : ''].filter(Boolean).join(' '),
      lat: f.lat || (ent && ent[1] != null ? ent[1] : ''), lon: f.lon || (ent && ent[2] != null ? ent[2] : ''), uncertainty_m: f.uncertainty_m || (ent ? ent[3] : ''), note: [a.note, f.note].filter(Boolean).join(' · ') }));
    else rows.push(Object.assign(r, { decision: 'nolink', target: lab })); }
  return toCSV(ID_HEAD, rows);
}
function exportMentions() {
  const head = ['kind', 'entry_uid', 'entry_id', 'old_value', 'occurrence', 'action', 'new_value', 'scientific_name', 'gbif_key', 'is_bird', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
  const rows = [];
  for (const t of TYPES) for (const k in S.men[t]) { const d = S.men[t][k]; if (d.d !== 'r' && d.d !== 'n') continue; const [uid, name, occ] = k.split('|'); const ei = E.findIndex(e => e[1] === uid);
    const mi = M[t].mByKey.get(k); const written = mi != null ? P[t].forms[P[t].men[mi][0]][0] : (d.written || name);
    rows.push({ kind: t, entry_uid: uid, entry_id: ei >= 0 ? E[ei][0] : '', old_value: written, occurrence: occ || 0, action: d.d === 'r' ? 'replace' : 'drop',
      new_value: d.d === 'r' ? (t === 'habitat' ? d.target.code : d.target.label) : '', scientific_name: d.target ? d.target.sci || '' : '', gbif_key: d.target ? d.target.key || '' : '',
      is_bird: t === 'taxon' ? (d.d === 'n' && d.reason !== 'misread' ? 'n' : 'y') : '', reason: d.reason || '', note: d.note || '', reviewed_by: d.by || 'student', reviewed_at: d.t || '' }); }
  return toCSV(head, rows);
}
function exportText() { return toCSV(['entry_uid', 'entry_id', 'old_text', 'new_text', 'note', 'reviewed_by', 'reviewed_at'], S.text.map(c => ({ entry_uid: c.entry_uid, entry_id: c.entry_id, old_text: c.old, new_text: c.new, note: c.note || '', reviewed_by: c.by || 'student', reviewed_at: c.t || '' }))); }
function exportEval() {
  const head = ['rank', 'entry_id', 'entry_uid', 'name_form', 'occurrence', 'taxon', 'scientific_name', 'gbif_key', 'evidence_class', 'judgement', 'correct_taxon', 'correct_scientific_name', 'note', 'reviewed_by', 'reviewed_at'];
  const lab = { y: 'correct', n: 'wrong', u: 'unclear' };
  return toCSV(head, P.sample.map((mi, k) => { const m = P.taxon.men[mi]; const f = P.taxon.forms[m[0]]; const e = P.taxon.ent[f[2]]; const key = M.taxon.mkey[mi]; const d = S.ev[key] || {};
    return { rank: k + 1, entry_id: E[m[1]][0], entry_uid: E[m[1]][1], name_form: f[0], occurrence: key.split('|')[2], taxon: e[0], scientific_name: e[1], gbif_key: e[2], evidence_class: f[3], judgement: lab[d.d] || '', correct_taxon: d.target ? d.target.label : '', correct_scientific_name: d.target ? d.target.sci || '' : '', note: d.note || '', reviewed_by: d.d ? d.by || 'student' : '', reviewed_at: d.t || '' }; }));
}
function exportQA() {
  const head = P.qa.head.concat(['decision', 'correction', 'review_note', 'reviewed_by', 'reviewed_at']); const lab = { y: 'confirmed', n: 'wrong', u: 'unsure' };
  return toCSV(head, P.qa.rows.map(r => { const k = r[0] + '|' + r[2] + '|' + r[4]; const d = S.qa[k] || {}; const o = {}; P.qa.head.forEach((h, i) => o[h] = r[i]);
    return Object.assign(o, { decision: lab[d.d] || '', correction: d.corr || '', review_note: d.note || '', reviewed_by: d.d ? d.by || 'student' : '', reviewed_at: d.d ? d.t : '' }); }));
}
function exportLog() {
  const rows = [];
  for (const t of TYPES) {
    for (const k in S.id[t]) { const d = S.id[t][k]; rows.push({ scope: 'name', type: t, key: k, decision: d.d, target: d.target ? d.target.label || d.target.code : '', reason: d.reason || '', note: d.note || '', reviewed_by: d.by || '', reviewed_at: d.t || '' }); }
    for (const k in S.men[t]) { const d = S.men[t][k]; rows.push({ scope: 'mention', type: t, key: k, decision: d.d, target: d.target ? d.target.label || d.target.code : '', reason: d.reason || '', note: d.note || '', reviewed_by: d.by || '', reviewed_at: d.t || '' }); }
    for (const k in S.ent[t]) { const d = S.ent[t][k]; rows.push({ scope: 'authority', type: t, key: k, decision: d.d, target: [d.qid, d.gnd, d.fix ? JSON.stringify(d.fix) : ''].filter(Boolean).join(' '), reason: '', note: d.note || '', reviewed_by: d.by || '', reviewed_at: d.t || '' }); }
  }
  for (const c of S.text) rows.push({ scope: 'reading', type: 'text', key: c.entry_id, decision: 'y', target: c.old + ' -> ' + c.new, reason: '', note: c.note || '', reviewed_by: c.by || '', reviewed_at: c.t || '' });
  return toCSV(['scope', 'type', 'key', 'decision', 'target', 'reason', 'note', 'reviewed_by', 'reviewed_at'], rows);
}
function progressJSON() { return JSON.stringify({ app: 'histornigraph-validation', version: 2, export: P.export, who: S.who, saved_at: new Date().toISOString(), id: S.id, men: S.men, ent: S.ent, text: S.text, qa: S.qa, ev: S.ev }, null, 1); }
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = b => { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
function zip(files) {
  const enc = new TextEncoder(); const parts = [], central = []; let off = 0;
  const now = new Date(); const dt = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xFFFF; const dd = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xFFFF;
  for (const [name, text] of files) {
    const nb = enc.encode(name), data = enc.encode(text), crc = crc32(data);
    const h = new DataView(new ArrayBuffer(30)); h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); h.setUint16(8, 0, true); h.setUint16(10, dt, true); h.setUint16(12, dd, true);
    h.setUint32(14, crc, true); h.setUint32(18, data.length, true); h.setUint32(22, data.length, true); h.setUint16(26, nb.length, true); h.setUint16(28, 0, true);
    parts.push(new Uint8Array(h.buffer), nb, data);
    const c = new DataView(new ArrayBuffer(46)); c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true); c.setUint16(10, 0, true); c.setUint16(12, dt, true); c.setUint16(14, dd, true);
    c.setUint32(16, crc, true); c.setUint32(20, data.length, true); c.setUint32(24, data.length, true); c.setUint16(28, nb.length, true); c.setUint32(42, off, true);
    central.push(new Uint8Array(c.buffer), nb); off += 30 + nb.length + data.length;
  }
  const csize = central.reduce((a, b) => a + b.length, 0);
  const e = new DataView(new ArrayBuffer(22)); e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true); e.setUint32(12, csize, true); e.setUint32(16, off, true);
  return new Blob([...parts, ...central, new Uint8Array(e.buffer)], { type: 'application/zip' });
}
function download(name, blob) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/^(\d{8})/, '$1-');
const whoSlug = () => (S.who || 'unbenannt').replace(/[^\p{L}\p{N}]+/gu, '_');
const README = () => 'HistOrniGraph Validierung (Abgleich), Export ' + new Date().toLocaleString('de-DE') + ' von ' + (S.who || '?') + '\nGrundlage: ' + P.export + '\n\n'
  + 'Nach data/review/ im Repository kopieren (Config-Abschnitt review:):\n'
  + '- review/identities.csv: Entscheidungen je Namensform (same/own/none/mentions/unsure) und Normdaten je Entität (link/nolink).\n'
  + '- review/value_corrections.csv: einzeln entschiedene Belege (replace/drop), angewendet direkt nach der Extraktion.\n'
  + '- review/text_corrections.csv: korrigierte Lesungen; diese Einträge werden bei der nächsten Extraktion neu gelesen.\n'
  + '- review/evaluation_taxa.csv: Stichprobe zur Genauigkeit der Artbestimmung (für die Auswertung, nicht für die Pipeline).\n'
  + '- review/qa_flags.csv: Urteile zu den Qualitätsflags (noch nicht von der Pipeline gelesen).\n'
  + 'validation_log.csv: alle Entscheidungen in einer Liste. validation_progress.json: Sicherung für „Fortschritt laden“.\n';
function showExport() {
  const nId = TYPES.reduce((a, t) => a + Object.keys(S.id[t]).length + Object.keys(S.ent[t]).length, 0);
  const nMen = TYPES.reduce((a, t) => a + Object.keys(S.men[t]).length, 0);
  let h = '<button class="lbtn x" data-close>Schließen ✕</button><h2>Exportieren</h2><p>Die Entscheidungen sind nur in diesem Browser gespeichert. Bitte regelmäßig exportieren und die Datei an Tobias schicken (oder in den gemeinsamen Drive-Ordner legen).</p>'
    + '<p><button class="dbtn y" id="exZip">Alles als ZIP herunterladen</button> <button class="dbtn" id="exJson">Nur Sicherung (JSON)</button></p>'
    + '<table><tr><td>Namensformen und Normdaten</td><td>' + fmt(nId) + '</td><td><button class="lbtn" data-ex="id">identities.csv</button></td></tr>'
    + '<tr><td>Einzelne Belege</td><td>' + fmt(nMen) + '</td><td><button class="lbtn" data-ex="men">value_corrections.csv</button></td></tr>'
    + '<tr><td>Lesungen</td><td>' + fmt(S.text.length) + '</td><td><button class="lbtn" data-ex="text">text_corrections.csv</button></td></tr>'
    + '<tr><td>Stichprobe</td><td>' + fmt(Object.keys(S.ev).length) + '</td><td><button class="lbtn" data-ex="eval">evaluation_taxa.csv</button></td></tr>'
    + '<tr><td>Qualitätsflags</td><td>' + fmt(Object.keys(S.qa).length) + '</td><td><button class="lbtn" data-ex="qa">qa_flags.csv</button></td></tr></table>'
    + '<h3>Fortschritt übertragen</h3><p>„Fortschritt laden“ (oben) spielt eine Sicherung wieder ein, auch Sicherungen der alten Oberfläche (Version 1). Bei Konflikten gilt die neuere Entscheidung.</p>';
  $('#exportBody').innerHTML = h; $('#ovExport').classList.add('show');
  const files = () => [['review/identities.csv', exportIdentities()], ['review/value_corrections.csv', exportMentions()], ['review/text_corrections.csv', exportText()], ['review/evaluation_taxa.csv', exportEval()], ['review/qa_flags.csv', exportQA()], ['validation_log.csv', exportLog()], ['validation_progress.json', progressJSON()], ['LIESMICH.txt', README()]];
  $('#exZip').onclick = () => { download('histornigraph_validierung_' + whoSlug() + '_' + stamp() + '.zip', zip(files())); toast('ZIP heruntergeladen'); };
  $('#exJson').onclick = () => download('histornigraph_validierung_' + whoSlug() + '_' + stamp() + '.json', new Blob([progressJSON()], { type: 'application/json' }));
  const one = { id: ['identities.csv', exportIdentities], men: ['value_corrections.csv', exportMentions], text: ['text_corrections.csv', exportText], eval: ['evaluation_taxa.csv', exportEval], qa: ['qa_flags.csv', exportQA] };
  document.querySelectorAll('[data-ex]').forEach(b => b.onclick = () => { const [n, f] = one[b.dataset.ex]; download(n, new Blob([f()], { type: 'text/csv' })); });
}
$('#btnExport').onclick = showExport;
document.querySelectorAll('.ov').forEach(o => o.addEventListener('click', e => { if (e.target === o || e.target.closest('[data-close]')) o.classList.remove('show'); }));

// ---------- import (v2 backups and v1 backups of the pair-review UI) ----------
$('#btnImport').onclick = () => $('#fileImport').click();
async function readZipJSON(buf) {
  const u = new Uint8Array(buf); const dv = new DataView(buf); const dec = new TextDecoder();
  for (let i = 0; i + 30 < u.length;) { if (dv.getUint32(i, true) !== 0x04034b50) break; const size = dv.getUint32(i + 18, true), nl = dv.getUint16(i + 26, true), xl = dv.getUint16(i + 28, true);
    const name = dec.decode(u.subarray(i + 30, i + 30 + nl)); const start = i + 30 + nl + xl; if (name === 'validation_progress.json') return JSON.parse(dec.decode(u.subarray(start, start + size))); i = start + size; }
  throw new Error('keine validation_progress.json im ZIP');
}
function newer(a, b) { return !a || (b.t || '') > (a.t || ''); }
function mergeStore(dst, src) { let n = 0; for (const k in src || {}) if (newer(dst[k], src[k])) { dst[k] = src[k]; n++; } return n; }
function importV1(j) {
  // Pair decisions "variant -> canonical" of the old UI become decisions on the variant name form:
  // "same" (y) always wins; "different" (n) only rejects the variant's current assignment.
  let n = 0; const secT = { taxon_merges: 'taxon', person_merges: 'person', place_merges: 'place', habitat_merges: 'habitat' };
  const known = t => { if (!known[t]) { known[t] = new Set(); P[t].ent.forEach(e => { for (const l of (t === 'place' ? e[8] : t === 'taxon' ? [e[0]] : e[3]) || []) known[t].add(lc(l)); }); } return known[t]; };
  const put = (t, name, o, force) => { const key = lc(name); if (!M[t].byName.has(key) && !known(t).has(key)) return; const cur0 = S.id[t][key];
    if (force || newer(cur0, o)) { S.id[t][key] = o; n++; } };
  const target = (t, c) => { const ci = M[t].byName.get(lc(c)); if (t === 'taxon' && ci) { const e = P.taxon.ent[ci.ent]; return { label: e[0], sci: e[1], key: e[2], rank: e[3] }; } return { label: ci ? entLabel(t, ci.ent) : c }; };
  for (const pass of ['u', 'n', 'y']) {
    for (const task in secT) { const t = secT[task];
      for (const key in (j.dec || {})[task] || {}) { const d = j.dec[task][key]; const m = key.match(/^[^:]+: (.*) -> (.*)$/); if (!m || d.d !== pass) continue; const [, v, c] = m; const it = M[t].byName.get(lc(v));
        const note = [d.note, 'v1: ' + v + ' → ' + c + ' ' + (d.d === 'y' ? 'zusammenführen' : d.d === 'n' ? 'getrennt' : 'unsicher')].filter(Boolean).join(' · ');
        const base = { note, by: d.by, t: d.t };
        const isCurrent = it && lc(entLabel(t, it.ent)) === lc(c);
        if (pass === 'u') put(t, v, Object.assign({ d: 'u' }, base));
        else if (pass === 'n') { if (isCurrent) put(t, v, Object.assign({ d: t === 'taxon' || t === 'habitat' ? 'x' : 'o' }, base), true); }
        else put(t, v, isCurrent ? Object.assign({ d: 'y' }, base) : Object.assign({ d: 'r', target: target(t, c) }, base), true); } }
  }
  for (const [task, l] of Object.entries(j.manual || {})) { const t = secT[task]; if (!t) continue;
    for (const x of l) put(t, x.variant, { d: 'r', target: target(t, x.canonical), note: 'v1: manuell ergänzt', by: x.by, t: x.t }); }
  for (const name in (j.dec || {}).taxon_links || {}) { const d = j.dec.taxon_links[name]; if (!d.d) continue;
    if (d.d === 'y' && d.fix) put('taxon', name, { d: 'r', target: { label: name, sci: d.fix.gbif_canonical_name, key: d.fix.gbif_key, rank: d.fix.gbif_match_type === 'EXACT' ? 'species' : '' }, note: d.note, by: d.by, t: d.t });
    else put('taxon', name, { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'x' : 'u', note: d.note, by: d.by, t: d.t }); }
  for (const name in (j.dec || {}).habitat_links || {}) { const d = j.dec.habitat_links[name]; if (!d.d) continue;
    if (d.d === 'y' && d.fix) put('habitat', name, { d: 'r', target: { code: d.fix.eunis_code, label: d.fix.eunis_code, match: d.fix.match }, note: d.note, by: d.by, t: d.t });
    else put('habitat', name, { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'x' : 'u', note: d.note, by: d.by, t: d.t }); }
  for (const name in (j.dec || {}).person_links || {}) { const d = j.dec.person_links[name]; const it = M.person.byName.get(lc(name)); if (!it || !d.d) continue; const lab = entLabel('person', it.ent);
    const o = { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'n' : 'u', qid: d.qid, wd_label: d.wd_label, wd_description: d.wd_description, gnd: d.gnd, gnd_label: d.gnd_label, gnd_info: d.gnd_info, note: [d.note, 'v1: ' + name].filter(Boolean).join(' · '), by: d.by, t: d.t };
    if (newer(S.ent.person[lab], o)) { S.ent.person[lab] = o; n++; } }
  for (const name in (j.dec || {}).place_links || {}) { const d = j.dec.place_links[name]; const it = M.place.byName.get(lc(name)); if (!it || !d.d) continue; const lab = entLabel('place', it.ent);
    const o = { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'n' : 'u', fix: d.fix, note: d.note, by: d.by, t: d.t }; if (newer(S.ent.place[lab], o)) { S.ent.place[lab] = o; n++; } }
  for (const key in (j.dec || {}).qa_flags || {}) { const d = j.dec.qa_flags[key]; if (newer(S.qa[key], d)) { S.qa[key] = d; n++; } }
  // value corrections: a misread name is a reading (text correction) of that entry, plus the mention decision
  for (const c of j.corr || []) { if (!c.entry_uid) continue; const t = c.kind === 'place' ? 'place' : 'taxon'; const k = c.entry_uid + '|' + lc(c.old) + '|0';
    const o = c.kind === 'taxon' && !c.is_bird ? { d: 'n', reason: 'non-bird', written: c.old, note: [c.note, 'v1: gelesen „' + c.old + '“, richtig „' + c.new + '“'].filter(Boolean).join(' · '), by: c.by, t: c.t }
      : { d: 'r', target: { label: c.new, sci: c.sci || '' }, written: c.old, note: c.note, by: c.by, t: c.t };
    if (newer(S.men[t][k], o)) { S.men[t][k] = o; n++; }
    const e = E.find(x => x[1] === c.entry_uid);
    if (e && e[7].includes(c.old) && !S.text.some(x => x.entry_uid === c.entry_uid && x.old === c.old)) { S.text.push({ id: 'v1' + (c.id || Date.now().toString(36)), entry_uid: c.entry_uid, entry_id: e[0], old: c.old, new: c.new, note: 'aus v1-Wertkorrektur', by: c.by, t: c.t }); n++; } }
  return n;
}
$('#fileImport').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  try {
    const j = /\.zip$/i.test(f.name) ? await readZipJSON(await f.arrayBuffer()) : JSON.parse(await f.text());
    if (j.export && j.export !== P.export && !confirm('Die Sicherung stammt von ' + j.export + ', diese Oberfläche von ' + P.export + '. Trotzdem laden?')) return;
    let n = 0;
    if ((j.version || 1) < 2) n = importV1(j);
    else { for (const k of ['id', 'men', 'ent']) for (const t of TYPES) n += mergeStore(S[k][t], (j[k] || {})[t]); n += mergeStore(S.qa, j.qa); n += mergeStore(S.ev, j.ev);
      for (const c of j.text || []) if (!S.text.some(x => x.id === c.id)) { S.text.push(c); n++; } }
    save(); toast(n + ' Entscheidungen übernommen' + ((j.version || 1) < 2 ? ' (aus Version 1)' : '')); openTask(cur.task && cur.task.items ? cur.task : null);
  } catch (err) { alert('Import fehlgeschlagen: ' + err.message); }
});

// ---------- help ----------
function showHelp() {
  $('#helpBody').innerHTML = '<button class="lbtn x" data-close>Schließen ✕</button><h2>Anleitung</h2>'
    + '<p>Jeder Name, wie er im Tagebuch steht (eine <b>Namensform</b>), ist einer Art, Person, einem Ort oder Lebensraum zugeordnet. Du prüfst diese Zuordnung. Alle Namensformen mit derselben Zuordnung werden im Graph <b>ein</b> Knoten; Zusammenführen ergibt sich also von selbst.</p>'
    + '<h3>Ablauf</h3><ol><li>Namen oben rechts eintragen.</li><li>Links eine Aufgabe wählen. Oben stehen die riskanten Namen, die häufigsten zuerst.</li><li>Belege lesen: Zeilenbild aus dem Scan, darunter die Transkription. Klick auf das Zeilenbild oder „Scan“ öffnet die ganze Seite; bei Einträgen über mehrere Seiten mit ‹ › blättern.</li><li>Entscheiden (Tasten in Klammern), am Ende <b>Exportieren → Alles als ZIP</b>.</li></ol>'
    + '<h3>Entscheidungen zur Namensform</h3><table>'
    + '<tr><td><kbd>Y</kbd> stimmt</td><td>Alle Belege dieses Namens meinen die angezeigte Art/Person/den Ort.</td></tr>'
    + '<tr><td><kbd>A</kbd> andere …</td><td>Der Name meint etwas anderes: suchen und auswählen (Arten auch direkt in GBIF).</td></tr>'
    + '<tr><td><kbd>F</kbd> falsch, offen</td><td>Arten/Lebensräume: Zuordnung falsch, das Richtige ist nicht bestimmbar.</td></tr>'
    + '<tr><td><kbd>O</kbd> eigene</td><td>Personen/Orte: nicht mit der anderen Schreibweise zusammenführen.</td></tr>'
    + '<tr><td><kbd>N</kbd> kein(e) …</td><td>Der Name ist gar keine Vogelart/Person/kein Ort (Lesefehler, anderes Tier, eigentlich ein Ort …).</td></tr>'
    + '<tr><td><kbd>E</kbd> einzeln</td><td>Die Belege meinen Verschiedenes: dann jeden Beleg mit ✓ ↪ ✗ entscheiden.</td></tr>'
    + '<tr><td><kbd>U</kbd> unsicher</td><td>Mit kurzer Anmerkung; wird später besprochen.</td></tr></table>'
    + '<h3>Einzelne Belege und Lesungen</h3><p>Jeder Beleg hat ✓ (stimmt), ↪ (anders zuordnen), ✗ (keine Art …) und ✎ (Lesung korrigieren). Eine Entscheidung am Beleg gilt nur dort und geht der Entscheidung zur Namensform vor.</p>'
    + '<p><b>✎ Lesung korrigieren</b> ist der richtige Weg bei Lesefehlern der Transkription: im Feld „gelesen“ steht der Text, rechts trägst du ein, was im Scan steht (z. B. „Kameradeneingänge“ → „Hausrotschwänzchen“, „5 Eis- Gimpel“ → „Stare, Gimpel“, „8. Mai“ → „9. Mai“). Der Eintrag wird bei der nächsten Extraktion neu gelesen, dabei ergeben sich Art, Anzahl, Ort und Datum neu. So braucht es kein „Aufteilen“ oder „Verschieben“ von Hand.</p>'
    + '<h3>Richtlinien für Arten</h3><ul>'
    + '<li><b>Zusammenführen heißt: dieselbe biologische Art</b>, nicht dasselbe Wort. Historische Namen (Dompfaff = Gimpel, Schwarzdrossel = Amsel, Weidenlaubvogel = Zilpzalp) und regionale Namen (Hausamsel, Schwarzamsel) sind dieselbe Art: <kbd>Y</kbd>. Der geschriebene Name bleibt im Graph erhalten (dwc:verbatimIdentification).</li>'
    + '<li><b>Farb- und Zusatzwörter</b>: Beschreibt der Zusatz nur das Aussehen (Schwarzamsel, alter Hahn), gilt die Art. Bezeichnet er eine eigene Unterart oder Form (Trauerbachstelze = <i>Motacilla alba yarrellii</i>), diese über ↪ wählen. Im Zweifel die Art wählen und eine Anmerkung schreiben. Wie oft ein Name vorkommt, spielt für die Entscheidung keine Rolle.</li>'
    + '<li><b>Lesefehler</b> (Trink, Tirol-Wort, Kameradeneingang) sind nie Synonyme. Wenn alle Belege denselben Fehler zeigen: Lesung korrigieren oder <kbd>N</kbd> „Lesefehler“. Wenn die Belege verschieden sind (Tirol mal Ort, mal verlesener Pirol): <kbd>E</kbd> und einzeln entscheiden.</li>'
    + '<li><b>Nest, Ei, Feder</b> einer Art zählen als Nachweis dieser Art (Gimpel-Nest → Gimpel).</li>'
    + '<li><b>Nur Gattung oder Familie</b> genannt (Möwe, Ente, Specht): die Gattung/Familie über ↪ „in GBIF suchen“ wählen, nicht eine beliebige Art.</li></ul>'
    + '<h3>Personen und Orte</h3><ul><li>Kurzformen (W. Wüst, Dr. Wüst) nur zuordnen, wenn der Zusammenhang eindeutig ist; sonst <kbd>O</kbd> oder <kbd>E</kbd>. „Frau X“ ist nicht „Herr X“.</li>'
    + '<li>Normdaten gehören zur Person bzw. zum Ort (unten in der Karte): Wikidata-Kandidat wählen oder suchen; GND wird aus Wikidata übernommen, wenn vorhanden.</li>'
    + '<li>Orte: ähnliche Schreibweise heißt nicht gleicher Ort (Hagenau/Hagnau). Kleine Örtlichkeiten ohne Gazetteer-Eintrag (Isarbrücke, Ruinenwiese): ungefähre Lage auf der Karte setzen und die Unsicherheit wählen.</li></ul>'
    + '<h3>Stichprobe</h3><p>Zufällig gezogene Belege über alle Bände. Nur beurteilen, ob die Art an dieser Stelle richtig bestimmt ist. Daraus wird die Genauigkeit der Artbestimmung mit Vertrauensintervall berechnet. Bitte nicht nach Belieben auswählen, sondern der Reihe nach.</p>'
    + '<h3>Tastatur</h3><table><tr><td><kbd>J</kbd> <kbd>K</kbd> / <kbd>↓</kbd> <kbd>↑</kbd></td><td>weiter / zurück</td></tr><tr><td><kbd>S</kbd></td><td>Scan des ersten Belegs</td></tr><tr><td><kbd>←</kbd> <kbd>→</kbd></td><td>Seiten im Scan</td></tr><tr><td><kbd>X</kbd></td><td>zurücksetzen</td></tr><tr><td><kbd>/</kbd></td><td>Suche</td></tr><tr><td><kbd>Esc</kbd></td><td>Scan/Fenster schließen</td></tr></table>'
    + '<h3>Speichern</h3><p>Automatisch im Browser, nur auf diesem Rechner. Regelmäßig exportieren; „Fortschritt laden“ spielt eine Sicherung wieder ein (auch aus der alten Oberfläche).</p>';
  $('#ovHelp').classList.add('show');
}
$('#btnHelp').onclick = showHelp;
$('#btnTheme').onclick = () => { const r = document.documentElement; const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; r.dataset.theme = dark ? 'light' : 'dark'; S.ui.theme = r.dataset.theme; save(); };
if (S.ui.theme) document.documentElement.dataset.theme = S.ui.theme;
window.__hog = { P, S, M, openTask, TBY, openScan, exportIdentities, exportMentions, exportText, exportEval, importV1 };

// ---------- start ----------
$('#loading').remove();
openTask(S.ui.task && TBY[S.ui.task] ? TBY[S.ui.task] : null);
if (!S.who) setTimeout(showHelp, 300);
})();
