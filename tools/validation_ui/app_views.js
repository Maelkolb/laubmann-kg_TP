// Laubmann-Abgleich v4 — part 3: task views and decisions.
let map = null;
function renderWork(fresh) {
  if (map) { try { ui.mapView = [map.getCenter(), map.getZoom()]; } catch (e) { ui.mapView = null; } map.remove(); map = null; }
  const w = $('#work'); const scrollTop = w.scrollTop;
  const it = cur.sel; if (!it) { w.innerHTML = '<div class="empty">Nichts ausgewählt.</div>'; return; }
  let h;
  if (cur.tab === 'check' || cur.tab === 'link') h = entityView(cur.type, it, cur.tab);
  else if (cur.tab === 'names') h = namesView(cur.type, it);
  else if (cur.tab === 'read') h = readView(it);
  else if (cur.tab === 'eval') h = evalView(it);
  else if (cur.tab === 'qa') h = qaView(it);
  else return;
  w.innerHTML = '<div class="wrap">' + h + kbdRow() + '</div>';
  w.scrollTop = fresh ? 0 : scrollTop;
  wireWork(); wireSnips(w);
  if (fresh && S.ui.follow) {
    if (cur.tab === 'read' || cur.tab === 'eval') scanFor('taxon', it.mi);
    else if (cur.tab === 'qa') { if (it.ei >= 0) showScan(it.ei); }
    else { const nm = it.names.find(n => n.men.length); if (nm) scanFor(cur.type, nm.men[0]); }
  }
  if (ui.panel) { const r = $('#work .rpanel[data-scope="' + ui.panel.scope + '"] .rq'); if (r && document.activeElement !== r) { r.focus(); if (r.value) renderLocalResults(r.closest('.rpanel')); } }
}
function kbdRow() {
  const k = TAB[cur.tab].typed ? '<kbd>Y</kbd> stimmt · <kbd>A</kbd> anders … · <kbd>N</kbd> keine/nicht bestimmbar · <kbd>U</kbd> unsicher · <kbd>⏎</kbd> nächster · <kbd>Z</kbd> rückgängig · <kbd>←</kbd>/<kbd>→</kbd> Seiten im Scan'
    : cur.tab === 'read' ? '<kbd>Y</kbd> Transkription stimmt · <kbd>1</kbd>/<kbd>2</kbd> Lesung übernehmen · <kbd>E</kbd> selbst korrigieren · <kbd>A</kbd> andere Art · <kbd>N</kbd> kein Vogel · <kbd>U</kbd> unsicher · <kbd>⏎</kbd> nächster · <kbd>Z</kbd> rückgängig'
    : '<kbd>Y</kbd> richtig · <kbd>N</kbd> falsch · <kbd>U</kbd> unsicher · <kbd>E</kbd> Lesung · <kbd>⏎</kbd> nächster · <kbd>Z</kbd> rückgängig';
  return '<div class="kbdrow">' + k + ' · <label><input type="checkbox" id="adv"' + (S.ui.adv ? ' checked' : '') + '> automatisch weiter</label> · <label><input type="checkbox" id="follow"' + (S.ui.follow ? ' checked' : '') + '> Scan folgt der Auswahl</label></div>';
}
function crumb() {
  return '<div class="crumb"><span>' + esc(TASK_TEXT[cur.tab][0]) + (TAB[cur.tab].typed ? ' · ' + esc(TT[cur.type].tab) : '') + (cur.pos >= 0 ? ' · ' + fmt(cur.pos + 1) + ' von ' + fmt(cur.list.length) : '') + '</span>'
    + '<span class="nav"><button class="nbtn" data-nav="-1">↑ vorheriger</button><button class="nbtn primary" data-nav="1">nächster offener ⏎</button></span></div>';
}
const stateLine = (d, text) => d && d.d ? '<div class="state ' + ({ y: 'y', r: 'r', n: 'n', u: 'u' }[d.d] || 'r') + '">' + text + (d.by ? ' <span class="muted small">· ' + esc(d.by) + ', ' + new Date(d.t).toLocaleString('de-DE') + '</span>' : '') + '</div>' : '';

