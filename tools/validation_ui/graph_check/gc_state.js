/* Graph-Prüfung — review layer, reviewer state, per-entry model, queues.
   R  = the review layer of build_review.py (+ obs table and sample of build_graph_check.py), read-only.
   RV = what the reviewer decided; the only thing that is stored and exported. Every decision carries
        what it needs for the export (`ref`, the machine's proposal `m`), so the export never depends
        on the review layer the page was built with. Keys:
          rec:<entry_uid>|<written lower>|<obs_index>     tc:<entry_uid>|<old>|<new>
          qa:<entry_uid>|<reason>|<value>                 miss:<entry_uid>|<text>
          entry:<entry_uid>                               name:<section>|<name lower>
          txt:<entry_uid>|<old>                           (free text correction)
        "lower" is Python's str.casefold() as build_review.py uses it (lower case, ß -> ss). */

let R = { meta: {}, pages: [], entries: {}, names: {}, obs: {}, sample: [], graph: {} };
const RV = { v: 1, who: '', dec: {}, log: [] };
// explorer build: the list starts with all entries in diary order; `notes` = the switch "Prüfhinweise zeigen" (always on in the review build)
const RVU = { queue: store('queue') || (EXPLORER ? 'all' : 'finding'), sort: store('qsort') || (EXPLORER ? 'diary' : 'score'), notes: !EXPLORER || store('notes') !== '0', vol: 'all', mid: store('mid') === 'table' ? 'table' : 'graph',
  scan: store('scan') !== '0', media: store('media') !== '0', hints: false, corpus: clamp(+store('corpus') || 0, 0, 3), showOut: false,
  lvf: new Set((store('lvf') || '').split(',').filter(Boolean).map(Number)), card: 0, form: null, list: [], counts: {}, lsFail: false, armed: false };
const LS_STATE = 'laubmann-graphpruefung';
const HIST = [];
const cf = s => String(s == null ? '' : s).toLowerCase().replace(/ß/g, 'ss');
const nowIso = () => new Date().toISOString();

// ------------------------------------------------------------------ vocabularies and value formats (pipeline contracts)
const RECORD_TYPES = ['field-observation', 'third-party-report', 'literature-record'];
const SEXES = ['male', 'female', 'mixed'];
const LIFE_STAGES = ['adult', 'juvenile', 'pullus', 'immature', 'egg', 'mixed'];
const BREEDING = ['confirmed', 'probable', 'possible'];
const STATUSES = ['present', 'absent'];
const ENTRY_KINDS = ['field-day', 'species-digest', 'retrospective', 'correspondence', 'other'];
const CLEAR = new Set(['-', '–', '—']);
// record fields of review/observation_corrections.csv (species goes to review/value_corrections.csv)
const REC_FIELDS = ['species', 'count', 'locality', 'date', 'observer', 'co_observers', 'record_type', 'sex', 'life_stage', 'breeding', 'status'];
const FIELD_VOC = { record_type: [RECORD_TYPES, 'lkg:recordType', false], sex: [SEXES, 'dwc:sex', true], life_stage: [LIFE_STAGES, 'dwc:lifeStage', true],
  breeding: [BREEDING, 'lkg:breedingEvidence', true], status: [STATUSES, 'dwc:occurrenceStatus', false] };
const NUM = "(\\d[\\d.' ]*\\d|\\d)";
const RE_RANGE = new RegExp('^(?:ca\\.?|etwa|ungefähr|rund|gegen)?\\s*' + NUM + '\\s*(?:-|–|bis)\\s*' + NUM + '$');
const RE_ONE = new RegExp('^(ca\\.?|etwa|ungefähr|rund|gegen|an die|mind\\.?|mindestens|über|ueber|>=|>|bis zu|bis|höchstens|max\\.?|<=|<)?\\s*' + NUM + '\\s*(\\+)?$');
function validCount(v) {   // normalization/observation_corrections.py parse_count
  const s = String(v).trim().toLowerCase();
  if (!s) return false;
  if (CLEAR.has(s) || RE_RANGE.test(s) || RE_ONE.test(s)) return true;
  return !/\d/.test(s);
}
function cleanCount(v) {   // a checker's count as the contract accepts it ("16 (5+7+1+3)" -> "16"), or null
  const s = String(v).trim(); if (validCount(s)) return s;
  const a = s.replace(/\s*\([^)]*\)\s*$/, '').trim(); if (a && validCount(a)) return a;
  const b = a.replace(/\s*[♂♀].*$/, '').replace(/\s+(ad|juv|immat)\b\.?.*$/i, '').trim(); if (b && validCount(b)) return b;
  return null;
}
const RE_DATE = /^\d{4}-\d{2}-\d{2}(\s*\/\s*\d{4}-\d{2}-\d{2})?$/;
const normEnum = (v, voc) => { const s = String(v).trim().toLowerCase().replace(/[_ ]/g, '-'); return voc.includes(s) ? s : null; };
function fieldCheck(f, v, lenient) {   // the value as it is exported, or null when the pipeline could not read it
  if (f === 'species') return v && typeof v === 'object' && String(v.de || '').trim() ? { de: String(v.de).trim(), sci: String(v.sci || '').trim(), key: String(v.key || '').trim() } : null;
  const s = String(v == null ? '' : v).trim(); if (!s) return null;
  if (f === 'count') return lenient ? cleanCount(s) : (validCount(s) ? s : null);
  if (f === 'date' || f === 'entry_date') return RE_DATE.test(s) ? s.replace(/\s*\/\s*/, '/') : (f === 'date' && CLEAR.has(s) ? '-' : null);
  if (f === 'entry_kind') return normEnum(s, ENTRY_KINDS);
  const voc = FIELD_VOC[f];
  if (voc) { if (CLEAR.has(s) || (lenient && s.toLowerCase() === 'none')) return voc[2] ? '-' : null; return normEnum(s, voc[0]); }
  return s;   // locality, observer, co_observers: free text, "-" clears
}

