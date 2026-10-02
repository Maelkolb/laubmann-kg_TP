// ---------------------------------------------------------------- decisions on the entry
function setEnt(ty, e, d) { commit(e.l + ': ' + (d ? decText(ty, d) : t('toast.cleared')), [['ent', ty, e.k, d]]); }
function formObj(ty, e, name, d, via, to, toLink) {
  const o = { d, name, ent: e.l, via: via || 'toggle' };
  if (d === 'same') { o.to = to; if (ty === 'taxon' && toLink && toLink.key) o.toLink = { key: String(toLink.key), sci: toLink.sci || '', rank: toLink.rank || '' }; }
  return stamp(o);
}
const taxonByKey = key => { const x = D.TAXA.find(r => String(r[2]) === String(key)); return x ? { label: x[0], sci: x[1], key: x[2], rank: x[3] } : null; };
function formSuggestionOp(ty, e, f) {
  const m = f.m; if (!m || m.ap || !m.diff) return null;
  if (m.none) return ['form', ty, cf(f.f), formObj(ty, e, f.f, 'none', 'accept')];
  if (m.nolink) return ['form', ty, cf(f.f), formObj(ty, e, f.f, 'own', 'accept')];
  if (m.key) { const tx = taxonByKey(m.key); return ['form', ty, cf(f.f), formObj(ty, e, f.f, 'same', 'accept', (tx && tx.label) || m.sci || f.f, { key: m.key, sci: m.sci || (tx && tx.sci) || '', rank: (tx && tx.rank) || '' })]; }
  return null;
}
function acceptSuggestion(ty, e) {
  if (!hasSuggestion(ty, e)) return toast(t('toast.noprop'));
  const ops = []; const p = e.m.prop;
  if (p) ops.push(['ent', ty, e.k, p.none ? makeDec(ty, e, 'none', 'accept') : p.nolink ? makeDec(ty, e, 'nolink', 'accept') : makeDec(ty, e, 'link', 'accept', p, gradePick || (ty === 'habitat' ? p.match : null))]);
  if (ty === 'taxon') for (const f of formSuggestions(e)) { const op = formSuggestionOp(ty, e, f); if (op) ops.push(op); }
  if (!ops.length) return toast(t('toast.noprop'));
  commit(e.l + ': ' + t('dec.link.accept'), ops);
}
function revertChange(ty, e) {
  if (e.q !== 'changed') return toast(t('toast.nobefore'));
  const ops = [];
  if (ty === 'taxon' && !e.gone) {
    for (const f of e.forms) if (f.was && f.was.known) ops.push(['form', ty, cf(f.f), f.was.key ? formObj(ty, e, f.f, 'same', 'revert', f.was.label || f.f, { key: f.was.key, sci: f.was.sci }) : formObj(ty, e, f.f, 'own', 'revert')]);
  } else if (e.bsrc) ops.push(['ent', ty, e.k, e.before ? makeDec(ty, e, 'link', 'revert', e.before, e.before.grade === 'broad' ? 'broad' : null) : makeDec(ty, e, 'nolink', 'revert')]);
  if (!ops.length) return toast(t('toast.nobefore'));
  commit(e.l + ': ' + t('dec.link.revert'), ops);
}
function focusSearch() { const s = $('#sInput'); if (!s) return; s.scrollIntoView({ block: 'center' }); s.focus(); s.select(); }
function act(k) {
  const ty = cur.type; const e = curEnt();
  if (k === 'undo') return undo();
  if (k === 'corpus-off') return setCorpus(0);
  if (k === 'corpus-info') return showCorpusInfo();
  if (!e) return;
  if (k === 'confirm') {
    if (e.gone) return setEnt(ty, e, makeDec(ty, e, 'none', 'confirm'));
    if (e.cur) return setEnt(ty, e, makeDec(ty, e, 'link', 'confirm', e.cur, ty === 'taxon' || ty === 'habitat' ? curGrade(ty, e) : null));
    toast(t('toast.nolinkconfirm')); return setEnt(ty, e, makeDec(ty, e, 'nolink', 'confirm'));
  }
  if (k === 'other') return focusSearch();
  if (k === 'nolink') return setEnt(ty, e, makeDec(ty, e, 'nolink', e.cur || e.gone ? 'reject' : 'confirm'));
  if (k === 'none') return setEnt(ty, e, makeDec(ty, e, 'none', e.gone ? 'confirm' : 'reject'));
  if (k === 'unsure') return setEnt(ty, e, makeDec(ty, e, 'unsure', 'unsure'));
  if (k === 'accept') return acceptSuggestion(ty, e);
  if (k === 'revert') return revertChange(ty, e);
  if (k === 'clear') return setEnt(ty, e, null);
  if (k === 'tolink') { S.ui.q[ty] = e.q; S.ui.sub[ty] = ''; return openEntity(ty, e.k); }
  if (k === 'mgsame' || k === 'mgdiff') {
    const v = mergeNames(e).find(n => !formDec(ty, n)) || mergeNames(e)[0]; const first = e.mg.find(c => c.v === v);
    return k === 'mgsame' ? mergeSame(ty, e, v, first.to) : commit(v + ': ' + t('mg.decided.own'), [['form', ty, cf(v), formObj(ty, e, v, 'own', 'merge')]]);
  }
}
function mergeSame(ty, e, v, to) {
  const te = BYK[ty].get(cf(to));
  commit(v + ': ' + t('mg.decided.same', to), [['form', ty, cf(v), formObj(ty, e, v, 'same', 'merge', to, te && te.cur)]]);
}
function pickCand(k) {
  const ty = cur.type; const e = curEnt(); const c = view.cands[k]; if (!e || !c) return false;
  const target = Object.assign({}, c);
  if (ty === 'place' && target.unc == null) { const u = $('#punc'); target.unc = u && +u.value ? +u.value : 1000; }
  const grade = ty === 'habitat' ? (gradePick || c.match || 'close') : ty === 'taxon' ? (gradePick || 'exact') : null;
  const via = sameLink(ty, target, e.cur) ? 'confirm' : (e.m && e.m.prop && !e.m.prop.none && !e.m.prop.nolink && sameLink(ty, target, e.m.prop) && c.o === 'm' ? 'accept' : c.o === 'b' ? 'revert' : searchRes ? 'search' : 'cand');
  searchRes = null;
  setEnt(ty, e, makeDec(ty, e, 'link', via, target, grade));
  return true;
}
function pickDigit(n) {
  const ty = cur.type; const e = curEnt(); if (!e) return false;
  if (panelForm) { const r = $$('#formpanel .r[data-ent]')[n - 1]; if (r) { r.click(); return true; } return false; }
  if (curQ(ty) === 'merge' && e.mg) { const v = mergeNames(e).find(x => !formDec(ty, x)) || mergeNames(e)[0]; const c = e.mg.filter(x => x.v === v)[n - 1]; if (c) { mergeSame(ty, e, v, c.to); return true; } return false; }
  return pickCand(n - 1);
}

