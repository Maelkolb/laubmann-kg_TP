// Laubmann-Abgleich v4 — part 1: data, state, model, queues.
// Four tasks: Prüfen (verify authority links) · Verknüpfen (link the unlinked) · Namen (which written names belong
// to an identifier) · Lesefehler (mentions where model readings disagree with the transcription).
'use strict';
const $ = s => document.querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = n => Number(n || 0).toLocaleString('de-DE');
const pct = x => (100 * (x || 0)).toLocaleString('de-DE', { maximumFractionDigits: 1 }) + ' %';
const lc = s => String(s || '').toLowerCase();
const fold = s => lc(s).normalize('NFC').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
const letters = s => fold(s).replace(/[^a-z]/g, '');
const LS = 'hog-validation-v2';
function toast(msg, ms) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), ms || 2400); }
function lev(a, b) {
  if (a === b) return 0; if (!a.length || !b.length) return a.length || b.length;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) { const row = [i]; for (let j = 1; j <= b.length; j++) row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = row; }
  return prev[b.length];
}
function sameWord(a, b) { a = letters(a); b = letters(b); if (!a || !b) return a === b; if (a === b) return true; if ((a.startsWith(b) || b.startsWith(a)) && Math.abs(a.length - b.length) <= 3) return true; return lev(a, b) <= Math.max(1, Math.floor(Math.min(a.length, b.length) * 0.12)); }

// ---------------------------------------------------------------- payload
async function loadPayload() {
  const b64 = $('#data').textContent.trim();
  let bytes;
  try { bytes = await (await fetch('data:application/octet-stream;base64,' + b64)).arrayBuffer(); }
  catch (e) { const bin = atob(b64); bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); }
  const ds = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(ds).text());
}
let P, DRIVE = {};
const TYPES = ['taxon', 'person', 'place', 'habitat'];
let E, PG, SUG, SUG3, SUGS, PM, CAND, EUNIS, uid2e, MV;

// ---------------------------------------------------------------- state, persistence, undo
let S = { who: '', id: {}, men: {}, ent: {}, grp: {}, text: [], qa: {}, ev: {}, ui: {} };
function normalizeState() {
  for (const k of ['id', 'men', 'ent', 'grp']) { S[k] = S[k] || {}; for (const t of TYPES) S[k][t] = S[k][t] || {}; }
  S.text = S.text || []; S.qa = S.qa || {}; S.ev = S.ev || {}; S.ui = S.ui || {};
  S.ui.adv = S.ui.adv === true; S.ui.follow = S.ui.follow !== false; S.ui.sel = S.ui.sel || {}; S.ui.show = S.ui.show || {}; S.ui.sort = S.ui.sort || {}; S.ui.type = S.ui.type || {};
}
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
function snapshot() { return JSON.stringify({ id: S.id, men: S.men, ent: S.ent, grp: S.grp, text: S.text, qa: S.qa, ev: S.ev }); }
function commit(label, fn) { HIST.push([label, snapshot()]); if (HIST.length > 150) HIST.shift(); fn(); save(); refresh(); }
function undo() { const h = HIST.pop(); if (!h) return toast('Nichts rückgängig zu machen'); Object.assign(S, JSON.parse(h[1])); normalizeState(); save(); refresh(); toast('Rückgängig: ' + h[0]); }

