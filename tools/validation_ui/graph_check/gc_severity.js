/* Graph-Prüfung — gravity of flags.

   THE table: every rule that turns a finding, an automatic change or a hint into one of four levels
   lives in SEV. Colour carries the level, the marker carries the kind of flag:
       3 schwer (red) · 2 mittel (orange) · 1 leicht (amber) · 0 Hinweis (grey-blue)
       "!" finding of a check · "M" automatic change · "?" suggestion / missing · "×" removed · "✓" decided
   The README and the page (help, overview) show the same table; the page builds it from SEV (sevDoc). */

const SEV = {
  rec: {   // finding of a scan check on a record: its gravest field, then the two adjustments
    spurious: 3, unsure: 1,
    field: { species: 3, sci: 3, name: 3, status: 3,   // sci / name: the checks' codes for the scientific / German species name
      count: 2, date: 2, locality: 2, observer: 2, record_type: 2,
      georef: 1, place: 1,   // concerns the place name; decided on the link page
      sex: 1, life_stage: 1, breeding: 1, evidence: 1, call: 1, vocalisation: 1, behav: 1, behaviour: 1, notes: 1, other: 1 },
    both: +1,                // both checks flag the record (max 3)
    lowConf: 0.8, lowConfDelta: -1 },   // confidence below 0.8 (min 1)
  miss: { observation: 2, other: 1 },   // missing record; person, travel, weather, other statement
  ent: { date: 3, place: 2, kind: 1 },  // entry header found wrong
  name: {   // applied machine decision on a name of the entry
    taxa: { relinked: 2, removed: 2, linked: 1, rekeyed: 1 },   // rekeyed: another GBIF record of the same scientific name
    places: { moved: 1, removed: 1, linked: 0 },
    persons: { moved: 1, removed: 1, linked: 0 },
    habitats: { moved: 1, removed: 1, linked: 0 },
    confirmed: 0, suggest: 0 },         // confirmed, unchanged · suggestion below the thresholds
  auto: { species: 2, dropped: 2, field: 1 },   // automatic value correction on one record
  tc: { birdOrNumber: 2, place: 1, other: 0 },  // applied reading correction that a check contests, by what it changes
  qa: { transcript_illegible: 2, review_not_taxon: 2, value_dropped: 1,   // review_not_*: the name rules above, when the name has no row of its own
    non_bird: 1, low_confidence_taxon: 1, nonplace: 1, date_year_corrected: 1, date_corrected: 1, date_from_position: 1,
    review_not_place: 1, review_not_person: 1, review_not_habitat: 1, other: 0 },
  ins: { unread: 2, partly: 1, other: 0 },      // text insert by its read state
};
const LEVELS = [3, 2, 1];
const lvName = lv => t('lv_' + lv);

