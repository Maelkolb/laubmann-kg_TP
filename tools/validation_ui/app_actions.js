// Laubmann-Abgleich v4 — part 4: decisions, panels, searches, readings editor, keyboard, clicks.
const targetOf = (t, e) => t === 'taxon' ? { label: e.label, sci: e.e[1], key: e.e[2], rank: e.e[3] } : { label: e.label };
const entTarget = (t, e) => t === 'habitat' ? { code: e.e[1], label: e.e[1] + ' ' + ((EUNIS.get(e.e[1]) || [])[1] || ''), match: e.e[2] || 'close' } : targetOf(t, e);
function setEnt(t, e, obj) { if (!obj) delete S.ent[t][e.label]; else S.ent[t][e.label] = stampObj(obj); }
function setName(t, nm, obj) { if (!obj) delete S.id[t][nm.key]; else S.id[t][nm.key] = stampObj(obj); }
function setMen(t, mi, obj) { const k = X[t].mkey[mi]; if (!obj) delete S.men[t][k]; else S.men[t][k] = stampObj(obj); }
function setGrp(t, e, obj) { if (!obj) delete S.grp[t][e.label]; else S.grp[t][e.label] = stampObj(obj); }
// after a decision: with "automatisch weiter" the next open item follows once this one is done
function afterDecision() {
  if (!S.ui.adv || !cur.sel || ui.panel) return;
  const st = itemState(cur.tab, cur.type, cur.sel); const done = cur.tab === 'names' ? st === 'y' || st === 'r' : DONE(st);
  if (done) { const it = cur.sel; setTimeout(() => { if (cur.sel === it && !ui.panel) nextItem(1); }, 450); }
}

