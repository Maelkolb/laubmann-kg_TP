/* Graph-Explorer (--mode explorer) — the reading view for external readers, English only: the list of all entries,
   the Text tab (the entry set like an edition, the machine's changes and the bird names of the records marked,
   the records with their error risk, images and inserts), the head of the Notes tab, the overview. */

const XT = { media: null, layers: false };
const cap = s => (s ? s[0].toUpperCase() + s.slice(1) : s);

// ------------------------------------------------------------------ names, dates, volumes
function xDate(s, short) {   // 1941-08-04 -> 4 August 1941; ranges as 3–5 August 1941, 30 April – 2 May 1941
  if (!s) return '';
  const months = t(short ? 'months' : 'x_months').split(',');
  const parts = String(s).split('/').map(p => /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(p.trim()) || p.trim());
  const one = (m, y = true, mo = true) => (typeof m === 'string' ? m : [m[3] ? String(+m[3]) : '', mo && m[2] ? months[+m[2] - 1] : '', y ? m[1] : ''].filter(Boolean).join(' '));
  if (parts.length === 2 && typeof parts[0] !== 'string' && typeof parts[1] !== 'string' && parts[0][1] === parts[1][1]) {
    const [a, b] = parts; if (a[0] === b[0]) return one(b);
    if (a[2] === b[2] && a[3] && b[3]) return `${+a[3]}–${one(b)}`;
    return `${one(a, false)} – ${one(b)}`;
  }
  return parts.map(p => one(p)).join(' – ');
}
const xVolNo = v => { const m = /(\d+)\s*$/.exec(prefDe(v, 'rdfs:label') || ''); return m ? +m[1] : null; };
const xVolName = v => (v < 0 ? t('no_vol') : xVolNo(v) != null ? t('x_vol', xVolNo(v)) : label(v));
function xVolYears(v) { const ys = (pref(v, 'dcterms:temporal') || '').split('/').map(x => x.slice(0, 4)).filter(Boolean); return ys.length && ys[0] !== ys[ys.length - 1] ? ys[0] + '–' + ys[ys.length - 1] : ys[0] || ''; }
const xEntryPlace = r => (r.place >= 0 ? nameOf(r.place) : prefDe(r.n, 'dwc:verbatimLocality') || '');
function xLabel(n, k) {   // English labels of entries and volumes (the graph's own labels are German)
  if (k === 'volume') return xVolName(n);
  const r = entryRec(n); return r ? [xDate(r.date), xEntryPlace(r)].filter(Boolean).join(', ') || r.id : localName(n);
}
function xRecPlace(o) { const loc = node1(o, 'lkg:hasLocality'), at = node1(o, 'lkg:observedAt'); return loc >= 0 ? nameOf(loc) : at >= 0 ? nameOf(at) : prefDe(o, 'dwc:verbatimLocality') || ''; }
const xSci = o => { const tx = node1(o, 'lkg:observedTaxon'); return tx >= 0 ? prefDe(tx, 'dwc:scientificName') || '' : ''; };
const xWritten = o => { const it = EM && EM.byNode.get(o); return it ? it.written : writtenOf(o); };
const xLevel = o => { const q = qOf(o); return q ? q.lv || qLevelOf(q.p) : 0; };