// ---------------------------------------------------------------- vocabulary
const TT = {
  taxon: { tab: 'Arten', one: 'Art', unit: 'Belege', auth: 'GBIF',
    cls: { A: ['belegter Name', 'ok', 'Deutscher Name dieser Art laut GBIF oder Wikidata (auch historische Namen).'], B: ['Variante', 'info', 'Schreib- oder Wortvariante eines belegten Namens.'], C: ['unbelegt', 'risk', 'Kein belegter Name dieser Art: oft ein Lesefehler oder ein seltener Volksname.'], L: ['ohne GBIF-Art', 'warn', 'Keiner GBIF-Art zugeordnet.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['non-bird', 'anderes Tier oder Pflanze'], ['place', 'eigentlich ein Ort'], ['person', 'eigentlich eine Person'], ['other', 'sonstiges']] },
  person: { tab: 'Personen', one: 'Person', unit: 'Nennungen', auth: 'Wikidata/GND',
    cls: { V: ['zugeordnet', 'warn', 'Automatisch dieser Person zugeordnet (Kurzform, Initiale, Nachname).'], K: ['voller Name', 'plain', 'Voller Name.'], W: ['verknüpft', 'ok', 'Mit Wikidata oder GND verknüpft.'], E: ['nur ein Namensteil', 'plain', 'Einzelner Name.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['place', 'eigentlich ein Ort'], ['taxon', 'eigentlich ein Vogel'], ['other', 'sonstiges (Institution, Zeitschrift …)']] },
  place: { tab: 'Orte', one: 'Ort', unit: 'Nennungen', auth: 'GeoNames/Wikidata',
    cls: { V: ['zugeordnet', 'warn', 'Einem ähnlich geschriebenen Ort zugeordnet.'], R: ['Lage prüfen', 'warn', 'Unsichere Georeferenz.'], N: ['ohne Lage', 'warn', 'Keine Koordinate.'], G: ['mit Lage', 'ok', 'Automatisch georeferenziert.'] },
    not: [['misread', 'Lesefehler / kein Name'], ['generic', 'kein Ortsname (Wald, See, Garten …)'], ['taxon', 'eigentlich ein Vogel'], ['person', 'eigentlich eine Person'], ['habitat', 'eigentlich ein Lebensraum'], ['other', 'sonstiges']] },
  habitat: { tab: 'Lebensräume', one: 'Lebensraum', unit: 'Beobachtungen', auth: 'EUNIS',
    cls: { V: ['Variante', 'info', 'Schreibvariante.'], R: ['prüfen', 'warn', 'Unsichere EUNIS-Klasse.'], N: ['ohne Klasse', 'warn', 'Keine EUNIS-Klasse.'], E: ['mit Klasse', 'ok', 'Automatisch einer EUNIS-Klasse zugeordnet.'] },
    not: [['misread', 'Lesefehler / kein Lebensraum'], ['place', 'eigentlich ein Ort'], ['other', 'sonstiges']] },
};
const RULE_DE = { 'same-key': 'gleicher Name ohne Titel', 'initial-unique': 'Initiale passt nur hierher', 'initial-ambiguous': 'Initiale passt zu mehreren', 'surname-unique': 'gleicher Nachname', 'surname-ambiguous': 'gleicher Nachname, mehrdeutig', dominant: 'häufigste passende Person', manual: 'von Hand zusammengeführt', wikidata: 'gleiches Wikidata-Objekt', orthographic: 'gleiche Schreibung (ü/ue, ß/ss …)', similar: 'ähnliche Schreibung' };
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
  { id: 'check', label: 'Prüfen', kind: 'ent', typed: true }, { id: 'link', label: 'Verknüpfen', kind: 'ent', typed: true }, { id: 'names', label: 'Namen', kind: 'ent', typed: true },
  { id: 'read', label: 'Zweitlesung', kind: 'read' }, { id: 'eval', label: 'Stichprobe', kind: 'eval' }, { id: 'qa', label: 'Hinweise', kind: 'qa' }, { id: 'log', label: 'Protokoll', kind: 'log' },
];
const TAB = Object.fromEntries(TABS.map(t => [t.id, t]));
const MODEL_DE = { g: 'Gemini 3.5 Flash', o: 'Claude Opus 5.5', s: 'Claude Sonnet 5.5' };

// ---------------------------------------------------------------- model
const X = {};
const TITLES = /\b(dr|prof|herr|hr|frau|fr|frl|fraeulein|lehrer|oberlehrer|pfarrer|oberfoerster|foerster|forstmeister|cand|phil|med|rer|nat|stud|ing|hofrat|major|direktor|dir)\b\.?/g;
const pkey = n => fold(n).replace(/\?/g, '').replace(TITLES, ' ').replace(/[^a-z]/g, '');
function buildModel() {
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
    for (const e of ents) e.names.sort((a, b) => (safeName(t, a) === safeName(t, b) ? 0 : safeName(t, a) ? 1 : -1) || b.n - a.n);
  }
}
const ENT = (t, i) => X[t].ents[i];
const isLabel = (t, nm) => nm.key === lc(ENT(t, nm.ent).label);
function safeName(t, nm) {
  if (isLabel(t, nm)) return true;
  if (t === 'taxon') return nm.cls === 'A';
  if (t === 'person') return pkey(nm.name) === pkey(ENT(t, nm.ent).label);
  return (nm.f[4] || '') === 'orthographic';
}
const linked = (t, e) => t === 'taxon' ? !!e.e[2] : t === 'person' ? !!(e.e[1] || e.e[2]) : t === 'place' ? e.e[1] != null : !!e.e[1];
function authText(t, e) {
  const x = e.e;
  if (t === 'taxon') return x[2] ? '<i>' + esc(x[1]) + '</i> · GBIF ' + esc(x[2]) : 'ohne GBIF-Art';
  if (t === 'person') return [x[1] ? 'Wikidata ' + esc(x[1]) : '', x[2] ? 'GND ' + esc(x[2]) : ''].filter(Boolean).join(' · ') || 'ohne Normdaten';
  if (t === 'place') return x[1] != null ? esc(x[1] + ', ' + x[2]) + (x[4] ? ' · GeoNames ' + esc(x[4]) : '') : 'ohne Lage';
  return x[1] ? 'EUNIS ' + esc(x[1]) : 'ohne EUNIS-Klasse';
}
// model readings of a taxon mention: [{src, word, kind, species, sci, conf, target, note, same}]
function writtenOf(mi) { const m = P.taxon.men[mi]; return m[2] >= 0 ? E[m[1]][7].slice(m[2], m[3]) : P.taxon.forms[m[0]][0]; }
// the model may read more than the mention (a compound, the next word) or less: the text already says it
function wordInText(word, mi) {
  const m = P.taxon.men[mi]; if (m[2] < 0) return false; const a = letters(word); if (!a) return false;
  const t = E[m[1]][7]; const from = Math.max(0, m[2] - word.length - 2);
  return letters(t.slice(from, m[3] + word.length + 2)).includes(a);
}
function readingDiffers(r, mi) {
  const m = P.taxon.men[mi]; const cur = P.taxon.forms[m[0]][2]; const ce = P.taxon.ent[cur];
  if (r.kind && r.kind !== 'bird') return true;
  const wordDiff = !r.same && !sameWord(r.word, writtenOf(mi)) && !wordInText(r.word, mi);
  if (r.target >= 0) return r.target !== cur || wordDiff;
  if (!r.sci && !r.species) return wordDiff;
  const binom = x => lc(x).split(/\s+/).slice(0, 2).join(' ');
  const sameSp = (r.sci && ce[1] && binom(r.sci) === binom(ce[1])) || (r.species && [ce[0], ...ce[9]].some(n => sameWord(n, r.species)));
  return !sameSp || wordDiff;
}
function readingsOf(mi) {
  const out = [];
  const g = SUG[mi], o = SUG3[mi], s = SUGS[mi];
  if (g) out.push({ src: 'g', word: g[0], same: !!g[1], kind: g[2], species: g[3], sci: g[4], conf: g[5], note: g[6], target: g[7] });
  if (o && o[1]) out.push({ src: 'o', word: o[0], same: false, kind: o[2], species: o[3], sci: o[4], conf: o[5], note: o[6], target: o[7] });
  if (s && s[1]) out.push({ src: 's', word: s[0], same: false, kind: s[2], species: s[3], sci: s[4], conf: s[5], note: s[6], target: s[7] });
  for (const r of out) r.differs = readingDiffers(r, mi);
  return out;
}
function agreement(rs) {
  if (rs.length < 2) return rs.length && rs[0].differs ? 2 : 0;
  const [a, b] = rs; const sameW = sameWord(a.word, b.word); const sameT = a.target >= 0 && a.target === b.target || (a.kind === b.kind && a.kind !== 'bird') || (a.sci && b.sci && lc(a.sci) === lc(b.sci));
  if (sameW && sameT) return a.differs || b.differs ? 3 : 0;
  return 1;
}
// the word the model read stands elsewhere in the entry: the line image probably shows another line (two-column lists)
function wordElsewhere(word, mi) {
  const m = P.taxon.men[mi]; if (m[2] < 0) return false; const a = letters(word); if (a.length < 5) return false;
  const t = E[m[1]][7];
  return letters(t.slice(0, Math.max(0, m[2] - word.length - 2))).includes(a) || letters(t.slice(m[3] + word.length + 2)).includes(a);
}
const READ = [];   // read-task items
function buildReadItems() {
  const all = new Set([...Object.keys(SUG), ...Object.keys(SUG3), ...Object.keys(SUGS)].map(Number));
  for (const mi of all) { const rs = readingsOf(mi); const diff = rs.filter(r => r.differs); if (!diff.length) continue; const ag = agreement(rs);
    const mis = diff.every(r => r.kind === 'bird' && !r.same && wordElsewhere(r.word, mi));
    // what is disputed: the word itself, only the species behind an agreed word, or whether it is a bird at all
    const nb = diff.some(r => r.kind && r.kind !== 'bird'); const wd = diff.some(r => r.kind === 'bird' && !r.same && !sameWord(r.word, writtenOf(mi)) && !wordInText(r.word, mi));
    READ.push({ mi, rs, ag, mis, kind: nb ? 'nonbird' : wd ? 'word' : 'species', key: X.taxon.mkey[mi], ei: P.taxon.men[mi][1], n: P.taxon.forms[P.taxon.men[mi][0]][1] }); }
  READ.sort((a, b) => a.mis - b.mis || b.ag - a.ag || b.n - a.n);
}
const READ_KIND = { word: ['Wort anders gelesen', 'warn'], species: ['Wort stimmt, Art anders', 'info'], nonbird: ['kein Vogel?', 'risk'] };
// entity issues (names task) and person model suggestion
function nameIssues(t, e) {
  let risky = 0; for (const nm of e.names) if (!safeName(t, nm)) risky++;
  const inc = (CAND[t].ec[e.i] || []).length;
  return { risky, inc };
}

// ---------------------------------------------------------------- decisions and states
const entDec = (t, e) => S.ent[t][e.label];
const nameDec = (t, nm) => S.id[t][nm.key];
const grpDec = (t, e) => S.grp[t][e.label];
function readingFor(ei) { return S.text.filter(c => c.entry_uid === E[ei][1]); }
function menReading(t, mi) { const m = P[t].men[mi]; if (m[2] < 0) return null; const text = E[m[1]][7]; const key = X[t].mkey[mi]; return readingFor(m[1]).find(c => { if (c.men === key) return true; const i = text.indexOf(c.old); return i >= 0 && i < m[3] && i + c.old.length > m[2]; }) || null; }
function menState(t, mi) { const d = S.men[t][X[t].mkey[mi]]; if (d && d.d) return d.d; return menReading(t, mi) ? 't' : ''; }
// name -> '' | y | r | o | x | n | u ; f = follows a relinked/rejected entity
function nameState(t, nm) {
  const d = nameDec(t, nm); if (d && d.d) return d.d;
  const e = ENT(t, nm.ent); const ed = entDec(t, e);
  if (grpDec(t, e)) return 'y';
  if (ed && ed.d) { if (ed.d === 'y' && safeName(t, nm)) return 'y'; if ((t === 'taxon' || t === 'habitat') && (ed.d === 'r' || ed.d === 'n')) return 'f'; }
  if (nm.n <= 60 && nm.men.length && nm.men.every(mi => menState(t, mi))) return 'm';   // every mention decided or re-read on its own
  return '';
}
const nameGone = st => ['r', 'o', 'x', 'n'].includes(st);
// a read item is settled by its own mention decision, by an explicit decision on the written name, or by a relinked entity
function readState(it) {
  const d = S.men.taxon[it.key]; if (d && d.d) return d.d === 'y' ? 'y' : d.d === 'u' ? 'u' : 'r';
  const nm = X.taxon.names[P.taxon.men[it.mi][0]]; const nd = nameDec('taxon', nm);
  if (nd && nd.d) return nd.d === 'y' ? 'y' : nd.d === 'u' ? 'u' : 'r';
  const ed = entDec('taxon', ENT('taxon', nm.ent)); if (ed && (ed.d === 'r' || ed.d === 'n')) return 'r';
  return menReading('taxon', it.mi) ? 'r' : '';
}
function entState(t, e) {   // link decision state of the entity
  const ed = entDec(t, e); if (!ed || !ed.d) { if (e.names.length && e.names.every(nm => nameGone(nameState(t, nm)))) return 'r'; return ''; }
  if (ed.d === 'u') return 'u'; if (ed.d === 'n') return 'n';
  if (ed.d === 'r' || ed.fix || (t === 'person' && ed.qid && ed.qid !== e.e[1])) return 'r';
  return 'y';
}
function namesState(t, e) {
  let open = 0, changed = false, unsure = false;
  for (const nm of e.names) { const st = nameState(t, nm); if (!st) open++; else if (nameGone(st)) changed = true; else if (st === 'u') unsure = true; }
  const cands = (CAND[t].ec[e.i] || []).map(([fi]) => X[t].names[fi]).filter(nm => nm.ent !== e.i);
  const inc = cands.some(nm => { const st = nameDec(t, nm); return st && st.d === 'r' && st.target && st.target.label === e.label; });
  // candidates count as reviewed once the group is confirmed or the entity itself was decided with them on screen
  const pending = !grpDec(t, e) && !(entDec(t, e) || {}).d && cands.some(nm => !nameDec(t, nm));
  if (unsure) return 'u';
  if (open || pending) return (e.names.length - open) || inc ? 'p' : '';
  return changed || inc ? 'r' : 'y';
}
const DONE = s => s === 'y' || s === 'r' || s === 'n';
const STATE_DE = { y: 'bestätigt', r: 'korrigiert', n: 'abgelehnt', u: 'unsicher', p: 'begonnen', '': 'offen' };