// ------------------------------------------------------------------ review layer
async function loadReview() {
  const el = document.getElementById('rv-data'); if (!el) return;
  const b64 = el.textContent.trim(); el.textContent = ''; el.remove();
  if (!b64 || b64 === '{{' + 'REVIEW}}') return;
  const stream = new Blob([decodeB64(b64)]).stream().pipeThrough(new DecompressionStream('gzip'));
  R = Object.assign(R, JSON.parse(await new Response(stream).text()));
}
function prefDe(n, name) {   // literal value independent of the UI language: German, then untagged, then any
  const p = PI(name); if (p < 0 || n < 0) return null; const { sOff, tP, tO } = G; let best = null, bs = -1;
  for (let i = sOff[n], e = sOff[n + 1]; i < e; i++) if (tP[i] === p && tO[i] < 0) {
    const l = -tO[i] - 1; const lg = G.langs[G.litLang[l]]; const sc = lg === 'de' ? 3 : lg === '' ? 2 : 1;
    if (sc > bs) { bs = sc; best = G.lits[l]; }
  }
  return best;
}
const nameOf = n => (n < 0 ? '' : prefDe(n, 'skos:prefLabel') || prefDe(n, 'rdfs:label') || prefDe(n, 'schema:name') || localName(n));
function writtenOf(o) { const w = prefDe(o, 'dwc:verbatimIdentification'); if (w) return w; const tx = node1(o, 'lkg:observedTaxon'); return tx >= 0 ? nameOf(tx) : ''; }
const uidOfNode = e => localName(e).replace(/^entry_/, '');
const flagged = rec => ['g', 's'].some(c => rec[c] && (rec[c].v === 'wrong' || rec[c].v === 'spurious'));
const SECTION_OF = { taxon: 'taxa', place: 'places', person: 'persons', habitat: 'habitats' };
const KIND_OF_SECTION = { taxa: 'taxon', places: 'place', persons: 'person', habitats: 'habitat' };
function authMap(s) { const m = {}; for (const tok of String(s || '').split(/\s+/)) { const i = tok.indexOf(':'); if (i > 0) m[tok.slice(0, i)] = tok.slice(i + 1); } return m; }
function rowDiffers(section, row, now) {   // does a machine row say something else than the link the graph has?
  if (!now) return true; const a = authMap(row.auth);
  if (row.d === 'none') return true;
  if (section === 'taxa') { if (row.d === 'own') return !!now[2]; return a.gbif ? a.gbif !== String(now[2] || '') : cf(row.t) !== cf(now[0]); }
  if (section === 'persons') { if (row.d === 'nolink') return !!(now[1] || now[2]); return (a.wd || '') !== (now[1] || '') || (!!a.gnd && a.gnd !== (now[2] || '')); }
  if (section === 'places') { if (row.d === 'nolink') return now[1] != null && now[1] !== ''; if (row.lat == null || now[1] == null || now[1] === '') return (row.lat == null) !== (now[1] == null || now[1] === '');
    return Math.abs(+row.lat - +now[1]) > 0.005 || Math.abs(+row.lon - +now[2]) > 0.008; }
  if (row.d === 'nolink') return !!now[1]; return (a.eunis || '') !== (now[1] || '') || (row.eunis || '') !== (now[2] || '');
}
function sameLink(section, a, b) {   // before = now? (places: the source note and rounding do not count)
  if (!a || !b) return !a && !b; const eq = (x, y) => cf(x == null ? '' : x) === cf(y == null ? '' : y);
  if (section !== 'places') return [0, 1, 2].every(i => eq(a[i], b[i]));
  const num = (x, y) => (x == null || x === '' || y == null || y === '' ? eq(x, y) : Math.abs(+x - +y) < 1e-4);
  return eq(a[0], b[0]) && num(a[1], b[1]) && num(a[2], b[2]) && eq(a[3], b[3]) && eq(a[4], b[4]);
}
function nameKind(key, info) {   // changed | removed | confirmed | suggest | same
  if (info._k) return info._k; const section = key.slice(0, key.indexOf('|')); const rows = info.rows || []; const applied = rows.filter(r => r.auto);
  let k;
  if (applied.length) k = applied.some(r => r.d === 'none') ? 'removed' : info.before && !sameLink(section, info.before, info.now) ? 'changed' : 'confirmed';
  else k = rows.some(r => rowDiffers(section, r, info.now)) ? 'suggest' : 'same';
  info._k = k; return k;
}
const NODE_KEYS = new Map();
function nodeNameKeys(n, section) {   // name forms of a place / person / habitat node that the machine review has a row for
  let a = NODE_KEYS.get(n); if (a) return a; a = [];
  const forms = uniq([nameOf(n)].concat(litsOf(n, 'skos:altLabel'), litsOf(n, 'rdfs:label')).filter(Boolean));
  for (const f of forms) { const key = section + '|' + cf(f); if (R.names[key] && !a.some(x => x[0] === key)) a.push([key, f]); }
  NODE_KEYS.set(n, a); return a;
}
function forEachName(e, obsNodes, fn) {   // fn(section, key, form, node) for every name of the entry with machine rows
  const hit = (section, form, node) => { if (!form) return false; const key = section + '|' + cf(form); if (!R.names[key]) return false; fn(section, key, form, node); return true; };
  const nodeForms = (n, section) => { for (const [key, f] of nodeNameKeys(n, section)) fn(section, key, f, n); };
  for (const o of obsNodes) {
    const tx = node1(o, 'lkg:observedTaxon'); hit('taxa', writtenOf(o), tx);
    const loc = node1(o, 'lkg:hasLocality'); if (loc >= 0 && !hit('places', prefDe(o, 'dwc:verbatimLocality'), loc)) nodeForms(loc, 'places');
    for (const p of nodeObjs(o, 'dwciri:recordedBy')) nodeForms(p, 'persons');
    const habs = nodeObjs(o, 'dwciri:habitat'); const hv = litsOf(o, 'dwc:habitat');
    for (const h of habs) { let any = false; for (const v of hv) any = hit('habitats', v, h) || any; if (!any) nodeForms(h, 'habitats'); }
  }
  const ep = node1(e, 'lkg:entryPlace'); if (ep >= 0 && !hit('places', prefDe(e, 'dwc:verbatimLocality'), ep)) nodeForms(ep, 'places');
  for (let i = G.sOff[e], end = G.sOff[e + 1]; i < end; i++) { const x = G.tO[i]; if (x >= 0 && G.kind[x] === KI.person) nodeForms(x, 'persons'); }
}