// ---------------------------------------------------------------- authority record
function authBlock(t, e, tab) {
  const x = e.e; const a = entDec(t, e) || {};
  if (t === 'taxon') {
    const llm = e.names.map(nm => nm.f[5]).find(Boolean);
    return '<div class="auth"><div class="ah">GBIF</div>' + (x[2] ? '<a href="https://www.gbif.org/species/' + esc(x[2]) + '" target="_blank" rel="noopener"><i>' + esc(x[1] || x[2]) + '</i> ↗</a> <span class="muted small">' + esc(x[3] || '') + (x[4] ? ' · ' + esc(x[4]) : '') + (x[6] ? ' · ' + esc(x[6]) : '') + (x[7] ? ' · ' + esc(x[7]) : '') + '</span>' + (x[4] === 'HIGHERRANK' ? ' <span class="bd warn">nur übergeordnete Ebene</span>' : '')
      + (x[9].length ? '<div class="small muted" style="margin-top:4px">Deutsche Namen laut GBIF/Wikidata: ' + x[9].slice(0, 16).map(esc).join(', ') + (x[9].length > 16 ? ' …' : '') + '</div>' : '')
      : '<span class="bd warn">keine Art zugeordnet</span>' + (llm ? ' · Modell schlug <i>' + esc(llm) + '</i> vor' : '')) + '</div>';
  }
  if (t === 'person') return personAuth(e, tab);
  if (t === 'place') return placeAuth(e, tab);
  const ex = EUNIS.get(x[1]); const lr = e.names.length ? e.names[0].f[5] || [] : [];
  return '<div class="auth"><div class="ah">EUNIS</div>' + (x[1] ? '<b>' + esc(x[1]) + '</b> ' + esc((ex || [])[1] || lr[4] || '') + ' <span class="muted small">(' + esc(x[2]) + (lr[1] ? ', Konfidenz ' + esc(lr[1]) : '') + ')</span> · <a href="https://biodiversity.europa.eu/resources/search-habitat/eunis-habitat-types-hierarchical-view-2012?searchTerm=' + encodeURIComponent(x[1]) + '" target="_blank" rel="noopener">BISE ↗</a>' + (ex && ex[3] ? '<div class="small muted">übergeordnet: ' + esc(ex[3]) + ' ' + esc((EUNIS.get(ex[3]) || [])[1] || '') + '</div>' : '') + (lr[2] ? '<div class="small muted">Begründung Modell: ' + esc(lr[2]) + '</div>' : '')
    : '<span class="bd warn">keine Klasse</span>' + (lr[3] ? ' · Vorschlag ' + esc(lr[3]) + ' ' + esc(lr[4]) + ' <button class="btn sm" data-eunis="' + esc(lr[3]) + '" data-match="' + esc(lr[5] || 'close') + '">übernehmen</button>' : '')) + '</div>';
}
function personAuth(e, tab) {
  const x = e.e, a = entDec('person', e) || {}; const pm = PM[e.i];
  const cands = new Map(); for (const nm of e.names) for (const c of nm.f[5] || []) if (!cands.has(c[0])) cands.set(c[0], c);
  if (x[1] && !cands.has(x[1])) cands.set(x[1], [x[1], 'im Graph verknüpft', '']);
  if (a.qid && !cands.has(a.qid)) cands.set(a.qid, [a.qid, a.wd_label || a.qid, a.wd_description || 'selbst gesucht']);
  const model = pm && /^Q\d+$/.test(pm[0]) ? pm[0] : null;
  const chosen = a.d === 'y' ? a.qid : a.d ? null : (model || x[1]);
  let list = [...cands.values()].map((c, k) => '<div class="cand' + (chosen === c[0] ? ' on' : '') + '" data-qid="' + esc(c[0]) + '"><span class="k">' + (k < 9 ? k + 1 : '') + '</span><div><div class="cl">' + esc(c[1]) + (c[0] === x[1] ? ' <span class="bd info">automatisch verknüpft</span>' : '') + (c[0] === model ? ' <span class="bd tip">Vorschlag des Modells</span>' : '') + '</div><div class="cd">' + esc(c[2] || 'keine Beschreibung') + '<span data-wdx="' + esc(c[0]) + '"></span></div></div><a class="ci" href="https://www.wikidata.org/wiki/' + esc(c[0]) + '" target="_blank" rel="noopener">' + esc(c[0]) + ' ↗</a></div>').join('');
  const gnd = a.gnd || (!a.d && x[2]) || '';
  return '<div class="auth"><div class="ah">Wikidata / GND</div><div class="cands">' + (list || '<div class="muted small">Keine Wikidata-Kandidaten. Unten suchen oder ✗ „Keine Normdaten“.</div>') + '</div>'
    + (pm ? '<div class="modelbox"><b>Modell (Claude Opus 5.5)</b>: ' + (pm[0] === 'none' ? 'keiner der Kandidaten passt' : pm[0] === 'unclear' ? 'nicht entscheidbar' : 'Kandidat ' + esc(pm[0])) + ' · ' + Math.round(100 * pm[1]) + ' % — ' + esc(pm[2]) + '</div>' : '')
    + '<div class="row" style="margin-top:8px"><span class="small muted">GND:</span>' + (gnd ? '<a href="https://d-nb.info/gnd/' + esc(gnd) + '" target="_blank" rel="noopener">' + esc(a.gnd_label && a.gnd_label !== gnd ? a.gnd_label + ' · ' : '') + esc(gnd) + ' ↗</a> <span class="muted small">' + esc(a.gnd_info || (a.gnd ? '' : 'im Graph')) + '</span> <button class="lbtn" id="gndclear">entfernen</button>' : '<span class="small muted">noch keine</span>') + '</div>'
    + '<div class="panel"><h5>Suchen</h5><div class="row"><input type="text" class="grow ftext" id="wq" value="' + esc(e.label.replace(/^(Prof\.|Dr\.|Herr|Frau|Frl\.|Lehrer|Pfarrer|Oberförster|Förster)\s+/g, '')) + '"><button class="lbtn" id="wbtn">Wikidata</button><button class="lbtn" id="gndbtn">GND</button></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" class="ftext" id="wqid" placeholder="QID, z. B. Q12345" style="width:160px"><button class="lbtn" id="wqidbtn">übernehmen</button><input type="text" class="ftext" id="gndid" placeholder="GND-ID oder d-nb.info-Link" style="width:210px"><button class="lbtn" id="gndidbtn">übernehmen</button></div><div id="wres" class="res"></div></div></div>';
}
function placeAuth(e, tab) {
  const x = e.e, a = entDec('place', e) || {}, fix = a.fix; const lr = ((e.names.find(nm => isLabel('place', nm)) || e.names[0]).f[5]) || [];
  return '<div class="auth"><div class="ah">Lage · GeoNames / Wikidata</div><dl class="facts" style="margin:0">' + (x[1] != null ? '<dt>Im Graph</dt><dd>' + x[1] + ', ' + x[2] + (x[3] ? ' (± ' + fmt(x[3]) + ' m)' : '') + (x[7] ? ' <span class="muted small">· ' + esc(x[7]) + '</span>' : '') + '</dd>' : '<dt>Im Graph</dt><dd><span class="bd warn">keine Koordinate</span>' + (lr[4] && lr[5] ? ' · Gazetteer-Vorschlag ' + esc(lr[7] || '') + ' ' + esc(lr[4]) + ', ' + esc(lr[5]) + (lr[8] ? ' (' + esc(lr[8]) + ')' : '') + ' <button class="btn sm" data-setll="' + esc(lr[4]) + ',' + esc(lr[5]) + ',' + esc(lr[6] || '') + ',' + esc(lr[9] || '') + '">übernehmen</button>' : '') + '</dd>')
    + (x[4] ? '<dt>GeoNames</dt><dd><a href="https://www.geonames.org/' + esc(x[4]) + '" target="_blank" rel="noopener">' + esc(lr[7] || x[4]) + ' ↗</a>' + (lr[11] ? ' · ' + esc(lr[11]) : '') + (lr[8] ? ' · ' + esc(lr[8]) : '') + '</dd>' : '')
    + (x[5] ? '<dt>Wikidata</dt><dd><a href="https://www.wikidata.org/wiki/' + esc(x[5]) + '" target="_blank" rel="noopener">' + esc(x[5]) + ' ↗</a></dd>' : '') + (lr[3] ? '<dt>Hinweis</dt><dd class="small">' + esc(lr[3]) + '</dd>' : '')
    + (fix ? '<dt>Korrektur</dt><dd>' + (fix.lat ? fix.lat + ', ' + fix.lon + ' (± ' + fmt(fix.uncertainty_m) + ' m)' : 'Koordinaten wie im Graph') + (fix.geonames_id ? ' · GeoNames ' + esc(fix.geonames_id) : '') + (fix.qid ? ' · ' + esc(fix.qid) : '') + (fix.note ? ' · <span class="small">' + esc(fix.note) + '</span>' : '') + ' <button class="lbtn" id="unfix">verwerfen</button></dd>' : '') + '</dl>'
    + '<div id="map"></div><div class="maplegend"><span><i style="background:#e0542e"></i>im Graph</span><span><i style="background:#1e7a4c"></i>Korrektur</span><span><i style="background:#3a6fb0;opacity:.6"></i>Orte derselben Einträge</span><span>Klick in die Karte setzt die Lage</span></div>'
    + '<div class="panel"><h5>Lage suchen</h5><div class="row"><input type="text" class="grow ftext" id="nq" value="' + esc(e.label) + '"><button class="lbtn" id="nbtn">OpenStreetMap</button><button class="lbtn" id="pwbtn">Wikidata</button><a class="lbtn" target="_blank" rel="noopener" href="https://www.geonames.org/search.html?q=' + encodeURIComponent(e.label) + '">GeoNames ↗</a></div>'
    + '<div class="row" style="margin-top:6px"><input type="text" class="ftext" id="ll" placeholder="Breite, Länge" style="width:140px"><select id="unc" class="ftext"><option value="100">± 100 m</option><option value="500">± 500 m</option><option value="1000" selected>± 1 km</option><option value="2000">± 2 km</option><option value="5000">± 5 km</option><option value="10000">± 10 km</option></select><button class="lbtn" id="llbtn">setzen</button>'
    + '<input type="text" class="ftext" id="gnid" placeholder="GeoNames-ID" style="width:120px" value="' + esc((fix && fix.geonames_id) || '') + '"><input type="text" class="ftext" id="pqid" placeholder="Wikidata-QID" style="width:110px" value="' + esc((fix && fix.qid) || '') + '"><button class="lbtn" id="idbtn">IDs übernehmen</button></div><div id="nres" class="res"></div></div></div>';
}

