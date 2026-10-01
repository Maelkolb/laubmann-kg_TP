// ---------------------------------------------------------------- line snippets and scan pane
const thumb = id => 'https://drive.google.com/thumbnail?id=' + id + '&sz=w1600';
function snipHtml(loc, ctx) {
  if (!Array.isArray(loc) || loc.length < 5) return '';
  const [p, x0, y0, x1, y1] = loc; const u = loc.length > 5 ? loc[5] : 1; const g = PG[p]; if (!g || !DRIVE[g[0]] || !g[5]) return '';
  const lh = Math.max(24, (y1 - y0) / Math.max(1, Math.round((y1 - y0) / 60))); const c = (ctx || 0.9) * (u ? 2.4 : 1);
  const top = Math.max(0, Math.round(y0 - lh * c)), bot = Math.min(g[6], Math.round(y1 + lh * c));
  const fx = loc.length > 7 ? loc[6] + ',' + loc[7] : '';
  return '<div class="snip' + (u ? ' approx' : '') + '" data-p="' + p + '" data-b="' + x0 + ',' + top + ',' + x1 + ',' + bot + '" data-hl="' + y0 + ',' + y1 + '" data-fx="' + fx + '" title="' + esc(u ? t('snip.approxTip') + ' · ' + t('snip.tip') : t('snip.tip')) + '"></div>';
}
const snipObs = 'IntersectionObserver' in window ? new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { fillSnip(e.target); snipObs.unobserve(e.target); } }, { rootMargin: '400px' }) : null;
function fillSnip(el) {
  if (el.dataset.done) return; el.dataset.done = 1;
  const g = PG[+el.dataset.p]; const [x0, top, x1, bot] = el.dataset.b.split(',').map(Number); const [h0, h1] = el.dataset.hl.split(',').map(Number);
  const W = el.clientWidth || 700; const s = W / (x1 - x0);
  el.style.height = Math.round((bot - top) * s) + 'px';
  const img = new Image(); img.alt = ''; img.style.width = Math.round(g[5] * s) + 'px'; img.style.left = Math.round(-x0 * s) + 'px'; img.style.top = Math.round(-top * s) + 'px';
  img.onerror = () => { el.classList.add('fail'); el.innerHTML = t('snip.fail'); el.style.height = 'auto'; };
  img.src = thumb(DRIVE[g[0]]);
  const band = document.createElement('i'); band.style.top = Math.round((h0 - top) * s) + 'px'; band.style.height = Math.round((h1 - h0) * s) + 'px';
  el.appendChild(img); el.appendChild(band);
  if (el.dataset.fx) { const [f0, f1] = el.dataset.fx.split(',').map(Number); const seg = document.createElement('i'); seg.className = 'seg'; seg.style.top = band.style.top; seg.style.height = band.style.height; seg.style.left = Math.round(f0 * (x1 - x0) * s) + 'px'; seg.style.width = Math.max(8, Math.round((f1 - f0) * (x1 - x0) * s)) + 'px'; el.appendChild(seg); }
  if (el.classList.contains('approx')) { const lab = document.createElement('span'); lab.className = 'approxlab'; lab.textContent = t('snip.approx'); el.appendChild(lab); }
}
function wireSnips(root) { $$('.snip:not([data-done])', root).forEach(el => snipObs ? snipObs.observe(el) : fillSnip(el)); }
const scan = { e: null, p: -1, hl: null, zoom: 0 };
function showScan(_, e, hl, keepHidden) {
  if (!e) return; scan.e = e; scan.hl = hl || null;
  const pages = e[8] || []; scan.p = hl && hl.length >= 5 && pages.includes(hl[0]) ? hl[0] : hl && hl.length >= 5 ? hl[0] : (pages[0] ?? -1);
  if (!keepHidden) $('#main').classList.remove('noscan');
  renderScan();
}
function renderScan() {
  const e = scan.e; if (!e) return; const pages = e[8] || [];
  $('#scantitle').innerHTML = (scan.p >= 0 ? esc(pageLabel(scan.p)) : t('scan.noPage')) + ' <span>· ' + esc(e[0]) + (pages.length > 1 ? ' · ' + t('scan.pageOf', (pages.indexOf(scan.p) + 1 || '?'), pages.length) : '') + '</span>';
  $('#scanpages').innerHTML = pages.map((p, k) => '<button class="nbtn' + (p === scan.p ? ' on' : '') + '" data-page="' + p + '">' + (k + 1) + '</button>').join('');
  const body = $('#scanbody');
  if (scan.p < 0) { body.innerHTML = '<div class="msg">' + t('scan.noPageKnown') + '</div>'; return; }
  const g = PG[scan.p]; const id = DRIVE[g[0]]; $('#scanopen').href = id ? 'https://drive.google.com/file/d/' + id + '/view' : '#';
  if (!id) { body.innerHTML = '<div class="msg">' + t('scan.noScan', esc(g[0])) + '</div>'; return; }
  body.innerHTML = '<div class="scanwrap' + (scan.zoom ? ' z' + scan.zoom : '') + '" id="scanwrap"><img id="scanimg" alt="" src="' + thumb(id) + '"></div>';
  const img = $('#scanimg'); img.onerror = () => { body.innerHTML = '<div class="msg">' + t('scan.fail') + ' <a href="' + $('#scanopen').href + '" target="_blank" rel="noopener" style="color:#9cf">' + t('scan.openDrive') + '</a></div>'; };
  img.onload = () => placeHl();
}
function placeHl() {
  const img = $('#scanimg'); const wrap = $('#scanwrap'); if (!img || !wrap || !scan.hl || scan.hl[0] !== scan.p || scan.hl.length < 5) return;
  const g = PG[scan.p]; const s = img.clientWidth / (g[5] || 1); const [, x0, y0, x1, y1, u] = scan.hl;
  const box = document.createElement('div'); box.className = 'hlbox' + (u ? ' approx' : ''); box.style.left = (x0 * s - 4) + 'px'; box.style.top = (y0 * s - 4) + 'px'; box.style.width = ((x1 - x0) * s + 8) + 'px'; box.style.height = ((y1 - y0) * s + 8) + 'px';
  wrap.appendChild(box);
  if (scan.hl.length > 7) { const seg = document.createElement('div'); seg.className = 'hlseg'; seg.style.top = box.style.top; seg.style.height = box.style.height; seg.style.left = ((x0 + scan.hl[6] * (x1 - x0)) * s - 2) + 'px'; seg.style.width = Math.max(10, (scan.hl[7] - scan.hl[6]) * (x1 - x0) * s + 4) + 'px'; wrap.appendChild(seg); }
  const sb = $('#scanbody'); sb.scrollTop = Math.max(0, y0 * s - sb.clientHeight * 0.35);
}
function scanFor(ei, tt, mi) { const e = E[ei]; if (!e) return; const m = mi != null && tt ? MEN[tt][mi] : null; const it = ITEMS[cur.i]; showScan(null, e, m && Array.isArray(m[4]) ? m[4] : (it && it.t === 'tc' && it.ei === ei ? it.hl : null)); }

