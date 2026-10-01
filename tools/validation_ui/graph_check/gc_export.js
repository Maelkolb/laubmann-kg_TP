/* Graph-Prüfung — export of the decisions in the pipeline's review contracts, statistics files,
   progress file (re-loadable), ZIP, import. Everything is written from RV.dec alone: each decision
   carries its `ref` (entry uid/id, written name, index …) and the machine's proposal `m`.

   file in the ZIP                       consumer (loader)
   review/observation_corrections.csv    normalization/observation_corrections.py  load_observation_corrections
   review/value_corrections.csv          normalization/corrections.py              load_corrections
   review/transcript_decisions.csv       extraction/reading.py                     load_transcript_decisions
   review/text_corrections.csv           review/readings.py                        load_readings
   review/qa_decisions.csv               qa.py                                     load_qa_decisions
   review/identities.csv                 review/identities.py                      Identities.load
   entry_checks.csv, graph_audit.csv     statistics
   graph_progress.json, LIESMICH.txt     re-loadable state, read-me */

const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const OC_HEAD = ['entry_uid', 'entry_id', 'written', 'obs_index', 'occurrence', 'action', 'field', 'new_value', 'old_value', 'species_de', 'scientific_name', 'gbif_key', 'count', 'locality', 'date', 'observer', 'record_type', 'text', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const VC_HEAD = ['kind', 'entry_uid', 'entry_id', 'old_value', 'occurrence', 'action', 'new_value', 'scientific_name', 'gbif_key', 'is_bird', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const TD_HEAD = ['entry_uid', 'entry_id', 'old_text', 'new_text', 'decision', 'final_text', 'note', 'reviewed_by', 'reviewed_at'];
const TC_HEAD = ['entry_uid', 'entry_id', 'old_text', 'new_text', 'note', 'reviewed_by', 'reviewed_at'];
const QD_HEAD = ['entry_uid', 'entry_id', 'reason', 'value', 'decision', 'note', 'reviewed_by', 'reviewed_at'];
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const EC_HEAD = ['entry_uid', 'entry_id', 'queue', 'n_records', 'confirmed', 'corrected', 'added', 'dropped', 'reviewed_by', 'reviewed_at'];
const AU_HEAD = ['key', 'kind', 'section', 'entry_uid', 'entry_id', 'subject', 'obs_index', 'source', 'machine_verdict', 'machine_fields', 'machine_proposal', 'machine_confidence', 'human_decision', 'human_value', 'agreed', 'note', 'reviewed_by', 'reviewed_at'];
const whoOf = d => d.by || RV.who || 'reviewer';
const decsOf = type => Object.keys(RV.dec).filter(k => k.startsWith(type + ':')).sort().map(k => [k, RV.dec[k]]);
const blank = head => Object.fromEntries(head.map(h => [h, '']));
const SRC_DE = { g: 'Gemini', s: 'Claude' };
function recReason(d) {
  const m = d.m || {}; const fl = ['g', 's'].filter(c => m[c] === 'wrong' || m[c] === 'spurious').map(c => SRC_DE[c]);
  if (d.d === 'x') { const sp = ['g', 's'].filter(c => m[c] === 'spurious').map(c => SRC_DE[c]); return sp.length ? 'laut Scanprüfung (' + sp.join(' + ') + ') überzählig; bei der Graph-Prüfung gestrichen' : 'bei der Graph-Prüfung am Scan gestrichen'; }
  if (d.d === 'a') return 'Befund der Scanprüfung (' + (fl.join(' + ') || '–') + ') bei der Graph-Prüfung übernommen';
  return 'bei der Graph-Prüfung am Scan korrigiert';
}

function exportObs() {
  const rows = []; const base = (d, ref) => Object.assign(blank(OC_HEAD), { entry_uid: ref.uid, entry_id: ref.id, note: d.note || '', reviewed_by: whoOf(d), reviewed_at: d.t || '' });
  for (const [, d] of decsOf('rec')) {
    if (!(d.d === 'a' || d.d === 'e') || !d.vals || !d.ref) continue; const ref = d.ref; const sp = d.vals.species;
    // after a species replacement (value_corrections.csv, applied first) the record carries the NEW name
    for (const f of REC_FIELDS) if (f !== 'species' && f in d.vals) rows.push(Object.assign(base(d, ref), { written: sp ? sp.de : ref.w, obs_index: ref.idx < 1e6 ? ref.idx : '', occurrence: sp ? '' : ref.occ,
      action: 'set', field: f, new_value: d.vals[f], old_value: (d.old || {})[f] || '', reason: recReason(d) }));
  }
  for (const [, d] of decsOf('miss')) {
    if (d.d !== 'add' || !d.rec || !d.ref) continue; const r = d.rec; const src = (d.m || {}).src;
    rows.push(Object.assign(base(d, d.ref), { written: r.species_de, action: 'add', species_de: r.species_de, scientific_name: r.scientific_name || '', gbif_key: r.gbif_key || '', count: r.count || '', locality: r.locality || '',
      date: r.date || '', observer: r.observer || '', record_type: r.record_type || '', text: r.text || '', reason: SRC_DE[src] ? 'fehlender Datensatz laut Scanprüfung (' + SRC_DE[src] + '), bei der Graph-Prüfung ergänzt' : 'bei der Graph-Prüfung ergänzt' }));
  }
  for (const [, d] of decsOf('entry')) {
    if (!d.ref) continue;
    if (d.date) rows.push(Object.assign(base(d, d.ref), { action: 'set', field: 'entry_date', new_value: d.date.v, old_value: d.date.old || '', reason: 'Datum des Eintrags bei der Graph-Prüfung korrigiert' }));
    if (d.kind) rows.push(Object.assign(base(d, d.ref), { action: 'set', field: 'entry_kind', new_value: d.kind.v, old_value: d.kind.old || '', reason: 'Art des Eintrags bei der Graph-Prüfung korrigiert' }));
  }
  return toCSV(OC_HEAD, rows);
}
function orderTaxonRows(rows) {
  /* corrections.py applies the rows one after the other and counts `occurrence` among the records that
     carry the name AT THAT MOMENT. So within one entry: rows of one name from the highest occurrence
     down (a drop or replacement never shifts a lower one), and the rows of a name before any row that
     renames another record INTO that name. */
  const byEntry = new Map(); for (const r of rows) { if (!byEntry.has(r.entry_uid)) byEntry.set(r.entry_uid, []); byEntry.get(r.entry_uid).push(r); }
  const out = [];
  for (const list of byEntry.values()) {
    const groups = new Map(); for (const r of list) { const k = cf(r.old_value); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); }
    for (const g of groups.values()) g.sort((a, b) => (+b.occurrence || 0) - (+a.occurrence || 0));
    const left = new Set(groups.keys());
    while (left.size) {
      let pick = [...left].find(y => !groups.get(y).some(r => r.action === 'replace' && cf(r.new_value) !== y && left.has(cf(r.new_value))));
      if (pick === undefined) pick = left.values().next().value;   // two names swapped: no order is right for both
      out.push(...groups.get(pick)); left.delete(pick);
    }
  }
  return out;
}
function exportValues() {
  const taxon = [], other = [];
  const base = (d, ref) => Object.assign(blank(VC_HEAD), { kind: 'taxon', entry_uid: ref.uid, entry_id: ref.id, old_value: ref.was || ref.w, occurrence: ref.was ? '' : ref.occ, action: 'replace', note: d.note || '', reviewed_by: whoOf(d), reviewed_at: d.t || '' });
  for (const [, d] of decsOf('rec')) {
    if (!d.ref) continue;
    if (d.d === 'x') taxon.push(Object.assign(base(d, d.ref), { action: 'drop', reason: recReason(d) }));
    else if ((d.d === 'a' || d.d === 'e') && d.vals && d.vals.species) { const sp = d.vals.species; taxon.push(Object.assign(base(d, d.ref), { new_value: sp.de, scientific_name: sp.sci || '', gbif_key: sp.key || '', is_bird: 'y', reason: recReason(d) })); }
  }
  for (const [, d] of decsOf('entry')) if (d.ref && d.place && d.place.old) other.push(Object.assign(blank(VC_HEAD), { kind: 'place', entry_uid: d.ref.uid, entry_id: d.ref.id, old_value: d.place.old, action: 'replace', new_value: d.place.v,
    reason: 'Ort des Eintrags bei der Graph-Prüfung korrigiert', reviewed_by: whoOf(d), reviewed_at: d.t || '' }));
  return toCSV(VC_HEAD, orderTaxonRows(taxon).concat(other));
}
function exportTranscript() {
  return toCSV(TD_HEAD, decsOf('tc').filter(([, d]) => d.ref && ['accept', 'reject', 'edit'].includes(d.d)).map(([, d]) => ({ entry_uid: d.ref.uid, entry_id: d.ref.id, old_text: d.ref.old, new_text: d.ref.new, decision: d.d,
    final_text: d.d === 'accept' ? d.ref.new : d.d === 'reject' ? d.ref.old : d.final || '', note: d.note || '', reviewed_by: whoOf(d), reviewed_at: d.t || '' })));
}
function exportText() {
  return toCSV(TC_HEAD, decsOf('txt').filter(([, d]) => d.ref && d.new).map(([, d]) => ({ entry_uid: d.ref.uid, entry_id: d.ref.id, old_text: d.ref.old, new_text: d.new, note: d.note || 'Graph-Prüfung', reviewed_by: whoOf(d), reviewed_at: d.t || '' })));
}
function exportQA() {
  return toCSV(QD_HEAD, decsOf('qa').filter(([, d]) => d.ref && ['confirm', 'false_alarm'].includes(d.d)).map(([, d]) => ({ entry_uid: d.ref.uid, entry_id: d.ref.id, reason: d.ref.reason, value: d.ref.value, decision: d.d, note: d.note || '', reviewed_by: whoOf(d), reviewed_at: d.t || '' })));
}
function revertRow(section, r, before, form) {   // the link as it was before the machine decision, as a human row (a human row always wins)
  if (r.d !== 'link' && r.d !== 'nolink') {
    if (section === 'taxa' && before && before[2]) return { decision: 'same', target: before[0] || form, authority: 'gbif:' + before[2], scientific_name: before[1] || '' };
    return { decision: 'unsure', reason: 'Maschinenentscheidung bei der Graph-Prüfung zurückgenommen; es gilt die automatische Zuordnung' };
  }
  const tgt = (before && before[0]) || r.t || form;
  if (section === 'persons') return before && (before[1] || before[2]) ? { decision: 'link', target: tgt, authority: [before[1] ? 'wd:' + before[1] : '', before[2] ? 'gnd:' + before[2] : ''].filter(Boolean).join(' ') } : { decision: 'nolink', target: tgt };
  if (section === 'places') return before && before[1] != null && before[1] !== '' ? { decision: 'link', target: tgt, authority: [before[3] ? 'gn:' + before[3] : '', before[4] ? 'wd:' + before[4] : ''].filter(Boolean).join(' '), lat: before[1], lon: before[2] } : { decision: 'nolink', target: tgt };
  return before && before[1] ? { decision: 'link', target: tgt, authority: 'eunis:' + before[1], eunis_match: before[2] || 'close' } : { decision: 'nolink', target: tgt };
}
function exportIdentities() {
  const rows = []; const seen = new Set();
  const push = r => { const k = r.section + '|' + cf(r.name_form) + '|' + (r.decision === 'link' || r.decision === 'nolink' ? 'L' : 'F'); if (seen.has(k)) return; seen.add(k); rows.push(r); };
  for (const [, d] of decsOf('name')) {
    if (!d.ref) continue; const sec = d.ref.section; const form = ((d.rows || []).find(r => r.n) || {}).n || d.ref.form;   // the name as written (machine row), else as the graph has it
    const base = () => Object.assign(blank(ID_HEAD), { section: sec, name_form: form, reviewed_by: whoOf(d), reviewed_at: d.t || '' });
    const mrows = (d.rows || []).filter(r => (d.d === 'apply' ? !r.auto || !(d.rows || []).some(x => !x.auto) : r.auto));
    if (d.d === 'confirm' || d.d === 'apply') for (const r of mrows) push(Object.assign(base(), { decision: r.d, target: r.t || '', authority: r.auth || '', scientific_name: r.sci || '', rank: r.rank || '', lat: r.lat == null ? '' : r.lat, lon: r.lon == null ? '' : r.lon,
      uncertainty_m: r.unc != null && r.unc !== '' ? r.unc : d.d === 'confirm' && r.lat != null ? d.unc || '' : '', eunis_match: r.eunis || '', reason: r.why || '',
      note: [r.note, d.d === 'confirm' ? 'Maschinenentscheidung bei der Graph-Prüfung bestätigt' : 'Maschinenvorschlag bei der Graph-Prüfung übernommen', d.note].filter(Boolean).join(' · ') }));
    else if (d.d === 'revert') for (const r of mrows) push(Object.assign(base(), { note: ['Maschinenentscheidung (' + r.d + (r.t ? ' → ' + r.t : '') + ') bei der Graph-Prüfung zurückgenommen', d.note].filter(Boolean).join(' · ') }, revertRow(sec, r, d.before, d.ref.form)));
  }
  return toCSV(ID_HEAD, rows);
}
function entryCounts(uid) {
  const c = { ok: 0, corrected: 0, dropped: 0, added: 0 }; const pre = 'rec:' + uid + '|', pm = 'miss:' + uid + '|';
  for (const k in RV.dec) { const d = RV.dec[k]; if (k.startsWith(pre)) { if (d.d === 'ok') c.ok++; else if (d.d === 'a' || d.d === 'e') c.corrected++; else if (d.d === 'x') c.dropped++; } else if (k.startsWith(pm) && d.d === 'add') c.added++; }
  return c;
}
function implOf(d) {   // records that count as confirmed because the entry was marked checked (and still have no decision of their own)
  const uid = (d.ref || {}).uid; return ((d.checked || {}).impl || []).filter(x => !isDecided('rec:' + uid + '|' + cf(x[1]) + '|' + x[0]));
}
function exportChecks() {
  return toCSV(EC_HEAD, decsOf('entry').filter(([, d]) => d.checked && d.ref).map(([, d]) => { const c = entryCounts(d.ref.uid); const ch = d.checked;
    return { entry_uid: d.ref.uid, entry_id: d.ref.id, queue: ch.queue || '', n_records: ch.n == null ? '' : ch.n, confirmed: implOf(d).length + c.ok, corrected: c.corrected, added: c.added, dropped: c.dropped, reviewed_by: ch.by || whoOf(d), reviewed_at: ch.t || d.t || '' }; }));
}
// did the human do what the machine said? yes | partly | no | '' (not comparable)
function agreeRec(v, d) {
  if (d === 'u' || d === 'revert' || v === 'unsure' || !v) return '';
  if (v === 'ok') return d === 'ok' ? 'yes' : 'no';
  if (v === 'wrong') return d === 'a' ? 'yes' : d === 'e' || d === 'x' ? 'partly' : 'no';
  return d === 'x' ? 'yes' : 'no';   // spurious
}
function agreeTc(v, d) {   // a checker's verdict on a reading correction against the reviewer's decision
  if (!v || v === 'unclear') return ''; if (v === 'right' || v === 'none') return d === 'accept' ? 'yes' : d === 'edit' ? 'partly' : 'no';
  if (v === 'wrong') return d === 'accept' ? 'no' : 'yes'; return d === 'edit' ? 'yes' : d === 'reject' ? 'partly' : 'no';   // partly
}
function auditRows() {
  const rows = []; const J = o => (o && Object.keys(o).length ? JSON.stringify(o) : '');
  const row = (key, d, o) => rows.push(Object.assign(blank(AU_HEAD), { key, entry_uid: (d.ref || {}).uid || '', entry_id: (d.ref || {}).id || '', note: d.note || '', reviewed_by: whoOf(d), reviewed_at: d.t || '' }, o));
  const SRC = { g: 'gemini', s: 'claude' };
  for (const [key, d] of decsOf('rec')) {
    if (!d.d || !d.ref) continue; const m = d.m || {}; let any = false; const hv = J(d.vals);
    for (const c of ['g', 's']) if (m[c]) { any = true; row(key, d, { kind: 'record_' + m[c], subject: d.ref.w, obs_index: d.ref.idx, source: SRC[c], machine_verdict: m[c], machine_fields: m[c + 'f'] || '', machine_proposal: J(m[c + 'p']), machine_confidence: m[c + 'c'] == null ? '' : m[c + 'c'], human_decision: d.d, human_value: hv, agreed: agreeRec(m[c], d.d) }); }
    if (m.auto) { any = true; row(key, d, { kind: 'auto_value', subject: d.ref.w, obs_index: d.ref.idx, source: 'machine_value', machine_verdict: 'applied', machine_proposal: JSON.stringify(m.auto), human_decision: d.d, human_value: hv, agreed: d.d === 'u' ? '' : d.d === 'revert' || d.d === 'x' || (d.vals && d.vals.species) ? 'no' : 'yes' }); }
    if (!any) row(key, d, { kind: 'record_unchecked', subject: d.ref.w, obs_index: d.ref.idx, source: 'human', human_decision: d.d, human_value: hv });
  }
  for (const [key, d] of decsOf('entry')) {
    if (!d.ref) continue; const m = d.m || {};
    for (const f of ['date', 'place', 'kind']) {
      let any = false;
      for (const c of ['g', 's']) { const fnd = m[c]; if (!fnd || fnd[f + '_ok'] !== false) continue; if (!(d[f] || d.hdr)) continue; any = true;
        row(key, d, { kind: 'entry_' + f, subject: f, source: SRC[c], machine_verdict: 'wrong', machine_proposal: fnd[f] || '', human_decision: d[f] ? 'set' : 'ok', human_value: d[f] ? d[f].v : '', agreed: d[f] ? (fnd[f] && cf(d[f].v) === cf(fnd[f]) ? 'yes' : 'partly') : 'no' }); }
      if (!any && d[f]) row(key, d, { kind: 'entry_' + f, subject: f, source: 'human', human_decision: 'set', human_value: d[f].v });
    }
    if (d.checked) for (const x of implOf(d)) {   // records without a decision count as confirmed right
      const base = { subject: x[1], obs_index: x[0], human_decision: 'implicit_ok', reviewed_by: d.checked.by || whoOf(d), reviewed_at: d.checked.t || '' }; let any = false;
      for (const [c, v] of [['g', x[2]], ['s', x[3]]]) if (v) { any = true; row(key, d, Object.assign({ kind: 'record_' + v, source: SRC[c], machine_verdict: v, agreed: agreeRec(v, 'ok') }, base)); }
      if (!any) row(key, d, Object.assign({ kind: 'record_unchecked', source: 'human' }, base));
    }
  }
  for (const [key, d] of decsOf('miss')) { if (!d.d || !d.ref) continue; const m = d.m || {}; const src = SRC[m.src];
    row(key, d, { kind: m.kind && m.kind !== 'observation' ? 'missing_other' : src ? 'missing_record' : 'missing_manual', subject: (d.rec && d.rec.species_de) || m.de || d.ref.text, source: src || 'human', machine_verdict: src ? 'missing' : '', machine_confidence: m.c == null ? '' : m.c,
      human_decision: d.d, human_value: J(d.rec), agreed: src && (!m.kind || m.kind === 'observation') ? (d.d === 'add' ? 'yes' : 'no') : '' }); }
  for (const [key, d] of decsOf('name')) { if (!d.d || !d.ref) continue; const r0 = (d.rows || []).find(r => r.auto) || (d.rows || [])[0] || {};
    row(key, d, { kind: 'name_' + (d.kind || ''), section: d.ref.section, subject: d.ref.form, source: 'machine_review', machine_verdict: r0.d || '', machine_proposal: JSON.stringify({ before: d.before, now: d.now, rows: d.rows }), machine_confidence: r0.c == null ? '' : r0.c,
      human_decision: d.d, agreed: d.d === 'confirm' || d.d === 'apply' ? 'yes' : 'no' }); }
  for (const [key, d] of decsOf('tc')) { if (!d.d || !d.ref) continue; const m = d.m || {}; const subj = d.ref.old + ' → ' + d.ref.new; const hvv = d.d === 'edit' ? d.final : '';
    row(key, d, { kind: 'reading_' + (m.rel ? 'relevant' : 'other'), subject: subj, source: 'reading', machine_verdict: m.applied ? 'applied' : 'not_applied', machine_fields: m.kind || '', human_decision: d.d, human_value: hvv, agreed: d.d === 'accept' ? 'yes' : d.d === 'edit' ? 'partly' : 'no' });
    for (const c of ['g', 's']) if (m[c] && agreeTc(m[c], d.d)) row(key, d, { kind: 'reading_verdict', subject: subj, source: SRC[c], machine_verdict: m[c], machine_proposal: m.better || '', human_decision: d.d, human_value: hvv, agreed: agreeTc(m[c], d.d) }); }
  for (const [key, d] of decsOf('qa')) { if (!d.d || !d.ref) continue; const m = d.m || {};
    row(key, d, { kind: m.action === 'excluded' ? 'qa_excluded' : 'qa_flagged', subject: d.ref.reason + ': ' + d.ref.value, source: 'qa', machine_verdict: m.action || '', human_decision: d.d, agreed: d.d === 'confirm' ? 'yes' : 'no' }); }
  for (const [key, d] of decsOf('txt')) if (d.ref) row(key, d, { kind: 'text', subject: d.ref.old, source: 'human', human_decision: 'text', human_value: d.new });
  return rows;
}
const exportAudit = () => toCSV(AU_HEAD, auditRows());
function progressJSON() { return JSON.stringify({ app: 'laubmann-graphpruefung', v: 1, export: (R.meta || {}).export || '', graph: G.meta.sourcePath || G.meta.source, built: G.meta.built, saved: nowIso(), state: { who: RV.who, dec: RV.dec, log: RV.log } }); }
function liesmich() {
  const p = progressStats(); const n = k => decsOf(k).length;
  return `Laubmann-KG · Graph-Prüfung — Export ${nowIso()}
Graph: ${G.meta.sourcePath || G.meta.source} (gebaut ${G.meta.built}) · Prüfschicht: ${(R.meta || {}).export || '?'} (${(R.meta || {}).built || '?'})
Prüfer/in: ${RV.who || '-'}

Stand: ${p.checked} Einträge als geprüft markiert · Datensätze: ${p.ok} bestätigt, ${p.corrected} korrigiert, ${p.dropped} gestrichen, ${p.added} ergänzt, ${p.unsure} unsicher
       ${n('name')} Namensentscheidungen · ${n('tc')} Lesekorrekturen · ${n('qa')} QA-Hinweise · ${n('txt')} eigene Textkorrekturen

Die Entscheidungen ändern den Graphen erst beim nächsten Pipeline-Lauf. Dazu die Dateien aus review/ nach
data/review/ legen (vorhandene Dateien gleichen Namens: Zeilen anhängen, nicht ersetzen) und die Pipeline laufen lassen.

review/observation_corrections.csv  -> src/laubmann_kg/normalization/observation_corrections.py
    je korrigiertem Feld eines Datensatzes eine Zeile (action=set: count, locality, date, observer, co_observers,
    record_type, sex, life_stage, breeding, status; "-" leert das Feld), ergänzte Datensätze (action=add) und
    Datum/Art des Eintrags (written leer, field=entry_date|entry_kind).
review/value_corrections.csv        -> src/laubmann_kg/normalization/corrections.py
    andere Art für EINEN Datensatz (kind=taxon, action=replace), gestrichene Datensätze (action=drop), Ort des
    Eintrags ersetzt (kind=place). Die Zeilen eines Eintrags stehen in der Reihenfolge, in der sie angewendet
    werden müssen (höchste occurrence zuerst) – bitte nicht umsortieren.
review/transcript_decisions.csv     -> src/laubmann_kg/extraction/reading.py (load_transcript_decisions)
    accept | reject | edit (+ final_text) je Lesekorrektur der Bildlesung; Schlüssel (entry_uid, old_text, new_text).
review/text_corrections.csv         -> src/laubmann_kg/review/readings.py
    eigene Korrektur einer Textstelle (old_text muss so in der Transkription stehen).
review/qa_decisions.csv             -> src/laubmann_kg/qa.py (load_qa_decisions)
    confirm | false_alarm je QA-Hinweis; Schlüssel (entry_uid, reason, value). Ein Fehlalarm holt nur bei
    non_bird, low_confidence_taxon und implausible_date den Ausschluss zurück.
review/identities.csv               -> src/laubmann_kg/review/identities.py
    Namensentscheidungen (gelten für den Namen in ALLEN Einträgen): bestätigte Maschinenzeilen (jetzt mit
    reviewed_by = Mensch) und zurückgenommene (früherer Link als same/link/nolink, sonst unsure = die
    Maschinenzeile gilt nicht mehr). Menschliche Zeilen gewinnen gegen identities_machine.csv.
entry_checks.csv    je als geprüft markiertem Eintrag: Warteschlange, Zahl der Datensätze, bestätigt (ausdrücklich
                    oder weil ohne Entscheidung), korrigiert, ergänzt, gestrichen.
graph_audit.csv     jede Entscheidung mit dem, was Prüfung/Maschine vorgeschlagen hatte, und agreed = yes | partly | no.
                    Daraus ergibt sich die Präzision je Prüfer und je Art automatischer Änderung.
graph_progress.json der ganze Stand; mit „Fortschritt laden“ wieder einlesbar (auch aus diesem ZIP).

Nicht über diese Dateien umsetzbar (stehen nur in graph_audit.csv):
- zurückgenommene automatische Wertkorrekturen (kind=auto_value, human_decision=revert): die Zeile muss aus
  data/review/machine/value_corrections_machine.csv entfernt werden.
- als falsch markierte, von der Maschine nur bestätigte (unveränderte) Verknüpfungen (kind=name_confirmed, agreed=no)
  und Georeferenz-Befunde: den Namen auf der Verknüpfungsseite für alle Einträge prüfen.
`;
}
function exportFiles() {
  return [['review/observation_corrections.csv', exportObs()], ['review/value_corrections.csv', exportValues()], ['review/transcript_decisions.csv', exportTranscript()], ['review/text_corrections.csv', exportText()],
    ['review/qa_decisions.csv', exportQA()], ['review/identities.csv', exportIdentities()], ['entry_checks.csv', exportChecks()], ['graph_audit.csv', exportAudit()], ['graph_progress.json', progressJSON()], ['LIESMICH.txt', liesmich()]];
}
// minimal ZIP (store only) — as in tools/validation_ui/pruefung/app_io.js
function crc32(buf) { let c, crc = 0xFFFFFFFF; for (let i = 0; i < buf.length; i++) { c = (crc ^ buf[i]) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; } return (crc ^ 0xFFFFFFFF) >>> 0; }
function makeZip(files) {
  const enc = new TextEncoder(); const parts = []; const central = []; let off = 0; const now = new Date(); const dt = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xFFFF; const dd = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xFFFF;
  const le = (n, b) => { const a = new Uint8Array(b); for (let i = 0; i < b; i++) a[i] = (n >>> (8 * i)) & 0xFF; return a; };
  for (const [name, text] of files) { const nm = enc.encode(name), data = enc.encode(text); const crc = crc32(data);
    const loc = [le(0x04034b50, 4), le(20, 2), le(0x0800, 2), le(0, 2), le(dt, 2), le(dd, 2), le(crc, 4), le(data.length, 4), le(data.length, 4), le(nm.length, 2), le(0, 2), nm, data];
    const cen = [le(0x02014b50, 4), le(20, 2), le(20, 2), le(0x0800, 2), le(0, 2), le(dt, 2), le(dd, 2), le(crc, 4), le(data.length, 4), le(data.length, 4), le(nm.length, 2), le(0, 2), le(0, 2), le(0, 2), le(0, 2), le(0, 4), le(off, 4), nm];
    parts.push(...loc); central.push(...cen); off += loc.reduce((a, x) => a + x.length, 0); }
  const cenLen = central.reduce((a, x) => a + x.length, 0);
  parts.push(...central, le(0x06054b50, 4), le(0, 2), le(0, 2), le(files.length, 2), le(files.length, 2), le(cenLen, 4), le(off, 4), le(0, 2));
  return new Blob(parts, { type: 'application/zip' });
}
function download(name, blob) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
const stampName = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1-$2');
const whoSlug = () => (RV.who || 'x').replace(/[^\p{L}\p{N}]+/gu, '_');
function closeModal() { $('#modalbg').hidden = true; $('#modal').innerHTML = ''; }
function showExport() {
  const files = exportFiles(); const nrows = txt => Math.max(0, txt.split('\n').length - 2); const p = progressStats();
  const consumer = { 'review/observation_corrections.csv': 'normalization/observation_corrections.py', 'review/value_corrections.csv': 'normalization/corrections.py', 'review/transcript_decisions.csv': 'extraction/reading.py',
    'review/text_corrections.csv': 'review/readings.py', 'review/qa_decisions.csv': 'qa.py', 'review/identities.csv': 'review/identities.py' };
  $('#modal').innerHTML = `<button class="btn mx" data-m="close">✕</button><h2>${t('ex_title')}</h2>
    <p>${esc(t('ex_state', fmt(p.checked), fmt(p.total)))} ${RV.who ? esc(t('ex_who', RV.who)) : `<b class="warnc">${t('ex_noname')}</b>`}</p>
    <h3>${t('ex_h_backup')}</h3><p class="muted">${t('ex_p_backup')}</p>
    <div class="btnrow">${'showSaveFilePicker' in window ? `<button class="abtn primary" data-m="bind">${t(fileHandle ? 'ex_bound' : 'ex_bind')}</button>` : ''}<button class="abtn" data-m="json">${t('ex_json')}</button><button class="abtn" data-m="load">${t('btn_load')}</button></div>
    <h3>${t('ex_h_zip')}</h3><p class="muted">${t('ex_p_zip')}</p>
    <div class="btnrow"><button class="abtn primary" data-m="zip">${t('ex_zip')}</button></div>
    <table class="t" style="margin-top:10px"><tr><th>${t('ex_file')}</th><th style="text-align:right">${t('ex_rows')}</th><th>${t('ex_consumer')}</th></tr>
    ${files.filter(f => f[0].endsWith('.csv')).map(f => `<tr><td class="mono">${esc(f[0])}</td><td class="num" style="text-align:right">${fmt(nrows(f[1]))}</td><td class="muted">${esc(consumer[f[0]] || t('ex_stats'))}</td></tr>`).join('')}</table>`;
  $('#modalbg').hidden = false;
}
async function modalClick(ev) {
  const b = ev.target.closest('[data-m]'); if (!b) { if (ev.target.id === 'modalbg') closeModal(); return; } const a = b.dataset.m;
  if (a === 'close') closeModal();
  else if (a === 'json') { download('laubmann_graphpruefung_' + whoSlug() + '_' + stampName() + '.json', new Blob([progressJSON()], { type: 'application/json' })); dirtyN = 0; }
  else if (a === 'zip') { download('laubmann_graphpruefung_export_' + whoSlug() + '_' + stampName() + '.zip', makeZip(exportFiles())); dirtyN = 0; }
  else if (a === 'load') $('#fileImport').click();
  else if (a === 'bind') {
    try { fileHandle = await window.showSaveFilePicker({ suggestedName: 'laubmann_graphpruefung_' + whoSlug() + '.json', types: [{ description: 'JSON', accept: { 'application/json': ['.json'] } }] });
      const w = await fileHandle.createWritable(); await w.write(progressJSON()); await w.close(); lastSaved = new Date(); dirtyN = 0; rvSavedLabel(); toast(t('ex_bound_toast'), 3000); showExport(); }
    catch (e) { /* picker cancelled */ }
  }
}
// ------------------------------------------------------------------ import of the page's own progress (JSON or ZIP)
function readZipProgress(buf) {
  const u = new Uint8Array(buf); const dv = new DataView(buf); const td = new TextDecoder();
  for (let i = 0; i + 30 < u.length;) { if (dv.getUint32(i, true) !== 0x04034b50) break; const size = dv.getUint32(i + 18, true), nl = dv.getUint16(i + 26, true), xl = dv.getUint16(i + 28, true);
    const name = td.decode(u.subarray(i + 30, i + 30 + nl)); const start = i + 30 + nl + xl; if (/(^|\/)graph_progress\.json$/.test(name)) return JSON.parse(td.decode(u.subarray(start, start + size))); i = start + size; }
  throw new Error(t('im_nozip'));
}
const stamp = d => (d ? [d.t || '', (d.checked || {}).t || ''].sort().pop() : '');
function importState(j) {   // merge: per key the newer decision wins
  const st = j && j.app === 'laubmann-graphpruefung' ? j.state : j && j.dec ? j : null; if (!st || !st.dec) throw new Error(t('im_unknown'));
  let n = 0; const hist = [];
  for (const k in st.dec) { const cur = RV.dec[k]; if (cur && stamp(cur) >= stamp(st.dec[k])) continue; hist.push([k, cur ? JSON.parse(JSON.stringify(cur)) : null]); RV.dec[k] = st.dec[k]; n++; }
  if (hist.length) HIST.push(hist);
  if (st.who && !RV.who) RV.who = st.who;
  const have = new Set(RV.log.map(l => l.k + '|' + l.t)); RV.log = RV.log.concat((st.log || []).filter(l => !have.has(l.k + '|' + l.t))).sort((a, b) => (b.t || '').localeCompare(a.t || '')).slice(0, 3000);
  saveSoon(); if (EM) EM.items = buildItems(EM); rvApplyStatic(); rvRefresh();
  return n;
}
async function importFile(f) {
  try { const j = /\.zip$/i.test(f.name) ? readZipProgress(await f.arrayBuffer()) : JSON.parse(await f.text()); const n = importState(j); toast(t('im_done', fmt(n)), 4000); closeModal(); }
  catch (e) { toast(t('im_fail', e.message), 6000); }
}