// ------------------------------------------------------------------ entry list
function xListOptionHtml() {
  const c = (RVU.counts.img || { n: 0 }).n;
  return `<label class="xonly" title="${esc(t('x_only_img_t'))}"><input type="checkbox" id="onlyimg"${RVU.queue === 'img' ? ' checked' : ''}>${esc(t('x_only_img'))}<span class="num">${fmt(c)}</span></label>`;
}
function xRenderVolSelect(sel_) {
  sel_.innerHTML = `<option value="all">${esc(t('x_vol_all'))}</option>` + G.vols.concat(G.entByVol.has(-1) ? [-1] : []).map(v => `<option value="${v}">${esc(xVolName(v))}${v >= 0 ? ` (${esc(xVolYears(v))})` : ''}</option>`).join('');
  sel_.value = RVU.vol;
}
function xListRowHtml(r, i) {
  const s = RVS.get(r.n);
  const n = corpusOn() ? `<span class="n" title="${esc(t('l_records_corp', fmt(s.qn), fmt(r.nobs), qfName()))}"><b>${fmt(s.qn)}</b> / ${fmt(r.nobs)}</span>`
    : `<span class="n" title="${esc(t('x_n_records', fmt(r.nobs)))}">${r.nobs ? fmt(r.nobs) : ''}</span>`;
  return `<div class="erow${r.n === S.e ? ' on' : ''}" data-e="${r.n}" style="top:${i * ROW_H}px" title="${esc(r.id)}"><span class="d">${esc(xDate(r.date, true) || prefDe(r.n, 'dwc:verbatimEventDate') || r.id)}</span>${n}<span class="p">${esc(xEntryPlace(r))}</span></div>`;
}
function xHeadHtml(e, q) {
  const m = entryModel(e); const out = outCount(m);
  const corp = corpusOn() ? `<span class="hcorp" title="${esc(t('head_corp_t'))}">${esc(t('head_corp', qfName(), fmt(m.obs.length - out), fmt(m.obs.length)))}</span>` : '';
  return `<button class="btn" data-act="list" title="${esc(t('toggle_list'))}">☰</button><span class="navb"><button class="btn" data-act="prev" title="${esc(t('prev'))}"${q.pos === 0 ? ' disabled' : ''}>◀</button><button class="btn" data-act="next" title="${esc(t('next'))}"${q.pos >= q.n - 1 ? ' disabled' : ''}>▶</button></span>
    <span class="seg" title="${esc(t('mid_t'))}"><button data-act="mid-graph" class="${RVU.mid === 'graph' ? 'on' : ''}">${t('mid_graph')}</button><button data-act="mid-table" class="${RVU.mid === 'table' ? 'on' : ''}">${t('mid_table')}</button></span>
    <button class="btn${RVU.scan ? ' on' : ''}" data-act="scan" title="${esc(t('scan_toggle_t'))}">${t('scan_btn')}</button>
    <span class="sp"></span>${corp}<span class="muted hpos num">${q.pos >= 0 ? esc(t('x_pos', fmt(q.pos + 1), fmt(q.n))) : esc(xVolName(entryRec(e).vol))}</span>`;
}

function xToolsHtml() {   // the graph's tool row: layers and their options in a menu, presets, zoom
  const out = EM ? outCount(EM) : 0; const g = S.group;
  const chips = LAYERS.map(([l, c]) => `<span class="chip ${S.layers[l] ? 'on' : ''}" data-layer="${l}"><i style="background:var(--c-${c})"></i>${esc(t('l_' + l))}</span>`).join('');
  const opts = `<select id="grpsel" title="${esc(t('group_by'))}">${['auto', 'none', 'order', 'family', 'place', 'recordedBy', 'recordType'].map(k => `<option value="${k}"${k === g ? ' selected' : ''}>${esc(t('grp_short'))}: ${esc(t('g_' + k))}</option>`).join('')}</select>
    <button class="zbtn" data-act="expand" title="${esc(t('expand_all'))}">▾▾</button><button class="zbtn" data-act="collapse" title="${esc(t('collapse_all'))}">▸▸</button>
    <select id="lblsel" title="${esc(t('labels'))}">${['auto', 'all', 'none'].map(k => `<option value="${k}"${k === S.labels ? ' selected' : ''}>${esc(t('labels_short'))}: ${esc(t('lb_' + k))}</option>`).join('')}</select>` +
    (S.layers.props ? `<select id="propsel" title="${esc(t('props_t'))}">${['auto', 'compact', 'all'].map(k => `<option value="${k}"${k === S.props ? ' selected' : ''}>${esc(t('props_short'))}: ${esc(t('pm_' + k))}</option>`).join('')}</select>` : '');
  return `<span class="xlay"><button class="zbtn wide${XT.layers ? ' on' : ''}" data-act="xlayers" aria-expanded="${XT.layers}">${esc(t('x_layers'))} ▾</button><div class="xpop"${XT.layers ? '' : ' hidden'}><div class="xchips">${chips}</div><div class="xpop-row">${opts}</div></div></span>
    <span class="seg" title="${esc(t('preset_t'))}"><button data-act="preset-std" class="${isPreset(false) ? 'on' : ''}">${esc(t('preset_std'))}</button><button data-act="preset-all" class="${isPreset(true) ? 'on' : ''}">${esc(t('preset_all'))}</button></span>` +
    (out ? `<span class="chip outchip${RVU.showOut ? ' on' : ''}" data-act="showout" title="${esc(t('out_t'))}"><i></i>${esc(t(RVU.showOut ? 'out_hide' : 'out_show', fmt(out)))}</span>` : '') +
    `<span class="sp"></span><button class="zbtn" data-act="zout" title="−">−</button><button class="zbtn" data-act="zin" title="+">+</button><button class="zbtn" data-act="fit" title="${esc(t('fit'))}">⤢</button>`;
}

