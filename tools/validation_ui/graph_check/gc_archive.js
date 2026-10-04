/* Graph-Prüfung / Graph-Explorer — images of the archive nodes.
   lkg:DiaryPage: its scan with every region outlined (text regions from the review layer `regions`, images and
   inserts from `media`), the entries written on it. lkg:SourceRegion (text) and lkg:MultimodalRegion: the
   region's image, its page, the entries whose text runs through it. Classes Seite / Quellregion / multimodale
   Region and a volume node: a paginated grid of thumbnails. Subgraph (archive layer): a small thumbnail in the
   page and region nodes, a larger one in the tooltip; selecting such a node shows its page in the scan pane.

   Image sources (scanSources, cropSources): with --image-base-url first <base>/pages/<page_id>.jpg and
   <base>/crops/<region_uid>.jpg, then the Drive thumbnail by file id, then the local JPEG; a region without an
   image of its own is cut out of its page scan by its box. Nothing is requested before it is visible: grids
   and figures fill through an IntersectionObserver, the thumbnails of the subgraph by their place in the view. */

const ARCH = { pix: null, byPage: null, io: null, vol: { n: -1, page: 0 }, GRID: 48 };
const ARCH_KINDS = new Set(['page', 'region', 'mmregion']);
const GRID_KINDS = new Set(['page', 'region', 'mmregion']);
function pageIndex(pid) { if (!ARCH.pix) { ARCH.pix = new Map(); (R.pages || []).forEach((p, i) => ARCH.pix.set(p[0], i)); } const i = ARCH.pix.get(pid); return i === undefined ? -1 : i; }
const pageIdOf = n => pref(n, 'dcterms:identifier') || '';
function pageTitle(n) { const i = pageIdOf(n); const side = /_([LR])$/.exec(i); return (label(n).replace(/\s*\([^)]*\)\s*$/, '') || i) + (side ? ' ' + side[1] : ''); }   // "Vol. 17 · scan 40 L"
function regionBox(uid) {   // [page index, x0, y0, x1, y1] of a text or multimodal region, or null
  const g = (R.regions || {})[uid]; if (g && g[3] > g[1] && g[4] > g[2]) return g;
  const mm = MEDIA.get(uid); return mm && hasBox(mm.x) ? [mm.x[2], mm.x[3], mm.x[4], mm.x[5], mm.x[6]] : null;
}
function regionPageNode(n) { const p = nodeObjs(n, 'dcterms:isPartOf').find(x => isKind(x, 'page')); return p === undefined ? -1 : p; }
function regionPageId(n) { const b = regionBox(regionUid(n)); if (b && R.pages[b[0]]) return R.pages[b[0]][0]; const p = regionPageNode(n); return p >= 0 ? pageIdOf(p) : ''; }
function pageRegions(pi) {   // every region with a box on a page: [{uid, n, box: [x0, y0, x1, y1], media: kind | null}], top to bottom
  if (!ARCH.byPage) {
    const m = ARCH.byPage = new Map(); const add = (p, r) => { let a = m.get(p); if (!a) m.set(p, a = []); a.push(r); };
    for (const uid in R.regions || {}) { const g = R.regions[uid]; if (g[3] > g[1] && g[4] > g[2]) add(g[0], { uid, box: g.slice(1), media: null }); }
    for (const [uid, mm] of MEDIA) if (hasBox(mm.x) && !(R.regions || {})[uid]) add(mm.x[2], { uid, box: mm.x.slice(3, 7), media: mm.x[1] || 'region' });
    for (const a of m.values()) a.sort((x, y) => x.box[1] - y.box[1] || x.box[0] - y.box[0]);
  }
  return ARCH.byPage.get(pi) || [];
}
const byDiary = (a, b) => (G.entPos.get(a) || 0) - (G.entPos.get(b) || 0);
function regionEntries(n) { return uniq(incoming(n, 'lkg:hasSourceRegion').concat(incoming(n, 'lkg:hasMultimodalRegion')).filter(e => isKind(e, 'entry'))).sort(byDiary); }
function pageEntries(n) {   // the entries written on a page: directly part of it, or through one of its regions
  const out = [];
  for (const x of incoming(n, 'dcterms:isPartOf')) { if (isKind(x, 'entry')) out.push(x); else if (isKind(x, 'region') || isKind(x, 'mmregion')) out.push(...regionEntries(x)); }
  return uniq(out).sort(byDiary);
}
function entryRowsHtml(list, max) {
  const cap = max || 60;
  return '<table class="t arlist">' + list.slice(0, cap).map(e => { const r = entryRec(e); return `<tr class="click" data-go="${esc(entryHash(e))}"><td class="num">${esc(r.date || pref(e, 'dwc:verbatimEventDate') || '')}</td><td>${esc(entryPlaceLabel(r))}</td><td class="mono">${esc(r.id)}</td><td class="num r" title="${t('l_records')}">${r.nobs ? fmt(r.nobs) : ''}</td></tr>`; }).join('') +
    (list.length > cap ? `<tr><td colspan="4" class="muted">${t('more', fmt(list.length - cap))}</td></tr>` : '') + '</table>';
}