// ---------------------------------------------------------------- map (places)
let map = null, pick = null;
function initMap(it) {
  const el = $('#map'); if (!el || typeof L === 'undefined') return;
  if (map) { try { map.remove(); } catch (e) { } map = null; }
  map = L.map(el, { zoomControl: true, attributionControl: false });
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', { maxZoom: 17 }).addTo(map);
  const pts = [];
  const mk = (lat, lon, color, title, r) => { const c = L.circleMarker([lat, lon], { radius: r || 8, color: '#fff', weight: 1.5, fillColor: color, fillOpacity: .95 }).addTo(map).bindTooltip(title); pts.push([lat, lon]); return c; };
  if (it.cur.lat != null) mk(it.cur.lat, it.cur.lon, '#c0392b', t('map.cur') + ': ' + it.label + ' (' + it.cur.lat.toFixed(3) + ', ' + it.cur.lon.toFixed(3) + ')');
  if (it.now && it.now.lat != null && !(it.now.lat === it.cur.lat && it.now.lon === it.cur.lon)) mk(it.now.lat, it.now.lon, '#7a2a8a', t('map.now') + ': ' + it.now.label, 6);
  if (it.prop && it.prop.lat != null) mk(it.prop.lat, it.prop.lon, '#0e6a70', t('map.prop') + ': ' + (it.prop.name || ''));
  for (const c of it.cands || []) if (!(it.prop && c.lat === it.prop.lat && c.lon === it.prop.lon)) mk(c.lat, c.lon, '#2f5f9a', t('map.cand') + ': ' + (c.name || ''), 6);
  for (const a of it.anchors || []) if (a.lat != null) mk(a.lat, a.lon, '#888', t('map.anchor') + ': ' + a.place + ' (' + a.n + ')', 6);
  if (it.hint_ll) mk(it.hint_ll[0], it.hint_ll[1], '#e67e22', t('map.hint') + ': ' + it.hint, 6);
  for (const r of it.scan || []) if (r.lat != null && !(it.prop && it.prop.lat === +r.lat && it.prop.lon === +r.lon)) mk(+r.lat, +r.lon, '#b35a1a', t('map.scan') + ': ' + (r.place || r.reading) + (r.region ? ' (' + r.region + ')' : ''), 6);
  const d = dec(it); if (d && d.target && d.target.lat != null) pick = L.marker([d.target.lat, d.target.lon]).addTo(map).bindTooltip(t('map.own')); else pick = null;
  if (pts.length) { const b = L.latLngBounds(pts.map(p => L.latLng(p[0], p[1]))); map.fitBounds(b.pad(0.3), { maxZoom: 12 }); } else map.setView([48.14, 11.58], 8);
  map.on('click', ev => { if (!$('#other .otherplace')) return; setPick(ev.latlng.lat, ev.latlng.lng); });
}
function setPick(lat, lon) { if (!map) return; if (pick) pick.setLatLng([lat, lon]); else pick = L.marker([lat, lon]).addTo(map).bindTooltip(t('map.own')); const la = $('#plat'), lo = $('#plon'); if (la) la.value = lat.toFixed(5); if (lo) lo.value = lon.toFixed(5); }