// ---------------------------------------------------------------- merge suggestions ("dasselbe wie")
function mergeSuggestions(t, e) {
  const votes = new Map();
  for (const nm of e.names) for (const [ent, score, why] of (CAND[t].nc[nm.fi] || [])) { const v = votes.get(ent) || { score: 0, why: new Set() }; v.score += score * Math.log(2 + nm.n); v.why.add(why); votes.set(ent, v); }
  if (t === 'taxon') { const llm = e.names.map(nm => nm.f[5]).find(Boolean); if (llm) { const y = X.taxon.ents.find(z => z.e[2] && lc(z.e[1]) === lc(llm)); if (y && y.i !== e.i) { const v = votes.get(y.i) || { score: 0, why: new Set() }; v.score += 5; v.why.add('Vorschlag des Sprachmodells'); votes.set(y.i, v); } }
    for (const nm of e.names) for (const mi of nm.men) for (const r of readingsOf(mi)) if (r.target >= 0 && r.target !== e.i) { const v = votes.get(r.target) || { score: 0, why: new Set() }; v.score += 2; v.why.add('Zweitlesung'); votes.set(r.target, v); } }
  return [...votes.entries()].map(([i, v]) => ({ ent: X[t].ents[i], score: v.score, why: [...v.why].join(', ') })).filter(c => c.ent.names.length).sort((a, b) => (linked(t, b.ent) - linked(t, a.ent)) || b.score - a.score).slice(0, 5);
}
function mergeBlock(t, e) {
  const sg = mergeSuggestions(t, e); if (!sg.length) return '';
  const what = { taxon: 'dieselbe Art wie', person: 'dieselbe Person wie', place: 'derselbe Ort wie', habitat: 'derselbe Lebensraum wie' }[t];
  return '<div class="q">Ist es dasselbe wie ein anderer Eintrag?<small>dann gehören alle Namen dorthin</small></div><div class="cands">' + sg.map((c, k) => { const y = c.ent; return '<div class="cand" data-merge="' + y.i + '"><span class="k" title="Umschalt+' + String.fromCharCode(65 + k) + '">⇧' + String.fromCharCode(65 + k) + '</span><div><div class="cl">' + esc(what) + ' „' + esc(y.label) + '“ <span class="muted">' + authText(t, y) + '</span></div><div class="cd">' + esc(c.why) + ' · ' + fmt(y.n) + ' ' + TT[t].unit + (y.names.length > 1 ? ' · Namen: ' + y.names.slice(0, 4).map(n => esc(n.name)).join(', ') + (y.names.length > 4 ? ' …' : '') : '') + '</div></div><span class="bd ' + (linked(t, y) ? 'ok' : 'plain') + '">' + (linked(t, y) ? 'verknüpft' : 'ohne Normdaten') + '</span></div>'; }).join('') + '</div>';
}