// ------------------------------------------------------------------ page images
function pageImg(pid, cls, size, lazy) {
  const list = scanSources(pid, size).list; if (!list.length) return cropFail(cls);
  return `<img class="pscan ${cls || ''}" alt=""${lazy === false ? '' : ' loading="lazy"'} data-page="${esc(pid)}" data-i="0" data-size="${size || 1600}" src="${esc(list[0])}" onerror="LKGC.pageErr(this)" onload="LKGC.pageLoaded(this)">`;
}
function pageErr(img) {   // next source of the page scan; after the last one a note
  const list = scanSources(img.dataset.page, +img.dataset.size).list; const i = +img.dataset.i + 1;
  if (i < list.length) { img.dataset.i = i; img.src = list[i]; return; }
  const d = document.createElement('div'); d.innerHTML = cropFail(img.className.replace(/\bpscan\b/, '').trim()); img.replaceWith(d.firstElementChild);
}
function pageLoaded(img) {   // a page without layout geometry takes the proportions of its image
  const box = img.closest('.pagebox'); if (box && box.dataset.free === '1' && img.naturalWidth) box.style.aspectRatio = (img.naturalWidth / img.naturalHeight).toFixed(4);
}
function pageFigHtml(pid, opts = {}) {   // the scan of a page with every region outlined; a click on an outline opens the region's node
  const pi = pageIndex(pid); const p = R.pages[pi] || []; const known = !!(p[1] && p[2]); const ar = known ? p[1] / p[2] : 1675 / 2675;
  const regs = pi >= 0 ? pageRegions(pi) : []; let nt = 0;
  const marks = regs.map(r => {
    const n = regionNode(r.uid); const b = r.box; const lab = r.media ? mediaKind(r.media) : t('ar_text', ++nt);
    const tip = (n >= 0 ? label(n) : r.uid) + (n >= 0 ? regionEntries(n).slice(0, 3).map(e => ' · ' + entryRec(e).id).join('') : '');
    return `<div class="pr ${r.media ? 'pr-m' : 'pr-t'}${opts.on === r.uid ? ' on' : ''}"${n >= 0 ? ` data-n="${n}"` : ''} data-uid="${esc(r.uid)}" style="left:${(b[0] * 100).toFixed(2)}%;top:${(b[1] * 100).toFixed(2)}%;width:${((b[2] - b[0]) * 100).toFixed(2)}%;height:${((b[3] - b[1]) * 100).toFixed(2)}%" title="${esc(tip)}"><span>${esc(lab)}</span></div>`;
  }).join('');
  return `<div class="pagebox${opts.big ? ' big' : ''}" style="aspect-ratio:${ar.toFixed(4)}" data-free="${known ? 0 : 1}"${opts.big ? '' : ` data-page-open="${esc(pid)}" title="${esc(t('ar_open_page'))}"`}>${pageImg(pid, opts.big ? 'big' : 'fig', opts.big ? 2400 : 1600, !opts.big)}${marks}</div>`;
}
function openPage(pid, on) {   // large view of a page scan with its outlines (zoom, pan, Esc — as for the crops)
  const box = $('#lightbox'); const n = pageNode(pid); const src = scanSources(pid);
  Object.assign(LB, { k: 1, x: 0, y: 0, uid: null });
  box.innerHTML = `<div class="lb-bar"><span class="rc-kind k-media">${esc(kindLabel('page'))}</span><b>${esc(n >= 0 ? label(n) : pid)}</b><span class="lb-desc">${esc(t('ar_hint'))}</span>
    ${src.view ? `<a class="zbtn" href="${esc(src.view)}" target="_blank" rel="noopener">Drive ↗</a>` : ''}<button class="zbtn" data-lb="zout" title="−">−</button><button class="zbtn" data-lb="zin" title="+">+</button><button class="zbtn" data-lb="fit">${t('crop_fit')}</button><button class="zbtn" data-lb="close">✕ Esc</button></div>
    <div class="lb-view"><div class="lb-stage">${pageFigHtml(pid, { big: true, on })}</div><div class="lb-hint">${t('crop_hint')}</div></div>`;
  box.hidden = false;
}

