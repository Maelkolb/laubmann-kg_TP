// ---------------------------------------------------------------- utilities
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const loc = () => (LANG === 'en' ? 'en-GB' : 'de-DE');
const fmt = n => Number(n || 0).toLocaleString(loc());
const dec2 = x => Number(x).toLocaleString(loc(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// key of a written name: the pipeline matches names with str.casefold() (review/identities.py)
const cf = s => String(s == null ? '' : s).trim().toLowerCase().replace(/ß/g, 'ss').replace(/ſ/g, 's');
const fold = s => cf(s).normalize('NFD').replace(/[̀-ͯ]/g, '');
const uniq = a => Array.from(new Set(a));
let toastT = null;
function toast(msg, ms) { const el = $('#toast'); el.textContent = msg; el.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('show'), ms || 2000); }
async function loadData() {
  const b64 = $('#data').textContent.trim();
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(ds).text());
}

// ---------------------------------------------------------------- data
const TYPES = ['taxon', 'person', 'place', 'habitat'];
const SECTION = { taxon: 'taxa', person: 'persons', place: 'places', habitat: 'habitats' };
const TYPE_OF_SECTION = { taxa: 'taxon', persons: 'person', places: 'place', habitats: 'habitat' };
const STATUS_Q = ['changed', 'confirmed', 'suggest', 'pipeline', 'unlinked'];
const QUEUES = STATUS_Q.concat(['merge', 'done']);
let D = null, PAGES = [], EUNIS = new Map();
const ENTS = {}, BYK = {}, FORMK = {};
function indexData() {
  PAGES = D.PAGES;
  for (const e of D.EUNIS) EUNIS.set(e[0], e);
  for (const t of TYPES) {
    ENTS[t] = D.ents[t] || []; BYK[t] = new Map(); FORMK[t] = new Map();
    for (const e of ENTS[t]) { BYK[t].set(e.k, e); for (const f of e.forms) if (!e.gone && !FORMK[t].has(cf(f.f))) FORMK[t].set(cf(f.f), e); }
  }
}

// ---------------------------------------------------------------- state
// ent:  type -> key of the entity label -> { d: link|nolink|none|unsure, target, grade, via, label, fs, note, by, t }
// form: type -> key of the written name -> { d: same|own|none, to, toLink, name, ent, via, by, t }
const LS = 'laubmann-link-check-v1';
let S = { who: '', ent: {}, form: {}, ui: {}, n: 0 };
function normalizeState() {
  S.ent = S.ent || {}; S.form = S.form || {}; S.ui = S.ui || {};
  for (const t of TYPES) { S.ent[t] = S.ent[t] || {}; S.form[t] = S.form[t] || {}; }
  const u = S.ui; u.q = u.q || {}; u.sel = u.sel || {}; u.sub = u.sub || {}; u.find = u.find || {}; u.type = u.type || 'home'; if (u.scan == null) u.scan = true;
  u.corpus = Math.max(0, Math.min(3, u.corpus | 0));
}
const stamp = o => Object.assign({}, o, { by: S.who || '', t: new Date().toISOString() });
let saveT = null;
function save() {
  clearTimeout(saveT);
  saveT = setTimeout(() => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { toast(t('toast.nosave'), 5000); } savedLabel(); }, 250);
}
function savedLabel() { const el = $('#saved'); if (!el) return; el.textContent = S.n > 0 ? t('saved.dirty', fmt(S.n)) : t('saved.browser'); el.className = 'saved' + (S.n > 60 ? ' warn' : ''); }
const HIST = [];
// ops: [store ('ent' | 'form'), type, key, value | null]
function commit(label, ops) {
  const back = ops.map(([s, ty, k]) => [s, ty, k, S[s][ty][k] ? JSON.parse(JSON.stringify(S[s][ty][k])) : null]);
  for (const [s, ty, k, v] of ops) { if (v == null) delete S[s][ty][k]; else S[s][ty][k] = v; }
  HIST.push({ label, ops: back, type: cur.type, key: cur.key }); if (HIST.length > 300) HIST.shift();
  S.n = (S.n || 0) + 1; save(); refresh();
}
function undo() {
  const h = HIST.pop(); if (!h) return toast(t('toast.noundo'));
  for (const [s, ty, k, v] of h.ops) { if (v == null) delete S[s][ty][k]; else S[s][ty][k] = v; }
  S.n = Math.max(0, (S.n || 0) - 1); save(); toast(t('toast.undone', h.label));
  if (h.type && h.type !== 'home' && BYK[h.type] && BYK[h.type].has(h.key)) { cur.type = h.type; S.ui.type = h.type; cur.key = h.key; S.ui.sel[h.type] = h.key; }
  refresh(true);
}