function recFindingLevel(rec) {   // 0 = no finding
  let best = 0, conf = null, n = 0;
  for (const c of ['g', 's']) {
    const f = rec[c]; if (!f || !f.v || f.v === 'ok') continue; let lv;
    if (f.v === 'spurious') { lv = SEV.rec.spurious; n++; }
    else if (f.v === 'unsure') lv = SEV.rec.unsure;
    else { n++; lv = 0; for (const x of f.f || []) lv = Math.max(lv, SEV.rec.field[x] != null ? SEV.rec.field[x] : SEV.rec.field.other); lv = lv || SEV.rec.field.other; }
    if (lv > best || (lv === best && (f.c || 0) > (conf || 0))) { best = lv; conf = f.c; }
  }
  if (!best) return 0;
  if (n >= 2) best += SEV.rec.both;
  if (conf != null && conf < SEV.rec.lowConf) best += SEV.rec.lowConfDelta;
  return Math.max(1, Math.min(3, best));
}
function recAutoLevel(rec) { let lv = 0; for (const a of rec.auto || []) lv = Math.max(lv, a[0] === 'value' ? SEV.auto.species : a[0] === 'drop' || a[0] === 'dropped' ? SEV.auto.dropped : SEV.auto.field); return lv; }
const recLevel = rec => Math.max(recFindingLevel(rec), recAutoLevel(rec));
const missLevel = x => (x.src === 'h' ? 0 : x.kind === 'observation' ? SEV.miss.observation : SEV.miss.other);
function entLevel(ent) { let lv = 0; for (const c of ['g', 's']) { const f = (ent || {})[c]; if (!f) continue; for (const k of ['date', 'place', 'kind']) if (f[k + '_ok'] === false) lv = Math.max(lv, SEV.ent[k]); } return lv; }
function tcLevel(c) {
  const scan = c[11] === 'scan';   // the scan agent's correction: the machine layer applies it, like a contested one it wants a look
  if (!c[2] && !scan) return 0; const contested = scan || [c[6], c[7]].some(v => v === 'wrong' || v === 'partly'); if (!contested) return 0;
  return /[bn]/.test(c[5] || '') ? SEV.tc.birdOrNumber : c[5] ? SEV.tc.place : SEV.tc.other;
}
const qaLevel = q => (SEV.qa[q[0]] != null ? SEV.qa[q[0]] : SEV.qa.other);
const insLevel = st => (SEV.ins[st] != null ? SEV.ins[st] : SEV.ins.other);
function nameLevel(key, info) {   // by what the applied machine row did to the link
  const section = key.slice(0, key.indexOf('|')); const kind = nameKind(key, info); const T = SEV.name[section] || SEV.name.places;
  if (kind === 'confirmed') return SEV.name.confirmed; if (kind === 'suggest' || kind === 'same') return SEV.name.suggest;
  if (kind === 'removed') return T.removed;
  const b = info.before || [], n = info.now || []; const has = (a, i) => a[i] != null && a[i] !== '';
  if (section === 'taxa') return !has(b, 2) && has(n, 2) ? T.linked : has(b, 2) && !has(n, 2) ? T.removed : cf(String(b[1] || '')) !== cf(String(n[1] || '')) ? T.relinked : T.rekeyed;
  const linkedB = section === 'places' ? has(b, 1) : section === 'persons' ? has(b, 1) || has(b, 2) : has(b, 1);
  const linkedN = section === 'places' ? has(n, 1) : section === 'persons' ? has(n, 1) || has(n, 2) : has(n, 1);
  return !linkedB && linkedN ? T.linked : linkedB && !linkedN ? T.removed : T.moved;
}
// marker = kind of flag
const QA_AUTO = new Set(['date_corrected', 'date_year_corrected', 'date_from_position', 'volume_reassigned', 'value_corrected', 'record_corrected', 'record_added']);
function itemMark(it) {
  if (it.type === 'rec') return flagged(it.o.rec) ? '!' : it.o.rec.auto ? 'M' : ['g', 's'].some(c => it.o.rec[c] && it.o.rec[c].v === 'unsure') ? '?' : '';
  if (it.type === 'miss') return '?';
  if (it.type === 'name') return it.x.kind === 'suggest' ? '?' : 'M';
  if (it.type === 'tc') return it.c[2] ? 'M' : '?';
  if (it.type === 'ent') return it.lv ? '!' : '';
  if (it.type === 'qa') return it.q[1] === 'excluded' ? '×' : QA_AUTO.has(it.q[0]) ? 'M' : 'i';
  if (it.type === 'media') return it.lv ? '!' : '';
  return '';
}
function itemLevel(m, it) {
  if (it.type === 'rec') return recLevel(it.o.rec);
  if (it.type === 'miss') return missLevel(it.x);
  if (it.type === 'name') return nameLevel(it.x.key, it.x.info);
  if (it.type === 'tc') return tcLevel(it.c);
  if (it.type === 'ent') return entLevel(m.rv.ent);
  if (it.type === 'qa') return qaLevel(it.q);
  if (it.type === 'media') return it.ins ? insLevel(it.ins[3].startsWith('read-in') ? 'read' : it.ins[3]) : 0;
  return 0;
}
const lvPill = (lv, n, title) => `<span class="lvp lv${lv}"${title ? ` title="${esc(title)}"` : ''}>${n == null ? '' : esc(String(n))}</span>`;
const lvDot = lv => `<i class="lvd lv${lv}"></i>`;