// ---------------------------------------------------------------- name group (checkbox list)
function nameRow(t, e, nm, incoming) {
  const st = nameState(t, nm); const d = nameDec(t, nm); const cls = TT[t].cls[nm.cls] || [nm.cls, 'plain', ''];
  const checked = incoming ? (d && d.d === 'r' && d.target && d.target.label === e.label) : !nameGone(st);
  let why = '';
  if (t === 'taxon') why = nm.cls === 'A' ? (nm.f[4] && lc(nm.f[4]) !== nm.key ? 'wie „' + esc(nm.f[4]) + '“' : '') : nm.cls === 'B' ? 'Variante von „' + esc(nm.f[4]) + '“' : nm.cls === 'C' ? (nm.f[4] ? 'ähnlich: „' + esc(nm.f[4]) + '“' : 'kein belegter Name dieser Art') : '';
  else if (nm.f[4] && !isLabel(t, nm)) why = 'zusammengeführt: ' + esc(RULE_DE[nm.f[4]] || nm.f[4]);
  const home = incoming ? ENT(t, nm.ent) : null;
  const cand = incoming ? (CAND[t].ec[e.i] || []).find(c => c[0] === nm.fi) : null;
  const readMen = t === 'taxon' ? nm.men.filter(mi => readingsOf(mi).some(r => r.differs)) : []; const readings = readMen.length;
  const open = ui.open.has(nm.fi);
  const stTxt = d && d.d ? '<span class="bd ' + (d.d === 'y' ? 'ok' : d.d === 'u' ? 'warn' : d.d === 'n' ? 'risk' : 'info') + '">' + decLine(t, d).replace(/<[^>]+>/g, '') + '</span>' : st === 'y' ? '<span class="bd ok">✓ bestätigt</span>' : st === 'f' ? '<span class="bd info">folgt dem Eintrag</span>' : st === 'm' ? '<span class="bd info" title="Jeder Beleg dieses Namens wurde einzeln entschieden oder neu gelesen">alle Belege einzeln entschieden</span>' : '';
  const gone = d && nameGone(d.d) && !d.target;
  const located = nm.men.some(mi => P[t].men[mi][2] >= 0);
  return '<div class="nm' + (checked ? '' : ' off') + '" data-fi="' + nm.fi + '" data-inc="' + (incoming ? 1 : 0) + '"><div class="nh"><input type="checkbox" class="cb" ' + (checked ? 'checked' : '') + ' title="' + (incoming ? 'gehört auch hierher' : 'gehört zu diesem Eintrag') + '"><div><span class="nn">' + esc(nm.name) + '</span><span class="ct">' + fmt(nm.n) + '×</span> <span class="bd ' + cls[1] + '" title="' + esc(cls[2]) + '">' + esc(cls[0]) + '</span>' + (isLabel(t, nm) && !incoming ? '<span class="bd plain">Hauptname</span>' : '') + (readings ? '<span class="bd tip" data-read="' + readMen[0] + '" style="cursor:pointer" title="Modelle lesen bei diesen Belegen etwas anderes — Klick öffnet die Aufgabe Zweitlesung">' + readings + ' Zweitlesung ↗</span>' : '') + '<span class="why">' + why + (incoming ? (cand ? 'derzeit bei „' + esc(home.label) + '“ (' + authText(t, home).replace(/<[^>]+>/g, '') + ') · ' + esc(cand[2]) : 'aus „' + esc(home.label) + '“ hierher zugeordnet') : '') + '</span> ' + stTxt + '</div>'
    + '<span class="tools">' + (!incoming && located ? '<button class="lbtn" data-nread="' + nm.fi + '" title="Der Name ist überall falsch transkribiert: alle Belege neu lesen als …">✎</button>' : '') + '<button class="lbtn" data-toggle="' + nm.fi + '">' + (open ? 'Belege ▴' : 'Belege ▾') + '</button></span></div>'
    + (gone ? '<div class="sub2"><span class="muted">gehört nicht hierher —</span><button class="lbtn" data-nreassign="' + nm.fi + '">↪ zu welchem Eintrag?</button><button class="lbtn" data-nnot="' + nm.fi + '">✗ kein(e) ' + esc(TT[t].one) + ' …</button></div>' : '')
    + (ui.nword === nm.fi ? '<div style="padding:0 10px 8px">' + nwordRow(t, nm) + '</div>' : '')
    + (ui.panel && ui.panel.scope === 'n:' + nm.fi ? '<div style="padding:0 10px 8px">' + panelHtml(t, ui.panel) + '</div>' : '')
    + (open ? '<div class="body">' + mentionsOf(t, nm).map(mi => menHtml(t, mi)).join('') + (nm.men.length > 6 && !ui.all.has(nm.fi) ? '<div class="row" style="margin-top:8px"><button class="lbtn" data-allmen="' + nm.fi + '">alle ' + fmt(nm.men.length) + ' Belege zeigen</button></div>' : '') + '</div>' : '') + '</div>';
}
function mentionsOf(t, nm) {
  const all = nm.men.map(mi => [mi, P[t].men[mi][1]]);
  const shown = ui.all.has(nm.fi) ? all.slice().sort((a, b) => (E[a[1]][2] || '').localeCompare(E[b[1]][2] || '')) : pickSpread(all, 6);
  for (const x of all) if (!shown.some(y => y[0] === x[0]) && (S.men[t][X[t].mkey[x[0]]] || (t === 'taxon' && readingsOf(x[0]).some(r => r.differs)))) shown.push(x);
  return shown.map(x => x[0]);
}
function nwordRow(t, nm) {
  const n = nm.men.filter(mi => P[t].men[mi][2] >= 0).length;
  return '<div class="wordfix"><span class="small muted">„' + esc(nm.name) + '“ überall lesen als</span><input type="text" id="nwordfix" data-t="' + t + '" data-fi="' + nm.fi + '" value="' + esc(nm.name) + '" placeholder="so steht es im Scan"><button class="btn sm y" id="nwordsave">für ' + fmt(n) + ' Belege speichern <kbd>⏎</kbd></button><span class="small muted">jeder Beleg erhält eine Lesungskorrektur; die Einträge werden neu ausgewertet</span></div>';
}
// the names of an entity: its own, the ones reassigned here from elsewhere, and candidates from similar names (same block in every task)
function namesBlock(t, e) {
  const cands = (CAND[t].ec[e.i] || []).map(([fi]) => X[t].names[fi]).filter(nm => nm.ent !== e.i);
  const here = X[t].names.filter(nm => nm.ent !== e.i && !cands.includes(nm) && (nameDec(t, nm) || {}).d === 'r' && ((nameDec(t, nm) || {}).target || {}).label === e.label);
  const inc = here.concat(cands);
  const open = e.names.filter(nm => !nameState(t, nm)).length;
  let h = '<div class="q">' + (e.names.length > 1 ? 'Gehören diese ' + e.names.length + ' Namen zu diesem Eintrag?' : 'Der Name im Tagebuch') + '<small>Haken weg = gehört nicht hierher</small>' + (open > 1 ? ' <button class="lbtn" id="bulk" style="margin-left:8px">alle ' + open + ' offenen bestätigen</button>' : '') + '</div>';
  for (const nm of e.names) h += nameRow(t, e, nm, false);
  if (inc.length) { h += '<div class="q">Gehören diese Namen auch hierher?<small>' + (cands.length ? 'Vorschläge aus ähnlichen Namen anderer Einträge — Haken setzen = zusammenführen' : 'aus anderen Einträgen hierher zugeordnet') + '</small></div>'; for (const nm of inc) h += nameRow(t, e, nm, true); }
  h += '<div class="panel rpanel" data-scope="add" data-kind="' + t + '"><h5>Weiteren Namen hinzufügen</h5><div class="row"><input type="text" class="grow rq" placeholder="geschriebenen Namen aus dem ganzen Graphen suchen …" autocomplete="off"></div><div class="res rres"></div></div>';
  return h;
}

