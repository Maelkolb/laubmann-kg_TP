/* Graph-Prüfung — the check tab ("Prüfen"): one compact card per decidable item of the entry, grouped;
   the actions behind J N E X U, the inline forms, the keyboard. */

const fieldLabel = f => { const k = 'f_' + f; return UI[LANG][k] || UI.de[k] || f; };
const srcName = c => t(c === 'g' ? 'src_g' : c === 's' ? 'src_s' : c === 'h' ? 'src_h' : 'src_m');
const markup = s => esc(s).replace(/&lt;(\/?)u&gt;/g, '<$1u>').replace(/\n/g, '<span class="nl">⏎</span> ');
const kbd = k => `<kbd>${k}</kbd>`;
const abtn = (act, key, lab, cls, dis) => `<button type="button" class="abtn ${cls || ''}" data-act="${act}"${dis ? ' disabled' : ''}>${key ? kbd(key) + ' ' : ''}${esc(lab)}</button>`;
function gbifLink(key) { return key ? `<a href="https://www.gbif.org/species/${esc(key)}" target="_blank" rel="noopener">GBIF ${esc(key)} ↗</a>` : ''; }
function authLinks(a) {
  const out = [];
  if (a.gbif) out.push(gbifLink(a.gbif));
  if (a.wd) out.push(`<a href="https://www.wikidata.org/wiki/${esc(a.wd)}" target="_blank" rel="noopener">Wikidata ${esc(a.wd)} ↗</a>`);
  if (a.gnd) out.push(`<a href="https://d-nb.info/gnd/${esc(a.gnd)}" target="_blank" rel="noopener">GND ${esc(a.gnd)} ↗</a>`);
  if (a.gn) out.push(`<a href="https://www.geonames.org/${esc(a.gn)}" target="_blank" rel="noopener">GeoNames ${esc(a.gn)} ↗</a>`);
  if (a.osm) out.push(`<a href="https://www.openstreetmap.org/${esc(a.osm)}" target="_blank" rel="noopener">OSM ↗</a>`);
  if (a.eunis) out.push(`EUNIS ${esc(a.eunis)}`);
  return out.join(' · ');
}
function linkHtml(section, a) {   // an entity link as build_review.py lists it (before / now)
  if (!a) return `<span class="muted">${t('link_none')}</span>`;
  if (section === 'taxa') return `${esc(a[0])}${a[1] ? ` <i>${esc(a[1])}</i>` : ''} ${a[2] ? gbifLink(a[2]) : `<span class="muted">${t('link_nogbif')}</span>`}`;
  if (section === 'persons') return `${esc(a[0])} ${authLinks({ wd: a[1], gnd: a[2] }) || `<span class="muted">${t('link_noauth')}</span>`}`;
  if (section === 'places') return `${esc(a[0])} ${a[1] != null && a[1] !== '' ? `<span class="num">${(+a[1]).toFixed(4)}, ${(+a[2]).toFixed(4)}</span> ` + authLinks({ gn: a[3], wd: a[4] }) : `<span class="muted">${t('link_nocoord')}</span>`}`;
  return `${esc(a[0])} ${a[1] ? `EUNIS ${esc(a[1])}${a[2] ? ` (${esc(t(a[2]) === a[2] ? a[2] : t(a[2]))})` : ''}` : `<span class="muted">${t('link_noauth')}</span>`}`;
}
function rowHtml(section, r) {   // what a machine row decides
  const a = authMap(r.auth); const kind = t('kind_' + KIND_OF_SECTION[section]);
  if (r.d === 'none') return `<b>${esc(t('row_none', kind))}</b>`;
  if (r.d === 'nolink') return `<b>${esc(t('row_nolink'))}</b>`;
  if (r.d === 'own') return `<b>${esc(t('row_own'))}</b>`;
  let s = `<b>${esc(r.t || '')}</b>${r.sci ? ` <i>${esc(r.sci)}</i>` : ''}${r.rank ? ` <span class="muted">${esc(r.rank)}</span>` : ''}`;
  if (r.lat != null) s += ` <span class="num">${(+r.lat).toFixed(4)}, ${(+r.lon).toFixed(4)}</span>`;
  if (r.eunis) s += ` <span class="muted">(${esc(r.eunis)})</span>`;
  const al = authLinks(a); return s + (al ? ' ' + al : '');
}
const decName = (type, d) => t('d_' + type + '_' + d);
function mineHtml(type, d, extra) {
  return `<div class="mine"><span class="tick">✓</span> <span class="ml">${t('mine')}:</span> <b>${esc(decName(type, d.d))}</b>${extra ? ' ' + extra : ''}<span class="link reset" data-act="reset">${t('reset')}</span></div>`;
}
function valsHtml(vals, old) { return Object.keys(vals || {}).map(k => `<span class="hv"><span class="fl">${esc(fieldLabel(k))}</span> ${old && old[k] ? `<span class="was">${esc(showVal(k, old[k]))}</span> → ` : ''}<b>${esc(showVal(k, vals[k]))}</b></span>`).join(' '); }