// ---------------------------------------------------------------- written names
function toggleForm(name, v) {
  const ty = cur.type; const e = curEnt(); if (!e) return;
  const fd = formDec(ty, name); const key = cf(name);
  const isCand = (e.mgin || []).some(c => cf(c.v) === key) || mergeNames(e).includes(name);
  const via = isCand ? 'merge' : 'toggle';
  const state = fd ? (fd.d === 'same' ? (cf(fd.to) === e.k ? 'same' : 'other') : fd.d) : '';
  if (v === 'other') { panelForm = panelForm === name ? null : name; renderCard(); if (panelForm) { const i = $('#fInput'); if (i) i.focus(); } return; }
  panelForm = null;
  if (state === v) return commit(name + ': ' + t('toast.cleared'), [['form', ty, key, null]]);
  const d = entDec(ty, e); const link = d && d.d === 'link' ? d.target : e.cur;
  const o = v === 'same' ? formObj(ty, e, name, 'same', via, e.l, link) : formObj(ty, e, name, v, via);
  commit(name + ': ' + formDecText(ty, e, o), [['form', ty, key, o]]);
}
function renderFormPanel(ty, e) {
  const el = $('#formpanel'); if (!el) return;
  el.innerHTML = '<div class="row"><input type="text" class="grow" id="fInput" placeholder="' + esc(t('search.entity')) + '" autocomplete="off" style="border:1px solid var(--line2);border-radius:6px;padding:4px 8px;background:var(--panel);color:var(--ink)"><button class="tb" data-fclose="1">✕</button></div><div class="res" id="fRes"></div>';
  const inp = $('#fInput');
  const show = () => {
    const q = fold(inp.value); if (!q) { $('#fRes').innerHTML = ''; return; }
    const hits = []; for (const x of ENTS[ty]) { if (x === e || x.gone) continue; const st = searchText(x); const i = st.indexOf(q); if (i < 0) continue; hits.push([fold(x.l) === q ? 0 : fold(x.l).startsWith(q) ? 1 : i === 0 ? 2 : 3, x]); if (hits.length > 400) break; }
    hits.sort((a, b) => a[0] - b[0] || b[1].n - a[1].n);
    $('#fRes').innerHTML = hits.slice(0, 9).map((h, k) => '<div class="r" data-ent="' + esc(h[1].k) + '"><span class="k">' + (k + 1) + '</span><b>' + esc(h[1].l) + '</b><small>' + esc(linkShort(ty, h[1].cur)) + ' · ' + fmt(h[1].n) + '</small></div>').join('') || '<div class="r muted">' + esc(t('search.nohit')) + '</div>';
  };
  inp.oninput = show; inp.value = '';
}
function pickFormTarget(key) {
  const ty = cur.type; const e = curEnt(); const te = BYK[ty].get(key); const name = panelForm; if (!e || !te || !name) return;
  panelForm = null;
  commit(name + ': ' + t('names.dec.same', te.l), [['form', ty, cf(name), formObj(ty, e, name, 'same', 'toggle', te.l, te.cur)]]);
}

