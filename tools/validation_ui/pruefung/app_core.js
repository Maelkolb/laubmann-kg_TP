// ---------------------------------------------------------------- utilities
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => Number(n || 0).toLocaleString(LANG === 'en' ? 'en-GB' : 'de-DE');
const pct = x => Math.round((x || 0) * 100) + ' %';
const num = x => Number(x).toLocaleString(LANG === 'en' ? 'en-GB' : 'de-DE');
const lc = s => (s || '').toLowerCase();
const fold = s => lc(s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ß/g, 'ss');
const stripTags = s => String(s || '').replace(/<[^>]+>/g, '');
let toastT = null;
function toast(msg, ms) { const el = $('#toast'); el.textContent = msg; el.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('show'), ms || 1800); }
async function loadData() {
  const b64 = $('#data').textContent.trim();
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(ds).text());
}
const LS = 'laubmann-validierung-v1';
const LS_OLD = { pruefung: 'laubmann-pruefung-v1', abgleich: 'hog-validation-v2' };
let D, E, PG, DRIVE, MEN, FORMS, SUG, ROWS, ITEMS, STATS, TAXA, EUNIS, uid2e = new Map(), id2e = new Map();
const KEY2I = new Map();
const TYPES = ['taxon', 'person', 'place', 'habitat'];

// ---------------------------------------------------------------- vocabulary (via t())
const TYPE = k => t('type.' + k);
const CAT = k => STR['cat.' + k] ? t('cat.' + k) : k;
const SRC_KIND = { text: 't', gemtext: 't', scan: 's', gemini: 's', opus: 's', 'entry-check': 's', gbif: 'h', xref: 'h', nominatim: 'h', anchor: 'h', generic: 'h', incoming: 't' };
// part A: machine-checked (sign-off) · part B: not machine-checked (own review)
const TABS = [{ id: 'home' }, { id: 'change', part: 'A' }, { id: 'sample', part: 'A' }, { id: 'open', part: 'A' }, { id: 'tc', part: 'A' }, { id: 'extract', part: 'A' },
  { id: 'unchecked', part: 'B' }, { id: 'habitat', part: 'B' }, { id: 'qa', part: 'B' }, { id: 'log' }];
const TAB = Object.fromEntries(TABS.map(x => [x.id, x]));
const tabLabel = id => t('tab.' + id);
const SECONDS = { change: 30, open: 40, sample: 25, text: 20, extract: 120, rest: 25, tc: 30, unchecked: 30, habitat: 20, qa: 15 };

// ---------------------------------------------------------------- state
// dec: item key -> decision; names: type -> written name (lower case) -> decision; mens: type -> entry_uid|name|occurrence -> decision.
// text / ev: imported from Laubmann_Abgleich.html (reading corrections, evaluation sample), kept and exported.
let S = { who: '', dec: {}, names: {}, mens: {}, text: [], ev: {}, log: [], ui: {} };
function normalizeState() {
  S.dec = S.dec || {}; S.log = S.log || []; S.ui = S.ui || {}; S.text = S.text || []; S.ev = S.ev || {};
  S.names = S.names || {}; S.mens = S.mens || {}; for (const t0 of TYPES) { S.names[t0] = S.names[t0] || {}; S.mens[t0] = S.mens[t0] || {}; }
  S.ui.filt = S.ui.filt || {}; S.ui.sel = S.ui.sel || {}; S.ui.show = S.ui.show || {}; S.ui.mode = S.ui.mode || {}; S.ui.adv = S.ui.adv !== false; S.ui.q = S.ui.q || {};
}
const stamp = o => Object.assign({}, o, { by: S.who || '', t: new Date().toISOString() });
let saveTimer = null, dirty = 0, lastFile = null, fileHandle = null;
function save() {
  clearTimeout(saveTimer); dirty++;
  saveTimer = setTimeout(async () => {
    try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { toast(t('toast.nosave'), 5000); }
    if (fileHandle) { try { const w = await fileHandle.createWritable(); await w.write(progressJSON()); await w.close(); lastFile = new Date(); dirty = 0; } catch (e) { fileHandle = null; } }
    savedLabel();
  }, 400);
}
function savedLabel() {
  const el = $('#saved'); const time = d => d.toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'de-DE', { hour: '2-digit', minute: '2-digit' });
  if (fileHandle && lastFile) { el.textContent = t('saved.file', time(lastFile)); el.className = 'saved'; }
  else { el.textContent = dirty > 40 ? t('saved.warn', dirty) : t('saved.browser'); el.className = 'saved' + (dirty > 40 ? ' warn' : ''); }
}
const HIST = [];
const snapshot = () => JSON.stringify({ dec: S.dec, names: S.names, mens: S.mens, text: S.text, ev: S.ev, log: S.log });
function commit(label, fn) { HIST.push([label, snapshot(), cur.i, cur.tab]); if (HIST.length > 200) HIST.shift(); fn(); save(); refresh(); }
function undo() {
  const h = HIST.pop(); if (!h) return toast(t('toast.noundo'));
  const o = JSON.parse(h[1]); Object.assign(S, o); normalizeState(); save(); toast(t('toast.undone', h[0]));
  if (h[3] && h[3] !== cur.tab) openTab(h[3], h[2]); else if (h[2] >= 0 && ITEMS[h[2]]) openTab(cur.tab, h[2]); else refresh();
}