// ---------------------------------------------------------------- panels (reassign / reasons)
function panelHtml(t, pn) {
  if (pn.kind === 'not') return '<div class="panel" data-scope="' + pn.scope + '"><h5>Warum? (Taste 1–' + TT[t].not.length + ')</h5><div class="opts">' + TT[t].not.map(([k, l], i) => '<button class="btn sm" data-reason="' + k + '"><kbd>' + (i + 1) + '</kbd> ' + esc(l) + '</button>').join('') + '</div></div>';
  const title = { taxon: 'Welche Art ist gemeint?', person: 'Welche Person ist gemeint?', place: 'Welcher Ort ist gemeint?', habitat: 'Welche EUNIS-Klasse?' }[t];
  const ph = { taxon: 'deutscher oder wissenschaftlicher Name …', person: 'Person im Graph suchen …', place: 'Ort im Graph suchen …', habitat: 'EUNIS-Code oder englischer Begriff (reed, forest, C3.2) …' }[t];
  const special = pn.scope === 'e' || pn.scope === 'ev' || pn.scope === 'qa' ? '' : t === 'taxon' ? '<button class="btn sm" data-special="x">Art nicht bestimmbar</button>' : t === 'person' ? '<button class="btn sm" data-special="o">eigene Person</button>' : t === 'place' ? '<button class="btn sm" data-special="o">eigener Ort</button>' : '';
  return '<div class="panel rpanel" data-scope="' + pn.scope + '" data-kind="' + t + '"><h5>' + esc(pn.title || title) + ' <span class="muted">· ↑↓ wählen, ⏎ übernehmen, Esc schließt</span></h5><div class="row"><input type="text" class="grow rq" placeholder="' + esc(ph) + '" autocomplete="off" value="' + esc(pn.q || '') + '">'
    + (t === 'taxon' ? '<button class="lbtn rgbif">in GBIF suchen</button>' : '') + (t === 'habitat' ? '<select class="rmatch" title="exact = gleiche Bedeutung, close = sehr ähnlich, broad = Klasse ist allgemeiner"><option value="exact">exact</option><option value="close" selected>close</option><option value="broad">broad</option></select>' : '')
    + special + '</div><div class="res rres"></div></div>';
}
function openPanel(scope, kind, q, title) {
  ui.panel = { scope, kind, q: q || '', title };
  if (scope.startsWith('m:') && TAB[cur.tab].typed) ui.open.add(P[cur.type].men[+scope.slice(2)][0]);
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
  X[t].ents.forEach(e => { if (!e.names.length && t !== 'habitat') return; const labs = (t === 'place' ? e.e[8] : e.e[3]) || [e.label]; const hay = [...labs, ...e.names.map(n => n.name)].map(fold); if (!hay.some(h => h.includes(f))) return;
    res.push([fold(e.label) === f ? 0 : hay.some(h => h.startsWith(f)) ? 1 : 2, -e.n, e]); });
  return res.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(x => x[2]);
}
function localNames(t, e, q) {
  const f = fold(q); if (!f) return [];
  return X[t].names.filter(nm => nm.ent !== e.i && fold(nm.name).includes(f)).sort((a, b) => (fold(a.name) === f ? 0 : 1) - (fold(b.name) === f ? 0 : 1) || b.n - a.n).slice(0, 12);
}
function renderLocalResults(root) {
  const t = root.dataset.kind; const scope = root.dataset.scope; const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim();
  if (t === 'habitat' && scope !== 'add') return eunisFilter(root);
  if (!q) { box.innerHTML = ''; root._rows = null; return; }
  let rows;
  if (scope === 'add') { const e = cur.sel; rows = localNames(t, e, q).map(nm => { const h = ENT(t, nm.ent); return { html: '<b>' + esc(nm.name) + '</b> <small>' + fmt(nm.n) + '× · derzeit bei „' + esc(h.label) + '“ (' + authText(t, h).replace(/<[^>]+>/g, '') + ')</small>', pick: () => { commit('Name hinzugefügt: ' + nm.name, () => setName(t, nm, { d: 'r', target: targetOf(t, e) })); } }; }); }
  else if (t === 'taxon') rows = localTaxa(q).map(e => ({ html: '<b>' + esc(e.label) + '</b> <i>' + esc(e.e[1]) + '</i> <small>' + esc(e.e[3] || '') + ' · ' + fmt(e.n) + ' Belege</small>', pick: () => chooseTarget(t, scope, targetOf('taxon', e)) }));
  else rows = localEnts(t, q).map(e => ({ html: '<b>' + esc(e.label) + '</b> <small>' + fmt(e.n) + ' ' + TT[t].unit + ' · ' + authText(t, e).replace(/<[^>]+>/g, '') + '</small>', pick: () => chooseTarget(t, scope, { label: e.label }) }));
  box.innerHTML = rows.length ? rows.map((x, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '">' + x.html + '</div>').join('') : '<div class="r muted">Nichts im Graph gefunden' + (t === 'taxon' && scope !== 'add' ? ' — ⏎ sucht in GBIF' : '') + '.</div>';
  root._rows = rows.length ? rows : null; root._hi = 0;
  $$('.r[data-k]', box).forEach(el => el.onclick = () => rows[+el.dataset.k].pick());
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
    root._rows = rows.length ? rows.map(x => ({ pick: () => pickGbif(x, scope) })) : null; root._hi = 0;
    $$('.r[data-k]', box).forEach(el => el.onclick = () => pickGbif(rows[+el.dataset.k], scope));
  } catch (e) { box.innerHTML = '<div class="r muted">GBIF nicht erreichbar (' + esc(e.message) + ').</div>'; }
}
async function pickGbif(x, scope) {
  let key = x.key, name = x.name, rank = x.rank; const vn = (x.vn || '').split(',')[0];
  if (x.acc && x.acc !== x.key && x.status && x.status !== 'ACCEPTED') { try { const a = await getJSON('https://api.gbif.org/v1/species/' + x.acc); key = a.key; name = a.canonicalName || a.scientificName; rank = a.rank; toast('Synonym: auf den gültigen Namen ' + name + ' umgestellt'); } catch (e) { } }
  const local = X.taxon.ents.find(e => e.e[2] === String(key));
  chooseTarget('taxon', scope, { label: local ? local.label : (vn || name), sci: name, key: String(key), rank: lc(rank) });
}
function eunisFilter(root) {
  const box = root.querySelector('.rres'); const q = root.querySelector('.rq').value.trim().toLowerCase(); const scope = root.dataset.scope; if (!q) { box.innerHTML = ''; root._rows = null; return; }
  const res = P.eunis.filter(e => e[0].toLowerCase().startsWith(q) || e[1].toLowerCase().includes(q)).sort((a, b) => a[2] - b[2] || a[0].localeCompare(b[0])).slice(0, 80);
  const match = root.querySelector('.rmatch');
  box.innerHTML = res.length ? res.map((e, k) => '<div class="r' + (k === 0 ? ' hi' : '') + '" data-k="' + k + '" style="padding-left:' + (6 + 10 * (e[2] - 1)) + 'px"><b>' + esc(e[0]) + '</b> ' + esc(e[1]) + ' <small>Ebene ' + e[2] + '</small></div>').join('') : '<div class="r muted">Keine Klasse gefunden (Namen sind englisch).</div>';
  const pick = e => chooseTarget('habitat', scope, { code: e[0], label: e[0] + ' ' + e[1], match: match ? match.value : 'close' });
  root._rows = res.length ? res.map(e => ({ pick: () => pick(e) })) : null; root._hi = 0;
  $$('.r[data-k]', box).forEach(el => el.onclick = () => pick(res[+el.dataset.k]));
}
function panelKeys(ev) {
  const root = ev.target.closest && ev.target.closest('.rpanel'); if (!root) return false;
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { const rs = $$('.rres .r[data-k]', root); if (!rs.length) return true; root._hi = Math.max(0, Math.min(rs.length - 1, (root._hi || 0) + (ev.key === 'ArrowDown' ? 1 : -1))); rs.forEach((r, i) => r.classList.toggle('hi', i === root._hi)); rs[root._hi].scrollIntoView({ block: 'nearest' }); ev.preventDefault(); return true; }
  if (ev.key === 'Enter') { ev.preventDefault(); const rs = $$('.rres .r[data-k]', root); const hi = rs[root._hi || 0];
    if (root._rows && hi) hi.click(); else if (root.dataset.kind === 'taxon' && root.dataset.scope !== 'add') gbifSearch(root); return true; }
  return false;
}