// ---------------------------------------------------------------- live search (GBIF, Wikidata, lobid-GND, Nominatim; EUNIS and graph taxa locally)
async function getJSON(url) { const r = await fetch(url, { headers: { Accept: 'application/json' } }); if (!r.ok) throw new Error(String(r.status)); return r.json(); }
const year = s => (s ? String(s).replace(/^\+/, '').slice(0, 4) : '');
async function wdDetails(ids) {
  if (!ids.length) return {};
  const j = await getJSON('https://www.wikidata.org/w/api.php?action=wbgetentities&ids=' + ids.slice(0, 40).join('|') + '&props=claims|labels|descriptions&languages=de|en&format=json&origin=*');
  const out = {};
  for (const [q, en] of Object.entries(j.entities || {})) {
    const cl = en.claims || {}; const val = p => { const s = (cl[p] || [])[0]; const v = s && s.mainsnak && s.mainsnak.datavalue && s.mainsnak.datavalue.value; return v == null ? '' : (v.time || v.id || v); };
    out[q] = { qid: q, label: ((en.labels || {}).de || (en.labels || {}).en || {}).value || '', desc: ((en.descriptions || {}).de || (en.descriptions || {}).en || {}).value || '', born: year(val('P569')), died: year(val('P570')), gnd: String(val('P227') || ''), human: val('P31') === 'Q5' };
  }
  return out;
}
const WDX = {};
async function enrichWD() {
  const ids = uniq($$('[data-wdlabel]').map(x => x.dataset.wdlabel).filter(q => /^Q\d+$/.test(q) && !(q in WDX)));
  if (ids.length) { for (const q of ids) WDX[q] = null; try { Object.assign(WDX, await wdDetails(ids)); } catch (e) { /* offline: the record keeps its id */ } }
  for (const el of $$('[data-wdlabel]')) { const x = WDX[el.dataset.wdlabel]; if (x && x.label) el.textContent = x.label; }
  for (const el of $$('[data-wdlife]')) { const x = WDX[el.dataset.wdlife]; if (x && (x.born || x.died)) el.innerHTML = life(x); }
  for (const el of $$('[data-wddesc]')) { const x = WDX[el.dataset.wddesc]; if (x && x.desc) el.textContent = x.desc; }
}
function localTaxa(q) {
  q = fold(q); if (!q) return [];
  const sc = x => { const a = fold(x[0]), b = fold(x[1]); return a === q || b === q ? 0 : a.startsWith(q) || b.startsWith(q) ? 1 : a.includes(q) || b.includes(q) ? 2 : 9; };
  return D.TAXA.map(x => [sc(x), x]).filter(p => p[0] < 9).sort((a, b) => a[0] - b[0] || a[1][0].localeCompare(b[1][0])).slice(0, 9).map(p => ({ label: p[1][0], sci: p[1][1], key: p[1][2], rank: p[1][3], o: 'graph' }));
}
function localEunis(q) {
  q = fold(q); if (!q) return [];
  return D.EUNIS.filter(x => fold(x[0]).startsWith(q) || fold(x[1]).includes(q)).sort((a, b) => (fold(a[0]) === q ? -1 : 0) - (fold(b[0]) === q ? -1 : 0) || a[2] - b[2] || a[0].localeCompare(b[0])).slice(0, 12).map(x => ({ code: x[0], label: x[1], match: gradePick || 'close', o: 'search' }));
}
function showResults(list) { searchRes = list; updateCands(); if (cur.type === 'place') { const e = curEnt(); if (e) initMap(e); } }
function updateCands() {
  const ty = cur.type; const e = curEnt(); const el = $('#candlist'); if (!e || !el) return;
  view.cands = searchRes || e.cands || [];
  el.innerHTML = view.cands.length ? '<div class="cands">' + view.cands.slice(0, 12).map((c, k) => candHtml(ty, c, k)).join('') + '</div>' : '<div class="small muted">' + esc(searchRes ? t('search.nohit') : t('cand.none')) + '</div>';
  enrichWD();
}
async function runSearch(kind) {
  const ty = cur.type; const e = curEnt(); if (!e) return;
  const inp = $('#sInput'); const q = inp ? inp.value.trim() : '';
  if (kind === 'clear') { searchRes = null; if (inp) inp.value = ''; updateCands(); if (ty === 'place') initMap(e); return; }
  if (kind === 'ids') {
    const qid = ($('#pqid').value || '').trim().toUpperCase(), gnd = ($('#pgnd').value || '').trim();
    if (!/^Q\d+$/.test(qid) && !gnd) return toast(t('search.need'));
    return setEnt(ty, e, makeDec(ty, e, 'link', 'search', { qid: /^Q\d+$/.test(qid) ? qid : '', gnd, label: (WDX[qid] || {}).label || '' }));
  }
  if (kind === 'coords') {
    const lat = parseFloat(($('#plat').value || '').replace(',', '.')), lon = parseFloat(($('#plon').value || '').replace(',', '.'));
    if (isNaN(lat) || isNaN(lon)) return toast(t('search.need'));
    return setEnt(ty, e, makeDec(ty, e, 'link', 'search', { lat, lon, unc: +$('#punc').value || 1000, name: e.l }));
  }
  if (!q) return toast(t('search.need'));
  const cl = $('#candlist'); if (cl) cl.innerHTML = '<div class="small muted">' + esc(t('search.wait')) + '</div>';
  try {
    let list = [];
    if (kind === 'gbif') {
      const seen = new Set();
      const add = x => { const key = String(x.usageKey || x.nubKey || x.key || ''); if (!key || seen.has(key)) return; seen.add(key); const de = (x.vernacularNames || []).find(v => v.language === 'deu'); const g = taxonByKey(key);
        list.push({ key, sci: x.canonicalName || x.scientificName || '', rank: String(x.rank || '').toLowerCase(), label: (g && g.label) || (de && de.vernacularName) || '', family: x.family || '', order: x.order || '', o: 'search' }); };
      // taxa of the graph first (they carry the diary's German names), then an exact GBIF name match, then the GBIF search (species before subspecies)
      for (const g of localTaxa(q).slice(0, 4)) { seen.add(String(g.key)); list.push(g); }
      const m = await getJSON('https://api.gbif.org/v1/species/match?name=' + encodeURIComponent(q) + '&kingdom=Animalia&class=Aves').catch(() => null);
      if (m && (m.matchType === 'EXACT' || m.matchType === 'FUZZY') && m.usageKey) add(m);
      const s = await getJSON('https://api.gbif.org/v1/species/search?q=' + encodeURIComponent(q) + '&datasetKey=d7dddbf4-2cf0-4f39-9b2a-bb099caae36c&status=ACCEPTED&highertaxonKey=212&limit=20');
      const order = { SPECIES: 0, GENUS: 1, FAMILY: 2, SUBSPECIES: 3 };
      for (const x of (s.results || []).slice().sort((a, b) => (order[a.rank] != null ? order[a.rank] : 4) - (order[b.rank] != null ? order[b.rank] : 4))) add(x);
      list = list.slice(0, 12);
    } else if (kind === 'wd') {
      const s = await getJSON('https://www.wikidata.org/w/api.php?action=wbsearchentities&search=' + encodeURIComponent(q) + '&language=de&uselang=de&type=item&limit=10&format=json&origin=*');
      const ids = (s.search || []).map(x => x.id); const det = await wdDetails(ids).catch(() => ({}));
      list = (s.search || []).map(x => Object.assign({ qid: x.id, label: x.label || '', desc: x.description || '', o: 'search' }, det[x.id] ? { born: det[x.id].born, died: det[x.id].died, gnd: det[x.id].gnd, human: det[x.id].human } : {}));
      list.sort((a, b) => (b.human ? 1 : 0) - (a.human ? 1 : 0));
    } else if (kind === 'gnd') {
      try {                                       // lobid refuses requests from a page opened as a file: then via Wikidata (P227)
        const j = await getJSON('https://lobid.org/gnd/search?q=' + encodeURIComponent(q) + '&filter=type%3APerson&format=json&size=10');
        list = (j.member || []).map(x => ({ gnd: x.gndIdentifier || '', label: x.preferredName || '', born: year((x.dateOfBirth || [])[0]), died: year((x.dateOfDeath || [])[0]), desc: (x.professionOrOccupation || []).map(o => o.label).slice(0, 3).join(', '),
          qid: ((x.sameAs || []).map(s => s.id || '').find(u => u.indexOf('wikidata.org/entity/') >= 0) || '').split('/').pop() || '', o: 'search' }));
      } catch (err) {
        toast(t('search.gndfallback'));
        const s = await getJSON('https://www.wikidata.org/w/api.php?action=query&list=search&srsearch=' + encodeURIComponent(q + ' haswbstatement:P227') + '&srlimit=10&format=json&origin=*');
        const ids = ((s.query || {}).search || []).map(x => x.title); const det = await wdDetails(ids);
        list = ids.map(i => det[i]).filter(Boolean).map(x => Object.assign(x, { o: 'search' }));
      }
    } else if (kind === 'nom') {
      const s = await getJSON('https://nominatim.openstreetmap.org/search?q=' + encodeURIComponent(q) + '&format=jsonv2&limit=9&accept-language=de&extratags=1');
      list = (s || []).map(x => ({ lat: +x.lat, lon: +x.lon, name: x.display_name || x.name || '', feature: [x.category, x.type].filter(Boolean).join('/'), osm: x.osm_type ? x.osm_type + '/' + x.osm_id : '', qid: (x.extratags || {}).wikidata || '', o: 'search' }));
    }
    showResults(list);
    if (inp) inp.blur();
  } catch (err) { toast(t('search.down'), 3500); searchRes = null; updateCands(); }
}

