/* Graph-Prüfung — the multimodal regions of the entries (drawings, maps, photographs, prints, objects,
   text inserts, lists): crop images, cards of the check tab, large view.
   A crop loads like a scan: Drive thumbnail by file id (review layer `crops`), on error the local JPEG
   (<crops dir>/<region_uid>.jpg), on error a cut-out of the page scan by the region box (review layer
   `media`), else a note. The image elements carry inline error handlers (window.LKGC.cropErr /
   cutErr), so they work wherever their HTML is inserted (cards, node view, tooltip, large view). */

const MEDIA = new Map();   // region uid -> { x: [uid, kind, page, x0, y0, x1, y1], e: entry node, id: entry id }
const IMG_KINDS = new Set(['drawing', 'map', 'photograph', 'print', 'object']);
function mediaIndex() { for (const r of G.ent) { const rv = R.entries[r.id]; for (const x of (rv && rv.media) || []) if (!MEDIA.has(x[0])) MEDIA.set(x[0], { x, e: r.n, id: r.id }); } }
const regionUid = n => localName(n).replace(/^region_/, '');
const regionNode = uid => { const n = G.N.get('data:region_' + uid); return n === undefined ? -1 : n; };
const mediaKind = k => { const key = 'mkind_' + k; return UI[LANG][key] || UI.de[key] || k || ''; };
const hasBox = x => x && x.length >= 7 && x[5] > x[3] && x[6] > x[4];
function cropSources(uid, size) {
  const id = (R.crops || {})[uid]; const sc = G.meta.scans || {}; const out = [];
  if (id) out.push('https://drive.google.com/thumbnail?id=' + encodeURIComponent(id) + '&sz=w' + (size || 800));
  if (sc.crops) out.push(sc.crops.replace(/\/$/, '') + '/' + encodeURIComponent(uid) + '.jpg');
  return sc.mode === 'local' ? out.reverse() : out;
}
function cropFail(cls) { return `<div class="cropfail ${cls || ''}">${t('crop_fail')}</div>`; }
function cutoutHtml(uid, cls) {   // the region cut out of the page scan
  const mm = MEDIA.get(uid); const x = mm && mm.x; const pg = hasBox(x) ? R.pages[x[2]] : null; if (!pg) return cropFail(cls);
  const src = scanSources(pg[0]).list; if (!src.length) return cropFail(cls);
  const w = x[5] - x[3], h = x[6] - x[4]; const ar = (w * (pg[1] || 1675)) / (h * (pg[2] || 2675));
  return `<div class="cutout ${cls || ''}" style="aspect-ratio:${ar.toFixed(4)}" title="${esc(t('crop_cutout'))}"><img alt="" data-page="${esc(pg[0])}" data-i="0" src="${esc(src[0])}" style="width:${(100 / w).toFixed(2)}%;left:${(-x[3] / w * 100).toFixed(2)}%;top:${(-x[4] / h * 100).toFixed(2)}%" onerror="LKGC.cutErr(this)"><span class="cutnote">${t('crop_cutout')}</span></div>`;
}
function cropHtml(uid, cls, size) {
  const src = cropSources(uid, size); if (!src.length) return cutoutHtml(uid, cls);
  return `<img class="crop ${cls || ''}" alt="" loading="lazy" data-crop="${esc(uid)}" data-i="0" data-size="${size || 800}" src="${esc(src[0])}" onerror="LKGC.cropErr(this)">`;
}
function cropErr(img) {   // next source of the crop; after the last one the cut-out of the page scan
  const uid = img.dataset.crop; const list = cropSources(uid, +img.dataset.size); const i = +img.dataset.i + 1;
  if (i < list.length) { img.dataset.i = i; img.src = list[i]; return; }
  const d = document.createElement('div'); d.innerHTML = cutoutHtml(uid, img.className.replace(/\bcrop\b/, '').trim()); img.replaceWith(d.firstElementChild);
}
function cutErr(img) {
  const list = scanSources(img.dataset.page).list; const i = +img.dataset.i + 1;
  if (i < list.length) { img.dataset.i = i; img.src = list[i]; return; }
  const box = img.closest('.cutout'); const d = document.createElement('div'); d.innerHTML = cropFail(box.className.replace(/\bcutout\b/, '').trim()); box.replaceWith(d.firstElementChild);
}