// ---------------------------------------------------------------- model
const dec = it => S.dec[it.key] || null;
const isDone = it => { const d = dec(it); return !!(d && d.d); };
const ttOf = it => it.t === 'form' || it.t === 'mention' ? 'taxon' : it.t;
const nameKey = (tt, fi) => lc(((FORMS[tt] || {})[fi] || [''])[0]);
const menKey = (tt, mi) => { const m = (MEN[tt] || {})[mi]; if (!m) return ''; return E[m[1]][1] + '|' + lc(FORMS[tt][m[0]][0]) + '|' + (m.length > 6 ? m[6] : 0); };
function logPush(it, d, lab, time) { S.log.unshift({ k: it.key, d, t: time || new Date().toISOString(), by: S.who, lab }); if (S.log.length > 5000) S.log.pop(); }
function setDec(it, obj, label) {
  commit(label || 'decision', () => {
    if (!obj) { const prev = S.dec[it.key]; if (prev && (prev.obs || prev.miss)) S.dec[it.key] = { d: '', note: prev.note || '', obs: prev.obs, miss: prev.miss, by: prev.by, t: prev.t }; else delete S.dec[it.key]; logPush(it, '', t('d.removed')); return; }
    const prev = S.dec[it.key] || {};
    S.dec[it.key] = stamp(Object.assign({}, obj, { note: prev.note || obj.note || '' }));
    for (const k of ['obs', 'miss']) if (prev[k]) S.dec[it.key][k] = prev[k];
    if (it.t === 'tc') S.dec[it.key].ref = { uid: E[it.ei][1], id: E[it.ei][0], old: it.label, new: it.new };
    if (it.t === 'qa') S.dec[it.key].ref = { uid: it.uid, id: it.id, reason: it.k, value: it.label };
    logPush(it, obj.d, decLabel(it, S.dec[it.key]), S.dec[it.key].t);
  });
}
const SUBKINDS = ['names', 'mens', 'obs', 'miss'];
function subStore(it, kind) { const tt = ttOf(it); if (kind === 'names') return S.names[tt]; if (kind === 'mens') return S.mens[tt]; const d = dec(it); return d && d[kind] ? d[kind] : null; }
function subOf(it, kind, key) { const st = subStore(it, kind); return st ? st[key] || null : null; }
function subCount(it) {
  const tt = ttOf(it); let n = 0;
  if (it.forms && S.names[tt]) for (const fi of it.forms) if (S.names[tt][nameKey(tt, fi)]) n++;
  if (it.ev && S.mens[tt]) for (const mi of it.ev) if (S.mens[tt][menKey(tt, mi)]) n++;
  const d = dec(it); if (d) for (const k of ['obs', 'miss']) if (d[k]) n += Object.keys(d[k]).length;
  return n;
}
function setSub(it, kind, key, val, label) {
  commit(label || 'item decision', () => {
    if (kind === 'names' || kind === 'mens') { const st = kind === 'names' ? S.names[ttOf(it)] : S.mens[ttOf(it)]; if (!val) delete st[key]; else st[key] = stamp(val); }
    else {
      const d = S.dec[it.key] || (S.dec[it.key] = stamp({ d: '', note: '' }));
      d[kind] = d[kind] || {};
      if (!val) delete d[kind][key]; else d[kind][key] = stamp(val);
      if (!Object.keys(d[kind]).length) delete d[kind];
      if (!d.d && !d.obs && !d.miss) delete S.dec[it.key];
    }
    logPush(it, 'sub', label || 'item decision');
  });
}
// state of one written name after entity decision + override: y (belongs), o (other), k (none), x (own entity), u, ''
function nameState(it, fi) {
  const tt = ttOf(it); const s = subOf(it, 'names', nameKey(tt, fi)); if (s) return s.d;
  const d = dec(it); if (!d || !d.d) return '';
  if (it.k === 'name-unsure' && !(it.focus || []).includes(+fi)) return '';
  if (it.t === 'habitat') return { y: 'y', o: 'y', k: 'k', a: 'y', r: 'y' }[d.d] || '';
  return { a: 'y', y: 'y', r: 'y', k: 'k', o: 'o', u: 'u' }[d.d] || '';
}
function decLabel(it, d) {
  if (!d) return '';
  if (!d.d) return subCount(it) ? t('d.partial', subCount(it)) : '';
  let L;
  if (it.t === 'tc') L = t('d.tc.' + d.d, d.target ? '„' + d.target.value + '“' : '');
  else if (it.t === 'qa') L = t('d.qa.' + d.d, d.target ? d.target.fix : '');
  else if (it.t === 'habitat' && d.d === 'o') L = t('d.o', d.target ? d.target.code + ' ' + (d.target.label || '') : '');
  else if (it.t === 'habitat' && d.d === 'y') L = t('d.hab.y');
  else if (it.t === 'habitat' && d.d === 'k') L = t('d.hab.k');
  else if (d.d === 'a') L = it.t === 'entry' ? t('d.a.entry') : t('d.a');
  else if (d.d === 'r') L = it.t === 'entry' ? t('d.r.entry') : (it.q === 'sample' || it.q === 'rest') ? t('d.r.sample') : t('d.r');
  else if (d.d === 'o') L = t('d.o', d.target ? targetLabel(d.target) : '');
  else if (d.d === 'u') L = t('d.u');
  else if (d.d === 'y') L = t('d.y');
  else if (d.d === 'k') L = t(it.t === 'person' ? 'd.k.person' : it.t === 'place' ? 'd.k.place' : 'd.k.taxon');
  else L = d.d;
  const n = subCount(it);
  return L + (n ? ' · ' + t(n === 1 ? 'd.sub' : 'd.subs', n) : '');
}
function targetLabel(x) { if (!x) return ''; if (x.none) return t('d.none'); if (x.own) return t('d.own'); if (x.nolink) return t('d.nolink'); if (x.fix) return x.fix; if (x.code) return x.code + ' ' + (x.label || ''); return [x.label || x.name || x.qid, x.sci ? '(' + x.sci + ')' : '', x.qid && x.label ? x.qid : '', x.gnd ? 'GND ' + x.gnd : '', x.lat != null && !x.name && !x.label ? (+x.lat).toFixed(4) + ', ' + (+x.lon).toFixed(4) : '', x.value ? '„' + x.value + '“' : ''].filter(Boolean).join(' '); }