// ---------------------------------------------------------------- entity views
function entActs(t, e, tab) {
  const cd = entDec(t, e) || {};
  const b = (k, label, key, dis) => '<button class="btn ' + k + (cd.d === k ? ' on' : '') + '" data-ea="' + k + '"' + (dis ? ' disabled title="' + esc(dis) + '"' : '') + '>' + label + ' <kbd>' + key + '</kbd></button>';
  const L = { taxon: ['Art stimmt', 'Andere Art …', 'Nicht bestimmbar'], person: ['Normdaten stimmen', 'Suchen …', 'Keine Normdaten'], place: ['Lage stimmt', 'Lage ändern …', 'Nicht bestimmbar'], habitat: ['Klasse stimmt', 'Andere Klasse …', 'Keine Klasse passt'] }[t];
  let yDis = '';
  if (t === 'taxon' && !e.e[2]) yDis = 'Keine GBIF-Art: zuerst eine Art zuordnen';
  if (t === 'habitat' && !e.e[1]) yDis = 'Keine EUNIS-Klasse';
  if (t === 'person' && !(cd.qid || cd.gnd || (!cd.d && (e.e[1] || e.e[2] || (PM[e.i] && /^Q/.test(PM[e.i][0])))))) yDis = 'Erst einen Kandidaten wählen';
  if (t === 'place' && e.e[1] == null && !(cd.fix && cd.fix.lat)) yDis = 'Keine Koordinate';
  const q = tab === 'link' ? (t === 'taxon' ? 'Welche GBIF-Art ist gemeint?' : t === 'person' ? 'Welche Person ist gemeint?' : t === 'place' ? 'Wo liegt der Ort?' : 'Welche EUNIS-Klasse passt?') : (t === 'taxon' ? 'Ist die GBIF-Art richtig?' : t === 'person' ? 'Ist der Normdatensatz richtig?' : t === 'place' ? 'Ist die Lage richtig?' : 'Ist die EUNIS-Klasse richtig?');
  return '<div class="q">' + q + '</div><div class="acts">' + (tab === 'link' && t === 'taxon' ? '' : b('y', L[0], 'Y', yDis)) + b('r', tab === 'link' && t === 'taxon' ? 'GBIF-Art suchen …' : L[1], 'A') + b('n', L[2], 'N') + b('u', 'Unsicher', 'U') + (cd.d ? '<button class="lbtn" data-ea="">zurücksetzen</button>' : '') + '</div>'
    + stateLine(cd, entStateText(t, e, cd)) + (ui.panel && ui.panel.scope === 'e' ? panelHtml(t, ui.panel) : '');
}
function entStateText(t, e, cd) {
  if (cd.d === 'u') return '? unsicher';
  if (t === 'taxon') return cd.d === 'y' ? '✓ Art bestätigt' : cd.d === 'r' ? '↪ zugeordnet: <b>' + esc(cd.target.label) + '</b> <i>' + esc(cd.target.sci || '') + '</i>' : '✗ nicht bestimmbar: ohne GBIF-Art';
  if (t === 'habitat') return cd.d === 'y' ? '✓ Klasse bestätigt' : cd.d === 'r' ? '↪ Klasse: <b>' + esc(cd.target.label) + '</b> (' + esc(cd.target.match) + ')' : '✗ keine EUNIS-Klasse';
  if (t === 'person') return cd.d === 'y' ? '✓ Normdaten: ' + [cd.qid ? 'Wikidata ' + esc(cd.qid) : '', cd.gnd ? 'GND ' + esc(cd.gnd) : ''].filter(Boolean).join(' · ') : cd.d === 'r' ? '↪ dieselbe Person wie <b>' + esc(cd.target.label) + '</b>' : '✗ keine passenden Normdaten';
  return cd.d === 'y' ? '✓ Lage ' + (cd.fix && cd.fix.lat ? 'gesetzt: ' + cd.fix.lat + ', ' + cd.fix.lon + ' (± ' + fmt(cd.fix.uncertainty_m) + ' m)' : 'bestätigt') : cd.d === 'r' ? '↪ derselbe Ort wie <b>' + esc(cd.target.label) + '</b>' : '✗ Lage nicht bestimmbar';
}
function entityView(t, e, tab) {
  const x = e.e;
  const head = '<span class="bd ' + (linked(t, e) ? 'ok' : 'warn') + '">' + esc(TT[t].one) + ' · ' + (linked(t, e) ? 'verknüpft' : 'ohne Normdaten') + '</span><h1 class="t">' + esc(e.label) + (t === 'taxon' && x[1] ? ' <i>' + esc(x[1]) + '</i>' : '') + '</h1><div class="sub">' + fmt(e.n) + ' ' + TT[t].unit + ' · ' + e.names.length + (e.names.length === 1 ? ' Name' : ' Namen') + (t === 'place' && x[6] ? ' · ' + esc(x[6]) : '') + '</div>';
  return crumb() + '<div class="card"><div class="cb">' + head + authBlock(t, e, tab) + entActs(t, e, tab) + (tab === 'link' ? mergeBlock(t, e) : '') + '</div><div class="cb">' + namesBlock(t, e) + '</div></div>';
}
function namesView(t, e) {
  const head = '<span class="bd ' + (linked(t, e) ? 'ok' : 'warn') + '">' + esc(TT[t].one) + ' · ' + authText(t, e) + '</span><h1 class="t">' + esc(e.label) + (t === 'taxon' && e.e[1] ? ' <i>' + esc(e.e[1]) + '</i>' : '') + '</h1><div class="sub">' + fmt(e.n) + ' ' + TT[t].unit + (t === 'taxon' && e.e[9].length ? ' · deutsche Namen laut GBIF/Wikidata: ' + e.e[9].slice(0, 10).map(esc).join(', ') : '') + '</div>';
  const gd = grpDec(t, e);
  return crumb() + '<div class="card"><div class="cb">' + head + '<div class="acts" style="margin-top:10px"><button class="btn y' + (gd ? ' on' : '') + '" data-grp="y">Namensgruppe stimmt so <kbd>Y</kbd></button>' + (gd ? '<button class="lbtn" data-grp="">zurücksetzen</button>' : '') + '</div>' + stateLine(gd, '✓ Namensgruppe bestätigt') + '</div><div class="cb">' + namesBlock(t, e) + '</div></div>';
}