// ---------------------------------------------------------------- corpus filter (a view only: decisions and export never depend on it)
// S.ui.corpus = lowest record tier that counts: 0 vollständig, 1 Kern, 2 strenger Kern, 3 strenger Kern mit Koordinaten.
// e.nc / f.nc = mentions of an entry / a written name in the records of the four corpora (build_data.py).
const corpus = () => (D && D.corpus ? (S.ui.corpus | 0) : 0);
const cn = e => { const c = corpus(); return c === 0 ? e.n : (e.nc ? e.nc[c] : 0); };
const fcn = f => { const c = corpus(); return c === 0 ? f.n : (f.nc ? f.nc[c] : 0); };
const menIn = m => (m.k != null && m.k >= corpus() ? 1 : 0);          // is a passage in the chosen corpus
const CENTS = {};
function corpusItems(ty) {     // the entries with at least one mention in the corpus, most mentions in the corpus first
  const c = corpus(); if (c === 0) return ENTS[ty];
  const key = ty + c;
  if (!CENTS[key]) CENTS[key] = ENTS[ty].filter(e => e.nc && e.nc[c] > 0).sort((a, b) => b.nc[c] - a.nc[c] || b.n - a.n || a.l.localeCompare(b.l));
  return CENTS[key];
}

// ---------------------------------------------------------------- model
const cur = { type: 'home', key: null };
const curEnt = () => (cur.type !== 'home' && BYK[cur.type] ? BYK[cur.type].get(cur.key) || null : null);
const entDec = (ty, e) => S.ent[ty][e.k] || null;
const formDec = (ty, name) => S.form[ty][cf(name)] || null;
// a name decision that settles the name's link: removed, moved to another entry, or (species) carrying its own GBIF decision
function formSettles(ty, e, f) { const d = formDec(ty, f.f); if (!d) return false; if (d.d === 'none') return true; if (d.d === 'same') return ty === 'taxon' || cf(d.to) !== e.k; return ty === 'taxon'; }
function entDone(ty, e) { return !!S.ent[ty][e.k] || (e.forms.length > 0 && e.forms.every(f => formSettles(ty, e, f))); }
const mergeNames = e => uniq((e.mg || []).map(c => c.v));
function mergeDone(ty, e) { return !!e.mg && mergeNames(e).every(v => formDec(ty, v)); }
function inQueue(ty, e, q) { return q === 'all' ? true : q === 'done' ? entDone(ty, e) : q === 'merge' ? !!e.mg : e.q === q; }
function isOpen(ty, e, q) { return q === 'merge' ? !mergeDone(ty, e) : !entDone(ty, e); }
function decClass(ty, e) {
  const d = entDec(ty, e);
  if (!d) return entDone(ty, e) ? 'p' : '';
  if (d.d === 'unsure') return 'u';
  if (d.d === 'nolink' || d.d === 'none') return 'r';
  return d.via === 'confirm' ? 'a' : 'o';
}
const km = (a, b) => { const R = Math.PI / 180, la1 = a[0] * R, la2 = b[0] * R; const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((b[1] - a[1]) * R / 2) ** 2; return 12742 * Math.asin(Math.sqrt(h)); };
function sameLink(ty, a, b) {
  if (!a || !b) return !a && !b;
  if (ty === 'taxon') return String(a.key || '') === String(b.key || '');
  if (ty === 'person') return (a.qid || '') === (b.qid || '') && (a.gnd || '') === (b.gnd || '');
  if (ty === 'habitat') return a.code === b.code;
  if (a.lat == null || b.lat == null) return a.lat == null && b.lat == null && (a.gn || '') === (b.gn || '') && (a.qid || '') === (b.qid || '');
  if (km([a.lat, a.lon], [b.lat, b.lon]) > 0.5) return false;
  for (const k of ['gn', 'qid']) if (a[k] && b[k] && String(a[k]) !== String(b[k])) return false;
  return true;
}
const SLIM = { taxon: ['key', 'sci', 'rank', 'label', 'family'], person: ['qid', 'gnd', 'label', 'desc', 'born', 'died'], place: ['lat', 'lon', 'unc', 'gn', 'qid', 'osm', 'name', 'feature'], habitat: ['code', 'match', 'label'] };
function slim(ty, x) { const o = {}; for (const k of SLIM[ty]) if (x[k] != null && x[k] !== '') o[k] = x[k]; return o; }
function defaultGrade(ty, target, e) {
  if (ty === 'habitat') return (target && target.match) || 'close';
  if (ty === 'taxon') return target && target.mt === 'HIGHERRANK' ? 'broad' : 'exact';
  return 'exact';                                  // a reviewed person / place link is an identity claim (kg/authority.py)
}
const namesOf = e => e.forms.map(f => f.f);
// names for which the machine suggests something else (not applied): a link decision on the entry leaves them open
const openSuggested = e => e.forms.filter(f => f.m && !f.m.ap && f.m.diff).map(f => f.f);
function makeDec(ty, e, d, via, target, grade) {
  const prev = entDec(ty, e) || {};
  const skip = d === 'link' ? new Set(openSuggested(e).map(cf)) : new Set();
  const o = { d, via, label: e.l, fs: namesOf(e).filter(n => !skip.has(cf(n))), note: prev.note || '' };
  if (d === 'link') { o.target = slim(ty, target); o.grade = grade || defaultGrade(ty, target, e); }
  if (keepsName(ty, e, d)) o.keep = 1;
  return stamp(o);
}
function keepsName(ty, e, d) { return ty !== 'taxon' && (d === 'link' || d === 'nolink') && (!!e.gone || !!(e.m && e.m.prop && e.m.prop.none)); }
// what the machine holds to be right: its proposal, else (when it confirms) the graph's link
function machineState(ty, e) {
  const m = e.m; if (!m) return undefined;
  if (m.prop) return m.prop.none ? { none: 1 } : m.prop.nolink ? { nolink: 1 } : m.prop;
  if (['ok', 'link', 'same'].includes(m.word)) return e.cur || { nolink: 1 };
  if (m.word === 'nolink') return { nolink: 1 };
  return undefined;
}
function sameState(ty, d, st) {
  if (!st) return '';
  if (d.d === 'unsure') return '';
  if (d.d === 'none') return st.none ? 'y' : 'n';
  if (d.d === 'nolink') return st.nolink ? 'y' : 'n';
  return !st.none && !st.nolink && sameLink(ty, d.target, st) ? 'y' : 'n';
}