function sevDoc() {   // the rules as rows for help, overview and README: [group, [[rule, level or adjustment], ...]]
  const R_ = SEV.rec, F = R_.field, N = SEV.name, Q = SEV.qa;
  return [
    ['sd_rec', [['sd_rec_spurious', R_.spurious], ['sd_rec_species', F.species], ['sd_rec_mid', F.count], ['sd_rec_georef', F.georef], ['sd_rec_minor', F.sex], ['sd_rec_unsure', R_.unsure],
      ['sd_rec_both', '+' + R_.both], ['sd_rec_lowconf', String(R_.lowConfDelta).replace('-', '−')]]],
    ['sd_miss', [['sd_miss_obs', SEV.miss.observation], ['sd_miss_other', SEV.miss.other]]],
    ['sd_ent', [['sd_ent_date', SEV.ent.date], ['sd_ent_place', SEV.ent.place], ['sd_ent_kind', SEV.ent.kind]]],
    ['sd_name', [['sd_name_relinked', N.taxa.relinked], ['sd_name_linked', N.taxa.linked], ['sd_name_rekeyed', N.taxa.rekeyed], ['sd_name_place', N.places.moved], ['sd_name_person', N.persons.removed], ['sd_name_habitat', N.habitats.removed], ['sd_name_zero', N.confirmed]]],
    ['sd_auto', [['sd_auto_species', SEV.auto.species], ['sd_auto_field', SEV.auto.field]]],
    ['sd_tc', [['sd_tc_bn', SEV.tc.birdOrNumber], ['sd_tc_p', SEV.tc.place], ['sd_tc_other', SEV.tc.other]]],
    ['sd_qa', [['sd_qa_2', Q.transcript_illegible], ['sd_qa_1', Q.non_bird], ['sd_qa_0', Q.other]]],
    ['sd_ins', [['sd_ins_unread', SEV.ins.unread], ['sd_ins_partly', SEV.ins.partly], ['sd_ins_read', SEV.ins.other]]],
    ['sd_sugg', [['sd_sugg_0', N.suggest]]],
  ];
}
function sevTableHtml() {
  return `<table class="t sevt"><tr><th>${t('sd_h_kind')}</th><th>${t('sd_h_rule')}</th><th>${t('sd_h_level')}</th></tr>` +
    sevDoc().map(([g, rules]) => rules.map(([r, lv], i) => `<tr>${i ? '' : `<td rowspan="${rules.length}" class="sevg">${t(g)}</td>`}<td>${t(r)}</td><td class="sevl">${typeof lv === 'number' ? lvDot(lv) + ' ' + lv + ' ' + lvName(lv) : esc(lv)}</td></tr>`).join('')).join('') + '</table>';
}
function markLegendHtml() {   // colour = level, marker = kind
  return `<span class="li lgh" title="${esc(t('lg_level_t'))}">${t('lg_level')}</span>` + [3, 2, 1, 0].map(lv => `<span class="li">${lvDot(lv)}${lvName(lv)}</span>`).join('') +
    `<span class="li lgh" title="${esc(t('lg_kind_t'))}">${t('lg_kind')}</span>` + [['!', 'lg_err'], ['M', 'lg_auto'], ['?', 'lg_sugg'], ['×', 'lg_gone'], ['✓', 'lg_ok']].filter(x => !(EXPLORER && x[0] === '✓')).map(([m, k]) => `<span class="li"><span class="mk${m === '✓' ? ' mk-ok' : ''}">${m}</span>${t(k)}</span>`).join('');
}