// ------------------------------------------------------------------ summaries of all entries (queues, list badges)
const RVS = new Map();   // entry node -> summary
const QUEUES = ['finding', 'auto', 'tc', 'ins', 'img', 'qa', 'sample', 'all', 'done'].filter(q => !(EXPLORER && q === 'done'));   // no "Geprüft" without decisions
const NOTE_QUEUES = new Set(['finding', 'auto', 'tc', 'qa']);   // queues that are review notes: gone with "Prüfhinweise zeigen" off
const queueList = () => (RVU.notes ? QUEUES : QUEUES.filter(q => !NOTE_QUEUES.has(q)));
function buildSummaries() {
  /* per entry: the keys of its decidable items per queue, and `lv` = [key, level, kind, tier] of every item
     of level >= 1 (gc_severity.js) — the same rules as the cards of the entry (buildItems) */
  const sample = new Set(R.sample || []);
  for (const r of G.ent) {
    const rv = R.entries[r.id] || {}; const uid = rv.uid || uidOfNode(r.n);
    const s = { e: r.n, id: r.id, uid, find: [], miss: [], auto: [], tc: [], qa: [], lv: [], ins: (rv.ins || []).length, unread: 0, img: (rv.media || []).filter(x => IMG_KINDS.has(x[1])).length, sample: sample.has(r.id), chk: rv.chk || '' };
    const lv = (key, level, kind, tier) => { if (level >= 1 && !s.lv.some(x => x[0] === key)) s.lv.push([key, level, kind, tier == null ? -1 : tier]); };
    let hasAuto = false;
    for (const idx in rv.rec || {}) {
      const rec = rv.rec[idx]; const key = 'rec:' + uid + '|' + cf(rec.w) + '|' + idx; if (flagged(rec)) s.find.push(key); if (rec.auto) { s.auto.push(key); hasAuto = true; }
      lv(key, recLevel(rec), recFindingLevel(rec) ? 'rec' : 'auto', rec.t == null ? 0 : rec.t);
    }
    for (const m of rv.miss || []) { const k = 'miss:' + uid + '|' + (m.text || ''); if (m.kind === 'observation' && !s.miss.includes(k)) s.miss.push(k); lv(k, missLevel(m), 'miss'); }
    lv('entry:' + uid, entLevel(rv.ent), 'ent');
    for (const q of rv.qa || []) {
      const key = 'qa:' + uid + '|' + q[0] + '|' + (q[2] || ''); s.qa.push(key);
      const m = /^review_not_(taxon|place|person|habitat)$/.exec(q[0]); const nk = m ? SECTION_OF[m[1]] + '|' + cf(q[2]) : null; const asName = !!(nk && R.names[nk]);
      if (q[1] === 'excluded') s.auto.push(asName ? 'name:' + nk : key);
      if (asName) lv('name:' + nk, nameLevel(nk, R.names[nk]), 'name');
      else if (!((q[0] === 'value_corrected' || q[0] === 'record_corrected') && hasAuto)) lv(key, qaLevel(q), 'qa');
    }
    for (const c of rv.tc || []) { const key = 'tc:' + uid + '|' + c[0] + '|' + c[1]; if ((c[2] || c[11] === 'scan') && c[5]) s.tc.push(key); lv(key, tcLevel(c), 'tc'); }
    for (const i of rv.ins || []) { if (i[3] === 'unread' || i[3] === 'partly') s.unread++; lv('media:' + uid + '|' + i[0], insLevel(i[3].startsWith('read-in') ? 'read' : i[3]), 'ins'); }
    const flat = R.obs[r.id] || []; const obs = []; for (let i = 0; i < flat.length; i += 3) obs.push(flat[i]);
    forEachName(r.n, obs, (section, key) => { const k = nameKind(key, R.names[key]); if ((k === 'changed' || k === 'removed') && !s.auto.includes('name:' + key)) s.auto.push('name:' + key); lv('name:' + key, nameLevel(key, R.names[key]), 'name'); });
    RVS.set(r.n, s);
  }
}
const isDecided = k => { const d = RV.dec[k]; return !!(d && d.d); };
const entryDec = uid => RV.dec['entry:' + uid] || {};
const isChecked = uid => !!entryDec(uid).checked;
function keyDecided(k) {   // as itemDecided, by key
  if (k.startsWith('entry:')) { const d = RV.dec[k] || {}; return !!(d.date || d.kind || d.place || d.hdr); }
  if (k.startsWith('media:')) return false;
  return isDecided(k);
}
const keyInCorpus = x => !(x[3] >= 0 && corpusOn() && x[3] < RVU.corpus);   // record-level items of records outside the corpus do not count
const LVC = new Map();   // entry node -> open items per level [0, leicht, mittel, schwer]; cleared on every decision
function openLevels(s) {
  let c = LVC.get(s.e); if (c) return c; c = [0, 0, 0, 0];
  if (!isChecked(s.uid)) for (const x of s.lv) if (keyInCorpus(x) && !keyDecided(x[0])) c[x[1]]++;
  LVC.set(s.e, c); return c;
}
function inQueue(s, q) {
  if (!entryInCorpus(s)) return false;
  if (q === 'all') return true; if (q === 'done') return isChecked(s.uid); if (q === 'sample') return s.sample;
  if (q === 'finding') return s.miss.length > 0 || (corpusOn() ? queueKeys(s, q).length > 0 : s.find.length > 0); if (q === 'auto') return s.auto.length > 0;
  if (q === 'tc') return s.tc.length > 0; if (q === 'ins') return s.ins > 0; if (q === 'img') return s.img > 0; return s.qa.length > 0;
}
function queueKeys(s, q) {
  if (q === 'finding') { const t_ = corpusOn() ? new Map(s.lv.map(x => [x[0], x[3]])) : null; return (t_ ? s.find.filter(k => (t_.get(k) || 0) >= RVU.corpus) : s.find).concat(s.miss); }
  return q === 'auto' ? s.auto : q === 'tc' ? s.tc : q === 'qa' ? s.qa : [];
}
function isOpen(s, q) {   // still something to decide for this queue
  if (isChecked(s.uid)) return false; const keys = queueKeys(s, q);
  return keys.length ? keys.some(k => !isDecided(k)) : true;
}
const levelOk = s => !RVU.notes || !RVU.lvf.size || [...RVU.lvf].some(l => openLevels(s)[l] > 0);   // level filter chips (schwer / mittel / leicht)
function countQueues() {
  const c = {}; for (const q of QUEUES) c[q] = { n: 0, open: 0 };
  for (const s of RVS.values()) for (const q of QUEUES) if (inQueue(s, q)) { c[q].n++; if (q !== 'done' && isOpen(s, q)) c[q].open++; }
  RVU.counts = c; return c;
}
function levelTotals() {   // open items per level and per kind over the entries of the corpus: {kind: [0, l1, l2, l3]}
  const out = {}; for (const s of RVS.values()) { if (!entryInCorpus(s) || isChecked(s.uid)) continue;
    for (const x of s.lv) if (keyInCorpus(x) && !keyDecided(x[0])) { (out[x[2]] || (out[x[2]] = [0, 0, 0, 0]))[x[1]]++; } }
  return out;
}