// ------------------------------------------------------------------ node view / node tab
function rvNodeExtra(n) {   // what the node view and the node tab show above the statements
  const k = kindOf(n);
  if (k === 'obs') { const rec = recOfNode(n); return rec ? tierLine({ n, rec }) : ''; }
  if (k === 'page') {
    const pid = pageIdOf(n); const pi = pageIndex(pid); const regs = pi >= 0 ? pageRegions(pi) : []; const ents = pageEntries(n).filter(rvSrcOk);
    return `<div class="pagefig">${pageFigHtml(pid)}</div><div class="muted arhint"><span class="link" data-page-open="${esc(pid)}">⤢ ${t('ar_open_page')}</span> · ${esc(t('ar_regions', fmt(regs.filter(r => !r.media).length), fmt(regs.filter(r => r.media).length)))} · ${t('ar_hint')}</div>` +
      `<h3 class="sec">${esc(t('ar_entries_page', fmt(ents.length)))}</h3>${ents.length ? entryRowsHtml(ents) : `<p class="muted">${t('ar_no_entries')}</p>`}`;
  }
  if (k === 'region' || k === 'mmregion') {
    const uid = regionUid(n); const mm = MEDIA.get(uid); const pg = regionPageNode(n); const pid = regionPageId(n); const ents = regionEntries(n).filter(rvSrcOk); const b = regionBox(uid);
    return `<div class="nodecrop" data-crop-open="${esc(uid)}" title="${esc(t('crop_open'))}">${cropHtml(uid, 'node', 1000)}</div>` +
      `<div class="muted arhint">${esc(k === 'mmregion' ? mediaKind(mm ? mm.x[1] : '') : t('ar_textregion'))} · ${t('ar_page')}: ${pg >= 0 ? `<span class="link" data-n="${pg}">${esc(pageTitle(pg))}</span>` : esc(pid || '–')}` +
      `${pid && b ? ` · <span class="link" data-page-open="${esc(pid)}" data-on="${esc(uid)}">${t('ar_on_page')}</span>` : ''}${b ? '' : ` · ${t('media_nobox')}`}</div>` +
      `<h3 class="sec">${esc(t(k === 'mmregion' ? 'ar_entries_mm' : 'ar_entries_region', fmt(ents.length)))}</h3>${ents.length ? entryRowsHtml(ents, 20) : `<p class="muted">${t('ar_no_entries')}</p>`}`;
  }
  if (k === 'volume') {
    if (ARCH.vol.n !== n) ARCH.vol = { n, page: 0 };
    return `<div id="volgrid">${volGridHtml(n)}</div>`;
  }
  return '';
}
function archiveTip(v) {   // a larger image in the tooltip of a page or region node of the subgraph
  if (v.n < 0 || !ARCH_KINDS.has(v.kind)) return '';
  if (v.kind === 'page') return `<div class="tipcrop tippage">${pageImg(pageIdOf(v.n), 'tip', 400, false)}</div>`;
  const uid = regionUid(v.n); if (v.kind === 'mmregion') { const mm = MEDIA.get(uid); if (!mm || !IMG_KINDS.has(mm.x[1])) { if (!regionBox(uid)) return ''; } }
  return `<div class="tipcrop">${cropHtml(uid, 'tip fit', 300).replace(' loading="lazy"', '')}</div>`;
}