// ---------------------------------------------------------------- read view (misreadings)
function readView(it) {
  const mi = it.mi; const m = P.taxon.men[mi]; const ce = P.taxon.ent[P.taxon.forms[m[0]][2]]; const e = E[m[1]]; const written = writtenOf(mi); const d = S.men.taxon[it.key] || {}; const rd = menReading('taxon', mi);
  const rows = it.rs.map((r, k) => { const tgt = r.target >= 0 ? P.taxon.ent[r.target] : null; const what = r.kind === 'bird' ? (tgt ? esc(tgt[0]) + ' <i>' + esc(tgt[1]) + '</i>' : esc(r.species || '') + (r.sci ? ' <i>' + esc(r.sci) + '</i>' : '') + (r.species || r.sci ? ' <span class="muted">(nicht im Graph)</span>' : '')) : ({ other_animal: 'kein Vogel (anderes Tier)', place: 'ein Ort', person: 'eine Person', other: 'kein Vogelname' }[r.kind] || esc(r.kind));
    return '<tr' + (r.differs ? ' class="hi"' : '') + '><td>' + esc(MODEL_DE[r.src]) + '</td><td class="rd">„' + esc(r.word) + '“</td><td>' + what + '</td><td>' + Math.round(100 * (r.conf || 0)) + ' %</td><td class="small muted">' + esc(r.note || '') + '</td><td>' + (r.differs ? '<button class="btn sm tip" data-accept="' + k + '">übernehmen <kbd>' + (k + 1) + '</kbd></button>' : '<span class="bd ok">wie Transkription</span>') + '</td></tr>'; }).join('');
  const ag = (it.ag === 3 ? '<span class="bd ok">beide Modelle lesen dasselbe</span>' : it.ag === 1 ? '<span class="bd warn">die Modelle widersprechen sich</span>' : '<span class="bd tip">nur eine Zweitlesung</span>') + (it.mis ? ' <span class="bd warn">Zeilenbild verrutscht?</span>' : '');
  const best = it.rs.find(r => r.differs) || it.rs[0]; const nm0 = X.taxon.names[m[0]];
  const diag = it.kind === 'species' ? '<div class="hint" style="margin-top:8px;font-size:13px"><b>Keine Lesefrage:</b> die Modelle lesen dasselbe Wort wie die Transkription, bestimmen aber eine andere Art — <b>' + esc(best.species || best.word) + '</b>' + (best.sci ? ' <i>' + esc(best.sci) + '</i>' : '') + ' statt ' + esc(ce[0]) + '. Das betrifft die Zuordnung des Namens „' + esc(nm0.name) + '“' + (nm0.n > 1 ? ' — am besten unten für alle ' + fmt(nm0.n) + ' Belege entscheiden.' : '.') + '</div>'
    : it.kind === 'nonbird' ? '<div class="hint" style="margin-top:8px;font-size:13px"><b>Laut Modell kein Vogelname</b> (' + esc({ place: 'ein Ort', person: 'eine Person', other_animal: 'ein anderes Tier', other: 'anderes' }[best.kind] || best.kind) + '): dann <kbd>N</kbd> „Kein Vogel“, sonst <kbd>Y</kbd>.</div>'
    : '<div class="hint" style="margin-top:8px;font-size:13px"><b>Lesefrage:</b> die Modelle lesen „' + esc(best.word) + '“, die Transkription „' + esc(written) + '“. Stimmt die Lesung des Modells, <kbd>1</kbd>/<kbd>2</kbd> übernehmen (setzt Wort und Art); sonst <kbd>Y</kbd> oder <kbd>E</kbd>.</div>';
  const misHint = diag + (it.mis ? '<div class="hint" style="margin-top:8px">Das gelesene Wort steht an anderer Stelle dieses Eintrags: der Zeilenausschnitt zeigt vermutlich eine andere Zeile (häufig bei zweispaltigen Artenlisten). Bitte auf der Seite rechts die Zeile mit „' + esc(written) + '“ suchen; stimmt die Transkription dort, <kbd>Y</kbd>.</div>' : '');
  const b = (k, label, key) => '<button class="btn ' + k + (d.d === k ? ' on' : '') + '" data-ra="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  return crumb() + '<div class="card"><div class="cb"><span class="bd ' + READ_KIND[it.kind][1] + '">' + READ_KIND[it.kind][0] + '</span> ' + ag + '<h1 class="t">„' + esc(written) + '“ <span class="muted">→</span> ' + esc(ce[0]) + (ce[1] ? ' <i>' + esc(ce[1]) + '</i>' : '') + '</h1><div class="sub">' + entryHead(m[1]) + '</div>'
    + misHint + '<div style="margin-top:10px">' + snipHtml(m[4], 1.4, 'big') + '</div><div class="kw" style="padding:8px 0;font:14px/1.55 Georgia,serif">' + kwic(e[7], m[2], m[3], ui.full.has('taxon' + mi)) + '<button class="more" data-full="' + mi + '" style="border:0;background:none;color:var(--navy2);cursor:pointer;font:12px system-ui">' + (ui.full.has('taxon' + mi) ? 'weniger' : 'ganzer Eintrag') + '</button></div>'
    + '<table class="readings"><tr><th>Lesung</th><th>Wort</th><th>bezeichnet</th><th>sicher</th><th>Anmerkung</th><th></th></tr><tr><td>Transkription</td><td class="rd">„' + esc(written) + '“</td><td>' + esc(ce[0]) + (ce[1] ? ' <i>' + esc(ce[1]) + '</i>' : '') + '</td><td></td><td class="small muted">so steht es im Graph</td><td>' + b('y', 'stimmt', 'Y') + '</td></tr>' + rows + '</table>'
    + nameLevelBox(it, m)
    + '<div class="q">Was steht im Scan?<small>Zeilenbild oben, ganze Seite rechts</small></div><div class="acts">' + b('e', 'Selbst korrigieren …', 'E') + b('r', 'Wort stimmt, andere Art …', 'A') + b('n', 'Kein Vogel …', 'N') + b('u', 'Unsicher', 'U') + (d.d || rd ? '<button class="lbtn" data-ra="">zurücksetzen</button>' : '') + '</div>'
    + (ui.word != null ? '<div class="wordfix"><span class="small muted">gelesen</span><span class="rd">„' + esc(written) + '“</span><span>→</span><input type="text" id="wordfix" value="' + esc(ui.word) + '" placeholder="so steht es im Scan"><button class="btn sm y" id="wordsave">Lesung speichern <kbd>⏎</kbd></button><span class="small muted">Art danach über „andere Art“ oder eine Modell-Lesung</span></div>' : '')
    + (ui.panel && (ui.panel.scope === 'm:' + mi) ? panelHtml('taxon', ui.panel) : '')
    + (rd ? '<div class="state y">✎ Lesung: „' + esc(rd.old) + '“ → „<b>' + esc(rd.new) + '</b>“' + (rd.note ? ' <span class="muted small">(' + esc(rd.note) + ')</span>' : '') + '</div>' : '') + stateLine(d, 'Beleg: ' + decLine('taxon', d)) + '</div></div>';
}

