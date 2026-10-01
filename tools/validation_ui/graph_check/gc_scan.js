/* Graph-Prüfung — the persistent scan pane: the entry's page(s) with its region boxes, the line of the
   selected record, wheel zoom, drag pan, fit. Scans load exactly as in the explorer (scanSources:
   Drive thumbnail by file id, local JPEG as fallback). Positions come from the review layer only
   (reg, loc); nothing is drawn where the layer has no position. */

const SC = { k: 1, x: 0, y: 0, pi: 0, pages: [], W: 1675, H: 2675, hl: null, token: 0, mode: 'entry' };
const PAGE_NODE = new Map();
function pageNode(pid) {
  if (!PAGE_NODE.size) for (let n = 0; n < G.nodes.length; n++) if (G.kind[n] === KI.page) PAGE_NODE.set(pref(n, 'dcterms:identifier') || '', n);
  const n = PAGE_NODE.get(pid); return n === undefined ? -1 : n;
}
function pageShort(pid) { const m = /_(\d{3,4})(?:_([A-Za-z]+))?$/.exec(pid); return m ? t('scan_n', String(+m[1]) + (m[2] ? ' ' + (m[2].length > 1 ? m[2].toLowerCase() : m[2]) : '')) : pid; }   // …_0055_R, …_0138_full
function scanPagesOf(m) {   // [{pid, w, h, idx}] — the pages of the entry's regions, else the pages the graph links
  const out = m.pages.map(i => { const p = R.pages[i] || []; return { pid: p[0] || '', w: p[1] || 1675, h: p[2] || 2675, idx: i, known: !!(p[1] && p[2]) }; }).filter(p => p.pid);
  if (out.length) return out;
  return entryPages(m.e).map(n => ({ pid: pref(n, 'dcterms:identifier') || '', w: 1675, h: 2675, idx: -1 })).filter(p => p.pid);
}
function scanEnter(m, changed) {
  $('#scanpane').hidden = !RVU.scan; $('#hsplit').hidden = !RVU.scan;
  if (!changed && SC.pages.length) { scanDraw(); return; }
  SC.pages = scanPagesOf(m); SC.pi = 0; SC.hl = null; SC.mode = 'entry';
  scanShowPage(true);
}
function scanShowPage(fit) {
  const p = SC.pages[SC.pi]; const stage = $('#scanstage'); const img = $('#scanimg');
  scanBar();
  if (!p) { stage.hidden = true; scanMsg(t('scans_none')); return; }
  stage.hidden = false; SC.W = p.w; SC.H = p.h;
  stage.style.width = p.w + 'px'; stage.style.height = p.h + 'px';
  const src = scanSources(p.pid); const list = src.list; const token = ++SC.token; let i = 0;
  img.onload = () => {
    if (token !== SC.token) return; img.style.visibility = 'visible'; scanMsg('');
    if (!p.known && img.naturalWidth) {   // a page without layout geometry (pages that only carry images): take the proportions of the image
      p.w = SC.W = 1675; p.h = SC.H = Math.round(1675 * img.naturalHeight / img.naturalWidth); p.known = true;
      stage.style.width = p.w + 'px'; stage.style.height = p.h + 'px'; scanFit(SC.mode);
    }
  };
  img.onerror = () => { if (token !== SC.token) return; i++; if (i < list.length) img.src = list[i]; else { img.style.visibility = 'hidden'; scanMsg(t('scan_fail', p.pid + '.jpg')); } };
  img.style.visibility = 'hidden'; img.removeAttribute('src');
  if (list.length) { scanMsg(t('scan_loading')); img.src = list[0]; } else scanMsg(t('scan_fail', p.pid + '.jpg'));
  if (fit) scanFit(SC.mode); else scanApply();
}
function scanMsg(s) { const el = $('#scanmsg'); el.textContent = s; el.hidden = !s; }
function scanBar() {
  const p = SC.pages[SC.pi]; const src = p ? scanSources(p.pid) : null;
  $('#scanbar').classList.toggle('many', SC.pages.length > 3);   // many pages: the page tabs get a row of their own
  $('#scanbar').innerHTML = `<span class="scanpages">${SC.pages.map((x, i) => `<button class="zbtn${i === SC.pi ? ' on' : ''}" data-sc="p${i}" title="${esc(pageNode(x.pid) >= 0 ? label(pageNode(x.pid)) : x.pid)}">${esc(i && SC.pages.length > 3 ? pageShort(x.pid).replace(/^\D+/, '') : pageShort(x.pid))}</button>`).join('')}</span>
    <span class="sp"></span>${SC.hl && SC.hl.none ? `<span class="muted">${t(SC.hl.media ? 'scan_noregion' : 'scan_noline')}</span>` : ''}
    ${EM && (EM.rv.media || []).length ? `<button class="zbtn mtoggle${RVU.media ? ' on' : ''}" data-sc="media" title="${t('scan_media_t')}">▣ ${t('scan_media')}</button>` : ''}
    <button class="zbtn" data-sc="zout" title="−">−</button><button class="zbtn" data-sc="zin" title="+">+</button>
    <button class="zbtn" data-sc="entry" title="${t('scan_fit_entry_t')}">${t('scan_fit_entry')}</button><button class="zbtn" data-sc="page" title="${t('scan_fit_page_t')}">${t('scan_fit_page')}</button>
    ${src && src.view ? `<a class="zbtn" href="${esc(src.view)}" target="_blank" rel="noopener" title="${t('open_drive')}">Drive ↗</a>` : ''}${src && src.local ? `<a class="zbtn" href="${esc(src.local)}" target="_blank" title="${t('open_local')}">JPEG ↗</a>` : ''}
    <button class="zbtn" data-sc="hide" title="${t('scan_hide_t')}">✕</button>`;
  const on = $('#scanbar .scanpages .on'); if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
function scanRegs() { const p = SC.pages[SC.pi]; return p && EM ? (EM.rv.reg || []).filter(g => g[0] === p.idx) : []; }
function scanMedia() { const p = SC.pages[SC.pi]; return p && EM ? (EM.rv.media || []).filter(x => x[2] === p.idx && hasBox(x)) : []; }
function scanDraw() {   // overlay: region boxes of the entry, its multimodal regions, line (and word span) of the selected record
  const svg = $('#scanov'); const W = SC.W, H = SC.H; const p = SC.pages[SC.pi]; if (!p) { svg.innerHTML = ''; return; }
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const fs = clamp(12 / SC.k, 8, 90); let s = '';
  for (const g of scanRegs()) {
    const x = g[1] * W, y = g[2] * H, w = (g[3] - g[1]) * W, h = (g[4] - g[2]) * H;
    if (w >= W * 0.98 && h >= H * 0.98) continue;   // no region box known: the whole page
    s += `<rect class="reg${g[5] ? ' approx' : ''}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}"/>`;
    if (g[5]) s += `<text class="reglbl" x="${(x + 4 / SC.k).toFixed(1)}" y="${(y - 5 / SC.k).toFixed(1)}" font-size="${fs.toFixed(1)}">${esc(t('scan_approx'))}</text>`;
  }
  const hl = SC.hl;
  for (const x of scanMedia()) {   // multimodal regions: thin, their own colour, kind label; the selected one stronger
    const on = hl && hl.media === x[0]; if (!RVU.media && !on) continue;
    const mx = x[3] * W, my = x[4] * H, mw = (x[5] - x[3]) * W, mh = (x[6] - x[4]) * H;
    s += `<rect class="mreg${on ? ' on' : ''}" x="${mx.toFixed(1)}" y="${my.toFixed(1)}" width="${mw.toFixed(1)}" height="${mh.toFixed(1)}"/>` +
      `<text class="mreglbl" x="${(mx + 5 / SC.k).toFixed(1)}" y="${(my + 14 / SC.k).toFixed(1)}" font-size="${(fs * 0.92).toFixed(1)}">${esc(mediaKind(x[1]))}</text>`;
  }
  if (hl && !hl.none && !hl.media && hl.page === p.idx) {
    const x = hl.x0 * W, y = hl.y0 * H, w = (hl.x1 - hl.x0) * W, h = (hl.y1 - hl.y0) * H; const pad = Math.max(3, h * 0.18);
    s += `<rect class="line${hl.approx ? ' approx' : ''}" x="${x.toFixed(1)}" y="${(y - pad).toFixed(1)}" width="${w.toFixed(1)}" height="${(h + 2 * pad).toFixed(1)}"/>`;
    if (hl.fx1 > hl.fx0) s += `<rect class="word" x="${(x + hl.fx0 * w).toFixed(1)}" y="${(y - pad).toFixed(1)}" width="${((hl.fx1 - hl.fx0) * w).toFixed(1)}" height="${(h + 2 * pad).toFixed(1)}"/>`;
    s += `<text class="linelbl" x="${x.toFixed(1)}" y="${(y - pad - 5 / SC.k).toFixed(1)}" font-size="${fs.toFixed(1)}">${esc(hl.label + (hl.approx ? ' · ' + t('scan_approx') : ''))}</text>`;
  }
  svg.innerHTML = s;
}
function scanApply() { $('#scanstage').style.transform = `translate(${SC.x.toFixed(1)}px,${SC.y.toFixed(1)}px) scale(${SC.k.toFixed(4)})`; scanDraw(); }
function scanFit(mode) {
  const v = $('#scanview'); const vw = v.clientWidth || 500, vh = v.clientHeight || 360; const W = SC.W, H = SC.H; SC.mode = mode;
  let bx = 0, by = 0, bw = W, bh = H; const regs = scanRegs().filter(g => !(g[3] - g[1] >= 0.98 && g[4] - g[2] >= 0.98));
  if (mode === 'entry' && regs.length) {
    const x0 = Math.min(...regs.map(g => g[1])), y0 = Math.min(...regs.map(g => g[2])), x1 = Math.max(...regs.map(g => g[3])), y1 = Math.max(...regs.map(g => g[4]));
    const mx = 0.02 * W, my = 0.012 * H; bx = Math.max(0, x0 * W - mx); by = Math.max(0, y0 * H - my); bw = Math.min(W, x1 * W + mx) - bx; bh = Math.min(H, y1 * H + my) - by;
    SC.k = clamp(vw / bw, 0.05, 1.6);   // as large as the width allows; a tall entry starts at its top
  } else SC.k = Math.min(vw / bw, vh / bh);
  SC.x = (vw - bw * SC.k) / 2 - bx * SC.k;
  SC.y = bh * SC.k <= vh ? (vh - bh * SC.k) / 2 - by * SC.k : 6 - by * SC.k;
  scanApply();
}
function scanZoom(mx, my, f) { const k2 = clamp(SC.k * f, 0.05, 6); SC.x = mx - (mx - SC.x) * k2 / SC.k; SC.y = my - (my - SC.y) * k2 / SC.k; SC.k = k2; scanApply(); }
function scanHighlight(o) {   // o = record item of the entry model, or null
  if (!RVU.scan || !EM) return;
  const loc = o && o.rec.loc;
  if (!o) SC.hl = null;
  else if (!loc) SC.hl = { none: true };
  else SC.hl = { page: loc[0], x0: loc[1], y0: loc[2], x1: loc[3], y1: loc[4], approx: !!loc[5], fx0: loc[6] || 0, fx1: loc[7] || 0, label: o.written };
  if (loc) {
    const pi = SC.pages.findIndex(p => p.idx === loc[0]);
    if (pi >= 0 && pi !== SC.pi) { SC.pi = pi; scanShowPage(true); }
    const v = $('#scanview'); const vw = v.clientWidth, vh = v.clientHeight; const hl = SC.hl;
    const ly0 = SC.y + hl.y0 * SC.H * SC.k, ly1 = SC.y + hl.y1 * SC.H * SC.k, lx0 = SC.x + hl.x0 * SC.W * SC.k, lx1 = SC.x + hl.x1 * SC.W * SC.k;
    if (ly0 < 26 || ly1 > vh - 14) SC.y += vh * 0.38 - (ly0 + ly1) / 2;
    if (lx1 < 40 || lx0 > vw - 40) SC.x += vw / 2 - (lx0 + lx1) / 2;
  }
  scanBar(); scanApply();
}
function scanHighlightMedia(x) {   // a multimodal region: its page, its box
  if (!RVU.scan || !EM) return;
  const pi = SC.pages.findIndex(p => p.idx === x[2]);
  if (pi >= 0 && pi !== SC.pi) { SC.pi = pi; SC.mode = 'page'; scanShowPage(true); }
  if (!hasBox(x)) SC.hl = { none: true, media: x[0] };
  else {
    SC.hl = { media: x[0], page: x[2] };
    const v = $('#scanview'); const vw = v.clientWidth, vh = v.clientHeight; const bw = (x[5] - x[3]) * SC.W, bh = (x[6] - x[4]) * SC.H;
    if (bw * SC.k > vw - 30 || bh * SC.k > vh - 30) SC.k = Math.min((vw - 40) / bw, (vh - 40) / bh);   // too large for the pane: show the whole region
    const x0 = SC.x + x[3] * SC.W * SC.k, y0 = SC.y + x[4] * SC.H * SC.k, x1 = x0 + bw * SC.k, y1 = y0 + bh * SC.k;
    if (x0 < 6 || x1 > vw - 6) SC.x += vw / 2 - (x0 + x1) / 2;
    if (y0 < 6 || y1 > vh - 6) SC.y += vh / 2 - (y0 + y1) / 2;
  }
  scanBar(); scanApply();
}
function scanMediaAt(clientX, clientY) {   // the multimodal region under a point of the pane (the smallest one)
  const r = $('#scanview').getBoundingClientRect(); const fx = (clientX - r.left - SC.x) / SC.k / SC.W, fy = (clientY - r.top - SC.y) / SC.k / SC.H;
  const hit = (RVU.media ? scanMedia() : []).filter(x => fx >= x[3] && fx <= x[5] && fy >= x[4] && fy <= x[6]);
  hit.sort((a, b) => (a[5] - a[3]) * (a[6] - a[4]) - (b[5] - b[3]) * (b[6] - b[4])); return hit[0] || null;
}
function selectMedia(uid) {   // open the card of a region (click on its outline)
  const m = EM; if (!m) return; const i = visibleItems(m).findIndex(it => it.type === 'media' && it.x[0] === uid); if (i < 0) return;
  S.tab = 'check'; RVU.card = i; renderPanel(); focusCard(i);
}
function scanToggle(on) {
  RVU.scan = on == null ? !RVU.scan : on; store('scan', RVU.scan ? '1' : '0');
  $('#scanpane').hidden = !RVU.scan; $('#hsplit').hidden = !RVU.scan;
  if (RVU.scan && EM) { if (!SC.pages.length) SC.pages = scanPagesOf(EM); scanShowPage(true); }
  if (S.view === 'entry') renderEntryHead();
}
function scanWire() {
  const view = $('#scanview'); let drag = null;
  view.addEventListener('wheel', ev => { ev.preventDefault(); const r = view.getBoundingClientRect(); scanZoom(ev.clientX - r.left, ev.clientY - r.top, Math.exp(-ev.deltaY * 0.0016)); }, { passive: false });
  view.addEventListener('pointerdown', ev => { if (ev.button !== 0) return; drag = { x: ev.clientX, y: ev.clientY, sx: SC.x, sy: SC.y, moved: false }; view.classList.add('drag'); view.setPointerCapture(ev.pointerId); });
  view.addEventListener('pointermove', ev => { if (!drag) { view.classList.toggle('overmedia', !!scanMediaAt(ev.clientX, ev.clientY)); return; } if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3) drag.moved = true; SC.x = drag.sx + ev.clientX - drag.x; SC.y = drag.sy + ev.clientY - drag.y; $('#scanstage').style.transform = `translate(${SC.x.toFixed(1)}px,${SC.y.toFixed(1)}px) scale(${SC.k.toFixed(4)})`; });
  const end = () => { drag = null; view.classList.remove('drag'); };
  view.addEventListener('pointerup', ev => { const click = drag && !drag.moved; end(); if (click) { const x = scanMediaAt(ev.clientX, ev.clientY); if (x) selectMedia(x[0]); } });   // a click (no drag) on a region outline opens its card
  view.addEventListener('pointercancel', end);
  view.addEventListener('dblclick', () => scanFit('entry'));
  $('#scanbar').addEventListener('click', ev => {
    const b = ev.target.closest('[data-sc]'); if (!b) return; const a = b.dataset.sc; const v = $('#scanview');
    if (a === 'zin') scanZoom(v.clientWidth / 2, v.clientHeight / 2, 1.3);
    else if (a === 'zout') scanZoom(v.clientWidth / 2, v.clientHeight / 2, 1 / 1.3);
    else if (a === 'entry' || a === 'page') scanFit(a);
    else if (a === 'hide') scanToggle(false);
    else if (a === 'media') { RVU.media = !RVU.media; store('media', RVU.media ? '1' : '0'); scanBar(); scanDraw(); }
    else if (a[0] === 'p') { SC.pi = +a.slice(1); scanShowPage(true); }
  });
  const hs = $('#hsplit'); let sp = null;
  hs.addEventListener('pointerdown', ev => { sp = { y: ev.clientY, h: $('#scanpane').getBoundingClientRect().height }; hs.setPointerCapture(ev.pointerId); });
  hs.addEventListener('pointermove', ev => { if (!sp) return; const h = clamp(sp.h + ev.clientY - sp.y, 120, $('#panel').clientHeight - 160); $('#panel').style.setProperty('--scan-h', h + 'px'); });
  hs.addEventListener('pointerup', () => { if (sp) { sp = null; store('scanh', $('#panel').style.getPropertyValue('--scan-h')); scanFit(SC.mode); } });
  const sh = store('scanh'); if (sh) $('#panel').style.setProperty('--scan-h', sh);
}
