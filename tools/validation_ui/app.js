(async function () {
'use strict';
// Laubmann-Abgleich (v3). One entity at a time: its authority record, the names the diary uses for it,
// and the mentions with their line of the scan. Same four actions everywhere: ✓ stimmt · ↪ anders · ✗ keine/r · ? unsicher.

// ---------------------------------------------------------------- utils
const $ = s => document.querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = n => Number(n || 0).toLocaleString('de-DE');
const pct = x => (100 * (x || 0)).toLocaleString('de-DE', { maximumFractionDigits: 1 }) + ' %';
const lc = s => String(s || '').toLowerCase();
const fold = s => lc(s).normalize('NFC').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
const LS = 'hog-validation-v2';
function toast(msg, ms) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), ms || 2400); }

// ---------------------------------------------------------------- payload
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
catch (e) { $('#loading').textContent = 'Die Daten konnten nicht geladen werden. Bitte Chrome, Edge oder Firefox (aktuell) verwenden. (' + e.message + ')'; return; }
let DRIVE = {};
try { DRIVE = JSON.parse($('#drive').textContent || '{}'); } catch (e) { DRIVE = {}; }
const E = P.E;      // [id, uid, date, vdate, kind, vol, place, text, [page idx], location_raw]
const PG = P.PG;    // [page_id, vol, scan, side, printed number, w, h]
const SUG = P.sug || {};
const EUNIS = new Map(P.eunis.map(e => [e[0], e]));
const uid2e = new Map(E.map((e, i) => [e[1], i]));
$('#exportname').textContent = P.export;

// ---------------------------------------------------------------- state, persistence, undo
const TYPES = ['taxon', 'person', 'place', 'habitat'];
let S = { who: '', id: {}, men: {}, ent: {}, text: [], qa: {}, ev: {}, ui: {} };
try { const raw = localStorage.getItem(LS); if (raw) S = Object.assign(S, JSON.parse(raw)); } catch (e) { }
function normalizeState() {
  for (const k of ['id', 'men', 'ent']) { S[k] = S[k] || {}; for (const t of TYPES) S[k][t] = S[k][t] || {}; }
  S.text = S.text || []; S.qa = S.qa || {}; S.ev = S.ev || {}; S.ui = S.ui || {};
  S.ui.adv = S.ui.adv !== false; S.ui.follow = S.ui.follow !== false; S.ui.sel = S.ui.sel || {}; S.ui.show = S.ui.show || {}; S.ui.sort = S.ui.sort || {}; S.ui.chips = S.ui.chips || {};
}
normalizeState();
const stampObj = o => Object.assign({}, o, { by: S.who || '', t: new Date().toISOString() });
let saveTimer = null, dirty = 0, lastFile = null, fileHandle = null;
function save() {
  clearTimeout(saveTimer); dirty++;
  saveTimer = setTimeout(async () => {
    try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { toast('Speichern im Browser nicht möglich: bitte „Sichern & Export“ benutzen', 5000); }
    if (fileHandle) { try { const w = await fileHandle.createWritable(); await w.write(progressJSON()); await w.close(); lastFile = new Date(); dirty = 0; } catch (e) { fileHandle = null; } }
    savedLabel();
  }, 400);
}
function savedLabel() {
  const el = $('#saved'); const time = d => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  if (fileHandle && lastFile) { el.textContent = 'in Datei gesichert ' + time(lastFile); el.className = 'saved'; el.title = 'Jede Entscheidung wird automatisch in die gewählte Datei geschrieben.'; }
  else { el.textContent = dirty > 40 ? 'Bitte sichern (' + dirty + ' ungesichert)' : 'im Browser gespeichert'; el.className = 'saved' + (dirty > 40 ? ' warn' : ''); el.title = 'Die Entscheidungen liegen im Browser. „Sichern & Export“ legt eine Sicherung an.'; }
}
const HIST = [];
function snapshot() { return JSON.stringify({ id: S.id, men: S.men, ent: S.ent, text: S.text, qa: S.qa, ev: S.ev }); }
function commit(label, fn) {
  HIST.push([label, snapshot()]); if (HIST.length > 120) HIST.shift();
  fn(); save(); refresh();
}
function undo() {
  const h = HIST.pop(); if (!h) return toast('Nichts rückgängig zu machen');
  Object.assign(S, JSON.parse(h[1])); normalizeState(); save(); refresh(); toast('Rückgängig: ' + h[0]);
}