// ---------------------------------------------------------------- navigation
function nav(dir) {
  const ty = cur.type; if (ty === 'home') return;
  const items = listItems(ty); const pos = items.findIndex(e => e.k === cur.key); const q = curQ(ty); let nx;
  if (dir === 'prev') nx = items[pos - 1]; else if (dir === 'next') nx = items[pos + 1];
  else nx = items.slice(pos + 1).find(e => isOpen(ty, e, q)) || items.slice(0, Math.max(0, pos)).find(e => isOpen(ty, e, q));
  if (!nx) return toast(dir === 'open' ? t('toast.noopen') : t('toast.end'));
  const i = items.indexOf(nx); if (i >= (SHOW[ty] || LIST_STEP)) SHOW[ty] = Math.ceil((i + 1) / LIST_STEP) * LIST_STEP;
  openEntity(ty, nx.k);
}
function setQueue(ty, q, sub) {
  S.ui.q[ty] = q; S.ui.sub[ty] = sub || ''; SHOW[ty] = LIST_STEP; cur.type = ty; S.ui.type = ty;
  const items = listItems(ty); const first = items.find(e => isOpen(ty, e, q)) || items[0];
  openEntity(ty, first ? first.k : null);
  const ql = $('#qlist'); if (ql && !first) ql.scrollTop = 0;
}
function setCorpus(c) {          // a view: the lists, counts and passages follow; decisions and the export do not
  S.ui.corpus = Math.max(0, Math.min(3, +c || 0));
  for (const ty of TYPES) SHOW[ty] = LIST_STEP;
  save();
  if (cur.type === 'home') refresh(); else openType(cur.type);
}
function setLang(l) { LANG = l === 'en' ? 'en' : 'de'; S.ui.lang = LANG; for (const ty of TYPES) for (const e of ENTS[ty]) delete e._st; save(); refresh(); }
function setTheme(th) { document.documentElement.dataset.theme = th === 'dark' ? 'dark' : 'light'; try { localStorage.setItem(LS + '-theme', document.documentElement.dataset.theme); } catch (e) { /* private mode */ } }