function xFit(W, H) {   // the whole graph when its labels stay readable (zoom >= 0.88), else the columns from the left that fit; the rest is a pan away
  const MIN = 0.88, MAX = 1.15; const kw = Math.min(W / SUB.width, MAX); let k = kw;
  if (kw >= MIN) k = Math.min(kw, Math.max(H / SUB.height, MIN));
  else {
    k = clamp(kw, 0.6, MAX); const used = SUB.used;
    for (let i = used.length - 1; i >= 1; i--) {
      const c = used[i - 1]; const kk = Math.min(W / (SUB.colX[c] + colW(c) + 14), MAX);
      if (kk >= MIN && SUB.colX[used[i]] * kk >= W - 2) { k = kk; break; }
    }
  }
  Z.k = k; Z.x = SUB.width * k <= W ? (W - SUB.width * k) / 2 : 2;
  const ev = SUB.V.get('n' + S.e);   // a graph taller than the pane: its columns are centred on the tallest one, so centre on the entry
  Z.y = SUB.height * k <= H ? Math.max(6, (H - SUB.height * k) / 2 - 10) : ev ? Math.min(6, H / 2 - (ev.y + ev.h / 2) * k) : 6;
  applyZ();
}

// ------------------------------------------------------------------ panel tabs: Text first; Notes and Node smaller
function xTabs() {
  const b = $('#ptabs [data-tab="check"]'); if (!b || !EM) return;
  const n = visibleItems(EM).filter(it => it.lv >= 1).length;
  b.innerHTML = `${esc(t('tab_check'))}${n ? `<span class="tabn num">${fmt(n)}</span>` : ''}`;
  b.title = t('x_tab_notes_t');
}
function xNotesHead(m) {
  const chk = m.rv.chk || '';
  const who = chk ? t('chk_by', [chk.includes('g') ? srcName('g') : '', chk.includes('s') ? srcName('s') : ''].filter(Boolean).join(t('x_and'))) : t('chk_none');
  return `<div class="xnhead"><span class="muted">${esc(who)}</span><span class="sp"></span><label class="xsw" title="${esc(t('x_notes_sw_t'))}"><input type="checkbox" id="notesw"${RVU.notes ? ' checked' : ''}>${esc(t('x_notes_sw'))}</label></div>`;
}