// the written name behind a read item: decide it once for every mention instead of mention by mention
function nameLevelBox(it, m) {
  const nm = X.taxon.names[m[0]]; if (nm.n < 2) return '';
  // the graph files this mention under a name form; if the text says something else, the question is about this mention only
  if (!sameWord(writtenOf(it.mi), nm.name)) return '<div class="hint" style="margin-top:8px">Im Text steht „' + esc(writtenOf(it.mi)) + '“, im Graph läuft der Beleg unter dem Namen „' + esc(nm.name) + '“ (' + fmt(nm.n) + '×). Hier nur diesen Beleg entscheiden; der Name selbst steht in „Prüfen“.</div>';
  const cur = P.taxon.forms[m[0]][2]; const inList = READ.filter(x => P.taxon.men[x.mi][0] === m[0] && sameWord(writtenOf(x.mi), nm.name)).length;
  const bt = it.rs.filter(r => r.differs && r.kind === 'bird' && r.target >= 0 && r.target !== cur); const tgt = bt.length && bt.every(r => r.target === bt[0].target) ? P.taxon.ent[bt[0].target] : null;
  const nd = nameDec('taxon', nm);
  return '<div class="q">Für alle ' + fmt(nm.n) + ' Belege des Namens „' + esc(nm.name) + '“<small>' + inList + ' davon in dieser Liste — gilt die Entscheidung für den Namen überall, nicht nur hier?</small></div><div class="acts">'
    + (tgt ? '<button class="btn r" data-nameto="' + bt[0].target + '" data-fi="' + nm.fi + '" title="Der Name meint überall diese Art (die Schreibung bleibt als Name erhalten)">Name → ' + esc(tgt[0]) + ' <i>' + esc(tgt[1]) + '</i></button>' : '')
    + '<button class="btn" data-nreassign="' + nm.fi + '" data-t="taxon">Name → andere Art …</button><button class="btn" data-nread="' + nm.fi + '">✎ Name überall lesen als …</button></div>'
    + (nd && nd.d ? '<div class="state ' + (nd.d === 'y' ? 'y' : nd.d === 'u' ? 'u' : nd.d === 'n' ? 'n' : 'r') + '">Name „' + esc(nm.name) + '“: ' + decLine('taxon', nd) + ' <button class="lbtn" data-nclear="' + nm.fi + '">zurücksetzen</button></div>' : '')
    + (ui.nword === nm.fi ? nwordRow('taxon', nm) : '') + (ui.panel && ui.panel.scope === 'n:' + nm.fi ? panelHtml('taxon', ui.panel) : '');
}