// ---------------------------------------------------------------- dialogs
const closeModal = () => $('#ovModal').classList.remove('show');
function showExport() {
  const nEnt = TYPES.reduce((a, ty) => a + Object.keys(S.ent[ty]).length, 0), nForm = TYPES.reduce((a, ty) => a + Object.keys(S.form[ty]).length, 0);
  $('#modal').innerHTML = '<button class="nbtn x" data-close="1">' + esc(t('btn.close')) + '</button><h2>' + esc(t('ex.title')) + '</h2><p>' + esc(t('ex.n', fmt(nEnt), fmt(nForm))) + '</p>'
    + '<p><label>' + esc(t('ex.who')) + '<br><input type="text" class="exwho" id="who" value="' + esc(S.who || '') + '" style="margin-top:4px;width:260px"></label></p>'
    + '<div class="row"><button class="nbtn primary" id="exZip">' + esc(t('ex.zip')) + '</button><button class="nbtn" id="exJson">' + esc(t('ex.json')) + '</button><button class="nbtn" id="exLoad">' + esc(t('ex.load')) + '</button></div>'
    + '<p class="small">' + t('ex.files') + '</p><p class="small muted">' + esc(t('ex.loadhint')) + '</p><h3>' + esc(t('ex.preview')) + '</h3><pre id="exPre">' + esc(exportIdentities().split('\n').slice(0, 30).join('\n')) + '</pre>';
  $('#ovModal').classList.add('show');
  const need = () => { if (S.who) return true; toast(t('ex.needwho'), 3000); $('#who').focus(); return false; };
  $('#who').oninput = ev => { S.who = ev.target.value.trim(); save(); $('#exPre').textContent = exportIdentities().split('\n').slice(0, 30).join('\n'); };
  $('#exZip').onclick = () => { if (!need()) return; download('laubmann_verknuepfungen_' + whoSlug() + '_' + stampName() + '.zip', makeZip(exportFiles())); S.n = 0; save(); };
  $('#exJson').onclick = () => { if (!need()) return; download('link_progress_' + whoSlug() + '_' + stampName() + '.json', new Blob([progressJSON()], { type: 'application/json' })); };
  $('#exLoad').onclick = () => $('#fileImport').click();
}
function showHelp() {
  $('#modal').innerHTML = '<button class="nbtn x" data-close="1">' + esc(t('btn.close')) + '</button><h2>' + esc(t('help.title')) + '</h2><p>' + esc(t('home.lead')) + '</p><h3>' + esc(t('home.h.queues')) + '</h3><ul>'
    + QUEUES.map(q => '<li><b>' + esc(t('q.' + q)) + '</b> — ' + esc(t('q.' + q + '.tip')) + '</li>').join('') + '</ul><h3>' + esc(t('home.h.thresh')) + '</h3><p>' + esc(t('home.thresh', dec2(D.thresholds.conf), D.thresholds.agree)) + '</p>'
    + '<h3>' + esc(t('home.h.how')) + '</h3><ol>' + t('home.how') + '</ol><h3>' + esc(t('home.h.keys')) + '</h3><p class="kbdrow">' + t('home.keys') + '</p>';
  $('#ovModal').classList.add('show');
}
$('#fileImport').addEventListener('change', async ev => {
  const f = ev.target.files[0]; if (!f) return; ev.target.value = '';
  try {
    const j = /\.zip$/i.test(f.name) ? await readZipJSON(await f.arrayBuffer()) : JSON.parse(await f.text());
    const [n, lost] = importAny(j); closeModal(); toast(t('im.done', fmt(n)) + (lost ? ' · ' + t('im.skipped', fmt(lost)) : ''), 4500);
  } catch (e) { toast(t('im.fail', e.message), 5000); }
});