// ---------------------------------------------------------------- vocabulary
const TT = {
  taxon: { tab: 'Arten', one: 'Art', unit: 'Belege',
    cls: { A: ['belegter Name', 'ok', 'Deutscher Name dieser Art laut GBIF oder Wikidata (auch historische Namen).'], B: ['Variante', 'info', 'Schreib- oder Wortvariante eines belegten Namens.'],
      C: ['unbelegt', 'risk', 'Kein belegter Name dieser Art: oft ein Lesefehler oder ein seltener Volksname.'], L: ['ohne GBIF-Art', 'warn', 'Keiner GBIF-Art zugeordnet.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['non-bird', 'anderes Tier oder Pflanze'], ['place', 'eigentlich ein Ort'], ['person', 'eigentlich eine Person'], ['other', 'sonstiges']] },
  person: { tab: 'Personen', one: 'Person', unit: 'Nennungen',
    cls: { V: ['zugeordnet', 'warn', 'Automatisch dieser Person zugeordnet (Kurzform, Initiale, Nachname).'], K: ['voller Name', 'plain', 'Voller Name.'], W: ['verknüpft', 'ok', 'Mit Wikidata oder GND verknüpft.'], E: ['nur ein Namensteil', 'plain', 'Einzelner Name, keiner Person zugeordnet.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['place', 'eigentlich ein Ort'], ['taxon', 'eigentlich ein Vogel'], ['other', 'sonstiges (Institution, Zeitschrift …)']] },
  place: { tab: 'Orte', one: 'Ort', unit: 'Nennungen',
    cls: { V: ['zugeordnet', 'warn', 'Einem ähnlich geschriebenen Ort zugeordnet.'], R: ['Lage prüfen', 'warn', 'Unsichere Georeferenz.'], N: ['ohne Lage', 'warn', 'Keine Koordinate gefunden.'], G: ['mit Lage', 'ok', 'Automatisch georeferenziert.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['generic', 'kein Ortsname (Wald, See, Garten …)'], ['taxon', 'eigentlich ein Vogel'], ['person', 'eigentlich eine Person'], ['habitat', 'eigentlich ein Lebensraum'], ['other', 'sonstiges']] },
  habitat: { tab: 'Lebensräume', one: 'Lebensraum', unit: 'Beobachtungen',
    cls: { V: ['Variante', 'info', 'Schreibvariante.'], R: ['prüfen', 'warn', 'Unsichere EUNIS-Klasse.'], N: ['ohne Klasse', 'warn', 'Keine EUNIS-Klasse.'], E: ['mit Klasse', 'ok', 'Automatisch einer EUNIS-Klasse zugeordnet.'] },
    not: [['misread', 'Lesefehler / kein Lebensraum'], ['place', 'eigentlich ein Ort'], ['other', 'sonstiges']] },
};
const KIND_DE = { 'field-day': 'Feldtag', 'species-digest': 'Artenübersicht', 'third-party-report': 'Fremdbericht', other: 'sonstiges', correspondence: 'Korrespondenz' };
const QA_DE = {
  non_bird: ['Kein Vogel', 'Die Beobachtung wurde entfernt, weil das Modell das Tier nicht als Vogel eingestuft hat.'],
  low_confidence_taxon: ['Unsichere Art', 'Die Beobachtung wurde entfernt: Artname nicht auflösbar, Konfidenz niedrig.'],
  date_year_corrected: ['Jahr korrigiert', 'Das Jahr wurde aus der Bandabdeckung oder den Nachbareinträgen korrigiert.'],
  date_from_position: ['Datum aus Position', 'Das Datum wurde aus der Position im Band erschlossen.'],
  date_out_of_coverage: ['Datum außerhalb des Bandes', 'Das Datum liegt außerhalb des Zeitraums, den der Band abdeckt.'],
  date_corrected: ['Datum korrigiert', 'Das Modell hat das Eintragsdatum geändert.'],
  nonplace: ['Kein Ort', 'Die Kopfzeile enthält laut Modell keinen verwertbaren Ort.'],
  record_type_conflict: ['Beobachtungstyp widersprüchlich', 'Eigene Beobachtung, obwohl Beobachter oder Zitat genannt ist.'],
  volume_reassigned: ['Band neu zugeordnet', 'Die Seite wurde einem anderen Band zugeordnet.'],
  duplicate_entry: ['Doppelter Eintrag', 'Eintrag wurde als Dublette entfernt.'],
  date_out_of_span: ['Datum außerhalb der Tagebuchzeit', 'Eintrag entfernt, das Jahr liegt außerhalb von 1917–1965.'],
  implausible_date: ['Ungültiges Datum', 'Eintrag entfernt, das Datum ist ungültig.'],
  no_observations: ['Keine Vogelbeobachtung', 'Eintrag ohne Vogelnachweis, aber mit Wetter oder Reise.'],
  empty: ['Leerer Eintrag', 'Keine Beobachtung extrahiert (möglicherweise Segmentierungsfehler).'],
};
const QA_DEFAULT = Object.keys(QA_DE).filter(k => !['no_observations', 'empty', 'date_corrected'].includes(k));
const TABS = [
  { id: 'taxon', label: 'Arten', kind: 'ent' }, { id: 'person', label: 'Personen', kind: 'ent' }, { id: 'place', label: 'Orte', kind: 'ent' }, { id: 'habitat', label: 'Lebensräume', kind: 'ent' },
  { id: 'eval', label: 'Stichprobe', kind: 'eval' }, { id: 'qa', label: 'Hinweise', kind: 'qa' }, { id: 'log', label: 'Änderungen', kind: 'log' },
];
const TAB = Object.fromEntries(TABS.map(t => [t.id, t]));

// ---------------------------------------------------------------- model
const X = {};
for (const t of TYPES) {
  const sec = P[t];
  const names = sec.forms.map((f, fi) => ({ t, fi, name: f[0], key: lc(f[0]), n: f[1], ent: f[2], cls: f[3], f, men: [] }));
  sec.men.forEach((m, i) => names[m[0]].men.push(i));
  const ents = sec.ent.map((e, i) => ({ t, i, label: e[0], e, names: [], n: 0 }));
  for (const nm of names) { ents[nm.ent].names.push(nm); ents[nm.ent].n += nm.n; }
  const occ = new Map(); const mkey = new Array(sec.men.length);
  sec.men.forEach((m, i) => { const k = E[m[1]][1] + '|' + lc(sec.forms[m[0]][0]); const n = occ.get(k) || 0; occ.set(k, n + 1); mkey[i] = k + '|' + n; });
  const byKey = new Map(); for (const nm of names) { if (!byKey.has(nm.key)) byKey.set(nm.key, []); byKey.get(nm.key).push(nm); }
  X[t] = { sec, names, ents, mkey, mByKey: new Map(mkey.map((k, i) => [k, i])), byKey, entByLabel: new Map(ents.map(e => [e.label, e.i])) };
}
const ENT = (t, i) => X[t].ents[i];
const isLabel = (t, nm) => nm.key === lc(ENT(t, nm.ent).label);
const TITLES = /\b(dr|prof|herr|hr|frau|fr|frl|fraeulein|lehrer|oberlehrer|pfarrer|oberfoerster|foerster|forstmeister|cand|phil|med|rer|nat|stud|ing)\b\.?/g;
const pkey = n => fold(n).replace(/\?/g, '').replace(TITLES, ' ').replace(/[^a-z]/g, '');
function safeName(t, nm) {
  if (isLabel(t, nm)) return true;
  if (t === 'taxon') return nm.cls === 'A';
  // persons: only the same name without titles ("Dr. Walter Wüst" = "Walter Wüst"); rule chains are not safe
  if (t === 'person') return pkey(nm.name) === pkey(ENT(t, nm.ent).label);
  return (nm.f[4] || '') === 'orthographic';
}
// model second reading: does it contradict the current assignment?
function lev(a, b) {
  if (a === b) return 0; if (!a.length || !b.length) return a.length || b.length;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) { const row = [i]; for (let j = 1; j <= b.length; j++) row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = row; }
  return prev[b.length];
}
const letters = s => fold(s).replace(/[^a-z]/g, '');
// same word up to inflection ("Wildente"/"Wildenten") and small spelling noise
function sameWord(a, b) { a = letters(a); b = letters(b); if (a === b) return true; if ((a.startsWith(b) || b.startsWith(a)) && Math.abs(a.length - b.length) <= 3) return true; return lev(a, b) <= Math.max(1, Math.floor(Math.min(a.length, b.length) * 0.12)); }
function sugDiffers(mi) {
  const s = SUG[mi]; if (!s) return false;
  const m = P.taxon.men[mi]; const cur = P.taxon.forms[m[0]][2]; const ce = P.taxon.ent[cur];
  if (s[2] && s[2] !== 'bird') return true;
  if (s[7] >= 0) return s[7] !== cur;
  if (!s[4] && !s[3]) return false;
  const names = [ce[0], ...ce[9]]; const sci = letters(ce[1]);
  const binom = x => lc(x).split(/\s+/).slice(0, 2).join(' ');
  if (s[4] && ce[1] && binom(s[4]) === binom(ce[1])) return false;
  if (s[3] && names.some(n => sameWord(n, s[3]))) return false;
  return true;
}
function sugReads(mi) { const s = SUG[mi]; if (!s || s[1]) return false; const m = P.taxon.men[mi]; const w = m[2] >= 0 ? E[m[1]][7].slice(m[2], m[3]) : P.taxon.forms[m[0]][0]; return !sameWord(s[0], w); }
// issues, priority, review set
for (const t of TYPES) for (const e of X[t].ents) {
  const iss = new Set(); let risk = 0; const x = e.e;
  e.names.sort((a, b) => (safeName(t, a) - safeName(t, b)) || b.n - a.n);
  if (t === 'taxon') {
    for (const nm of e.names) { if (nm.cls === 'C') { iss.add('C'); risk += nm.n * 3; } else if (nm.cls === 'B') { iss.add('B'); risk += nm.n; } }
    if (!x[2]) { iss.add('L'); risk += e.n * 2; }
    if (/llm/.test(x[5] || '')) { iss.add('llm'); risk += e.n * 0.5; }
    if (x[4] === 'HIGHERRANK' || ['genus', 'family', 'group'].includes(x[3])) iss.add('higher');
    const nd = e.names.reduce((a, nm) => a + nm.men.filter(sugDiffers).length, 0); if (nd) { iss.add('sug'); risk += nd * 20; e.sugN = nd; }
    if (e.n >= 50) iss.add('top');
  } else if (t === 'person') {
    for (const nm of e.names) if (!safeName(t, nm)) { iss.add('V'); risk += nm.n * 2; }
    if (x[1] || x[2]) { iss.add('auto'); risk += e.n; }
    else if (e.n >= 3) { iss.add('nolink'); risk += e.n * 0.5; }
  } else if (t === 'place') {
    for (const nm of e.names) if (!safeName(t, nm)) { iss.add('V'); risk += nm.n * 2; }
    const st = (e.names.find(nm => isLabel(t, nm)) || e.names[0] || { f: [] }).f[5] || [];
    if (st[0] === 'review') { iss.add('R'); risk += e.n; }
    if (x[1] == null && e.n >= 2) { iss.add('N'); risk += e.n; }
    if (x[1] != null && e.n >= 10) { iss.add('top'); risk += e.n * 0.2; }
  } else {
    for (const nm of e.names) if (!safeName(t, nm)) { iss.add('V'); risk += nm.n * 2; }
    const lr = e.names.length ? (e.names[0].f[5] || []) : [];
    if (lr[0] === 'review') { iss.add('R'); risk += e.n; }
    if (!x[1]) { iss.add('N'); risk += e.n; }
    if (x[1] && e.n >= 20) { iss.add('top'); risk += e.n * 0.2; }
  }
  e.iss = iss; e.risk = risk; e.review = risk > 0 && e.names.length > 0;
}
const ISSUE = {
  taxon: { sug: ['Zweitlesung widerspricht', 'tip'], C: ['unbelegte Namen', 'risk'], L: ['ohne GBIF-Art', 'warn'], B: ['Varianten', 'info'], llm: ['vom Modell bestimmt', 'info'], higher: ['Gattung/Familie', 'plain'], top: ['häufig', 'plain'] },
  person: { V: ['zugeordnete Namen', 'warn'], auto: ['automatisch verknüpft', 'info'], nolink: ['ohne Normdaten', 'plain'] },
  place: { V: ['zugeordnete Namen', 'warn'], R: ['Lage prüfen', 'warn'], N: ['ohne Lage', 'warn'], top: ['häufig', 'plain'] },
  habitat: { V: ['Varianten', 'warn'], R: ['Klasse prüfen', 'warn'], N: ['ohne Klasse', 'warn'], top: ['häufig', 'plain'] },
};

// ---------------------------------------------------------------- decisions and states
const entDec = (t, e) => S.ent[t][e.label];
const nameDec = (t, nm) => S.id[t][nm.key];
function readingFor(ei) { return S.text.filter(c => c.entry_uid === E[ei][1]); }
function menReading(t, mi) {
  const m = P[t].men[mi]; if (m[2] < 0) return null; const text = E[m[1]][7];
  return readingFor(m[1]).find(c => { const i = text.indexOf(c.old); return i >= 0 && i < m[3] && i + c.old.length > m[2]; }) || null;
}
function menState(t, mi) { const d = S.men[t][X[t].mkey[mi]]; if (d && d.d) return d.d; return menReading(t, mi) ? 't' : ''; }
function nameState(t, nm) {
  const d = nameDec(t, nm); if (d && d.d && d.d !== 'e') return d.d;
  if (nm.men.length && nm.men.every(mi => menState(t, mi))) return 'm';
  const ed = entDec(t, ENT(t, nm.ent));
  if (ed && ed.d) { if (ed.d === 'y' && safeName(t, nm)) return 'y'; if ((t === 'taxon' || t === 'habitat') && (ed.d === 'r' || ed.d === 'n')) return 'f'; }
  return '';
}
function entState(t, e) {
  const ed = entDec(t, e);
  if (ed && ed.d === 'u') return 'u';
  let open = 0, changed = !!(ed && (ed.d === 'r' || (t === 'taxon' && ed.d === 'n') || (ed.fix && ed.d === 'y') || (t === 'person' && ed.d === 'y' && ed.qid && ed.qid !== e.e[1]))), any = !!(ed && ed.d);
  for (const nm of e.names) { const s = nameState(t, nm); if (!s) open++; else { any = true; if (['r', 'o', 'x', 'n', 'm'].includes(s)) changed = true; } if (s === 'u') return 'u'; }
  if (ed && ed.d && !open) return changed ? 'r' : 'y';
  if (!open && e.names.length && e.names.every(nm => ['r', 'o', 'x', 'n'].includes(nameState(t, nm)))) return 'r';
  return any ? 'p' : '';
}
const DONE = s => s === 'y' || s === 'r';
const linked = (t, e) => t === 'taxon' ? !!e.e[2] : t === 'person' ? !!(e.e[1] || e.e[2]) : t === 'place' ? e.e[1] != null : !!e.e[1];
const STATE_DE = { y: 'bestätigt', r: 'korrigiert', n: 'abgelehnt', u: 'unsicher', p: 'begonnen', '': 'offen' };
const NSTATE = { y: ['✓ stimmt', 'ok'], r: ['↪ neu zugeordnet', 'info'], o: ['↪ eigene', 'info'], x: ['↪ nicht bestimmbar', 'info'], n: ['✗ kein Eintrag', 'risk'], u: ['? unsicher', 'warn'], m: ['Belege einzeln entschieden', 'mix'], f: ['folgt dem Eintrag', 'info'] };

// ---------------------------------------------------------------- tabs and queue
let cur = { tab: S.ui.tab && TAB[S.ui.tab] ? S.ui.tab : 'taxon', list: [], shown: 0, sel: null, pos: -1, focus: 'e' };
const ui = { open: new Set(), all: new Set(), panel: null, full: new Set(), mapView: null };
const qaKey = r => r[0] + '|' + r[2] + '|' + r[4];
function tabCount(tab) {
  if (TYPES.includes(tab)) return X[tab].ents.filter(e => e.names.length && linked(tab, e) && !DONE(entState(tab, e))).length;
  if (tab === 'eval') return P.sample.filter(mi => !(S.ev[X.taxon.mkey[mi]] || {}).d).length;
  if (tab === 'qa') return P.qa.rows.filter(r => QA_DEFAULT.includes(r[2]) && !(S.qa[qaKey(r)] || {}).d).length;
  return '';
}
function renderTabs() {
  $('#tabs').innerHTML = TABS.map(t => { const c = tabCount(t.id); return '<button class="tab' + (cur.tab === t.id ? ' on' : '') + '" data-tab="' + t.id + '">' + esc(t.label) + (c !== '' ? '<span class="c">' + fmt(c) + '</span>' : '') + '</button>'; }).join('');
}
$('#tabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) openTab(b.dataset.tab); });
function tabItems(tab) {
  if (TYPES.includes(tab)) return X[tab].ents;
  if (tab === 'eval') { if (!tabItems.ev) tabItems.ev = P.sample.map((mi, k) => ({ mi, k, key: X.taxon.mkey[mi], ei: P.taxon.men[mi][1] })); return tabItems.ev; }
  if (tab === 'qa') { if (!tabItems.qa) { const ord = ['non_bird', 'low_confidence_taxon', 'date_out_of_span', 'implausible_date', 'date_year_corrected', 'date_from_position', 'date_out_of_coverage', 'nonplace', 'record_type_conflict', 'duplicate_entry', 'volume_reassigned', 'date_corrected', 'no_observations', 'empty'];
    tabItems.qa = P.qa.rows.map((r, i) => ({ r, i, ei: P.qa.ei[i], key: qaKey(r) })).sort((a, b) => (ord.indexOf(a.r[2]) + 99) % 99 - (ord.indexOf(b.r[2]) + 99) % 99 || a.r[0].localeCompare(b.r[0])); } return tabItems.qa; }
  return [];
}
function itemState(tab, it) {
  if (TYPES.includes(tab)) return entState(tab, it);
  if (tab === 'eval') { const d = S.ev[it.key]; return d && d.d ? ({ y: 'y', n: 'r', u: 'u' }[d.d]) : ''; }
  if (tab === 'qa') { const d = S.qa[it.key]; return d && d.d ? ({ y: 'y', n: 'r', u: 'u' }[d.d]) : ''; }
  return '';
}
const selKey = it => it.key != null ? it.key : it.t + ':' + it.i;
function openTab(tab, keepSel) {
  cur.tab = tab; S.ui.tab = tab; ui.panel = null; renderTabs();
  const kind = TAB[tab].kind;
  $('#main').classList.toggle('noscan', kind === 'log' || S.ui.noscan === true);
  if (kind === 'log') { $('#qtitle').textContent = 'Änderungen'; $('#qcount').textContent = ''; $('#pbar').innerHTML = ''; $('#pnote').textContent = ''; $('.qctl').style.display = 'none'; $('#qsearch').style.display = 'none'; $('#qchips').innerHTML = ''; $('#qlist').innerHTML = '<div class="qmore">Alle Entscheidungen stehen rechts.</div>'; cur.sel = null; renderLog(); return; }
  $('.qctl').style.display = ''; $('#qsearch').style.display = '';
  const shows = kind === 'ent' ? [['check', '1 · Prüfen: schon verknüpft'], ['link', '2 · Verknüpfen: ohne Normdaten'], ['open', 'Alle offenen'], ['done', 'Erledigt'], ['u', 'Unsicher'], ['all', 'Alle']] : [['open', 'Offen'], ['done', 'Erledigt'], ['u', 'Unsicher'], ['all', 'Alle']];
  $('#qshow').innerHTML = shows.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('');
  $('#qshow').value = S.ui.show[tab] && shows.some(s => s[0] === S.ui.show[tab]) ? S.ui.show[tab] : shows[0][0];
  const sorts = kind === 'ent' ? [['prio', 'Wichtigste zuerst'], ['n', 'Häufigste zuerst'], ['alpha', 'Alphabetisch']] : [['order', 'Reihenfolge']];
  $('#qsort').innerHTML = sorts.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('');
  $('#qsort').value = S.ui.sort[tab] && sorts.some(s => s[0] === S.ui.sort[tab]) ? S.ui.sort[tab] : sorts[0][0];
  $('#qsearch').value = '';
  renderChips(); buildList();
  const want = keepSel != null ? keepSel : S.ui.sel[tab];
  const pos = want != null ? cur.list.findIndex(it => selKey(it) === want) : -1;
  if (pos < 0 && want != null) { const it = tabItems(tab).find(x => selKey(x) === want); if (it) { selectItem(it); return; } }
  selectPos(pos >= 0 ? pos : cur.list.length ? 0 : -1);
}
function renderChips() {
  const tab = cur.tab;
  if (TYPES.includes(tab)) {
    const on = new Set(S.ui.chips[tab] || []); const cnt = {};
    for (const e of X[tab].ents) if (e.review) for (const k of e.iss) cnt[k] = (cnt[k] || 0) + 1;
    $('#qchips').innerHTML = Object.entries(ISSUE[tab]).filter(([k]) => cnt[k]).map(([k, [l]]) => '<span class="chip' + (on.has(k) ? ' on' : '') + '" data-c="' + k + '">' + esc(l) + ' ' + fmt(cnt[k]) + '</span>').join('');
  } else if (tab === 'qa') {
    const on = new Set(S.ui.chips.qa || QA_DEFAULT); const cnt = {}; for (const r of P.qa.rows) cnt[r[2]] = (cnt[r[2]] || 0) + 1;
    $('#qchips').innerHTML = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a]).map(k => '<span class="chip' + (on.has(k) ? ' on' : '') + '" data-c="' + k + '" title="' + esc((QA_DE[k] || [])[1] || '') + '">' + esc((QA_DE[k] || [k])[0]) + ' ' + fmt(cnt[k]) + '</span>').join('');
  } else $('#qchips').innerHTML = '';
}
$('#qchips').addEventListener('click', e => {
  const c = e.target.closest('.chip'); if (!c) return; const tab = cur.tab;
  const s = new Set(tab === 'qa' ? (S.ui.chips.qa || QA_DEFAULT) : (S.ui.chips[tab] || []));
  s.has(c.dataset.c) ? s.delete(c.dataset.c) : s.add(c.dataset.c); S.ui.chips[tab] = [...s]; save(); renderChips(); buildList(); selectPos(cur.list.length ? 0 : -1);
});
function buildList() {
  const tab = cur.tab; const items = tabItems(tab); const show = $('#qshow').value; const q = fold($('#qsearch').value.trim());
  let list = items;
  if (TYPES.includes(tab)) {
    const chips = S.ui.chips[tab] || [];
    list = list.filter(e => {
      if (!e.names.length) return false;
      const st = entState(tab, e);
      if (show === 'todo' && (!e.review || DONE(st))) return false;
      if (show === 'check' && (!linked(tab, e) || DONE(st))) return false;
      if (show === 'link' && (linked(tab, e) || DONE(st))) return false;
      if (show === 'open' && DONE(st)) return false;
      if (show === 'done' && !DONE(st)) return false;
      if (show === 'u' && st !== 'u') return false;
      if (chips.length && !chips.some(c => e.iss.has(c))) return false;
      if (q && !fold(e.label + ' ' + (tab === 'taxon' ? e.e[1] : '') + ' ' + e.names.map(x => x.name).join(' ')).includes(q)) return false;
      return true;
    });
    const sort = $('#qsort').value;
    if (show === 'link' && sort === 'prio') list = list.slice().sort((a, b) => b.n - a.n);
    else if (sort === 'prio') list = list.slice().sort((a, b) => b.risk - a.risk || b.n - a.n);
    else if (sort === 'n') list = list.slice().sort((a, b) => b.n - a.n);
    else list = list.slice().sort((a, b) => a.label.localeCompare(b.label, 'de'));
  } else {
    const chips = tab === 'qa' ? new Set(S.ui.chips.qa || QA_DEFAULT) : null;
    list = list.filter(it => {
      const st = itemState(tab, it);
      if (show === 'open' && st) return false; if (show === 'done' && !DONE(st)) return false; if (show === 'u' && st !== 'u') return false;
      if (chips && !chips.has(it.r[2])) return false;
      if (q && !fold(itemLabel(tab, it)).includes(q)) return false;
      return true;
    });
  }
  cur.list = list; cur.shown = 0; $('#qlist').innerHTML = ''; $('#qlist').scrollTop = 0; renderMore(); renderProgress();
}
function itemLabel(tab, it) {
  if (tab === 'eval') { const m = P.taxon.men[it.mi]; const f = P.taxon.forms[m[0]]; return f[0] + ' ' + P.taxon.ent[f[2]][0] + ' ' + E[m[1]][0]; }
  if (tab === 'qa') return it.r.join(' ');
  return '';
}
function renderProgress() {
  const tab = cur.tab; let tot = 0, y = 0, n = 0, u = 0, note = '';
  if (TYPES.includes(tab)) {
    let cov = 0; const all = X[tab].ents.reduce((a, e) => a + e.n, 0);
    for (const e of X[tab].ents) { const st = entState(tab, e); if (DONE(st)) cov += e.n; if (!e.review) continue; tot++; if (st === 'y') y++; else if (st === 'r') n++; else if (st === 'u') u++; }
    let lk = 0, lkd = 0, ul = 0, uld = 0; for (const e of X[tab].ents) { if (!e.names.length) continue; const d = DONE(entState(tab, e)); if (linked(tab, e)) { lk++; if (d) lkd++; } else { ul++; if (d) uld++; } }
    note = 'Verknüpfte geprüft ' + fmt(lkd) + '/' + fmt(lk) + ' · ohne Normdaten bearbeitet ' + fmt(uld) + '/' + fmt(ul) + ' · ' + pct(cov / Math.max(1, all)) + ' der ' + TT[tab].unit + ' geprüft';
    $('#qtitle').textContent = TT[tab].tab;
  } else {
    for (const it of tabItems(tab)) { if (tab === 'qa' && !QA_DEFAULT.includes(it.r[2])) continue; tot++; const st = itemState(tab, it); if (st === 'y') y++; else if (st === 'r') n++; else if (st === 'u') u++; }
    note = fmt(y + n) + ' von ' + fmt(tot) + ' beurteilt';
    $('#qtitle').textContent = TAB[tab].label;
  }
  const w = x => (100 * x / Math.max(1, tot)).toFixed(2) + '%';
  $('#pbar').innerHTML = '<i class="y" style="width:' + w(y) + '"></i><i class="n" style="width:' + w(n) + '"></i><i class="u" style="width:' + w(u) + '"></i>';
  $('#pnote').textContent = note; $('#qcount').textContent = fmt(cur.list.length) + ' in der Liste';
}
function qiHtml(pos) {
  const tab = cur.tab; const it = cur.list[pos]; const st = itemState(tab, it); let l1, l2 = '', num = '';
  if (TYPES.includes(tab)) {
    const e = it; l1 = esc(e.label) + (tab === 'taxon' && e.e[1] ? ' <i class="small muted">' + esc(e.e[1]) + '</i>' : '');
    num = fmt(e.n) + '×';
    l2 = [...e.iss].filter(k => ISSUE[tab][k] && k !== 'top').slice(0, 3).map(k => '<span class="bd ' + ISSUE[tab][k][1] + '">' + esc(ISSUE[tab][k][0]) + (k === 'sug' ? ' ' + e.sugN : '') + '</span>').join('');
    if (e.names.length > 1) l2 += '<span class="bd plain">' + e.names.length + ' Namen</span>';
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
  if (!cur.list.length) $('#qlist').innerHTML = '<div class="qmore">Nichts in dieser Auswahl.' + ($('#qshow').value === 'todo' ? ' Alles Wichtige ist erledigt. 🎉' : '') + '</div>';
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
  cur.sel = it; S.ui.sel[cur.tab] = selKey(it); save();
  ui.open = new Set(); ui.all = new Set(); ui.panel = null; ui.mapView = null; cur.focus = 'e';
  if (TYPES.includes(cur.tab)) for (const nm of it.names) { const risky = !safeName(cur.tab, nm); const hasSug = cur.tab === 'taxon' && nm.men.some(mi => SUG[mi]); if ((risky && nm.n <= 8) || (hasSug && nm.n <= 12) || it.names.length === 1) ui.open.add(nm.fi); }
  renderWork(true);
}
function nextItem(dir) {
  if (!cur.list.length) return;
  if (dir > 0) { for (let p = (cur.pos ?? -1) + 1; p < cur.list.length; p++) if (!DONE(itemState(cur.tab, cur.list[p]))) return selectPos(p); toast('Keine offenen Einträge mehr in dieser Liste'); }
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
function snipHtml(loc, ctx) {
  if (!Array.isArray(loc) || loc.length < 5) return '';
  const [p, x0, y0, x1, y1] = loc; const g = PG[p]; if (!DRIVE[g[0]] || !g[5]) return '';
  const lh = Math.max(24, (y1 - y0) / Math.max(1, Math.round((y1 - y0) / 60))); const c = ctx || 0.9;
  const top = Math.max(0, Math.round(y0 - lh * c)), bot = Math.min(g[6], Math.round(y1 + lh * c));
  return '<div class="snip" data-p="' + p + '" data-b="' + x0 + ',' + top + ',' + x1 + ',' + bot + '" data-hl="' + y0 + ',' + y1 + '" title="Seite rechts anzeigen"></div>';
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
    if (hl && g[5]) { const s = img.clientWidth / g[5]; const b = document.createElement('i'); b.className = 'hlbox';
      Object.assign(b.style, { left: (hl[1] * s - 3) + 'px', top: (hl[2] * s - 5) + 'px', width: ((hl[3] - hl[1]) * s + 6) + 'px', height: ((hl[4] - hl[2]) * s + 10) + 'px' }); wrap.appendChild(b);
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
(() => { // resizable scan panel
  if (S.ui.scanw) document.documentElement.style.setProperty('--scanw', S.ui.scanw + 'px');
  let drag = false; $('#grip').addEventListener('mousedown', e => { drag = true; e.preventDefault(); document.body.style.cursor = 'col-resize'; });
  window.addEventListener('mousemove', e => { if (!drag) return; const w = Math.max(320, Math.min(window.innerWidth - 700, window.innerWidth - e.clientX)); document.documentElement.style.setProperty('--scanw', w + 'px'); S.ui.scanw = w; });
  window.addEventListener('mouseup', () => { if (drag) { drag = false; document.body.style.cursor = ''; save(); } });
})();
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
  const txt = { y: '✓ stimmt', r: '↪ anders zugeordnet', n: '✗ kein(e) ' + TT[t].one + (d.reason ? ' (' + esc(reasonLabel(t, d.reason)) + ')' : ''), u: '? unsicher', o: '↪ eigene ' + TT[t].one, x: '↪ Art nicht bestimmbar' }[d.d] || d.d;
  return txt + tg + (d.note ? ' · ' + esc(d.note) : '');
}
function sugHtml(mi) {
  const s = SUG[mi]; if (!s) return '';
  const tgt = s[7] >= 0 ? P.taxon.ent[s[7]] : null; const differs = sugDiffers(mi) || sugReads(mi);
  const what = s[2] === 'bird' ? (tgt ? esc(tgt[0]) + ' <i>' + esc(tgt[1]) + '</i>' : esc(s[3] || '') + (s[4] ? ' <i>' + esc(s[4]) + '</i>' : '') + ' <small>(nicht im Graph)</small>') : ({ other_animal: 'kein Vogel (anderes Tier)', place: 'ein Ort', person: 'eine Person', other: 'kein Vogelname' }[s[2]] || esc(s[2]));
  return '<div class="sug"><span class="ic">Zweitlesung</span><div class="tx">Im Scan steht „<b>' + esc(s[0]) + '</b>“' + (s[1] ? ' (wie transkribiert)' : '') + ' → ' + what + ' <small>· ' + Math.round(100 * s[5]) + ' % · ' + esc(s[6]) + '</small></div>'
    + (differs ? '<button class="btn sm tip" data-sug="' + mi + '" title="Vorschlag übernehmen (G)">übernehmen <kbd>G</kbd></button>' : '<span class="bd ok">bestätigt</span>') + '</div>';
}
function menHtml(t, mi, opts) {
  opts = opts || {};
  const m = P[t].men[mi]; const ei = m[1]; const e = E[ei]; const key = X[t].mkey[mi]; const d = S.men[t][key]; const rd = menReading(t, mi);
  const b = (k, sym, title) => '<button class="mb ' + k + (d && d.d === k ? ' on' : '') + '" data-ma="' + k + '" title="' + title + '">' + sym + '</button>';
  const acts = opts.noActs ? '<span class="mini"><button class="mb" data-ma="e" title="Lesung korrigieren (E)">✎</button></span>' : '<span class="mini">' + b('y', '✓', 'Beleg stimmt (Y)') + (t === 'habitat' ? '' : b('r', '↪', 'Beleg anders zuordnen (A)')) + b('n', '✗', 'Kein(e) ' + TT[t].one + ' (N)') + '<button class="mb" data-ma="e" title="Lesung korrigieren: was steht im Scan? (E)">✎</button></span>';
  const role = m[5] ? '<span class="bd plain">' + esc(m[5]) + '</span>' : '';
  const note = (d && d.d ? '<div class="note ' + (d.d === 'o' || d.d === 'x' ? 'r' : d.d) + '">Beleg: ' + decLine(t, d) + ' <button class="lbtn" data-mclear="1">zurücksetzen</button></div>' : '')
    + (rd ? '<div class="note t">✎ Lesung korrigiert: „' + esc(rd.old) + '“ → „<b>' + esc(rd.new) + '</b>“' + (rd.note ? ' <span class="muted">(' + esc(rd.note) + ')</span>' : '') + '</div>' : '');
  const full = ui.full.has(t + mi);
  return '<div class="men" data-f="m:' + mi + '" data-t="' + t + '" data-mi="' + mi + '" data-ei="' + ei + '"><div class="mh">' + entryHead(ei) + role + '<span class="sp"></span>' + acts + '</div>'
    + snipHtml(m[4]) + '<div class="kw">' + kwic(e[7], m[2], m[3], full) + (e[7] && e[7].length > 460 ? '<button class="more" data-full="' + mi + '">' + (full ? 'weniger' : 'ganzer Eintrag') + '</button>' : '') + '</div>'
    + (t === 'taxon' ? sugHtml(mi) : '') + note + (ui.panel && ui.panel.scope === 'm:' + mi ? panelHtml(t, ui.panel) : '') + '</div>';
}

// ---------------------------------------------------------------- panels (reassign / reasons)
function panelHtml(t, pn) {
  if (pn.kind === 'not') return '<div class="panel" data-scope="' + pn.scope + '"><h5>Warum? (Taste 1–' + TT[t].not.length + ')</h5><div class="opts">' + TT[t].not.map(([k, l], i) => '<button class="btn sm" data-reason="' + k + '"><kbd>' + (i + 1) + '</kbd> ' + esc(l) + '</button>').join('') + '</div></div>';
  const title = { taxon: 'Andere Art', person: 'Andere Person', place: 'Anderer Ort', habitat: 'Andere EUNIS-Klasse' }[t];
  const ph = { taxon: 'deutscher oder wissenschaftlicher Name …', person: 'Person suchen …', place: 'Ort suchen …', habitat: 'EUNIS-Code oder englischer Begriff (reed, forest, C3.2) …' }[t];
  const special = pn.scope === 'e' || pn.scope === 'ev' || pn.scope === 'qa' ? '' : t === 'taxon' ? '<button class="btn sm" data-special="x">Art nicht bestimmbar</button>' : t === 'person' ? '<button class="btn sm" data-special="o">eigene Person</button>' : t === 'place' ? '<button class="btn sm" data-special="o">eigener Ort</button>' : '';
  return '<div class="panel rpanel" data-scope="' + pn.scope + '" data-kind="' + t + '"><h5>' + (pn.title || title) + ' · ↑↓ wählen, ⏎ übernehmen</h5><div class="row"><input type="text" class="grow rq" placeholder="' + esc(ph) + '" autocomplete="off" value="' + esc(pn.q || '') + '">'
    + (t === 'taxon' ? '<button class="lbtn rgbif">in GBIF suchen</button>' : '') + (t === 'habitat' ? '<select class="rmatch" title="exact = gleiche Bedeutung, close = sehr ähnlich, broad = Klasse ist allgemeiner"><option value="exact">exact</option><option value="close" selected>close</option><option value="broad">broad</option></select>' : '')
    + special + '</div><div class="res rres"></div></div>';
}
function openPanel(scope, kind, q, title) {
  ui.panel = { scope, kind, q: q || '', title };
  if (scope.startsWith('m:') && TYPES.includes(cur.tab)) { const fi = P[cur.tab].men[+scope.slice(2)][0]; ui.open.add(fi); }
  renderWork(false);
  const r = $('#work .rpanel[data-scope="' + scope + '"] .rq'); if (r) { r.focus(); r.select(); if (r.value) renderLocalResults(r.closest('.rpanel')); }
}
function localTaxa(q) {
  const f = fold(q); if (!f) return [];
  const res = [];
  X.taxon.ents.forEach(e => { if (!e.e[2]) return; const hay = [e.label, e.e[1], ...e.e[9]].map(fold); if (!hay.some(h => h.includes(f))) return;
    res.push([fold(e.label) === f || fold(e.e[1]) === f ? 0 : hay.some(h => h.startsWith(f)) ? 1 : 2, -e.n, e]); });
  return res.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(x => x[2]);
}
function localEnts(t, q) {
  const f = fold(q); if (!f) return [];
  const res = [];
  X[t].ents.forEach(e => { if (!e.names.length && t !== 'habitat') return; const labs = (t === 'place' ? e.e[8] : e.e[3]) || [e.label]; const hay = labs.map(fold); if (!hay.some(h => h.includes(f))) return;
    res.push([fold(e.label) === f ? 0 : hay.some(h => h.startsWith(f)) ? 1 : 2, -e.n, e]); });
  return res.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(x => x[2]);
}
function renderLocalResults(root) {
  const t = root.dataset.kind; const scope = root.dataset.scope; const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim();
  if (t === 'habitat') return eunisFilter(root);
  if (!q) { box.innerHTML = ''; root._rows = null; return; }
  let rows;
  if (t === 'taxon') rows = localTaxa(q).map(e => ({ html: '<b>' + esc(e.label) + '</b> <i>' + esc(e.e[1]) + '</i> <small>' + esc(e.e[3] || '') + ' · ' + fmt(e.n) + ' Belege</small>', target: { label: e.label, sci: e.e[1], key: e.e[2], rank: e.e[3] } }));
  else rows = localEnts(t, q).map(e => ({ html: '<b>' + esc(e.label) + '</b> <small>' + fmt(e.n) + ' ' + TT[t].unit + (t === 'place' && e.e[1] != null ? ' · ' + e.e[1] + ', ' + e.e[2] : '') + (t === 'person' && e.e[1] ? ' · ' + e.e[1] : '') + '</small>', target: { label: e.label } }));
  box.innerHTML = rows.length ? rows.map((x, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '">' + x.html + '</div>').join('') : '<div class="r muted">Nichts im Graph gefunden' + (t === 'taxon' ? ' — ⏎ sucht in GBIF' : '') + '.</div>';
  root._rows = rows.length ? rows : null; root._hi = 0;
  $$('.r[data-k]', box).forEach(el => el.onclick = () => chooseTarget(t, scope, rows[+el.dataset.k].target));
}
async function gbifSearch(root) {
  const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim(); const scope = root.dataset.scope;
  if (!q) return; box.innerHTML = '<div class="r muted">suche in GBIF …</div>';
  try {
    const [m, s] = await Promise.all([getJSON('https://api.gbif.org/v1/species/match?verbose=true&class=Aves&name=' + encodeURIComponent(q)).catch(() => ({})),
      getJSON('https://api.gbif.org/v1/species/search?datasetKey=d7dddbf4-2cf0-4f39-9b2a-bb099caae36c&limit=15&q=' + encodeURIComponent(q)).catch(() => ({ results: [] }))]);
    const seen = new Set(); const rows = [];
    const push = x => { const key = x.usageKey || x.key; if (!key || seen.has(key)) return; seen.add(key);
      rows.push({ key, name: x.canonicalName || x.scientificName, rank: x.rank, status: x.status || x.taxonomicStatus, acc: x.acceptedUsageKey || x.acceptedKey, cls: x.class, fam: x.family, vn: (x.vernacularNames || []).filter(v => v.language === 'deu').map(v => v.vernacularName).slice(0, 2).join(', ') }); };
    if (m.usageKey) push(m); (m.alternatives || []).forEach(push); (s.results || []).forEach(push);
    box.innerHTML = rows.length ? rows.map((x, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '"><b><i>' + esc(x.name) + '</i></b> <small>' + esc(x.rank || '') + ' · ' + esc(x.status || '') + ' · ' + esc(x.key) + (x.fam ? ' · ' + esc(x.fam) : '') + (x.cls ? ' · ' + esc(x.cls) : '') + '</small>' + (x.vn ? '<br><small>' + esc(x.vn) + '</small>' : '') + '</div>').join('') : '<div class="r muted">Keine Treffer in GBIF.</div>';
    root._rows = rows.length ? rows : null; root._hi = 0;
    $$('.r[data-k]', box).forEach(el => el.onclick = async () => {
      const x = rows[+el.dataset.k]; let key = x.key, name = x.name, rank = x.rank; const vn = x.vn.split(',')[0];
      if (x.acc && x.acc !== x.key && x.status && x.status !== 'ACCEPTED') { try { const a = await getJSON('https://api.gbif.org/v1/species/' + x.acc); key = a.key; name = a.canonicalName || a.scientificName; rank = a.rank; toast('Synonym: auf den gültigen Namen ' + name + ' umgestellt'); } catch (e) { } }
      const local = X.taxon.ents.find(e => e.e[2] === String(key));
      chooseTarget('taxon', scope, { label: local ? local.label : (vn || name), sci: name, key: String(key), rank: lc(rank) });
    });
  } catch (e) { box.innerHTML = '<div class="r muted">GBIF nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
function eunisFilter(root) {
  const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim().toLowerCase(); const scope = root.dataset.scope; if (!q) { box.innerHTML = ''; root._rows = null; return; }
  const res = P.eunis.filter(e => e[0].toLowerCase().startsWith(q) || e[1].toLowerCase().includes(q)).sort((a, b) => a[2] - b[2] || a[0].localeCompare(b[0])).slice(0, 80);
  const match = root.querySelector('.rmatch');
  box.innerHTML = res.length ? res.map((e, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '" style="padding-left:' + (6 + 10 * (e[2] - 1)) + 'px"><b>' + esc(e[0]) + '</b> ' + esc(e[1]) + ' <small>Ebene ' + e[2] + '</small></div>').join('') : '<div class="r muted">Keine Klasse gefunden (Namen sind englisch).</div>';
  root._rows = res.length ? res : null; root._hi = 0;
  $$('.r[data-k]', box).forEach(el => el.onclick = () => { const e = res[+el.dataset.k]; chooseTarget('habitat', scope, { code: e[0], label: e[0] + ' ' + e[1], match: match ? match.value : 'close' }); });
}
function panelKeys(ev) {
  const root = ev.target.closest && ev.target.closest('.rpanel'); if (!root) return false;
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { const rs = $$('.rres .r[data-k]', root); if (!rs.length) return true; root._hi = Math.max(0, Math.min(rs.length - 1, (root._hi || 0) + (ev.key === 'ArrowDown' ? 1 : -1))); rs.forEach((r, i) => r.classList.toggle('hi', i === root._hi)); rs[root._hi].scrollIntoView({ block: 'nearest' }); ev.preventDefault(); return true; }
  if (ev.key === 'Enter') { ev.preventDefault(); const rs = $$('.rres .r[data-k]', root); const hi = rs[root._hi || 0];
    if (root._rows && hi) hi.click(); else if (root.dataset.kind === 'taxon') gbifSearch(root); return true; }
  return false;
}

// ---------------------------------------------------------------- decisions
function setEnt(t, e, obj) { if (!obj) delete S.ent[t][e.label]; else S.ent[t][e.label] = stampObj(obj); }
function setName(t, nm, obj) { if (!obj) delete S.id[t][nm.key]; else S.id[t][nm.key] = stampObj(obj); }
function setMen(t, mi, obj) { const k = X[t].mkey[mi]; if (!obj) delete S.men[t][k]; else S.men[t][k] = stampObj(obj); }
function chooseTarget(t, scope, target) {
  ui.panel = null;
  if (cur.tab === 'eval') { const it = cur.sel; commit('Stichprobe', () => { S.ev[it.key] = stampObj(Object.assign({}, S.ev[it.key] || {}, { d: 'n', target, cls: P.taxon.forms[P.taxon.men[it.mi][0]][3] })); setMen('taxon', it.mi, { d: 'r', target, note: 'aus der Stichprobe' }); }); if (S.ui.adv) setTimeout(() => nextItem(1), 250); return; }
  if (cur.tab === 'qa') { const it = cur.sel; commit('Hinweis', () => { S.men.taxon[it.r[1] + '|' + lc(it.r[4]) + '|0'] = stampObj({ d: 'r', target, written: it.r[4], note: 'Hinweis ' + it.r[2] }); if (!(S.qa[it.key] || {}).d) S.qa[it.key] = stampObj({ d: 'n' }); }); return; }
  const e = cur.sel;
  if (scope === 'e') commit(TT[t].one + ' neu zugeordnet', () => setEnt(t, e, { d: 'r', target }));
  else if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('Name neu zugeordnet', () => setName(t, nm, { d: 'r', target })); }
  else if (scope.startsWith('m:')) commit('Beleg neu zugeordnet', () => setMen(t, +scope.slice(2), { d: 'r', target }));
  afterDecision(scope);
}
function special(t, scope, code) {
  ui.panel = null;
  if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('Name', () => setName(t, nm, { d: code })); }
  else if (scope.startsWith('m:')) commit('Beleg', () => setMen(t, +scope.slice(2), { d: code }));
  afterDecision(scope);
}
function reason(t, scope, r) {
  ui.panel = null;
  if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('kein Eintrag', () => setName(t, nm, { d: 'n', reason: r })); }
  else if (scope.startsWith('m:')) commit('Beleg entfernt', () => setMen(t, +scope.slice(2), { d: 'n', reason: r }));
  afterDecision(scope);
}
// the four actions on the focused row
function act(a) {
  const tab = cur.tab;
  if (tab === 'eval' || tab === 'qa') return simpleDecide(a);
  if (!TYPES.includes(tab) || !cur.sel) return;
  const t = tab, e = cur.sel, f = cur.focus || 'e';
  if (f === 'e') return entAct(t, e, a);
  if (f.startsWith('n:')) {
    const nm = X[t].names[+f.slice(2)];
    if (a === 'r') return openPanel(f, 'r');
    if (a === 'n') return openPanel(f, 'not');
    const cd = nameDec(t, nm);
    commit('Name', () => setName(t, nm, cd && cd.d === a ? null : { d: a }));
    return afterDecision(f);
  }
  if (f.startsWith('m:')) {
    const mi = +f.slice(2);
    if (a === 'r') { if (t === 'habitat') return; return openPanel(f, 'r'); }
    if (a === 'n') return openPanel(f, 'not');
    const cd = S.men[t][X[t].mkey[mi]];
    commit('Beleg', () => setMen(t, mi, cd && cd.d === a ? null : { d: a }));
    return afterDecision(f);
  }
}
function entAct(t, e, a) {
  const cd = entDec(t, e) || {};
  if (a === 'u') { commit('unsicher', () => setEnt(t, e, cd.d === 'u' ? null : Object.assign({}, cd, { d: 'u' }))); return afterDecision('e'); }
  if (t === 'taxon') {
    if (a === 'y') { if (!e.e[2]) return toast('Keine GBIF-Art: mit ↪ eine Art zuordnen oder ✗ „nicht bestimmbar“'); commit('Art bestätigt', () => setEnt(t, e, cd.d === 'y' ? null : { d: 'y' })); return afterDecision('e'); }
    if (a === 'r') { const llm = e.names.map(nm => nm.f[5]).find(Boolean); return openPanel('e', 'r', e.e[2] ? '' : (llm || e.label), e.e[2] ? 'Andere Art für alle Namen' : 'GBIF-Art zuordnen'); }
    if (a === 'n') { commit('nicht bestimmbar', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision('e'); }
  }
  if (t === 'habitat') {
    if (a === 'y') { if (!e.e[1]) return toast('Keine EUNIS-Klasse: mit ↪ eine Klasse wählen oder ✗'); commit('Klasse bestätigt', () => setEnt(t, e, cd.d === 'y' ? null : { d: 'y' })); return afterDecision('e'); }
    if (a === 'r') return openPanel('e', 'r', '');
    if (a === 'n') { commit('keine Klasse', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision('e'); }
  }
  if (t === 'person') {
    if (a === 'y') { const q = cd.qid || (cd.d ? null : e.e[1]); const g = cd.gnd || (cd.d ? null : e.e[2]); if (!q && !g) return toast('Erst einen Wikidata-Kandidaten oder eine GND wählen (oder ✗ keine Normdaten)');
      commit('Normdaten bestätigt', () => setEnt(t, e, Object.assign({}, cd, { d: 'y', qid: q || null, gnd: g || null }))); return afterDecision('e'); }
    if (a === 'r') { const w = $('#wq'); if (w) { w.focus(); w.select(); } return; }
    if (a === 'n') { commit('keine Normdaten', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision('e'); }
  }
  if (t === 'place') {
    if (a === 'y') { if (e.e[1] == null && !(cd.fix && cd.fix.lat)) return toast('Keine Lage: suchen, Koordinate eingeben oder in die Karte klicken'); commit('Lage bestätigt', () => setEnt(t, e, Object.assign({}, cd, { d: 'y' }))); return afterDecision('e'); }
    if (a === 'r') { const w = $('#nq'); if (w) { w.focus(); w.select(); } return; }
    if (a === 'n') { commit('Lage nicht bestimmbar', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision('e'); }
  }
}
function bulkNames(t, e) {
  const open = e.names.filter(nm => !nameState(t, nm));
  if (!open.length) return toast('Keine offenen Namen');
  commit('alle offenen Namen bestätigt', () => { for (const nm of open) setName(t, nm, { d: 'y' }); });
  afterDecision('e');
}
// after a decision: focus the next open row; the entity is done -> next entity
function afterDecision(scope) {
  if (!TYPES.includes(cur.tab)) return;
  const t = cur.tab, e = cur.sel;
  if (DONE(entState(t, e))) { if (S.ui.adv) { toast('Erledigt: ' + e.label); setTimeout(() => { if (cur.sel === e && !ui.panel) nextItem(1); }, 450); } return; }
  const rows = focusRows(); const i = rows.indexOf(scope);
  const open = r => r === 'e' ? !(entDec(t, e) || {}).d : r.startsWith('n:') ? !nameState(t, X[t].names[+r.slice(2)]) : r.startsWith('m:') ? !menState(t, +r.slice(2)) && !nameState(t, X[t].names[P[t].men[+r.slice(2)][0]]) : false;
  const nxt = rows.slice(i + 1).find(open) || rows.find(open);
  if (nxt) setFocus(nxt);
}
function simpleDecide(a) {
  const it = cur.sel; if (!it || a === 'r') return;
  if (cur.tab === 'eval') {
    const cd = S.ev[it.key];
    commit('Stichprobe', () => { if (cd && cd.d === a) delete S.ev[it.key]; else S.ev[it.key] = stampObj({ d: a, cls: P.taxon.forms[P.taxon.men[it.mi][0]][3], note: (cd || {}).note || '' }); });
    if (a === 'n' && (S.ev[it.key] || {}).d === 'n') return openPanel('ev', 'r', '', 'Richtige Art (optional; Esc = überspringen)');
    if (S.ui.adv && (S.ev[it.key] || {}).d) setTimeout(() => nextItem(1), 180);
    return;
  }
  if (cur.tab === 'qa') {
    const cd = S.qa[it.key];
    commit('Hinweis', () => { if (cd && cd.d === a) delete S.qa[it.key]; else S.qa[it.key] = stampObj(Object.assign({}, cd || {}, { d: a })); });
    if (S.ui.adv && (S.qa[it.key] || {}).d) setTimeout(() => nextItem(1), 180);
  }
}

// ---------------------------------------------------------------- focus
function focusRows() { return $$('#work [data-f]').map(el => el.dataset.f); }
function setFocus(f, noScan) {
  cur.focus = f; $$('#work .focus').forEach(el => el.classList.remove('focus'));
  let el = $('#work [data-f="' + f + '"]');
  if (!el && f.startsWith('m:') && TYPES.includes(cur.tab) && !setFocus.busy) { const fi = P[cur.tab].men[+f.slice(2)][0]; if (X[cur.tab].names[fi].ent === cur.sel.i) { setFocus.busy = true; ui.open.add(fi); ui.all.add(fi); try { renderWork(false); } finally { setFocus.busy = false; } el = $('#work [data-f="' + f + '"]'); } }
  if (!el) return;
  el.classList.add('focus'); el.scrollIntoView({ block: 'nearest' });
  if (!noScan && S.ui.follow && f.startsWith('m:')) scanFor(el.dataset.t, +f.slice(2));
}
function moveFocus(dir) { const rows = focusRows(); if (!rows.length) return; let i = rows.indexOf(cur.focus); i = Math.max(0, Math.min(rows.length - 1, (i < 0 ? -1 : i) + dir)); setFocus(rows[i]); }

// ---------------------------------------------------------------- workspace
let map = null;
function renderWork(fresh) {
  if (map) { try { ui.mapView = [map.getCenter(), map.getZoom()]; } catch (e) { ui.mapView = null; } map.remove(); map = null; }
  const w = $('#work'); const scrollTop = w.scrollTop;
  const it = cur.sel; if (!it) { w.innerHTML = '<div class="empty">Nichts ausgewählt.</div>'; return; }
  let h;
  if (TYPES.includes(cur.tab)) h = entityView(cur.tab, it);
  else if (cur.tab === 'eval') h = evalView(it);
  else if (cur.tab === 'qa') h = qaView(it);
  else return;
  w.innerHTML = '<div class="wrap">' + h + kbdRow() + '</div>';
  w.scrollTop = fresh ? 0 : scrollTop;
  wireWork(); wireSnips(w);
  const rows = focusRows(); if (!rows.includes(cur.focus)) cur.focus = rows[0] || 'e';
  setFocus(cur.focus, true);
  if (fresh) {
    const f = rows.find(r => r.startsWith('m:'));
    if (f && S.ui.follow) scanFor($('#work [data-f="' + f + '"]').dataset.t, +f.slice(2));
    else if (it.ei != null && it.ei >= 0) showScan(it.ei);
  }
  if (ui.panel) { const r = $('#work .rpanel[data-scope="' + ui.panel.scope + '"] .rq'); if (r && document.activeElement !== r) { r.focus(); if (r.value) renderLocalResults(r.closest('.rpanel')); } }
}
function kbdRow() {
  const k = TYPES.includes(cur.tab)
    ? '<kbd>J</kbd>/<kbd>K</kbd> Zeile · <kbd>Y</kbd> ✓ · <kbd>A</kbd> ↪ · <kbd>N</kbd> ✗ · <kbd>U</kbd> ? · <kbd>Leertaste</kbd> Belege · <kbd>E</kbd> Lesung · <kbd>G</kbd> Zweitlesung · <kbd>⏎</kbd> nächster · <kbd>Z</kbd> rückgängig · <kbd>←</kbd>/<kbd>→</kbd> Seiten'
    : '<kbd>Y</kbd> richtig · <kbd>N</kbd> falsch · <kbd>U</kbd> unsicher · <kbd>E</kbd> Lesung · <kbd>⏎</kbd> nächster · <kbd>Z</kbd> rückgängig';
  return '<div class="kbdrow">' + k + ' · <label><input type="checkbox" id="adv"' + (S.ui.adv ? ' checked' : '') + '> automatisch weiter</label> · <label><input type="checkbox" id="follow"' + (S.ui.follow ? ' checked' : '') + '> Scan folgt der Auswahl</label></div>';
}
function crumb() {
  return '<div class="crumb"><span>' + esc(TAB[cur.tab].label) + (cur.pos >= 0 ? ' · ' + fmt(cur.pos + 1) + ' von ' + fmt(cur.list.length) : '') + '</span>'
    + '<span class="nav"><button class="nbtn" data-nav="-1">↑ vorheriger</button><button class="nbtn" data-nav="1">nächster offener ⏎</button></span></div>';
}
function entActs(t, e) {
  const cd = entDec(t, e) || {};
  const b = (k, label, key, dis) => '<button class="btn ' + k + (cd.d === k ? ' on' : '') + '" data-ea="' + k + '"' + (dis ? ' disabled title="' + esc(dis) + '"' : '') + '>' + label + ' <kbd>' + key + '</kbd></button>';
  const L = { taxon: [e.e[2] ? 'Art stimmt' : 'Art stimmt', e.e[2] ? 'Andere Art …' : 'GBIF-Art zuordnen …', 'Nicht bestimmbar'], person: ['Normdaten stimmen', 'Suchen …', 'Keine Normdaten'], place: ['Lage stimmt', 'Lage ändern …', 'Nicht bestimmbar'], habitat: ['Klasse stimmt', 'Andere Klasse …', 'Keine Klasse passt'] }[t];
  let yDis = '';
  if (t === 'taxon' && !e.e[2]) yDis = 'Keine GBIF-Art zugeordnet';
  if (t === 'habitat' && !e.e[1]) yDis = 'Keine EUNIS-Klasse';
  if (t === 'person' && !(cd.qid || cd.gnd || (!cd.d && (e.e[1] || e.e[2])))) yDis = 'Erst einen Kandidaten wählen';
  if (t === 'place' && e.e[1] == null && !(cd.fix && cd.fix.lat)) yDis = 'Keine Koordinate';
  const safe = e.names.filter(nm => safeName(t, nm) && !nameDec(t, nm));
  return '<div class="acts" data-f="e">' + b('y', L[0], 'Y', yDis) + b('r', L[1], 'A') + b('n', L[2], 'N') + b('u', 'Unsicher', 'U') + (cd.d ? '<button class="lbtn" data-ea="">zurücksetzen</button>' : '') + '</div>'
    + (safe.length && e.names.length > 1 ? '<div class="hint">„' + L[0] + '“ bestätigt auch ' + (safe.length === 1 ? 'den sicheren Namen „' + esc(safe[0].name) + '“' : 'die ' + safe.length + ' sicheren Namen (' + safe.slice(0, 4).map(x => '„' + esc(x.name) + '“').join(', ') + (safe.length > 4 ? ' …' : '') + ')') + '.</div>' : '')
    + (cd.d ? '<div class="state ' + ({ y: 'y', r: 'r', n: 'n', u: 'u' }[cd.d]) + '">' + entStateText(t, e, cd) + (cd.by ? ' <span class="muted small">· ' + esc(cd.by) + ', ' + new Date(cd.t).toLocaleString('de-DE') + '</span>' : '') + '</div>' : '')
    + (ui.panel && ui.panel.scope === 'e' ? panelHtml(t, ui.panel) : '');
}
function entStateText(t, e, cd) {
  if (cd.d === 'u') return '? unsicher';
  if (t === 'taxon') return cd.d === 'y' ? '✓ Art bestätigt' : cd.d === 'r' ? '↪ neu zugeordnet: <b>' + esc(cd.target.label) + '</b> <i>' + esc(cd.target.sci || '') + '</i> (Namen ohne eigene Entscheidung folgen)' : '✗ nicht bestimmbar: ohne GBIF-Art';
  if (t === 'habitat') return cd.d === 'y' ? '✓ Klasse bestätigt' : cd.d === 'r' ? '↪ neue Klasse: <b>' + esc(cd.target.label) + '</b> (' + esc(cd.target.match) + ')' : '✗ keine EUNIS-Klasse';
  if (t === 'person') return cd.d === 'y' ? '✓ Normdaten: ' + [cd.qid ? 'Wikidata ' + esc(cd.qid) : '', cd.gnd ? 'GND ' + esc(cd.gnd) : ''].filter(Boolean).join(' · ') : '✗ keine passenden Normdaten';
  return cd.d === 'y' ? '✓ Lage ' + (cd.fix && cd.fix.lat ? 'korrigiert: ' + cd.fix.lat + ', ' + cd.fix.lon + ' (± ' + fmt(cd.fix.uncertainty_m) + ' m)' : 'bestätigt') : '✗ Lage nicht bestimmbar';
}
function namesBlock(t, e) {
  const open = e.names.filter(nm => !nameState(t, nm)).length;
  let h = '<div class="sec"><h3>' + (e.names.length > 1 ? 'Zusammengeführte Namen · ' + e.names.length + ' (gehört jeder dazu?)' : 'Name im Tagebuch') + '</h3><span class="sp"></span>' + (open > 1 ? '<button class="lbtn" id="bulk">alle ' + open + ' offenen Namen ✓</button>' : '') + '</div>';
  for (const nm of e.names) h += nameRow(t, e, nm);
  return h;
}
function sugGroups(nm) {
  const diff = nm.men.filter(mi => sugDiffers(mi) || sugReads(mi));
  const groups = new Map(); for (const mi of diff) { const s = SUG[mi]; const k = s[2] + '|' + (s[7] >= 0 ? s[7] : s[4]) + '|' + fold(s[0]).replace(/[^a-z]/g, ''); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(mi); }
  return { diff, top: [...groups.values()].sort((a, b) => b.length - a.length)[0] || [] };
}
function nameRow(t, e, nm) {
  const st = nameState(t, nm); const d = nameDec(t, nm); const isOpen = ui.open.has(nm.fi);
  const cls = TT[t].cls[nm.cls] || [nm.cls, 'plain', ''];
  const b = (k, sym, title) => '<button class="mb ' + k + (d && d.d === k ? ' on' : '') + '" data-na="' + k + '" title="' + title + '">' + sym + '</button>';
  let why = '';
  if (t === 'taxon') why = nm.cls === 'A' ? (nm.f[4] && lc(nm.f[4]) !== nm.key ? 'wie „' + esc(nm.f[4]) + '“' : '') : nm.cls === 'B' ? 'Variante von „' + esc(nm.f[4]) + '“' : nm.cls === 'C' ? (nm.f[4] ? 'ähnlich: „' + esc(nm.f[4]) + '“' : '') : '';
  else if (nm.f[4] && !isLabel(t, nm)) why = 'zusammengeführt: ' + esc(RULE_DE[nm.f[4]] || nm.f[4]);
  const others = (X[t].byKey.get(nm.key) || []).filter(x => x.ent !== nm.ent);
  const ns = NSTATE[st];
  const stTxt = st ? '<span class="bd ' + (ns ? ns[1] : 'plain') + '">' + (ns ? ns[0] : st) + (d && d.target ? ': ' + esc(d.target.label || d.target.code || '') : '') + (d && d.reason ? ' (' + esc(reasonLabel(t, d.reason)) + ')' : '') + '</span>' : '<span class="bd plain">offen</span>';
  let sugAgg = '';
  if (t === 'taxon') {
    const sugs = nm.men.filter(mi => SUG[mi]);
    if (sugs.length) {
      const { diff, top } = sugGroups(nm); const agree = sugs.length - diff.length;
      sugAgg = '<div class="dl"><span class="bd tip">Zweitlesung</span> ' + sugs.length + ' von ' + nm.men.length + ' Belegen gelesen' + (agree ? ' · ' + agree + ' bestätigen' : '') + (diff.length ? ' · <b>' + diff.length + ' widersprechen</b>' : '')
        + (top.length > 1 ? ' · meist „' + esc(SUG[top[0]][0]) + '“ <button class="lbtn" data-sugall="' + nm.fi + '" title="G">für diese ' + top.length + ' übernehmen</button>' : '') + '</div>';
    }
  }
  let body = '';
  if (isOpen) {
    const all = nm.men.map(mi => [mi, P[t].men[mi][1]]);
    const shown = ui.all.has(nm.fi) ? all.slice().sort((a, b) => (E[a[1]][2] || '').localeCompare(E[b[1]][2] || '')) : pickSpread(all, 6);
    for (const x of all) if (!shown.some(y => y[0] === x[0]) && (S.men[t][X[t].mkey[x[0]]] || (t === 'taxon' && SUG[x[0]] && (sugDiffers(x[0]) || sugReads(x[0]))))) shown.push(x);
    body = '<div class="body">' + shown.map(([mi]) => menHtml(t, mi)).join('')
      + (all.length > shown.length ? '<div class="row" style="margin-top:8px"><button class="lbtn" data-allmen="' + nm.fi + '">alle ' + fmt(all.length) + ' Belege zeigen</button><span class="small muted">' + shown.length + ' über die Jahre verteilt gezeigt</span></div>' : '') + '</div>';
  }
  return '<div class="nm" data-fi="' + nm.fi + '"><div class="nh" data-f="n:' + nm.fi + '"><span class="tw">' + (isOpen ? '▾' : '▸') + '</span><span class="nn">' + esc(nm.name) + '</span><span class="ct">' + fmt(nm.n) + '×</span>'
    + '<span class="bd ' + cls[1] + '" title="' + esc(cls[2]) + '">' + esc(cls[0]) + '</span>' + (isLabel(t, nm) && e.names.length > 1 ? '<span class="bd plain">Hauptname</span>' : '') + '<span class="why">' + why + '</span>'
    + (others.length ? '<span class="bd warn" title="Derselbe Name ist auch anderen Einträgen zugeordnet; eine Entscheidung hier gilt für den Namen überall">auch bei ' + others.slice(0, 3).map(x => esc(ENT(t, x.ent).label)).join(', ') + '</span>' : '')
    + '<span class="sp"></span>' + stTxt + '<span class="mini">' + b('y', '✓', 'Name gehört zu diesem Eintrag (Y)') + b('r', '↪', 'Name gehört zu einem anderen Eintrag (A)') + b('n', '✗', 'Kein(e) ' + TT[t].one + ' (N)') + b('u', '?', 'Unsicher (U)') + '</span></div>'
    + sugAgg + (ui.panel && ui.panel.scope === 'n:' + nm.fi ? '<div style="padding:0 10px 8px">' + panelHtml(t, ui.panel) + '</div>' : '') + body + '</div>';
}
const RULE_DE = { 'same-key': 'gleicher Name ohne Titel/Umlaut', 'initial-unique': 'Initiale passt nur zu dieser Person', 'initial-ambiguous': 'Initiale passt zu mehreren', 'surname-unique': 'gleicher Nachname', 'surname-ambiguous': 'gleicher Nachname, mehrdeutig', dominant: 'häufigste passende Person', manual: 'von Hand zusammengeführt', wikidata: 'gleiches Wikidata-Objekt', orthographic: 'gleiche Schreibung (ü/ue, ß/ss …)', similar: 'ähnliche Schreibung' };
const surname = n => { const w = fold(n).split(/[^a-z]+/).filter(x => x.length > 2); return w[w.length - 1] || ''; };
function suggestions(t, e) {
  const out = []; const seen = new Set([e.i]);
  const add = (ent, why, kind) => { if (!ent || seen.has(ent.i)) return; seen.add(ent.i); out.push({ ent, why, kind }); };
  if (t === 'taxon') {
    const llm = e.names.map(nm => nm.f[5]).find(Boolean);
    if (llm) add(X.taxon.ents.find(x => x.e[2] && lc(x.e[1]) === lc(llm)), 'Vorschlag des Sprachmodells', 'llm');
    const votes = new Map(); for (const nm of e.names) for (const mi of nm.men) { const sg = SUG[mi]; if (sg && sg[2] === 'bird' && sg[7] >= 0 && sg[7] !== e.i) votes.set(sg[7], (votes.get(sg[7]) || 0) + 1); }
    for (const [i, n] of [...votes.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2)) add(X.taxon.ents[i], 'Zweitlesung (' + n + '×)', 'sug');
    const keys = e.names.map(nm => letters(nm.name)).filter(k => k.length >= 4);
    const sim = [];
    for (const x of X.taxon.ents) { if (!x.e[2] || x.i === e.i) continue; const labs = [x.label, ...x.e[9]].map(letters);
      let best = 0; for (const k of keys) for (const l of labs) { if (l.length < 4) continue; const sc = k === l ? 3 : (k.endsWith(l) && l.length >= 5) ? 2 : sameWord(k, l) ? 1.5 : 0; if (sc > best) best = sc; }
      if (best) sim.push([best, x.n, x]); }
    sim.sort((a, b) => b[0] - a[0] || b[1] - a[1]).slice(0, 4).forEach(([sc, , x]) => add(x, sc === 3 ? 'gleicher deutscher Name' : sc === 2 ? 'Grundwort passt' : 'ähnlicher Name', 'name'));
  } else {
    const keys = new Set(e.names.map(nm => t === 'person' ? surname(nm.name) : letters(nm.name)).filter(k => k.length >= 3));
    const inits = ent => { const out = new Set(); for (const nm of ent.names) { const w = fold(nm.name).replace(TITLES, ' ').split(/[^a-z]+/).filter(Boolean); w.pop(); for (const x of w) out.add(x[0]); } return out; };
    const mine = t === 'person' ? inits(e) : null;
    const sim = [];
    for (const x of X[t].ents) { if (x.i === e.i || !x.names.length) continue;
      let hit = false; for (const nm of x.names) { const k = t === 'person' ? surname(nm.name) : letters(nm.name); if (!k) continue;
        if (t === 'person' ? keys.has(k) : [...keys].some(q => sameWord(q, k) || (q.length >= 6 && k.length >= 6 && (q.includes(k) || k.includes(q))))) { hit = true; break; } }
      if (hit && t === 'person') { const theirs = inits(x); if (mine.size && theirs.size && ![...mine].some(c => theirs.has(c))) hit = false; }
      if (hit) sim.push([linked(t, x) ? 1 : 0, x.n, x]); }
    sim.sort((a, b) => b[0] - a[0] || b[1] - a[1]).slice(0, 5).forEach(([, , x]) => add(x, t === 'person' ? 'gleicher Nachname' : 'ähnlicher Name', 'name'));
  }
  return out;
}
function sugBlock(t, e) {
  const sg = suggestions(t, e); const x = e.e;
  let extra = '';
  if (t === 'taxon' && !x[2]) { const llm = e.names.map(nm => nm.f[5]).find(Boolean); if (llm && !X.taxon.ents.some(y => y.e[2] && lc(y.e[1]) === lc(llm))) extra = '<button class="btn sm" data-gbifq="' + esc(llm) + '">in GBIF suchen: <i>' + esc(llm) + '</i></button>'; }
  if (t === 'place' && x[1] == null) { const lr = (e.names.find(nm => isLabel(t, nm)) || e.names[0]).f[5] || []; if (lr[4] && lr[5]) extra += '<button class="btn sm" data-setll="' + esc(lr[4]) + ',' + esc(lr[5]) + '">Gazetteer-Vorschlag übernehmen: ' + esc(lr[7] || '') + ' ' + esc(lr[4]) + ', ' + esc(lr[5]) + '</button>'; }
  if (!sg.length && !extra) return '';
  const what = { taxon: 'dieselbe Art wie', person: 'dieselbe Person wie', place: 'derselbe Ort wie', habitat: 'derselbe Lebensraum wie' }[t];
  return '<div class="panel"><h5>Vorschläge · Zusammenführen heißt: alle Namen hier gehören zu dem gewählten Eintrag</h5><div class="cands">'
    + sg.map((c, k) => { const y = c.ent; const auth = t === 'taxon' ? '<i>' + esc(y.e[1] || '') + '</i>' : t === 'person' ? esc([y.e[1], y.e[2] ? 'GND ' + y.e[2] : ''].filter(Boolean).join(' · ') || 'ohne Normdaten') : t === 'place' ? (y.e[1] != null ? esc(y.e[1] + ', ' + y.e[2]) : 'ohne Lage') : esc(y.e[1] || 'ohne Klasse');
      return '<div class="cand" data-merge="' + y.i + '"><span class="k" title="Umschalt+' + String.fromCharCode(65 + k) + '">⇧' + String.fromCharCode(65 + k) + '</span><div><div class="cl">' + esc(what) + ' „' + esc(y.label) + '“ ' + auth + '</div><div class="cd">' + esc(c.why) + ' · ' + fmt(y.n) + ' ' + TT[t].unit + (y.names.length > 1 ? ' · ' + y.names.length + ' Namen' : '') + '</div></div><span class="bd ' + (linked(t, y) ? 'ok' : 'plain') + '">' + (linked(t, y) ? 'verknüpft' : 'ohne Normdaten') + '</span></div>'; }).join('')
    + '</div>' + (extra ? '<div class="row" style="margin-top:8px">' + extra + '</div>' : '') + '</div>';
}
function mergeInto(t, e, y) {
  if (t === 'taxon' || t === 'habitat') {
    const target = t === 'taxon' ? { label: y.label, sci: y.e[1], key: y.e[2], rank: y.e[3] } : { code: y.e[1], label: y.e[1] + ' ' + ((EUNIS.get(y.e[1]) || [])[1] || ''), match: y.e[2] || 'close' };
    if (t === 'habitat' && !y.e[1]) { commit('zusammengeführt', () => { for (const nm of e.names) setName(t, nm, { d: 'r', target: { label: y.label } }); }); return afterDecision('e'); }
    commit('zusammengeführt mit ' + y.label, () => setEnt(t, e, { d: 'r', target })); return afterDecision('e');
  }
  commit('zusammengeführt mit ' + y.label, () => { for (const nm of e.names) if (!nameDec(t, nm)) setName(t, nm, { d: 'r', target: { label: y.label } }); });
  afterDecision('e');
}
function entityView(t, e) {
  const x = e.e;
  let head;
  if (t === 'taxon') {
    const llm = e.names.map(nm => nm.f[5]).find(Boolean);
    head = '<h1 class="t">' + esc(e.label) + (x[1] ? ' <i>' + esc(x[1]) + '</i>' : '') + '</h1><div class="sub">' + fmt(e.n) + ' Belege · ' + e.names.length + (e.names.length === 1 ? ' Name' : ' Namen') + (x[6] ? ' · ' + esc(x[6]) : '') + (x[7] ? ' · ' + esc(x[7]) : '') + '</div>'
      + '<dl class="facts">' + (x[2] ? '<dt>GBIF</dt><dd><a href="https://www.gbif.org/species/' + esc(x[2]) + '" target="_blank" rel="noopener"><i>' + esc(x[1] || x[2]) + '</i> ↗</a> <span class="muted small">' + esc(x[3] || '') + (x[4] ? ' · ' + esc(x[4]) : '') + (x[5] ? ' · ' + esc(x[5]) : '') + '</span>' + (x[4] === 'HIGHERRANK' ? ' <span class="bd warn">nur übergeordnete Ebene</span>' : '') + '</dd>'
        : '<dt>GBIF</dt><dd><span class="bd warn">keine Art zugeordnet</span>' + (llm ? ' · Modell schlug <i>' + esc(llm) + '</i> vor' : '') + '</dd>')
      + (x[9].length ? '<dt>Deutsche Namen</dt><dd class="small">' + x[9].slice(0, 16).map(esc).join(', ') + (x[9].length > 16 ? ' …' : '') + '</dd>' : '')
      + (llm && x[1] && fold(llm) !== fold(x[1]) ? '<dt>Modell las</dt><dd><i>' + esc(llm) + '</i></dd>' : '') + '</dl>';
  } else if (t === 'person') head = personHead(e);
  else if (t === 'place') head = placeHead(e);
  else {
    const ex = EUNIS.get(x[1]); const lr = e.names.length ? e.names[0].f[5] || [] : [];
    head = '<h1 class="t">' + esc(e.label) + '</h1><div class="sub">' + fmt(e.n) + ' Beobachtungen</div><dl class="facts"><dt>EUNIS</dt><dd>' + (x[1] ? '<b>' + esc(x[1]) + '</b> ' + esc((ex || [])[1] || lr[4] || '') + ' <span class="muted small">(' + esc(x[2]) + (lr[1] ? ', Konfidenz ' + esc(lr[1]) : '') + ')</span> · <a href="https://biodiversity.europa.eu/resources/search-habitat/eunis-habitat-types-hierarchical-view-2012?searchTerm=' + encodeURIComponent(x[1]) + '" target="_blank" rel="noopener">BISE ↗</a>' : '<span class="bd warn">keine Klasse</span>') + '</dd>'
      + (ex && ex[3] ? '<dt>übergeordnet</dt><dd>' + esc(ex[3]) + ' ' + esc((EUNIS.get(ex[3]) || [])[1] || '') + '</dd>' : '') + (lr[2] ? '<dt>Begründung Modell</dt><dd class="small">' + esc(lr[2]) + '</dd>' : '') + '</dl>';
  }
  return crumb() + '<div class="card"><div class="cb">' + (linked(t, e) ? '<span class="bd ok">verknüpft · prüfen</span>' : '<span class="bd warn">ohne Normdaten · verknüpfen oder zusammenführen</span>') + head + entActs(t, e) + sugBlock(t, e) + '</div></div>' + namesBlock(t, e);
}
function personHead(e) {
  const t = 'person', x = e.e, lab = e.label, a = entDec(t, e) || {};
  const cands = new Map(); for (const nm of e.names) for (const c of nm.f[5] || []) if (!cands.has(c[0])) cands.set(c[0], c);
  if (x[1] && !cands.has(x[1])) cands.set(x[1], [x[1], 'im Graph verknüpft', '']);
  const chosen = a.d === 'y' ? a.qid : (a.d ? null : x[1]);
  let list = [...cands.values()].map((c, k) => '<div class="cand' + (chosen === c[0] ? ' on' : '') + '" data-qid="' + esc(c[0]) + '"><span class="k">' + (k < 9 ? k + 1 : '') + '</span><div><div class="cl">' + esc(c[1]) + (c[0] === x[1] && !a.d ? ' <span class="bd info">automatisch, ungeprüft</span>' : '') + '</div><div class="cd">' + esc(c[2] || 'keine Beschreibung') + '<span data-wdx="' + esc(c[0]) + '"></span></div></div><a class="ci" href="https://www.wikidata.org/wiki/' + esc(c[0]) + '" target="_blank" rel="noopener">' + esc(c[0]) + ' ↗</a></div>').join('');
  if (a.qid && !cands.has(a.qid)) list += '<div class="cand on"><span class="k">+</span><div><div class="cl">' + esc(a.wd_label || a.qid) + '</div><div class="cd">' + esc(a.wd_description || 'selbst gesucht') + '</div></div><a class="ci" href="https://www.wikidata.org/wiki/' + esc(a.qid) + '" target="_blank" rel="noopener">' + esc(a.qid) + ' ↗</a></div>';
  const gnd = a.gnd || (!a.d && x[2]) || '';
  const roles = {}; for (const nm of e.names) for (const mi of nm.men) { const r = P.person.men[mi][5]; if (r) for (const p of r.split('/')) roles[p] = (roles[p] || 0) + 1; }
  return '<h1 class="t">' + esc(lab) + '</h1><div class="sub">' + fmt(e.n) + ' Nennungen · ' + e.names.length + (e.names.length === 1 ? ' Name' : ' Namen') + (Object.keys(roles).length ? ' · ' + Object.entries(roles).map(([r, n]) => esc(r) + ' ' + n).join(', ') : '') + '</div>'
    + '<div class="cands">' + (list || '<div class="muted small">Keine Wikidata-Kandidaten. Unten suchen oder ✗ „Keine Normdaten“.</div>') + '</div>'
    + '<div class="row" style="margin-top:8px"><span class="small muted">GND:</span>' + (gnd ? '<a href="https://d-nb.info/gnd/' + esc(gnd) + '" target="_blank" rel="noopener">' + esc(a.gnd_label && a.gnd_label !== gnd ? a.gnd_label + ' · ' : '') + esc(gnd) + ' ↗</a> <span class="muted small">' + esc(a.gnd_info || (a.gnd ? '' : 'im Graph')) + '</span> <button class="lbtn" id="gndclear">entfernen</button>' : '<span class="small muted">noch keine</span>') + '</div>'
    + '<div class="panel"><h5>Normdaten suchen</h5><div class="row"><input type="text" class="grow ftext" id="wq" value="' + esc(lab.replace(/^(Prof\.|Dr\.|Herr|Frau|Frl\.|Lehrer|Pfarrer|Oberförster|Förster)\s+/g, '')) + '"><button class="lbtn" id="wbtn">Wikidata</button><button class="lbtn" id="gndbtn">GND</button></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" class="ftext" id="wqid" placeholder="QID, z. B. Q12345" style="width:160px"><button class="lbtn" id="wqidbtn">übernehmen</button><input type="text" class="ftext" id="gndid" placeholder="GND-ID oder d-nb.info-Link" style="width:210px"><button class="lbtn" id="gndidbtn">übernehmen</button></div><div id="wres" class="res"></div></div>';
}
function placeHead(e) {
  const x = e.e, lab = e.label, a = entDec('place', e) || {}, fix = a.fix; const lr = ((e.names.find(nm => isLabel('place', nm)) || e.names[0] || { f: [] }).f[5]) || [];
  return '<h1 class="t">' + esc(lab) + '</h1><div class="sub">' + fmt(e.n) + ' Nennungen · ' + e.names.length + (e.names.length === 1 ? ' Name' : ' Namen') + (x[6] ? ' · ' + esc(x[6]) : '') + '</div>'
    + '<dl class="facts">' + (x[1] != null ? '<dt>Im Graph</dt><dd>' + x[1] + ', ' + x[2] + (x[3] ? ' (± ' + fmt(x[3]) + ' m)' : '') + (x[7] ? ' <span class="muted small">· ' + esc(x[7]) + '</span>' : '') + '</dd>' : '<dt>Im Graph</dt><dd><span class="bd warn">keine Koordinate</span></dd>')
    + (x[4] ? '<dt>GeoNames</dt><dd><a href="https://www.geonames.org/' + esc(x[4]) + '" target="_blank" rel="noopener">' + esc(lr[7] || x[4]) + ' ↗</a>' + (lr[11] ? ' · ' + esc(lr[11]) : '') + (lr[8] ? ' · ' + esc(lr[8]) : '') + '</dd>' : '')
    + (x[5] ? '<dt>Wikidata</dt><dd><a href="https://www.wikidata.org/wiki/' + esc(x[5]) + '" target="_blank" rel="noopener">' + esc(x[5]) + ' ↗</a></dd>' : '')
    + (lr[3] ? '<dt>Hinweis</dt><dd class="small">' + esc(lr[3]) + '</dd>' : '')
    + (fix ? '<dt>Korrektur</dt><dd>' + (fix.lat ? fix.lat + ', ' + fix.lon + ' (± ' + fmt(fix.uncertainty_m) + ' m)' : 'Koordinaten wie im Graph') + (fix.geonames_id ? ' · GeoNames ' + esc(fix.geonames_id) : '') + (fix.qid ? ' · ' + esc(fix.qid) : '') + (fix.note ? ' · <span class="small">' + esc(fix.note) + '</span>' : '') + ' <button class="lbtn" id="unfix">verwerfen</button></dd>' : '') + '</dl>'
    + '<div id="map"></div><div class="maplegend"><span><i style="background:#e0542e"></i>im Graph</span><span><i style="background:#1e7a4c"></i>Korrektur</span><span><i style="background:#3a6fb0;opacity:.6"></i>Orte derselben Einträge</span><span>Klick in die Karte setzt die Lage</span></div>'
    + '<div class="panel"><h5>Lage suchen</h5><div class="row"><input type="text" class="grow ftext" id="nq" value="' + esc(lab) + '"><button class="lbtn" id="nbtn">OpenStreetMap</button><button class="lbtn" id="pwbtn">Wikidata</button><a class="lbtn" target="_blank" rel="noopener" href="https://www.geonames.org/search.html?q=' + encodeURIComponent(lab) + '">GeoNames ↗</a></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" class="ftext" id="ll" placeholder="Breite, Länge" style="width:140px"><select id="unc" class="ftext"><option value="100">± 100 m</option><option value="500">± 500 m</option><option value="1000" selected>± 1 km</option><option value="2000">± 2 km</option><option value="5000">± 5 km</option><option value="10000">± 10 km</option></select><button class="lbtn" id="llbtn">setzen</button>'
    + '<input type="text" class="ftext" id="gnid" placeholder="GeoNames-ID" style="width:120px" value="' + esc((fix && fix.geonames_id) || '') + '"><input type="text" class="ftext" id="pqid" placeholder="Wikidata-QID" style="width:110px" value="' + esc((fix && fix.qid) || '') + '"><button class="lbtn" id="idbtn">IDs übernehmen</button></div><div id="nres" class="res"></div></div>';
}
function initMap(e) {
  if (typeof L === 'undefined' || !$('#map')) return;
  const x = e.e, lab = e.label; const fix = (entDec('place', e) || {}).fix;
  map = L.map('map', { zoomSnap: .5 });
  const esri = s => 'https://server.arcgisonline.com/ArcGIS/rest/services/' + s + '/MapServer/tile/{z}/{y}/{x}';
  const base = { 'Straßenkarte': L.tileLayer(esri('World_Street_Map'), { maxZoom: 19, attribution: 'Tiles © Esri, HERE, Garmin, OpenStreetMap' }), 'Topographie': L.tileLayer(esri('World_Topo_Map'), { maxZoom: 19, attribution: 'Tiles © Esri' }), 'Luftbild': L.tileLayer(esri('World_Imagery'), { maxZoom: 19, attribution: 'Tiles © Esri, Maxar' }) };
  (base[S.ui.basemap] || base['Straßenkarte']).addTo(map); L.control.layers(base, null, { position: 'topright' }).addTo(map);
  map.on('baselayerchange', ev => { S.ui.basemap = ev.name; save(); });
  const pts = []; const entries = new Set(); for (const nm of e.names) for (const mi of nm.men) entries.add(P.place.men[mi][1]);
  const ctx = new Map(); P.place.men.forEach(m => { if (!entries.has(m[1])) return; const en = P.place.forms[m[0]][2]; if (en === e.i) return; const y = P.place.ent[en]; if (y[1] == null) return; ctx.set(en, (ctx.get(en) || 0) + 1); });
  const top = [...ctx.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40); const mx = Math.max(1, ...top.map(q => q[1]));
  for (const [en, n] of top) { const y = P.place.ent[en]; L.circleMarker([y[1], y[2]], { radius: 3 + 9 * Math.sqrt(n / mx), color: '#3a6fb0', weight: 1, fillOpacity: .35 }).bindTooltip(esc(y[0]) + ' (' + n + '× gemeinsam)').addTo(map); pts.push([y[1], y[2]]); }
  if (x[1] != null) { const ll = [x[1], x[2]]; if (+x[3]) L.circle(ll, { radius: +x[3], color: '#e0542e', weight: 1, fillOpacity: .06 }).addTo(map); L.circleMarker(ll, { radius: 8, color: '#fff', weight: 2, fillColor: '#e0542e', fillOpacity: 1 }).bindTooltip('im Graph: ' + esc(lab)).addTo(map); pts.push(ll); }
  if (fix && fix.lat) { const ll = [+fix.lat, +fix.lon]; L.circle(ll, { radius: +fix.uncertainty_m || 1000, color: '#1e7a4c', weight: 1, fillOpacity: .08 }).addTo(map); L.circleMarker(ll, { radius: 8, color: '#fff', weight: 2, fillColor: '#1e7a4c', fillOpacity: 1 }).bindTooltip('Korrektur').addTo(map); pts.push(ll); }
  if (ui.mapView && ui.mapView[0]) map.setView(ui.mapView[0], ui.mapView[1]); else if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(.25), { maxZoom: 12 }); else map.setView([48.14, 11.58], 8);
  map.on('click', ev => { L.popup().setLatLng(ev.latlng).setContent('<div style="font-size:13px">' + ev.latlng.lat.toFixed(5) + ', ' + ev.latlng.lng.toFixed(5) + '<br><button class="lbtn" id="popset">als Lage übernehmen</button></div>').openOn(map);
    setTimeout(() => { const b = document.getElementById('popset'); if (b) b.onclick = () => setPlaceFix(e, ev.latlng.lat, ev.latlng.lng, { note: 'auf der Karte gesetzt' }); }, 0); });
}
function setPlaceFix(e, lat, lon, extra) {
  const unc = (extra && extra.uncertainty_m) || +($('#unc') ? $('#unc').value : 1000);
  commit('Lage gesetzt', () => setEnt('place', e, Object.assign({}, entDec('place', e) || {}, { d: 'y', fix: Object.assign({ lat: (+lat).toFixed(5), lon: (+lon).toFixed(5), osm: '', note: '', qid: '', geonames_id: '' }, extra || {}, { uncertainty_m: unc }) })));
  afterDecision('e');
}
function pickPerson(e, qid, extra) {
  const cands = new Map(); for (const nm of e.names) for (const c of nm.f[5] || []) cands.set(c[0], c); const c = cands.get(qid) || [];
  const prev = entDec('person', e) || {};
  commit('Normdaten gewählt', () => setEnt('person', e, Object.assign({}, prev, { d: 'y', qid, wd_label: c[1] || '', wd_description: c[2] || '' }, extra || {})));
  if (!(entDec('person', e) || {}).gnd) wdClaims(qid).then(cl => { const g = claimValue(cl, 'P227'); const d = entDec('person', e) || {}; if (!g || d.gnd || d.qid !== qid) return;
    S.ent.person[e.label] = stampObj(Object.assign({}, d, { gnd: g, gnd_label: g, gnd_info: 'aus Wikidata übernommen' })); save(); if (cur.sel === e) refresh(); toast('GND aus Wikidata übernommen'); });
  afterDecision('e');
}
async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }
async function wdClaims(qid) { try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims|labels|descriptions&languages=de|en&ids=' + qid); return (j.entities || {})[qid] || {}; } catch (e) { return {}; } }
function claimValue(ent, p) { const c = ((ent.claims || {})[p] || [])[0]; return c && c.mainsnak && c.mainsnak.datavalue ? c.mainsnak.datavalue.value : null; }
const gndId = v => { const m = String(v || '').match(/(?:d-nb\.info\/gnd\/)?([0-9]+-[0-9X]|[0-9]{1,10}[0-9X])\b/); return m ? m[1] : ''; };
async function wikidataSearch(e, q) {
  const box = $('#wres'); box.innerHTML = '<div class="r muted">suche …</div>';
  try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&origin=*&language=de&uselang=de&type=item&limit=12&search=' + encodeURIComponent(q)); const res = j.search || [];
    box.innerHTML = res.length ? res.map(x => '<div class="r" data-q="' + esc(x.id) + '" data-l="' + esc(x.label || '') + '" data-dd="' + esc(x.description || '') + '"><b>' + esc(x.label || x.id) + '</b> <small>' + esc(x.id) + '</small><br><small>' + esc(x.description || '') + '</small></div>').join('') : '<div class="r muted">Keine Treffer.</div>';
    $$('.r[data-q]', box).forEach(el => el.onclick = () => pickPerson(e, el.dataset.q, { wd_label: el.dataset.l, wd_description: el.dataset.dd }));
  } catch (err) { box.innerHTML = '<div class="r muted">Wikidata nicht erreichbar (' + esc(err.message) + ').</div>'; }
}
async function gndSearch(e, q) {
  const box = $('#wres'); box.innerHTML = '<div class="r muted">suche in der GND …</div>';
  let res = [], via = 'GND (lobid)';
  try {
    const j = await getJSON('https://lobid.org/gnd/search?q=' + encodeURIComponent(q) + '&filter=type:Person&format=json&size=10');
    res = (j.member || []).map(x => ({ id: x.gndIdentifier, name: x.preferredName, info: [[(x.dateOfBirth || [])[0], (x.dateOfDeath || [])[0]].filter(Boolean).join('–'), (x.professionOrOccupation || []).map(p => p.label).slice(0, 3).join(', '), (x.placeOfActivity || []).map(p => p.label).slice(0, 2).join(', ')].filter(Boolean).join(' · ') }));
  } catch (err) {
    // lobid is not reachable from a page opened as a file: GND numbers of Wikidata persons (P227)
    via = 'GND über Wikidata';
    try {
      const sr = await getJSON('https://www.wikidata.org/w/api.php?action=query&list=search&format=json&origin=*&srlimit=12&srsearch=' + encodeURIComponent(q + ' haswbstatement:P227'));
      const ids = ((sr.query || {}).search || []).map(x => x.title);
      if (ids.length) { const ents = (await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims|labels|descriptions&languages=de|en&ids=' + ids.join('|'))).entities || {};
        res = ids.map(id => { const en = ents[id] || {}; const yr = pp => { const v = claimValue(en, pp); return v && v.time ? v.time.slice(1, 5) : ''; };
          return { id: claimValue(en, 'P227'), qid: id, name: ((en.labels || {}).de || (en.labels || {}).en || {}).value || id, info: [[yr('P569'), yr('P570')].filter(Boolean).join('–'), ((en.descriptions || {}).de || (en.descriptions || {}).en || {}).value || '', 'Wikidata ' + id].filter(Boolean).join(' · ') }; }).filter(x => x.id); }
    } catch (e2) { box.innerHTML = '<div class="r muted">GND und Wikidata nicht erreichbar (' + esc(e2.message) + ').</div>'; return; }
  }
  const manual = '<div class="r muted">Nicht dabei? <a href="https://lobid.org/gnd/search?q=' + encodeURIComponent(q) + '&filter=type:Person" target="_blank" rel="noopener">in der GND suchen ↗</a> und die GND-Nummer oben bei „GND-ID“ eintragen.</div>';
  box.innerHTML = (res.length ? res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.name) + '</b> <small>GND ' + esc(x.id) + ' · ' + via + '</small><br><small>' + esc(x.info) + '</small></div>').join('') : '<div class="r muted">Keine Treffer (' + via + ').</div>') + manual;
  $$('.r[data-k]', box).forEach(el => el.onclick = () => { const x = res[+el.dataset.k]; commit('GND gewählt', () => { const prev = entDec('person', e) || {}; setEnt('person', e, Object.assign({}, prev, { d: 'y', gnd: x.id, gnd_label: x.name, gnd_info: x.info }, x.qid && !prev.qid ? { qid: x.qid, wd_label: x.name, wd_description: x.info } : {})); }); afterDecision('e'); });
}
// Wikidata candidates: life dates and GND number next to each candidate
const WDX = new Map();
async function enrichCands() {
  const els = $$('#work [data-wdx]'); const need = [...new Set(els.map(el => el.dataset.wdx))].filter(q => !WDX.has(q));
  if (need.length) { try { const ents = (await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims&ids=' + need.slice(0, 40).join('|'))).entities || {};
    for (const q of need) { const en = ents[q] || {}; const yr = pp => { const v = claimValue(en, pp); return v && v.time ? v.time.slice(1, 5) : ''; }; WDX.set(q, [[yr('P569'), yr('P570')].filter(Boolean).join('–'), claimValue(en, 'P227') || ''].filter(Boolean)); } } catch (err) { return; } }
  for (const el of $$('#work [data-wdx]')) { const v = WDX.get(el.dataset.wdx); if (v && v.length) el.textContent = ' · ' + v.map((x, i) => i === 1 || /^[0-9X-]{6,}$/.test(x) && x.length > 5 && !/–/.test(x) ? 'GND ' + x : x).join(' · '); }
}
async function osmSearch(e, q) {
  const box = $('#nres'); box.innerHTML = '<div class="r muted">suche …</div>';
  try { const res = await getJSON('https://nominatim.openstreetmap.org/search?format=jsonv2&extratags=1&limit=10&accept-language=de&q=' + encodeURIComponent(q));
    box.innerHTML = res.length ? res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.name || x.display_name.split(',')[0]) + '</b> <small>' + esc(x.category + '/' + x.type) + '</small><br><small>' + esc(x.display_name) + '</small></div>').join('') : '<div class="r muted">Keine Treffer.</div>';
    $$('.r[data-k]', box).forEach(el => { const x = res[+el.dataset.k];
      el.onmouseenter = () => { if (map) { if (map._hover) map.removeLayer(map._hover); map._hover = L.circleMarker([+x.lat, +x.lon], { radius: 8, color: '#1e7a4c', dashArray: '3', fillOpacity: .2 }).addTo(map); } };
      el.onclick = async () => { const unc = ['city', 'town', 'administrative'].includes(x.type) ? 5000 : ['village', 'suburb'].includes(x.type) ? 2000 : 1000;
        const qid = ((x.extratags || {}).wikidata || '').match(/^Q\d+$/) ? x.extratags.wikidata : ''; const g = qid ? claimValue(await wdClaims(qid), 'P1566') || '' : '';
        setPlaceFix(e, +x.lat, +x.lon, { osm: x.osm_type + '/' + x.osm_id, note: x.display_name.slice(0, 160), uncertainty_m: unc, qid, geonames_id: g }); }; });
  } catch (err) { box.innerHTML = '<div class="r muted">OpenStreetMap nicht erreichbar (' + esc(err.message) + ').</div>'; }
}
async function placeWikidataSearch(e, q) {
  const box = $('#nres'); box.innerHTML = '<div class="r muted">suche …</div>';
  try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&origin=*&language=de&uselang=de&type=item&limit=12&search=' + encodeURIComponent(q)); const res = j.search || [];
    box.innerHTML = res.length ? res.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.label || x.id) + '</b> <small>' + esc(x.id) + '</small><br><small>' + esc(x.description || '') + '</small></div>').join('') : '<div class="r muted">Keine Treffer.</div>';
    $$('.r[data-k]', box).forEach(el => el.onclick = async () => { const x = res[+el.dataset.k]; const ent = await wdClaims(x.id); const c = claimValue(ent, 'P625'); const g = claimValue(ent, 'P1566');
      const ids = { qid: x.id, geonames_id: g || '', note: (x.label || '') + (x.description ? ', ' + x.description : '') };
      if (c) setPlaceFix(e, c.latitude, c.longitude, ids); else { commit('IDs gesetzt', () => setEnt('place', e, Object.assign({}, entDec('place', e) || {}, { d: 'y', fix: Object.assign({}, (entDec('place', e) || {}).fix || {}, ids) }))); toast('Wikidata-Eintrag ohne Koordinaten'); } });
  } catch (err) { box.innerHTML = '<div class="r muted">Wikidata nicht erreichbar (' + esc(err.message) + ').</div>'; }
}

// ---------------------------------------------------------------- readings (transcription corrections)
function tokens(s) { return s.match(/\s+|[\p{L}\p{N}]+|[^\s\p{L}\p{N}]/gu) || []; }
function applyReadings(orig, hunks) {
  const hs = hunks.map(h => ({ h, i: orig.indexOf(h.old) })).filter(x => x.i >= 0).sort((a, b) => a.i - b.i);
  let out = '', pos = 0; for (const { h, i } of hs) { if (i < pos) continue; out += orig.slice(pos, i) + h.new; pos = i + h.old.length; }
  return out + orig.slice(pos);
}
function diffHunks(a, b) {
  // token LCS -> changed spans, each widened by whole tokens until its old text is unique in ``a``
  const A = tokens(a), B = tokens(b); let p = 0; while (p < A.length && p < B.length && A[p] === B[p]) p++;
  let q = 0; while (q < A.length - p && q < B.length - p && A[A.length - 1 - q] === B[B.length - 1 - q]) q++;
  const a2 = A.slice(p, A.length - q), b2 = B.slice(p, B.length - q); const n = a2.length, m = b2.length;
  let spans = [];
  if (!n && !m) return [];
  if (n * m > 4e6 || !n || !m) spans = [[p, A.length - q, p, B.length - q]];
  else {
    const W = m + 1; const dp = new Uint32Array((n + 1) * W);
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i * W + j] = a2[i] === b2[j] ? dp[(i + 1) * W + j + 1] + 1 : Math.max(dp[(i + 1) * W + j], dp[i * W + j + 1]);
    let i = 0, j = 0, open = null;
    while (i < n || j < m) {
      if (i < n && j < m && a2[i] === b2[j]) { if (open) { spans.push([open[0] + p, i + p, open[1] + p, j + p]); open = null; } i++; j++; }
      else { if (!open) open = [i, j]; if (j < m && (i === n || dp[i * W + j + 1] >= dp[(i + 1) * W + j])) j++; else i++; }
    }
    if (open) spans.push([open[0] + p, n + p, open[1] + p, m + p]);
  }
  const offA = [0]; for (const t of A) offA.push(offA[offA.length - 1] + t.length);
  const offB = [0]; for (const t of B) offB.push(offB[offB.length - 1] + t.length);
  const count = (s, x) => { let c = 0, i = s.indexOf(x); while (i >= 0) { c++; i = s.indexOf(x, i + 1); } return c; };
  let changed = true;
  while (changed) {
    changed = false;
    for (const s of spans) {
      let guard = 0;
      while (guard++ < 60) { const old = a.slice(offA[s[0]], offA[s[1]]); if (old.trim() && count(a, old) === 1) break;
        const canL = s[0] > 0, canR = s[1] < A.length; if (!canL && !canR) break;
        if (canL) { s[0]--; s[2]--; } if (canR) { s[1]++; s[3]++; } }
    }
    spans.sort((x, y) => x[0] - y[0]);
    for (let k = 0; k + 1 < spans.length; k++) if (spans[k][1] >= spans[k + 1][0]) { spans[k] = [spans[k][0], Math.max(spans[k][1], spans[k + 1][1]), spans[k][2], Math.max(spans[k][3], spans[k + 1][3])]; spans.splice(k + 1, 1); changed = true; break; }
  }
  return spans.map(s => ({ old: a.slice(offA[s[0]], offA[s[1]]), new: b.slice(offB[s[2]], offB[s[3]]) })).filter(h => h.old !== h.new);
}
function setReadings(ei, hunks, note, src) {
  const e = E[ei];
  S.text = S.text.filter(c => c.entry_uid !== e[1]);
  hunks.forEach((h, k) => S.text.push(stampObj({ id: e[1] + ':' + Date.now().toString(36) + k, entry_uid: e[1], entry_id: e[0], old: h.old, new: h.new, note: h.note != null ? h.note : (note || ''), src: src || 'editor' })));
}
function openEditor(ei, s, e0, t, mi) {
  const e = E[ei]; const orig = e[7]; const hunks = readingFor(ei); const curText = applyReadings(orig, hunks);
  let loc = t != null && mi != null ? P[t].men[mi][4] : null;
  if (!(Array.isArray(loc) && loc.length === 5)) loc = null;
  $('#modal').innerHTML = '<div class="editor"><button class="lbtn x" data-close>Schließen ✕</button><h2>Lesung korrigieren · ' + esc(e[0]) + '</h2><p class="small muted">' + esc(e[3] || e[2]) + ' · ' + esc(e[8].length ? pageLabel(e[8][0]) : '') + '. Den Text so ändern, wie er im Scan steht (die Seite ist rechts zu sehen). Der Eintrag wird später mit dieser Lesung neu ausgewertet; Art, Anzahl, Ort und Datum ergeben sich daraus.</p>'
    + (loc ? '<div class="edsnip">' + snipHtml(loc, 2.4) + '</div>' : '')
    + '<textarea id="edtext" spellcheck="false">' + esc(curText) + '</textarea><div class="diff" id="eddiff"></div>'
    + '<div class="row" style="margin-top:10px"><input type="text" class="grow ftext" id="ednote" placeholder="Anmerkung (optional)" value="' + esc((hunks[0] || {}).note || '') + '"><button class="btn y" id="edsave">Speichern <kbd>Strg+⏎</kbd></button>' + (hunks.length ? '<button class="btn n" id="edreset">Original wiederherstellen</button>' : '') + '</div></div>';
  $('#ovModal').classList.add('show'); wireSnips($('#modal'));
  if (loc) scanFor(t, mi); else showScan(ei);
  const ta = $('#edtext'); const upd = () => { const hs = diffHunks(orig, ta.value); $('#eddiff').innerHTML = hs.length ? hs.map(h => '<div><del>' + esc(h.old) + '</del> → <ins>' + esc(h.new) + '</ins></div>').join('') : '<span class="muted">keine Änderung gegenüber der Transkription</span>'; };
  ta.oninput = upd; upd();
  ta.focus();
  if (s != null && s >= 0) { const word = orig.slice(s, e0); let i = hunks.length ? curText.indexOf(word) : s; if (i < 0) i = Math.min(s, curText.length); ta.setSelectionRange(i, i + (e0 - s)); const before = curText.slice(0, i); ta.scrollTop = Math.max(0, (before.split('\n').length - 3) * 22 + before.length / 90 * 22 - 60); }
  const doSave = () => { const hs = diffHunks(orig, ta.value); commit('Lesung', () => setReadings(ei, hs, $('#ednote').value.trim())); closeModal(); toast(hs.length ? hs.length + (hs.length === 1 ? ' Änderung' : ' Änderungen') + ' gespeichert' : 'Lesung zurückgesetzt'); };
  $('#edsave').onclick = doSave; ta.onkeydown = ev => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); doSave(); } };
  const rs = $('#edreset'); if (rs) rs.onclick = () => { commit('Lesung zurückgesetzt', () => setReadings(ei, [], '')); closeModal(); };
}
function closeModal() { $('#ovModal').classList.remove('show'); }
$('#ovModal').addEventListener('click', e => { if (e.target.id === 'ovModal' || e.target.closest('[data-close]')) closeModal(); });

// ---------------------------------------------------------------- second reading
function acceptSug(mi, batch) {
  const s = SUG[mi]; if (!s) return;
  const t = 'taxon'; const m = P.taxon.men[mi]; const ei = m[1]; const text = E[ei][7]; const curEnt = P.taxon.forms[m[0]][2];
  const run = () => {
    if (!s[1] && m[2] >= 0) {
      const old = text.slice(m[2], m[3]); let rd = String(s[0]).trim(); if (!/[.,;:]$/.test(old)) rd = rd.replace(/[.,;:]+$/, '');
      if (fold(rd).replace(/[^a-z]/g, '') !== fold(old).replace(/[^a-z]/g, '')) {
        const hs = readingFor(ei).map(h => ({ old: h.old, new: h.new, note: h.note }));
        const edited = applyReadings(text, hs);
        let pos = m[2];
        if (hs.length) { const shift = applyReadings(text.slice(0, m[2]), hs.filter(h => text.indexOf(h.old) + h.old.length <= m[2])).length - m[2]; pos = m[2] + shift; if (edited.slice(pos, pos + old.length) !== old) pos = edited.indexOf(old); }
        if (pos >= 0) { const next = edited.slice(0, pos) + rd + edited.slice(pos + old.length); const nh = diffHunks(text, next).map(h => Object.assign(h, { note: (hs.find(x => x.old === h.old) || {}).note || 'Zweitlesung (Modell)' })); setReadings(ei, nh, 'Zweitlesung (Modell)', 'model'); }
      }
    }
    if (s[2] === 'bird') {
      if (s[7] >= 0) { const te = P.taxon.ent[s[7]]; setMen(t, mi, s[7] === curEnt ? { d: 'y', note: 'Zweitlesung' } : { d: 'r', target: { label: te[0], sci: te[1], key: te[2], rank: te[3] }, note: 'Zweitlesung' }); }
      else if (s[4] || s[3]) setMen(t, mi, { d: 'r', target: { label: s[3] || s[0], sci: s[4] }, note: 'Zweitlesung (Art nicht im Graph)' });
    } else setMen(t, mi, { d: 'n', reason: { place: 'place', person: 'person', other_animal: 'non-bird' }[s[2]] || 'misread', note: 'Zweitlesung' });
  };
  if (batch) run(); else { commit('Zweitlesung übernommen', run); afterDecision('m:' + mi); }
}

// ---------------------------------------------------------------- sample and hints
function wilson(k, n) { if (!n) return [0, 0, 0]; const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [p, Math.max(0, c - h), Math.min(1, c + h)]; }
function evalStats() { const by = {}; let k = 0, n = 0; for (const mi of P.sample) { const d = S.ev[X.taxon.mkey[mi]]; if (!d || (d.d !== 'y' && d.d !== 'n')) continue; const c = P.taxon.forms[P.taxon.men[mi][0]][3]; by[c] = by[c] || [0, 0]; by[c][1]++; n++; if (d.d === 'y') { k++; by[c][0]++; } } return { k, n, by }; }
function evalView(it) {
  const mi = it.mi; const m = P.taxon.men[mi]; const f = P.taxon.forms[m[0]]; const x = P.taxon.ent[f[2]]; const d = S.ev[it.key] || {};
  const st = evalStats(); const [p, lo, hi] = wilson(st.k, st.n);
  const b = (k, label, key) => '<button class="btn ' + k + (d.d === k ? ' on' : '') + '" data-sa="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  return crumb() + '<div class="card"><div class="cb"><div class="row"><div><div class="small muted">Genauigkeit der Artbestimmung</div><div class="big">' + (st.n ? pct(p) : '–') + '</div><div class="small muted">' + (st.n ? '95 %-Intervall ' + pct(lo) + ' – ' + pct(hi) + ' · ' + st.k + ' von ' + st.n + ' richtig' : 'noch nichts beurteilt') + '</div></div><div class="sp"></div><div class="small muted">' + Object.entries(st.by).map(([c, [a, bb]]) => esc(TT.taxon.cls[c][0]) + ' ' + a + '/' + bb).join(' · ') + '</div></div></div></div>'
    + '<div class="card"><div class="cb"><h1 class="t">' + esc(f[0]) + ' → ' + esc(x[0]) + (x[1] ? ' <i>' + esc(x[1]) + '</i>' : '') + '</h1><div class="sub">Beleg ' + (it.k + 1) + ' von ' + P.sample.length + ' (zufällig gezogen). Ist an dieser Stelle diese Art gemeint? Der Reihe nach beurteilen, nichts auslassen.</div>'
    + '<div class="acts" data-f="e">' + b('y', 'Richtig bestimmt', 'Y') + b('n', 'Falsch', 'N') + b('u', 'Nicht entscheidbar', 'U') + '</div>'
    + (d.d === 'n' && d.target ? '<div class="state r">Richtig wäre: <b>' + esc(d.target.label) + '</b> <i>' + esc(d.target.sci || '') + '</i></div>' : '')
    + (ui.panel && ui.panel.scope === 'ev' ? panelHtml('taxon', ui.panel) : '') + '</div></div>' + menHtml('taxon', mi, { noActs: true });
}
function qaView(it) {
  const r = it.r; const q = QA_DE[r[2]] || [r[2], '']; const d = S.qa[it.key] || {};
  const b = (k, label, key) => '<button class="btn ' + k + (d.d === k ? ' on' : '') + '" data-sa="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  const isTaxon = ['non_bird', 'low_confidence_taxon'].includes(r[2]) && r[4]; const md = isTaxon ? S.men.taxon[r[1] + '|' + lc(r[4]) + '|0'] : null;
  let entry = '<div class="card"><div class="cb muted">Eintrag nicht mehr im Graph, kein Text verfügbar.</div></div>';
  if (it.ei >= 0) {
    const e = E[it.ei]; const i = r[4] && !/^\d+$/.test(r[4]) ? lc(e[7]).indexOf(lc(r[4])) : -1; const hs = readingFor(it.ei);
    entry = '<div class="men" data-ei="' + it.ei + '"><div class="mh">' + entryHead(it.ei) + '<span class="sp"></span><button class="lbtn" data-scanentry="' + it.ei + '">Scan</button><button class="mb" data-edit="' + it.ei + '" data-s="' + i + '" data-e="' + (i >= 0 ? i + r[4].length : -1) + '" title="Lesung korrigieren (E)">✎</button></div>'
      + '<div class="kw">' + (i >= 0 ? highlight(e[7], i, i + r[4].length) : esc(e[7])) + '</div>' + hs.map(h => '<div class="note t">✎ Lesung: „' + esc(h.old) + '“ → „<b>' + esc(h.new) + '</b>“</div>').join('') + '</div>';
  }
  return crumb() + '<div class="card"><div class="cb"><h1 class="t">' + esc(q[0]) + (r[4] && ['non_bird', 'low_confidence_taxon', 'nonplace'].includes(r[2]) ? ' · ' + esc(r[4]) : '') + '</h1><div class="sub">' + esc(q[1]) + ' <span class="bd ' + (r[3] === 'excluded' ? 'risk' : 'warn') + '">' + (r[3] === 'excluded' ? 'entfernt' : 'nur markiert') + '</span></div>'
    + '<dl class="facts"><dt>Eintrag</dt><dd>' + esc(r[0]) + '</dd><dt>Begründung</dt><dd>' + esc(r[5]) + '</dd></dl>'
    + '<div class="acts" data-f="e">' + b('y', 'Richtig erkannt', 'Y') + b('n', 'Falsch erkannt', 'N') + b('u', 'Unsicher', 'U') + '</div>'
    + (isTaxon ? (md && md.target ? '<div class="state r">Richtige Art in diesem Eintrag: <b>' + esc(md.target.label) + '</b> <i>' + esc(md.target.sci || '') + '</i> <button class="lbtn" id="qaunfix">verwerfen</button></div>' : panelHtml('taxon', { scope: 'qa', kind: 'r', title: 'Doch ein Vogel? Richtige Art' })) : '')
    + '<div class="row" style="margin-top:8px"><input type="text" class="grow ftext" id="qanote" placeholder="Anmerkung / Korrektur, falls bekannt" value="' + esc(d.note || '') + '"></div>'
    + '<div class="hint">Falsch gelesenes Datum oder Wort: im Eintrag unten ✎ „Lesung korrigieren“ (<kbd>E</kbd>).</div></div></div>' + entry;
}

// ---------------------------------------------------------------- wiring
function wireWork() {
  const W = $('#work');
  const adv = $('#adv'); if (adv) adv.onchange = () => { S.ui.adv = adv.checked; save(); };
  const fol = $('#follow'); if (fol) fol.onchange = () => { S.ui.follow = fol.checked; save(); };
  $$('.rpanel', W).forEach(root => { const q = root.querySelector('.rq'); q.oninput = () => renderLocalResults(root); const g = root.querySelector('.rgbif'); if (g) g.onclick = () => gbifSearch(root); const mt = root.querySelector('.rmatch'); if (mt) mt.onchange = () => renderLocalResults(root); });
  const bulk = $('#bulk'); if (bulk) bulk.onclick = () => bulkNames(cur.tab, cur.sel);
  const e = cur.sel;
  if (cur.tab === 'person') {
    $$('.cand[data-qid]', W).forEach(c => c.onclick = ev => { if (ev.target.closest('a')) return; pickPerson(e, c.dataset.qid); });
    $('#wbtn').onclick = () => wikidataSearch(e, $('#wq').value); $('#wq').onkeydown = ev => { if (ev.key === 'Enter') wikidataSearch(e, $('#wq').value); };
    $('#gndbtn').onclick = () => gndSearch(e, $('#wq').value);
    $('#wqidbtn').onclick = () => { const q = ($('#wqid').value.match(/Q\d+/i) || [''])[0].toUpperCase(); if (!q) return toast('Ungültige QID'); pickPerson(e, q, { wd_label: q, wd_description: 'von Hand eingetragen' }); };
    $('#gndidbtn').onclick = () => { const g = gndId($('#gndid').value); if (!g) return toast('Ungültige GND-ID'); commit('GND', () => setEnt('person', e, Object.assign({}, entDec('person', e) || {}, { d: 'y', gnd: g, gnd_label: g, gnd_info: 'von Hand eingetragen' }))); };
    enrichCands();
    const gc = $('#gndclear'); if (gc) gc.onclick = () => commit('GND entfernt', () => { const d = Object.assign({}, entDec('person', e) || {}); d.gnd = null; d.gnd_label = null; d.gnd_info = null; if (!d.d) d.d = d.qid || e.e[1] ? 'y' : 'n'; if (!d.qid && d.d === 'y') d.qid = e.e[1] || null; setEnt('person', e, d); });
  }
  if (cur.tab === 'place') {
    initMap(e);
    $('#nbtn').onclick = () => osmSearch(e, $('#nq').value); $('#nq').onkeydown = ev => { if (ev.key === 'Enter') osmSearch(e, $('#nq').value); };
    $('#pwbtn').onclick = () => placeWikidataSearch(e, $('#nq').value);
    $('#idbtn').onclick = () => { const g = ($('#gnid').value.match(/\d{3,}/) || [''])[0], q = ($('#pqid').value.match(/Q\d+/i) || [''])[0].toUpperCase(); if (!g && !q) return toast('GeoNames-ID oder QID eintragen');
      commit('IDs gesetzt', () => setEnt('place', e, Object.assign({}, entDec('place', e) || {}, { d: 'y', fix: Object.assign({}, (entDec('place', e) || {}).fix || {}, { geonames_id: g, qid: q }) }))); };
    $('#llbtn').onclick = () => { const m = $('#ll').value.replace(/,(\d)/g, '.$1').match(/(-?\d+(?:\.\d+)?)[\s;,]+(-?\d+(?:\.\d+)?)/); if (!m) return toast('Format: 48.137, 11.575'); setPlaceFix(e, +m[1], +m[2], { note: 'von Hand eingetragen' }); };
    const uf = $('#unfix'); if (uf) uf.onclick = () => commit('Lage verworfen', () => { const d = Object.assign({}, entDec('place', e) || {}); delete d.fix; if (d.d === 'y' && e.e[1] == null) delete d.d; setEnt('place', e, d.d ? d : null); });
  }
  const qn = $('#qanote'); if (qn) qn.oninput = () => { clearTimeout(qn.t); qn.t = setTimeout(() => { const it = cur.sel; S.qa[it.key] = Object.assign({}, S.qa[it.key] || {}, { note: qn.value.trim(), by: S.who, t: (S.qa[it.key] || {}).t || new Date().toISOString() }); save(); }, 400); };
  const qu = $('#qaunfix'); if (qu) qu.onclick = () => commit('verworfen', () => { delete S.men.taxon[cur.sel.r[1] + '|' + lc(cur.sel.r[4]) + '|0']; });
}
$('#work').addEventListener('click', ev => {
  const t0 = ev.target;
  const nav = t0.closest('[data-nav]'); if (nav) return nextItem(+nav.dataset.nav);
  const ea = t0.closest('[data-ea]'); if (ea) { cur.focus = 'e'; if (ea.dataset.ea === '') { commit('zurückgesetzt', () => setEnt(cur.tab, cur.sel, null)); return; } return entAct(cur.tab, cur.sel, ea.dataset.ea); }
  const sa = t0.closest('[data-sa]'); if (sa) return simpleDecide(sa.dataset.sa);
  const sp = t0.closest('[data-special]'); if (sp) { const root = sp.closest('.rpanel'); return special(root.dataset.kind, root.dataset.scope, sp.dataset.special); }
  const rs = t0.closest('[data-reason]'); if (rs) { const root = rs.closest('[data-scope]'); return reason(cur.tab, root.dataset.scope, rs.dataset.reason); }
  const sg = t0.closest('[data-sug]'); if (sg) return acceptSug(+sg.dataset.sug);
  const mg = t0.closest('[data-merge]'); if (mg && TYPES.includes(cur.tab)) return mergeInto(cur.tab, cur.sel, X[cur.tab].ents[+mg.dataset.merge]);
  const gq = t0.closest('[data-gbifq]'); if (gq) { openPanel('e', 'r', gq.dataset.gbifq, 'GBIF-Art zuordnen'); const root = $('#work .rpanel[data-scope="e"]'); if (root) gbifSearch(root); return; }
  const sll = t0.closest('[data-setll]'); if (sll) { const [la, lo] = sll.dataset.setll.split(','); return setPlaceFix(cur.sel, +la, +lo, { note: 'Gazetteer-Vorschlag', uncertainty_m: 2000 }); }
  const sgall = t0.closest('[data-sugall]'); if (sgall) { const nm = X.taxon.names[+sgall.dataset.sugall]; const { top } = sugGroups(nm); commit('Zweitlesung für ' + top.length + ' Belege', () => top.forEach(mi => acceptSug(mi, true))); afterDecision('n:' + nm.fi); return; }
  const am = t0.closest('[data-allmen]'); if (am) { ui.all.add(+am.dataset.allmen); return renderWork(false); }
  const fu = t0.closest('[data-full]'); if (fu) { const k = fu.closest('.men').dataset.t + fu.dataset.full; ui.full.has(k) ? ui.full.delete(k) : ui.full.add(k); return renderWork(false); }
  const mc = t0.closest('[data-mclear]'); if (mc) { const card = mc.closest('.men'); return commit('zurückgesetzt', () => setMen(card.dataset.t, +card.dataset.mi, null)); }
  const ed = t0.closest('[data-edit]'); if (ed) return openEditor(+ed.dataset.edit, +ed.dataset.s, +ed.dataset.e);
  const se = t0.closest('[data-scanentry]'); if (se) return showScan(+se.dataset.scanentry);
  const ma = t0.closest('[data-ma]'); if (ma) { const card = ma.closest('.men'); const mi = +card.dataset.mi; const t = card.dataset.t; if (TYPES.includes(cur.tab)) setFocus('m:' + mi, true);
    if (ma.dataset.ma === 'e') { const m = P[t].men[mi]; return openEditor(m[1], m[2], m[3], t, mi); } return act(ma.dataset.ma); }
  const na = t0.closest('[data-na]'); if (na) { const fi = +na.closest('.nm').dataset.fi; setFocus('n:' + fi, true); return act(na.dataset.na); }
  const sn = t0.closest('.snip'); if (sn) { const card = sn.closest('.men'); if (card && card.dataset.mi) { const t = card.dataset.t, mi = +card.dataset.mi; if (TYPES.includes(cur.tab)) setFocus('m:' + mi, true); return scanFor(t, mi); } }
  const nh = t0.closest('.nh'); if (nh && !t0.closest('button') && !t0.closest('a')) { const fi = +nh.closest('.nm').dataset.fi; ui.open.has(fi) ? ui.open.delete(fi) : ui.open.add(fi); cur.focus = 'n:' + fi; return renderWork(false); }
  const card = t0.closest('.men[data-mi]'); if (card && !t0.closest('button') && !t0.closest('a') && TYPES.includes(cur.tab)) setFocus('m:' + card.dataset.mi);
});
document.addEventListener('keydown', ev => {
  if (panelKeys(ev)) return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (ev.key === 'Escape') { if ($('#ovModal').classList.contains('show')) return closeModal(); if (ui.panel) { ui.panel = null; renderWork(false); if (cur.tab === 'eval' && S.ui.adv && (S.ev[cur.sel.key] || {}).d) nextItem(1); return; } if (tag === 'input' || tag === 'textarea') ev.target.blur(); return; }
  if ((ev.ctrlKey || ev.metaKey) && lc(ev.key) === 'k') { ev.preventDefault(); return openSearch(); }
  if ((ev.ctrlKey || ev.metaKey) && lc(ev.key) === 'z' && tag !== 'input' && tag !== 'textarea') { ev.preventDefault(); return undo(); }
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if ($('#ovModal').classList.contains('show')) return;
  const k = ev.key; const kl = lc(k);
  if (ui.panel && ui.panel.kind === 'not' && /^[1-9]$/.test(k)) { const t = TYPES.includes(cur.tab) ? cur.tab : 'taxon'; const opt = TT[t].not[+k - 1]; if (opt) { ev.preventDefault(); return reason(t, ui.panel.scope, opt[0]); } }
  if (k === 'ArrowLeft' || k === 'ArrowRight') { if (scan.p >= 0) { ev.preventDefault(); (k === 'ArrowLeft' ? $('#scanprev') : $('#scannext')).click(); } return; }
  if (kl === 'j' || k === 'ArrowDown') { ev.preventDefault(); return moveFocus(1); }
  if (kl === 'k' || k === 'ArrowUp') { ev.preventDefault(); return moveFocus(-1); }
  if (k === 'Enter') { ev.preventDefault(); return nextItem(ev.shiftKey ? -1 : 1); }
  if (k === ' ') { ev.preventDefault(); if (!TYPES.includes(cur.tab)) return; const f = cur.focus || ''; const fi = f.startsWith('n:') ? +f.slice(2) : f.startsWith('m:') ? P[cur.tab].men[+f.slice(2)][0] : null; if (fi != null) { ui.open.has(fi) ? ui.open.delete(fi) : ui.open.add(fi); cur.focus = 'n:' + fi; renderWork(false); } return; }
  if (ev.shiftKey && /^[A-E]$/.test(k) && TYPES.includes(cur.tab)) { const c = $$('#work .cand[data-merge]')[k.charCodeAt(0) - 65]; if (c) { ev.preventDefault(); c.click(); } return; }
  if (['y', 'a', 'n', 'u', 'e', 'g', 'z', 'b'].includes(kl)) ev.preventDefault();
  if (kl === 'y') return act('y'); if (kl === 'a') return act('r'); if (kl === 'n') return act('n'); if (kl === 'u') return act('u');
  if (kl === 'e') { const f = cur.focus || ''; if (f.startsWith('m:')) { const el = $('#work [data-f="' + f + '"]'); const t = el.dataset.t; const mi = +f.slice(2); const m = P[t].men[mi]; return openEditor(m[1], m[2], m[3], t, mi); } const q = $('#work [data-edit], #work .men [data-ma="e"]'); if (q) q.click(); return; }
  if (kl === 'g') { const f = cur.focus || ''; if (cur.tab !== 'taxon') return; if (f.startsWith('m:') && SUG[+f.slice(2)]) return acceptSug(+f.slice(2)); if (f.startsWith('n:')) { const b = $('#work [data-sugall="' + f.slice(2) + '"]'); if (b) b.click(); } return; }
  if (kl === 'z') return undo();
  if (kl === 'b') { S.ui.noscan = !$('#main').classList.contains('noscan'); $('#main').classList.toggle('noscan', S.ui.noscan); save(); return; }
  if (k === '/') { ev.preventDefault(); return $('#qsearch').focus(); }
  if (k === '?') return showHelp();
  if (/^[1-9]$/.test(k) && cur.tab === 'person') { const c = $$('#work .cand[data-qid]')[+k - 1]; if (c) c.click(); }
  if (ev.shiftKey && /^[A-E]$/.test(k) && TYPES.includes(cur.tab)) { const c = $$('#work .cand[data-merge]')[k.charCodeAt(0) - 65]; if (c) c.click(); }
});

// ---------------------------------------------------------------- global search
function openSearch() {
  $('#modal').innerHTML = '<div class="gsearch"><button class="lbtn x" data-close>✕</button><h2>Alles durchsuchen</h2><input id="gq" placeholder="Art, Person, Ort, Lebensraum oder geschriebener Name …" autocomplete="off"><div class="res" id="gres" style="max-height:60vh"></div></div>';
  $('#ovModal').classList.add('show'); const inp = $('#gq'); inp.focus(); let hi = 0, rows = [];
  const run = () => { const f = fold(inp.value.trim()); rows = []; if (f.length < 2) { $('#gres').innerHTML = ''; return; }
    for (const t of TYPES) for (const e of X[t].ents) { if (!e.names.length) continue; const hay = [e.label, t === 'taxon' ? e.e[1] : '', ...e.names.map(x => x.name)]; const i = hay.findIndex(h => fold(h).includes(f)); if (i < 0) continue;
      const lab = fold(e.label); const words = lab.split(/[^a-z0-9]+/);
      rows.push({ t, e, score: lab === f ? 0 : words.includes(f) ? 1 : lab.startsWith(f) || words.some(w => w.startsWith(f)) ? 2 : 3, via: i > 1 ? hay[i] : '' }); }
    rows.sort((a, b) => a.score - b.score || b.e.n - a.e.n); rows = rows.slice(0, 40); hi = 0;
    $('#gres').innerHTML = rows.length ? rows.map((r, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '"><span class="bd plain">' + esc(TT[r.t].tab) + '</span> <b>' + esc(r.e.label) + '</b>' + (r.t === 'taxon' && r.e.e[1] ? ' <i>' + esc(r.e.e[1]) + '</i>' : '') + (r.via ? ' <small>(als „' + esc(r.via) + '“)</small>' : '') + ' <small>· ' + fmt(r.e.n) + '</small> <span class="dot ' + entState(r.t, r.e) + '" style="vertical-align:-1px"></span></div>').join('') : '<div class="r muted">Nichts gefunden.</div>';
    $$('#gres .r[data-k]').forEach(el => el.onclick = () => go(rows[+el.dataset.k])); };
  const go = r => { closeModal(); if (cur.tab !== r.t) openTab(r.t, selKey(r.e)); else selectItem(r.e); };
  inp.oninput = run;
  inp.onkeydown = ev => { const rs = $$('#gres .r[data-k]'); if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { ev.preventDefault(); hi = Math.max(0, Math.min(rs.length - 1, hi + (ev.key === 'ArrowDown' ? 1 : -1))); rs.forEach((r, i) => r.classList.toggle('hi', i === hi)); }
    if (ev.key === 'Enter' && rows[hi]) go(rows[hi]); };
}
$('#btnSearch').onclick = openSearch;
$('#btnUndo').onclick = undo;

// ---------------------------------------------------------------- change log
function logRows() {
  const rows = [];
  for (const t of TYPES) {
    for (const k in S.ent[t]) { const d = S.ent[t][k]; if (d.d) rows.push({ scope: 'ent', t, key: k, what: k + ': ' + entStateText(t, { e: [], label: k }, d).replace(/<[^>]+>/g, ''), by: d.by || '', at: d.t || '' }); }
    for (const k in S.id[t]) { const d = S.id[t][k]; if (d.d) rows.push({ scope: 'id', t, key: k, what: 'Name „' + ((X[t].byKey.get(k) || [{ name: k }])[0].name) + '“: ' + decLine(t, d).replace(/<[^>]+>/g, ''), by: d.by || '', at: d.t || '' }); }
    for (const k in S.men[t]) { const d = S.men[t][k]; if (!d.d) continue; const [uid, name] = k.split('|'); const ei = uid2e.get(uid); rows.push({ scope: 'men', t, key: k, what: 'Beleg „' + (d.written || name) + '“ in ' + (ei != null ? E[ei][0] : uid) + ': ' + decLine(t, d).replace(/<[^>]+>/g, ''), by: d.by || '', at: d.t || '' }); }
  }
  for (const c of S.text) rows.push({ scope: 'text', t: 'text', key: c.id, what: 'Lesung ' + c.entry_id + ': „' + c.old + '“ → „' + c.new + '“' + (c.note ? ' (' + c.note + ')' : ''), by: c.by || '', at: c.t || '' });
  for (const k in S.ev) { const d = S.ev[k]; if (d.d) rows.push({ scope: 'ev', t: 'eval', key: k, what: 'Stichprobe „' + k.split('|')[1] + '“: ' + ({ y: 'richtig', n: 'falsch', u: 'unklar' }[d.d]) + (d.target ? ' → ' + d.target.label : ''), by: d.by || '', at: d.t || '' }); }
  for (const k in S.qa) { const d = S.qa[k]; if (d.d) rows.push({ scope: 'qa', t: 'qa', key: k, what: 'Hinweis ' + k.replace(/\|/g, ' · ') + ': ' + ({ y: 'richtig erkannt', n: 'falsch erkannt', u: 'unsicher' }[d.d]), by: d.by || '', at: d.t || '' }); }
  return rows.sort((a, b) => (b.at || '').localeCompare(a.at || ''));
}
function renderLog() {
  const rows = logRows(); const st = evalStats(); const [p, lo, hi] = wilson(st.k, st.n);
  const AREA = { taxon: 'Arten', person: 'Personen', place: 'Orte', habitat: 'Lebensräume', text: 'Lesung', eval: 'Stichprobe', qa: 'Hinweis' };
  let h = '<div class="wrap"><h1 class="t">Änderungen und Stand</h1><div class="sub">Alle Entscheidungen, neueste zuerst. Einzelne Zeilen lassen sich entfernen.</div><div class="stats" style="margin-top:12px">';
  for (const t of TYPES) { let d = 0, tot = 0; for (const e of X[t].ents) if (e.review) { tot++; if (DONE(entState(t, e))) d++; } h += '<div class="stat"><div class="n">' + fmt(d) + ' <span class="small muted">/ ' + fmt(tot) + '</span></div><div class="l">' + esc(TT[t].tab) + ' geprüft</div></div>'; }
  h += '<div class="stat"><div class="n">' + fmt(S.text.length) + '</div><div class="l">korrigierte Lesungen</div></div><div class="stat"><div class="n">' + (st.n ? pct(p) : '–') + '</div><div class="l">Genauigkeit Stichprobe' + (st.n ? ' (' + pct(lo) + '–' + pct(hi) + ', n = ' + st.n + ')' : '') + '</div></div></div>';
  h += '<div class="card" style="margin-top:14px"><div class="cb">' + (rows.length ? '<table class="tbl"><tr><th>Wann</th><th>Bereich</th><th>Entscheidung</th><th>von</th><th></th></tr>' + rows.slice(0, 3000).map((r, i) => '<tr><td class="small">' + esc(r.at ? new Date(r.at).toLocaleString('de-DE') : '') + '</td><td class="small">' + esc(AREA[r.t] || r.t) + '</td><td>' + esc(r.what) + '</td><td class="small">' + esc(r.by) + '</td><td><button class="lbtn" data-del="' + i + '">entfernen</button></td></tr>').join('') + '</table>' : '<p class="muted">Noch keine Entscheidungen.</p>') + '</div></div></div>';
  $('#work').innerHTML = h;
  $$('#work [data-del]').forEach(b => b.onclick = () => { const r = rows[+b.dataset.del]; commit('entfernt', () => {
    if (r.scope === 'ent') delete S.ent[r.t][r.key]; else if (r.scope === 'id') delete S.id[r.t][r.key]; else if (r.scope === 'men') delete S.men[r.t][r.key];
    else if (r.scope === 'text') S.text = S.text.filter(c => c.id !== r.key); else if (r.scope === 'ev') delete S.ev[r.key]; else if (r.scope === 'qa') delete S.qa[r.key]; }); });
}

// ---------------------------------------------------------------- export
const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.map(csvCell).join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const SECTION = { taxon: 'taxa', person: 'persons', place: 'places', habitat: 'habitats' };
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
function exportIdentities() {
  const rows = []; const done = new Set();
  const base = (t, name, d) => ({ section: SECTION[t], name_form: name, note: d.note || '', reviewed_by: d.by || 'student', reviewed_at: d.t || '' });
  const taxonTarget = e => { const ed = entDec('taxon', e); if (ed && ed.d === 'r') return { label: ed.target.label, key: ed.target.key, sci: ed.target.sci, rank: ed.target.rank }; if (ed && ed.d === 'n') return null; return e.e[2] ? { label: e.label, key: e.e[2], sci: e.e[1], rank: e.e[3] } : null; };
  for (const t of TYPES) for (const e of X[t].ents) {
    const ed = entDec(t, e);
    for (const nm of e.names) {
      if (done.has(t + '|' + nm.key)) continue;
      const d = nameDec(t, nm); const r = base(t, nm.name, (d && d.d) ? d : (ed || {}));
      let dec = d && d.d && d.d !== 'e' ? d.d : null;
      if (!dec && ed && ed.d && ed.d !== 'u') { if (ed.d === 'y' && safeName(t, nm)) { dec = 'y'; r.note = 'mit dem Eintrag bestätigt'; } else if (t === 'taxon' && (ed.d === 'r' || ed.d === 'n')) dec = ed.d === 'r' ? 'y' : 'x'; }
      if (!dec) continue;
      done.add(t + '|' + nm.key);
      if (t === 'taxon') {
        if (dec === 'y') { const tg = taxonTarget(e); Object.assign(r, tg && tg.key ? { decision: 'same', target: tg.label, authority: 'gbif:' + tg.key, scientific_name: tg.sci || '', rank: tg.rank || '' } : { decision: 'own', target: nm.name }); }
        else if (dec === 'r') Object.assign(r, { decision: 'same', target: d.target.label, authority: d.target.key ? 'gbif:' + d.target.key : '', scientific_name: d.target.sci || '', rank: d.target.rank || '' });
        else if (dec === 'x') Object.assign(r, { decision: 'own', target: nm.name, reason: 'rejected' });
      } else {
        if (dec === 'y') Object.assign(r, { decision: 'same', target: e.label });
        else if (dec === 'r') Object.assign(r, { decision: 'same', target: d.target.label });
        else if (dec === 'o' || dec === 'x') Object.assign(r, { decision: 'own', target: nm.name });
      }
      if (dec === 'n') Object.assign(r, { decision: 'none', reason: (d && d.reason) || '' });
      else if (dec === 'u') r.decision = 'unsure';
      if (r.decision) rows.push(r);
    }
    if (!ed || !ed.d || ed.d === 'u') continue;
    const r = base(t, e.label, ed);
    // the authority goes on every name that stays with the entity, so it survives a new run whose canonical label differs
    const stays = e.names.filter(nm => nameState(t, nm) === 'y');   // only names confirmed as belonging here carry the authority
    const linkRows = extra => { const out = [r]; for (const nm of stays) if (lc(nm.name) !== lc(e.label)) out.push(Object.assign(base(t, nm.name, ed), extra, { target: e.label })); return out; };
    if (t === 'person') { const ex = ed.d === 'y' && (ed.qid || ed.gnd) ? { decision: 'link', authority: [ed.qid ? 'wd:' + ed.qid : '', ed.gnd ? 'gnd:' + ed.gnd : ''].filter(Boolean).join(' ') } : { decision: 'nolink' };
      Object.assign(r, ex, { target: e.label }); rows.push(...linkRows(ex)); }
    if (t === 'place') { const f = ed.fix || {}; const x = e.e;
      const ex = ed.d === 'y' ? { decision: 'link', authority: [(f.geonames_id || (!f.lat && x[4])) ? 'gn:' + (f.geonames_id || x[4]) : '', (f.qid || (!f.lat && x[5])) ? 'wd:' + (f.qid || x[5]) : '', f.osm ? 'osm:' + f.osm : ''].filter(Boolean).join(' '),
        lat: f.lat || (x[1] != null ? x[1] : ''), lon: f.lon || (x[2] != null ? x[2] : ''), uncertainty_m: f.uncertainty_m || x[3] || '' } : { decision: 'nolink' };
      Object.assign(r, ex, { target: e.label, note: [ed.note, f.note].filter(Boolean).join(' · ') }); rows.push(...linkRows(ex)); }
    if (t === 'habitat') { const ex = ed.d === 'y' && e.e[1] ? { decision: 'link', authority: 'eunis:' + e.e[1], eunis_match: e.e[2] } : ed.d === 'r' ? { decision: 'link', authority: 'eunis:' + ed.target.code, eunis_match: ed.target.match || 'close' } : { decision: 'nolink' };
      Object.assign(r, ex, { target: e.label }); rows.push(...linkRows(ex)); }
  }
  // two separate entities given the same authority record are one entity: merge them explicitly
  for (const t of ['person', 'place']) {
    const groups = new Map();
    for (const e of X[t].ents) { const ed = entDec(t, e); if (!ed || ed.d !== 'y') continue; const f = ed.fix || {};
      const k = t === 'person' ? (ed.qid || e.e[1] ? 'wd:' + (ed.qid || e.e[1]) : ed.gnd || e.e[2] ? 'gnd:' + (ed.gnd || e.e[2]) : '') : (f.geonames_id || (!f.lat && e.e[4]) ? 'gn:' + (f.geonames_id || e.e[4]) : f.qid || (!f.lat && e.e[5]) ? 'wd:' + (f.qid || e.e[5]) : '');
      if (!k) continue; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(e); }
    for (const [k, es] of groups) { if (es.length < 2) continue; es.sort((a, b) => b.n - a.n); const main = es[0];
      for (const e of es.slice(1)) for (const nm of e.names) { if (['r', 'o', 'x', 'n'].includes(nameState(t, nm))) continue;
        rows.push(Object.assign(base(t, nm.name, entDec(t, e)), { decision: 'same', target: main.label, authority: k, note: 'gleiche Normdaten wie „' + main.label + '“' })); } }
  }
  return toCSV(ID_HEAD, rows);
}
function exportMentions() {
  const head = ['kind', 'entry_uid', 'entry_id', 'old_value', 'occurrence', 'action', 'new_value', 'scientific_name', 'gbif_key', 'is_bird', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
  const rows = [];
  for (const t of TYPES) for (const k in S.men[t]) {
    const d = S.men[t][k]; if (!['r', 'n', 'x', 'o'].includes(d.d)) continue;
    const [uid, name, occ] = k.split('|'); const ei = uid2e.get(uid); const mi = X[t].mByKey.get(k); const written = mi != null ? P[t].forms[P[t].men[mi][0]][0] : (d.written || name);
    const base = { kind: t, entry_uid: uid, entry_id: ei != null ? E[ei][0] : '', old_value: written, occurrence: occ || 0, reason: d.reason || '', note: d.note || '', reviewed_by: d.by || 'student', reviewed_at: d.t || '' };
    if (d.d === 'n') rows.push(Object.assign(base, { action: 'drop', is_bird: t === 'taxon' ? (d.reason === 'misread' ? 'y' : 'n') : '' }));
    else if (d.d === 'x') rows.push(Object.assign(base, { action: 'replace', new_value: written + ' (unbestimmt)', is_bird: 'y', reason: 'not determinable' }));
    else if (d.d === 'o') rows.push(Object.assign(base, { action: 'replace', new_value: written + ' (' + (E[ei] || [''])[0] + ')', reason: 'own entity' }));
    else if (d.target) rows.push(Object.assign(base, { action: 'replace', new_value: d.target.label, scientific_name: d.target.sci || '', gbif_key: d.target.key || '', is_bird: t === 'taxon' ? 'y' : '' }));
  }
  return toCSV(head, rows);
}
function exportText() { return toCSV(['entry_uid', 'entry_id', 'old_text', 'new_text', 'note', 'reviewed_by', 'reviewed_at'], S.text.map(c => ({ entry_uid: c.entry_uid, entry_id: c.entry_id, old_text: c.old, new_text: c.new, note: c.note || '', reviewed_by: c.by || 'student', reviewed_at: c.t || '' }))); }
function exportEval() {
  const head = ['rank', 'entry_id', 'entry_uid', 'name_form', 'occurrence', 'taxon', 'scientific_name', 'gbif_key', 'evidence_class', 'judgement', 'correct_taxon', 'correct_scientific_name', 'note', 'reviewed_by', 'reviewed_at'];
  const lab = { y: 'correct', n: 'wrong', u: 'unclear' };
  return toCSV(head, P.sample.map((mi, k) => { const m = P.taxon.men[mi]; const f = P.taxon.forms[m[0]]; const x = P.taxon.ent[f[2]]; const key = X.taxon.mkey[mi]; const d = S.ev[key] || {};
    return { rank: k + 1, entry_id: E[m[1]][0], entry_uid: E[m[1]][1], name_form: f[0], occurrence: key.split('|')[2], taxon: x[0], scientific_name: x[1], gbif_key: x[2], evidence_class: f[3], judgement: lab[d.d] || '', correct_taxon: d.target ? d.target.label : '', correct_scientific_name: d.target ? d.target.sci || '' : '', note: d.note || '', reviewed_by: d.d ? d.by || 'student' : '', reviewed_at: d.t || '' }; }));
}
function exportQA() {
  const head = P.qa.head.concat(['decision', 'review_note', 'reviewed_by', 'reviewed_at']); const lab = { y: 'confirmed', n: 'wrong', u: 'unsure' };
  return toCSV(head, P.qa.rows.map(r => { const d = S.qa[qaKey(r)] || {}; const o = {}; P.qa.head.forEach((h, i) => o[h] = r[i]); return Object.assign(o, { decision: lab[d.d] || '', review_note: d.note || '', reviewed_by: d.d ? d.by || 'student' : '', reviewed_at: d.d ? d.t : '' }); }));
}
function exportLog() { return toCSV(['when', 'area', 'decision', 'by'], logRows().map(r => ({ when: r.at, area: r.t, decision: r.what, by: r.by }))); }
function progressJSON() { return JSON.stringify({ app: 'histornigraph-validation', version: 3, export: P.export, who: S.who, saved_at: new Date().toISOString(), id: S.id, men: S.men, ent: S.ent, text: S.text, qa: S.qa, ev: S.ev }, null, 1); }
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
const README = () => 'Laubmann-Abgleich, Export ' + new Date().toLocaleString('de-DE') + ' von ' + (S.who || '?') + '\nGrundlage: ' + P.export + '\n\n'
  + 'Die Dateien in review/ gehören nach data/review/ im Repository (Config-Abschnitte review: und corrections:):\n'
  + '- identities.csv: welche Art/Person/welchen Ort ein Name meint (same/own/none/unsure) und Normdaten je Eintrag (link/nolink).\n'
  + '- value_corrections.csv: einzeln entschiedene Belege (replace/drop), angewendet direkt nach der Extraktion.\n'
  + '- text_corrections.csv: korrigierte Lesungen; diese Einträge werden bei der nächsten Extraktion neu gelesen.\n'
  + '- evaluation_taxa.csv: Stichprobe zur Genauigkeit der Artbestimmung (Auswertung).\n'
  + '- qa_flags.csv: Urteile zu den Hinweisen (noch nicht von der Pipeline gelesen).\n'
  + 'validation_log.csv: alle Entscheidungen. validation_progress.json: Sicherung für „Fortschritt laden“.\n';
function exportFiles() { return [['review/identities.csv', exportIdentities()], ['review/value_corrections.csv', exportMentions()], ['review/text_corrections.csv', exportText()], ['review/evaluation_taxa.csv', exportEval()], ['review/qa_flags.csv', exportQA()], ['validation_log.csv', exportLog()], ['validation_progress.json', progressJSON()], ['LIESMICH.txt', README()]]; }
// automatic backup file (File System Access API, Chrome/Edge)
const IDB = { open: () => new Promise((res, rej) => { const r = indexedDB.open('laubmann-abgleich', 1); r.onupgradeneeded = () => r.result.createObjectStore('h'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }),
  async get(k) { const db = await IDB.open(); return new Promise(res => { const q = db.transaction('h').objectStore('h').get(k); q.onsuccess = () => res(q.result); q.onerror = () => res(null); }); },
  async set(k, v) { const db = await IDB.open(); return new Promise(res => { const tx = db.transaction('h', 'readwrite'); tx.objectStore('h').put(v, k); tx.oncomplete = res; tx.onerror = res; }); } };
async function chooseBackupFile() {
  if (!window.showSaveFilePicker) return toast('Dieser Browser kann nicht direkt in Dateien schreiben: bitte „Alles als ZIP“ benutzen', 5000);
  try { fileHandle = await showSaveFilePicker({ suggestedName: 'laubmann_abgleich_' + whoSlug() + '.json', types: [{ description: 'Sicherung', accept: { 'application/json': ['.json'] } }] });
    try { await IDB.set('file', fileHandle); } catch (e) { } dirty = 1; save(); toast('Automatische Sicherung eingerichtet'); showExport(); } catch (e) { }
}
async function reconnectBackupFile() {
  try { const h = await IDB.get('file'); if (!h) return; if ((await h.requestPermission({ mode: 'readwrite' })) === 'granted') { fileHandle = h; dirty = 1; save(); toast('Sicherung verbunden: ' + h.name); showExport(); } } catch (e) { toast('Verbindung nicht möglich, bitte die Datei neu wählen'); }
}
async function showExport() {
  let stored = null; try { stored = window.showSaveFilePicker ? await IDB.get('file') : null; } catch (e) { }
  const nDec = TYPES.reduce((a, t) => a + Object.keys(S.id[t]).length + Object.keys(S.ent[t]).length + Object.keys(S.men[t]).length, 0);
  $('#modal').innerHTML = '<button class="lbtn x" data-close>Schließen ✕</button><h2>Sichern &amp; Export</h2>'
    + '<p>' + fmt(nDec) + ' Entscheidungen, ' + fmt(S.text.length) + ' Lesungen, ' + fmt(Object.keys(S.ev).length) + ' Stichproben-Urteile. Alles liegt zunächst nur in diesem Browser.</p>'
    + '<h3>1. Automatisch sichern (empfohlen)</h3><p class="small">Eine Datei wählen (z. B. im Drive-Ordner); danach wird jede Entscheidung sofort dort gespeichert.</p><div class="row">'
    + (fileHandle ? '<span class="bd ok">aktiv: ' + esc(fileHandle.name) + '</span>' : '<button class="btn y" id="exFile">Sicherungsdatei wählen …</button>' + (stored ? '<button class="btn" id="exReconnect">wieder verbinden: ' + esc(stored.name) + '</button>' : '')) + '</div>'
    + '<h3>2. Ergebnis abgeben</h3><p class="small">ZIP mit den Dateien für die Pipeline und einer Sicherung. Bitte an Tobias schicken oder in den gemeinsamen Drive-Ordner legen.</p><div class="row"><button class="btn y" id="exZip">Alles als ZIP herunterladen</button><button class="btn" id="exJson">nur Sicherung (JSON)</button></div>'
    + '<h3>3. Fortschritt laden</h3><p class="small">Eine Sicherung (JSON oder ZIP) einspielen, auch aus den früheren Oberflächen. Bei Konflikten gilt die neuere Entscheidung.</p><div class="row"><button class="btn" id="exImport">Datei laden …</button></div>'
    + '<h3>Bearbeiterin/Bearbeiter</h3><div class="row"><input type="text" class="ftext" id="exWho" value="' + esc(S.who) + '" placeholder="Name oder Kürzel"></div>';
  $('#ovModal').classList.add('show');
  const f = $('#exFile'); if (f) f.onclick = chooseBackupFile; const rc = $('#exReconnect'); if (rc) rc.onclick = reconnectBackupFile;
  $('#exZip').onclick = () => { download('laubmann_abgleich_' + whoSlug() + '_' + stamp() + '.zip', zip(exportFiles())); dirty = 0; savedLabel(); toast('ZIP heruntergeladen'); };
  $('#exJson').onclick = () => { download('laubmann_abgleich_' + whoSlug() + '_' + stamp() + '.json', new Blob([progressJSON()], { type: 'application/json' })); dirty = 0; savedLabel(); };
  $('#exImport').onclick = () => $('#fileImport').click();
  $('#exWho').oninput = e => { S.who = e.target.value.trim(); save(); };
}
$('#btnExport').onclick = showExport;

// ---------------------------------------------------------------- import (v1 pair decisions, v2/v3 backups)
async function readZipJSON(buf) {
  const u = new Uint8Array(buf); const dv = new DataView(buf); const dec = new TextDecoder();
  for (let i = 0; i + 30 < u.length;) { if (dv.getUint32(i, true) !== 0x04034b50) break; const size = dv.getUint32(i + 18, true), nl = dv.getUint16(i + 26, true), xl = dv.getUint16(i + 28, true);
    const name = dec.decode(u.subarray(i + 30, i + 30 + nl)); const start = i + 30 + nl + xl; if (name === 'validation_progress.json') return JSON.parse(dec.decode(u.subarray(start, start + size))); i = start + size; }
  throw new Error('keine validation_progress.json im ZIP');
}
const newer = (a, b) => !a || (b.t || '') > (a.t || '');
function mergeStore(dst, src) { let n = 0; for (const k in src || {}) if (newer(dst[k], src[k])) { dst[k] = src[k]; n++; } return n; }
function importV1(j) {
  let n = 0; const secT = { taxon_merges: 'taxon', person_merges: 'person', place_merges: 'place', habitat_merges: 'habitat' };
  const known = t => { if (!known[t]) { known[t] = new Set(); P[t].ent.forEach(e => { for (const l of (t === 'place' ? e[8] : t === 'taxon' ? [e[0]] : e[3]) || []) known[t].add(lc(l)); }); } return known[t]; };
  const put = (t, name, o, force) => { const key = lc(name); if (!X[t].byKey.has(key) && !known(t).has(key)) return; if (force || newer(S.id[t][key], o)) { S.id[t][key] = o; n++; } };
  const target = (t, c) => { const cs = X[t].byKey.get(lc(c)); if (t === 'taxon' && cs) { const e = ENT(t, cs[0].ent).e; return { label: e[0], sci: e[1], key: e[2], rank: e[3] }; } return { label: cs ? ENT(t, cs[0].ent).label : c }; };
  for (const pass of ['u', 'n', 'y']) for (const task in secT) { const t = secT[task];
    for (const key in (j.dec || {})[task] || {}) { const d = j.dec[task][key]; const m = key.match(/^[^:]+: (.*) -> (.*)$/); if (!m || d.d !== pass) continue; const [, v, c] = m; const cs = X[t].byKey.get(lc(v));
      const note = [d.note, 'v1: ' + v + ' → ' + c + ' ' + (d.d === 'y' ? 'zusammenführen' : d.d === 'n' ? 'getrennt' : 'unsicher')].filter(Boolean).join(' · '); const base = { note, by: d.by, t: d.t };
      const isCur = cs && cs.some(x => lc(ENT(t, x.ent).label) === lc(c));
      if (pass === 'u') put(t, v, Object.assign({ d: 'u' }, base));
      else if (pass === 'n') { if (isCur) put(t, v, Object.assign({ d: t === 'taxon' || t === 'habitat' ? 'x' : 'o' }, base), true); }
      else put(t, v, isCur ? Object.assign({ d: 'y' }, base) : Object.assign({ d: 'r', target: target(t, c) }, base), true); } }
  for (const [task, l] of Object.entries(j.manual || {})) { const t = secT[task]; if (t) for (const x of l) put(t, x.variant, { d: 'r', target: target(t, x.canonical), note: 'v1: manuell ergänzt', by: x.by, t: x.t }); }
  for (const name in (j.dec || {}).taxon_links || {}) { const d = j.dec.taxon_links[name]; if (!d.d) continue;
    if (d.d === 'y' && d.fix) put('taxon', name, { d: 'r', target: { label: name, sci: d.fix.gbif_canonical_name, key: d.fix.gbif_key, rank: d.fix.gbif_match_type === 'EXACT' ? 'species' : '' }, note: d.note, by: d.by, t: d.t });
    else put('taxon', name, { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'x' : 'u', note: d.note, by: d.by, t: d.t }); }
  for (const name in (j.dec || {}).habitat_links || {}) { const d = j.dec.habitat_links[name]; const i = X.habitat.entByLabel.get(name); if (!d.d || i == null) continue;
    const o = d.d === 'y' && d.fix ? { d: 'r', target: { code: d.fix.eunis_code, label: d.fix.eunis_code, match: d.fix.match } } : { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'n' : 'u' };
    if (newer(S.ent.habitat[name], d)) { S.ent.habitat[name] = Object.assign(o, { note: d.note, by: d.by, t: d.t }); n++; } }
  for (const name in (j.dec || {}).person_links || {}) { const d = j.dec.person_links[name]; const cs = X.person.byKey.get(lc(name)); if (!cs || !d.d) continue; const lab = ENT('person', cs[0].ent).label;
    const o = { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'n' : 'u', qid: d.qid, wd_label: d.wd_label, wd_description: d.wd_description, gnd: d.gnd, gnd_label: d.gnd_label, gnd_info: d.gnd_info, note: [d.note, 'v1: ' + name].filter(Boolean).join(' · '), by: d.by, t: d.t };
    if (newer(S.ent.person[lab], o)) { S.ent.person[lab] = o; n++; } }
  for (const name in (j.dec || {}).place_links || {}) { const d = j.dec.place_links[name]; const cs = X.place.byKey.get(lc(name)); if (!cs || !d.d) continue; const lab = ENT('place', cs[0].ent).label;
    const o = { d: d.d === 'y' ? 'y' : d.d === 'n' ? 'n' : 'u', fix: d.fix, note: d.note, by: d.by, t: d.t }; if (newer(S.ent.place[lab], o)) { S.ent.place[lab] = o; n++; } }
  for (const key in (j.dec || {}).qa_flags || {}) { const d = j.dec.qa_flags[key]; if (newer(S.qa[key], d)) { S.qa[key] = d; n++; } }
  for (const c of j.corr || []) { if (!c.entry_uid) continue; const t = c.kind === 'place' ? 'place' : 'taxon'; const k = c.entry_uid + '|' + lc(c.old) + '|0';
    const o = c.kind === 'taxon' && !c.is_bird ? { d: 'n', reason: 'non-bird', written: c.old, note: [c.note, 'v1: gelesen „' + c.old + '“, richtig „' + c.new + '“'].filter(Boolean).join(' · '), by: c.by, t: c.t } : { d: 'r', target: { label: c.new, sci: c.sci || '' }, written: c.old, note: c.note, by: c.by, t: c.t };
    if (newer(S.men[t][k], o)) { S.men[t][k] = o; n++; }
    const ei = uid2e.get(c.entry_uid); if (ei != null && E[ei][7].includes(c.old) && !S.text.some(x => x.entry_uid === c.entry_uid && x.old === c.old)) { S.text.push({ id: 'v1' + (c.id || Date.now().toString(36)), entry_uid: c.entry_uid, entry_id: E[ei][0], old: c.old, new: c.new, note: 'aus v1-Wertkorrektur', by: c.by, t: c.t }); n++; } }
  return n;
}
function migrate() {
  // v2 kept EUNIS decisions on the name of a habitat; v3 on the habitat itself
  for (const key of Object.keys(S.id.habitat)) { const d = S.id.habitat[key]; const cs = X.habitat.byKey.get(key); if (!cs) continue; const e = ENT('habitat', cs[0].ent); if (lc(e.label) !== key) continue;
    if (['y', 'r', 'x'].includes(d.d)) { if (!S.ent.habitat[e.label]) S.ent.habitat[e.label] = Object.assign({}, d, { d: d.d === 'x' ? 'n' : d.d }); delete S.id.habitat[key]; } }
  for (const t of TYPES) for (const k of Object.keys(S.id[t])) if (S.id[t][k].d === 'e') delete S.id[t][k];
}
$('#fileImport').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  try {
    const j = /\.zip$/i.test(f.name) ? await readZipJSON(await f.arrayBuffer()) : JSON.parse(await f.text());
    if (j.export && j.export !== P.export && !confirm('Die Sicherung stammt von ' + j.export + ', diese Oberfläche von ' + P.export + '. Trotzdem laden?')) return;
    let n = 0; HIST.push(['Import', snapshot()]);
    if ((j.version || 1) < 2) n = importV1(j);
    else { for (const k of ['id', 'men', 'ent']) for (const t of TYPES) n += mergeStore(S[k][t], (j[k] || {})[t]); n += mergeStore(S.qa, j.qa); n += mergeStore(S.ev, j.ev);
      for (const c of j.text || []) if (!S.text.some(x => x.id === c.id)) { S.text.push(c); n++; } }
    if (!S.who && j.who) S.who = j.who;
    migrate(); save(); closeModal(); toast(n + ' Entscheidungen übernommen' + ((j.version || 1) < 2 ? ' (aus Version 1)' : '')); openTab(cur.tab);
  } catch (err) { alert('Laden fehlgeschlagen: ' + err.message); }
});

// ---------------------------------------------------------------- help
function showHelp(first) {
  $('#modal').innerHTML = '<button class="lbtn x" data-close>Schließen ✕</button><h2>' + (first ? 'Willkommen beim Laubmann-Abgleich' : 'Anleitung') + '</h2>'
    + (first ? '<div class="row" style="margin-bottom:10px"><span>Dein Name oder Kürzel:</span><input type="text" class="ftext" id="hwho" value="' + esc(S.who) + '" placeholder="z. B. AB"><button class="btn" id="himport">Fortschritt laden …</button></div>' : '')
    + '<p>Ziel: Jede Art, Person, jeder Ort und Lebensraum soll mit dem richtigen Normdatensatz verknüpft sein (GBIF, Wikidata/GND, GeoNames/Wikidata/Koordinaten, EUNIS). Namen, die mit demselben Datensatz verknüpft sind, werden im Graph <b>ein</b> Knoten – so entsteht das Zusammenführen.</p>'
    + '<p>Jede Liste hat zwei Stufen (Auswahl oben links): <b>1 · Prüfen</b> – schon verknüpfte Einträge bestätigen oder korrigieren; <b>2 · Verknüpfen</b> – Einträge ohne Normdaten verknüpfen oder mit einem vorhandenen Eintrag zusammenführen („Vorschläge“, Umschalt+A…E). Häufige Einträge stehen oben. Die Entscheidungen gelten auch für den künftigen Graphen mit der neuen Ontologie: sie hängen am geschriebenen Namen und an der Tagebuchstelle, nicht am alten Graphen.</p>'
    + '<h3>So geht es</h3><ol><li><b>Oben: der Eintrag selbst.</b> Stimmt die Art (GBIF), die Person (Wikidata/GND), die Lage auf der Karte, die EUNIS-Klasse? <kbd>Y</kbd> stimmt, <kbd>A</kbd> anders, <kbd>N</kbd> nicht bestimmbar/keine, <kbd>U</kbd> unsicher. „Stimmt“ bestätigt auch die sicheren Namen (belegte Namen, reine Schreibvarianten).</li>'
    + '<li><b>Darunter: die Namen.</b> Für jeden offenen Namen: gehört er hierher (✓), meint er etwas anderes (↪, z. B. eine andere Art, „nicht bestimmbar“, „eigene Person“), ist er gar kein(e) Art/Person/Ort (✗, mit Grund)?</li>'
    + '<li><b>Belege</b> (Klick auf den Namen oder <kbd>Leertaste</kbd>): Zeilenbild aus dem Scan und Text. Einzelne Belege können abweichend entschieden werden. Rechts erscheint die ganze Seite mit der markierten Zeile; <kbd>←</kbd> <kbd>→</kbd> blättern, auch über Seitenwechsel.</li>'
    + '<li><b>Lesefehler</b> mit ✎ (<kbd>E</kbd>) im Text korrigieren, so wie es im Scan steht. Der Eintrag wird später mit der korrigierten Lesung neu ausgewertet.</li>'
    + '<li><b>Zweitlesung</b>: Ein Modell hat die Zeilenbilder zweifelhafter Namen noch einmal gelesen. Passt der Vorschlag, mit <kbd>G</kbd> übernehmen (setzt Lesung und Art). Es ist nur ein Vorschlag: bitte am Bild prüfen.</li>'
    + '<li>Ist alles entschieden, geht es automatisch (oder mit <kbd>⏎</kbd>) zum nächsten Eintrag. <kbd>Z</kbd> macht die letzte Entscheidung rückgängig.</li></ol>'
    + '<h3>Richtlinien</h3><ul><li><b>Gleiche Art, nicht gleiches Wort</b>: historische und regionale Namen (Dompfaff = Gimpel, Schwarzdrossel = Amsel, Hausamsel) gehören zur Art; der geschriebene Name bleibt im Graph erhalten.</li>'
    + '<li>Ein Zusatzwort, das nur das Aussehen beschreibt (Schwarzamsel) → die Art; bezeichnet es eine eigene Unterart/Form (Trauerbachstelze) → diese über ↪. Wie oft ein Name vorkommt, entscheidet nie über seine Bedeutung.</li>'
    + '<li>Lesefehler sind keine Synonyme: Lesung korrigieren oder ✗ „Lesefehler“. Nest, Ei, Feder einer Art zählen als Nachweis dieser Art. Nur Gattung/Familie genannt (Möwe, Specht) → die Gattung/Familie wählen, nicht eine Art.</li>'
    + '<li>Personen: Kurzformen (W. Wüst) nur bei eindeutigem Zusammenhang zuordnen; „Frau X“ ist nicht „Herr X“. Orte: ähnlich geschrieben heißt nicht gleicher Ort; kleine Örtlichkeiten mit ungefährer Lage und passender Unsicherheit setzen; allgemeine Wörter (Wald, See, Garten) sind kein Ortsname.</li></ul>'
    + '<h3>Stichprobe und Hinweise</h3><p>„Stichprobe“: zufällige Belege der Reihe nach beurteilen (richtig/falsch); daraus ergibt sich die Genauigkeit der Artbestimmung. „Hinweise“: automatische Prüfungen (entfernte Nicht-Vögel, korrigierte Daten …) bestätigen oder widerlegen.</p>'
    + '<h3>Sichern</h3><p>Alles wird im Browser gespeichert. Am besten unter „Sichern &amp; Export“ eine Sicherungsdatei wählen (z. B. im Drive-Ordner): dann wird jede Entscheidung sofort in die Datei geschrieben. Zum Abgeben: „Alles als ZIP“.</p>'
    + '<h3>Tastatur</h3><table><tr><td><kbd>J</kbd> <kbd>K</kbd></td><td>Zeile wechseln (Eintrag, Namen, Belege)</td></tr><tr><td><kbd>Y</kbd> <kbd>A</kbd> <kbd>N</kbd> <kbd>U</kbd></td><td>✓ stimmt · ↪ anders · ✗ keine/r · ? unsicher</td></tr><tr><td><kbd>Leertaste</kbd></td><td>Belege eines Namens auf/zu</td></tr><tr><td><kbd>E</kbd> · <kbd>G</kbd></td><td>Lesung korrigieren · Zweitlesung übernehmen</td></tr><tr><td><kbd>⏎</kbd> · <kbd>⇧⏎</kbd></td><td>nächster offener · vorheriger Eintrag</td></tr><tr><td><kbd>Z</kbd></td><td>rückgängig</td></tr><tr><td><kbd>←</kbd> <kbd>→</kbd> · <kbd>B</kbd></td><td>Seiten im Scan · Scan ein/aus</td></tr><tr><td><kbd>/</kbd> · <kbd>Strg+K</kbd></td><td>Liste durchsuchen · alles durchsuchen</td></tr></table>';
  $('#ovModal').classList.add('show');
  const hw = $('#hwho'); if (hw) { hw.focus(); hw.oninput = e => { S.who = e.target.value.trim(); save(); }; }
  const hi = $('#himport'); if (hi) hi.onclick = () => $('#fileImport').click();
}
$('#btnHelp').onclick = () => showHelp(false);
$('#btnTheme').onclick = () => { const r = document.documentElement; const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; r.dataset.theme = dark ? 'light' : 'dark'; S.ui.theme = r.dataset.theme; save(); };
if (S.ui.theme) document.documentElement.dataset.theme = S.ui.theme;
window.addEventListener('beforeunload', () => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { } });
window.__hog = { P, S, X, SUG, openTab, selectItem, showScan, act, acceptSug, diffHunks, applyReadings, exportIdentities, exportMentions, exportText, exportEval, importV1, entState, nameState, undo, cur, setFocus };

// ---------------------------------------------------------------- start
migrate();
$('#loading').remove();
if (S.ui.noscan) $('#main').classList.add('noscan');
savedLabel();
openTab(cur.tab);
if (!S.who) setTimeout(() => showHelp(true), 300);
})();