// ---------------------------------------------------------------- labels of links
function linkAuth(ty, x) {
  if (!x) return '';
  if (ty === 'taxon') return x.key ? 'gbif:' + x.key : '';
  if (ty === 'person') return [x.qid ? 'wd:' + x.qid : '', x.gnd ? 'gnd:' + x.gnd : ''].filter(Boolean).join(' ');
  if (ty === 'place') return [x.gn ? 'gn:' + x.gn : '', x.qid ? 'wd:' + x.qid : '', x.osm ? 'osm:' + x.osm : ''].filter(Boolean).join(' ');
  return x.code ? 'eunis:' + x.code : '';
}
function linkText(ty, x) {
  if (!x) return '';
  if (x.none) return 'none'; if (x.nolink) return 'nolink';
  if (ty === 'taxon') return [x.sci || x.label || '', linkAuth(ty, x)].filter(Boolean).join(' ');
  if (ty === 'person') return [x.label || '', linkAuth(ty, x)].filter(Boolean).join(' ');
  if (ty === 'place') return [x.lat != null ? (+x.lat).toFixed(5) + ',' + (+x.lon).toFixed(5) : '', linkAuth(ty, x)].filter(Boolean).join(' ');
  return [x.code || '', x.match || x.grade || ''].filter(Boolean).join(' ');
}
function linkShort(ty, x) {
  if (!x) return t('chg.nolink');
  if (x.none) return t('ck.none.' + ty); if (x.nolink) return t('chg.nolink');
  if (ty === 'taxon') return (x.label && x.label !== x.sci ? x.label + ' · ' : '') + (x.sci || 'GBIF ' + x.key);
  if (ty === 'person') return (x.label || x.qid || '') + (x.born || x.died ? ' (' + (x.born || '?').slice(0, 4) + '–' + (x.died || '').slice(0, 4) + ')' : '') + (x.label && x.qid ? ' · ' + x.qid : '') + (x.gnd ? ' · GND ' + x.gnd : '');
  if (ty === 'place') return (x.name ? x.name.split(',')[0] + ' · ' : '') + (x.lat != null ? (+x.lat).toFixed(4) + ', ' + (+x.lon).toFixed(4) : (x.gn ? 'GeoNames ' + x.gn : x.qid || ''));
  return x.code + ' ' + (x.label || '') + (x.match || x.grade ? ' (' + (x.match || x.grade) + ')' : '');
}