// ------------------------------------------------------------------ grids of thumbnails (classes, volume)
function lazyFill() {   // fill the cells that have come into view
  if (!ARCH.io) ARCH.io = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { ARCH.io.unobserve(e.target); thumbFill(e.target); } }, { rootMargin: '160px' });
  for (const el of $$('.gimg[data-thumb]:not([data-on])')) ARCH.io.observe(el);
}
function thumbFill(el) {
  el.dataset.on = '1'; const [kind, id] = el.dataset.thumb.split('|');
  el.innerHTML = kind === 'p' ? pageImg(id, 'gthumb', 400, false) : cropHtml(id, 'gthumb fit', 400).replace(' loading="lazy"', '');
}
function gridCell(n) {
  const k = kindOf(n); let th, sub;
  let lab = label(n);
  if (k === 'page') { th = 'p|' + pageIdOf(n); lab = pageTitle(n); const vol = nodeObjs(n, 'dcterms:isPartOf').find(x => isKind(x, 'volume')); sub = vol !== undefined ? label(vol).replace(/^Laubmann\s*·\s*/, '') : ''; }
  else { const uid = regionUid(n); th = 'r|' + uid; const pg = regionPageNode(n); const mm = MEDIA.get(uid); sub = (k === 'mmregion' ? mediaKind(mm ? mm.x[1] : '') : t('ar_textregion')) + (pg >= 0 ? ' · ' + pageTitle(pg) : ''); }
  return `<div class="gcell k-${k}" data-go="/n/${esc(G.nodes[n])}" title="${esc(label(n))}"><div class="gimg" data-thumb="${esc(th)}"></div><div class="gl">${esc(lab)}</div><div class="gs muted">${esc(sub)}</div></div>`;
}
const gridHtml = nodes => `<div class="agrid">${nodes.map(gridCell).join('')}</div>`;
// class view: "Tabelle / Bilder" for the classes with images
const classMode = k => (GRID_KINDS.has(k) && store('cmode.' + k) === 'img' ? 'img' : 'table');
const rvClassPer = k => (classMode(k) === 'img' ? ARCH.GRID : 100);
function rvClassSwitch(k) {
  if (!GRID_KINDS.has(k)) return ''; const m = classMode(k);
  return `<span class="seg cmode" title="${t('ar_mode_t')}"><button data-cmode="table" class="${m === 'table' ? 'on' : ''}">${t('ar_table')}</button><button data-cmode="img" class="${m === 'img' ? 'on' : ''}">${t('ar_images')}</button></span>`;
}
function rvClassBody(k, rows) { return classMode(k) === 'img' ? gridHtml(rows.map(r => r.n)) : ''; }
function rvClassAct(ev) {
  const b = ev.target.closest('[data-cmode]'); if (!b) return false;
  store('cmode.' + CV.k, b.dataset.cmode); CV.page = 0;
  CV.sort = b.dataset.cmode === 'img' ? ['ord', 1] : ['uses', -1];   // images in the order of the archive: volume, scan, position on the page
  renderClassTable(CV.kinds); return true;
}
function rvClassOrd(n, k) {   // order of the image grid: page by page, regions top to bottom
  if (k === 'page') return pageTitle(n);
  if (k === 'region' || k === 'mmregion') { const b = regionBox(regionUid(n)); const pg = regionPageNode(n); return (pg >= 0 ? pageTitle(pg) : '~') + ' | ' + (b ? String(Math.round(b[2] * 1000)).padStart(4, '0') : '9999'); }
  return '';
}
function volPages(n) { return incoming(n, 'dcterms:isPartOf').filter(x => isKind(x, 'page') && rvClassOk(x, 'page')).sort((a, b) => coll.compare(pageIdOf(a), pageIdOf(b))); }
function volGridHtml(n) {
  const pages = volPages(n); const per = ARCH.GRID; const np = Math.max(1, Math.ceil(pages.length / per)); ARCH.vol.page = clamp(ARCH.vol.page, 0, np - 1); const p = ARCH.vol.page;
  return `<h3 class="sec">${esc(t('ar_vol_pages', fmt(pages.length)))}</h3><div class="pager"><button class="btn" data-vpage="-1" ${p <= 0 ? 'disabled' : ''}>◀</button><span>${t('page_n', p + 1, np)}</span><button class="btn" data-vpage="1" ${p >= np - 1 ? 'disabled' : ''}>▶</button></div>` +
    gridHtml(pages.slice(p * per, p * per + per));
}

