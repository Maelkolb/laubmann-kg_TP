// ---------------------------------------------------------------- export (pipeline contracts)
const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const VC_HEAD = ['kind', 'entry_uid', 'entry_id', 'old_value', 'occurrence', 'action', 'new_value', 'scientific_name', 'gbif_key', 'is_bird', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
const TC_HEAD = ['entry_uid', 'entry_id', 'old_text', 'new_text', 'note', 'reviewed_by', 'reviewed_at'];
const TD_HEAD = ['entry_uid', 'entry_id', 'old_text', 'new_text', 'decision', 'final_text', 'note', 'reviewed_by', 'reviewed_at'];
const QD_HEAD = ['entry_uid', 'entry_id', 'reason', 'value', 'decision', 'note', 'reviewed_by', 'reviewed_at'];
const SECTION = { taxon: 'taxa', form: 'taxa', person: 'persons', place: 'places', habitat: 'habitats' };
const MNOTE = { a: 'machine verdict accepted', y: 'machine verdict accepted', r: 'machine verdict rejected', o: 'machine verdict replaced', k: 'machine verdict replaced' };
const isConf = it => it.q === 'sample' || it.q === 'rest';
function exportIdentities() {
  const rows = []; const seen = new Set(); const covered = { taxon: new Set(), person: new Set(), place: new Set(), habitat: new Set() };
  const LINKDEC = ['link', 'nolink'];
  const push = r => { const k = r.section + '|' + lc(r.name_form) + '|' + (LINKDEC.includes(r.decision) ? 'L' : 'F'); if (seen.has(k)) return; seen.add(k); rows.push(r); };
  const base = (it, d, name) => ({ section: SECTION[it.t], name_form: name, decision: '', target: '', authority: '', scientific_name: '', rank: '', lat: '', lon: '', uncertainty_m: '', eunis_match: '', reason: '', note: d.note || '', reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '' });
  for (const it of ITEMS) {
    if (!(it.t in SECTION)) continue;
    const tt = ttOf(it); const d = dec(it) || {};
    for (const fi of it.forms || []) covered[tt].add(nameKey(tt, fi));
    const ov = {}; for (const fi of it.forms || []) { const s = S.names[tt][nameKey(tt, fi)]; if (s) ov[fi] = s; }
    if (!d.d && !Object.keys(ov).length) continue;
    const fis = it.t === 'form' ? (it.forms || []) : (it.forms || []).filter(fi => !(it.moved || []).includes(fi));
    const ovNames = new Set(Object.keys(ov).map(fi => nameKey(tt, fi)));
    const has = d.d && d.d !== 'u';
    const machineNote = it.q === 'unchecked' || it.q === 'habitat' ? '' : ' · ' + (MNOTE[d.d] || '');
    let state = null, link = null, loc = null, eun = null;
    if (tt === 'taxon') {
      const curS = it.cur && it.cur.key ? { key: it.cur.key, sci: it.cur.sci, label: it.t === 'form' ? it.cur.label : it.label, rank: it.cur.rank } : null;
      if (d.d === 'a') state = it.k === 'none' || it.k === 'name-none' ? { none: true } : it.prop && it.prop.key ? { key: it.prop.key, sci: it.prop.sci, label: it.prop.de || it.prop.sci, rank: it.prop.rank } : curS;
      else if (d.d === 'r') state = isConf(it) ? { own: true } : curS || { unsure: true };
      else if (d.d === 'y' || !d.d) state = curS || (d.d ? { unsure: true } : null);
      else if (d.d === 'k') state = { none: true };
      else if (d.d === 'o') state = d.target && d.target.none ? { none: true } : d.target && d.target.own ? { own: true } : d.target ? { key: d.target.key, sci: d.target.sci, label: d.target.label, rank: d.target.rank } : null;
    } else if (tt === 'person') {
      const curL = it.cur.qid || it.cur.gnd ? { qid: it.cur.qid, gnd: it.cur.gnd } : { none: true };
      if (d.d === 'a') link = it.prop ? (it.prop.qid || it.prop.gnd ? { qid: it.prop.qid, gnd: it.prop.gnd } : { none: true }) : curL;
      else if (d.d === 'r') link = isConf(it) ? { none: true } : curL;
      else if (d.d === 'y' || !d.d) link = curL;
      else if (d.d === 'k') link = { none: true };
      else if (d.d === 'o') link = d.target ? (d.target.qid || d.target.gnd ? { qid: d.target.qid, gnd: d.target.gnd } : { none: true }) : null;
    } else if (tt === 'place') {
      const curL = it.cur.lat != null ? { lat: it.cur.lat, lon: it.cur.lon, unc: it.cur.unc, gn: it.cur.gn, qid: it.cur.qid } : { nolink: true };
      if (d.d === 'a') loc = it.k === 'not_a_place' ? { none: true } : it.prop && it.prop.lat != null ? { lat: it.prop.lat, lon: it.prop.lon, unc: it.unc || it.cur.unc || '', qid: it.prop.qid, osm: it.prop.osm } : curL;
      else if (d.d === 'r') loc = isConf(it) ? { nolink: true } : curL;
      else if (d.d === 'y' || !d.d) loc = curL;
      else if (d.d === 'k') loc = { none: true };
      else if (d.d === 'o') loc = d.target && d.target.nolink ? { nolink: true } : d.target && d.target.lat != null ? { lat: d.target.lat, lon: d.target.lon, unc: d.target.unc, qid: d.target.qid, osm: d.target.osm, gn: d.target.gn } : null;
    } else if (tt === 'habitat') {
      const curE = it.cur && it.cur.code ? { code: it.cur.code, match: it.cur.match || 'close' } : { nolink: true };
      if (d.d === 'a') eun = it.prop ? (it.prop.none ? { none: true } : { code: it.prop.code, match: it.prop.match || 'close' }) : curE;
      else if (d.d === 'r') eun = isConf(it) ? { nolink: true } : curE;
      else if (d.d === 'y' || !d.d) eun = curE;
      else if (d.d === 'o') eun = d.target && d.target.code ? { code: d.target.code, match: d.target.match || 'close' } : null;
      else if (d.d === 'k') eun = { nolink: true };
    }
    const taxonRow = (r, st) => { if (st.none) Object.assign(r, { decision: 'none', reason: 'not a bird / no taxon' }); else if (st.own) Object.assign(r, { decision: 'own', target: r.name_form, reason: 'species link rejected in review' }); else if (st.unsure) Object.assign(r, { decision: 'unsure', reason: 'machine proposal rejected, species open' }); else Object.assign(r, { decision: 'same', target: st.label || r.name_form, authority: st.key ? 'gbif:' + st.key : '', scientific_name: st.sci || '', rank: st.rank || '' }); return r; };
    const personRow = (r, lk) => Object.assign(r, lk.none ? { decision: 'nolink', target: it.label } : { decision: 'link', target: it.label, authority: [lk.qid ? 'wd:' + lk.qid : '', lk.gnd ? 'gnd:' + lk.gnd : ''].filter(Boolean).join(' ') });
    const placeRow = (r, lo) => { if (lo.none) Object.assign(r, { decision: 'none', reason: 'not a place name' }); else if (lo.nolink) Object.assign(r, { decision: 'nolink', target: it.label }); else Object.assign(r, { decision: 'link', target: it.label, authority: [lo.gn ? 'gn:' + lo.gn : '', lo.qid ? 'wd:' + lo.qid : '', lo.osm ? 'osm:' + lo.osm : ''].filter(Boolean).join(' '), lat: lo.lat, lon: lo.lon, uncertainty_m: lo.unc || '' }); return r; };
    const habRow = (r, e) => Object.assign(r, e.none ? { decision: 'none', reason: 'not a habitat' } : e.nolink ? { decision: 'nolink', target: it.label } : { decision: 'link', target: it.label, authority: 'eunis:' + e.code, eunis_match: e.match || 'close' });
    for (const [fi, sub] of Object.entries(ov)) {
      const f = FORMS[tt][fi]; if (!f) continue; const r = base(it, sub, f[0]); r.note = 'item decision for this name' + (sub.note ? ' · ' + sub.note : d.note ? ' · ' + d.note : '');
      if (tt === 'taxon') {
        if (sub.d === 'y') { if (state && !state.unsure) taxonRow(r, state); else if (it.cur && it.cur.key) taxonRow(r, { key: it.cur.key, sci: it.cur.sci, label: it.t === 'form' ? it.cur.label : it.label, rank: it.cur.rank }); else continue; }
        else if (sub.d === 'o') { if (!sub.target) continue; taxonRow(r, sub.target.none ? { none: true } : { key: sub.target.key, sci: sub.target.sci, label: sub.target.label, rank: sub.target.rank }); }
        else if (sub.d === 'k') taxonRow(r, { none: true });
        else if (sub.d === 'x') Object.assign(r, { decision: 'own', target: f[0], reason: sub.reason || 'separate' });
        else if (sub.d === 'u') r.decision = 'unsure';
      } else {
        if (sub.d === 'x') Object.assign(r, { decision: 'own', target: f[0], reason: sub.reason || 'separate' });
        else if (sub.d === 'o') Object.assign(r, sub.target && sub.target.label ? { decision: 'same', target: sub.target.label } : { decision: 'own', target: f[0], reason: 'separate' });
        else if (sub.d === 'k') Object.assign(r, { decision: 'none', reason: sub.reason || '' });
        else if (sub.d === 'y') { if (tt === 'person' && link) personRow(r, link); else if (tt === 'place' && loc) placeRow(r, loc); else if (tt === 'habitat' && eun) habRow(r, eun); else Object.assign(r, { decision: 'same', target: it.label }); }
        else if (sub.d === 'u') r.decision = 'unsure';
      }
      if (r.decision) push(r);
    }
    if (!has) continue;
    if (d.d === 'a' || (d.d === 'y' && isConf(it))) {
      const rs = (it.rows || []).map(ri => ROWS[ri]).filter(r => r && !ovNames.has(lc(r.name_form)));
      if (rs.length) { for (const r of rs) { const o = {}; for (const h of ID_HEAD) o[h] = r[h] || ''; push(Object.assign(o, { reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '', note: (r.note || '') + machineNote + (d.note ? ' · ' + d.note : '') })); } continue; }
    }
    const list = (it.k === 'name-unsure' ? (it.focus || []) : fis).filter(fi => !ov[fi]);
    if (tt === 'taxon') { if (!state) continue; for (const fi of list) { const f = FORMS.taxon[fi]; if (!f) continue; const r = taxonRow(base(it, d, f[0]), state); r.note += machineNote; push(r); } }
    else {
      const row = tt === 'person' ? (link && personRow) : tt === 'place' ? (loc && placeRow) : (eun && habRow); const val = tt === 'person' ? link : tt === 'place' ? loc : eun; if (!row) continue;
      const names = [it.label].concat(list.map(fi => (FORMS[tt][fi] || [''])[0]).filter(x => x && lc(x) !== lc(it.label)));
      for (const n of names) { const r = row(base(it, d, n), val); r.note += machineNote; push(r); }
    }
  }
  // name decisions without an item here (imported from an earlier export): only the context-free ones
  for (const tt of TYPES) for (const [key, sub] of Object.entries(S.names[tt])) {
    if (covered[tt].has(key)) continue;
    const r = base({ t: tt }, sub, sub.written || key); r.note = 'imported name decision' + (sub.note ? ' · ' + sub.note : '');
    if (sub.d === 'k') Object.assign(r, { decision: 'none', reason: sub.reason || '' });
    else if (sub.d === 'x') Object.assign(r, { decision: 'own', target: r.name_form, reason: sub.reason || 'separate' });
    else if (sub.d === 'u') r.decision = 'unsure';
    else if (sub.d === 'o' && sub.target) { if (tt === 'taxon' && sub.target.key) Object.assign(r, { decision: 'same', target: sub.target.label, authority: 'gbif:' + sub.target.key, scientific_name: sub.target.sci || '', rank: sub.target.rank || '' }); else if (sub.target.label) Object.assign(r, { decision: 'same', target: sub.target.label }); }
    if (r.decision) push(r);
  }
  return toCSV(ID_HEAD, rows);
}
function exportValues() {
  const rows = []; const seen = new Set();
  const push = r => { const k = r.kind + '|' + r.entry_uid + '|' + lc(r.old_value) + '|' + r.occurrence; if (seen.has(k)) return; seen.add(k); rows.push(r); };
  const cleanDe = v => (v || '').replace(/\s*\(.*?\)\s*/g, ' ').replace(/\?/g, '').trim();
  for (const it of ITEMS) {
    const d = dec(it); if (!d) continue;
    if (it.t === 'mention' && d.d && d.d !== 'u' && d.d !== 'r') {
      const r = {}; for (const h of VC_HEAD) r[h] = it.vrow[h] == null ? '' : it.vrow[h];
      Object.assign(r, { reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '', note: (it.vrow.note || '') + (d.note ? ' · ' + d.note : '') });
      if (d.d === 'o' && d.target) { if (d.target.drop) Object.assign(r, { action: 'drop', new_value: '', scientific_name: '', gbif_key: '' }); else Object.assign(r, { action: 'replace', new_value: d.target.label, scientific_name: d.target.sci || '', gbif_key: d.target.key || '', is_bird: 'y' }); }
      push(r);
    }
    if (it.t === 'entry') { const e = E[it.ei]; const eff = d.d === 'a' ? 'y' : d.d === 'r' ? 'n' : '';
      for (const o of it.obs) { const sub = (d.obs || {})[lc(o.written) + '|' + (o.occ || 0)]; const st = sub ? sub.d : eff; if (st !== 'y') continue;
        if (o.v === 'spurious') push({ kind: 'taxon', entry_uid: e[1], entry_id: e[0], old_value: o.written, occurrence: o.occ || 0, action: 'drop', new_value: '', scientific_name: '', gbif_key: '', is_bird: 'n', reason: o.reason, note: 'extraction check, confirmed by reviewer', reviewed_by: (sub || d).by || S.who || 'reviewer', reviewed_at: (sub || d).t || '' });
        else if (o.v === 'wrong' && o.fields.includes('species') && o.corr && cleanDe(o.corr.species_de)) push({ kind: 'taxon', entry_uid: e[1], entry_id: e[0], old_value: o.written, occurrence: o.occ || 0, action: 'replace', new_value: cleanDe(o.corr.species_de), scientific_name: o.corr.sci || '', gbif_key: '', is_bird: 'y', reason: o.reason, note: 'extraction check, confirmed by reviewer', reviewed_by: (sub || d).by || S.who || 'reviewer', reviewed_at: (sub || d).t || '' }); } }
  }
  // passage decisions (global store, keyed entry_uid|written|occurrence)
  for (const tt of TYPES) for (const [key, sub] of Object.entries(S.mens[tt])) {
    const parts = key.split('|'); const occ = parts.pop(); const uid = parts.shift(); const name = parts.join('|'); const ei = uid2e.get(uid);
    const written = sub.written || name; const eid = ei != null ? E[ei][0] : (sub.entry_id || '');
    const r = { kind: tt, entry_uid: uid, entry_id: eid, old_value: written, occurrence: occ || 0, action: 'replace', new_value: '', scientific_name: '', gbif_key: '', is_bird: '', reason: sub.reason || 'item decision on the passage', note: sub.note || '', reviewed_by: sub.by || S.who || 'reviewer', reviewed_at: sub.t || '' };
    if (sub.d === 'n') Object.assign(r, { action: 'drop', is_bird: tt === 'taxon' ? (sub.reason === 'misread' ? 'y' : 'n') : '' });
    else if (sub.d === 'x') Object.assign(r, { new_value: written + ' (unbestimmt)', is_bird: 'y', reason: 'not determinable' });
    else if (sub.d === 'w') Object.assign(r, { new_value: written + ' (' + eid + ')', reason: 'own entity' });
    else if (sub.d === 'o') { if (!sub.target) continue; if (sub.target.none || sub.target.drop) Object.assign(r, { action: 'drop', is_bird: tt === 'taxon' ? 'n' : '' }); else { Object.assign(r, { new_value: sub.target.label || sub.target.name || sub.target.qid || '', scientific_name: sub.target.sci || '', gbif_key: sub.target.key || '', is_bird: tt === 'taxon' ? 'y' : '' }); if (!r.new_value) continue; } }
    else continue;
    push(r);
  }
  return toCSV(VC_HEAD, rows);
}
function exportObs() {
  const head = ['entry_uid', 'entry_id', 'obs_index', 'occurrence', 'written', 'taxon', 'scientific_name', 'machine_verdict', 'fields', 'correction', 'human', 'action', 'round', 'note', 'reviewed_by', 'reviewed_at'];
  const rows = [];
  for (const it of ITEMS) { if (it.t !== 'entry') continue; const d = dec(it); if (!d) continue; const e = E[it.ei]; const eff = d.d === 'a' ? 'y' : d.d === 'r' ? 'n' : d.d === 'u' ? 'u' : '';
    for (const o of it.obs) { const sub = (d.obs || {})[lc(o.written) + '|' + (o.occ || 0)]; const st = sub ? sub.d : eff; if (!st || (o.v === 'ok' && !sub)) continue;
      rows.push({ entry_uid: e[1], entry_id: e[0], obs_index: o.i, occurrence: o.occ || 0, written: o.written, taxon: o.taxon, scientific_name: o.sci, machine_verdict: o.v, fields: o.fields.join(';'), correction: o.corr ? JSON.stringify(o.corr) : '', human: { y: 'agree', n: 'disagree', u: 'unsure' }[st], action: st === 'y' ? (o.v === 'spurious' ? 'drop' : o.v === 'wrong' ? 'fix' : 'none') : 'keep', round: it.rnd, note: d.note || '', reviewed_by: (sub || d).by || S.who || 'reviewer', reviewed_at: (sub || d).t || '' }); }
    it.miss.forEach(m => { const sub = (d.miss || {})[lc(m.text).trim()]; const st = sub ? sub.d : eff; if (!st) return;
      rows.push({ entry_uid: e[1], entry_id: e[0], obs_index: '', occurrence: '', written: m.text, taxon: m.de || '', scientific_name: m.sci || '', machine_verdict: 'missing:' + m.kind, fields: '', correction: JSON.stringify({ count: m.count || null, note: m.note || null }), human: { y: 'agree', n: 'disagree', u: 'unsure' }[st], action: st === 'y' ? 'add' : 'keep', round: it.rnd, note: d.note || '', reviewed_by: (sub || d).by || S.who || 'reviewer', reviewed_at: (sub || d).t || '' }); }); }
  return toCSV(head, rows);
}
function exportText() {
  const rows = []; const seen = new Set();
  for (const it of ITEMS) { if (it.t !== 'text') continue; const d = dec(it); if (!d || !d.d || d.d === 'u' || d.d === 'r') continue; const e = E[it.ei]; seen.add(e[1] + '|' + it.label); rows.push({ entry_uid: e[1], entry_id: e[0], old_text: it.label, new_text: d.d === 'o' && d.target ? d.target.value : it.prop.value, note: (it.reason || '') + (d.note ? ' · ' + d.note : ''), reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '' }); }
  for (const c of S.text) { if (seen.has(c.entry_uid + '|' + c.old)) continue; seen.add(c.entry_uid + '|' + c.old); rows.push({ entry_uid: c.entry_uid, entry_id: c.entry_id, old_text: c.old, new_text: c.new, note: c.note || 'Laubmann-Abgleich', reviewed_by: c.by || S.who || 'reviewer', reviewed_at: c.t || '' }); }
  return toCSV(TC_HEAD, rows);
}
const TD_DEC = { a: 'accept', r: 'reject', e: 'edit', u: 'unsure' };
function exportTranscript() {
  const rows = [];
  for (const [key, d] of Object.entries(S.dec)) {
    if (!key.startsWith('tc:') || !d || !TD_DEC[d.d]) continue;
    const it = KEY2I.has(key) ? ITEMS[KEY2I.get(key)] : null; const ref = d.ref || (it ? { uid: E[it.ei][1], id: E[it.ei][0], old: it.label, new: it.new } : null); if (!ref) continue;
    const fin = d.d === 'a' ? ref.new : d.d === 'r' ? ref.old : d.d === 'e' ? (d.target ? d.target.value : '') : '';
    rows.push({ entry_uid: ref.uid, entry_id: ref.id, old_text: ref.old, new_text: ref.new, decision: TD_DEC[d.d], final_text: fin, note: d.note || '', reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '' });
  }
  return toCSV(TD_HEAD, rows);
}
const QD_DEC = { a: 'confirm', r: 'false_alarm', o: 'fix' };
function exportQA() {
  const rows = [];
  for (const [key, d] of Object.entries(S.dec)) {
    if (!key.startsWith('qa:') || !d || !QD_DEC[d.d]) continue;
    const it = KEY2I.has(key) ? ITEMS[KEY2I.get(key)] : null; const ref = d.ref || (it ? { uid: it.uid, id: it.id, reason: it.k, value: it.label } : null); if (!ref || !ref.uid) continue;
    rows.push({ entry_uid: ref.uid, entry_id: ref.id, reason: ref.reason, value: ref.value, decision: QD_DEC[d.d], note: [d.target && d.target.fix, d.note].filter(Boolean).join(' · '), reviewed_by: d.by || S.who || 'reviewer', reviewed_at: d.t || '' });
  }
  return toCSV(QD_HEAD, rows);
}
function exportAudit() {
  const head = ['key', 'type', 'queue', 'category', 'stratum', 'round', 'label', 'entry_id', 'mentions', 'machine_confidence', 'machine_agreement', 'machine_sources', 'pipeline_auto', 'machine_proposal', 'human_decision', 'human_target', 'agrees_with_machine', 'sub_decisions', 'note', 'reviewed_by', 'reviewed_at'];
  const DN = { a: 'accept', r: 'reject', o: 'other', u: 'unsure', y: 'confirm', k: 'none', e: 'edit' };
  const rows = ITEMS.filter(it => dec(it) && (dec(it).d || subCount(it))).map(it => { const d = dec(it); const agree = d.d === 'a' || d.d === 'y' ? 'yes' : d.d === 'r' || d.d === 'o' || d.d === 'k' || d.d === 'e' ? 'no' : '';
    return { key: it.key, type: it.t, queue: it.q, category: it.k, stratum: it.stratum || '', round: it.rnd || '', label: it.label || it.id, entry_id: it.ei != null ? E[it.ei][0] : (it.id || ''), mentions: it.n || '', machine_confidence: it.conf ?? '', machine_agreement: it.agree ?? '', machine_sources: (it.src || []).join('+'), pipeline_auto: it.auto ? 'y' : 'n', machine_proposal: it.prop ? JSON.stringify(it.prop) : it.m ? JSON.stringify(it.m) : '', human_decision: d.d ? (DN[d.d] || d.d) : 'partial', human_target: d.target ? JSON.stringify(d.target) : '', agrees_with_machine: it.q === 'open' || it.q === 'unchecked' || it.q === 'habitat' || it.q === 'qa' || !d.d ? '' : agree, sub_decisions: subCount(it), note: d.note || '', reviewed_by: d.by || '', reviewed_at: d.t || '' }; });
  return toCSV(head, rows);
}
function exportLog() { return toCSV(['time', 'reviewer', 'key', 'type', 'label', 'decision'], S.log.map(l => { const it = KEY2I.has(l.k) ? ITEMS[KEY2I.get(l.k)] : null; return { time: l.t, reviewer: l.by, key: l.k, type: it ? it.t : '', label: it ? it.label || it.id : '', decision: l.lab }; })); }
function exportEval() {
  const rows = Object.entries(S.ev).map(([k, d]) => { const [uid, name, occ] = k.split('|'); return { entry_uid: uid, name_form: name, occurrence: occ, judgement: { y: 'correct', n: 'wrong', u: 'unclear' }[d.d] || '', correct_taxon: d.target ? d.target.label || '' : '', correct_scientific_name: d.target ? d.target.sci || '' : '', note: d.note || '', reviewed_by: d.by || '', reviewed_at: d.t || '' }; });
  return toCSV(['entry_uid', 'name_form', 'occurrence', 'judgement', 'correct_taxon', 'correct_scientific_name', 'note', 'reviewed_by', 'reviewed_at'], rows);
}
function progressJSON() { const st = { who: S.who, dec: S.dec, names: S.names, mens: S.mens, text: S.text, ev: S.ev, log: S.log }; return JSON.stringify({ app: 'laubmann-validierung', v: 2, export: D.export, built: D.built, saved: new Date().toISOString(), state: st }, null, 0); }
function statusLine() {
  const q = ['change', 'sample', 'open', 'tc', 'extract', 'text', 'unchecked', 'habitat', 'qa']; return q.map(x => t('log.' + x) + ' ' + progress(QUEUES[x] || []).done + '/' + (QUEUES[x] || []).length).join(' · ');
}
function README() {
  if (LANG === 'en') return 'Laubmann validation — export ' + new Date().toISOString() + '\nGraph ' + D.export + ' · machine rounds ' + (D.rounds || []).map(r => 'R' + r.n + ' ' + r.model + ' ' + (r.built || '').slice(0, 10)).join(', ') + '\nReviewer: ' + (S.who || '-') + '\n\nStatus: ' + statusLine() + '\n\nFiles (review/* go to data/review/):\n- review/identities.csv: contract of data/review/identities.csv (taxa, persons, places, habitats with eunis:). Accepted machine rows carry reviewed_by = reviewer; rejected proposals write the earlier state. Human rows always win over identities_machine.csv.\n- review/value_corrections.csv: passage corrections (contract data/review/value_corrections.csv).\n- review/text_corrections.csv: accepted reading corrections of the extraction check (and imported ones).\n- review/transcript_decisions.csv: decisions on the transcript corrections of the visual reading (accept|reject|edit|unsure, final_text).\n- review/qa_decisions.csv: decisions on the QA flags (confirm|false_alarm|fix).\n- observation_corrections.csv: confirmed extraction findings per observation (no pipeline consumer yet).\n- machine_audit.csv: every decision with the machine verdict, round, confidence, sources.\n- evaluation_imported.csv: evaluation-sample judgements imported from Laubmann_Abgleich.html (if any).\n- validation_log.csv, validation_progress.json (re-importable).\n';
  return 'Laubmann-Validierung — Export ' + new Date().toISOString() + '\nGraph ' + D.export + ' · Maschinenrunden ' + (D.rounds || []).map(r => 'R' + r.n + ' ' + r.model + ' ' + (r.built || '').slice(0, 10)).join(', ') + '\nPrüfer: ' + (S.who || '-') + '\n\nStand: ' + statusLine() + '\n\nDateien (review/* nach data/review/):\n- review/identities.csv: Vertrag von data/review/identities.csv (Arten, Personen, Orte, Lebensräume mit eunis:). Übernommene Maschinen-Zeilen tragen reviewed_by = Prüfer; abgelehnte Vorschläge schreiben den früheren Zustand. Menschliche Zeilen gewinnen gegen identities_machine.csv.\n- review/value_corrections.csv: Beleg-Korrekturen (Vertrag data/review/value_corrections.csv).\n- review/text_corrections.csv: übernommene Lesekorrekturen der Extraktionsprüfung (und importierte).\n- review/transcript_decisions.csv: Entscheidungen zu den Transkriptionskorrekturen der Bildlesung (accept|reject|edit|unsure, final_text).\n- review/qa_decisions.csv: Entscheidungen zu den QA-Hinweisen (confirm|false_alarm|fix).\n- observation_corrections.csv: bestätigte Befunde je Beobachtung (noch ohne Pipeline-Verbraucher).\n- machine_audit.csv: jede Entscheidung mit Maschinenurteil, Runde, Konfidenz, Quellen.\n- evaluation_imported.csv: Stichproben-Urteile aus Laubmann_Abgleich.html (falls importiert).\n- validation_log.csv, validation_progress.json (wieder einlesbar).\n';
}
function exportFiles() {
  const f = [['review/identities.csv', exportIdentities()], ['review/value_corrections.csv', exportValues()], ['review/text_corrections.csv', exportText()], ['review/transcript_decisions.csv', exportTranscript()], ['review/qa_decisions.csv', exportQA()],
    ['observation_corrections.csv', exportObs()], ['machine_audit.csv', exportAudit()], ['validation_log.csv', exportLog()], ['validation_progress.json', progressJSON()], ['LIESMICH.txt', README()]];
  if (Object.keys(S.ev).length) f.splice(6, 0, ['evaluation_imported.csv', exportEval()]);
  return f;
}
// minimal ZIP (store only)
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
const whoSlug = () => (S.who || 'x').replace(/[^\p{L}\p{N}]+/gu, '_');
function showExport() {
  const p = progress(ITEMS.filter(it => it.q !== 'rest'));
  $('#modal').innerHTML = '<button class="nbtn x">' + t('close') + '</button><h2>' + t('ex.title') + '</h2><p>' + t('ex.n', fmt(p.done), '<b>' + esc(S.who || '–') + '</b>') + '</p>'
    + '<h3>' + t('ex.h1') + '</h3><p>' + t('ex.p1') + '</p><div class="row">' + ('showSaveFilePicker' in window ? '<button class="nbtn primary" id="exBind">' + t('ex.bind') + '</button>' : '') + '<button class="nbtn" id="exJson">' + t('ex.json') + '</button><button class="nbtn" id="exImport">' + t('ex.import') + '</button></div>'
    + '<h3>' + t('ex.h2') + '</h3><p>' + t('ex.p2') + '</p><div class="row"><button class="nbtn primary" id="exZip">' + t('ex.zip') + '</button></div>'
    + '<h3>' + t('ex.preview') + '</h3><pre class="mono" style="max-height:220px;overflow:auto;background:var(--panel2);padding:8px;border-radius:6px">' + esc(exportIdentities().split('\n').slice(0, 25).join('\n')) + '</pre>';
  $('#ovModal').classList.add('show');
  if ($('#exBind')) $('#exBind').onclick = async () => { try { fileHandle = await window.showSaveFilePicker({ suggestedName: 'laubmann_validierung_' + whoSlug() + '.json', types: [{ description: 'JSON', accept: { 'application/json': ['.json'] } }] }); const w = await fileHandle.createWritable(); await w.write(progressJSON()); await w.close(); lastFile = new Date(); dirty = 0; savedLabel(); toast(t('ex.bound')); } catch (e) { } };
  $('#exJson').onclick = () => { download('laubmann_validierung_' + whoSlug() + '_' + stampName() + '.json', new Blob([progressJSON()], { type: 'application/json' })); dirty = 0; savedLabel(); };
  $('#exImport').onclick = () => $('#fileImport').click();
  $('#exZip').onclick = () => { download('laubmann_validierung_export_' + whoSlug() + '_' + stampName() + '.zip', makeZip(exportFiles())); dirty = 0; savedLabel(); };
}

// ---------------------------------------------------------------- import: this page, Laubmann_Pruefung.html (2026-09-30), Laubmann_Abgleich.html (v2–v4)
async function readZipJSON(buf) {
  const u = new Uint8Array(buf); const dv = new DataView(buf); const td = new TextDecoder();
  for (let i = 0; i + 30 < u.length;) { if (dv.getUint32(i, true) !== 0x04034b50) break; const size = dv.getUint32(i + 18, true), nl = dv.getUint16(i + 26, true), xl = dv.getUint16(i + 28, true);
    const name = td.decode(u.subarray(i + 30, i + 30 + nl)); const start = i + 30 + nl + xl; if (/(^|\/)validation_progress\.json$/.test(name)) return JSON.parse(td.decode(u.subarray(start, start + size))); i = start + size; }
  throw new Error(t('im.noZip'));
}
const newer = (a, b) => !a || (b.t || '') > (a.t || '');
function mergeInto(dst, key, val) { if (!val || !newer(dst[key], val)) return 0; dst[key] = val; return 1; }
function mergeOwn(st) {
  let n = 0;
  for (const [k, d] of Object.entries(st.dec || {})) n += mergeInto(S.dec, k, d);
  for (const t0 of TYPES) { for (const [k, d] of Object.entries((st.names || {})[t0] || {})) n += mergeInto(S.names[t0], k, d); for (const [k, d] of Object.entries((st.mens || {})[t0] || {})) n += mergeInto(S.mens[t0], k, d); }
  for (const c of st.text || []) if (!S.text.some(x => x.entry_uid === c.entry_uid && x.old === c.old)) { S.text.push(c); n++; }
  for (const [k, d] of Object.entries(st.ev || {})) n += mergeInto(S.ev, k, d);
  const have = new Set(S.log.map(l => l.k + '|' + l.t)); S.log = S.log.concat((st.log || []).filter(l => !have.has(l.k + '|' + l.t))).sort((a, b) => (b.t || '').localeCompare(a.t || '')).slice(0, 5000);
  return n;
}
const typeOfKey = k => { const p = k.split(':')[0]; return p === 'form' || p === 'men' ? 'taxon' : p; };
function importPruefung(st) {
  const L = D.LEGACY; if (!L) throw new Error(t('im.noLegacy'));
  let n = 0, lost = 0;
  for (const [oi, d] of Object.entries(st.dec || {})) {
    const key = L.keys[+oi]; if (!key) { lost++; continue; }
    const tt = typeOfKey(key);
    if (d.d) { const o = { d: d.d, note: d.note || '', by: d.by, t: d.t }; if (d.target) o.target = d.target; const prev = S.dec[key]; if (newer(prev, o)) { S.dec[key] = Object.assign(o, prev && prev.obs ? { obs: prev.obs } : {}, prev && prev.miss ? { miss: prev.miss } : {}); n++; } }
    for (const [fi, sub] of Object.entries(d.names || {})) { const nm = ((L.forms || {})[tt] || {})[fi]; if (nm) n += mergeInto(S.names[tt], nm, sub); else lost++; }
    for (const [mi, sub] of Object.entries(d.mens || {})) { const mk = ((L.mens || {})[tt] || {})[mi]; if (mk) n += mergeInto(S.mens[tt], mk, Object.assign({}, sub, sub.d === 'n' || sub.d === 'o' ? { written: sub.written || mk.split('|')[1] } : {})); else lost++; }
    for (const kind of ['obs', 'miss']) for (const [k, sub] of Object.entries(d[kind] || {})) {
      const nk = kind === 'obs' ? ((L.obs || {})[oi] || {})[k] : ((L.miss || {})[oi] || [])[+k]; if (!nk) { lost++; continue; }
      const dd = S.dec[key] || (S.dec[key] = { d: '', note: d.note || '', by: d.by, t: d.t }); dd[kind] = dd[kind] || {}; n += mergeInto(dd[kind], nk, sub);
    }
  }
  const have = new Set(S.log.map(l => l.k + '|' + l.t));
  for (const l of st.log || []) { const k = L.keys[l.i]; if (k && !have.has(k + '|' + l.t)) S.log.push({ k, d: l.d, t: l.t, by: l.by, lab: l.lab }); }
  S.log.sort((a, b) => (b.t || '').localeCompare(a.t || '')); S.log = S.log.slice(0, 5000);
  if (st.who && !S.who) S.who = st.who;
  return [n, lost];
}
function sameAsProp(it, x) {
  if (!it.prop || !x) return false;
  if (it.t === 'taxon' || it.t === 'form') return !!x.key && String(x.key) === String(it.prop.key);
  if (it.t === 'person') return !!x.qid && x.qid === it.prop.qid;
  if (it.t === 'place') return x.lat != null && it.prop.lat != null && Math.abs(x.lat - it.prop.lat) < 0.01 && Math.abs(x.lon - it.prop.lon) < 0.015;
  return false;
}
function convAbgleichEnt(t0, d, it) {
  const base = { note: [d.note, 'Laubmann-Abgleich'].filter(Boolean).join(' · '), by: d.by, t: d.t };
  let o = null;
  if (d.d === 'u') o = { d: 'u' };
  else if (d.d === 'n') o = t0 === 'taxon' ? { d: 'o', target: { own: true } } : t0 === 'place' ? { d: 'o', target: { nolink: true } } : { d: 'k' };
  else if (d.d === 'r' && d.target) o = { d: 'o', target: t0 === 'habitat' ? { code: d.target.code, label: (EUNIS.get(d.target.code) || [])[1] || d.target.label || '', match: d.target.match || 'close' } : Object.assign({}, d.target) };
  else if (d.d === 'y') {
    if (t0 === 'person' && (d.qid || d.gnd) && (!it || (d.qid || '') !== (it.cur.qid || '') || (d.gnd && d.gnd !== it.cur.gnd))) o = { d: 'o', target: { qid: d.qid || '', gnd: d.gnd || '', label: d.wd_label || d.gnd_label || d.qid || d.gnd } };
    else if (t0 === 'place' && d.fix && d.fix.lat) o = { d: 'o', target: { lat: +d.fix.lat, lon: +d.fix.lon, name: d.fix.geonames_name || (it ? it.label : ''), qid: d.fix.qid || '', osm: d.fix.osm || '', gn: d.fix.geonames_id || '', unc: +d.fix.uncertainty_m || 1000 } };
    else o = { d: 'y' };
  }
  if (!o) return null;
  if (it && it.q === 'change') { if (o.d === 'y') o.d = 'r'; else if (o.d === 'o' && sameAsProp(it, o.target)) { o.d = 'a'; delete o.target; } }
  else if (it && isConf(it)) { if (o.d === 'y') o.d = 'a'; }
  return Object.assign(o, base);
}
function importAbgleich(j) {
  if ((j.version || 2) < 2 && !j.id) throw new Error(t('im.v1'));
  let n = 0, lost = 0; const find = (t0, label) => { const i = KEY2I.get(t0 + ':' + lc(label)); return i != null ? ITEMS[i] : null; };
  for (const t0 of TYPES) {
    for (const [label, d] of Object.entries((j.ent || {})[t0] || {})) { if (!d || !d.d) continue; const it = find(t0, label); const o = convAbgleichEnt(t0, d, it); if (!o) continue; if (!it) lost++; n += mergeInto(S.dec, it ? it.key : t0 + ':' + lc(label), o); }
    for (const [key, d] of Object.entries((j.id || {})[t0] || {})) { if (!d || !d.d) continue;
      const o = { y: { d: 'y' }, r: d.target ? { d: 'o', target: Object.assign({}, d.target) } : null, x: { d: 'x', reason: 'rejected' }, o: { d: 'x', reason: 'separate' }, n: { d: 'k', reason: d.reason || '' }, u: { d: 'u' } }[d.d];
      if (o) n += mergeInto(S.names[t0], key, Object.assign(o, { note: d.note || '', by: d.by, t: d.t, written: d.written || '' })); }
    for (const [key, d] of Object.entries((j.men || {})[t0] || {})) { if (!d || !d.d) continue;
      const o = { r: d.target ? { d: 'o', target: Object.assign({}, d.target) } : null, n: { d: 'n', reason: d.reason || '' }, x: { d: 'x' }, o: { d: 'w' } }[d.d];
      if (o) n += mergeInto(S.mens[t0], key, Object.assign(o, { note: d.note || '', by: d.by, t: d.t, written: d.written || key.split('|')[1] })); }
    for (const [label, d] of Object.entries((j.grp || {})[t0] || {})) { if (!d || d.d !== 'y') continue; const it = find(t0, label); if (!it) { lost++; continue; }
      for (const fi of it.forms || []) { const k = nameKey(t0, fi); if (!S.names[t0][k]) { S.names[t0][k] = { d: 'y', note: 'Namensgruppe bestätigt (Laubmann-Abgleich)', by: d.by, t: d.t }; n++; } } }
  }
  for (const c of j.text || []) if (c.entry_uid && !S.text.some(x => x.entry_uid === c.entry_uid && x.old === c.old)) { S.text.push(c); n++; }
  const qaIdx = new Map(QUEUES.qa.map(it => [it.id + '|' + it.k + '|' + it.label, it]));
  for (const [k, d] of Object.entries(j.qa || {})) { if (!d || !d.d) continue; const it = qaIdx.get(k); const o = { d: { y: 'a', n: 'r', u: 'u' }[d.d] || 'u', note: [d.note, 'Laubmann-Abgleich'].filter(Boolean).join(' · '), by: d.by, t: d.t };
    if (it) { o.ref = { uid: it.uid, id: it.id, reason: it.k, value: it.label }; n += mergeInto(S.dec, it.key, o); } else { const [id, reason, value] = k.split('|'); o.ref = { uid: '', id, reason, value }; n += mergeInto(S.dec, 'qa:' + k, o); lost++; } }
  for (const [k, d] of Object.entries(j.ev || {})) n += mergeInto(S.ev, k, d);
  if (j.who && !S.who) S.who = j.who;
  return [n, lost];
}
function importAny(j) {
  const HISTL = ['import', snapshot(), cur.i, cur.tab];
  let n = 0, lost = 0;
  if (j.app === 'laubmann-validierung') n = mergeOwn(j.state || j);
  else if (j.app === 'laubmann-pruefung') [n, lost] = importPruefung(j.state || j);
  else if (j.app === 'histornigraph-validation' || j.id || j.ent) [n, lost] = importAbgleich(j);
  else if (j.dec && j.names) n = mergeOwn(j);
  else if (j.dec && Object.keys(j.dec).some(k => !/^\d+$/.test(k))) throw new Error(t('im.v1'));
  else if (j.dec) [n, lost] = importPruefung(j);
  else throw new Error(t('im.unknown'));
  HIST.push(HISTL); normalizeState(); save(); refresh();
  return [n, lost];
}
$('#fileImport').addEventListener('change', async ev => {
  const f = ev.target.files[0]; if (!f) return; ev.target.value = '';
  try { const j = /\.zip$/i.test(f.name) ? await readZipJSON(await f.arrayBuffer()) : JSON.parse(await f.text());
    const [n, lost] = importAny(j); toast(t('im.done', n) + (lost ? ' · ' + t('im.lost', lost) : ''), 4000); $('#ovModal').classList.remove('show'); }
  catch (e) { toast(t('im.fail', e.message), 5000); }
});
function importFromBrowser(kind) {
  try { const j = JSON.parse(localStorage.getItem(LS_OLD[kind]) || 'null'); if (!j) return;
    const [n, lost] = kind === 'pruefung' ? (() => { const HISTL = ['import', snapshot(), cur.i, cur.tab]; const r = importPruefung(j); HIST.push(HISTL); return r; })() : (() => { const HISTL = ['import', snapshot(), cur.i, cur.tab]; const r = importAbgleich(j); HIST.push(HISTL); return r; })();
    S.ui.imported = Object.assign(S.ui.imported || {}, { [kind]: new Date().toISOString() }); normalizeState(); save(); refresh(); toast(t('im.done', n) + (lost ? ' · ' + t('im.lost', lost) : ''), 4000); }
  catch (e) { toast(t('im.fail', e.message), 5000); }
}
// ---------------------------------------------------------------- help, search
function showHelp() {
  $('#modal').innerHTML = '<button class="nbtn x">' + t('close') + '</button><h2>' + t('help.title') + '</h2><p>' + t('help.p1') + '</p>'
    + '<h3>' + t('help.h.src') + '</h3><p>' + t('help.src', sourceChips(['text']), sourceChips(['scan']), sourceChips(['nominatim']), '<span class="bd auto">' + t('chip.auto') + '</span>', num(D.thresholds.conf), D.thresholds.agree) + '</p>'
    + '<h3>' + t('help.h.tabs') + '</h3><ul>' + t('help.tabs') + '</ul>'
    + '<h3>' + t('help.h.rules') + '</h3><ul>' + t('help.rules') + '</ul>'
    + '<h3>' + t('help.h.keys') + '</h3><p>' + t('help.keys') + '</p>';
  $('#ovModal').classList.add('show');
}
function showSearch() {
  $('#modal').innerHTML = '<button class="nbtn x">' + t('close') + '</button><h2>' + t('gs.title') + '</h2><div class="gsearch"><input type="text" id="gs" placeholder="' + esc(t('gs.ph')) + '"></div><div class="res" id="gres" style="max-height:60vh"></div>';
  $('#ovModal').classList.add('show'); const inp = $('#gs'); inp.focus();
  inp.oninput = () => { const q = fold(inp.value.trim()); if (q.length < 2) { $('#gres').innerHTML = ''; return; } const hits = []; for (const it of ITEMS) { if (fold(searchText(it)).includes(q)) { hits.push(it); if (hits.length >= 80) break; } }
    $('#gres').innerHTML = hits.map(it => '<div class="r" data-goto="' + it.i + '"><b>' + esc(short(it.label || it.id, 90)) + '</b><small>' + esc(TYPE(it.t)) + ' · ' + esc(t('gs.q.' + it.q)) + ' · ' + esc(it.q === 'unchecked' ? t('cat.u.' + it.k) : it.t === 'qa' ? qaLabel(it.k) : it.t === 'tc' ? t('tck.' + it.k) : CAT(it.k)) + (isDone(it) ? ' · ' + esc(decLabel(it, dec(it))) : '') + '</small></div>').join('') || '<div class="r muted">' + t('gs.none') + '</div>'; };
  $('#gres').onclick = ev => { const r = ev.target.closest('[data-goto]'); if (!r) return; $('#ovModal').classList.remove('show'); goto(+r.dataset.goto); };
}
// ---------------------------------------------------------------- start
window.addEventListener('beforeunload', () => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { } });
try { const th = localStorage.getItem(LS + '-theme'); if (th) document.documentElement.dataset.theme = th; } catch (e) { }
document.documentElement.lang = LANG;
D = await loadData();
E = D.E; PG = D.PG; DRIVE = D.DRIVE; MEN = D.MEN; FORMS = D.FORMS; SUG = D.SUG; ROWS = D.ROWS; ITEMS = D.items; STATS = D.stats; TAXA = D.TAXA || [];
EUNIS = new Map((D.EUNIS || []).map(e => [e[0], e]));
for (const k in E) { uid2e.set(E[k][1], +k); id2e.set(E[k][0], +k); }
for (const it of ITEMS) KEY2I.set(it.key, it.i);
try { const raw = localStorage.getItem(LS); if (raw) S = Object.assign(S, JSON.parse(raw)); } catch (e) { }
normalizeState();
buildQueues();
$('#exportname').textContent = D.export;
$('#loading').remove();
savedLabel();
cur.tab = S.ui.tab && TAB[S.ui.tab] ? S.ui.tab : 'home';
openTab(cur.tab);
if (!S.who) toast(t('toast.name'), 3000);
window.__lp = { get S() { return S; }, D, ITEMS, QUEUES, KEY2I, exportFiles, dec, filtered, openTab, goto, setLang, importAny, importFromBrowser, get LANG() { return LANG; } };