// ------------------------------------------------------------------ the entry text
function xChanges(m, fn) {   // the machine's changes the graph text holds: [{a, b, i, c}], in text order, without overlaps
  const all = [];
  (m.rv.tc || []).forEach((c, i) => { if (TC_FIELD.test(c[0] || '')) return; const cur = tcNow(c); const p = tcAtNow(fn, c); if (p >= 0 && cur !== c[0]) all.push({ a: p, b: p + cur.length, i, c, markup: c[4] === 'markup' }); });
  all.sort((x, y) => x.a - y.a || y.b - x.b);
  const out = []; let end = -1; for (const x of all) if (x.a >= end) { out.push(x); end = x.b; }
  return out;
}
const foldName = s => String(s || '').toLowerCase().replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 'ss');
function xNames(m, fn) {   // where the bird name of each record stands in the text: Map record node -> [a, b]
  const plain = fn.replace(/<\/?u>/g, x => ' '.repeat(x.length));
  const words = []; const re = /\p{L}+/gu; let w;
  while ((w = re.exec(plain))) words.push({ a: w.index, b: w.index + w[0].length, f: foldName(w[0]) });
  const tp = textPos(m.e); const taken = new Set(); const out = new Map();
  const forms = o => { const tx = node1(o, 'lkg:observedTaxon'); return uniq([xWritten(o), prefDe(o, 'dwc:verbatimIdentification'), tx >= 0 ? nameOf(tx) : ''].concat(tx >= 0 ? litsOf(tx, 'skos:altLabel') : []).map(foldName).filter(f => f.length >= 3 && !/\s/.test(f))); };
  const find = (fs, a, b) => words.find(x => x.a >= a && x.b <= b && !taken.has(x.a) && fs.some(f => x.f.startsWith(f)));
  for (const o of m.obs) {
    const fs = forms(o.n); if (!fs.length) continue; const hit = tp.get(o.n);
    const w_ = (hit && find(fs, hit[0], hit[0] + hit[1])) || find(fs, 0, fn.length);
    if (w_) { taken.add(w_.a); out.set(o.n, [w_.a, w_.b]); }
  }
  return out;
}
function xMarkedText(m, fn, orig) {
  const changes = xChanges(m, fn);
  if (orig) {   // the transcription before the machine: every change taken back, the earlier text marked
    let s = ''; const chg = []; let i = 0;
    const put = (str, v) => { s += str; for (let j = 0; j < str.length; j++) chg.push(v); };
    for (const x of changes) { put(fn.slice(i, x.a), -1); put(x.c[0], x.markup ? -1 : x.i); i = x.b; }
    put(fn.slice(i), -1);
    return xSegments(s, chg, null);
  }
  const chg = new Int32Array(fn.length).fill(-1); for (const x of changes) if (!x.markup) chg.fill(x.i, x.a, x.b);   // an underline the reading added changes no word
  const bird = new Int32Array(fn.length).fill(-1); for (const [o, [a, b]] of xNames(m, fn)) bird.fill(o, a, b);
  return xSegments(fn, chg, bird);
}
function xSegments(s, chg, bird) {
  const n = s.length; const selN = S.sel && S.sel[0] === 'n' ? +S.sel.slice(1) : -1;
  const words = new Map(); for (let j = 0; j < n; j++) if (chg[j] >= 0 && (j === 0 || chg[j - 1] !== chg[j])) { let k = j; while (k < n && chg[k] === chg[j]) k++; words.set(chg[j], s.slice(j, k).replace(/<\/?u>/g, '').trim().split(/\s+/).length); }
  const long = new Set([...words].filter(([, w]) => w > 6).map(([c]) => c));   // a long passage: the fine underline without the tint
  const isTag = j => s.charCodeAt(j) === 60 && (s.startsWith('<u>', j) || s.startsWith('</u>', j));
  let out = '', i = 0, u = false;
  while (i < n) {
    if (isTag(i)) { u = s[i + 1] === 'u'; i += u ? 3 : 4; continue; }
    const c = chg[i], b = bird ? bird[i] : -1; let j = i + 1;
    while (j < n && chg[j] === c && (bird ? bird[j] : -1) === b && !isTag(j)) j++;
    const cls = [], attr = [];
    if (c >= 0) { cls.push('xc'); if (long.has(c)) cls.push('long'); attr.push(`data-chg="${c}"`); }
    if (b >= 0) { cls.push('xb', 'ql' + xLevel(b)); if (b === selN) cls.push('on'); if (!inCorpus(b)) cls.push('out'); attr.push(`data-obs="${b}"`); }
    if (u) cls.push('u');
    const txt = escHtml(s.slice(i, j));
    out += cls.length ? `<span class="${cls.join(' ')}"${attr.length ? ' ' + attr.join(' ') + ' tabindex="0"' : ''}>${txt}</span>` : txt;
    i = j;
  }
  return out;
}
function xRecordRows(m, names) {   // the entry's records in text order
  const tp = textPos(m.e); const pos = o => (names.has(o.n) ? names.get(o.n)[0] : tp.get(o.n) ? tp.get(o.n)[0] : 1e9);
  return m.obs.slice().sort((a, b) => pos(a) - pos(b) || a.idx - b.idx);
}
function xRecordsHtml(m, names) {
  const rows = xRecordRows(m, names); const shown = rows.filter(o => rvObsShown(o.n)); const hidden = rows.length - shown.length;
  if (!rows.length) return '';
  const selN = S.sel && S.sel[0] === 'n' ? +S.sel.slice(1) : -1;
  const row = o => {
    const q = qOf(o.n); const sci = xSci(o.n); const on = o.n === selN; const out = !inCorpus(o.n);
    let h = `<tr class="xr${on ? ' on' : ''}${out ? ' out' : ''}" data-obs="${o.n}" tabindex="0"><td class="sp" title="${esc([sci, o.written].filter(Boolean).join(' '))}">${sci ? `<i>${esc(sci)}</i>` : ''}<span lang="de">${esc(o.written)}</span></td><td class="r num" title="${esc(countStr(o.n))}">${esc(countStr(o.n))}</td><td class="pl" lang="de" title="${esc(xRecPlace(o.n))}">${esc(xRecPlace(o.n))}</td><td class="num dt">${esc(xDate(pref(o.n, 'dwc:eventDate'), true))}</td>` +
      `<td class="r num rk">${q ? `<span class="xdot ql${xLevel(o.n)}" title="${esc(t('ql_t_' + xLevel(o.n)))}"></span>${esc(qPct(q.p))}` : '<span class="muted">–</span>'}</td></tr>`;
    if (on) {
      const by = nodeObjs(o.n, 'dwciri:recordedBy').map(nameOf).join(', '); const ty = pref(o.n, 'lkg:recordType');
      h += `<tr class="xdet"><td colspan="5"><div class="xdet-kv">${by ? `<span><b>${esc(t('qn_observer'))}</b> ${esc(by)}</span>` : ''}${ty ? `<span><b>${esc(t('qn_record_type'))}</b> ${esc(cv('lkg:recordType', ty))}</span>` : ''}</div>${qualLine(o.n)}</td></tr>`;
    }
    return h;
  };
  return `<section class="xsec xrecs"><h3>${esc(t('x_records'))}<span class="cnt num">${fmt(rows.length)}</span></h3>
    <table class="xrec"><thead><tr><th>${esc(t('x_c_species'))}</th><th class="r">${esc(t('x_c_count'))}</th><th>${esc(t('x_c_place'))}</th><th>${esc(t('x_c_date'))}</th><th class="r" title="${esc(t('x_c_risk_t'))}">${esc(t('x_c_risk'))}</th></tr></thead>
    <tbody>${shown.map(row).join('')}</tbody></table>` +
    (hidden || RVU.showOut && corpusOn() && rows.some(o => !inCorpus(o.n)) ? `<p class="xout">${esc(t(RVU.showOut ? 'x_out_shown' : 'x_out', fmt(rows.filter(o => !inCorpus(o.n)).length), qfName()))} <span class="link" data-act="showout">${esc(t(RVU.showOut ? 'out_hide_s' : 'out_show_s'))}</span></p>` : '') + '</section>';
}
function xFiguresHtml(m) {
  const items = m.items.filter(it => it.type === 'media'); if (!items.length) return '';
  const fig = it => {
    const uid = it.x[0]; const n = regionNode(uid); const desc = n >= 0 ? pref(n, 'dcterms:description') || '' : '';
    const st = it.ins ? (it.ins[3].startsWith('read-in:') ? 'readin' : it.ins[3]) : '';
    return `<figure class="xfig${XT.media === uid ? ' on' : ''}" data-media="${esc(uid)}"><div class="xfig-img" data-crop-open="${esc(uid)}" title="${esc(t('crop_open'))}">${cropHtml(uid, 'xthumb fit', 800)}</div>
      <figcaption><span class="xfig-k">${esc(mediaKind(it.x[1]))}${st && st !== 'read' ? `<span class="xfig-st">${esc(t('ins_' + st))}</span>` : ''}</span>${desc ? `<span class="xfig-d" title="${esc(desc)}">${esc(desc)}</span>` : ''}</figcaption></figure>`;
  };
  return `<section class="xsec xmedia"><h3>${esc(t('x_media'))}<span class="cnt num">${fmt(items.length)}</span></h3><div class="xfigs">${items.map(fig).join('')}</div></section>`;
}
function xTextHtml(m) {
  const e = m.e, r = entryRec(e); const orig = RVU.textLayer === 'orig'; const fn = prefDe(e, 'dwc:fieldNotes') || '';
  const place = xEntryPlace(r); const pages = entryPages(e).map(p => pageShort(pref(p, 'dcterms:identifier') || '').replace(/^\D+/, '')).filter(Boolean);
  const seg = `<span class="seg tlayer" title="${esc(t('tlayer_t'))}"><button data-act="tlayer" data-layer="final" class="${orig ? '' : 'on'}">${esc(t('tlayer_final'))}</button><button data-act="tlayer" data-layer="orig" class="${orig ? 'on' : ''}">${esc(t('tlayer_orig'))}</button></span>`;
  const head = `<header class="xhead"><div class="xh1"><h2 class="xdate">${esc(xDate(r.date) || prefDe(e, 'dwc:verbatimEventDate') || r.id)}</h2>${fn ? seg : ''}</div>
    ${place ? `<div class="xplace" lang="de">${esc(place)}</div>` : ''}
    <div class="xmeta"><span>${esc(xVolName(r.vol))}</span>${pages.length ? `<span>${esc(t('scan_n', pages.join(', ')))}</span>` : ''}<span class="mono">${esc(r.id)}</span></div></header>`;
  const names = orig || !fn ? new Map() : xNames(m, fn);
  const legend = fn ? `<p class="xlegend"><span class="xc">${esc(t(orig ? 'x_lg_chg_orig' : 'x_lg_chg'))}</span>${orig ? '' : `<span class="xlg-r">${esc(t('x_lg_recs'))}</span>${[1, 2, 3, 4].map(lv => `<span class="xb ql${lv}" title="${esc(t('ql_t_' + lv))}">${esc(t('ql_' + lv))}</span>`).join('')}`}</p>` : '';
  return `<article class="xtext">${head}<div class="xbody" id="fnotes" lang="de">${fn ? xMarkedText(m, fn, orig) : `<span class="muted">${esc(t('no_text'))}</span>`}</div>${legend}${xRecordsHtml(m, names)}${xFiguresHtml(m)}</article>`;
}
function xRenderText(body) {
  const m = entryModel(S.e);
  const same = body.dataset.tab === 'text' && body.dataset.e === String(S.e); const keep = same ? body.scrollTop : 0; const moved = same && body.dataset.shown !== String(S.sel);
  body.innerHTML = xTextHtml(m); body.scrollTop = keep;
  if (moved) { const on = $('#fnotes .xb.on', body) || $('.xrec tr.on', body); if (on) on.scrollIntoView({ block: 'nearest' }); }
}
function xSelectMedia(uid, inText) {
  const m = EM; if (!m) return; const it = m.items.find(x => x.type === 'media' && x.x[0] === uid); if (!it) return;
  XT.media = uid;
  if (inText && S.tab === 'text') $$('#pbody .xfig').forEach(f => f.classList.toggle('on', f.dataset.media === uid));
  else { S.tab = 'text'; renderPanel(); }
  const f = $(`#pbody .xfig[data-media="${CSS.escape(uid)}"]`); if (f && !inText) f.scrollIntoView({ block: 'nearest' });
  scanHighlightMedia(it.x);
}