// ---------------------------------------------------------------- decisions
function act(it, k) {
  otherScope = null;
  if (k === 'o' || k === 'e') return openOther(it);
  if (k === 'a' && it.q === 'change' && it.t === 'place' && it.k === 'unlocated-nocand') return openOther(it);
  setDec(it, { d: k }, decLabel(it, { d: k }) + ': ' + (it.label || it.id));
  afterDecision();
}
function afterDecision() { if (S.ui.adv) { const items = filtered(cur.tab); const pos = items.indexOf(ITEMS[cur.i]); const nx = items.slice(pos + 1).find(x => !isDone(x)); if (nx) { cur.i = nx.i; S.ui.sel[cur.tab] = nx.key; save(); refresh(true); } } }
let otherScope = null;
function chooseTarget(it, target, label, code) {
  const sc = otherScope; otherScope = null; const el = $('#other'); if (el) el.innerHTML = '';
  if (sc && sc.name != null) return setSub(it, 'names', nameKey(ttOf(it), sc.name), { d: 'o', target }, t('log.nameTo', FORMS[ttOf(it)][sc.name][0], label));
  if (sc && sc.men != null) return setSub(it, 'mens', menKey(ttOf(it), sc.men), { d: 'o', target, written: MEN[ttOf(it)][sc.men] ? FORMS[ttOf(it)][MEN[ttOf(it)][sc.men][0]][0] : '' }, t('log.passageTo', label));
  setDec(it, { d: code || 'o', target }, t(code === 'e' ? 'log.edit' : 'log.other', label)); afterDecision();
}
function openOther(it, scope) {
  const el = $('#other'); if (!el) return; if (el.innerHTML && !scope) { el.innerHTML = ''; otherScope = null; return; }
  otherScope = scope || null;
  const tt = ttOf(it);
  const scopeLabel = scope && scope.name != null ? '<div class="bd alt big" style="margin-bottom:6px">' + t('o.forName', esc(FORMS[tt][scope.name][0])) + '</div>' : scope && scope.men != null ? '<div class="bd alt big" style="margin-bottom:6px">' + t('o.forPassage', esc(E[MEN[tt][scope.men][1]][0])) + '</div>' : '';
  if (it.t === 'tc') {
    const pre = (dec(it) && dec(it).target && dec(it).target.value) || (it.m && it.m.better) || it.new;
    el.innerHTML = '<div class="panel"><h5>' + t('o.tcTitle') + '</h5><div class="small muted" style="margin-bottom:5px">' + t('o.tcHint') + '</div><textarea id="tval" rows="3" style="width:100%;font-family:var(--serif);font-size:15px;border:1px solid var(--line2);border-radius:6px;padding:6px 8px;background:var(--panel);color:var(--ink)">' + esc(pre) + '</textarea>'
      + '<div class="row" style="margin-top:6px"><button class="nbtn" id="tfOld">' + t('o.tcOld') + '</button><button class="nbtn" id="tfNew">' + t('o.tcNew') + '</button>' + (it.m && it.m.better ? '<button class="nbtn" id="tfBetter">' + t('o.tcBetter') + '</button>' : '') + '<span class="sp"></span><button class="nbtn primary" id="tok">' + t('o.take') + ' ⏎</button></div></div>';
    const ta = $('#tval'); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
    $('#tfOld').onclick = () => { ta.value = it.label; ta.focus(); }; $('#tfNew').onclick = () => { ta.value = it.new; ta.focus(); }; if ($('#tfBetter')) $('#tfBetter').onclick = () => { ta.value = it.m.better; ta.focus(); };
    $('#tok').onclick = () => { const v = ta.value; if (!v.trim()) return toast(t('o.tcEmpty')); chooseTarget(it, { value: v }, v, 'e'); };
    ta.onkeydown = ev => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); $('#tok').click(); } };
    return;
  }
  if (it.t === 'qa') {
    const pre = (dec(it) && dec(it).target && dec(it).target.fix) || '';
    el.innerHTML = '<div class="panel"><h5>' + t('o.qaTitle') + '</h5><textarea id="qfix" rows="2" style="width:100%;border:1px solid var(--line2);border-radius:6px;padding:6px 8px;background:var(--panel);color:var(--ink)" placeholder="' + esc(t('o.qaPh')) + '">' + esc(pre) + '</textarea><div class="row" style="margin-top:6px"><span class="sp"></span><button class="nbtn primary" id="qok">' + t('o.take') + ' ⏎</button></div></div>';
    const ta = $('#qfix'); ta.focus();
    $('#qok').onclick = () => { const v = ta.value.trim(); if (!v) return toast(t('o.qaEmpty')); chooseTarget(it, { fix: v }, v); };
    ta.onkeydown = ev => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); $('#qok').click(); } };
    return;
  }
  if (it.t === 'habitat') {
    el.innerHTML = scopeLabel + '<div class="panel"><h5>' + t('o.habTitle') + '</h5><div class="row"><input type="text" class="grow" id="hsearch" placeholder="' + esc(t('o.habPh')) + '" autocomplete="off"><label class="small">' + t('o.habMatch') + ' <select id="hmatch"><option value="exact">exact</option><option value="close" selected>close</option><option value="broad">broad</option></select></label><button class="nbtn" id="hnone">' + t('b.habNone') + '</button></div><div class="res" id="hres"></div><div class="hint">' + t('o.habHint') + '</div></div>';
    const inp = $('#hsearch'); inp.focus();
    const show = () => { const q = fold(inp.value.trim()); const list = D.EUNIS.filter(e => !q || fold(e[0]).startsWith(q) || fold(e[1]).includes(q)).sort((a, b) => a[2] - b[2] || a[0].localeCompare(b[0])).slice(0, 60);
      $('#hres').innerHTML = list.map((e, k) => '<div class="r" data-pick="' + k + '"><span class="k">' + (k < 9 ? k + 1 : '') + '</span><b>' + esc(e[0]) + '</b> ' + esc(e[1]) + ' <small>' + t('hab.level', e[2]) + '</small></div>').join('') || '<div class="r muted">' + t('o.wdNone') + '</div>';
      $$('#hres [data-pick]').forEach(x => x.onclick = () => { const e = list[+x.dataset.pick]; chooseTarget(it, { code: e[0], label: e[1], match: $('#hmatch').value }, e[0] + ' ' + e[1]); }); };
    inp.oninput = show; show();
    $('#hnone').onclick = () => { el.innerHTML = ''; setDec(it, { d: 'k' }, t('log.habNone', it.label)); afterDecision(); };
    return;
  }
  if (tt === 'taxon' || tt === 'mention') {
    el.innerHTML = scopeLabel + '<div class="panel"><h5>' + (it.t === 'mention' || (scope && scope.men != null) ? t('o.taxonMention') : t('o.taxonTitle')) + '</h5><div class="row"><input type="text" class="grow" id="tsearch" placeholder="' + esc(t('o.taxonPh')) + '" autocomplete="off"><button class="nbtn" id="tgbif">' + t('o.gbif') + '</button>' + (it.t === 'mention' ? '<button class="nbtn" id="tdrop">' + t('o.dropPassage') + '</button>' : '<button class="nbtn" id="tnone">' + t('o.notBird') + '</button>') + '</div><div class="res" id="tres"></div><div class="hint">' + t('o.taxonHint') + '</div></div>';
    const inp = $('#tsearch'); inp.focus();
    const local = q => { q = fold(q); if (!q) return []; const sc = x => { const a = fold(x[0]), b = fold(x[1]); return a === q || b === q ? 0 : a.startsWith(q) || b.startsWith(q) ? 1 : a.includes(q) || b.includes(q) ? 2 : 9; }; return TAXA.map(x => [sc(x), x]).filter(p => p[0] < 9).sort((p, r) => p[0] - r[0] || p[1][0].localeCompare(r[1][0])).slice(0, 9).map(p => ({ label: p[1][0], sci: p[1][1], key: p[1][2], rank: p[1][3], src: t('o.graph') })); };
    const show = list => { $('#tres').innerHTML = list.map((r, k) => '<div class="r" data-k="' + k + '"><span class="k">' + (k + 1) + '</span><b>' + esc(r.label) + '</b> <i>' + esc(r.sci) + '</i><small>' + esc(r.rank || '') + ' · ' + esc(r.src) + ' · ' + esc(r.key) + '</small></div>').join(''); $('#tres').onclick = ev => { const r = ev.target.closest('.r'); if (!r) return; const x = list[+r.dataset.k]; chooseTarget(it, { label: x.label, sci: x.sci, key: x.key, rank: x.rank }, x.label); }; el._list = list; };
    inp.oninput = () => show(local(inp.value));
    const gbif = async () => { const q = inp.value.trim(); if (!q) return; $('#tres').innerHTML = '<div class="r muted">' + t('o.gbifWait') + '</div>'; try { const r = await fetch('https://api.gbif.org/v1/species/search?q=' + encodeURIComponent(q) + '&datasetKey=d7dddbf4-2cf0-4f39-9b2a-bb099caae36c&status=ACCEPTED&limit=12&class=Aves'); const j = await r.json(); const list = (j.results || []).map(x => ({ label: (x.vernacularNames || []).find(v => v.language === 'deu')?.vernacularName || x.canonicalName, sci: x.canonicalName, key: String(x.key), rank: lc(x.rank), src: 'GBIF' })); show(list.length ? list : local(q)); if (!list.length) toast(t('o.gbifNone')); } catch (e) { toast(t('o.gbifDown')); show(local(q)); } };
    $('#tgbif').onclick = gbif; inp.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); gbif(); } };
    if ($('#tnone')) $('#tnone').onclick = () => { if (otherScope && otherScope.name != null) { const fi = otherScope.name; otherScope = null; el.innerHTML = ''; return setSub(it, 'names', nameKey('taxon', fi), { d: 'k' }, t('log.nameK', FORMS.taxon[fi][0])); } if (otherScope && otherScope.men != null) { const mi = otherScope.men; otherScope = null; el.innerHTML = ''; return setSub(it, 'mens', menKey('taxon', mi), { d: 'n', written: FORMS.taxon[MEN.taxon[mi][0]][0] }, t('log.passageDrop')); } setDec(it, { d: 'k' }, t('log.notBird', it.label)); afterDecision(); };
    if ($('#tdrop')) $('#tdrop').onclick = () => chooseTarget(it, { drop: true, none: true }, t('log.drop'));
  } else if (tt === 'person') {
    const cands = it.cands || [];
    el.innerHTML = scopeLabel + '<div class="panel"><h5>' + t('o.personTitle') + '</h5><div class="cands">' + cands.slice(0, 9).map((c, k) => '<div class="cand" data-pick="' + k + '"><span class="k">' + (k + 1) + '</span><div><div class="cl">' + esc(c.label) + (c.born || c.died ? ' <span class="muted">(' + esc(c.born || '?') + '–' + esc(c.died || '?') + ')</span>' : '') + '</div><div class="cd">' + esc(c.desc) + '</div></div><span class="ci">' + esc(c.qid) + (c.gnd ? ' · GND ' + esc(c.gnd) : '') + '</span></div>').join('') + '</div><div class="row" style="margin-top:8px"><input type="text" class="grow" id="psearch" placeholder="' + esc(t('o.wdPh')) + '" value="' + esc(scope ? '' : it.label) + '"><button class="nbtn" id="pwd">' + t('o.wd') + '</button></div><div class="res" id="pres"></div><div class="row" style="margin-top:8px"><input type="text" id="pqid" placeholder="' + esc(t('o.qid')) + '" size="12"><input type="text" id="pgnd" placeholder="' + esc(t('o.gnd')) + '" size="14"><button class="nbtn primary" id="pok">' + t('o.link') + '</button><button class="nbtn" id="pnone">' + t('o.noLink') + '</button></div><div class="hint">' + t('o.personHint') + '</div></div>';
    $$('#other [data-pick]').forEach(x => x.onclick = () => { const c = cands[+x.dataset.pick]; chooseTarget(it, { qid: c.qid, gnd: c.gnd || '', label: c.label }, c.label); });
    const wd = async () => { const q = $('#psearch').value.trim(); if (!q) return; $('#pres').innerHTML = '<div class="r muted">' + t('o.wdWait') + '</div>'; try { const r = await fetch('https://www.wikidata.org/w/api.php?action=wbsearchentities&search=' + encodeURIComponent(q) + '&language=de&uselang=de&format=json&limit=10&origin=*'); const j = await r.json(); const list = j.search || []; $('#pres').innerHTML = list.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.label) + '</b><small>' + esc(x.description || '') + ' · ' + esc(x.id) + '</small></div>').join('') || '<div class="r muted">' + t('o.wdNone') + '</div>'; $('#pres').onclick = ev => { const r = ev.target.closest('.r'); if (!r || r.dataset.k == null) return; const x = list[+r.dataset.k]; $('#pqid').value = x.id; $('#pqid').dataset.label = x.label; }; } catch (e) { toast(t('o.wdDown')); } };
    $('#pwd').onclick = wd; $('#psearch').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); wd(); } };
    $('#pok').onclick = () => { const qid = $('#pqid').value.trim(), gnd = $('#pgnd').value.trim(); if (!qid && !gnd) return toast(t('o.needId')); chooseTarget(it, { qid, gnd, label: $('#pqid').dataset.label || qid || ('GND ' + gnd) }, $('#pqid').dataset.label || qid || gnd); };
    $('#pnone').onclick = () => { if (otherScope) { otherScope = null; el.innerHTML = ''; return toast(t('o.useMini')); } setDec(it, { d: 'k' }, t('log.noLink', it.label)); afterDecision(); };
    $('#psearch').focus();
  } else if (tt === 'place') {
    const cands = it.cands || (it.cands = []);
    const rc = (it.scan || []).filter(r => r.lat != null).map(r => ({ id: 'r', name: (r.place || r.reading) + (r.region ? ', ' + r.region : ''), type: t('box.scanType'), lat: +r.lat, lon: +r.lon, km: null, qid: '', osm: '' }));
    for (const c of rc) if (!cands.some(x => x.lat === c.lat && x.lon === c.lon)) cands.push(c);
    el.innerHTML = scopeLabel + '<div class="panel otherplace"><h5>' + t('o.placeTitle') + '</h5>' + (cands.length ? '<div class="cands">' + cands.slice(0, 9).map((c, k) => '<div class="cand" data-pick="' + k + '"><span class="k">' + (k + 1) + '</span><div><div class="cl">' + esc(c.name) + '</div><div class="cd">' + esc(c.type || '') + (c.km != null ? ' · ' + t('box.kmAnchor', c.km) : '') + '</div></div><span class="ci">' + c.lat.toFixed(3) + ', ' + c.lon.toFixed(3) + '</span></div>').join('') + '</div>' : '')
      + '<div class="row" style="margin-top:8px"><input type="text" class="grow" id="lsearch" placeholder="' + esc(t('o.nomPh')) + '" value="' + esc(it.label) + '"><button class="nbtn" id="lnom">' + t('o.search') + '</button></div><div class="res" id="lres"></div>'
      + '<div class="row" style="margin-top:8px"><span class="small muted">' + t('o.orMap') + '</span><input type="text" id="plat" placeholder="' + t('o.lat') + '" size="10"><input type="text" id="plon" placeholder="' + t('o.lon') + '" size="10"><input type="number" id="punc" placeholder="' + t('o.unc') + '" value="' + esc(it.unc || 1000) + '" style="width:90px"><button class="nbtn" id="phint"' + (it.hint_ll ? '' : ' disabled') + '>' + t('o.hintCoords') + ' <kbd>H</kbd></button><button class="nbtn primary" id="lok">' + t('o.setLoc') + '</button><button class="nbtn" id="lnone">' + t('o.notPlace') + '</button></div><div class="hint">' + t('o.placeHint') + '</div></div>';
    $$('#other [data-pick]').forEach(x => x.onclick = () => { const c = cands[+x.dataset.pick]; chooseTarget(it, { lat: c.lat, lon: c.lon, name: c.name, qid: c.qid || '', osm: c.osm || '', unc: +($('#punc').value) || it.unc || 1000 }, c.name.split(',')[0]); });
    const nom = async () => { const q = $('#lsearch').value.trim(); if (!q) return; $('#lres').innerHTML = '<div class="r muted">' + t('o.nomWait') + '</div>'; try { const r = await fetch('https://nominatim.openstreetmap.org/search?q=' + encodeURIComponent(q) + '&format=jsonv2&limit=8&accept-language=de', { headers: { 'Accept': 'application/json' } }); const list = await r.json(); $('#lres').innerHTML = list.map((x, k) => '<div class="r" data-k="' + k + '"><b>' + esc(x.display_name.split(',')[0]) + '</b><small>' + esc(x.display_name) + ' · ' + esc(x.type) + '</small></div>').join('') || '<div class="r muted">' + t('o.nomNone') + '</div>'; $('#lres').onclick = ev => { const r = ev.target.closest('.r'); if (!r || r.dataset.k == null) return; const x = list[+r.dataset.k]; setPick(+x.lat, +x.lon); $('#plat').dataset.name = x.display_name; $('#plat').dataset.osm = x.osm_type ? x.osm_type + '/' + x.osm_id : ''; if (map) map.setView([+x.lat, +x.lon], 12); }; } catch (e) { toast(t('o.nomDown')); } };
    $('#lnom').onclick = nom; $('#lsearch').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); nom(); } };
    $('#phint').onclick = () => { if (it.hint_ll) { setPick(it.hint_ll[0], it.hint_ll[1]); if (map) map.setView(it.hint_ll, 12); } };
    $('#lok').onclick = () => { const lat = parseFloat($('#plat').value), lon = parseFloat($('#plon').value); if (isNaN(lat) || isNaN(lon)) return toast(t('o.needPick')); chooseTarget(it, { lat, lon, name: $('#plat').dataset.name || it.label, osm: $('#plat').dataset.osm || '', unc: +($('#punc').value) || 1000 }, lat.toFixed(3) + ', ' + lon.toFixed(3)); };
    $('#lnone').onclick = () => { if (otherScope) { otherScope = null; el.innerHTML = ''; return toast(t('o.useMini')); } setDec(it, { d: 'k' }, t('log.notPlace', it.label)); afterDecision(); };
    const d = dec(it); if (d && d.target && d.target.lat != null) { $('#plat').value = d.target.lat; $('#plon').value = d.target.lon; }
  } else if (tt === 'text') {
    el.innerHTML = '<div class="panel"><h5>' + t('o.textTitle') + '</h5><div class="row"><span class="muted">„' + esc(it.label) + '“ →</span><input type="text" class="grow" id="tval" value="' + esc(it.prop.value) + '" style="font-family:var(--serif);font-size:15px"><button class="nbtn primary" id="tok">' + t('o.take') + '</button></div></div>';
    $('#tval').focus(); $('#tok').onclick = () => { const v = $('#tval').value.trim(); if (!v) return; chooseTarget(it, { value: v }, v); }; $('#tval').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); $('#tok').click(); } };
  }
}
function pickDigit(it, n) { const el = $('#other'); if (!el || !el.innerHTML) return false; const c = $$('#other [data-pick]')[n - 1]; if (c) { c.click(); return true; } const r = $$('#tres .r')[n - 1]; if (r) { r.click(); return true; } return false; }