// ---------------------------------------------------------------- export: review/identities.csv (contract of laubmann_kg/review/identities.py)
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const VIA_REASON = { confirm: 'link confirmed in review', accept: 'machine suggestion accepted in review', revert: 'machine decision rejected: state before the machine', cand: 'other record chosen in review', search: 'other record chosen in review', import: 'taken over from Laubmann_Validierung' };
const NONE_REASON = { taxon: 'not a taxon', person: 'not a person', place: 'not a place name', habitat: 'not a habitat' };
function idRows() {
  const rows = [], inForm = new Set(), inLink = new Set();
  const base = (ty, name, d) => ({ section: SECTION[ty], name_form: name, decision: '', target: '', authority: '', scientific_name: '', rank: '', lat: '', lon: '', uncertainty_m: '', eunis_match: '', reason: '', note: d.note || '', reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '' });
  const push = (set, r) => { const k = r.section + '|' + cf(r.name_form); if (set.has(k)) return; set.add(k); rows.push(r); };
  // 1. decisions on single written names (they win over the entry's decision)
  for (const ty of TYPES) for (const f of Object.values(S.form[ty])) {
    const r = base(ty, f.name, f);
    if (f.d === 'none') Object.assign(r, { decision: 'none', target: f.name, reason: NONE_REASON[ty] });
    else if (f.d === 'own') Object.assign(r, { decision: 'own', target: f.name, reason: f.via === 'merge' ? 'merge candidate rejected: an entity of its own' : f.via === 'revert' ? VIA_REASON.revert : 'an entity of its own' });
    else if (f.d === 'same') {
      Object.assign(r, { decision: 'same', target: f.to || f.name, reason: f.via === 'merge' ? 'merge candidate accepted: same entity' : VIA_REASON[f.via] || 'name assigned in review' });
      if (ty === 'taxon' && f.toLink && f.toLink.key) Object.assign(r, { authority: 'gbif:' + f.toLink.key, scientific_name: f.toLink.sci || '', rank: f.toLink.rank || '' });
    } else continue;
    push(inForm, r);
  }
  // 2. decisions on entries
  for (const ty of TYPES) for (const d of Object.values(S.ent[ty])) {
    const names = d.fs && d.fs.length ? d.fs : [d.label];
    const gradeNote = n => [n, d.grade ? 'match=' + d.grade : ''].filter(Boolean).join(' · ');
    if (d.d === 'unsure') { push(inForm, Object.assign(base(ty, d.label, d), { decision: 'unsure', target: d.label, reason: 'reviewer unsure' })); continue; }
    if (ty === 'taxon') {
      for (const name of names) {
        const r = base(ty, name, d);
        if (d.d === 'link') Object.assign(r, { decision: 'same', target: d.target.label || d.label, authority: 'gbif:' + d.target.key, scientific_name: d.target.sci || '', rank: d.target.rank || '', reason: VIA_REASON[d.via] || '', note: gradeNote(d.note) });
        else if (d.d === 'nolink') Object.assign(r, { decision: 'own', target: name, reason: d.via === 'revert' ? VIA_REASON.revert : 'no GBIF record fits' });
        else if (d.d === 'none') Object.assign(r, { decision: 'none', target: name, reason: NONE_REASON[ty] });
        push(inForm, r);
      }
      continue;
    }
    if (d.d === 'none') { for (const name of names) push(inForm, Object.assign(base(ty, name, d), { decision: 'none', target: d.label, reason: NONE_REASON[ty] })); continue; }
    if (d.keep) push(inForm, Object.assign(base(ty, d.label, d), { decision: 'own', target: d.label, reason: 'a name of its own: overrides the removal by the machine review' }));
    const r = base(ty, d.label, d);
    if (d.d === 'nolink') Object.assign(r, { decision: 'nolink', target: d.label, reason: d.via === 'revert' ? VIA_REASON.revert : 'no authority record fits' });
    else {
      Object.assign(r, { decision: 'link', target: d.label, authority: linkAuth(ty, d.target), reason: VIA_REASON[d.via] || '' });
      if (ty === 'place') Object.assign(r, { lat: d.target.lat != null ? d.target.lat : '', lon: d.target.lon != null ? d.target.lon : '', uncertainty_m: d.target.unc != null ? d.target.unc : '' });
      if (ty === 'habitat') r.eunis_match = d.grade || d.target.match || 'close';
      if (!r.authority && !(ty === 'place' && r.lat !== '')) continue;        // nothing to link to
    }
    push(inLink, r);
  }
  return rows;
}
const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const exportIdentities = () => toCSV(ID_HEAD, idRows());