// ------------------------------------------------------------------ the open entry
let EM = null;
const TAXA = { list: null, mentions: null };
function taxaIndex() {   // species of the graph for the species search: [label, scientific name, GBIF key, uses, node]
  if (TAXA.list) return TAXA.list; const out = [];
  for (let n = 0; n < G.nodes.length; n++) if (G.kind[n] === KI.taxon) {
    let key = ''; for (const m of MATCH) for (const x of nodeObjs(n, m)) { const c = G.nodes[x]; if (c.startsWith('gbif:')) key = key || c.slice(5); }
    out.push({ label: nameOf(n), sci: prefDe(n, 'dwc:scientificName') || '', key, uses: inCount(n, 'lkg:observedTaxon'), n, alt: litsOf(n, 'skos:altLabel').concat(litsOf(n, 'dwc:vernacularName')) });
  }
  out.sort((a, b) => b.uses - a.uses); TAXA.list = out; return out;
}
function findTaxon(de, sci) { const L = taxaIndex(); const d = cf(de), s = cf(sci); return L.find(x => d && cf(x.label) === d) || L.find(x => s && cf(x.sci) === s) || L.find(x => d && x.alt.some(a => cf(a) === d)) || null; }
function mentionCount(section, form, nodes) {
  if (section === 'taxa') {
    if (!TAXA.mentions) { const m = new Map(); for (const id in R.obs) { const f = R.obs[id]; for (let i = 0; i < f.length; i += 3) { const k = cf(writtenOf(f[i])); m.set(k, (m.get(k) || 0) + 1); } } TAXA.mentions = m; }
    return TAXA.mentions.get(cf(form)) || 0;
  }
  let c = 0; for (const n of nodes || []) c += G.inOff[n + 1] - G.inOff[n]; return c;
}
function countEdit(o) {   // the record's count in the format of the corrections contract
  if (prefDe(o, 'dwc:occurrenceStatus') === 'absent') return '';
  const c = prefDe(o, 'dwc:individualCount'), mn = prefDe(o, 'lkg:individualCountMin'), mx = prefDe(o, 'lkg:individualCountMax'), q = prefDe(o, 'lkg:countQualifier');
  if (mn != null && mx != null) return mn + '-' + mx;
  if (c != null) return ({ minimum: 'mind. ', maximum: 'bis ', approximate: 'ca. ' }[q] || '') + c;
  if (mn != null) return 'mind. ' + mn; if (mx != null) return 'bis ' + mx;
  return q === 'plural-unspecified' ? 'einige' : '';
}
function recVals(o) {   // what the graph says about a record, per editable field
  const loc = node1(o, 'lkg:hasLocality'); const by = nodeObjs(o, 'dwciri:recordedBy').map(nameOf);
  return { species: writtenOf(o), count: countEdit(o), locality: prefDe(o, 'dwc:verbatimLocality') || (loc >= 0 ? nameOf(loc) : ''), date: litsOf(o, 'dwc:eventDate').join('/'),
    observer: by[0] || '', co_observers: by.slice(1).join('; '), record_type: prefDe(o, 'lkg:recordType') || '', sex: prefDe(o, 'dwc:sex') || '', life_stage: prefDe(o, 'dwc:lifeStage') || '',
    breeding: prefDe(o, 'lkg:breedingEvidence') || '', status: prefDe(o, 'dwc:occurrenceStatus') || '' };
}
function showVal(f, v) {   // a field value for display (controlled values with their label)
  if (v == null || v === '') return ''; if (f === 'species') return typeof v === 'object' ? v.de + (v.sci ? ' (' + v.sci + ')' : '') : String(v);
  if (f === 'entry_kind') return cv('lkg:entryKind', v);
  if (CLEAR.has(v)) return t('v_cleared'); const voc = FIELD_VOC[f]; return voc ? cv(voc[1], v) : String(v);
}
function proposal(o, src) {   // what one checker proposes for a record, in the formats of the export
  const f = (o.rec || {})[src]; if (!f || !f.v || f.v === 'ok') return null;
  const p = { src, v: f.v, drop: f.v === 'spurious', vals: {}, bad: {}, other: [], georef: null, fields: f.f || [], c: f.c, why: f.why || '', q: f.q || '', qin: f.qin };
  const fix = f.fix || {};
  for (const k in fix) {
    let v = fix[k]; if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue; v = Array.isArray(v) ? v.join(', ') : String(v);
    if (k === 'species_de') { const de = v.replace(/\s*\(.*?\)\s*/g, ' ').replace(/\?/g, '').replace(/^evtl\.?\s*/i, '').trim(); if (de) p.vals.species = { de, sci: fix.sci ? String(fix.sci) : '', key: '' }; else p.bad.species = v; }
    else if (k === 'sci') { if (!fix.species_de) p.other.push('sci: ' + v); }
    else if (k === 'place') p.georef = v;
    else if (k === 'other' && p.fields.includes('record_type') && RECORD_TYPES.includes(v.trim().toLowerCase())) p.vals.record_type = v.trim().toLowerCase();
    else if (k === 'observer') { const parts = v.split(/\s*;\s*/).filter(Boolean); p.vals.observer = parts[0]; if (parts.length > 1) p.vals.co_observers = parts.slice(1).join('; '); }
    else if (REC_FIELDS.includes(k)) { const ok = fieldCheck(k, v, true); if (ok != null) p.vals[k] = ok; else p.bad[k] = v; }
    else p.other.push(fieldLabel(k) + ': ' + v);
  }
  if (p.vals.species) { const tx = findTaxon(p.vals.species.de, p.vals.species.sci); if (tx) { p.vals.species.key = tx.key; if (!p.vals.species.sci) p.vals.species.sci = tx.sci; } }
  // a georeference finding is about the PLACE; for this one record its locality can be set to the proposed place
  if (p.georef && !('locality' in p.vals) && !('locality' in p.bad)) p.geoLocal = p.georef;
  const cur = recVals(o.n);   // a proposal equal to the graph is none
  for (const k of Object.keys(p.vals)) if (k !== 'species' && cf(p.vals[k]) === cf(cur[k])) delete p.vals[k];
  return p;
}
function mergedProposal(o) {   // what J applies: the proposals of both checks, the more confident one first
  const ps = ['g', 's'].map(c => proposal(o, c)).filter(p => p && p.v !== 'unsure'); if (!ps.length) return null;
  ps.sort((a, b) => (b.c || 0) - (a.c || 0));
  const m = { drop: ps[0].drop && !ps.some(p => !p.drop && Object.keys(p.vals).length), vals: {}, bad: {}, from: {}, srcs: ps.map(p => p.src), geo: false };
  for (const p of ps) {
    for (const k in p.vals) if (!(k in m.vals)) { m.vals[k] = p.vals[k]; m.from[k] = p.src; }
    for (const k in p.bad) if (!(k in m.vals) && !(k in m.bad)) m.bad[k] = p.bad[k];
    if (p.geoLocal && !('locality' in m.vals)) { m.vals.locality = p.geoLocal; m.from.locality = p.src; m.geo = true; }
  }
  for (const k in m.bad) if (k in m.vals) delete m.bad[k];
  return m;
}
function machineOf(o) {   // snapshot of what the machine said about a record, stored with the decision (audit)
  const m = {}; for (const c of ['g', 's']) { const f = o.rec[c]; if (f) { m[c] = f.v; if (f.v !== 'ok') { m[c + 'f'] = (f.f || []).join(';'); m[c + 'p'] = f.fix || {}; m[c + 'c'] = f.c; } } }
  if (o.rec.auto) m.auto = o.rec.auto.map(a => a.slice(0, 3)); return m;
}
function entryModel(e) { if (EM && EM.e === e) return EM; EM = buildModel(e); return EM; }
function buildModel(e) {   // review data and graph of one entry joined; everything decidable as `items`
  const r = entryRec(e); const rv = R.entries[r.id] || {}; const uid = rv.uid || uidOfNode(e);
  const flat = R.obs[r.id] || []; const obs = []; const byNode = new Map();
  for (let i = 0; i < flat.length; i += 3) {
    const n = flat[i], idx = flat[i + 1], occ = flat[i + 2]; const written = writtenOf(n); let rec = (rv.rec || {})[idx]; if (rec && cf(rec.w) !== cf(written)) rec = null;
    const it = { n, idx, occ, written, rec: rec || {}, key: 'rec:' + uid + '|' + cf(written) + '|' + idx }; obs.push(it); byNode.set(n, it);
  }
  const names = new Map();
  forEachName(e, obs.map(o => o.n), (section, key, form, node) => { let x = names.get(key); if (!x) { x = { section, key, form, nodes: new Set(), info: R.names[key], kind: nameKind(key, R.names[key]) }; names.set(key, x); } if (node >= 0) x.nodes.add(node); });
  // pages of the entry text and of its multimodal regions, in reading order (page ids sort that way)
  const pages = uniq((rv.reg || []).map(g => g[0]).concat((rv.media || []).map(x => x[2]).filter(p => p != null))).sort((a, b) => coll.compare((R.pages[a] || [''])[0], (R.pages[b] || [''])[0]));
  const m = { e, id: r.id, uid, rv, obs, byNode, names, pages };
  m.items = buildItems(m); return m;
}
function buildItems(m) {   // everything decidable for the entry, in the order of the check tab
  const items = []; const { uid, rv } = m;
  for (const o of m.obs) { const fl = ['g', 's'].some(c => o.rec[c] && o.rec[c].v !== 'ok'); if (fl || o.rec.auto || RV.dec[o.key]) items.push({ type: 'rec', group: 'rec', key: o.key, o }); }
  const seen = new Set();
  for (const x of rv.miss || []) { const key = 'miss:' + uid + '|' + (x.text || ''); if (seen.has(key)) { items.find(i => i.key === key).also = x; continue; } seen.add(key); items.push({ type: 'miss', group: 'miss', key, x }); }
  for (const key in RV.dec) if (key.startsWith('miss:' + uid + '|') && !seen.has(key) && RV.dec[key].d === 'add') items.push({ type: 'miss', group: 'miss', key, x: { src: 'h', kind: 'observation', text: key.slice(('miss:' + uid + '|').length) } });
  const qaAsName = new Set();
  for (const q of rv.qa || []) { const mm = /^review_not_(taxon|place|person|habitat)$/.exec(q[0]); if (!mm) continue; const nk = SECTION_OF[mm[1]] + '|' + cf(q[2]);
    if (R.names[nk] && !m.names.has(nk)) { m.names.set(nk, { section: SECTION_OF[mm[1]], key: nk, form: q[2], nodes: new Set(), info: R.names[nk], kind: nameKind(nk, R.names[nk]), detail: q[3] }); qaAsName.add(q[0] + '|' + q[2]); }
    else if (R.names[nk]) qaAsName.add(q[0] + '|' + q[2]); }
  const order = { removed: 0, changed: 1, suggest: 2, confirmed: 3 };
  for (const x of [...m.names.values()].filter(x => x.kind !== 'same').sort((a, b) => order[a.kind] - order[b.kind] || coll.compare(a.form, b.form)))
    items.push({ type: 'name', group: 'name', key: 'name:' + x.key, x });
  (rv.tc || []).forEach((c, i) => items.push({ type: 'tc', group: 'tc', key: 'tc:' + uid + '|' + c[0] + '|' + c[1], c, i }));
  items.push({ type: 'ent', group: 'ent', key: 'entry:' + uid });
  const autoVal = new Set(['value_corrected', 'record_corrected']);
  const qa = (rv.qa || []).filter(q => !qaAsName.has(q[0] + '|' + q[2]) && !(autoVal.has(q[0]) && m.obs.some(o => o.rec.auto)));
  for (const q of qa.filter(q => q[1] === 'excluded').concat(qa.filter(q => q[1] !== 'excluded'))) items.push({ type: 'qa', group: 'qa', key: 'qa:' + uid + '|' + q[0] + '|' + (q[2] || ''), q });
  // every multimodal region; a text insert carries its read state (`ins`)
  const insBy = new Map((rv.ins || []).map(x => [x[0], x])); const media = (rv.media || []).slice();
  for (const x of rv.ins || []) if (!media.some(y => y[0] === x[0])) media.push([x[0], x[1]]);
  media.forEach((x, i) => items.push({ type: 'media', group: 'media', key: 'media:' + uid + '|' + x[0], x, ins: insBy.get(x[0]) || null, i }));
  if (!EXPLORER) items.push({ type: 'done', group: 'done', key: 'done:' + uid });
  m.itemByObs = new Map();
  for (const it of items) { it.lv = itemLevel(m, it); it.mk = itemMark(it); it.sec = itemSec(it); if (it.type === 'rec') m.itemByObs.set(it.o.n, it); }
  return items;
}
// sections of the check tab: by level (schwer first), then hints (collapsed), own changes, entry header, images, finish
const SEC_ORDER = ['l3', 'l2', 'l1', 'hint', 'own', 'ent', 'media', 'done'];
function itemSec(it) { if (it.type === 'done') return 'done'; if (it.lv >= 1) return 'l' + it.lv; if (it.type === 'ent') return 'ent'; if (it.type === 'media') return 'media'; if (it.type === 'rec' || it.type === 'miss') return 'own'; return 'hint'; }
const itemHidden = it => (!RVU.notes && it.type !== 'media') || (it.sec === 'hint' && !RVU.hints && !isDecided(it.key)) || (it.type === 'rec' && corpusOn() && !RVU.showOut && !inCorpus(it.o.n));
function visibleItems(m) { const out = []; for (const sec of SEC_ORDER) for (const it of m.items) if (it.sec === sec && !itemHidden(it)) out.push(it); return out; }
function openByLevel(m) {   // open items of the entry per level [0, leicht, mittel, schwer]; hidden records of another corpus do not count
  const c = [0, 0, 0, 0]; if (isChecked(m.uid)) return c; const seen = new Set();   // two cards with one key (the same reading correction twice) are one decision
  for (const it of m.items) { if (it.type === 'done' || itemDecided(it) || seen.has(it.key)) continue; if (it.type === 'rec' && corpusOn() && !inCorpus(it.o.n)) continue; seen.add(it.key); c[it.lv]++; }
  return c;
}
function itemDecided(it) { if (it.type === 'ent') { const d = RV.dec[it.key] || {}; return !!(d.date || d.kind || d.place || d.hdr); } if (it.type === 'done') return isChecked(it.key.slice(5)); if (it.type === 'media') return false; return isDecided(it.key); }