// ------------------------------------------------------------------ cards
function srcBlock(p, cur) {
  let s = `<div class="src src-${p.src}"><div class="src-h"><span class="who">${srcName(p.src)}</span><span class="vd vd-${p.v}">${t('v_' + p.v)}</span>` +
    p.fields.map(f => `<span class="fchip">${esc(fieldLabel(f))}</span>`).join('') + (p.c != null ? `<span class="conf" title="${t('conf_t')}">${fmtConf(p.c)}</span>` : '') + '</div>';
  for (const k in p.vals) s += `<div class="diff"><span class="fl">${esc(fieldLabel(k))}</span><span class="is">${esc(showVal(k, cur[k]) || '—')}</span><span class="arr">→</span><span class="to">${esc(showVal(k, p.vals[k]))}</span>${k === 'species' && p.vals[k].key ? ' ' + gbifLink(p.vals[k].key) : ''}</div>`;
  for (const k in p.bad) s += `<div class="diff bad"><span class="fl">${esc(fieldLabel(k))}</span><span class="is">${esc(showVal(k, cur[k]) || '—')}</span><span class="arr">→</span><span class="to">${esc(p.bad[k])}</span><span class="hint">${t('bad_format')}</span></div>`;
  if (p.georef) s += `<div class="diff geo"><span class="fl">${esc(fieldLabel('georef'))}</span><span class="to">${esc(p.georef)}</span></div>`;
  for (const o of p.other) s += `<div class="diff other">${esc(o)}</div>`;
  if (p.why) s += `<div class="why">${esc(p.why)}</div>`;
  if (p.q) s += `<div class="quote">„${esc(p.q)}“ <span class="qin ${p.qin ? 'yes' : 'no'}">${t(p.qin ? 'q_in' : 'q_notin')}</span></div>`;
  return s + '</div>';
}
const fmtConf = c => new Intl.NumberFormat(LANG === 'de' ? 'de-DE' : 'en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(c);
function recSummary(cur) { return [cur.count, cur.locality, cur.date, cur.observer && cur.observer !== 'Alfred Laubmann' ? cur.observer : '', cur.record_type && cur.record_type !== 'field-observation' ? showVal('record_type', cur.record_type) : ''].filter(Boolean).join(' · '); }
function recCard(m, it) {
  const o = it.o; const d = RV.dec[it.key]; const cur = recVals(o.n); const tx = node1(o.n, 'lkg:observedTaxon');
  const ps = ['g', 's'].map(c => proposal(o, c)).filter(Boolean); const mp = mergedProposal(o); const auto = o.rec.auto || [];
  const fl = ['g', 's'].filter(c => o.rec[c] && (o.rec[c].v === 'wrong' || o.rec[c].v === 'spurious'));
  let body = '';
  if (o.rec.g && o.rec.s) {
    if (fl.length === 2) body += `<div class="agree both">${t('agree_both')}</div>`;
    else if (fl.length === 1) { const other = fl[0] === 'g' ? 's' : 'g'; body += `<div class="agree conflict">${esc(t(o.rec[other].v === 'ok' ? 'agree_conflict' : 'agree_unsure', srcName(fl[0]), srcName(other)))}</div>`; }
  }
  for (const p of ps) body += srcBlock(p, cur);
  for (const a of auto) body += `<div class="src src-m"><div class="src-h"><span class="who">${t('src_auto')}</span><span class="vd vd-auto">${t('auto_applied')}</span></div><div class="diff"><span class="fl">${esc(fieldLabel(a[0] === 'value' ? 'species' : a[0]))}</span><span class="is">${esc(a[1] || '—')}</span><span class="arr">→</span><span class="to">${esc(a[2])}</span></div>${a[3] ? `<div class="why">${esc(a[3])}</div>` : ''}</div>`;
  if (ps.some(p => p.georef)) body += `<div class="geonote">${t('geo_note')}</div>`;
  body += tierLine(o);
  let jLab = t('a_apply'), jDis = false;
  if (!d) {
    if (mp && mp.drop) body += `<div class="preview">${t('j_drop')}</div>`;
    else if (mp && Object.keys(mp.bad).length) body += `<div class="preview">${esc(t('j_form', Object.keys(mp.bad).map(fieldLabel).join(', ')))}${Object.keys(mp.vals).length ? ' · ' + valsHtml(mp.vals) : ''}</div>`;
    else if (mp && (ps.length > 1 || mp.geo) && Object.keys(mp.vals).length) body += `<div class="preview">${t('j_applies')}: ${valsHtml(mp.vals)}</div>`;
  }
  if (mp && mp.drop) jLab = t('a_drop_j');
  else if (mp && mp.geo && Object.keys(mp.vals).length === 1) jLab = t('a_geo_j');
  else if (!mp || !(Object.keys(mp.vals).length || Object.keys(mp.bad).length)) { if (auto.length) jLab = t('a_confirm'); else jDis = true; }
  const head = `<span class="rc-kind k-rec">${t('c_rec')}</span><b class="rc-t">${esc(o.written)}</b>${tx >= 0 && cf(label(tx)) !== cf(o.written) ? `<span class="muted">= ${esc(label(tx))}</span>` : ''}<span class="rc-sum">${esc(recSummary(cur))}</span>`;
  const mine = d && d.d ? mineHtml('rec', d, d.vals ? valsHtml(d.vals, d.old) : '') : '';
  const acts = abtn('j', 'J', jLab, 'a-j', jDis) + abtn('n', 'N', auto.length && !ps.length ? t('a_revert') : t('a_rec_ok'), 'a-n') + abtn('e', 'E', t('a_edit'), '') + abtn('x', 'X', t('a_drop'), 'a-x') + abtn('u', 'U', t('a_unsure'), '') +
    (auto.length && ps.length ? abtn('r', '', t('a_revert_auto'), '') : '');
  return { head, body, mine, acts };
}
function missCard(m, it) {
  const x = it.x; const d = RV.dec[it.key]; const isObs = x.kind === 'observation';
  const chips = [x.count && [t('f_count'), x.count], x.loc && [t('f_locality'), x.loc], x.date && [t('f_date'), x.date], x.obs && [t('f_observer'), x.obs]].filter(Boolean);
  const head = `<span class="rc-kind k-miss">${t(isObs ? 'c_miss' : 'c_miss_other')}</span>${isObs ? `<b class="rc-t">${esc(x.de || '?')}</b>${x.sci ? `<i class="muted">${esc(x.sci)}</i>` : ''}` : `<b class="rc-t">${esc(t('mk_' + (x.kind || 'other')))}</b>`}`;
  let body = '';
  if (x.src !== 'h') body += `<div class="src src-${x.src}"><div class="src-h"><span class="who">${srcName(x.src)}</span>${it.also ? `<span class="who">+ ${srcName(it.also.src)}</span>` : ''}<span class="vd vd-sugg">${t('v_missing')}</span>${x.c != null ? `<span class="conf">${fmtConf(x.c)}</span>` : ''}</div>` +
    chips.map(c => `<div class="diff"><span class="fl">${esc(c[0])}</span><span class="to">${esc(c[1])}</span></div>`).join('') +
    (x.note ? `<div class="why">${esc(x.note)}</div>` : '') + (x.text ? `<div class="quote">„${markup(x.text)}“ <span class="qin ${x.in_text ? 'yes' : 'no'}">${t(x.in_text ? 'q_in' : 'q_notin')}</span></div>` : '') + '</div>';
  if (it.also && it.x.src !== it.also.src) body = `<div class="agree both">${t('agree_miss')}</div>` + body;
  if (!isObs) body += `<div class="hint">${t('miss_other_hint')}</div>`;
  const rec = d && d.rec;
  const mine = d && d.d ? mineHtml('miss', d, rec ? `<span class="hv"><b>${esc(rec.species_de)}</b>${rec.scientific_name ? ` <i>${esc(rec.scientific_name)}</i>` : ''} ${esc([rec.count, rec.locality, rec.date, rec.observer, rec.record_type].filter(Boolean).join(' · '))}</span>` : '') : '';
  const acts = abtn('j', 'J', t('a_add'), 'a-j', !isObs) + abtn('n', 'N', t(isObs ? 'a_noadd' : 'a_noted'), 'a-n');
  return { head, body, mine, acts };
}
function nameCard(m, it) {
  const x = it.x; const info = x.info; const d = RV.dec[it.key]; const sec = x.section; const kind = t('kind_' + KIND_OF_SECTION[sec]);
  const head = `<span class="rc-kind k-name">${esc(kind)}</span><b class="rc-t">„${esc(x.form)}“</b><span class="vd vd-${x.kind === 'suggest' ? 'sugg' : x.kind === 'confirmed' ? 'conf' : 'auto'}">${t('nk_' + x.kind)}</span>`;
  let body = '';
  if (x.kind === 'changed') body += `<div class="diff2"><div><span class="fl">${t('before')}</span>${linkHtml(sec, info.before)}</div><div><span class="fl">${t('now')}</span>${linkHtml(sec, info.now)}</div></div>`;
  else if (x.kind === 'suggest') body += `<div class="diff2"><div><span class="fl">${t('now')}</span>${linkHtml(sec, info.now)}</div></div>`;
  else if (x.kind === 'confirmed') body += `<div class="diff2"><div><span class="fl">${t('now')}</span>${linkHtml(sec, info.now)}</div></div>`;
  for (const r of info.rows || []) {
    if (x.kind !== 'suggest' && !r.auto && (info.rows || []).some(q => q.auto)) continue;
    body += `<div class="src src-m"><div class="src-h"><span class="who">${esc(t('src_round', r.rnd || '?'))}</span><span class="vd vd-${r.auto ? 'auto' : 'sugg'}">${t(r.auto ? 'row_applied' : 'row_suggest')}</span>` +
      String(r.src || '').split('+').filter(Boolean).map(sname => `<span class="fchip" title="${t('src_t')}">${esc(sname)}</span>`).join('') +
      `<span class="conf" title="${t('conf_t')}">${fmtConf(r.c || 0)} · ${esc(t(+r.ag === 1 ? 'n_source1' : 'n_sources', r.ag || 0))}</span></div>` +
      `<div class="diff"><span class="fl">${t(r.auto ? 'row_decides' : 'row_proposes')}</span><span class="to">${rowHtml(sec, r)}</span></div>` +
      (r.why ? `<div class="why">${esc(r.why)}</div>` : '') + (r.note ? `<div class="why muted">${esc(r.note)}</div>` : '') +
      (!r.auto ? `<div class="hint">${esc(t('below_threshold', fmtConf((R.meta.thresholds || {}).confidence || 0.9), (R.meta.thresholds || {}).agreement || 2))}</div>` : '') + '</div>';
  }
  if (x.detail) body += `<div class="why">${esc(x.detail)}</div>`;
  const n = mentionCount(sec, x.form, x.nodes);
  body += `<div class="scope">${t('name_scope')}${n ? ' · ' + esc(t(sec === 'taxa' ? 'name_mentions' : 'name_uses', fmt(n))) : ''}${x.kind !== 'suggest' && x.kind !== 'confirmed' ? '' : ' · ' + t('name_linkpage')}</div>`;
  const mine = d && d.d ? mineHtml('name', d) : '';
  const acts = x.kind === 'suggest' ? abtn('j', 'J', t('a_apply'), 'a-j') + abtn('n', 'N', t('a_reject'), 'a-n')
    : x.kind === 'confirmed' ? abtn('j', 'J', t('a_confirm'), 'a-j') + abtn('n', 'N', t('a_wrong'), 'a-n')
      : abtn('j', 'J', t('a_confirm'), 'a-j') + abtn('n', 'N', t('a_revert'), 'a-n');
  return { head, body, mine, acts };
}
function tcCard(m, it) {
  const c = it.c; const d = RV.dec[it.key]; const rel = (c[5] || '').split('').map(ch => `<span class="fchip rel">${t('rel_' + ch)}</span>`).join('');
  const head = `<span class="rc-kind k-tc">${t('c_tc')}</span><span class="rc-t">${t('tck_' + c[4])}</span>${rel}${c[2] ? '' : `<span class="vd vd-off">${t('tc_unapplied')}</span>`}`;
  let body = `<div class="tcdiff"><del>${markup(c[0])}</del><span class="arr">→</span><ins>${markup(c[1])}</ins></div>`;
  const vs = [];
  if (c[6]) vs.push(`<span class="who">${srcName('s')}</span><span class="vd vd-tc-${c[6]}">${t('tcv_' + c[6])}</span>`);
  if (c[7]) vs.push(`<span class="who">${srcName('g')}</span><span class="vd vd-tc-${c[7]}">${t('tcv_' + c[7])}</span>`);
  else if ((m.rv.chk || '').includes('g')) vs.push(`<span class="who">${srcName('g')}</span><span class="vd vd-tc-none">${t('tcv_none')}</span>`);
  if (vs.length) body += `<div class="src-h">${vs.join('')}</div>`;
  if (c[8]) body += `<div class="diff"><span class="fl">${t('tc_better')}</span><span class="to">„${markup(c[8])}“</span></div>`;
  const mine = d && d.d ? mineHtml('tc', d, d.d === 'edit' ? `<span class="hv">„${markup(d.final || '')}“</span>` : '') : '';
  const acts = abtn('j', 'J', t('a_tc_ok'), 'a-j') + abtn('n', 'N', t('a_tc_no'), 'a-n') + abtn('e', 'E', t('a_tc_edit'), '');
  return { head, body, mine, acts };
}
function entProposal(m) {   // entry-level findings of both checks as exportable values
  const out = { vals: {}, bad: {}, from: {}, notes: [] }; const ent = m.rv.ent || {}; const cur = entCur(m); const curPlace = cur.place || cur.header;
  for (const c of ['s', 'g']) { const f = ent[c]; if (!f) continue;
    if (f.date_ok === false) { const v = f.date && fieldCheck('entry_date', f.date); if (v) { if (!out.vals.date && v !== cur.date) { out.vals.date = v; out.from.date = c; } } else if (f.date) out.bad.date = f.date; }
    if (f.kind_ok === false) { const v = f.kind && fieldCheck('entry_kind', f.kind); if (v) { if (!out.vals.kind && v !== cur.kind) { out.vals.kind = v; out.from.kind = c; } } else if (f.kind) out.bad.kind = f.kind; }
    if (f.place_ok === false && f.place && !out.vals.place && cf(f.place) !== cf(curPlace)) { out.vals.place = f.place; out.from.place = c; }
    if (f.note) out.notes.push([c, f.note]); }
  return out;
}
function entCur(m) { const e = m.e; const ep = node1(e, 'lkg:entryPlace'); return { date: litsOf(e, 'dwc:eventDate').join('/'), place: ep >= 0 ? nameOf(ep) : '', header: prefDe(e, 'dwc:verbatimLocality') || '', kind: prefDe(e, 'lkg:entryKind') || '', vdate: prefDe(e, 'dwc:verbatimEventDate') || '' }; }
function entCard(m, it) {
  const d = RV.dec[it.key] || {}; const cur = entCur(m); const ent = m.rv.ent || {}; const p = entProposal(m);
  const head = `<span class="rc-kind k-ent">${t('c_ent')}</span><b class="rc-t">${esc(cur.date || cur.vdate || '—')}</b><span class="rc-sum">${esc([cur.place || cur.header, cur.kind ? cv('lkg:entryKind', cur.kind) : ''].filter(Boolean).join(' · '))}</span>`;
  const row = (f, lab, curv, show) => {
    let s = `<div class="diff"><span class="fl">${esc(lab)}</span><span class="is">${esc(show(curv) || '—')}</span>`;
    for (const c of ['g', 's']) { const fnd = ent[c]; if (!fnd || fnd[f + '_ok'] !== false) continue;
      const ok = f === 'place' ? fnd.place : fnd[f] && fieldCheck('entry_' + f, fnd[f]);
      if (ok && cf(ok) === cf(curv)) { s += `<span class="who">${srcName(c)}</span><span class="hint">${t('ent_same')}</span>`; continue; }
      s += `<span class="arr">→</span><span class="to${ok || !fnd[f] ? '' : ' badv'}">${esc(fnd[f] ? (ok ? show(ok) : fnd[f]) : t('ent_wrong'))}</span><span class="who">${srcName(c)}</span>${fnd[f] && !ok ? `<span class="hint">${t(f === 'kind' ? 'bad_kind' : 'bad_format')}</span>` : ''}`; }
    if (d[f]) s += `<span class="hv"><span class="tick">✓</span> <b>${esc(show(d[f].v))}</b></span>`;
    return s + '</div>';
  };
  let body = row('date', t('date'), cur.date, v => v) + (cur.vdate ? `<div class="diff sub"><span class="fl">${t('v_date')}</span><span class="is">${esc(cur.vdate)}</span></div>` : '') +
    row('place', t('place'), cur.place || cur.header, v => v) + row('kind', t('kind'), cur.kind, v => (v ? cv('lkg:entryKind', v) : ''));
  for (const [c, note] of p.notes) body += `<div class="why"><span class="who">${srcName(c)}</span> ${esc(note)}</div>`;
  const has = Object.keys(p.vals).length > 0;
  const decided = d.date || d.kind || d.place || d.hdr;
  const mine = decided ? `<div class="mine"><span class="tick">✓</span> <span class="ml">${t('mine')}:</span> <b>${esc(d.hdr === 'ok' && !(d.date || d.kind || d.place) ? t('d_ent_ok') : t('d_ent_set'))}</b><span class="link reset" data-act="reset">${t('reset')}</span></div>` : '';
  const acts = abtn('j', 'J', t('a_apply'), 'a-j', !has) + abtn('n', 'N', t('a_ent_ok'), 'a-n') + abtn('e', 'E', t('a_edit'), '');
  return { head, body, mine, acts };
}
const qaLabel = r => { const k = 'qa_' + r; return UI[LANG][k] || UI.de[k] || r; };
function qaCard(m, it) {
  const q = it.q; const d = RV.dec[it.key]; const ex = q[1] === 'excluded';
  const head = `<span class="rc-kind k-qa">${t(ex ? 'c_gone' : 'c_qa')}</span><b class="rc-t${ex ? ' strike' : ''}">${esc(q[2] && q[2].length < 60 ? q[2] : qaLabel(q[0]))}</b><span class="rc-sum">${esc(q[2] && q[2].length < 60 ? qaLabel(q[0]) : '')}</span>`;
  const body = `<div class="why">${esc(q[3] || '')}</div>${q[2] && q[2].length >= 60 ? `<div class="quote">${esc(q[2])}</div>` : ''}${ex ? `<div class="hint">${t(QA_UNDO.has(q[0]) ? 'qa_ex_hint' : 'qa_ex_noeffect')}</div>` : ''}`;
  const mine = d && d.d ? mineHtml('qa', d) : '';
  return { head, body, mine, acts: abtn('j', 'J', t('a_confirm'), 'a-j') + abtn('n', 'N', t('a_false_alarm'), 'a-n') };
}
const QA_UNDO = new Set(['non_bird', 'low_confidence_taxon', 'implausible_date']);   // qa.py: a false alarm brings these back
// the cards of multimodal regions (images, inserts) are in gc_media.js
// what holds back "geprüft" (asks twice): open items of level schwer or mittel; images and inserts have no decision
function openFindings(m) { return m.items.filter(it => it.lv >= 2 && it.type !== 'media' && it.type !== 'done' && !itemDecided(it) && !(it.type === 'rec' && corpusOn() && !inCorpus(it.o.n))).length; }
function doneCard(m) {
  const d = entryDec(m.uid); const open = openFindings(m); const undecided = m.obs.filter(o => !isDecided(o.key)).length;
  if (d.checked) return { head: `<span class="tick big">✓</span><b class="rc-t">${t('checked')}</b><span class="rc-sum">${esc((d.checked.t || '').slice(0, 16).replace('T', ' ') + (d.checked.by ? ' · ' + d.checked.by : ''))}</span>`, body: '', mine: '', acts: abtn('reset', '', t('a_uncheck'), '') };
  return { head: `<b class="rc-t">${t('finish')}</b>`, body: `<div class="why">${esc(t('finish_hint', fmt(undecided), fmt(m.obs.length)))}</div>${open ? `<div class="hint warn">${esc(t(RVU.armed ? 'finish_open_again' : 'finish_open', fmt(open)))}</div>` : ''}`, mine: '',
    acts: abtn('done', '⏎', t(open && RVU.armed ? 'a_done_anyway' : 'a_done'), 'primary') };
}
const CARD = { rec: recCard, miss: missCard, name: nameCard, tc: tcCard, ent: entCard, qa: qaCard, media: mediaCard, done: doneCard };
function markPill(it, done) {   // marker = kind of flag, colour = level; a decided item carries the green tick
  if (done) return '<span class="mkp dec" title="' + esc(t('lg_ok')) + '">✓</span>';
  return it.mk ? `<span class="mkp lv${it.lv}" title="${esc(lvName(it.lv) + ' · ' + t('mk_' + ({ '!': 'f', M: 'a', '?': 's', '×': 'r', i: 'h' }[it.mk] || 'h')))}">${esc(it.mk)}</span>` : '';
}
function cardHtml(m, it, i) {
  const c = CARD[it.type](m, it); const done = itemDecided(it); const form = RVU.form && RVU.form.key === it.key ? formHtml(m, it) : '';
  const out = it.type === 'rec' && corpusOn() && !inCorpus(it.o.n);
  return `<div class="rcard t-${it.type} lv${it.type === 'done' ? 'x' : it.lv}${done ? ' done' : ''}${out ? ' out' : ''}${i === RVU.card ? ' focus' : ''}" data-ci="${i}"><div class="rc-head">${it.type === 'done' ? '' : markPill(it, done)}${c.head}</div>${c.mine}${c.body ? `<div class="rc-body">${c.body}</div>` : ''}${form}<div class="rc-acts">${c.acts}</div></div>`;
}
function secHead(m, sec, all, shown) {   // heading of a section of the check tab
  const open = all.filter(it => !itemDecided(it)).length;
  if (sec === 'l3' || sec === 'l2' || sec === 'l1') { const lv = +sec[1]; return `<h3 class="sec gsec lvh">${lvDot(lv)}${lvName(lv)}<span class="cnt" title="${t('sec_cnt_t')}">${fmt(open)} / ${fmt(all.length)}</span></h3>`; }
  if (sec === 'hint') return `<h3 class="sec gsec lvh">${lvDot(0)}${lvName(0)}<span class="cnt">${fmt(all.length)}</span><span class="link" data-act="hints" title="${t('hints_t')}">${RVU.hints ? t('hints_less') : esc(t('hints_more', fmt(all.length)))}</span></h3>`;
  if (sec === 'done') return '';
  return `<h3 class="sec gsec">${t('g_' + sec)}<span class="cnt">${sec === 'ent' ? '' : fmt(all.length)}</span></h3>`;
}
function rvRenderCheck(body) {
  const m = entryModel(S.e); const items = visibleItems(m); RVU.items = items; const keep = body.dataset.e === String(S.e) && body.dataset.tab === 'check' ? body.scrollTop : 0;
  RVU.card = clamp(RVU.card, 0, items.length - 1);
  const chk = m.rv.chk || ''; const nFl = m.obs.filter(o => flagged(o.rec)).length;
  let s = `<div class="chead"><span>${chk ? esc(t('chk_by', [chk.includes('g') ? srcName('g') : '', chk.includes('s') ? srcName('s') : ''].filter(Boolean).join(' + '))) : `<span class="vd vd-off">${t('chk_none')}</span>`}</span>
    <span class="muted">${esc(t('chk_counts', fmt(m.obs.length), fmt(nFl)))}</span><span class="sp"></span><button class="btn" data-act="addrec">${t('a_add_rec')}</button></div>`;
  if (RVU.form && RVU.form.key === 'new') s += `<div class="rcard t-miss focus"><div class="rc-head"><span class="rc-kind k-miss">${t('c_new')}</span></div>${formHtml(m, { type: 'miss', key: 'new', x: { kind: 'observation', src: 'h' } })}</div>`;
  if (RVU.form && RVU.form.kind === 'rec' && !items.some(it => it.key === RVU.form.key)) {   // a record without a card (edited from the table)
    const o = m.obs.find(x => x.key === RVU.form.key);
    if (o) { const it = { type: 'rec', group: 'rec', key: o.key, o, lv: 0, mk: '' }; s += `<div class="rcard t-rec focus"><div class="rc-head">${recCard(m, it).head}</div>${formHtml(m, it)}</div>`; }
  }
  const hiddenOut = outCount(m);
  if (hiddenOut) s += `<p class="gnote corpnote">${esc(t(RVU.showOut ? 'out_cards_shown' : 'out_cards', fmt(hiddenOut), corpusName(RVU.corpus)))} <span class="link" data-act="showout">${t(RVU.showOut ? 'out_hide_s' : 'out_show_s')}</span></p>`;
  if (!m.items.some(it => it.lv >= 1)) s += `<p class="muted gnote">${t('no_flags')}</p>`;
  for (const sec of SEC_ORDER) {   // schwer, mittel, leicht first; hints collapsed; then own changes, entry header, images, finish
    const all = m.items.filter(it => it.sec === sec && !(it.type === 'rec' && corpusOn() && !RVU.showOut && !inCorpus(it.o.n))); if (!all.length) continue;
    s += secHead(m, sec, all);
    for (const it of all) { const i = items.indexOf(it); if (i >= 0) s += cardHtml(m, it, i); }
  }
  body.innerHTML = s; body.dataset.e = String(S.e); body.dataset.tab = 'check'; body.scrollTop = keep;
  const f = $('.rform', body); if (f && RVU.form && !RVU.form.shown) { RVU.form.shown = true; wireForm(f); }
  if (RVU.enter) { RVU.enter = false; focusCard(RVU.card, false); }
}

// ------------------------------------------------------------------ focus and selection
function markSel(key) { S.sel = key; if (SUB) for (const [k, el] of SUB.nodeEls) el.classList.toggle('sel', k === key); propsSelSync(); $$('#rtable tr.on').forEach(r => r.classList.remove('on')); if (key && key[0] === 'n') { const r = $(`#rtable tr[data-o="${key.slice(1)}"]`); if (r) r.classList.add('on'); } }
function itemNodeKey(m, it) {
  if (it.type === 'rec') return 'n' + it.o.n; if (it.type === 'ent') return 'n' + m.e;
  if (it.type === 'name') { const n = [...it.x.nodes][0]; return n !== undefined ? 'n' + n : (SUB && [...SUB.V.values()].find(v => v.item === it.key) || {}).key || null; }
  if (it.type === 'miss' || it.type === 'qa') return (SUB && [...SUB.V.values()].find(v => v.item === it.key) || {}).key || null;
  if (it.type === 'media') { const n = regionNode(it.x[0]); return n >= 0 ? 'n' + n : null; }
  return null;
}
function focusCard(i, scroll) {
  const items = RVU.items || []; if (!items.length) return; RVU.card = clamp(i, 0, items.length - 1); RVU.armed = false;
  const body = $('#pbody'); $$('.rcard.focus', body).forEach(c => c.classList.remove('focus'));
  const el = $(`.rcard[data-ci="${RVU.card}"]`, body); if (el) { el.classList.add('focus'); if (scroll !== false) el.scrollIntoView({ block: 'nearest' }); }
  const it = items[RVU.card]; const m = EM; const key = itemNodeKey(m, it);
  if (key && SUB && !SUB.V.has(key)) revealNode(key);
  markSel(key); if (key) rvReveal(key);
  if (it.type === 'media') scanHighlightMedia(it.x); else scanHighlight(it.type === 'rec' ? it.o : null);
}
function rvReveal(key) {   // bring a node into view: vertical pan only, unless it is cut off horizontally
  if (!SUB) return; const v = SUB.V.get(key); if (!v) return; const c = $('#gcanvas'); const W = c.clientWidth, H = c.clientHeight; if (!W || !H) return;
  const y0 = Z.y + v.y * Z.k, y1 = Z.y + (v.y + v.h) * Z.k, x0 = Z.x + v.x * Z.k, x1 = Z.x + (v.x + v.w) * Z.k;
  if (y0 < 34 || y1 > H - 12) Z.y += H / 2 - (y0 + y1) / 2;
  if (x1 < 60) Z.x += 60 - x0; else if (x0 > W - 60) Z.x -= x1 - (W - 20);
  applyZ();
}
function cardIndexFor(key) {   // the card that belongs to a graph node / ghost
  const m = EM; if (!m || !key) return -1; let it = null;
  if (key[0] === 'n') { const n = +key.slice(1); if (n === m.e) it = m.items.find(x => x.type === 'ent'); else if (kindOf(n) === 'mmregion') { const u = regionUid(n); it = m.items.find(x => x.type === 'media' && x.x[0] === u); } else it = m.items.find(x => (x.type === 'rec' && x.o.n === n) || (x.type === 'name' && x.x.nodes.has(n) && x.kind !== 'same')); }
  else { const v = SUB && SUB.V.get(key); if (v && v.item) it = m.items.find(x => x.key === v.item); }
  if (!it) return -1;
  if (it.sec === 'hint') RVU.hints = true;   // a click on a node opens its card even when it is among the collapsed hints
  if (it.type === 'rec' && corpusOn() && !inCorpus(it.o.n)) RVU.showOut = true;
  return visibleItems(m).indexOf(it);
}
function rvOnSelect(key) {
  if (!EM) return; const ci = cardIndexFor(key); if (ci >= 0) RVU.card = ci;
  $$('#rtable tr.on').forEach(r => r.classList.remove('on'));
  if (key && key[0] === 'n') { const n = +key.slice(1); const r = $(`#rtable tr[data-o="${n}"]`); if (r) r.classList.add('on'); scanHighlight(EM.byNode.get(n) || null); }
  else scanHighlight(null);
}
function rvNodeClick(v, ev) {
  if (ev && ev.target.classList && ev.target.classList.contains('pmore')) {   // expand / collapse the long values of a node
    if (S.propOpen.has(v.key)) S.propOpen.delete(v.key); else S.propOpen.add(v.key); renderGraph(true); return;
  }
  const ci = cardIndexFor(v.key);
  selectKey(v.key, { tab: ci >= 0 ? 'check' : v.kind === 'entry' ? 'text' : 'node' });
  if (ci >= 0) { const el = $(`.rcard[data-ci="${RVU.card}"]`); if (el) el.scrollIntoView({ block: 'nearest' }); }
}
function advance() {   // after a decision: the next undecided card (the final button when none is left)
  const items = RVU.items || []; let i = RVU.card + 1;
  while (i < items.length - 1 && (itemDecided(items[i]) || items[i].type === 'media')) i++;
  focusCard(Math.min(i, items.length - 1));
}

// ------------------------------------------------------------------ actions
function refOf(m, extra) { return Object.assign({ uid: m.uid, id: m.id }, extra || {}); }
function recRef(m, o) { const a = (o.rec.auto || []).find(x => x[0] === 'value'); return refOf(m, Object.assign({ w: o.written, idx: o.idx, occ: o.occ }, a ? { was: a[1] } : {})); }
function oldVals(o, vals) { const cur = recVals(o.n); const old = {}; for (const k in vals) old[k] = cur[k] || ''; return old; }
function decideRec(m, o, d, vals, lab) {
  const v = { d, ref: recRef(m, o), m: machineOf(o) }; if (vals && Object.keys(vals).length) { v.vals = vals; v.old = oldVals(o, vals); }
  decide(o.key, v, lab);
}
function actRec(m, it, a) {
  const o = it.o; const mp = mergedProposal(o); const auto = o.rec.auto || [];
  if (a === 'j') {
    if (mp && mp.drop) return decideRec(m, o, 'x', null, 'drop'), true;
    if (mp && Object.keys(mp.bad).length) { openForm(it.key, 'rec', { fromJ: true }); toast(t('j_bad_toast'), 3500); return false; }
    if (mp && Object.keys(mp.vals).length) return decideRec(m, o, 'a', mp.vals, 'apply'), true;
    if (auto.length) return decideRec(m, o, 'ok', null, 'confirm'), true;
    return false;
  }
  if (a === 'n') return decideRec(m, o, auto.length && !['g', 's'].some(c => proposal(o, c)) ? 'revert' : 'ok', null, 'ok'), true;
  if (a === 'r') return decideRec(m, o, 'revert', null, 'revert'), true;
  if (a === 'x') return decideRec(m, o, 'x', null, 'drop'), true;
  if (a === 'u') return decideRec(m, o, 'u', null, 'unsure'), true;
  if (a === 'e') { openForm(it.key, 'rec'); return false; }
  return false;
}
function nameDecision(it, d) {   // the machine rows and both links travel with the decision (export without the layer)
  const x = it.x; const node = [...x.nodes][0];
  const unc = node !== undefined && x.section === 'places' ? prefDe(node, 'dwc:coordinateUncertaintyInMeters') : null;
  return { d, ref: { section: x.section, form: x.form, nk: x.key }, kind: x.kind, rows: (x.info.rows || []).map(r => Object.assign({}, r)), before: x.info.before || null, now: x.info.now || null, unc: unc || '', n: mentionCount(x.section, x.form, x.nodes) };
}
function cardAct(a) {
  const m = EM; const items = RVU.items || []; const it = items[RVU.card]; if (!m || !it) return;
  let moved = false;
  if (a === 'reset') {
    // the entry key holds the header decisions AND the checked mark: reset one, keep the other
    const ed = entryDec(m.uid);
    if (it.type === 'done') { const d = Object.assign({}, ed); delete d.checked; decide('entry:' + m.uid, d.date || d.kind || d.place || d.hdr ? d : null, 'uncheck'); }
    else if (it.type === 'ent') decide(it.key, ed.checked ? { ref: ed.ref, checked: ed.checked } : null, 'reset');
    else decide(it.key, null, 'reset');
    return;
  }
  if (it.type === 'rec') moved = actRec(m, it, a);
  else if (it.type === 'miss') {
    if (a === 'j' && it.x.kind === 'observation') openForm(it.key, 'add');
    else if (a === 'n') { decide(it.key, { d: 'no', ref: refOf(m, { text: it.x.text || '' }), m: { src: it.x.src, c: it.x.c, de: it.x.de, kind: it.x.kind } }, 'no'); moved = true; }
  } else if (it.type === 'name') {
    if (a === 'j') { decide(it.key, nameDecision(it, it.x.kind === 'suggest' ? 'apply' : 'confirm'), 'confirm'); moved = true; }
    else if (a === 'n') { decide(it.key, nameDecision(it, it.x.kind === 'suggest' ? 'reject' : it.x.kind === 'confirmed' ? 'wrong' : 'revert'), 'revert'); moved = true; }
  } else if (it.type === 'tc') {
    const c = it.c; const base = () => ({ ref: refOf(m, { old: c[0], new: c[1] }), m: { applied: c[2], kind: c[4], rel: c[5], s: c[6], g: c[7] || ((m.rv.chk || '').includes('g') ? 'none' : ''), better: c[8] } });
    if (a === 'j') { decide(it.key, Object.assign(base(), { d: 'accept', final: c[1] }), 'accept'); moved = true; }
    else if (a === 'n') { decide(it.key, Object.assign(base(), { d: 'reject', final: c[0] }), 'reject'); moved = true; }
    else if (a === 'e') openForm(it.key, 'tc');
  } else if (it.type === 'ent') {
    const p = entProposal(m); const cur = entCur(m);
    const setEnt = (parts, lab) => { const d = Object.assign({}, RV.dec[it.key] || {}, parts, { ref: refOf(m), m: m.rv.ent || {} }); decide(it.key, d, lab); };
    if (a === 'j' && Object.keys(p.vals).length) { const parts = {}; for (const f in p.vals) parts[f] = { v: p.vals[f], old: f === 'place' ? (cur.place || cur.header) : cur[f], src: p.from[f] }; setEnt(parts, 'apply'); moved = true; }
    else if (a === 'n') { setEnt({ hdr: 'ok' }, 'ok'); moved = true; }
    else if (a === 'e') openForm(it.key, 'ent');
  } else if (it.type === 'qa') {
    const q = it.q; const v = d => ({ d, ref: refOf(m, { reason: q[0], value: q[2] || '' }), m: { action: q[1], detail: q[3] } });
    if (a === 'j') { decide(it.key, v('confirm'), 'confirm'); moved = true; }
    else if (a === 'n') { decide(it.key, v('false_alarm'), 'false_alarm'); moved = true; }
  } else if (it.type === 'media') { if (a === 'j') openForm('new', 'add'); else if (a === 'big') openCrop(it.x[0]); }
  else if (it.type === 'done' && a === 'done') markChecked(m);
  if (moved) advance();
}
function markChecked(m) {
  const open = openFindings(m);
  if (open && !RVU.armed) { RVU.armed = true; renderPanel(); return; }
  RVU.armed = false;
  const impl = m.obs.filter(o => !isDecided(o.key)).map(o => [o.idx, o.written, (o.rec.g || {}).v || '', (o.rec.s || {}).v || '']);
  const d = Object.assign({}, entryDec(m.uid), { ref: refOf(m), checked: { t: nowIso(), by: RV.who || '', queue: RVU.queue, n: m.obs.length, impl } });
  decide('entry:' + m.uid, d, 'checked'); toast(t('checked_toast'));
}

// ------------------------------------------------------------------ forms (inline in the card)
function openForm(key, kind, opts) { RVU.form = Object.assign({ key, kind }, opts || {}); if (S.tab !== 'check') S.tab = 'check'; renderPanel(); }
function cancelForm() { RVU.form = null; renderPanel(); }
const inp = (name, val, ph, cls) => `<input type="text" name="${name}" value="${esc(val == null ? '' : val)}" placeholder="${esc(ph || '')}" autocomplete="off" spellcheck="false" class="${cls || ''}">`;
const sel = (name, val, voc, pred, clear) => `<select name="${name}">${(clear ? [''] : []).concat(voc).map(v => `<option value="${v}"${v === (val || '') ? ' selected' : ''}>${v ? esc(cv(pred, v)) : '—'}</option>`).join('')}</select>`;
function taxonPick(sp) {
  return `<div class="tpick"><div class="frow">${inp('species_de', sp.de, t('ph_species'))}${inp('species_sci', sp.sci, t('ph_sci'))}${inp('species_key', sp.key, 'GBIF')}<button type="button" class="btn" data-act="gbif">${t('gbif_search')}</button></div><div class="tres"></div></div>`;
}
function formHtml(m, it) {
  const F = RVU.form; let s = '';
  if (F.kind === 'rec') {
    const o = it.o; const cur = recVals(o.n); const d = RV.dec[it.key]; const mp = F.fromJ ? mergedProposal(o) : null;
    const v = Object.assign({}, cur, d && d.vals ? d.vals : {}, mp ? mp.vals : {}); const bad = mp ? mp.bad : {};
    const sp = typeof v.species === 'object' ? v.species : { de: v.species, sci: prefDe(node1(o.n, 'lkg:observedTaxon'), 'dwc:scientificName') || '', key: '' };
    const val = f => (f in bad ? bad[f] : CLEAR.has(v[f]) ? '' : v[f]);
    s = `<label class="wide">${t('f_species')}${taxonPick(sp)}</label>
      <label>${t('f_count')}${inp('count', val('count'), '', bad.count ? 'bad' : '')}<small>${t('hint_count')}</small></label>
      <label>${t('f_date')}${inp('date', val('date'), 'JJJJ-MM-TT', bad.date ? 'bad' : '')}<small>${t('hint_date')}</small></label>
      <label class="wide">${t('f_locality')}${inp('locality', val('locality'))}</label>
      <label>${t('f_observer')}${inp('observer', val('observer'))}<small>${t('hint_observer')}</small></label>
      <label>${t('f_co_observers')}${inp('co_observers', val('co_observers'))}<small>${t('hint_co')}</small></label>
      <label>${t('f_record_type')}${sel('record_type', v.record_type, RECORD_TYPES, 'lkg:recordType', !cur.record_type)}</label>
      <label>${t('f_status')}${sel('status', v.status, STATUSES, 'dwc:occurrenceStatus', !cur.status)}</label>
      <label>${t('f_sex')}${sel('sex', val('sex'), SEXES, 'dwc:sex', true)}</label>
      <label>${t('f_life_stage')}${sel('life_stage', val('life_stage'), LIFE_STAGES, 'dwc:lifeStage', true)}</label>
      <label>${t('f_breeding')}${sel('breeding', val('breeding'), BREEDING, 'lkg:breedingEvidence', true)}</label>`;
  } else if (F.kind === 'add') {
    const x = it.x || {}; const d = RV.dec[it.key]; const r = (d && d.rec) || {}; const tx = x.de ? findTaxon(x.de, x.sci) : null;
    const sp = { de: r.species_de || x.de || '', sci: r.scientific_name || x.sci || (tx ? tx.sci : ''), key: r.gbif_key || (tx ? tx.key : '') };
    const cnt = r.count != null ? r.count : x.count ? (cleanCount(x.count) || x.count) : '';
    s = `<label class="wide">${t('f_species')} *${taxonPick(sp)}</label>
      <label>${t('f_count')}${inp('count', cnt, '', cnt && !validCount(cnt) ? 'bad' : '')}<small>${t('hint_count')}</small></label>
      <label>${t('f_date')}${inp('date', r.date != null ? r.date : x.date || '', 'JJJJ-MM-TT', x.date && !RE_DATE.test(x.date) && r.date == null ? 'bad' : '')}<small>${t('hint_date_add')}</small></label>
      <label class="wide">${t('f_locality')}${inp('locality', r.locality != null ? r.locality : x.loc || '')}</label>
      <label>${t('f_observer')}${inp('observer', r.observer != null ? r.observer : x.obs || '')}<small>${t('hint_observer_add')}</small></label>
      <label>${t('f_record_type')}${sel('record_type', r.record_type || '', RECORD_TYPES, 'lkg:recordType', true)}</label>
      <label class="wide">${t('f_text')}<textarea name="text" rows="2" spellcheck="false">${esc(r.text != null ? r.text : x.text || '')}</textarea><small>${t('hint_text')}</small></label>`;
  } else if (F.kind === 'tc') {
    const c = it.c; const d = RV.dec[it.key];
    s = `<label class="wide">${t('f_reading')}<textarea name="final" rows="2" spellcheck="false">${esc(d && d.d === 'edit' ? d.final : c[8] || c[1])}</textarea><small>${t('hint_reading')}</small></label>`;
  } else if (F.kind === 'ent') {
    const d = RV.dec[it.key] || {}; const cur = entCur(m); const p = entProposal(m);
    const v = f => (d[f] ? d[f].v : p.vals[f] != null ? p.vals[f] : f === 'place' ? cur.place || cur.header : cur[f]);
    s = `<label>${t('date')}${inp('date', v('date'), 'JJJJ-MM-TT')}<small>${t('hint_date_add')}</small></label>
      <label>${t('kind')}<select name="kind">${ENTRY_KINDS.map(k => `<option value="${k}"${k === v('kind') ? ' selected' : ''}>${esc(cv('lkg:entryKind', k))}</option>`).join('')}</select></label>
      <label class="wide">${t('place')}${inp('place', v('place'))}<small>${t('hint_place')}</small></label>`;
  } else if (F.kind === 'txt') {
    s = `<label class="wide">${t('txt_old')}<div class="oldtext">${markup(F.old)}</div></label><label class="wide">${t('txt_new')}<textarea name="new" rows="2" spellcheck="false">${esc(F.old)}</textarea><small>${t('hint_txt')}</small></label>`;
  }
  return `<form class="rform" data-kind="${F.kind}" data-key="${esc(it.key)}">${s}<div class="frow fbtn"><button type="submit" class="abtn primary">${kbd('⏎')} ${t('save')}</button><button type="button" class="abtn" data-act="cancel">${kbd('Esc')} ${t('cancel')}</button><span class="ferr"></span></div></form>`;
}
function wireForm(f) {
  const first = f.querySelector(f.dataset.kind === 'add' || f.dataset.kind === 'rec' ? (RVU.form.fromJ ? 'input.bad' : 'input[name="species_de"]') : 'textarea, input') || f.querySelector('input');
  if (first) { first.focus(); if (first.select && f.dataset.kind !== 'rec') first.select(); }
  f.scrollIntoView({ block: 'nearest' });
  f.addEventListener('submit', ev => { ev.preventDefault(); submitForm(f); });
  f.addEventListener('keydown', ev => { if (ev.key === 'Enter' && ev.target.tagName === 'TEXTAREA' && !ev.shiftKey) { ev.preventDefault(); submitForm(f); } });
  const de = f.querySelector('input[name="species_de"]');
  if (de) {
    const res = f.querySelector('.tres');
    const show = list => { res.innerHTML = list.map((x, i) => `<div class="r" data-i="${i}"><b>${esc(x.label)}</b> <i>${esc(x.sci)}</i><span class="sub">${x.key ? 'GBIF ' + esc(x.key) : ''} · ${esc(x.src || t('o_graph'))}</span></div>`).join(''); res._list = list; };
    const local = q => { q = cf(q.trim()); if (q.length < 2) return []; const L = taxaIndex(); const a = L.filter(x => cf(x.label).startsWith(q)); const b = L.filter(x => !a.includes(x) && (cf(x.label).includes(q) || cf(x.sci).includes(q) || x.alt.some(y => cf(y).includes(q)))); return a.concat(b).slice(0, 7); };
    de.addEventListener('input', () => { f.elements.species_key.value = ''; f.elements.species_sci.value = ''; show(local(de.value)); });
    res.addEventListener('click', ev => { const r = ev.target.closest('.r'); if (!r) return; const x = res._list[+r.dataset.i]; de.value = x.label; f.elements.species_sci.value = x.sci || ''; f.elements.species_key.value = x.key || ''; res.innerHTML = ''; });
    f.querySelector('[data-act="gbif"]').addEventListener('click', async () => {
      const q = de.value.trim() || f.elements.species_sci.value.trim(); if (!q) return; res.innerHTML = `<div class="r muted">GBIF …</div>`;
      try {
        const r = await fetch('https://api.gbif.org/v1/species/search?q=' + encodeURIComponent(q) + '&datasetKey=d7dddbf4-2cf0-4f39-9b2a-bb099caae36c&status=ACCEPTED&limit=10&class=Aves');
        const j = await r.json(); const list = (j.results || []).map(x => ({ label: ((x.vernacularNames || []).find(v => v.language === 'deu') || {}).vernacularName || x.canonicalName, sci: x.canonicalName, key: String(x.key), src: 'GBIF' }));
        if (list.length) show(list); else { show(local(q)); toast(t('gbif_none')); }
      } catch (e) { show(local(q)); toast(t('gbif_down')); }
    });
  }
}
function submitForm(f) {
  const m = EM; const F = RVU.form; const key = f.dataset.key; const val = n => (f.elements[n] ? String(f.elements[n].value).trim() : '');
  const it = m.items.find(x => x.key === key) || (F.kind === 'rec' ? { o: m.obs.find(o => o.key === key) } : null);
  const fail = (name, msg) => { const el = f.elements[name]; if (el) { el.classList.add('bad'); el.focus(); } f.querySelector('.ferr').textContent = msg; return false; };
  $$('.bad', f).forEach(el => el.classList.remove('bad'));
  if (F.kind === 'rec') {
    const o = it.o; const cur = recVals(o.n); const vals = {};
    const de = val('species_de'); if (!de) return fail('species_de', t('err_species'));
    if (cf(de) !== cf(cur.species)) vals.species = { de, sci: val('species_sci'), key: val('species_key').replace(/\D/g, '') };
    for (const k of REC_FIELDS.slice(1)) {
      let v = val(k); const c = cur[k] || '';
      if (v === c) continue;
      if (!v) { if (k === 'record_type' || k === 'status') continue; v = '-'; }
      const ok = fieldCheck(k, v); if (ok == null) return fail(k, t('err_format', fieldLabel(k)));
      vals[k] = ok;
    }
    if (!Object.keys(vals).length) { RVU.form = null; toast(t('no_change')); renderPanel(); return; }
    const mp = mergedProposal(o); const same = mp && !mp.drop && JSON.stringify(vals) === JSON.stringify(Object.assign({}, mp.vals));
    RVU.form = null; decideRec(m, o, same ? 'a' : 'e', vals, 'edit'); advance(); return;
  }
  if (F.kind === 'add') {
    const de = val('species_de'); if (!de) return fail('species_de', t('err_species'));
    const count = val('count'); if (count && !validCount(count)) return fail('count', t('err_format', fieldLabel('count')));
    const date = val('date'); if (date && !RE_DATE.test(date)) return fail('date', t('err_format', fieldLabel('date')));
    const text = val('text'); const x = (it && it.x) || { src: 'h' };
    const rec = { species_de: de, scientific_name: val('species_sci'), gbif_key: val('species_key').replace(/\D/g, ''), count, locality: val('locality'), date: date.replace(/\s*\/\s*/, '/'), observer: val('observer'), record_type: val('record_type'), text };
    const k = key === 'new' ? 'miss:' + m.uid + '|' + (text || de) : key;
    RVU.form = null; decide(k, { d: 'add', ref: refOf(m, { text: key === 'new' ? (text || de) : x.text || '' }), rec, m: { src: x.src || 'h', c: x.c, de: x.de, kind: x.kind || 'observation' } }, 'add');
    if (key === 'new') { const i = visibleItems(m).findIndex(z => z.key === k); if (i >= 0) focusCard(i); } else advance();
    return;
  }
  if (F.kind === 'tc') {
    const c = it.c; const fin = f.elements.final.value; if (!fin.trim()) return fail('final', t('err_empty'));
    RVU.form = null; decide(key, { d: fin === c[1] ? 'accept' : fin === c[0] ? 'reject' : 'edit', final: fin, ref: refOf(m, { old: c[0], new: c[1] }), m: { applied: c[2], kind: c[4], rel: c[5], s: c[6], g: c[7] || ((m.rv.chk || '').includes('g') ? 'none' : ''), better: c[8] } }, 'edit'); advance(); return;
  }
  if (F.kind === 'ent') {
    const cur = entCur(m); const parts = {}; const p = entProposal(m); const d0 = Object.assign({}, RV.dec[key] || {});
    const date = val('date'); if (date !== cur.date) { const ok = fieldCheck('entry_date', date); if (!ok) return fail('date', t('err_format', t('date'))); parts.date = { v: ok, old: cur.date, src: p.vals.date === ok ? p.from.date : '' }; } else delete d0.date;
    const kind = val('kind'); if (kind !== cur.kind) parts.kind = { v: kind, old: cur.kind, src: p.vals.kind === kind ? p.from.kind : '' }; else delete d0.kind;
    const place = val('place'); const cp = cur.place || cur.header; if (place && place !== cp) parts.place = { v: place, old: cp, src: p.vals.place === place ? p.from.place : '' }; else delete d0.place;
    RVU.form = null; decide(key, Object.assign(d0, parts, Object.keys(parts).length ? {} : { hdr: 'ok' }, { ref: refOf(m), m: m.rv.ent || {} }), 'edit'); advance(); return;
  }
  if (F.kind === 'txt') {
    const nw = f.elements.new.value; if (!nw.trim() || nw === F.old) return fail('new', t('err_same'));
    RVU.form = null; decide('txt:' + m.uid + '|' + F.old, { d: 'text', ref: refOf(m, { old: F.old }), new: nw }, 'text'); return;
  }
}

// ------------------------------------------------------------------ clicks and keys
function rvPanelClick(ev) {
  const card = ev.target.closest('.rcard'); const act = ev.target.closest('[data-act]');
  if (ev.target.closest('.rform') && (!act || act.dataset.act === 'gbif')) return;
  if (act && act.dataset.act === 'addrec') { openForm('new', 'add'); return; }
  if (act && act.dataset.act === 'hints') { RVU.hints = !RVU.hints; renderPanel(); return; }
  if (act && act.dataset.act === 'showout') { rvHeadAct('showout'); return; }
  if (act && act.dataset.act === 'cancel') { cancelForm(); return; }
  if (act && act.dataset.act === 'txtedit') { textEditStart(); return; }
  if (act && act.dataset.act === 'txtdel') { decide(act.dataset.key, null, 'reset'); return; }
  const tcm = ev.target.closest('[data-tc]');
  if (tcm && S.tab === 'text') { const i = +tcm.dataset.tc; const m = EM; const it = m.items.find(x => x.type === 'tc' && x.i === i); if (it) { if (it.sec === 'hint') RVU.hints = true; S.tab = 'check'; RVU.card = Math.max(0, visibleItems(m).indexOf(it)); renderPanel(); focusCard(RVU.card); } return; }
  const mk = ev.target.closest('[data-obs]');
  if (mk && S.tab === 'text') { const key = 'n' + mk.dataset.obs; if (SUB && !SUB.V.has(key)) revealNode(key); selectKey(key, { center: true }); return; }
  if (card && card.dataset.ci != null) {
    const i = +card.dataset.ci; if (i !== RVU.card) focusCard(i, false);
    if (act && !act.disabled) { cardAct(act.dataset.act); }
  }
}
function moveCard(d) { const items = RVU.items || []; if (!items.length) return; focusCard(clamp(RVU.card + d, 0, items.length - 1)); }
function rvKey(ev) {
  if (!$('#lightbox').hidden) { if (ev.key === 'Escape') closeCrop(); else if (ev.key === '+' || ev.key === '-') { const v = $('#lightbox .lb-view'); lbZoom(v.clientWidth / 2, v.clientHeight / 2, ev.key === '+' ? 1.4 : 1 / 1.4); } return true; }
  if (!$('#modalbg').hidden) { if (ev.key === 'Escape') { closeModal(); return true; } return true; }
  const inField = ev.target && ev.target.closest && ev.target.closest('input,select,textarea');
  if (inField) {
    if (ev.key === 'Escape') { if (ev.target.closest('.rform')) { cancelForm(); return true; } if (ev.target.closest('#rtable')) { rvRenderTable(); return true; } if (ev.target.id === 'who') { ev.target.blur(); return true; } }
    return false;
  }
  if (ev.ctrlKey || ev.metaKey || ev.altKey || S.view !== 'entry') return false;
  const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;
  if (k === 'ArrowLeft' || k === 'ArrowRight') { ev.preventDefault(); stepEntry(k === 'ArrowLeft' ? -1 : 1); return true; }
  if (k === 'z') { ev.preventDefault(); undo(); return true; }
  if (k === 's') { ev.preventDefault(); scanToggle(); return true; }
  if (k === 'g') { ev.preventDefault(); rvHeadAct('mid'); return true; }
  if (k === 'Escape' && RVU.form) { cancelForm(); return true; }
  if (S.tab !== 'check') return false;
  if (k === 'ArrowUp' || k === 'ArrowDown') { ev.preventDefault(); moveCard(k === 'ArrowUp' ? -1 : 1); return true; }
  if ('jnexu'.includes(k) && k.length === 1) { ev.preventDefault(); cardAct(k); return true; }
  if (k === 'Enter') { const it = (RVU.items || [])[RVU.card]; if (it && it.type === 'done' && !entryDec(EM.uid).checked) { ev.preventDefault(); cardAct('done'); return true; } }
  return false;
}