// ---------------------------------------------------------------- decisions
function chooseTarget(t, scope, target) {
  ui.panel = null;
  if (scope === 'ev') { const it = cur.sel; commit('Stichprobe', () => { S.ev[it.key] = stampObj(Object.assign({}, S.ev[it.key] || {}, { d: 'n', target, cls: P.taxon.forms[P.taxon.men[it.mi][0]][3] })); setMen('taxon', it.mi, { d: 'r', target, note: 'aus der Stichprobe' }); }); afterDecision(); return; }
  if (scope === 'qa') { const it = cur.sel; commit('Hinweis', () => { S.men.taxon[it.r[1] + '|' + lc(it.r[4]) + '|0'] = stampObj({ d: 'r', target, written: it.r[4], note: 'Hinweis ' + it.r[2] }); if (!(S.qa[it.key] || {}).d) S.qa[it.key] = stampObj({ d: 'n' }); }); return; }
  const e = cur.sel;
  if (scope === 'e') commit(TT[t].one + ' zugeordnet: ' + target.label, () => setEnt(t, e, { d: 'r', target }));
  else if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('Name zugeordnet', () => setName(t, nm, { d: 'r', target })); }
  else if (scope.startsWith('m:')) { const mi = +scope.slice(2); const cu = P[t].forms[P[t].men[mi][0]][2]; const same = t === 'taxon' ? target.key && target.key === P.taxon.ent[cu][2] : target.label === ENT(t, cu).label; commit('Beleg zugeordnet', () => setMen(t, mi, same ? { d: 'y', note: 'geprüft' } : { d: 'r', target })); }
  afterDecision();
}
function special(t, scope, code) {
  ui.panel = null;
  if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('Name', () => setName(t, nm, { d: code })); }
  else if (scope.startsWith('m:')) commit('Beleg', () => setMen(t, +scope.slice(2), { d: code }));
  afterDecision();
}
function reason(t, scope, r) {
  ui.panel = null;
  if (scope.startsWith('n:')) { const nm = X[t].names[+scope.slice(2)]; commit('kein Eintrag', () => setName(t, nm, { d: 'n', reason: r })); }
  else if (scope.startsWith('m:')) commit('Beleg entfernt', () => setMen(t, +scope.slice(2), { d: 'n', reason: r }));
  afterDecision();
}
function personPick(e) {   // the candidate that "stimmt" would confirm: chosen, else automatic link, else the model's suggestion
  const cd = entDec('person', e) || {}; if (cd.qid || cd.gnd) return [cd.qid || null, cd.gnd || null];
  if (cd.d) return [null, null];
  if (e.e[1] || e.e[2]) return [e.e[1] || null, e.e[2] || null];
  const pm = PM[e.i]; return [pm && /^Q\d+$/.test(pm[0]) ? pm[0] : null, null];
}
function entAct(t, e, a) {
  const cd = entDec(t, e) || {};
  if (a === '') { commit('zurückgesetzt', () => setEnt(t, e, null)); return; }
  if (a === 'u') { commit('unsicher', () => setEnt(t, e, cd.d === 'u' ? null : Object.assign({}, cd, { d: 'u' }))); return afterDecision(); }
  if (t === 'taxon') {
    if (a === 'y') { if (!e.e[2]) return toast('Keine GBIF-Art: mit „Andere Art …“ eine Art zuordnen oder „nicht bestimmbar“'); commit('Art bestätigt', () => setEnt(t, e, cd.d === 'y' ? null : { d: 'y' })); return afterDecision(); }
    if (a === 'r') { const llm = e.names.map(nm => nm.f[5]).find(Boolean); return openPanel('e', 'r', e.e[2] ? '' : (llm || e.label), e.e[2] ? 'Andere Art für alle Namen dieses Eintrags' : 'GBIF-Art zuordnen (⏎ sucht in GBIF)'); }
    if (a === 'n') { commit('nicht bestimmbar', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision(); }
  }
  if (t === 'habitat') {
    if (a === 'y') { if (!e.e[1]) return toast('Keine EUNIS-Klasse: mit „Andere Klasse …“ eine wählen oder „Keine Klasse passt“'); commit('Klasse bestätigt', () => setEnt(t, e, cd.d === 'y' ? null : { d: 'y' })); return afterDecision(); }
    if (a === 'r') return openPanel('e', 'r', '');
    if (a === 'n') { commit('keine Klasse', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision(); }
  }
  if (t === 'person') {
    if (a === 'y') { const [q, g] = personPick(e); if (!q && !g) return toast('Erst einen Wikidata-Kandidaten oder eine GND wählen (oder „Keine Normdaten“)');
      if (q && q !== cd.qid) return pickPerson(e, q);
      commit('Normdaten bestätigt', () => setEnt(t, e, Object.assign({}, cd, { d: 'y', qid: q || null, gnd: g || null }))); return afterDecision(); }
    if (a === 'r') { const w = $('#wq'); if (w) { w.focus(); w.select(); } return; }
    if (a === 'n') { commit('keine Normdaten', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision(); }
  }
  if (t === 'place') {
    if (a === 'y') { if (e.e[1] == null && !(cd.fix && cd.fix.lat)) return toast('Keine Lage: suchen, Koordinate eingeben oder in die Karte klicken'); commit('Lage bestätigt', () => setEnt(t, e, Object.assign({}, cd, { d: 'y' }))); return afterDecision(); }
    if (a === 'r') { const w = $('#nq'); if (w) { w.focus(); w.select(); } return; }
    if (a === 'n') { commit('Lage nicht bestimmbar', () => setEnt(t, e, cd.d === 'n' ? null : { d: 'n' })); return afterDecision(); }
  }
}
function mvAccept(t, e) {   // take the machine verdict over as the reviewer's own decision (one click, undoable)
  const v = machineVerdict(t, e); if (!v) return;
  if (t === 'taxon') {
    if (v.new_key) { commit('Maschine: Art übernommen', () => setEnt(t, e, { d: 'r', target: { label: v.species_de || v.new_sci || v.new_key, sci: v.new_sci || v.sci || '', key: String(v.new_key), rank: v.new_rank || 'species' }, note: 'Maschinelle Prüfung' })); return afterDecision(); }
    if (v.link === 'ok' && e.e[2]) { commit('Maschine: Art bestätigt', () => setEnt(t, e, { d: 'y', note: 'Maschinelle Prüfung' })); return afterDecision(); }
    if (v.link === 'none') { commit('Maschine: nicht bestimmbar', () => setEnt(t, e, { d: 'n', note: 'Maschinelle Prüfung' })); return afterDecision(); }
  }
  if (t === 'person') {
    const q = /^Q\d+$/.test(v.wikidata || '') ? v.wikidata : '', g = v.gnd && !/^(none|unclear)$/.test(v.gnd) ? v.gnd : '';
    if (q || g) { const cands = new Map(); for (const nm of e.names) for (const c of nm.f[5] || []) cands.set(c[0], c); const c = cands.get(q) || [];
      commit('Maschine: Normdaten übernommen', () => setEnt(t, e, Object.assign({}, entDec(t, e) || {}, { d: 'y', qid: q || null, wd_label: c[1] || '', wd_description: c[2] || '', gnd: g || null, gnd_label: g || '', gnd_info: g ? 'Maschinelle Prüfung' : '', note: 'Maschinelle Prüfung' }))); return afterDecision(); }
    if (v.wikidata === 'none') { commit('Maschine: keine Normdaten', () => setEnt(t, e, { d: 'n', note: 'Maschinelle Prüfung' })); return afterDecision(); }
  }
  if (t === 'place') {
    const c = v.candidate;
    if (v.verdict === 'ok' && e.e[1] != null) { commit('Maschine: Lage bestätigt', () => setEnt(t, e, Object.assign({}, entDec(t, e) || {}, { d: 'y', note: 'Maschinelle Prüfung' }))); return afterDecision(); }
    if ((v.verdict === 'wrong' || v.verdict === 'unlocated_ok') && c) return setPlaceFix(e, +c.lat, +c.lon, { note: 'Maschinelle Prüfung: ' + (c.display_name || ''), uncertainty_m: v.uncertainty_m || 1000, qid: c.wikidata || '', osm: c.osm || '' });
    if (v.verdict === 'not_a_place') { for (const nm of e.names) if (!nameDec(t, nm)) commit('Maschine: kein Ort', () => setName(t, nm, { d: 'n', reason: 'kein Ort (Maschinelle Prüfung)' })); return afterDecision(); }
  }
}
function mergeInto(t, e, y) {
  if (t === 'taxon' && y.e[2]) commit('zusammengeführt mit ' + y.label, () => setEnt(t, e, { d: 'r', target: targetOf(t, y) }));
  else if (t === 'habitat' && y.e[1]) commit('zusammengeführt mit ' + y.label, () => setEnt(t, e, { d: 'r', target: entTarget(t, y) }));
  else commit('zusammengeführt mit ' + y.label, () => { for (const nm of e.names) if (!nameDec(t, nm)) setName(t, nm, { d: 'r', target: targetOf(t, y) }); });
  toast('Alle Namen von „' + e.label + '“ gehören jetzt zu „' + y.label + '“'); afterDecision();
}
function nameCheck(t, e, nm, incoming, checked) {
  if (incoming) commit(checked ? 'Name hierher: ' + nm.name : 'Name zurück: ' + nm.name, () => setName(t, nm, checked ? { d: 'r', target: targetOf(t, e) } : null));
  else if (checked) commit('Name bestätigt: ' + nm.name, () => setName(t, nm, { d: 'y' }));
  else commit('Name gehört nicht hierher: ' + nm.name, () => setName(t, nm, { d: 'o' }));
  afterDecision();
}
function bulkNames(t, e) {
  const open = e.names.filter(nm => !nameState(t, nm));
  if (!open.length) return toast('Keine offenen Namen');
  commit('alle offenen Namen bestätigt', () => { for (const nm of open) setName(t, nm, { d: 'y' }); });
  afterDecision();
}
function menAct(t, mi, a) {
  if (a === 'e') { const m = P[t].men[mi]; return openEditor(m[1], m[2], m[3], t, mi); }
  if (a === 'r') { if (t === 'habitat') return; return openPanel('m:' + mi, 'r', '', 'Dieser Beleg meint …'); }
  if (a === 'n') return openPanel('m:' + mi, 'not');
  const cd = S.men[t][X[t].mkey[mi]];
  commit('Beleg', () => setMen(t, mi, cd && cd.d === a ? null : { d: a }));
}
function simpleDecide(a) {
  const it = cur.sel; if (!it || a === 'r') return;
  if (cur.tab === 'eval') {
    const cd = S.ev[it.key];
    commit('Stichprobe', () => { if (cd && cd.d === a) delete S.ev[it.key]; else S.ev[it.key] = stampObj({ d: a, cls: P.taxon.forms[P.taxon.men[it.mi][0]][3], note: (cd || {}).note || '' }); });
    if (a === 'n' && (S.ev[it.key] || {}).d === 'n') return openPanel('ev', 'r', '', 'Richtige Art (optional; Esc = überspringen)');
    return afterDecision();
  }
  if (cur.tab === 'qa') {
    const cd = S.qa[it.key];
    commit('Hinweis', () => { if (cd && cd.d === a) delete S.qa[it.key]; else S.qa[it.key] = stampObj(Object.assign({}, cd || {}, { d: a })); });
    afterDecision();
  }
}

// ---------------------------------------------------------------- readings task
function setWord(t, mi, word, note) {   // replace the written word of a mention in the entry text (a text correction hunk)
  const m = P[t].men[mi]; const ei = m[1]; const text = E[ei][7]; if (m[2] < 0) return false;
  const old = text.slice(m[2], m[3]); let rd = String(word).trim(); if (!/[.,;:]$/.test(old)) rd = rd.replace(/[.,;:]+$/, '');
  if (!rd || letters(rd) === letters(old) || (t === 'taxon' && wordInText(rd, mi))) return false;
  const hs = readingFor(ei).map(h => ({ old: h.old, new: h.new, note: h.note, men: h.men }));
  const edited = applyReadings(text, hs);
  let pos = m[2];
  if (hs.length) { const shift = applyReadings(text.slice(0, m[2]), hs.filter(h => text.indexOf(h.old) + h.old.length <= m[2])).length - m[2]; pos = m[2] + shift; if (edited.slice(pos, pos + old.length) !== old) pos = edited.indexOf(old); }
  if (pos < 0) return false;
  const next = edited.slice(0, pos) + rd + edited.slice(pos + old.length);
  const nh = diffHunks(text, next).map(h => { const prev = hs.find(x => x.old === h.old); return Object.assign(h, { note: (prev || {}).note || note, men: prev ? prev.men : X[t].mkey[mi] }); });
  setReadings(ei, nh, note, 'reading'); return true;
}
// the written name is a transcription error everywhere: re-read every located mention, then follow the corrected word
function saveNameWord(t, fi) {
  const nm = X[t].names[fi]; const w = $('#nwordfix'); if (!w) return; const word = w.value.trim(); if (!word) return toast('Bitte das Wort eintragen, wie es im Scan steht');
  if (letters(word) === letters(nm.name)) return toast('Das ist dieselbe Schreibung');
  const known = t === 'taxon' ? (X.taxon.byKey.get(lc(word)) || []).map(n => ENT('taxon', n.ent)).find(e => e.e[2]) : (X[t].byKey.get(lc(word)) || []).map(n => ENT(t, n.ent))[0];
  let n = 0;
  commit('Name überall gelesen als „' + word + '“', () => {
    for (const mi of nm.men) if (setWord(t, mi, word, 'Name „' + nm.name + '“ überall gelesen als „' + word + '“')) n++;
    if (known) setName(t, nm, known.i === nm.ent ? { d: 'y', note: 'Lesung korrigiert: ' + word } : { d: 'r', target: targetOf(t, known), note: 'Lesung korrigiert: ' + word });
  });
  ui.nword = null;
  toast(n + ' Belege werden als „' + word + '“ gelesen' + (known ? ' → ' + known.label : ' — Eintrag noch zuordnen'));
  if (!known) openPanel('n:' + fi, 'r', word, 'Wozu gehört „' + word + '“?'); else afterDecision();
}
function applyReading(mi, r) {
  const m = P.taxon.men[mi]; const curEnt = P.taxon.forms[m[0]][2]; const note = MODEL_DE[r.src] + ' gelesen, am Scan geprüft';
  commit('Lesung übernommen', () => {
    if (!r.same && r.word) setWord('taxon', mi, r.word, note);
    if (r.kind === 'bird') {
      if (r.target >= 0) { const te = P.taxon.ent[r.target]; setMen('taxon', mi, r.target === curEnt ? { d: 'y', note } : { d: 'r', target: { label: te[0], sci: te[1], key: te[2], rank: te[3] }, note }); }
      else if (r.sci || r.species) setMen('taxon', mi, { d: 'r', target: { label: r.species || r.word, sci: r.sci || '' }, note: note + ' (Art nicht im Graph)' });
      else setMen('taxon', mi, { d: 'y', note });
    } else setMen('taxon', mi, { d: 'n', reason: { place: 'place', person: 'person', other_animal: 'non-bird' }[r.kind] || 'misread', note });
  });
  afterDecision();
}
function readAct(a) {
  const it = cur.sel; if (!it) return; const mi = it.mi; const m = P.taxon.men[mi]; const cd = S.men.taxon[it.key] || {};
  if (a === '') { commit('zurückgesetzt', () => { setMen('taxon', mi, null); const rd = menReading('taxon', mi); if (rd) setReadings(m[1], readingFor(m[1]).filter(h => h !== rd), '', 'editor'); }); ui.word = null; return; }
  if (a === 'y') { commit('Transkription stimmt', () => { setMen('taxon', mi, cd.d === 'y' ? null : { d: 'y', note: 'am Scan geprüft' }); const rd = menReading('taxon', mi); if (rd && cd.d !== 'y') setReadings(m[1], readingFor(m[1]).filter(h => h !== rd), '', 'editor'); }); return afterDecision(); }
  if (a === 'u') { commit('unsicher', () => setMen('taxon', mi, cd.d === 'u' ? null : { d: 'u' })); return afterDecision(); }
  if (a === 'e') { ui.word = ui.word == null ? writtenOf(mi) : null; ui.panel = null; renderWork(false); const w = $('#wordfix'); if (w) { w.focus(); w.select(); } return; }
  if (a === 'r') return openPanel('m:' + mi, 'r', '', 'Welche Art ist an dieser Stelle gemeint?');
  if (a === 'n') return openPanel('m:' + mi, 'not');
}
function saveWord() {
  const it = cur.sel; const mi = it.mi; const w = $('#wordfix'); if (!w) return; const word = w.value.trim(); if (!word) return toast('Bitte das Wort eintragen, wie es im Scan steht');
  const m = P.taxon.men[mi]; const curEnt = P.taxon.forms[m[0]][2];
  const known = (X.taxon.byKey.get(lc(word)) || []).map(nm => ENT('taxon', nm.ent)).find(e => e.e[2]);
  commit('Lesung: ' + word, () => { setWord('taxon', mi, word, 'von Hand gelesen'); if (known) setMen('taxon', mi, known.i === curEnt ? { d: 'y', note: 'Lesung korrigiert' } : { d: 'r', target: targetOf('taxon', known), note: 'Lesung korrigiert' }); });
  ui.word = null;
  if (known) { toast('„' + word + '“ ist im Graph ' + known.label); afterDecision(); } else openPanel('m:' + mi, 'r', word, 'Welche Art ist „' + word + '“?');
}

// ---------------------------------------------------------------- persons and places
async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }
async function wdClaims(qid) { try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims|labels|descriptions&languages=de|en&ids=' + qid); return (j.entities || {})[qid] || {}; } catch (e) { return {}; } }
function claimValue(ent, p) { const c = ((ent.claims || {})[p] || [])[0]; return c && c.mainsnak && c.mainsnak.datavalue ? c.mainsnak.datavalue.value : null; }
const gndId = v => { const m = String(v || '').match(/(?:d-nb\.info\/gnd\/)?([0-9]+-[0-9X]|[0-9]{1,10}[0-9X])\b/); return m ? m[1] : ''; };
function pickPerson(e, qid, extra) {
  const cands = new Map(); for (const nm of e.names) for (const c of nm.f[5] || []) cands.set(c[0], c); const c = cands.get(qid) || [];
  const prev = entDec('person', e) || {};
  commit('Normdaten gewählt: ' + qid, () => setEnt('person', e, Object.assign({}, prev, { d: 'y', qid, wd_label: c[1] || '', wd_description: c[2] || '' }, extra || {})));
  if (!(entDec('person', e) || {}).gnd) wdClaims(qid).then(cl => { const g = claimValue(cl, 'P227'); const d = entDec('person', e) || {}; if (!g || d.gnd || d.qid !== qid) return;
    S.ent.person[e.label] = stampObj(Object.assign({}, d, { gnd: g, gnd_label: g, gnd_info: 'aus Wikidata übernommen' })); save(); if (cur.sel === e) refresh(); toast('GND aus Wikidata übernommen'); });
  afterDecision();
}
async function wikidataSearch(e, q) {
  const box = $('#wres'); box.innerHTML = '<div class="r muted">suche …</div>';
  try { const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&origin=*&language=de&uselang=de&type=item&limit=12&search=' + encodeURIComponent(q)); const res = j.search || [];
    box.innerHTML = res.length ? res.map(x => '<div class="r" data-q="' + esc(x.id) + '" data-l="' + esc(x.label || '') + '" data-dd="' + esc(x.description || '') + '"><b>' + esc(x.label || x.id) + '</b> <small>' + esc(x.id) + '</small><span data-wdx="' + esc(x.id) + '"></span><br><small>' + esc(x.description || '') + '</small></div>').join('') : '<div class="r muted">Keine Treffer.</div>';
    $$('.r[data-q]', box).forEach(el => el.onclick = () => pickPerson(e, el.dataset.q, { wd_label: el.dataset.l, wd_description: el.dataset.dd }));
    enrichCands();
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
  $$('.r[data-k]', box).forEach(el => el.onclick = () => { const x = res[+el.dataset.k]; commit('GND gewählt', () => { const prev = entDec('person', e) || {}; setEnt('person', e, Object.assign({}, prev, { d: 'y', gnd: x.id, gnd_label: x.name, gnd_info: x.info }, x.qid && !prev.qid ? { qid: x.qid, wd_label: x.name, wd_description: x.info } : {})); }); afterDecision(); });
}
// Wikidata candidates: life dates and GND number next to each candidate
const WDX = new Map();
async function enrichCands() {
  const els = $$('#work [data-wdx]'); const need = [...new Set(els.map(el => el.dataset.wdx))].filter(q => !WDX.has(q));
  if (need.length) { try { const ents = (await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&props=claims&ids=' + need.slice(0, 40).join('|'))).entities || {};
    for (const q of need) { const en = ents[q] || {}; const yr = pp => { const v = claimValue(en, pp); return v && v.time ? v.time.slice(1, 5) : ''; }; const life = [yr('P569'), yr('P570')].filter(Boolean).join('–'); const g = claimValue(en, 'P227'); WDX.set(q, [life ? life : '', g ? 'GND ' + g : ''].filter(Boolean)); } } catch (err) { return; } }
  for (const el of $$('#work [data-wdx]')) { const v = WDX.get(el.dataset.wdx); if (v && v.length) el.textContent = ' · ' + v.join(' · '); }
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
  afterDecision();
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

// ---------------------------------------------------------------- readings editor (whole entry text)
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
  hunks.forEach((h, k) => S.text.push(stampObj({ id: e[1] + ':' + Date.now().toString(36) + k, entry_uid: e[1], entry_id: e[0], old: h.old, new: h.new, note: h.note != null ? h.note : (note || ''), src: src || 'editor', men: h.men || '' })));
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

// ---------------------------------------------------------------- wiring of the work area
function wireWork() {
  const W = $('#work'); const e = cur.sel;
  const adv = $('#adv'); if (adv) adv.onchange = () => { S.ui.adv = adv.checked; save(); };
  const fol = $('#follow'); if (fol) fol.onchange = () => { S.ui.follow = fol.checked; save(); };
  $$('.rpanel', W).forEach(root => { const q = root.querySelector('.rq'); q.oninput = () => renderLocalResults(root); const g = root.querySelector('.rgbif'); if (g) g.onclick = () => gbifSearch(root); const mt = root.querySelector('.rmatch'); if (mt) mt.onchange = () => renderLocalResults(root); });
  const bulk = $('#bulk'); if (bulk) bulk.onclick = () => bulkNames(cur.type, e);
  const wf = $('#wordfix'); if (wf) wf.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); saveWord(); } if (ev.key === 'Escape') { ui.word = null; renderWork(false); } };
  const ws = $('#wordsave'); if (ws) ws.onclick = saveWord;
  const nwf = $('#nwordfix'); if (nwf) { const t2 = nwf.dataset.t, fi = +nwf.dataset.fi; nwf.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); saveNameWord(t2, fi); } if (ev.key === 'Escape') { ui.nword = null; renderWork(false); } }; $('#nwordsave').onclick = () => saveNameWord(t2, fi); }
  if ($('#wq')) {
    $$('.cand[data-qid]', W).forEach(c => c.onclick = ev => { if (ev.target.closest('a')) return; pickPerson(e, c.dataset.qid); });
    $('#wbtn').onclick = () => wikidataSearch(e, $('#wq').value); $('#wq').onkeydown = ev => { if (ev.key === 'Enter') wikidataSearch(e, $('#wq').value); };
    $('#gndbtn').onclick = () => gndSearch(e, $('#wq').value);
    $('#wqidbtn').onclick = () => { const q = ($('#wqid').value.match(/Q\d+/i) || [''])[0].toUpperCase(); if (!q) return toast('Ungültige QID'); pickPerson(e, q, { wd_label: q, wd_description: 'von Hand eingetragen' }); };
    $('#gndidbtn').onclick = () => { const g = gndId($('#gndid').value); if (!g) return toast('Ungültige GND-ID'); commit('GND', () => setEnt('person', e, Object.assign({}, entDec('person', e) || {}, { d: 'y', gnd: g, gnd_label: g, gnd_info: 'von Hand eingetragen' }))); };
    enrichCands();
    const gc = $('#gndclear'); if (gc) gc.onclick = () => commit('GND entfernt', () => { const d = Object.assign({}, entDec('person', e) || {}); d.gnd = null; d.gnd_label = null; d.gnd_info = null; if (!d.d) d.d = d.qid || e.e[1] ? 'y' : 'n'; if (!d.qid && d.d === 'y') d.qid = e.e[1] || null; setEnt('person', e, d); });
  }
  if ($('#nq')) {
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
$('#work').addEventListener('change', ev => {
  const cb = ev.target.closest('.nm .cb'); if (!cb) return;
  const row = cb.closest('.nm'); const t = cur.type; nameCheck(t, cur.sel, X[t].names[+row.dataset.fi], row.dataset.inc === '1', cb.checked);
});
$('#work').addEventListener('click', ev => {
  const t0 = ev.target; const t = cur.type;
  const nav = t0.closest('[data-nav]'); if (nav) return nextItem(+nav.dataset.nav);
  const ea = t0.closest('[data-ea]'); if (ea) return entAct(t, cur.sel, ea.dataset.ea);
  const ra = t0.closest('[data-ra]'); if (ra) return readAct(ra.dataset.ra);
  const ac = t0.closest('[data-accept]'); if (ac) return applyReading(cur.sel.mi, cur.sel.rs[+ac.dataset.accept]);
  const gr = t0.closest('[data-grp]'); if (gr) { const e = cur.sel; if (gr.dataset.grp === '') return commit('zurückgesetzt', () => setGrp(t, e, null)); commit('Namensgruppe bestätigt: ' + e.label, () => setGrp(t, e, { d: 'y' })); return afterDecision(); }
  const sa = t0.closest('[data-sa]'); if (sa) return simpleDecide(sa.dataset.sa);
  const sp = t0.closest('[data-special]'); if (sp) { const root = sp.closest('.rpanel'); return special(root.dataset.kind, root.dataset.scope, sp.dataset.special); }
  const rs = t0.closest('[data-reason]'); if (rs) { const root = rs.closest('[data-scope]'); return reason(TAB[cur.tab].typed ? t : 'taxon', root.dataset.scope, rs.dataset.reason); }
  const mg = t0.closest('[data-merge]'); if (mg) return mergeInto(t, cur.sel, X[t].ents[+mg.dataset.merge]);
  const eu = t0.closest('[data-eunis]'); if (eu) { const code = eu.dataset.eunis; return commit('EUNIS-Klasse übernommen', () => setEnt('habitat', cur.sel, { d: 'r', target: { code, label: code + ' ' + ((EUNIS.get(code) || [])[1] || ''), match: eu.dataset.match || 'close' } })); }
  const mva = t0.closest('[data-mvaccept]'); if (mva) return mvAccept(mva.dataset.mvaccept, cur.sel);
  const sll = t0.closest('[data-setll]'); if (sll) { const [la, lo, g, q] = sll.dataset.setll.split(','); return setPlaceFix(cur.sel, +la, +lo, { note: 'Gazetteer-Vorschlag', uncertainty_m: 2000, geonames_id: g || '', qid: q || '' }); }
  const rd = t0.closest('[data-read]'); if (rd) return openTab('read', X.taxon.mkey[+rd.dataset.read]);
  const tg = t0.closest('[data-toggle]'); if (tg) { const fi = +tg.dataset.toggle; ui.open.has(fi) ? ui.open.delete(fi) : ui.open.add(fi); return renderWork(false); }
  const nt = t0.closest('[data-nameto]'); if (nt) { const nm = X.taxon.names[+nt.dataset.fi]; const y = ENT('taxon', +nt.dataset.nameto); commit('Name „' + nm.name + '“ → ' + y.label, () => setName('taxon', nm, { d: 'r', target: targetOf('taxon', y), note: 'Lesung der Modelle' })); return afterDecision(); }
  const nc = t0.closest('[data-nclear]'); if (nc) { const nm = X.taxon.names[+nc.dataset.nclear]; return commit('zurückgesetzt', () => setName('taxon', nm, null)); }
  const nw = t0.closest('[data-nread]'); if (nw) { ui.nword = +nw.dataset.nread; ui.panel = null; renderWork(false); const w = $('#nwordfix'); if (w) { w.focus(); w.select(); } return; }
  const nr = t0.closest('[data-nreassign]'); if (nr) { const tt = nr.dataset.t || t; return openPanel('n:' + nr.dataset.nreassign, 'r', '', 'Zu welchem Eintrag gehört „' + X[tt].names[+nr.dataset.nreassign].name + '“?'); }
  const nn = t0.closest('[data-nnot]'); if (nn) return openPanel('n:' + nn.dataset.nnot, 'not');
  const am = t0.closest('[data-allmen]'); if (am) { ui.all.add(+am.dataset.allmen); return renderWork(false); }
  const fu = t0.closest('[data-full]'); if (fu) { const card = fu.closest('.men'); const k = (card ? card.dataset.t : 'taxon') + fu.dataset.full; ui.full.has(k) ? ui.full.delete(k) : ui.full.add(k); return renderWork(false); }
  const mc = t0.closest('[data-mclear]'); if (mc) { const card = mc.closest('.men'); return commit('zurückgesetzt', () => setMen(card.dataset.t, +card.dataset.mi, null)); }
  const ed = t0.closest('[data-edit]'); if (ed) return openEditor(+ed.dataset.edit, +ed.dataset.s, +ed.dataset.e);
  const se = t0.closest('[data-scanentry]'); if (se) return showScan(+se.dataset.scanentry);
  const ma = t0.closest('[data-ma]'); if (ma) { const card = ma.closest('.men'); return menAct(card.dataset.t, +card.dataset.mi, ma.dataset.ma); }
  const sn = t0.closest('.snip'); if (sn) { const card = sn.closest('.men'); if (card && card.dataset.mi) return scanFor(card.dataset.t, +card.dataset.mi); if (cur.tab === 'read' || cur.tab === 'eval') return scanFor('taxon', cur.sel.mi); }
  const nh = t0.closest('.nh'); if (nh && !t0.closest('button') && !t0.closest('a') && !t0.closest('input')) { const fi = +nh.closest('.nm').dataset.fi; ui.open.has(fi) ? ui.open.delete(fi) : ui.open.add(fi); return renderWork(false); }
});
document.addEventListener('keydown', ev => {
  if (panelKeys(ev)) return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (ev.key === 'Escape') { if ($('#ovModal').classList.contains('show')) return closeModal(); if (ui.panel) { ui.panel = null; renderWork(false); if (cur.tab === 'eval') afterDecision(); return; } if (ui.word != null || ui.nword != null) { ui.word = null; ui.nword = null; renderWork(false); return; } if (tag === 'input' || tag === 'textarea') ev.target.blur(); return; }
  if ((ev.ctrlKey || ev.metaKey) && lc(ev.key) === 'k') { ev.preventDefault(); return openSearch(); }
  if ((ev.ctrlKey || ev.metaKey) && lc(ev.key) === 'z' && tag !== 'input' && tag !== 'textarea') { ev.preventDefault(); return undo(); }
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if ($('#ovModal').classList.contains('show')) return;
  const k = ev.key; const kl = lc(k); const typed = TAB[cur.tab].typed;
  if (ui.panel && ui.panel.kind === 'not' && /^[1-9]$/.test(k)) { const t = typed ? cur.type : 'taxon'; const opt = TT[t].not[+k - 1]; if (opt) { ev.preventDefault(); return reason(t, ui.panel.scope, opt[0]); } }
  if (k === 'ArrowLeft' || k === 'ArrowRight') { if (scan.p >= 0) { ev.preventDefault(); (k === 'ArrowLeft' ? $('#scanprev') : $('#scannext')).click(); } return; }
  if (k === 'Enter') { ev.preventDefault(); return nextItem(ev.shiftKey ? -1 : 1); }
  if (k === 'ArrowDown' || k === 'ArrowUp') { ev.preventDefault(); return nextItem(k === 'ArrowDown' ? 1 : -1); }
  if (ev.shiftKey && /^[A-E]$/.test(k) && typed) { const c = $$('#work .cand[data-merge]')[k.charCodeAt(0) - 65]; if (c) { ev.preventDefault(); c.click(); } return; }
  if (['y', 'a', 'n', 'u', 'e', 'z', 'b'].includes(kl)) ev.preventDefault();
  if (kl === 'z') return undo();
  if (kl === 'b') { const hide = !$('#main').classList.contains('noscan'); if (cur.tab === 'names') S.ui.scanNames = !hide; else S.ui.noscan = hide; $('#main').classList.toggle('noscan', hide); save(); return; }
  if (k === '/') { ev.preventDefault(); return $('#qsearch').focus(); }
  if (k === '?') return showHelp();
  if (!cur.sel) return;
  if (cur.tab === 'read') { if (/^[1-9]$/.test(k)) { const b = $('#work [data-accept="' + (+k - 1) + '"]'); if (b) b.click(); return; } if (['y', 'a', 'n', 'u', 'e'].includes(kl)) return readAct({ y: 'y', a: 'r', n: 'n', u: 'u', e: 'e' }[kl]); return; }
  if (cur.tab === 'eval' || cur.tab === 'qa') { if (['y', 'n', 'u'].includes(kl)) return simpleDecide(kl); if (kl === 'e') { const q = $('#work [data-edit], #work .men [data-ma="e"]'); if (q) q.click(); } return; }
  if (cur.tab === 'names') { if (kl === 'y') { const b = $('#work [data-grp="y"]'); if (b) b.click(); } return; }
  if (typed) {
    if (/^[1-9]$/.test(k) && cur.type === 'person') { const c = $$('#work .cand[data-qid]')[+k - 1]; if (c) c.click(); return; }
    if (['y', 'a', 'n', 'u'].includes(kl)) return entAct(cur.type, cur.sel, { y: 'y', a: 'r', n: 'n', u: 'u' }[kl]);
    if (kl === 'e') { const q = $('#work .men [data-ma="e"]'); if (q) q.click(); }
  }
});