// ------------------------------------------------------------------ card of the check tab
function mediaCard(m, it) {
  const x = it.x; const uid = x[0]; const n = regionNode(uid); const ins = it.ins;
  const st = ins ? (ins[3].startsWith('read-in:') ? 'readin' : ins[3]) : ''; const other = st === 'readin' ? ins[3].slice(8) : '';
  const head = `<span class="rc-kind k-media">${esc(mediaKind(x[1]))}</span><b class="rc-t">${esc(n >= 0 ? label(n) : uid)}</b>${st ? `<span class="vd vd-ins-${st}">${t('ins_' + st)}</span>` : ''}` +
    `${ins ? `<span class="rc-sum">${esc(t('ins_chars', fmt(ins[2])))}</span>` : ''}${hasBox(x) ? '' : `<span class="vd vd-off" title="${esc(t('media_nobox_t'))}">${t('media_nobox')}</span>`}`;
  const desc = n >= 0 ? pref(n, 'dcterms:description') : null; const vt = n >= 0 ? pref(n, 'lkg:visibleText') : null;
  let txt = '';
  if (desc) txt += `<div class="why">${esc(desc)}</div>`;
  if (st === 'readin') txt += `<div class="why">${t('ins_readin_hint')} <span class="link" data-go="/e/${esc(other)}">${esc(other)}</span></div>`;
  if ((st === 'unread' || st === 'partly') && !EXPLORER) txt += `<div class="hint warn">${t('ins_unread_hint')}</div>`;
  if (vt) txt += `<details class="vt"${vt.length <= 260 ? ' open' : ''}><summary>${t('visible_text')} (${fmt(vt.length)})</summary><pre>${esc(vt)}</pre></details>`;
  const body = `<div class="mrow"><div class="mthumb" data-crop-open="${esc(uid)}" title="${esc(t('crop_open'))}">${cropHtml(uid, 'thumb', 800)}</div><div class="mtext">${txt || `<span class="muted">${t('media_nodesc')}</span>`}</div></div>`;
  return { head, body, mine: '', acts: abtn('big', '', t('crop_open'), '') + abtn('j', 'J', t('a_add_rec'), st === 'unread' || st === 'partly' ? 'a-j' : '') };
}
function rvNodeExtra(n) {   // node view / node tab of a MultimodalRegion: its crop; of a record: its corpus tier
  if (kindOf(n) === 'obs') { const rec = recOfNode(n); return rec ? tierLine({ n, rec }) : ''; }
  if (kindOf(n) !== 'mmregion') return ''; const uid = regionUid(n); const mm = MEDIA.get(uid);
  return `<div class="nodecrop" data-crop-open="${esc(uid)}" title="${esc(t('crop_open'))}">${cropHtml(uid, 'node', 1000)}</div>` +
    (mm ? `<div class="muted" style="font-size:.76rem;margin:2px 0 8px">${esc(mediaKind(mm.x[1]))} · <span class="link" data-go="/e/${esc(mm.id)}">${esc(t('open_entry'))} ${esc(mm.id)}</span></div>` : '');
}
function mediaTip(v) {   // thumbnail in the tooltip of a region node of the subgraph
  if (v.kind !== 'mmregion') return ''; const uid = regionUid(v.n); const mm = MEDIA.get(uid);
  return mm && IMG_KINDS.has(mm.x[1]) ? `<div class="tipcrop">${cropHtml(uid, 'tip', 300).replace(' loading="lazy"', '')}</div>` : '';
}

// ------------------------------------------------------------------ large view (zoom, pan, Esc)
const LB = { k: 1, x: 0, y: 0, uid: null };
function lbApply() { const s = $('#lightbox .lb-stage'); if (s) s.style.transform = `translate(${LB.x.toFixed(1)}px,${LB.y.toFixed(1)}px) scale(${LB.k.toFixed(4)})`; }
function lbZoom(mx, my, f) { const k2 = clamp(LB.k * f, 0.5, 12); LB.x = mx - (mx - LB.x) * k2 / LB.k; LB.y = my - (my - LB.y) * k2 / LB.k; LB.k = k2; lbApply(); }
function openCrop(uid) {
  const box = $('#lightbox'); const n = regionNode(uid); const mm = MEDIA.get(uid); const desc = n >= 0 ? pref(n, 'dcterms:description') : '';
  Object.assign(LB, { k: 1, x: 0, y: 0, uid });
  box.innerHTML = `<div class="lb-bar"><span class="rc-kind k-media">${esc(mm ? mediaKind(mm.x[1]) : '')}</span><b>${esc(n >= 0 ? label(n) : uid)}</b><span class="lb-desc" title="${esc(desc || '')}">${esc(desc || '')}</span>
    <button class="zbtn" data-lb="zout" title="−">−</button><button class="zbtn" data-lb="zin" title="+">+</button><button class="zbtn" data-lb="fit">${t('crop_fit')}</button><button class="zbtn" data-lb="close">✕ Esc</button></div>
    <div class="lb-view"><div class="lb-stage">${cropHtml(uid, 'big', 2000).replace(' loading="lazy"', '')}</div><div class="lb-hint">${t('crop_hint')}</div></div>`;
  box.hidden = false;
}
function closeCrop() { const box = $('#lightbox'); box.hidden = true; box.innerHTML = ''; LB.uid = null; }
function mediaWire() {
  document.addEventListener('click', ev => { const c = ev.target.closest('[data-crop-open]'); if (c && !ev.target.closest('#lightbox')) openCrop(c.dataset.cropOpen); });
  const box = $('#lightbox'); let drag = null, moved = false;
  box.addEventListener('click', ev => {
    const b = ev.target.closest('[data-lb]'); const v = $('.lb-view', box);
    if (b) { const a = b.dataset.lb; if (a === 'close') closeCrop(); else if (a === 'fit') { LB.k = 1; LB.x = 0; LB.y = 0; lbApply(); } else lbZoom(v.clientWidth / 2, v.clientHeight / 2, a === 'zin' ? 1.4 : 1 / 1.4); return; }
    if (!moved && ev.target.closest('.lb-view') && !ev.target.closest('img, .cutout')) closeCrop();   // click beside the image
  });
  box.addEventListener('wheel', ev => { const v = ev.target.closest('.lb-view'); if (!v) return; ev.preventDefault(); const r = v.getBoundingClientRect(); lbZoom(ev.clientX - r.left, ev.clientY - r.top, Math.exp(-ev.deltaY * 0.0018)); }, { passive: false });
  box.addEventListener('pointerdown', ev => { if (ev.button !== 0 || !ev.target.closest('.lb-view')) return; ev.preventDefault(); drag = { x: ev.clientX, y: ev.clientY, sx: LB.x, sy: LB.y }; moved = false; });
  box.addEventListener('pointermove', ev => { if (!drag) return; const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; LB.x = drag.sx + dx; LB.y = drag.sy + dy; lbApply(); });
  const end = () => { drag = null; }; box.addEventListener('pointerup', end); box.addEventListener('pointercancel', end);
  box.addEventListener('dblclick', ev => { if (ev.target.closest('.lb-view')) { LB.k = 1; LB.x = 0; LB.y = 0; lbApply(); } });
}