// queues and filters
const QUEUES = {};
const QNAMES = ['change', 'open', 'sample', 'extract', 'text', 'rest', 'tc', 'unchecked', 'habitat', 'qa'];
function buildQueues() {
  for (const q of QNAMES) QUEUES[q] = [];
  for (const it of ITEMS) (QUEUES[it.q] = QUEUES[it.q] || []).push(it);
  for (const q in QUEUES) QUEUES[q].sort((a, b) => a.pos - b.pos);
  QUEUES.tcSample = QUEUES.tc.filter(it => it.stratum); QUEUES.tcReview = QUEUES.tc.filter(it => it.rev && it.rev.length);
}
function tabItems(tab) {
  if (tab === 'extract') return (S.ui.mode.extract === 'text') ? QUEUES.text : QUEUES.extract;
  if (tab === 'sample') return (S.ui.mode.sample === 'all') ? QUEUES.sample.concat(QUEUES.rest) : QUEUES.sample;
  if (tab === 'tc') { const m = S.ui.mode.tc || 'sample'; return m === 'review' ? QUEUES.tcReview : m === 'all' ? QUEUES.tc : QUEUES.tcSample; }
  return QUEUES[tab] || [];
}
const STATE_F = ['state', [['open', 'f.open', it => !isDone(it)], ['done', 'f.done', it => isDone(it)]]];
const TC_KINDS = ['bird', 'num', 'place', 'word', 'ins', 'del'];
const FILTERS = {
  change: [['type', [['taxon', 'f.taxa', it => it.t === 'taxon' || it.t === 'form'], ['person', 'f.persons', it => it.t === 'person'], ['place', 'f.places', it => it.t === 'place'], ['habitat', 'f.habitats', it => it.t === 'habitat'], ['mention', 'f.mentions', it => it.t === 'mention']]],
    ['auto', [['auto', 'f.auto', it => it.auto], ['prop', 'f.prop', it => !it.auto]]], STATE_F],
  open: [['type', [['taxon', 'f.taxa', it => it.t === 'taxon'], ['person', 'f.persons', it => it.t === 'person'], ['place', 'f.places', it => it.t === 'place' && it.k !== 'unlocatable'], ['habitat', 'f.habitats', it => it.t === 'habitat'], ['unloc', 'f.unloc', it => it.k === 'unlocatable']]], STATE_F],
  sample: [['type', [['taxon-text', 'f.taxon-text', it => it.stratum === 'taxon-text'], ['taxon-scan', 'f.taxon-scan', it => it.stratum === 'taxon-scan'], ['person', 'f.person', it => it.stratum === 'person'], ['place-text', 'f.place-text', it => it.stratum === 'place-text'], ['place-corr', 'f.place-corr', it => it.stratum === 'place-corr'], ['habitat', 'f.habitats', it => it.stratum === 'habitat']]], STATE_F],
  extract: [STATE_F],
  tc: [['kind', TC_KINDS.map(k => [k, 'tck.' + k, it => it.k === k])], ['applied', [['y', 'f.applied', it => it.applied === 'y'], ['n', 'f.notApplied', it => it.applied !== 'y']]],
    ['why', [['m-wrong', 'f.mWrong', it => (it.rev || []).includes('m-wrong')], ['m-unclear', 'f.mUnclear', it => (it.rev || []).includes('m-unclear')], ['not-applied', 'f.notApplied2', it => (it.rev || []).includes('not-applied')]]], STATE_F],
  unchecked: [['type', [['taxon', 'f.taxa', it => it.t === 'taxon'], ['person', 'f.persons', it => it.t === 'person'], ['place', 'f.places', it => it.t === 'place']]],
    ['link', [['linked', 'f.linked', it => it.k === 'linked'], ['unlinked', 'f.unlinked', it => it.k === 'unlinked']]], ['many', [['m3', 'f.m3', it => it.n >= 3], ['m1', 'f.m1', it => it.n < 3]]], STATE_F],
  habitat: [['link', [['linked', 'f.hlinked', it => it.k === 'linked'], ['unlinked', 'f.hunlinked', it => it.k === 'unlinked']]], STATE_F],
  qa: [['reason', null], STATE_F],
};
function filterOpts(tab, key, opts) {
  if (opts) return opts;
  if (tab === 'qa' && key === 'reason') { const seen = new Map(); for (const it of QUEUES.qa) seen.set(it.k, (seen.get(it.k) || 0) + 1); return [...seen.keys()].map(r => [r, 'qa.' + r, it => it.k === r]); }
  return [];
}
function filtered(tab) {
  let items = tabItems(tab); const f = S.ui.filt[tab] || {};
  for (const [key, opts0] of (FILTERS[tab] || [])) { const on = f[key]; if (!on) continue; const o = filterOpts(tab, key, opts0).find(x => x[0] === on); if (o) items = items.filter(o[2]); }
  const q = fold((S.ui.q || {})[tab] || '').trim();
  if (q) items = items.filter(it => fold(searchText(it)).includes(q));
  return items;
}
function searchText(it) {
  if (it._st) return it._st;
  const tt = ttOf(it);
  const parts = [it.label, it.sci, it.id, it.k, it.reason, it.new, it.detail, it.t === 'qa' ? qaLabel(it.k) : '', (it.names || []).map(n => n[0]).join(' '), (it.forms || []).map(fi => ((FORMS[tt] || {})[fi] || [])[0]).join(' '),
    it.prop && (it.prop.sci || it.prop.de || it.prop.name || it.prop.value || it.prop.qid), it.ei != null && E[it.ei] ? E[it.ei][0] : '', it.cur && it.cur.code];
  return it._st = parts.filter(Boolean).join(' ');
}
const CLS = { a: 'a', y: 'a', r: 'r', k: 'r', o: 'o', e: 'o', u: 'u' };
function progress(items) { const c = { a: 0, r: 0, o: 0, u: 0, n: items.length, done: 0 }; for (const it of items) { const d = dec(it); if (d && d.d) { c.done++; c[CLS[d.d] || 'o']++; } } return c; }
function timeLeft(items, q) { const s = SECONDS[q] || 30; const left = items.filter(it => !isDone(it)).length * s; const mins = Math.round(left / 60); const h = Math.floor(mins / 60), m = mins % 60; return left < 60 ? t('time.lt') : h ? t('time.h', h, m) : t('time.m', m); }

