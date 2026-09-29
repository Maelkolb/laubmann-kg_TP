// Laubmann-Abgleich v4 — part 5: global search, log, export, backup file, import, help, start.
function openSearch() {
  $('#modal').innerHTML = '<div class="gsearch"><button class="lbtn x" data-close>✕</button><h2>Alles durchsuchen</h2><input id="gq" placeholder="Art, Person, Ort, Lebensraum oder geschriebener Name …" autocomplete="off"><div class="res" id="gres" style="max-height:60vh"></div></div>';
  $('#ovModal').classList.add('show'); const inp = $('#gq'); inp.focus(); let hi = 0, rows = [];
  const run = () => { const f = fold(inp.value.trim()); rows = []; if (f.length < 2) { $('#gres').innerHTML = ''; return; }
    for (const t of TYPES) for (const e of X[t].ents) { if (!e.names.length) continue; const hay = [e.label, t === 'taxon' ? e.e[1] : '', ...e.names.map(x => x.name)]; const i = hay.findIndex(h => fold(h).includes(f)); if (i < 0) continue;
      const lab = fold(e.label); const words = lab.split(/[^a-z0-9]+/);
      rows.push({ t, e, score: lab === f ? 0 : words.includes(f) ? 1 : lab.startsWith(f) || words.some(w => w.startsWith(f)) ? 2 : 3, via: i > 1 ? hay[i] : '' }); }
    rows.sort((a, b) => a.score - b.score || b.e.n - a.e.n); rows = rows.slice(0, 40); hi = 0;
    $('#gres').innerHTML = rows.length ? rows.map((r, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '"><span class="bd plain">' + esc(TT[r.t].tab) + '</span> <b>' + esc(r.e.label) + '</b>' + (r.t === 'taxon' && r.e.e[1] ? ' <i>' + esc(r.e.e[1]) + '</i>' : '') + (r.via ? ' <small>(als „' + esc(r.via) + '“)</small>' : '') + ' <small>· ' + fmt(r.e.n) + ' · ' + (linked(r.t, r.e) ? 'verknüpft' : 'ohne Normdaten') + '</small> <span class="dot ' + entState(r.t, r.e) + '" style="vertical-align:-1px"></span></div>').join('') : '<div class="r muted">Nichts gefunden.</div>';
    $$('#gres .r[data-k]').forEach(el => el.onclick = () => go(rows[+el.dataset.k])); };
  const go = r => { closeModal(); const tab = linked(r.t, r.e) ? 'check' : 'link'; cur.type = r.t; S.ui.type[tab] = r.t; S.ui.show[tab] = 'all'; openTab(tab, selKey(r.e)); };
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
    for (const k in S.grp[t]) { const d = S.grp[t][k]; if (d.d) rows.push({ scope: 'grp', t, key: k, what: k + ': Namensgruppe bestätigt', by: d.by || '', at: d.t || '' }); }
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
  let h = '<div class="wrap"><h1 class="t">Stand und Protokoll</h1><div class="sub">Alle Entscheidungen, neueste zuerst. Einzelne Zeilen lassen sich entfernen.</div><div class="stats" style="margin-top:12px">';
  for (const t of TYPES) { const c = checkItems(t), l = linkItems(t); const cd = c.filter(e => DONE(entState(t, e))).length, ld = l.filter(e => DONE(entState(t, e))).length; h += '<div class="stat"><div class="n">' + fmt(cd) + ' <span class="small muted">/ ' + fmt(c.length) + '</span></div><div class="l">' + esc(TT[t].tab) + ' geprüft</div><div class="n" style="margin-top:6px">' + fmt(ld) + ' <span class="small muted">/ ' + fmt(l.length) + '</span></div><div class="l">verknüpft</div></div>'; }
  const rd = READ.filter(it => DONE(itemState('read', 'taxon', it))).length;
  h += '<div class="stat"><div class="n">' + fmt(rd) + ' <span class="small muted">/ ' + fmt(READ.length) + '</span></div><div class="l">Lesefehler entschieden</div><div class="n" style="margin-top:6px">' + fmt(S.text.length) + '</div><div class="l">korrigierte Lesungen</div></div><div class="stat"><div class="n">' + (st.n ? pct(p) : '–') + '</div><div class="l">Genauigkeit Stichprobe' + (st.n ? ' (' + pct(lo) + '–' + pct(hi) + ', n = ' + st.n + ')' : '') + '</div></div></div>';
  h += '<div class="card" style="margin-top:14px"><div class="cb">' + (rows.length ? '<table class="tbl"><tr><th>Wann</th><th>Bereich</th><th>Entscheidung</th><th>von</th><th></th></tr>' + rows.slice(0, 3000).map((r, i) => '<tr><td class="small">' + esc(r.at ? new Date(r.at).toLocaleString('de-DE') : '') + '</td><td class="small">' + esc(AREA[r.t] || r.t) + '</td><td>' + esc(r.what) + '</td><td class="small">' + esc(r.by) + '</td><td><button class="lbtn" data-del="' + i + '">entfernen</button></td></tr>').join('') + '</table>' : '<p class="muted">Noch keine Entscheidungen.</p>') + '</div></div></div>';
  $('#work').innerHTML = h;
  $$('#work [data-del]').forEach(b => b.onclick = () => { const r = rows[+b.dataset.del]; commit('entfernt', () => {
    if (r.scope === 'ent') delete S.ent[r.t][r.key]; else if (r.scope === 'grp') delete S.grp[r.t][r.key]; else if (r.scope === 'id') delete S.id[r.t][r.key]; else if (r.scope === 'men') delete S.men[r.t][r.key];
    else if (r.scope === 'text') S.text = S.text.filter(c => c.id !== r.key); else if (r.scope === 'ev') delete S.ev[r.key]; else if (r.scope === 'qa') delete S.qa[r.key]; }); });
}

// ---------------------------------------------------------------- export (read by the pipeline: data/review/*.csv)
const csvCell = v => { v = v == null ? '' : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
const toCSV = (head, rows) => [head.map(csvCell).join(',')].concat(rows.map(r => head.map(h => csvCell(r[h])).join(','))).join('\n') + '\n';
const SECTION = { taxon: 'taxa', person: 'persons', place: 'places', habitat: 'habitats' };
const ID_HEAD = ['section', 'name_form', 'decision', 'target', 'authority', 'scientific_name', 'rank', 'lat', 'lon', 'uncertainty_m', 'eunis_match', 'reason', 'note', 'reviewed_by', 'reviewed_at'];
function exportIdentities() {
  const rows = []; const done = new Set();
  const base = (t, name, d) => ({ section: SECTION[t], name_form: name, note: d.note || '', reviewed_by: d.by || 'student', reviewed_at: d.t || '' });
  const taxonTarget = e => { const ed = entDec('taxon', e); if (ed && ed.d === 'r') return { label: ed.target.label, key: ed.target.key, sci: ed.target.sci, rank: ed.target.rank }; if (ed && ed.d === 'n') return null; return e.e[2] ? { label: e.label, key: e.e[2], sci: e.e[1], rank: e.e[3] } : null; };
  for (const t of TYPES) for (const e of X[t].ents) {
    const ed = entDec(t, e); const gd = grpDec(t, e);
    for (const nm of e.names) {
      if (done.has(t + '|' + nm.key)) continue;
      const d = nameDec(t, nm); const r = base(t, nm.name, (d && d.d) ? d : gd || ed || {});
      let dec = d && d.d ? d.d : null;
      if (!dec && gd) { dec = 'y'; r.note = 'Namensgruppe bestätigt'; }
      if (!dec && ed && ed.d && ed.d !== 'u') { if (ed.d === 'y' && safeName(t, nm)) { dec = 'y'; r.note = 'mit dem Eintrag bestätigt'; } else if ((t === 'taxon' || t === 'habitat') && (ed.d === 'r' || ed.d === 'n')) dec = ed.d === 'r' ? 'y' : 'x'; }
      if (!dec) continue;
      done.add(t + '|' + nm.key);
      if (t === 'taxon') {
        if (dec === 'y') { const tg = taxonTarget(e); Object.assign(r, tg && tg.key ? { decision: 'same', target: tg.label, authority: 'gbif:' + tg.key, scientific_name: tg.sci || '', rank: tg.rank || '' } : { decision: 'own', target: nm.name }); }
        else if (dec === 'r') Object.assign(r, { decision: 'same', target: d.target.label, authority: d.target.key ? 'gbif:' + d.target.key : '', scientific_name: d.target.sci || '', rank: d.target.rank || '' });
        else if (dec === 'x') Object.assign(r, { decision: 'own', target: nm.name, reason: 'rejected' });
        else if (dec === 'o') Object.assign(r, { decision: 'own', target: nm.name, reason: 'separate' });
      } else {
        if (dec === 'y') Object.assign(r, { decision: 'same', target: e.label });
        else if (dec === 'r') Object.assign(r, { decision: 'same', target: d.target.label });
        else if (dec === 'o' || dec === 'x') Object.assign(r, { decision: 'own', target: nm.name, reason: dec === 'o' ? 'separate' : 'rejected' });
      }
      if (dec === 'n') Object.assign(r, { decision: 'none', reason: (d && d.reason) || '' });
      else if (dec === 'u') r.decision = 'unsure';
      if (r.decision) rows.push(r);
    }
    if (!ed || !ed.d || ed.d === 'u') continue;
    const r = base(t, e.label, ed);
    // the authority goes on every name that stays with the entity, so it survives a new run whose canonical label differs
    const stays = e.names.filter(nm => nameState(t, nm) === 'y');
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
  // two entities confirmed on the same authority record are one entity: merge them explicitly
  for (const t of ['person', 'place']) {
    const groups = new Map();
    for (const e of X[t].ents) { const ed = entDec(t, e); if (!ed || ed.d !== 'y') continue; const f = ed.fix || {};
      const k = t === 'person' ? (ed.qid || e.e[1] ? 'wd:' + (ed.qid || e.e[1]) : ed.gnd || e.e[2] ? 'gnd:' + (ed.gnd || e.e[2]) : '') : (f.geonames_id || (!f.lat && e.e[4]) ? 'gn:' + (f.geonames_id || e.e[4]) : f.qid || (!f.lat && e.e[5]) ? 'wd:' + (f.qid || e.e[5]) : '');
      if (!k) continue; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(e); }
    for (const [k, es] of groups) { if (es.length < 2) continue; es.sort((a, b) => b.n - a.n); const main = es[0];
      for (const e of es.slice(1)) for (const nm of e.names) { if (nameGone(nameState(t, nm))) continue;
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
const qaKey = r => r[0] + '|' + r[2] + '|' + r[4];
function exportQA() {
  const head = P.qa.head.concat(['decision', 'review_note', 'reviewed_by', 'reviewed_at']); const lab = { y: 'confirmed', n: 'wrong', u: 'unsure' };
  return toCSV(head, P.qa.rows.map(r => { const d = S.qa[qaKey(r)] || {}; const o = {}; P.qa.head.forEach((h, i) => o[h] = r[i]); return Object.assign(o, { decision: lab[d.d] || '', review_note: d.note || '', reviewed_by: d.d ? d.by || 'student' : '', reviewed_at: d.d ? d.t : '' }); }));
}
// model readings the reviewer has not looked at yet, for the record (not read by the pipeline)
function exportReadings() {
  const head = ['entry_id', 'entry_uid', 'written', 'graph_taxon', 'model', 'reading', 'kind', 'species_de', 'scientific_name', 'confidence', 'note', 'agreement', 'decision'];
  const rows = [];
  for (const it of READ) { const m = P.taxon.men[it.mi]; const ce = P.taxon.ent[P.taxon.forms[m[0]][2]]; const d = S.men.taxon[it.key] || {};
    for (const r of it.rs) rows.push({ entry_id: E[m[1]][0], entry_uid: E[m[1]][1], written: writtenOf(it.mi), graph_taxon: ce[0], model: MODEL_DE[r.src], reading: r.word, kind: r.kind, species_de: r.species || '', scientific_name: r.sci || '', confidence: r.conf || '', note: r.note || '', agreement: it.ag, decision: d.d || '' }); }
  return toCSV(head, rows);
}
function exportLog() { return toCSV(['when', 'area', 'decision', 'by'], logRows().map(r => ({ when: r.at, area: r.t, decision: r.what, by: r.by }))); }
function progressJSON() { return JSON.stringify({ app: 'histornigraph-validation', version: 4, export: P.export, who: S.who, saved_at: new Date().toISOString(), id: S.id, men: S.men, ent: S.ent, grp: S.grp, text: S.text, qa: S.qa, ev: S.ev }, null, 1); }
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
  + '- identities.csv: welche Art/Person/welchen Ort ein geschriebener Name meint (same/own/none/unsure) und Normdaten je Eintrag (link/nolink mit gbif:/wd:/gnd:/gn:/osm:/eunis:).\n'
  + '- value_corrections.csv: einzeln entschiedene Belege (replace/drop), angewendet direkt nach der Extraktion.\n'
  + '- text_corrections.csv: korrigierte Lesungen; diese Einträge werden bei der nächsten Extraktion neu gelesen.\n'
  + '- evaluation_taxa.csv: Stichprobe zur Genauigkeit der Artbestimmung (Auswertung).\n'
  + '- qa_flags.csv: Urteile zu den Hinweisen (noch nicht von der Pipeline gelesen).\n'
  + 'model_readings.csv: Zweit- und Drittlesung der Modelle mit dem Stand der Entscheidung (zur Information).\n'
  + 'validation_log.csv: alle Entscheidungen. validation_progress.json: Sicherung für „Fortschritt laden“.\n';
function exportFiles() { return [['review/identities.csv', exportIdentities()], ['review/value_corrections.csv', exportMentions()], ['review/text_corrections.csv', exportText()], ['review/evaluation_taxa.csv', exportEval()], ['review/qa_flags.csv', exportQA()], ['model_readings.csv', exportReadings()], ['validation_log.csv', exportLog()], ['validation_progress.json', progressJSON()], ['LIESMICH.txt', README()]]; }
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
  const nDec = TYPES.reduce((a, t) => a + Object.keys(S.id[t]).length + Object.keys(S.ent[t]).length + Object.keys(S.men[t]).length + Object.keys(S.grp[t]).length, 0);
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

// ---------------------------------------------------------------- import (v1 pair decisions, v2–v4 backups)
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
  // v3 marked "edited" names with d = e; a reassignment without a target cannot be exported
  for (const t of TYPES) for (const k of Object.keys(S.id[t])) { const d = S.id[t][k]; if (d.d === 'e' || (d.d === 'r' && !d.target)) delete S.id[t][k]; }
}
$('#fileImport').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  try {
    const j = /\.zip$/i.test(f.name) ? await readZipJSON(await f.arrayBuffer()) : JSON.parse(await f.text());
    if (j.export && j.export !== P.export && !confirm('Die Sicherung stammt von ' + j.export + ', diese Oberfläche von ' + P.export + '. Trotzdem laden?')) return;
    let n = 0; HIST.push(['Import', snapshot()]);
    if ((j.version || 1) < 2) n = importV1(j);
    else { for (const k of ['id', 'men', 'ent', 'grp']) for (const t of TYPES) n += mergeStore(S[k][t], (j[k] || {})[t]); n += mergeStore(S.qa, j.qa); n += mergeStore(S.ev, j.ev);
      for (const c of j.text || []) if (!S.text.some(x => x.id === c.id)) { S.text.push(c); n++; } }
    if (!S.who && j.who) S.who = j.who;
    migrate(); save(); closeModal(); toast(n + ' Entscheidungen übernommen' + ((j.version || 1) < 2 ? ' (aus Version 1)' : '')); openTab(cur.tab);
  } catch (err) { alert('Laden fehlgeschlagen: ' + err.message); }
});

// ---------------------------------------------------------------- help
function showHelp(first) {
  $('#modal').innerHTML = '<button class="lbtn x" data-close>Schließen ✕</button><h2>' + (first ? 'Willkommen beim Laubmann-Abgleich' : 'Anleitung') + '</h2>'
    + (first ? '<div class="row" style="margin-bottom:10px"><span>Dein Name oder Kürzel:</span><input type="text" class="ftext" id="hwho" value="' + esc(S.who) + '" placeholder="z. B. AB"><button class="btn" id="himport">Fortschritt laden …</button></div>' : '')
    + '<p>Ziel: Jede Art, Person, jeder Ort und Lebensraum des Tagebuch-Graphen soll den richtigen Normdatensatz haben (GBIF, Wikidata/GND, GeoNames/Wikidata/Koordinaten, EUNIS), und alle geschriebenen Namen, die dasselbe meinen, sollen zusammengehören. Die Entscheidungen hängen am geschriebenen Namen und an der Tagebuchstelle; sie gelten daher auch für den neuen Graphen nach der endgültigen Ontologie.</p>'
    + '<h3>Vier Aufgaben (Reiter oben)</h3><ol>'
    + '<li><b>Prüfen</b> – Einträge, die schon Normdaten haben: Stimmt der Datensatz? <kbd>Y</kbd> stimmt · <kbd>A</kbd> anders … · <kbd>N</kbd> keine/nicht bestimmbar · <kbd>U</kbd> unsicher. Darunter die geschriebenen Namen mit Haken: Haken weg = der Name gehört nicht hierher (dann „zu welchem Eintrag?“ oder „kein(e) …“).</li>'
    + '<li><b>Verknüpfen</b> – Einträge ohne Normdaten: GBIF-Art suchen, Wikidata-Kandidat wählen (Ziffern <kbd>1</kbd>–<kbd>9</kbd>), Lage suchen oder in die Karte klicken, EUNIS-Klasse wählen. Oder „ist dasselbe wie …“: ein schon vorhandener Eintrag (<kbd>⇧A</kbd>–<kbd>⇧E</kbd>) – dann gehören alle Namen dorthin. Bei Personen steht ein Vorschlag von Claude Opus 5.5 dabei, der die Kandidaten mit Lebensdaten und Tagebuchstellen abgeglichen hat.</li>'
    + '<li><b>Namen</b> – Einträge mit unsicheren oder wahrscheinlich fehlenden Namen: Haken setzen = gehört hierher; Vorschläge aus ähnlich geschriebenen Namen anderer Einträge; über „Weiteren Namen hinzufügen“ jeden Namen des Graphen suchen. „Namensgruppe stimmt so“ (<kbd>Y</kbd>) bestätigt alle.</li>'
    + '<li><b>Lesefehler</b> – Belege, bei denen zwei Modelle (Gemini 3.5 Flash und Claude Opus 5.5) die Zeile im Scan anders lesen als die Transkription. Das Zeilenbild steht oben, die Seite rechts. <kbd>Y</kbd> Transkription stimmt · <kbd>1</kbd>/<kbd>2</kbd> Lesung eines Modells übernehmen (setzt Wort und Art) · <kbd>E</kbd> selbst lesen · <kbd>A</kbd> Wort stimmt, andere Art · <kbd>N</kbd> kein Vogel. „Beide Modelle lesen dasselbe“ ist meist richtig, aber bitte am Bild prüfen; bei schiefen oder falsch ausgeschnittenen Zeilen hilft die Seite rechts.</li></ol>'
    + '<p><b>Stichprobe</b>: zufällige Belege der Reihe nach beurteilen (richtig/falsch) – daraus ergibt sich die Genauigkeit der Artbestimmung. <b>Hinweise</b>: automatische Prüfungen bestätigen oder widerlegen. <b>Protokoll</b>: Stand und alle Entscheidungen.</p>'
    + '<h3>Richtlinien</h3><ul><li><b>Gleiche Art, nicht gleiches Wort</b>: historische und regionale Namen (Dompfaff = Gimpel, Weidenlaubvogel = Zilpzalp, Fischreiher = Graureiher) gehören zur Art; der geschriebene Name bleibt im Graph erhalten.</li>'
    + '<li>Ein Zusatzwort, das nur das Aussehen beschreibt (Schwarzamsel) → die Art; bezeichnet es eine eigene Unterart/Form (Trauerbachstelze) → diese über „anders“. Wie oft ein Name vorkommt, entscheidet nie über seine Bedeutung.</li>'
    + '<li>Lesefehler sind keine Synonyme: Lesung korrigieren oder ✗ „Lesefehler“. Nest, Ei, Feder einer Art zählen als Nachweis dieser Art. Nur Gattung/Familie genannt (Möwe, Specht) → die Gattung/Familie wählen, nicht eine Art.</li>'
    + '<li>Personen: Kurzformen (W. Wüst) nur bei eindeutigem Zusammenhang zuordnen; „Frau X“ ist nicht „Herr X“; die Person muss zur Zeit der Nennung gelebt haben. Orte: ähnlich geschrieben heißt nicht gleicher Ort; kleine Örtlichkeiten mit ungefährer Lage und passender Unsicherheit setzen; allgemeine Wörter (Wald, See, Garten) sind kein Ortsname.</li></ul>'
    + '<h3>Sichern</h3><p>Alles wird im Browser gespeichert. Am besten unter „Sichern &amp; Export“ eine Sicherungsdatei wählen (z. B. im Drive-Ordner): dann wird jede Entscheidung sofort in die Datei geschrieben. Zum Abgeben: „Alles als ZIP“.</p>'
    + '<h3>Tastatur</h3><table><tr><td><kbd>Y</kbd> <kbd>A</kbd> <kbd>N</kbd> <kbd>U</kbd></td><td>stimmt · anders · keine/nicht bestimmbar · unsicher</td></tr><tr><td><kbd>1</kbd>–<kbd>9</kbd></td><td>Kandidat (Personen) · Lesung übernehmen (Lesefehler) · Grund (bei „kein(e) …“)</td></tr><tr><td><kbd>E</kbd></td><td>Lesung korrigieren</td></tr><tr><td><kbd>⏎</kbd> · <kbd>⇧⏎</kbd> · <kbd>↓</kbd> <kbd>↑</kbd></td><td>nächster offener · vorheriger Eintrag</td></tr><tr><td><kbd>Z</kbd></td><td>rückgängig</td></tr><tr><td><kbd>←</kbd> <kbd>→</kbd> · <kbd>B</kbd></td><td>Seiten im Scan · Scan ein/aus</td></tr><tr><td><kbd>/</kbd> · <kbd>Strg+K</kbd></td><td>Liste durchsuchen · alles durchsuchen</td></tr><tr><td><kbd>Esc</kbd></td><td>Suche/Fenster schließen</td></tr></table>';
  $('#ovModal').classList.add('show');
  const hw = $('#hwho'); if (hw) { hw.focus(); hw.oninput = e => { S.who = e.target.value.trim(); save(); }; }
  const hi = $('#himport'); if (hi) hi.onclick = () => $('#fileImport').click();
}
$('#btnHelp').onclick = () => showHelp(false);
$('#btnTheme').onclick = () => { const r = document.documentElement; const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; r.dataset.theme = dark ? 'light' : 'dark'; S.ui.theme = r.dataset.theme; save(); };
window.addEventListener('beforeunload', () => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { } });

// ---------------------------------------------------------------- start
try { P = await loadPayload(); }
catch (e) { $('#loading').textContent = 'Die Daten konnten nicht geladen werden. Bitte Chrome, Edge oder Firefox (aktuell) verwenden. (' + e.message + ')'; return; }
try { DRIVE = JSON.parse($('#drive').textContent || '{}'); } catch (e) { DRIVE = {}; }
E = P.E; PG = P.PG; SUG = P.sug || {}; SUG3 = P.sug3 || {}; PM = P.pm || {}; CAND = P.cand; EUNIS = new Map(P.eunis.map(e => [e[0], e])); uid2e = new Map(E.map((e, i) => [e[1], i]));
for (const t of TYPES) CAND[t] = CAND[t] || { nc: {}, ec: {} };
$('#exportname').textContent = P.export;
try { const raw = localStorage.getItem(LS); if (raw) S = Object.assign(S, JSON.parse(raw)); } catch (e) { }
normalizeState();
document.documentElement.dataset.theme = S.ui.theme || 'light';   // light unless the reviewer switched
buildModel(); buildReadItems(); migrate();
window.__hog = { P, S, X, READ, SUG, SUG3, PM, CAND, cur, ui, openTab, selectItem, showScan, scanFor, entAct, readAct, applyReading, nameCheck, mergeInto, setName, setEnt, setMen, setGrp, commit, diffHunks, applyReadings, exportIdentities, exportMentions, exportText, exportEval, exportReadings, importV1, entState, nameState, namesState, readState, itemState, sameWord, writtenOf, undo };
$('#loading').remove();
if (S.ui.noscan) $('#main').classList.add('noscan');
savedLabel(); initGrip();
cur.tab = TAB[S.ui.tab] ? S.ui.tab : 'check';
openTab(cur.tab);
if (!S.who) setTimeout(() => showHelp(true), 300);