// ------------------------------------------------------------------ hover cards: a change, a record
const xQuote = s => { const x = String(s || ''); return escHtml(x.length > 240 ? x.slice(0, 240) + ' …' : x).replace(/&lt;(\/?)u&gt;/g, '<$1u>').replace(/\n/g, ' ⏎ '); };
const xCheckName = c => (['wrong', 'partly', 'unclear'].includes(c[7]) ? srcName('g') : c[6] ? srcName('s') : t('x_t_check'));
function xChangeSteps(c) {   // [step, text]: the transcription, then each machine step that changed this place
  const cur = tcNow(c); const steps = [[t('x_t_transcript'), c[0]]];
  if (c[11] === 'scan') steps.push([t('x_t_agent'), cur]);
  else {
    if (c[2] && c[1] !== c[0]) steps.push([t('x_t_reading'), c[1]]);
    if (tcMachine(c) && cur !== steps[steps.length - 1][1]) steps.push([xCheckName(c), cur]);
  }
  return steps;
}
function xChangeTip(c) {
  const steps = xChangeSteps(c);
  return `<div class="xt-h">${esc(t('x_t_title'))}</div><table class="xt-steps">${steps.map((s, i) => `<tr class="${i === steps.length - 1 ? 'now' : ''}"><th>${esc(s[0])}</th><td lang="de">${s[1] ? xQuote(s[1]) : `<span class="muted">${esc(t('x_t_empty'))}</span>`}</td></tr>`).join('')}</table>`;
}
function xRecordTip(o) {
  const sci = xSci(o); const by = nodeObjs(o, 'dwciri:recordedBy').map(nameOf).join(', '); const ty = pref(o, 'lkg:recordType');
  const rows = [[t('qn_count'), countStr(o)], [t('qn_place'), xRecPlace(o)], [t('qn_date'), xDate(pref(o, 'dwc:eventDate'))], [t('qn_observer'), by], [t('qn_record_type'), ty ? cv('lkg:recordType', ty) : '']].filter(r => r[1]);
  return `<div class="xt-name">${sci ? `<i>${esc(sci)}</i>` : ''}<span lang="de">${esc(xWritten(o))}</span></div><table class="xt-kv">${rows.map(r => `<tr><th>${esc(r[0])}</th><td>${esc(r[1])}</td></tr>`).join('')}</table>${qualLine(o)}`;
}
function xTipShow(el, ev) {
  const tip = $('#xtip'); const m = EM; if (!tip) return;
  let h = '';
  if (el.dataset.year != null) h = `<div class="xt-h">${esc(el.dataset.year)}</div><div>${esc(t('x_o_year_n', fmt(+el.dataset.v)))}</div>`;
  else if (m) {
    if (el.dataset.obs != null) h += `<div class="xt-rec">${xRecordTip(+el.dataset.obs)}</div>`;
    if (el.dataset.chg != null) { const c = (m.rv.tc || [])[+el.dataset.chg]; if (c) h += `<div class="xt-chg">${xChangeTip(c)}</div>`; }
  }
  xTipAt(tip, h, el, ev);
}
function xTipAt(tip, html, el, ev) {
  if (!html) return; tip.innerHTML = html; tip.hidden = false;
  const rects = [...el.getClientRects()]; const r = (ev && rects.find(x => ev.clientY >= x.top - 2 && ev.clientY <= x.bottom + 2)) || rects[0] || el.getBoundingClientRect();
  const w = tip.offsetWidth, h = tip.offsetHeight;
  const x = clamp((ev && rects.length > 1 ? ev.clientX - 20 : r.left), 8, innerWidth - w - 8);
  const y = r.bottom + 8 + h <= innerHeight - 8 ? r.bottom + 8 : Math.max(8, r.top - h - 8);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function xTipHide() { const tip = $('#xtip'); if (tip) tip.hidden = true; }

// ------------------------------------------------------------------ overview for external readers
function xYearChart(items) {   // records per year: one series, a hover card per bar, a click opens the year's first entry
  const W = 560, H = 176, padL = 44, padR = 6, padT = 8, padB = 24; const n = items.length; if (!n) return '';
  const mx = niceMax(Math.max(1, ...items.map(x => x.v))); const band = (W - padL - padR) / n; const bw = Math.min(24, Math.max(2, band - 2));
  const y = v => padT + (H - padT - padB) * (1 - v / mx);
  let s = `<svg class="xchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('x_o_per_year'))}">`;
  for (const g of [0, 0.5, 1]) s += `<line class="${g ? 'grid' : 'base'}" x1="${padL}" x2="${W - padR}" y1="${y(mx * g).toFixed(1)}" y2="${y(mx * g).toFixed(1)}"/><text class="ax" x="${padL - 8}" y="${(y(mx * g) + 3.5).toFixed(1)}" text-anchor="end">${fmt(mx * g)}</text>`;
  items.forEach((x, i) => {
    const x0 = padL + i * band + (band - bw) / 2; const top = y(x.v); const h = H - padB - top; const rr = Math.min(3, bw / 2, h);
    s += `<rect class="hit" x="${(padL + i * band).toFixed(1)}" y="${padT}" width="${band.toFixed(1)}" height="${H - padT - padB}" data-year="${x.l}" data-v="${x.v}"${x.go ? ` data-go="${esc(x.go)}"` : ''}/>`;
    if (x.v > 0) s += `<path class="bar" d="M${x0.toFixed(1)},${(H - padB).toFixed(1)} V${(top + rr).toFixed(1)} q0,${(-rr).toFixed(1)} ${rr.toFixed(1)},${(-rr).toFixed(1)} H${(x0 + bw - rr).toFixed(1)} q${rr.toFixed(1)},0 ${rr.toFixed(1)},${rr.toFixed(1)} V${(H - padB).toFixed(1)} Z"/>`;
    if (x.l % 10 === 0) s += `<text class="ax" x="${(padL + (i + 0.5) * band).toFixed(1)}" y="${H - 7}" text-anchor="middle">${x.l}</text>`;
  });
  return s + '</svg>';
}
function xRenderOverview(box) {
  const st = stats(); const qm = (R.meta || {}).quality || {}; const cal = qm['cross-validated calibration'] || {};
  const allYears = G.ent.map(r => +r.date.slice(0, 4)).filter(y => y >= 1900); const y0 = Math.min(...allYears), y1 = Math.max(...allYears);
  const first = G.ent.find(r => rvSrcOk(r.n));
  const species = st.taxa.filter(x => prefDe(x.n, 'dwc:taxonRank') === 'species').length;
  const ys = [...st.yE.keys()].filter(y => y >= y0 && y <= y1);
  const facts = [[t('x_o_entries'), fmt(st.kc[KI.entry])], [t('x_o_records'), fmt(st.kc[KI.obs])], [t('x_o_species'), fmt(species)], [t('x_o_places'), fmt(st.kc[KI.place])], [t('x_o_persons'), fmt(st.kc[KI.person])],
    [t('x_o_years'), ys.length ? Math.min(...ys) + '–' + Math.max(...ys) : '–']];
  const yearItems = []; for (let yr = y0; yr <= y1; yr++) { const f = G.ent.find(r => r.date.startsWith(String(yr)) && rvSrcOk(r.n)); yearItems.push({ l: yr, v: st.yO.get(yr) || 0, go: f ? entryHash(f.n) : '' }); }
  const lvN = [0, 0, 0, 0, 0], lvE = [0, 0, 0, 0, 0];
  for (const n of QF.nodes) { if (!inCorpus(n)) continue; const q = qOf(n); if (!q) continue; const lv = q.lv || qLevelOf(q.p); lvN[lv]++; lvE[lv] += q.p; }
  const tot = lvN.reduce((a, b) => a + b, 0), totE = lvE.reduce((a, b) => a + b, 0);
  const share = (a, b) => (b ? qPct(a / b, 1) : '–');
  const bar = `<div class="xlvbar" role="img" aria-label="${esc(t('x_o_rel'))}">${[1, 2, 3, 4].filter(lv => lvN[lv]).map(lv => `<i class="ql${lv}" style="flex-grow:${lvN[lv]}" title="${esc(t('ql_' + lv) + ': ' + fmt(lvN[lv]))}"></i>`).join('')}</div>`;
  const rel = `<table class="xlvt"><thead><tr><th>${esc(t('x_o_level'))}</th><th>${esc(t('x_o_risk'))}</th><th class="r">${esc(t('x_o_records'))}</th><th class="r">${esc(t('x_o_share'))}</th><th class="r">${esc(t('x_o_exp'))}</th></tr></thead><tbody>` +
    [1, 2, 3, 4].map(lv => `<tr><td><span class="xswatch ql${lv}"></span>${esc(cap(t('ql_' + lv)))}</td><td class="num muted">${esc(t('ql_r_' + lv))}</td><td class="r num">${fmt(lvN[lv])}</td><td class="r num">${share(lvN[lv], tot)}</td><td class="r num">${share(lvE[lv], lvN[lv])}</td></tr>`).join('') +
    `</tbody><tfoot><tr><td>${esc(t('x_o_all'))}</td><td></td><td class="r num">${fmt(tot)}</td><td class="r num">${tot ? '100 %' : '–'}</td><td class="r num">${share(totE, tot)}</td></tr></tfoot></table>`;
  const audit = qm['audit records used'] && cal['any: predicted'] != null ? `<p class="xo-foot">${esc(t('x_o_audit', fmt(qm['audit records used']), qPct(cal['any: predicted'] / 100, 1), qPct(cal['any: observed'] / 100, 1)))}</p>` : '';
  const vols = G.vols.map(v => { const ids = (G.entByVol.get(v) || []).filter(i => rvSrcOk(G.ent[i].n)); return `<button class="xvol" type="button"${ids.length ? ` data-go="${esc(entryHash(G.ent[ids[0]].n))}"` : ' disabled'}><span class="xv-n">${esc(xVolName(v))}</span><span class="xv-y num">${esc(xVolYears(v))}</span><span class="xv-c num">${esc(t('x_n_entries', fmt(ids.length)))}</span></button>`; }).join('');
  box.innerHTML = `<div class="xo">
    <header class="xo-head"><h2>${esc(t('x_o_title'))}</h2><p class="xo-lead">${esc(t('x_o_lead', fmt(G.vols.length), y0, y1))}</p>${first ? `<button class="xo-go" type="button" data-go="${esc(entryHash(first.n))}">${esc(t('x_o_start'))}</button>` : ''}${rvFilterNote(true)}</header>
    <div class="xo-row"><section class="xo-facts"><h3>${esc(t('x_o_graph'))}</h3><table class="xfacts">${facts.map(f => `<tr><th>${esc(f[0])}</th><td class="num">${esc(f[1])}</td></tr>`).join('')}</table></section>
      <section class="xo-years"><h3>${esc(t('x_o_per_year'))}</h3>${xYearChart(yearItems)}</section></div>
    <section class="xo-rel"><h3>${esc(t('x_o_rel'))}</h3>${bar}${rel}${audit}</section>
    <section class="xo-vols"><h3>${esc(t('x_o_vols'))}</h3><div class="xvols">${vols}</div></section></div>`;
}

// ------------------------------------------------------------------ start and events
function xBoot() {
  const gw = $('#gwrap'); gw.insertBefore($('#scanpane'), $('#gtools')); gw.insertBefore($('#hsplit'), $('#gtools'));   // the scan beside the text, above the graph
  const tabs = $('#ptabs'); tabs.prepend($('[data-tab="text"]', tabs)); $('[data-tab="check"]', tabs).removeAttribute('data-i18n');
  if (!['text', 'check', 'node'].includes(S.tab)) S.tab = 'text';
  $('#qsort').hidden = true;
  const tip = document.createElement('div'); tip.id = 'xtip'; tip.hidden = true; tip.setAttribute('role', 'tooltip'); document.body.appendChild(tip);
  for (const p in G.meta.vocab) for (const v in G.meta.vocab[p]) { const e = G.meta.vocab[p][v]; if (e.en === v) e.en = v.replace(/-/g, ' ').replace('third party', 'third-party'); }   // codes as words
}
function xWire() {
  const body = $('#pbody'); const marks = '#fnotes [data-chg], #fnotes [data-obs]';
  body.addEventListener('change', ev => { if (ev.target.id === 'notesw') setNotes(ev.target.checked); });
  body.addEventListener('mouseover', ev => { const el = ev.target.closest(marks); if (el) xTipShow(el, ev); });
  body.addEventListener('mouseout', ev => { const el = ev.target.closest(marks); if (el && !(ev.relatedTarget && el.contains(ev.relatedTarget))) xTipHide(); });
  body.addEventListener('focusin', ev => { const el = ev.target.closest(marks); if (el) xTipShow(el); });
  body.addEventListener('focusout', xTipHide);
  body.addEventListener('scroll', xTipHide, { passive: true });
  body.addEventListener('click', ev => { const f = ev.target.closest('.xfig[data-media]'); if (f) xSelectMedia(f.dataset.media, true); });
  body.addEventListener('keydown', ev => { if (ev.key === 'Enter' && ev.target.matches && ev.target.matches('[data-obs]')) ev.target.click(); });
  const ov = $('#rv-ov');
  ov.addEventListener('mouseover', ev => { const b = ev.target.closest('[data-year]'); if (b) { xTipShow(b, ev); ov.querySelectorAll('.hit.on').forEach(x => x.classList.remove('on')); b.classList.add('on'); } });
  ov.addEventListener('mouseout', ev => { const b = ev.target.closest('[data-year]'); if (b) { xTipHide(); b.classList.remove('on'); } });
  window.addEventListener('hashchange', xTipHide);
  document.addEventListener('click', ev => { if (XT.layers && !ev.target.closest('.xlay')) { XT.layers = false; if (S.view === 'entry') renderTools(); } });
}