// ---------------------------------------------------------------- events
function nav(dir) {
  const items = filtered(cur.tab); const pos = items.indexOf(ITEMS[cur.i]); let nx = null;
  if (dir === 'prev') nx = items[pos - 1]; else if (dir === 'next') nx = items[pos + 1]; else nx = items.slice(pos + 1).find(x => !isDone(x)) || items.slice(0, Math.max(0, pos)).find(x => !isDone(x));
  if (!nx) return toast(dir === 'nextopen' ? t('toast.noopen') : t('toast.end'));
  cur.i = nx.i; S.ui.sel[cur.tab] = nx.key; save(); refresh(true);
}
function goto(i) {
  const it = ITEMS[i]; if (!it) return;
  const tab = it.q === 'text' ? 'extract' : it.q === 'rest' ? 'sample' : it.q;
  if (it.q === 'text') S.ui.mode.extract = 'text'; if (it.q === 'rest') S.ui.mode.sample = 'all'; if (it.q === 'extract') S.ui.mode.extract = 'entries';
  if (it.q === 'tc' && !tabItems('tc').includes(it)) S.ui.mode.tc = 'all';
  S.ui.filt[tab] = {}; S.ui.q[tab] = ''; openTab(tab, i);
}
document.addEventListener('click', ev => {
  const t0 = ev.target;
  const tab = t0.closest('[data-tab]'); if (tab) return openTab(tab.dataset.tab);
  const qi = t0.closest('.qi'); if (qi) { cur.i = +qi.dataset.i; S.ui.sel[cur.tab] = ITEMS[cur.i].key; save(); refresh(); return; }
  const more = t0.closest('[data-more]'); if (more) { S.ui.show[cur.tab] = (S.ui.show[cur.tab] || LIST_STEP) + LIST_STEP; renderQueue(); return; }
  const chip = t0.closest('.chip[data-f]'); if (chip) { const f = S.ui.filt[cur.tab] = S.ui.filt[cur.tab] || {}; f[chip.dataset.f] = f[chip.dataset.f] === chip.dataset.v ? '' : chip.dataset.v; S.ui.show[cur.tab] = LIST_STEP; openTab(cur.tab); return; }
  const mode = t0.closest('.chip[data-mode]'); if (mode) { S.ui.mode[cur.tab] = mode.dataset.mode; S.ui.filt[cur.tab] = {}; openTab(cur.tab); return; }
  const nv = t0.closest('[data-nav]'); if (nv) return nav(nv.dataset.nav);
  const ac = t0.closest('[data-act]'); if (ac) return act(ITEMS[cur.i], ac.dataset.act);
  const hs = t0.closest('[data-hsug]'); if (hs) { const it = ITEMS[cur.i]; const e = EUNIS.get(it.sug.code) || []; setDec(it, { d: 'o', target: { code: it.sug.code, label: e[1] || it.sug.label || '', match: it.sug.match || 'close' } }, t('log.other', it.sug.code)); return afterDecision(); }
  const lg = t0.closest('[data-legacy]'); if (lg) return importFromBrowser(lg.dataset.legacy);
  const cl = t0.closest('[data-clear]'); if (cl) return setDec(ITEMS[cur.i], null, t('d.removed'));
  const sc = t0.closest('[data-scan]'); if (sc && !t0.closest('a[href="#"]')?.dataset?.mi && !t0.closest('.snip')) { scanFor(+sc.dataset.scan, sc.dataset.t, sc.dataset.mi != null ? +sc.dataset.mi : null); if (t0.tagName === 'A') ev.preventDefault(); return; }
  if (sc && t0.closest('a')) { ev.preventDefault(); scanFor(+sc.dataset.scan, sc.dataset.t, sc.dataset.mi != null ? +sc.dataset.mi : null); return; }
  const sn = t0.closest('.snip'); if (sn) { const men = sn.closest('.men'); const kw = men && $('.kw', men); const it = ITEMS[cur.i]; if (kw && kw.dataset.mi != null) scanFor(+kw.dataset.scan, kw.dataset.t, +kw.dataset.mi); else if (it && it.t === 'tc') showScan(null, E[it.ei], it.hl); return; }
  const pg = t0.closest('[data-page]'); if (pg) { scan.p = +pg.dataset.page; renderScan(); return; }
  const go = t0.closest('[data-goto]'); if (go) { ev.preventDefault(); return goto(+go.dataset.goto); }
  const rm = t0.closest('[data-rm]'); if (rm) return setDec(ITEMS[+rm.dataset.rm], null, t('d.removed'));
  const task = t0.closest('.task'); if (task) { const q = task.dataset.task; const f = JSON.parse(task.dataset.f || '{}'); S.ui.filt[q] = Object.assign({ state: 'open' }, f); if (task.dataset.mode) S.ui.mode[q] = task.dataset.mode; S.ui.show[q] = LIST_STEP; S.ui.q[q] = ''; return openTab(q); }
  const nb = t0.closest('.mb[data-name]'); if (nb) { const it = ITEMS[cur.i]; const fi = +nb.dataset.name; const v = nb.dataset.v; const tt = ttOf(it); const nm = FORMS[tt][fi][0]; const key = lc(nm); const cur0 = subOf(it, 'names', key);
    if (cur0 && cur0.d === v) return setSub(it, 'names', key, null, t('log.nameRm', nm));
    if (v === 'o') return openOther(it, { name: fi });
    return setSub(it, 'names', key, { d: v }, nm + ': ' + t('log.name.' + v)); }
  const mb2 = t0.closest('.mb[data-men]'); if (mb2) { const it = ITEMS[cur.i]; const mi = +mb2.dataset.men; const v = mb2.dataset.v; const tt = ttOf(it); const key = menKey(tt, mi); const cur0 = subOf(it, 'mens', key);
    if (cur0 && cur0.d === v) return setSub(it, 'mens', key, null, t('log.passageRm'));
    if (v === 'o') return openOther(it, { men: mi });
    return setSub(it, 'mens', key, { d: 'n', written: FORMS[tt][MEN[tt][mi][0]][0] }, t('log.passageDrop')); }
  const ob = t0.closest('.mb[data-obs],.mb[data-miss]'); if (ob) { const it = ITEMS[cur.i]; const kind = ob.dataset.obs != null ? 'obs' : 'miss'; const key = ob.dataset.obs != null ? ob.dataset.obs : ob.dataset.miss; const v = ob.dataset.v; const cur0 = subOf(it, kind, key);
    if (cur0 && cur0.d === v) return setSub(it, kind, key, null, t('log.rowRm'));
    return setSub(it, kind, key, { d: v }, t(kind === 'obs' ? 'log.obs' : 'log.miss', key.split('|')[0].slice(0, 40)) + ': ' + t({ y: 'log.right', n: 'log.wrong', u: 'log.unsure' }[v])); }
  const cd = t0.closest('.cand[data-cand]'); if (cd && !t0.closest('a')) { const it = ITEMS[cur.i]; const c = it.cands[+cd.dataset.cand]; if (c) chooseTarget(it, { qid: c.qid, gnd: c.gnd || '', label: c.label }, c.label); return; }
  const gc = t0.closest('.cand[data-gcand]'); if (gc && !t0.closest('a')) { const it = ITEMS[cur.i]; const c = it.gcands[+gc.dataset.gcand]; if (c) chooseTarget(it, { qid: c.wd || '', gnd: c.gnd, label: c.name }, c.name); return; }
  if (t0.id === 'scanclose') { S.ui.scan = false; save(); return $('#main').classList.add('noscan'); }
  if (t0.id === 'scanzoom') { scan.zoom = (scan.zoom + 1) % 3; renderScan(); return; }
  if (t0.id === 'scanprev' || t0.id === 'scannext') { if (scan.p < 0) return; const d = t0.id === 'scanprev' ? -1 : 1; const j = scan.p + d; if (j >= 0 && j < PG.length && PG[j][1] === PG[scan.p][1]) { scan.p = j; scan.hl = null; renderScan(); } return; }
  if (t0.id === 'btnUndo') return undo();
  if (t0.id === 'btnLang') { setLang(LANG === 'en' ? 'de' : 'en'); return refresh(); }
  if (t0.id === 'btnTheme') { const r = document.documentElement; const dark = r.dataset.theme === 'dark' || (!r.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches); r.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem(LS + '-theme', r.dataset.theme); } catch (e) { } return; }
  if (t0.id === 'btnHelp') return showHelp();
  if (t0.id === 'btnExport') return showExport();
  if (t0.id === 'btnImport') return $('#fileImport').click();
  if (t0.id === 'btnSearch') return showSearch();
  if (t0.id === 'btnList') return $('#main').classList.toggle('showlist');
  if (t0.id === 'ovModal') return $('#ovModal').classList.remove('show');
  if (t0.closest('.modal .x')) return $('#ovModal').classList.remove('show');
});
document.addEventListener('input', ev => {
  const t0 = ev.target;
  if (t0.id === 'qsearch') { S.ui.q[cur.tab] = t0.value; S.ui.show[cur.tab] = LIST_STEP; clearTimeout(t0._t); t0._t = setTimeout(() => { const v = t0.value; renderQueue(); const n = $('#qsearch'); n.value = v; n.focus(); n.setSelectionRange(v.length, v.length); }, 250); }
  if (t0.id === 'who') { S.who = t0.value.trim(); save(); }
  if (t0.id === 'note') { const it = ITEMS[cur.i]; if (S.dec[it.key]) { S.dec[it.key].note = t0.value; save(); } }
  if (t0.id === 'adv') { S.ui.adv = t0.checked; save(); }
});
document.addEventListener('keydown', ev => {
  const tag = (ev.target.tagName || '').toLowerCase(); const typing = tag === 'input' || tag === 'textarea' || tag === 'select';
  if (ev.key === 'Escape') { if ($('#ovModal').classList.contains('show')) return $('#ovModal').classList.remove('show'); if ($('#other') && $('#other').innerHTML) { $('#other').innerHTML = ''; otherScope = null; return; } if (typing) ev.target.blur(); return; }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') { ev.preventDefault(); return showSearch(); }
  if (typing) {
    if (ev.key === 'Enter' && ev.target.id === 'note') ev.target.blur();
    if (/^[1-9]$/.test(ev.key) && ['tsearch', 'psearch', 'lsearch', 'hsearch'].includes(ev.target.id) && ITEMS[cur.i] && pickDigit(ITEMS[cur.i], +ev.key)) ev.preventDefault();
    return;
  }
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if ($('#ovModal').classList.contains('show')) return;
  if (!(cur.tab in FILTERS)) return;
  const it = ITEMS[cur.i]; if (!it) return;
  const k = ev.key.toLowerCase();
  if (/^[1-9]$/.test(ev.key)) { if (pickDigit(it, +ev.key)) ev.preventDefault(); return; }
  const map1 = { j: 'a', n: 'r', a: 'o', u: 'u', e: 'e' };
  if (k in map1) {
    // preventDefault first: the key must not reach a text field the action opens
    ev.preventDefault(); const acts = $$('.acts .btn[data-act]'); const has = x => acts.some(b => b.dataset.act === x); let want = map1[k];
    if (want === 'a' && !has('a')) want = 'y'; if (want === 'r' && !has('r')) want = 'k'; if (want === 'o' && !has('o')) want = 'e'; if (want === 'e' && !has('e')) return;
    const b = acts.find(x => x.dataset.act === want); if (b) b.click(); return;
  }
  if (ev.key === 'Enter') { ev.preventDefault(); return nav('nextopen'); }
  if (ev.key === 'ArrowDown' || ev.key === 'PageDown') { ev.preventDefault(); return nav('next'); }
  if (ev.key === 'ArrowUp' || ev.key === 'PageUp') { ev.preventDefault(); return nav('prev'); }
  if (k === 'z') { ev.preventDefault(); return undo(); }
  if (k === 's') { ev.preventDefault(); const m = $('#main'); if (m.classList.contains('noscan')) { S.ui.scan = true; const e = entryOf(it) || (it.ev && it.ev.length ? E[MEN[menType(it)][it.ev[0]][1]] : null); if (e) showScan(null, e, it.t === 'tc' ? it.hl : null); } else { S.ui.scan = false; m.classList.add('noscan'); } save(); return; }
  if (k === 'h' && it.t === 'place' && it.hint_ll) { ev.preventDefault(); if (!$('#other').innerHTML) openOther(it); $('#phint').click(); return; }
  if (ev.key === '/') { ev.preventDefault(); const q = $('#qsearch'); if (q) q.focus(); }
  if (ev.key === '?') return showHelp();
});
// scan pane resize
(function () { const grip = $('#grip'); let drag = false; grip.addEventListener('mousedown', e => { drag = true; e.preventDefault(); }); document.addEventListener('mousemove', e => { if (!drag) return; const w = Math.min(70, Math.max(20, (window.innerWidth - e.clientX) / window.innerWidth * 100)); document.documentElement.style.setProperty('--scanw', w + 'vw'); }); document.addEventListener('mouseup', () => { drag = false; }); })();