// ------------------------------------------------------------------ subgraph: thumbnails inside page and region nodes
function thumbBox(v) {   // a fixed box, so that the layout does not jump when the image arrives
  if (v.n < 0 || !ARCH_KINDS.has(v.kind)) return null;
  if (v.kind === 'page') return pageIdOf(v.n) ? { w: 64, h: 100, id: 'p|' + pageIdOf(v.n) } : null;
  const uid = regionUid(v.n); if (!regionBox(uid) && !cropSources(uid, 400).length) return null;
  return { w: v.w - 16, h: 66, id: 'r|' + uid };
}
function rvThumbSvg(v) {
  const b = v.th; if (!b) return '';
  return `<svg class="nthumb" x="8" y="${v.hh + 2}" width="${b.w}" height="${b.h}" viewBox="0 0 ${b.w} ${b.h}" data-thumb="${esc(b.id)}" data-w="${b.w}" data-h="${b.h}"><rect class="tbg" width="${b.w}" height="${b.h}" rx="3"/><svg class="ti" width="${b.w}" height="${b.h}"><image width="${b.w}" height="${b.h}"/></svg></svg>`;
}
function thumbStart(el) {   // sources in turn: the region's own image, then the cut-out of its page scan
  el.dataset.on = '1'; const [kind, id] = el.dataset.thumb.split('|'); const w = +el.dataset.w, h = +el.dataset.h; const im = el.querySelector('image'); const ti = el.querySelector('svg.ti'); let list;
  const set = (node, o) => { for (const k in o) node.setAttribute(k, o[k]); };
  if (kind === 'p') list = scanSources(id, 400).list.map(src => ({ src }));
  else {
    list = cropSources(id, 400).map(src => ({ src })); const b = regionBox(id); const pg = b && R.pages[b[0]];
    if (pg) for (const src of scanSources(pg[0], 1600).list) list.push({ src, cut: b, W: pg[1] || 1675, H: pg[2] || 2675 });
  }
  let i = 0;
  const next = () => {
    const s = list[i++]; if (!s) { el.dataset.fail = '1'; im.removeAttribute('href'); return; }
    if (s.cut) {   // the inner viewport clips the page scan to the region and is fitted into the box
      const bw = (s.cut[3] - s.cut[1]) * s.W, bh = (s.cut[4] - s.cut[2]) * s.H; const f = Math.min(w / bw, h / bh);
      set(ti, { x: ((w - bw * f) / 2).toFixed(1), y: ((h - bh * f) / 2).toFixed(1), width: (bw * f).toFixed(1), height: (bh * f).toFixed(1), viewBox: `${(s.cut[1] * s.W).toFixed(1)} ${(s.cut[2] * s.H).toFixed(1)} ${bw.toFixed(1)} ${bh.toFixed(1)}`, preserveAspectRatio: 'none' });
      set(im, { width: s.W, height: s.H, preserveAspectRatio: 'none' }); el.dataset.cut = '1';
    } else { set(ti, { x: 0, y: 0, width: w, height: h, viewBox: `0 0 ${w} ${h}` }); ti.removeAttribute('preserveAspectRatio'); set(im, { width: w, height: h }); im.removeAttribute('preserveAspectRatio'); }
    im.setAttribute('href', s.src);
  };
  im.addEventListener('error', next); im.addEventListener('load', () => { el.dataset.ok = '1'; });
  next();
}
function thumbsSync() {   // request the thumbnails of the nodes that are inside the canvas (called after drawing, panning, zooming)
  thumbsSync.raf = 0; if (!SUB || S.view !== 'entry') return; const c = $('#gcanvas'); const W = c.clientWidth, H = c.clientHeight; if (!W || !H) return;
  for (const el of $$('#gsvg svg.nthumb:not([data-on])')) {
    const g = el.closest('.nd'); const v = g && SUB.V.get(g.dataset.key); if (!v) continue;
    const x0 = Z.x + v.x * Z.k, y0 = Z.y + v.y * Z.k, x1 = x0 + v.w * Z.k, y1 = y0 + v.h * Z.k;
    if (x1 > -120 && x0 < W + 120 && y1 > -120 && y0 < H + 120) thumbStart(el);
  }
}
function thumbsSoon() { if (!thumbsSync.raf) thumbsSync.raf = requestAnimationFrame(thumbsSync); }