// ------------------------------------------------------------------ decisions, undo, persistence
function logLine(key, lab) { RV.log.unshift({ k: key, t: nowIso(), by: RV.who || '', lab: lab || '' }); if (RV.log.length > 3000) RV.log.length = 3000; }
function decide(key, val, lab) {   // val = null removes the decision
  if (EXPLORER) return;   // the explorer build decides nothing
  LVC.clear();
  HIST.push([[key, RV.dec[key] ? JSON.parse(JSON.stringify(RV.dec[key])) : null]]); if (HIST.length > 300) HIST.shift();
  if (val == null) delete RV.dec[key]; else RV.dec[key] = Object.assign(val, { by: RV.who || '', t: nowIso() });
  logLine(key, lab || (val ? val.d || '' : 'reset'));
  if (EM) EM.items = buildItems(EM);   // a decided record gets a card, an added record a ghost
  saveSoon(); rvRefresh();
}
function undo() {
  if (EXPLORER) return;
  const h = HIST.pop(); if (!h) { toast(t('undo_none')); return; }
  for (const [k, prev] of h) { if (prev) RV.dec[k] = prev; else delete RV.dec[k]; }
  LVC.clear(); logLine(h[0][0], 'undo'); saveSoon(); if (EM) EM.items = buildItems(EM); rvRefresh(); toast(t('undone'));
}
let fileHandle = null, lastSaved = null, dirtyN = 0;
function saveState() {
  if (EXPLORER) return;
  try { localStorage.setItem(LS_STATE, JSON.stringify(RV)); RVU.lsFail = false; }
  catch (e) { if (!RVU.lsFail) toast(t('ls_full'), 6000); RVU.lsFail = true; }
  lastSaved = new Date(); writeBackup(); rvSavedLabel();
}
const saveSoon = (() => { const f = debounce(saveState, 350); return () => { dirtyN++; f(); }; })();
const writeBackup = debounce(async () => {
  if (!fileHandle) return;
  try { const w = await fileHandle.createWritable(); await w.write(progressJSON()); await w.close(); dirtyN = 0; rvSavedLabel(); }
  catch (e) { toast(t('backup_fail'), 5000); }
}, 1500);
function loadState() {
  if (EXPLORER) return;   // no decided state in the explorer build
  try { const raw = localStorage.getItem(LS_STATE); if (raw) { const j = JSON.parse(raw); if (j && j.dec) { RV.who = j.who || ''; RV.dec = j.dec; RV.log = j.log || []; } } } catch (e) { /* no stored state */ }
}