// ---------------------------------------------------------------- export: link_audit.csv (one row per decision, for precision statistics)
const AUDIT_HEAD = ['section', 'kind', 'name', 'entity', 'mentions', 'queue', 'change_kind', 'machine_applied', 'machine_verdict', 'machine_confidence', 'machine_agreement', 'machine_sources', 'machine_round',
  'pipeline_link', 'graph_link', 'machine_link', 'human_decision', 'human_link', 'human_grade', 'via', 'agrees_with_graph', 'agrees_with_machine', 'note', 'reviewed_by', 'reviewed_at'];
function auditRows() {
  const rows = [];
  for (const ty of TYPES) {
    for (const [k, d] of Object.entries(S.ent[ty])) {
      const e = BYK[ty].get(k); const m = e && e.m;
      const graphState = !e ? undefined : e.gone ? { none: 1 } : e.cur || { nolink: 1 };
      const pipe = !e ? '' : e.q === 'changed' ? (e.bsrc ? linkText(ty, e.before) || 'nolink' : 'unknown') : e.drift ? linkText(ty, e.drift.link) : (e.gone ? '' : linkText(ty, e.cur) || 'nolink');
      rows.push({ section: SECTION[ty], kind: 'entity', name: d.label, entity: d.label, mentions: e ? e.n : '', queue: e ? e.q : 'not in this graph', change_kind: e && e.ck || '',
        machine_applied: m ? (m.ap && !m.ineff ? 'y' : 'n') : '', machine_verdict: m ? m.word : '', machine_confidence: m && m.c != null ? m.c : '', machine_agreement: m && m.a != null ? m.a : '',
        machine_sources: m ? (m.s || []).join('+') : '', machine_round: m && m.r ? ((D.rounds.find(r => r.n === m.r) || {}).label || m.r) : '',
        pipeline_link: pipe, graph_link: graphState ? linkText(ty, graphState) : '', machine_link: m ? linkText(ty, machineState(ty, e)) : '',
        human_decision: d.d, human_link: d.d === 'link' ? linkText(ty, d.target) : '', human_grade: d.d === 'link' ? d.grade || '' : '', via: d.via || '',
        agrees_with_graph: graphState ? sameState(ty, d, graphState) : '', agrees_with_machine: m ? sameState(ty, d, machineState(ty, e)) : '', note: d.note || '', reviewed_by: d.by || S.who || '', reviewed_at: d.t || '' });
    }
    for (const f of Object.values(S.form[ty])) {
      const e = FORMK[ty].get(cf(f.name)); const fr = e && e.forms.find(x => cf(x.f) === cf(f.name)); const fm = fr && fr.m;
      const mlink = fm ? (fm.none ? 'none' : fm.nolink ? 'nolink' : fm.key ? linkText('taxon', { key: fm.key, sci: fm.sci }) : '') : '';
      const hlink = f.d === 'same' ? [f.to, f.toLink && f.toLink.key ? 'gbif:' + f.toLink.key : ''].filter(Boolean).join(' ') : '';
      const inGraph = e ? (cf(e.l) === cf(f.to || '') && (ty !== 'taxon' || !f.toLink || String(f.toLink.key) === String((e.cur || {}).key || '')) ? 'same' : 'other') : '';
      rows.push({ section: SECTION[ty], kind: f.via === 'merge' ? 'merge' : 'name', name: f.name, entity: f.ent || (e ? e.l : ''), mentions: fr ? fr.n : '', queue: e ? e.q : 'not in this graph', change_kind: fr && fr.was ? fr.was.ck : '',
        machine_applied: fm ? (fm.ap ? 'y' : 'n') : '', machine_verdict: fm ? fm.d : '', machine_confidence: fm ? fm.c : '', machine_agreement: fm ? fm.a : '', machine_sources: fm ? (fm.s || []).join('+') : '',
        machine_round: fm && fm.r ? ((D.rounds.find(r => r.n === fm.r) || {}).label || fm.r) : '', pipeline_link: fr && fr.was ? (fr.was.key ? 'gbif:' + fr.was.key : 'nolink') : '',
        graph_link: e ? [e.l, linkAuth(ty, e.cur)].filter(Boolean).join(' ') : '', machine_link: mlink, human_decision: f.d, human_link: hlink, human_grade: '', via: f.via || '',
        agrees_with_graph: f.d === 'same' ? (inGraph === 'same' ? 'y' : 'n') : (f.d === 'own' && e && cf(e.l) === cf(f.name) && e.forms.length === 1 ? 'y' : 'n'),
        agrees_with_machine: fm && fm.d !== 'unsure' ? ((f.d === 'none') === !!fm.none && (f.d !== 'same' || !fm.key || !f.toLink || String(fm.key) === String(f.toLink.key)) && (f.d !== 'own' || !!fm.nolink) ? 'y' : 'n') : '',
        note: f.note || '', reviewed_by: f.by || S.who || '', reviewed_at: f.t || '' });
    }
  }
  return rows;
}
const exportAudit = () => toCSV(AUDIT_HEAD, auditRows());
function progressJSON() { return JSON.stringify({ app: 'laubmann-link-check', v: 1, export: D.export, built: D.built, saved: new Date().toISOString(), state: { who: S.who, ent: S.ent, form: S.form } }); }
function typeProgress(ty, all) {     // mention-weighted; of the chosen corpus unless `all`
  let n = 0, done = 0, ents = 0, dn = 0, unsure = 0;
  for (const e of (all ? ENTS[ty] : corpusItems(ty))) { const w = all ? e.n : cn(e); n += w; ents++; if (entDone(ty, e)) { done += w; dn++; const d = entDec(ty, e); if (d && d.d === 'unsure') unsure++; } }
  return { n, done, ents, dn, unsure, pct: n ? Math.floor(done / n * 1000) / 10 : 0 };
}
function statusLine() { return TYPES.map(ty => { const p = typeProgress(ty, true); return t('type.' + ty) + ': ' + fmt(p.dn) + '/' + fmt(p.ents) + ' (' + t('list.progress', p.pct.toLocaleString(loc())) + ')'; }).join('\n'); }
function exportFiles() {
  return [['review/identities.csv', exportIdentities()], ['link_audit.csv', exportAudit()], ['link_progress.json', progressJSON()],
    ['LIESMICH.txt', t('liesmich', new Date().toISOString(), D.export, D.base_export || '-', S.who || '-', statusLine())]];
}
// minimal ZIP (store only)
function crc32(buf) { let c, crc = 0xFFFFFFFF; for (let i = 0; i < buf.length; i++) { c = (crc ^ buf[i]) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; } return (crc ^ 0xFFFFFFFF) >>> 0; }
function makeZip(files) {
  const enc = new TextEncoder(); const parts = []; const central = []; let off = 0; const now = new Date();
  const dt = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xFFFF; const dd = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xFFFF;
  const le = (n, b) => { const a = new Uint8Array(b); for (let i = 0; i < b; i++) a[i] = (n >>> (8 * i)) & 0xFF; return a; };
  for (const [name, text] of files) {
    const nm = enc.encode(name), data = enc.encode(text); const crc = crc32(data);
    const lo = [le(0x04034b50, 4), le(20, 2), le(0x0800, 2), le(0, 2), le(dt, 2), le(dd, 2), le(crc, 4), le(data.length, 4), le(data.length, 4), le(nm.length, 2), le(0, 2), nm, data];
    const ce = [le(0x02014b50, 4), le(20, 2), le(20, 2), le(0x0800, 2), le(0, 2), le(dt, 2), le(dd, 2), le(crc, 4), le(data.length, 4), le(data.length, 4), le(nm.length, 2), le(0, 2), le(0, 2), le(0, 2), le(0, 2), le(0, 4), le(off, 4), nm];
    parts.push(...lo); central.push(...ce); off += lo.reduce((a, x) => a + x.length, 0);
  }
  const cenLen = central.reduce((a, x) => a + x.length, 0);
  parts.push(...central, le(0x06054b50, 4), le(0, 2), le(0, 2), le(files.length, 2), le(files.length, 2), le(cenLen, 4), le(off, 4), le(0, 2));
  return new Blob(parts, { type: 'application/zip' });
}
function download(name, blob) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
const stampName = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1-$2');
const whoSlug = () => (S.who || 'x').replace(/[^\p{L}\p{N}]+/gu, '_');