// ---------------------------------------------------------------- sample and hints
function wilson(k, n) { if (!n) return [0, 0, 0]; const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [p, Math.max(0, c - h), Math.min(1, c + h)]; }
function evalStats() { const by = {}; let k = 0, n = 0; for (const mi of P.sample) { const d = S.ev[X.taxon.mkey[mi]]; if (!d || (d.d !== 'y' && d.d !== 'n')) continue; const c = P.taxon.forms[P.taxon.men[mi][0]][3]; by[c] = by[c] || [0, 0]; by[c][1]++; n++; if (d.d === 'y') { k++; by[c][0]++; } } return { k, n, by }; }
function evalView(it) {
  const mi = it.mi; const m = P.taxon.men[mi]; const f = P.taxon.forms[m[0]]; const x = P.taxon.ent[f[2]]; const d = S.ev[it.key] || {};
  const st = evalStats(); const [p, lo, hi] = wilson(st.k, st.n);
  const b = (k, label, key) => '<button class="btn ' + k + (d.d === k ? ' on' : '') + '" data-sa="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  return crumb() + '<div class="card"><div class="cb"><div class="row"><div><div class="small muted">Genauigkeit der Artbestimmung</div><div class="big">' + (st.n ? pct(p) : '–') + '</div><div class="small muted">' + (st.n ? '95 %-Intervall ' + pct(lo) + ' – ' + pct(hi) + ' · ' + st.k + ' von ' + st.n + ' richtig' : 'noch nichts beurteilt') + '</div></div><div class="sp"></div><div class="small muted">' + Object.entries(st.by).map(([c, [a, bb]]) => esc(TT.taxon.cls[c][0]) + ' ' + a + '/' + bb).join(' · ') + '</div></div></div></div>'
    + '<div class="card"><div class="cb"><h1 class="t">' + esc(f[0]) + ' → ' + esc(x[0]) + (x[1] ? ' <i>' + esc(x[1]) + '</i>' : '') + '</h1><div class="sub">Beleg ' + (it.k + 1) + ' von ' + P.sample.length + ' (zufällig gezogen). Ist an dieser Stelle diese Art gemeint? Der Reihe nach, nichts auslassen.</div>'
    + '<div class="acts" style="margin-top:10px">' + b('y', 'Richtig bestimmt', 'Y') + b('n', 'Falsch', 'N') + b('u', 'Nicht entscheidbar', 'U') + '</div>' + (d.d === 'n' && d.target ? '<div class="state r">Richtig wäre: <b>' + esc(d.target.label) + '</b> <i>' + esc(d.target.sci || '') + '</i></div>' : '')
    + (ui.panel && ui.panel.scope === 'ev' ? panelHtml('taxon', ui.panel) : '') + '</div></div>' + menHtml('taxon', mi, { noActs: true });
}
function qaView(it) {
  const r = it.r; const q = QA_DE[r[2]] || [r[2], '']; const d = S.qa[it.key] || {};
  const b = (k, label, key) => '<button class="btn ' + k + (d.d === k ? ' on' : '') + '" data-sa="' + k + '">' + label + ' <kbd>' + key + '</kbd></button>';
  const isTaxon = ['non_bird', 'low_confidence_taxon'].includes(r[2]) && r[4]; const md = isTaxon ? S.men.taxon[r[1] + '|' + lc(r[4]) + '|0'] : null;
  let entry = '<div class="card"><div class="cb muted">Eintrag nicht mehr im Graph, kein Text verfügbar.</div></div>';
  if (it.ei >= 0) { const e = E[it.ei]; const i = r[4] && !/^\d+$/.test(r[4]) ? lc(e[7]).indexOf(lc(r[4])) : -1; const hs = readingFor(it.ei);
    entry = '<div class="men" data-ei="' + it.ei + '"><div class="mh">' + entryHead(it.ei) + '<span class="sp"></span><button class="lbtn" data-scanentry="' + it.ei + '">Scan</button><button class="mb" data-edit="' + it.ei + '" data-s="' + i + '" data-e="' + (i >= 0 ? i + r[4].length : -1) + '" title="Lesung korrigieren (E)">✎</button></div><div class="kw">' + (i >= 0 ? highlight(e[7], i, i + r[4].length) : esc(e[7])) + '</div>' + hs.map(h => '<div class="note t">✎ Lesung: „' + esc(h.old) + '“ → „<b>' + esc(h.new) + '</b>“</div>').join('') + '</div>'; }
  return crumb() + '<div class="card"><div class="cb"><h1 class="t">' + esc(q[0]) + (r[4] && ['non_bird', 'low_confidence_taxon', 'nonplace'].includes(r[2]) ? ' · ' + esc(r[4]) : '') + '</h1><div class="sub">' + esc(q[1]) + ' <span class="bd ' + (r[3] === 'excluded' ? 'risk' : 'warn') + '">' + (r[3] === 'excluded' ? 'entfernt' : 'nur markiert') + '</span></div><dl class="facts"><dt>Eintrag</dt><dd>' + esc(r[0]) + '</dd><dt>Begründung</dt><dd>' + esc(r[5]) + '</dd></dl>'
    + '<div class="acts" style="margin-top:10px">' + b('y', 'Richtig erkannt', 'Y') + b('n', 'Falsch erkannt', 'N') + b('u', 'Unsicher', 'U') + '</div>'
    + (isTaxon ? (md && md.target ? '<div class="state r">Richtige Art in diesem Eintrag: <b>' + esc(md.target.label) + '</b> <i>' + esc(md.target.sci || '') + '</i> <button class="lbtn" id="qaunfix">verwerfen</button></div>' : panelHtml('taxon', { scope: 'qa', kind: 'r', title: 'Doch ein Vogel? Richtige Art' })) : '')
    + '<div class="row" style="margin-top:8px"><input type="text" class="grow ftext" id="qanote" placeholder="Anmerkung / Korrektur, falls bekannt" value="' + esc(d.note || '') + '"></div><div class="hint">Falsch gelesenes Datum oder Wort: im Eintrag unten ✎ „Lesung korrigieren“ (<kbd>E</kbd>).</div></div></div>' + entry;
}