// ------------------------------------------------------------------ scan pane: the page / region of a selected archive node
function scanShowArchive(n) {
  if (!RVU.scan || !EM) return false; const k = kindOf(n); if (!ARCH_KINDS.has(k)) return false;
  const uid = k === 'page' ? null : regionUid(n);
  if (uid) { const x = (EM.rv.media || []).find(m => m[0] === uid); if (x) { scanHighlightMedia(x); return true; } }
  const pid = k === 'page' ? pageIdOf(n) : regionPageId(n); if (!pid) return false;
  let pi = SC.pages.findIndex(p => p.pid === pid);
  if (pi < 0) { const ix = pageIndex(pid); const p = R.pages[ix] || []; SC.pages.push({ pid, w: p[1] || 1675, h: p[2] || 2675, idx: ix, known: !!(p[1] && p[2]) }); pi = SC.pages.length - 1; }
  if (pi !== SC.pi) { SC.pi = pi; SC.mode = 'page'; scanShowPage(true); }
  const b = uid ? regionBox(uid) : null;
  if (!b) { SC.hl = uid ? { none: true, media: uid } : null; if (!uid) scanFit('page'); else { scanBar(); scanApply(); } return true; }
  SC.hl = { box: b.slice(1), page: b[0], region: uid, label: label(n) };
  const v = $('#scanview'); const vw = v.clientWidth, vh = v.clientHeight; const bw = (b[3] - b[1]) * SC.W, bh = (b[4] - b[2]) * SC.H;
  if (bw * SC.k > vw - 30 || bh * SC.k > vh - 30) SC.k = Math.min((vw - 40) / bw, (vh - 40) / bh);
  const x0 = SC.x + b[1] * SC.W * SC.k, y0 = SC.y + b[2] * SC.H * SC.k, x1 = x0 + bw * SC.k, y1 = y0 + bh * SC.k;
  if (x0 < 6 || x1 > vw - 6) SC.x += vw / 2 - (x0 + x1) / 2;
  if (y0 < 6 || y1 > vh - 6) SC.y += vh / 2 - (y0 + y1) / 2;
  scanBar(); scanApply(); return true;
}
function archiveWire() {
  document.addEventListener('click', ev => {
    if (ev.target.closest('#lightbox [data-n]')) { closeCrop(); return; }   // an outline in the large view: the explorer's handler opens the node
    const po = ev.target.closest('[data-page-open]'); if (po && !ev.target.closest('.pr[data-n]')) { ev.preventDefault(); openPage(po.dataset.pageOpen, po.dataset.on || null); return; }
    const vp = ev.target.closest('[data-vpage]'); if (vp && $('#volgrid')) { ARCH.vol.page += +vp.dataset.vpage; $('#volgrid').innerHTML = volGridHtml(ARCH.vol.n); lazyFill(); }
  });
  // views are redrawn with innerHTML: fill what has come into view after each change
  new MutationObserver(() => { if (!lazyFill.raf) lazyFill.raf = requestAnimationFrame(() => { lazyFill.raf = 0; lazyFill(); }); }).observe($('#app'), { childList: true, subtree: true });
}