// ---------------------------------------------------------------- import: this page; Laubmann_Validierung.html (pruefung)
async function readZipJSON(buf) {
  const u = new Uint8Array(buf); const dv = new DataView(buf); const td = new TextDecoder();
  for (let i = 0; i + 30 < u.length;) {
    if (dv.getUint32(i, true) !== 0x04034b50) break;
    const size = dv.getUint32(i + 18, true), nl = dv.getUint16(i + 26, true), xl = dv.getUint16(i + 28, true);
    const name = td.decode(u.subarray(i + 30, i + 30 + nl)); const start = i + 30 + nl + xl;
    if (/(^|\/)(link_progress|validation_progress)\.json$/.test(name)) return JSON.parse(td.decode(u.subarray(start, start + size)));
    i = start + size;
  }
  throw new Error(t('im.nozip'));
}
const newer = (a, b) => !a || (b.t || '') > (a.t || '');
function importOwn(st, ops) {
  let n = 0;
  for (const store of ['ent', 'form']) for (const ty of TYPES) for (const [k, d] of Object.entries(((st[store] || {})[ty]) || {})) if (d && d.d && newer(S[store][ty][k], d)) { ops.push([store, ty, k, d]); n++; }
  if (st.who && !S.who) S.who = st.who;
  return [n, 0];
}
// target of a decision of Laubmann_Validierung.html -> a link of this page
function pruefTarget(ty, x) {
  if (!x) return null;
  if (ty === 'taxon') return x.key ? { key: String(x.key), sci: x.sci || '', rank: x.rank || '', label: x.label || '' } : null;
  if (ty === 'person') return x.qid || x.gnd ? { qid: x.qid || '', gnd: x.gnd || '', label: x.label || '' } : null;
  if (ty === 'place') return x.lat != null ? { lat: +x.lat, lon: +x.lon, unc: x.unc || null, gn: x.gn || '', qid: x.qid || '', osm: x.osm || '', name: x.name || '' } : null;
  return x.code ? { code: x.code, match: x.match || 'close', label: x.label || '' } : null;
}
function importPruefung(st, ops) {
  let n = 0, lost = 0;
  const meta = d => ({ by: d.by || '', t: d.t || new Date().toISOString(), note: d.note || '' });
  // name-level decisions: y belongs, o other entry / species, k not a name, x own entry (u: no effect)
  for (const ty of TYPES) for (const [key, d] of Object.entries(((st.names || {})[ty]) || {})) {
    if (!d || !d.d) continue;
    const e = FORMK[ty].get(cf(key)); const fr = e && e.forms.find(x => cf(x.f) === cf(key)); const name = (fr && fr.f) || d.written || key;
    let o = null;
    if (d.d === 'k') o = { d: 'none' };
    else if (d.d === 'x') o = { d: 'own' };
    else if (d.d === 'y' && e) o = { d: 'same', to: e.l, toLink: ty === 'taxon' && e.cur ? { key: e.cur.key, sci: e.cur.sci, rank: e.cur.rank } : undefined };
    else if (d.d === 'o' && d.target) {
      if (d.target.none) o = { d: 'none' };
      else if (d.target.own) o = { d: 'own' };
      else if (d.target.label) o = { d: 'same', to: d.target.label, toLink: ty === 'taxon' && d.target.key ? { key: String(d.target.key), sci: d.target.sci || '', rank: d.target.rank || '' } : undefined };
    }
    if (!o) { if (d.d !== 'u') lost++; continue; }
    o = Object.assign(o, { name, ent: e ? e.l : '', via: 'import' }, meta(d));
    if (newer(S.form[ty][cf(name)], o)) { ops.push(['form', ty, cf(name), o]); n++; }
  }
  // entry-level decisions, keyed "type:written label"
  for (const [key, d] of Object.entries(st.dec || {})) {
    const i = key.indexOf(':'); const ty = key.slice(0, i); if (!TYPES.includes(ty) || !d || !d.d) continue;
    const e = BYK[ty].get(cf(key.slice(i + 1))); if (!e) { lost++; continue; }
    let d2 = d.d, target = d.target || null, via = 'import', o = null;
    if (d2 === 'a') {                                // "accept the machine": applied -> the graph has it; else its proposal
      const p = e.m && e.m.prop;
      if (e.m && e.m.ap && !e.m.ineff) o = e.gone ? { d: 'none' } : e.cur ? { d: 'link', target: e.cur } : { d: 'nolink' };
      else if (p) o = p.none ? { d: 'none' } : p.nolink ? { d: 'nolink' } : { d: 'link', target: p };
    } else if (d2 === 'r') {                         // "reject the machine": the state before it
      if (e.q === 'changed') o = e.before ? { d: 'link', target: e.before } : { d: 'nolink' };
      else if (e.q === 'confirmed') o = { d: 'nolink' };
      else if (e.q === 'suggest') o = e.cur ? { d: 'link', target: e.cur } : { d: 'nolink' };
    } else if (d2 === 'y') o = e.cur ? { d: 'link', target: e.cur } : null;
    else if (d2 === 'k') o = { d: ty === 'person' || ty === 'habitat' ? 'nolink' : 'none' };
    else if (d2 === 'u') o = { d: 'unsure' };
    else if (d2 === 'o' && target) { const x = pruefTarget(ty, target); o = target.none ? { d: 'none' } : target.own || target.nolink ? { d: 'nolink' } : x ? { d: 'link', target: x } : null; }
    if (!o) { lost++; continue; }
    const full = Object.assign({ via, label: e.l, fs: namesOf(e), chk: 1 }, o, meta(d));
    if (full.d === 'link') { full.target = slim(ty, full.target); full.grade = defaultGrade(ty, full.target, e); }
    if (keepsName(ty, e, full.d)) full.keep = 1;
    if (newer(S.ent[ty][e.k], full)) { ops.push(['ent', ty, e.k, full]); n++; }
  }
  if (st.who && !S.who) S.who = st.who;
  return [n, lost];
}
function importAny(j) {
  const ops = []; let res;
  const st = j.state || j;
  if (j.app === 'laubmann-link-check' || (st.ent && st.form)) res = importOwn(st, ops);
  else if (j.app === 'laubmann-validierung' || (st.dec && st.names)) res = importPruefung(st, ops);
  else throw new Error(t('im.unknown'));
  if (ops.length) commit('import', ops); else refresh();
  return res;
}