// entry helpers
const entryOf = it => it.ei != null ? E[it.ei] : null;
function pageLabel(p) { const g = PG[p]; return t('scan.band', g[1], g[2]) + (g[3] === 'L' ? t('scan.left') : g[3] === 'R' ? t('scan.right') : '') + (g[4] ? t('scan.p', g[4].replace(/\.$/, '')) : ''); }
const dateDE = s => { if (!s) return ''; const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); return m ? (+m[3]) + '.' + (+m[2]) + '.' + m[1] : s; };
function sourceChips(src, big) {
  return (src || []).map(s => { const k = SRC_KIND[s] || 't'; const lab = STR['src.' + s] ? t('src.' + s) : s; const tip = STR['src.' + s + '.tip'] ? t('src.' + s + '.tip') : ''; return '<span class="bd ' + (k === 's' ? 'scn' : k === 'h' ? 'auth' : 'txt') + (big ? ' big' : '') + '" title="' + esc(tip) + '">' + (k === 's' ? '🖼 ' : k === 'h' ? '🔗 ' : '📄 ') + esc(lab) + '</span>'; }).join('');
}
function sourceIcons(src) { const k = new Set((src || []).map(s => SRC_KIND[s] || 't')); const ks = ['t', 's', 'h'].filter(x => k.has(x)); return '<span class="src" title="' + esc(ks.map(x => t('src.kind.' + x)).join(' + ')) + '">' + ks.map(x => '<i class="' + x + '">' + ({ t: 'T', s: 'S', h: 'N' })[x] + '</i>').join('') + '</span>'; }
function roundChip(it, big) { if (!it.rnd) return ''; const R = (D.rounds || []).find(r => r.n === it.rnd) || {}; return '<span class="bd rnd' + (big ? ' big' : '') + '" title="' + esc(t('rnd.tip', it.rnd, R.model || '', (R.built || '').slice(0, 10), R.graph || '')) + '">R' + it.rnd + '</span>'; }
const qaLabel = r => STR['qa.' + r] ? t('qa.' + r) : r;