// ---------------------------------------------------------------- events
document.addEventListener('click', ev => {
  const x = ev.target; const ty = cur.type;
  if (x.id === 'ovModal' || x.closest('[data-close]')) return closeModal();
  if (x.closest('.modal')) return;
  if (x.closest('#brand')) return openType('home');
  const tt = x.closest('[data-type]'); if (tt) return openType(tt.dataset.type);
  const cr = x.closest('[data-corpus]'); if (cr) { if (cr.blur) cr.blur(); return setCorpus(+cr.dataset.corpus); }
  const hq = x.closest('[data-home]'); if (hq) return setQueue(hq.dataset.home, hq.dataset.hq);
  const qc = x.closest('.chip[data-q]'); if (qc) return setQueue(ty, qc.dataset.q);
  const sc = x.closest('.chip[data-sub]'); if (sc) return setQueue(ty, 'suggest', S.ui.sub[ty] === sc.dataset.sub ? '' : sc.dataset.sub);
  const qi = x.closest('.qi'); if (qi) return openEntity(ty, qi.dataset.key, false);
  if (x.closest('[data-more]')) { SHOW[ty] = (SHOW[ty] || LIST_STEP) + LIST_STEP; return renderList(); }
  const op = x.closest('[data-open]'); if (op) { ev.preventDefault(); const e2 = BYK[ty].get(op.dataset.open); if (e2) { S.ui.q[ty] = e2.mg && curQ(ty) === 'merge' ? 'merge' : e2.q; S.ui.sub[ty] = ''; S.ui.find[ty] = ''; openEntity(ty, e2.k); } return; }
  const nv = x.closest('[data-nav]'); if (nv) return nav(nv.dataset.nav);
  const gr = x.closest('[data-grade]'); if (gr) { const e = curEnt(); gradePick = gr.dataset.grade; const d = e && entDec(ty, e); if (d && d.d === 'link') return setEnt(ty, e, Object.assign({}, d, { grade: gradePick, t: new Date().toISOString() })); return renderActbar(); }
  const ac = x.closest('[data-act]'); if (ac) return act(ac.dataset.act);
  const go = x.closest('[data-go]'); if (go) return runSearch(go.dataset.go);
  const fa = x.closest('[data-formacc]'); if (fa) { const e = curEnt(); const f = e.forms.find(z => z.f === fa.dataset.formacc); const o = f && formSuggestionOp(ty, e, f); if (o) commit(f.f + ': ' + t('dec.link.accept'), [o]); return; }
  const fc = x.closest('[data-formclear]'); if (fc) return commit(fc.dataset.formclear + ': ' + t('toast.cleared'), [['form', ty, cf(fc.dataset.formclear), null]]);
  if (x.closest('[data-fclose]')) { panelForm = null; return renderCard(); }
  const fr = x.closest('#formpanel .r[data-ent]'); if (fr) return pickFormTarget(fr.dataset.ent);
  const tb = x.closest('.tb[data-form]'); if (tb) return toggleForm(tb.dataset.form, tb.dataset.fv);
  if (x.closest('a.ext')) return;
  const mg = x.closest('.cand[data-mg]'); if (mg) { const e = curEnt(); return mergeSame(ty, e, mg.dataset.mg, mg.dataset.to); }
  const cd = x.closest('.cand[data-cand]'); if (cd) return void pickCand(+cd.dataset.cand);
  const mn = x.closest('.men'); if (mn) return showMention(+mn.dataset.men);
  const pg = x.closest('[data-page]'); if (pg) { scan.p = +pg.dataset.page; return renderScan(); }
  if (x.id === 'scanclose') { S.ui.scan = false; save(); return $('#main').classList.add('noscan'); }
  if (x.id === 'scanzoom') { scan.zoom = (scan.zoom + 1) % 3; return renderScan(); }
  if (x.id === 'scanprev' || x.id === 'scannext') { const i = scan.pages.indexOf(scan.p); const j = i + (x.id === 'scanprev' ? -1 : 1); if (i >= 0 && scan.pages[j] != null) { scan.p = scan.pages[j]; renderScan(); } return; }
  if (x.id === 'btnUndo') return undo();
  if (x.id === 'btnLang') return setLang(LANG === 'en' ? 'de' : 'en');
  if (x.id === 'btnTheme') return setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  if (x.id === 'btnHelp') return showHelp();
  if (x.id === 'btnExport') return showExport();
  if (x.id === 'btnImport') return $('#fileImport').click();
});
document.addEventListener('input', ev => {
  const x = ev.target; const ty = cur.type;
  if (x.id === 'qsearch') { S.ui.find[ty] = x.value; SHOW[ty] = LIST_STEP; clearTimeout(x._t); x._t = setTimeout(() => { save(); renderList(); }, 200); return; }
  if (x.id === 'note') { const e = curEnt(); const d = e && entDec(ty, e); if (d) { d.note = x.value; save(); } return; }
  if (x.id === 'sInput') {
    if (ty === 'taxon') { const l = localTaxa(x.value); searchRes = x.value.trim() ? l : null; updateCands(); }
    if (ty === 'habitat') { const l = localEunis(x.value); searchRes = x.value.trim() ? l : null; updateCands(); }
  }
});
document.addEventListener('keydown', ev => {
  const x = ev.target; const tag = (x.tagName || '').toLowerCase(); const typing = tag === 'input' || tag === 'textarea' || tag === 'select';
  const modal = $('#ovModal').classList.contains('show');
  if (ev.key === 'Escape') {
    if (modal) return closeModal();
    if (typing) { x.blur(); return; }
    if (panelForm) { panelForm = null; return renderCard(); }
    if (searchRes) return runSearch('clear');
    return;
  }
  if (typing) {
    if (ev.key === 'Enter') {
      if (x.id === 'sInput') { ev.preventDefault(); const b = $('#sGo'); if (b) runSearch(b.dataset.go); else x.blur(); }
      else if (x.id === 'fInput') { ev.preventDefault(); const r = $('#formpanel .r[data-ent]'); if (r) r.click(); }
      else if (x.id === 'note' || x.id === 'qsearch') x.blur();
      else if (x.id === 'pqid' || x.id === 'pgnd') { ev.preventDefault(); runSearch('ids'); }
      else if (x.id === 'plat' || x.id === 'plon' || x.id === 'punc') { ev.preventDefault(); runSearch('coords'); }
    }
    return;
  }
  if (ev.ctrlKey || ev.metaKey || ev.altKey || modal) return;
  if (ev.key === '?') return showHelp();
  const ty = cur.type; if (ty === 'home') return;
  const k = ev.key.toLowerCase(); const e = curEnt();
  if (ev.key === '/') { ev.preventDefault(); const q = $('#qsearch'); if (q) { q.focus(); q.select(); } return; }
  if (ev.key === 'ArrowDown' || ev.key === 'PageDown') { ev.preventDefault(); return nav('next'); }
  if (ev.key === 'ArrowUp' || ev.key === 'PageUp') { ev.preventDefault(); return nav('prev'); }
  if (ev.key === 'Enter') { ev.preventDefault(); return nav('open'); }
  if (k === 'z') { ev.preventDefault(); return undo(); }
  if (k === 's') { ev.preventDefault(); S.ui.scan = !S.ui.scan; save(); $('#main').classList.toggle('noscan', !S.ui.scan); if (S.ui.scan) renderScan(); return; }
  if (!e) return;
  if (/^[1-9]$/.test(ev.key)) { if (pickDigit(+ev.key)) ev.preventDefault(); return; }
  const merge = curQ(ty) === 'merge' && e.mg;
  const map1 = merge ? { j: 'mgsame', n: 'mgdiff' } : { j: 'confirm', a: 'other', n: 'nolink', x: 'none', u: 'unsure', v: 'accept', r: 'revert' };
  if (k in map1) { ev.preventDefault(); act(map1[k]); }      // preventDefault first: the key must not reach the search field it may focus
});
window.addEventListener('resize', () => placeHl());
(function () {                                               // scan pane resize
  const grip = $('#grip'); let drag = false;
  grip.addEventListener('mousedown', e => { drag = true; e.preventDefault(); });
  document.addEventListener('mousemove', e => { if (!drag) return; const w = Math.min(65, Math.max(20, (window.innerWidth - e.clientX) / window.innerWidth * 100)); document.documentElement.style.setProperty('--scanw', w + 'vw'); placeHl(); });
  document.addEventListener('mouseup', () => { drag = false; });
})();

// ---------------------------------------------------------------- start
D = await loadData();
indexData();
try { const st = JSON.parse(localStorage.getItem(LS) || 'null'); if (st && typeof st === 'object') S = st; } catch (e) { /* fresh state */ }
normalizeState();
LANG = S.ui.lang === 'en' ? 'en' : 'de';
let theme0 = 'light'; try { theme0 = localStorage.getItem(LS + '-theme') || 'light'; } catch (e) { /* private mode */ }
document.documentElement.dataset.theme = theme0 === 'dark' ? 'dark' : 'light';
window.__lc = { D, ENTS, BYK, FORMK, cur, STR, MISSING, HIST, view, scan, get S() { return S; }, get LANG() { return LANG; }, openEntity, openType, setQueue, setLang, setTheme, setCorpus, corpus, corpusItems, listItems, queueCounts, typeProgress, entDone, mergeDone,
  idRows, auditRows, exportFiles, exportIdentities, progressJSON, importAny, act, cf, refresh };
cur.type = TYPES.includes(S.ui.type) ? S.ui.type : 'home';
$('#loading').remove();
if (cur.type === 'home') refresh(); else openType(cur.type);
