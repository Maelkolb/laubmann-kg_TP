// ---------------------------------------------------------------- view state (not persisted)
const CFG = (() => { try { return JSON.parse($('#cfg').textContent || '{}'); } catch (e) { return {}; } })();
const LIST_STEP = 150;
const SHOW = {};
let panelForm = null;          // written name whose "other entry" search is open
let searchRes = null;          // live search results shown instead of the stored candidates
let gradePick = null;          // grade chosen for the next decision on this card
let curMen = -1;
const view = { cands: [] };    // what the digits 1-9 choose from

// ---------------------------------------------------------------- header
function renderHeader() {
  $('#brand').textContent = t('app.title');
  document.title = t('app.title');
  document.documentElement.lang = LANG;
  const tabs = ['home'].concat(TYPES).map(ty => {
    let c = '';
    if (ty !== 'home') { const p = typeProgress(ty); c = '<span class="c" title="' + esc(t('list.progress', p.pct.toLocaleString(loc()))) + '">' + p.pct.toLocaleString(loc()) + ' %</span>'; }
    return '<button class="ttab' + (cur.type === ty ? ' on' : '') + '" data-type="' + ty + '">' + esc(t('type.' + ty)) + c + '</button>';
  });
  $('#types').innerHTML = tabs.join('');
  $('#btnUndo').title = t('hd.undo'); $('#btnImport').textContent = t('hd.import'); $('#btnExport').textContent = t('hd.export');
  $('#btnHelp').title = t('hd.help'); $('#btnTheme').title = t('hd.theme'); $('#btnLang').textContent = LANG === 'en' ? 'DE' : 'EN'; $('#btnLang').title = t('hd.lang');
  $('#scanzoom').textContent = t('scan.zoom'); $('#scanclose').title = t('scan.hide'); $('#scanopen').title = t('scan.open');
  renderCorpusSel();
  savedLabel();
}
// corpus selector and the banner of an active filter
function renderCorpusSel() {
  const sel = $('#corpsel'), bar = $('#corpbar'); if (!sel || !bar) return;
  if (!D.corpus) { sel.style.display = 'none'; bar.hidden = true; return; }
  const c = corpus();
  sel.innerHTML = [0, 1, 2, 3].map(k => '<option value="' + k + '"' + (k === c ? ' selected' : '') + '>' + esc(t('corp.sel', t('corp.s.' + k), fmt(D.corpus.rec[k]))) + '</option>').join('');
  sel.title = t('corp.tip'); sel.classList.toggle('on', c > 0);
  bar.hidden = c === 0;
  bar.innerHTML = c === 0 ? '' : '<span class="trc tr' + c + '">K' + c + '</span><span class="cbt">' + esc(t('corp.active', t('corp.' + c), fmt(D.corpus.rec[c]), fmt(D.corpus.rec[0]))) + '</span><button class="nbtn" data-act="corpus-off">' + esc(t('corp.off')) + '</button>';
}
const tierName = k => t('tier.' + k);
const whyText = code => (has('tw.' + code) ? t('tw.' + code) : code);
function tierWhy(m) {          // why a passage's record is not in the next tier, in words
  if (m.k == null || m.k >= 3) return '';
  const codes = (m.kw || []).map(whyText).join('; ');
  if ((m.kw || []).includes('no-records')) return codes;
  return (m.ke ? t('tier.entry') + ' ' : '') + (m.k === 0 ? t('tier.out_why') : t('tier.next_why', tierName(m.k + 1))) + ' ' + codes;
}
function tierChip(m) {
  if (m.k == null || !D.corpus) return '';
  const why = tierWhy(m);
  return '<span class="trc tr' + m.k + '" title="' + esc(t(m.ke ? 'tier.t.entry' : 'tier.t') + ': ' + tierName(m.k) + (why ? ' — ' + why : '')) + '">K' + m.k + '</span>';
}
const countText = e => (corpus() ? t('card.mentions.c', fmt(cn(e)), fmt(e.n)) : e.n === 1 ? t('card.mention1') : t('card.mentions', fmt(e.n)));

// ---------------------------------------------------------------- list
function searchText(e) {
  if (e._st) return e._st;
  const c = e.cur || {};
  return e._st = fold([e.l, e.forms.map(f => f.f).join(' '), c.sci, c.label, c.name, c.qid, c.gnd, c.code, c.key].filter(Boolean).join(' '));
}
const curQ = ty => S.ui.q[ty] || 'changed';
function listItems(ty) {
  const q = curQ(ty); const sub = q === 'suggest' ? (S.ui.sub[ty] || '') : ''; const find = fold(S.ui.find[ty] || '');
  let items = corpusItems(ty).filter(e => inQueue(ty, e, q));
  if (sub) items = items.filter(e => e.sq === sub);
  if (find) items = items.filter(e => searchText(e).includes(find));
  return items;
}
function queueCounts(ty) {
  const c = {}; for (const q of QUEUES) c[q] = { n: 0, open: 0 };
  const sub = { change: 0, stale: 0, agree: 0, unsure: 0 };
  for (const e of corpusItems(ty)) {
    const done = entDone(ty, e);
    c[e.q].n++; if (!done) c[e.q].open++;
    if (e.mg) { c.merge.n++; if (!mergeDone(ty, e)) c.merge.open++; }
    if (done) c.done.n++;
    if (e.q === 'suggest' && e.sq) sub[e.sq]++;
  }
  return [c, sub];
}
function rowSub(ty, e) {
  const bits = [];
  if (e.gone) bits.push('<span class="bd no">' + esc(t('ck.none.' + ty)) + '</span>');
  else if (e.q === 'changed' && e.ck) bits.push('<span class="bd mach">' + esc(t('ck.' + e.ck)) + '</span>');
  if (e.q === 'suggest' && e.sq && curQ(ty) !== 'merge') bits.push('<span class="bd ' + (e.sq === 'change' ? 'alt' : e.sq === 'agree' ? 'ok' : 'unk') + '">' + esc(t('sq.' + e.sq)) + '</span>');
  if (curQ(ty) === 'merge' && e.mg) bits.push(esc('→ ' + e.mg.map(c => c.to).slice(0, 3).join(' · ') + (e.mg.length > 3 ? ' …' : '')));
  else if (e.cur) bits.push(esc(linkShort(ty, e.cur)));
  else if (!e.gone) bits.push(esc(t('chg.nolink')));
  if (e.nchg) bits.push(esc(t('list.nchg', fmt(e.nchg))));
  return bits.join(' ');
}
function rowHtml(ty, e) {
  return '<div class="qi' + (e.k === cur.key ? ' on' : '') + '" data-key="' + esc(e.k) + '"><span class="dot ' + decClass(ty, e) + '"></span><div><div class="l1">' + esc(e.l) + '</div><div class="l2">' + rowSub(ty, e)
    + '</div></div><div class="num" title="' + esc(corpus() ? t('corp.in', fmt(cn(e)), fmt(e.n)) : t('list.mentions')) + '">' + (corpus() ? '<b>' + fmt(cn(e)) + '</b> / ' + fmt(e.n) : fmt(e.n)) + '</div></div>';
}
function renderList(scroll) {
  const ty = cur.type; const el = $('#queue'); if (ty === 'home') { el.innerHTML = ''; return; }
  const p = typeProgress(ty); const [c, sub] = queueCounts(ty); const q = curQ(ty);
  const chip = k => '<button class="chip' + (q === k ? ' on' : '') + '" data-q="' + k + '" title="' + esc(t('q.' + k + '.tip')) + '">' + esc(t('q.' + k)) + ' <small>' + (k === 'done' ? fmt(c[k].n) : fmt(c[k].open) + '/' + fmt(c[k].n)) + '</small></button>';
  const subs = q === 'suggest' ? '<div class="chips subchips">' + ['change', 'stale', 'agree', 'unsure'].filter(k => sub[k] || k !== 'stale').map(k => '<button class="chip sub' + ((S.ui.sub[ty] || '') === k ? ' on' : '') + '" data-sub="' + k + '">' + esc(t('sq.' + k)) + ' <small>' + fmt(sub[k]) + '</small></button>').join('') + '</div>' : '';
  const items = listItems(ty); const show = SHOW[ty] || LIST_STEP;
  const keep = $('#qsearch') && document.activeElement === $('#qsearch');
  const top = $('#qlist') ? $('#qlist').scrollTop : 0;
  el.innerHTML = '<div class="qhead"><div class="pbar"><i style="width:' + p.pct + '%"></i></div><div class="pnote"><span><b>' + esc(t('list.progress', p.pct.toLocaleString(loc()))) + '</b></span><span>' + esc(t('list.entities', fmt(p.dn), fmt(p.ents))) + '</span></div>'
    + '<div class="chips" id="qchips">' + QUEUES.filter(k => c[k].n || k === 'done' || k === q).map(chip).join('') + '</div>' + subs
    + '<input class="qsearch" id="qsearch" type="search" placeholder="' + esc(t('list.search')) + '" value="' + esc(S.ui.find[ty] || '') + '" autocomplete="off"></div>'
    + '<div class="qlist" id="qlist">' + (items.length ? items.slice(0, show).map(e => rowHtml(ty, e)).join('') + (items.length > show ? '<div class="qmore" data-more="1">' + esc(t('list.more', fmt(Math.min(LIST_STEP, items.length - show)))) + '</div>' : '') : '<div class="qempty">' + esc(t('list.empty')) + '</div>') + '</div>';
  const ql = $('#qlist'); ql.scrollTop = top;
  if (keep) { const s = $('#qsearch'); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
  if (scroll) { const on = $('.qi.on', ql); if (on) on.scrollIntoView({ block: 'nearest' }); }
}

// ---------------------------------------------------------------- authority records
const EXT = {
  gbif: k => 'https://www.gbif.org/species/' + encodeURIComponent(k), wd: q => 'https://www.wikidata.org/wiki/' + encodeURIComponent(q), gnd: g => 'https://d-nb.info/gnd/' + encodeURIComponent(g),
  gn: g => 'https://www.geonames.org/' + encodeURIComponent(g), osm: o => 'https://www.openstreetmap.org/' + o, eunis: c => 'http://eunis.eea.europa.eu/eunishabitats/' + encodeURIComponent(c),
  map: (la, lo) => 'https://www.openstreetmap.org/?mlat=' + la + '&mlon=' + lo + '#map=13/' + la + '/' + lo,
};
const ext = (href, label) => '<a class="ext" href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(label) + ' ↗</a>';
const gradeBadge = g => g ? '<span class="bd grade ' + (g === 'exact' ? 'ok' : g === 'broad' ? 'unk' : 'acc') + '" title="' + esc(t('grade.' + g + '.tip')) + '">' + esc(t('grade') + ': ' + g) + '</span>' : '';
const life = x => (x.born || x.died ? ' <span class="muted">(' + esc((x.born || '?').slice(0, 4)) + '–' + esc((x.died || '').slice(0, 4)) + ')</span>' : '');
function eunisParents(code) { const out = []; let c = EUNIS.get(code); let guard = 0; while (c && c[3] && guard++ < 8) { c = EUNIS.get(c[3]); if (c) out.unshift(c); } return out; }
const FEATURE = { P: { de: 'Ort', en: 'populated place' }, H: { de: 'Gewässer', en: 'water' }, T: { de: 'Berg / Gelände', en: 'mountain / terrain' }, L: { de: 'Gebiet', en: 'area' }, A: { de: 'Verwaltungseinheit', en: 'administrative unit' }, S: { de: 'Bauwerk / Stelle', en: 'spot / building' }, V: { de: 'Wald / Vegetation', en: 'forest / vegetation' }, R: { de: 'Weg / Bahn', en: 'road / railway' } };
function featureText(f) { if (!f) return ''; const m = /^([A-Z])\.([A-Z0-9]+)$/.exec(f); return m && FEATURE[m[1]] ? FEATURE[m[1]][LANG === 'en' ? 'en' : 'de'] + ' (' + f + ')' : f; }
// title + description of one authority record (also used for candidates)
function recParts(ty, x) {
  if (ty === 'taxon') {
    const de = (x.de || []).filter(n => n !== x.sci);
    return { title: (x.label && x.label !== x.sci ? esc(x.label) + ' ' : '') + '<i>' + esc(x.sci || '') + '</i>', desc: [x.rank, x.family ? t('taxon.family') + ' ' + x.family + (x.order ? ' (' + x.order + ')' : '') : ''].filter(Boolean).map(esc).join(' · '),
      more: de.length ? esc(t('taxon.de') + ': ' + de.join(', ')) : '', links: [x.key ? ext(EXT.gbif(x.key), 'GBIF ' + x.key) : '', x.qid ? ext(EXT.wd(x.qid), 'Wikidata ' + x.qid) : ''] };
  }
  if (ty === 'person') {
    return { title: (x.label ? esc(x.label) : '<span data-wdlabel="' + esc(x.qid || '') + '">' + esc(x.qid || (x.gnd ? 'GND ' + x.gnd : '')) + '</span>') + '<span data-wdlife="' + esc(x.label ? '' : x.qid || '') + '">' + life(x) + '</span>',
      desc: '<span data-wddesc="' + esc(x.desc ? '' : x.qid || '') + '">' + esc([x.desc, (x.occ || []).filter(o => !(x.desc || '').includes(o)).join(', ')].filter(Boolean).join(' · ')) + '</span>', more: '',
      links: [x.qid ? ext(EXT.wd(x.qid), 'Wikidata ' + x.qid) : '', x.gnd ? ext(EXT.gnd(x.gnd), 'GND ' + x.gnd) : ''] };
  }
  if (ty === 'place') {
    const parts = (x.name || '').split(',').map(s => s.trim()).filter(Boolean);
    const admin = parts.length > 1 ? parts.slice(1).join(', ') : [x.admin1 ? 'Admin ' + x.admin1 : '', x.country].filter(Boolean).join(', ');
    const co = x.lat != null ? (+x.lat).toFixed(5) + ', ' + (+x.lon).toFixed(5) + (x.unc ? ' ' + t('place.unc', fmt(x.unc)) : '') : '';
    const named = parts[0] || (x.gn ? 'GeoNames ' + x.gn : x.qid || '');
    return { title: esc(named || co), desc: [featureText(x.feature), admin].filter(Boolean).map(esc).join(' · '), more: named ? esc(co) : '',
      links: [x.gn ? ext(EXT.gn(x.gn), 'GeoNames ' + x.gn) : '', x.qid ? ext(EXT.wd(x.qid), 'Wikidata ' + x.qid) : '', x.osm ? ext(EXT.osm(x.osm), 'OSM ' + x.osm) : '', x.lat != null ? ext(EXT.map(x.lat, x.lon), LANG === 'en' ? 'map' : 'Karte') : ''] };
  }
  const par = eunisParents(x.code); const lv = EUNIS.get(x.code);
  return { title: '<span class="mono" style="font-size:15px">' + esc(x.code) + '</span> ' + esc(x.label || (lv ? lv[1] : '')), desc: lv ? esc(t('habitat.level', lv[2])) : '',
    more: par.length ? esc(t('habitat.parents') + ': ') + par.map(p => '<span class="mono">' + esc(p[0]) + '</span> ' + esc(p[1])).join(' › ') : '', links: [ext(EXT.eunis(x.code), 'EUNIS ' + x.code)] };
}
function recHtml(ty, x, grade) {
  const p = recParts(ty, x);
  return '<div class="rec"><div class="rt">' + p.title + '</div>' + (p.desc ? '<div class="rd">' + p.desc + '</div>' : '') + (p.more ? '<div class="rd">' + p.more + '</div>' : '')
    + '<div class="rl">' + p.links.filter(Boolean).join('') + (grade ? gradeBadge(grade) : '') + '</div></div>';
}
const roundLabel = n => { const r = (D.rounds || []).find(x => x.n === n); return r ? r.label : (n ? 'R' + n : ''); };
function srcChips(src) { return (src || []).map(s => '<span class="bd" title="' + esc(has('src.' + s + '.tip') ? t('src.' + s + '.tip') : '') + '">' + esc(has('src.' + s) ? t('src.' + s) : s) + '</span>').join(''); }
const wordText = w => (w ? (has('m.word.' + w) ? t('m.word.' + w) : w) : '');
function ruleText(ty, w) {
  if (!w) return '';
  if (ty === 'taxon') return [w.rule ? (has('rule.' + w.rule) ? t('rule.' + w.rule) : w.rule) : '', w.mt ? 'GBIF ' + w.mt : '', !w.rule && w.status ? (has('rule.status.' + w.status) ? t('rule.status.' + w.status) : w.status) : ''].filter(Boolean).join(' · ');
  if (ty === 'person') return w.rule ? (has('rule.' + w.rule) ? t('rule.' + w.rule) : w.rule) : '';
  if (ty === 'place') return [w.rule ? (has('rule.' + w.rule) ? t('rule.' + w.rule) : w.rule) : '', !w.rule && w.status ? (has('rule.status.' + w.status) ? t('rule.status.' + w.status) : w.status) : '', w.conf ? t('m.conf') + ' ' + w.conf : '', w.note].filter(Boolean).join(' · ');
  return [w.by === 'pipeline' ? t('rule.habitat.llm') : (w.status && has('rule.status.' + w.status) ? t('rule.status.' + w.status) : ''), w.conf ? t('m.conf') + ' ' + w.conf : '', w.note].filter(Boolean).join(' · ');
}
function whoHtml(ty, e) {
  const w = e.who || {}; const m = e.m;
  if (w.by === 'machine') return '<div class="who"><span class="muted">' + esc(t('who.by')) + '</span> <span class="bd mach big">' + esc(t(e.gone ? 'who.removed' : 'who.machine')) + '</span>'
    + (m ? '<span>' + esc([roundLabel(m.r), t('m.conf') + ' ' + dec2(m.c), m.a != null ? (m.a === 1 ? t('m.source1') : t('m.sources', m.a)) : ''].filter(Boolean).join(' · ')) + '</span>' + srcChips(m.s) : '') + '</div>';
  if (w.by === 'pipeline') return '<div class="who"><span class="muted">' + esc(t('who.by')) + '</span> <span class="bd pipe big">' + esc(t('who.pipeline')) + '</span><span>' + esc(ruleText(ty, w)) + '</span></div>';
  if (w.by === 'reviewed') return '<div class="who"><span class="muted">' + esc(t('who.by')) + '</span> <span class="bd ok big">' + esc(t('who.reviewed')) + '</span></div>';
  const r = ruleText(ty, w);
  return r ? '<div class="who"><span class="bd big">' + esc(t('who.none')) + '</span><span>' + esc(r) + '</span></div>' : '';
}
function votesHtml(votes) {
  if (!votes || !votes.length) return '';
  return '<table class="votes">' + votes.map(v => '<tr><td class="s" title="' + esc(has('src.' + v.s + '.tip') ? t('src.' + v.s + '.tip') : '') + '">' + esc(has('src.' + v.s) ? t('src.' + v.s) : v.s) + '</td><td class="v">' + esc(wordText(v.v)) + (v.c != null ? ' <span class="muted">' + dec2(v.c) + '</span>' : '')
    + '</td><td class="w">' + esc([v.x, v.why].filter(Boolean).join(' — ')) + (v.id ? ' <span class="mono muted">' + esc(v.id) + '</span>' : '') + '</td></tr>').join('') + '</table>';
}
function machHtml(ty, e, actions) {
  const m = e.m; if (!m) return '';
  const ap = m.ap && !m.ineff;
  return '<div class="mbox"><div class="mh"><span class="bd ' + (ap ? 'mach' : 'unk') + ' big">' + esc(t(ap ? 'm.applied' : 'm.notapplied')) + '</span><b>' + esc(wordText(m.word)) + '</b><span class="muted">' + esc(roundLabel(m.r)) + '</span>'
    + '<span>' + esc(t('m.conf')) + '<span class="meter"><i style="width:' + Math.round((m.c || 0) * 100) + '%"></i></span>' + dec2(m.c || 0) + '</span>'
    + (m.a != null ? '<span>' + esc(m.a === 1 ? t('m.source1') : t('m.sources', m.a)) + '</span>' : '') + srcChips(m.s) + '</div>'
    + (m.why ? '<div class="reason">' + esc(m.why) + '</div>' : '') + (m.note && m.note !== m.hint ? '<div class="small muted">' + esc(m.note) + '</div>' : '')
    + (m.hint ? '<div class="small"><b>' + esc(t('m.hint')) + ':</b> ' + esc(m.hint) + '</div>' : '')
    + (m.ineff ? '<div class="warn small">' + esc(t('m.ineff')) + '</div>' : '') + (m.split ? '<div class="warn small">' + esc(t('m.split')) + '</div>' : '') + (m.nop ? '<div class="small muted">' + esc(t('m.nop')) + '</div>' : '')
    + (!m.ap ? '<div class="small muted">' + esc(t('m.threshold', dec2(D.thresholds.conf), D.thresholds.agree)) + '</div>' : '')
    + votesHtml(m.votes) + (actions ? '<div class="mact">' + actions + '</div>' : '') + '</div>';
}

// ---------------------------------------------------------------- card sections
const sec = (title, body, extra) => (body ? '<div class="sec"><h3>' + esc(title) + (extra ? ' <small>' + extra + '</small>' : '') + '</h3>' + body + '</div>' : '');
function secGraph(ty, e) {
  let body;
  if (e.gone) body = '<div class="box dash">' + esc(t('graph.gone', t('ck.none.' + ty))) + whoHtml(ty, e) + '</div>';
  else if (e.cur) body = '<div class="box">' + recHtml(ty, e.cur, e.cur.grade) + whoHtml(ty, e) + '</div>';
  else body = '<div class="box dash">' + esc(t('graph.nolink')) + whoHtml(ty, e) + '</div>';
  if (ty === 'place') body += '<div id="map"></div><div class="maplegend" id="maplegend"></div>';
  return sec(t('sec.graph'), body);
}
const beforeHead = e => (e.bsrc === 'A' ? t('chg.beforeA', D.r1_export || '') : e.bsrc ? t('chg.before') : t('chg.unknown'));
function secChange(ty, e) {
  if (e.q !== 'changed') return '';
  const acts = '<button class="btn sm a" data-act="confirm">' + esc(t(e.gone ? 'btn.confirm.gone' : 'btn.confirm')) + ' <kbd>J</kbd></button><button class="btn sm m" data-act="revert">' + esc(t('btn.revert')) + ' <kbd>R</kbd></button>';
  let body = '';
  const chgForms = e.forms.filter(f => f.was);
  if (ty === 'taxon' && e.ck === 'forms') {
    body = '<div class="box"><div>' + esc(t('chg.forms')) + '</div><ul style="margin:6px 0 0;padding-left:18px">' + chgForms.map(f => '<li>' + esc(t('chg.form', f.f, fmt(f.n), f.was.key ? (f.was.label || '') + ' (' + (f.was.sci || 'GBIF ' + f.was.key) + ')' : t('names.unlinked'))) + '</li>').join('') + '</ul></div>';
  } else {
    const b = e.before;
    const left = '<div class="box' + (b ? '' : ' dash') + '"><div class="bh">' + esc(beforeHead(e)) + '</div>' + (b ? recHtml(ty, b, b.grade) : esc(e.bsrc ? t('chg.nolink') : t('chg.unknown')))
      + (e.blabel ? '<div class="small muted" style="margin-top:4px">' + esc(t('chg.asentity', e.blabel)) + '</div>' : '') + '</div>';
    const right = '<div class="box now' + (e.cur ? '' : ' dash') + '"><div class="bh">' + esc(t('chg.after')) + '</div>' + (e.gone ? '<b>' + esc(t('chg.removed')) + '</b> <span class="bd no">' + esc(t('ck.none.' + ty)) + '</span>' : e.cur ? recHtml(ty, e.cur, e.cur.grade) : esc(t('chg.nolink'))) + '</div>';
    body = '<div class="diff2">' + left + '<div class="arrow">→</div>' + right + '</div>';
    if (ty === 'taxon' && chgForms.length > 1) body += '<div class="small muted" style="margin-top:5px">' + chgForms.map(f => esc(t('chg.form', f.f, fmt(f.n), f.was.key ? (f.was.label || '') + ' (' + (f.was.sci || '') + ')' : t('names.unlinked')))).join(' · ') + '</div>';
  }
  return sec(t('sec.change'), body + machHtml(ty, e, acts), '<span class="bd mach">' + esc(t(e.gone ? 'ck.none.' + ty : 'ck.' + e.ck)) + '</span>');
}
const formSuggestions = e => e.forms.filter(f => f.m && !f.m.ap && f.m.diff);
function hasSuggestion(ty, e) { const m = e.m; return !!m && (!m.ap || !!m.ineff) && (!!m.prop || (ty === 'taxon' && formSuggestions(e).length > 0)); }
function secSuggest(ty, e) {
  const m = e.m; if (!m || e.q === 'changed') return '';
  if (e.q !== 'suggest') return sec(t('sec.machine'), machHtml(ty, e));
  const p = m.prop; let body = '';
  const head = t(e.sq === 'change' ? 'sug.would' : e.sq === 'stale' ? 'sug.stale' : e.sq === 'agree' ? 'sug.agree' : 'sug.unsure');
  if (p && e.sq !== 'agree') {
    body += '<div class="box now"><div class="bh">' + esc(t('sug.to')) + '</div>' + (p.none ? '<b>' + esc(t('sug.none', t('one.' + ty))) + '</b>' : p.nolink ? '<b>' + esc(t('sug.nolink')) + '</b>' : recHtml(ty, p, p.match || '')) + '</div>';
  }
  if (ty === 'taxon' && formSuggestions(e).length) body += '<div class="small muted" style="margin-top:5px">' + esc(t('sug.forms')) + '</div>';
  if (e.drift && p && sameLink(ty, p, e.drift.link)) body += '<div class="small muted" style="margin-top:5px">' + esc(t('sug.checked', linkShort(ty, e.drift.link))) + '</div>';
  const acts = (hasSuggestion(ty, e) && e.sq !== 'agree' ? '<button class="btn sm m" data-act="accept">' + esc(t('btn.accept')) + ' <kbd>V</kbd></button>' : '');
  return sec(t('sec.suggest'), '<div class="small" style="margin-bottom:5px"><span class="bd ' + (e.sq === 'change' ? 'alt' : e.sq === 'agree' ? 'ok' : 'unk') + ' big">' + esc(head) + '</span></div>' + body + machHtml(ty, e, acts));
}
function secDrift(ty, e) {
  if (!e.drift || (e.q === 'suggest' && e.m && e.m.prop && sameLink(ty, e.m.prop, e.drift.link))) return '';
  return sec(t('sec.drift'), '<div class="box dash small">' + esc(t('drift', linkShort(ty, e.drift.link))) + '</div>');
}
function candHtml(ty, c, k) {
  const p = recParts(ty, c);
  const o = c.o ? (has('cand.o.' + c.o) ? t('cand.o.' + c.o) : c.o) : '';
  const right = [o ? '<span class="bd ' + (c.o === 'm' ? 'mach' : c.o === 'b' ? 'pipe' : '') + '">' + esc(o) + '</span>' : '', c.km != null ? esc(t('cand.km', (+c.km).toLocaleString(loc(), { maximumFractionDigits: 1 }))) : '', ty === 'habitat' && c.match ? '<span class="mono">' + esc(c.match) + '</span>' : ''].filter(Boolean).join('<br>');
  return '<div class="cand" data-cand="' + k + '"><span class="k">' + (k < 9 ? k + 1 : '') + '</span><div><div class="cl">' + p.title + '</div><div class="cd">' + [p.desc, p.more].filter(Boolean).join(' · ') + '</div>'
    + '<div class="cd">' + p.links.filter(Boolean).join(' ') + '</div></div><div class="cr">' + right + '</div></div>';
}
function searchPanel(ty, e) {
  const ph = t('search.' + ty);
  let extra = '';
  if (ty === 'taxon') extra = '<button class="nbtn" id="sGo" data-go="gbif">' + esc(t('search.gbif')) + ' ⏎</button>';
  if (ty === 'person') extra = '<button class="nbtn" id="sGo" data-go="wd">' + esc(t('search.wd')) + ' ⏎</button><button class="nbtn" data-go="gnd">' + esc(t('search.gnd')) + '</button>';
  if (ty === 'place') extra = '<button class="nbtn" id="sGo" data-go="nom">' + esc(t('search.nom')) + ' ⏎</button>';
  let direct = '';
  if (ty === 'person') direct = '<div class="row" style="margin-top:6px"><span class="small muted">' + esc(t('search.ids')) + '</span><input type="text" id="pqid" size="11" placeholder="' + esc(t('search.qid')) + '"><input type="text" id="pgnd" size="13" placeholder="' + esc(t('search.gndid')) + '"><button class="nbtn" data-go="ids">' + esc(t('btn.take')) + '</button></div>';
  if (ty === 'place') direct = '<div class="row" style="margin-top:6px"><span class="small muted">' + esc(t('search.ids')) + '</span><input type="text" id="plat" size="9" placeholder="' + esc(t('search.lat')) + '"><input type="text" id="plon" size="9" placeholder="' + esc(t('search.lon')) + '"><input type="number" id="punc" style="width:92px" placeholder="' + esc(t('search.unc')) + '" value="' + esc((e.cur && e.cur.unc) || (e.m && e.m.prop && e.m.prop.unc) || 1000) + '"><button class="nbtn" data-go="coords">' + esc(t('search.setloc')) + '</button></div><div class="hint">' + esc(t('search.maphint')) + '</div>';
  return '<div class="panel"><div class="row"><input type="text" class="grow" id="sInput" placeholder="' + esc(ph) + '" autocomplete="off" value="' + esc(ty === 'person' || ty === 'place' ? e.l : '') + '">' + extra
    + (searchRes ? '<button class="nbtn" data-go="clear">✕</button>' : '') + '</div>' + direct + '</div>';
}
function secCands(ty, e) {
  view.cands = searchRes || e.cands || [];
  const list = view.cands.length ? '<div class="cands">' + view.cands.slice(0, 12).map((c, k) => candHtml(ty, c, k)).join('') + '</div>' : '<div class="small muted">' + esc(searchRes ? t('search.nohit') : t('cand.none')) + '</div>';
  return sec(t('sec.cands'), '<div id="candlist">' + list + '</div>' + searchPanel(ty, e), esc(t('auth.' + ty)) + ' · <kbd>A</kbd> ' + esc(t('btn.search')) + ' · <kbd>1</kbd>–<kbd>9</kbd>');
}
function howText(ty, f) {
  const h = f.how || {};
  if (h.k === 'label') return t('names.label');
  const rule = h.rule ? (has('rule.' + h.rule) ? t('rule.' + h.rule) : h.rule) : '';
  if (h.k === 'reviewed') return t('names.how.reviewed', [rule, h.why].filter(Boolean).join(' – '));
  return rule ? t('names.how.rule', rule) : '';
}
function toggles(ty, e, name, fd, soft, isCand) {
  const b = (k, lab) => '<button class="tb ' + k + (fd && ((k === 'same' && fd.d === 'same' && cf(fd.to) === e.k) || (k === 'other' && fd.d === 'same' && cf(fd.to) !== e.k) || (k !== 'same' && k !== 'other' && fd.d === k)) ? ' on' : (!fd && soft && k === 'same' ? ' soft' : ''))
    + '" data-form="' + esc(name) + '" data-fv="' + k + '" title="' + esc(t('names.' + k + '.tip')) + '">' + esc(lab) + '</button>';
  return '<span class="tg">' + b('same', '✓ ' + t('names.same')) + b('own', t('names.own')) + (isCand ? '' : b('other', t('names.other')) + b('none', '✗ ' + t('names.none'))) + '</span>';
}
function formDecText(ty, e, fd) { return fd.d === 'same' ? t('names.dec.same', fd.to) + (fd.toLink && fd.toLink.sci ? ' (' + fd.toLink.sci + ')' : '') : t('names.dec.' + fd.d); }
function secNames(ty, e) {
  const d = entDec(ty, e); const covered = d && (d.d === 'link' || d.d === 'nolink') ? new Set((d.fs || []).map(cf)) : null;
  const rows = e.forms.map(f => {
    const fd = formDec(ty, f.f); const isLabel = cf(f.f) === e.k || e.forms.length === 1; const m = f.m;
    const why = [];
    const how = howText(ty, f); if (how) why.push(esc(how));
    if (f.was) why.push('<b>' + esc(t('names.was', f.was.key ? [f.was.label, f.was.sci, 'GBIF ' + f.was.key].filter(Boolean).join(' · ') : f.was.known ? t('names.unlinked') : t('chg.unknown'))) + '</b>');
    if (m) why.push('<span class="bd ' + (m.ap ? 'mach' : 'unk') + '">' + esc(t(m.ap ? 'badge.applied' : 'badge.suggest')) + '</span>' + esc(t('names.sugg', [wordText(m.none ? 'none' : m.nolink ? 'own' : m.d), m.diff && m.sci ? '→ ' + m.sci : '', dec2(m.c), (m.s || []).map(s => (has('src.' + s) ? t('src.' + s) : s)).join(' + ')].filter(Boolean).join(' · ')))
      + (m.why ? ' <span class="muted">— ' + esc(m.why) + '</span>' : '') + (!m.ap && m.diff ? ' <button class="tb" data-formacc="' + esc(f.f) + '">' + esc(t('btn.acceptform')) + '</button>' : ''));
    const fv = (m && m.votes ? m.votes : []).concat(f.rd || []);
    if (fv.length) why.push('<details class="fv"' + (f.was ? ' open' : '') + '><summary>' + esc(t('m.votes')) + ' (' + fv.length + ')</summary>' + votesHtml(fv) + '</details>');
    if (!f.n) why.push(esc(t('names.zero')));
    if (covered && !covered.has(cf(f.f)) && !fd) why.push('<span class="bd unk">' + esc(t(m && !m.ap && m.diff ? 'names.open' : 'names.new')) + '</span>');
    if (fd) why.push('<span class="bd alt">' + esc(t('dec.you')) + ': ' + esc(formDecText(ty, e, fd)) + '</span>');
    return '<div class="nm' + (f.was ? ' chg' : '') + '"><div><span class="nn">' + esc(f.f) + '</span><span class="ct"' + (corpus() ? ' title="' + esc(t('corp.in', fmt(fcn(f)), fmt(f.n))) + '"' : '') + '>' + (f.n ? (corpus() ? fmt(fcn(f)) + ' / ' : '') + fmt(f.n) : '–') + '</span></div>'
      + (isLabel && !fd ? '<span class="small muted">' + (e.forms.length === 1 ? '' : '') + '</span>' : toggles(ty, e, f.f, fd, covered && covered.has(cf(f.f))))
      + (why.length ? '<div class="why">' + why.join(' · ') + '</div>' : '') + (panelForm === f.f ? '<div class="why" id="formpanel"></div>' : '') + '</div>';
  });
  const inc = (e.mgin || []).map(c => {
    const fd = formDec(ty, c.v);
    return '<div class="nm cand2"><div><span class="bd">' + esc(t('names.cand')) + '</span><span class="nn">' + esc(c.v) + '</span><span class="ct">' + fmt(c.n) + '</span> <a href="#" class="small" data-open="' + esc(cf(c.from)) + '">' + esc(t('mg.open')) + '</a></div>'
      + toggles(ty, e, c.v, fd, false, true) + '<div class="why">' + esc(t('names.how.rule', has('rule.' + c.rule) ? t('rule.' + c.rule) : c.rule)) + (fd ? ' · <span class="bd alt">' + esc(t('dec.you')) + ': ' + esc(formDecText(ty, e, fd)) + '</span>' : '') + '</div></div>';
  });
  return sec(t('sec.names'), '<div class="names">' + rows.join('') + (inc.length ? '<div class="small muted" style="margin-top:6px">' + esc(t('names.incoming')) + '</div>' + inc.join('') : '') + '</div>', esc(t('card.names', fmt(e.forms.length))));
}
const dateText = d => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ''); return m ? (LANG === 'en' ? m[1] + '-' + m[2] + '-' + m[3] : (+m[3]) + '.' + (+m[2]) + '.' + m[1]) : (d || ''); };
function secEv(ty, e) {
  const ev = e.ev || []; const c = corpus();
  const order = ev.map((m, i) => i); if (c > 0) order.sort((a, b) => (menIn(ev[b]) - menIn(ev[a])) || a - b);     // passages of the corpus first
  const body = ev.length ? order.map(i => { const m = ev[i]; const out = c > 0 && !menIn(m);
    const tx = m.hs >= 0 && m.he > m.hs ? esc(m.tx.slice(0, m.hs)) + '<mark>' + esc(m.tx.slice(m.hs, m.he)) + '</mark>' + esc(m.tx.slice(m.he)) : esc(m.tx);
    const roles = (m.ro || '').split('/').filter(Boolean).map(r => (has('role.' + r) ? t('role.' + r) : r)).join(', ');
    return '<div class="men' + (i === curMen ? ' on' : '') + (out ? ' out' : '') + '" data-men="' + i + '" title="' + esc(t('ev.show')) + '"><div class="mh"><b>' + esc(dateText(m.d) || m.vd || '') + '</b><span class="mono">' + esc(m.id) + '</span>' + (cf(m.f) !== e.k ? '<span class="bd">' + esc(m.f) + '</span>' : '')
      + (roles ? '<span>' + esc(roles) + '</span>' : '') + (ty === 'place' && m.hp && cf(m.hp) !== e.k ? '<span class="muted">' + esc(t('ev.header', m.hp)) + '</span>' : '') + '<span class="sp"></span>'
      + (m.b ? (m.b[4] ? '<span class="bd unk">' + esc(t('ev.approx')) + '</span>' : '') : '<span class="bd">' + esc(t('ev.noscan')) + '</span>') + tierChip(m) + '</div><div class="kw">' + tx + '</div>'
      + (out ? '<div class="trw">' + esc(tierWhy(m)) + '</div>' : '') + '</div>';
  }).join('') : '<div class="small muted">' + esc(t('ev.none')) + '</div>';
  return sec(t('sec.ev'), body, esc(countText(e)));
}
function secYears(ty, e) {
  if (ty !== 'person' || !e.yrs || !e.yrs.length) return '';
  const d = entDec(ty, e); const lk = d && d.d === 'link' ? d.target : e.cur;
  const born = lk && lk.born ? +String(lk.born).slice(0, 4) : null, died = lk && lk.died ? +String(lk.died).slice(0, 4) : null;
  const y0 = Math.min(1917, e.yrs[0][0]), y1 = Math.max(1965, e.yrs[e.yrs.length - 1][0]); const max = Math.max(...e.yrs.map(y => y[1]));
  const W = 760, H = 86, pad = 14, bw = (W - 2 * pad) / (y1 - y0 + 1); const x = y => pad + (y - y0) * bw;
  let svg = '<svg class="hist" viewBox="0 0 ' + W + ' ' + H + '" role="img">';
  if (born || died) { const a = Math.max(y0, born || y0), b = Math.min(y1 + 1, died != null ? died + 1 : y1 + 1); if (b > a) svg += '<rect x="' + x(a) + '" y="4" width="' + (x(b) - x(a)) + '" height="' + (H - 22) + '" fill="var(--ok-soft)"></rect>'; }
  let out = 0;
  for (const [y, n] of e.yrs) { const h = Math.max(3, Math.round((H - 28) * n / max)); const bad = (born && y < born) || (died && y > died); if (bad) out += n; svg += '<rect x="' + (x(y) + 1) + '" y="' + (H - 18 - h) + '" width="' + Math.max(2, bw - 2) + '" height="' + h + '" fill="' + (bad ? 'var(--no)' : 'var(--acc2)') + '"><title>' + y + ': ' + n + '</title></rect>'; }
  svg += '<line x1="' + pad + '" y1="' + (H - 18) + '" x2="' + (W - pad) + '" y2="' + (H - 18) + '" stroke="var(--line2)"></line>';
  for (let y = Math.ceil(y0 / 10) * 10; y <= y1; y += 10) svg += '<text x="' + (x(y) + bw / 2) + '" y="' + (H - 5) + '" text-anchor="middle">' + y + '</text>';
  svg += '</svg>';
  const note = born || died ? esc(t('years.life', born || '?', died || '')) + ' · ' + (out ? '<span style="color:var(--no)">' + esc(t('years.outside', fmt(out))) + '</span>' : esc(t('years.inside'))) : '';
  return sec(t('sec.years'), '<div class="box">' + svg + (note ? '<div class="small muted">' + note + '</div>' : '') + '</div>', esc(t('card.years', e.yrs[0][0], e.yrs[e.yrs.length - 1][0])));
}
function secMerge(ty, e) {
  if (!e.mg) return '';
  const body = mergeNames(e).map(v => {
    const cands = e.mg.filter(c => c.v === v); const fd = formDec(ty, v);
    const state = fd ? '<div class="state ' + (fd.d === 'same' ? 'a' : 'o') + '"><b>' + esc(fd.d === 'same' ? t('mg.decided.same', fd.to) : fd.d === 'own' ? t('mg.decided.own') : t('names.dec.none')) + '</b><span class="sd"></span><button class="lbtn" data-formclear="' + esc(v) + '">' + esc(t('btn.clear')) + '</button></div>' : '';
    return '<div class="box"><div style="font-weight:620">' + esc(t('mg.q', v)) + '</div><div class="cands" style="margin-top:6px">' + cands.map((c, k) => {
      const te = BYK[ty].get(cf(c.to));
      return '<div class="cand" data-mg="' + esc(v) + '" data-to="' + esc(c.to) + '"><span class="k">' + (k + 1) + '</span><div><div class="cl">' + esc(c.to) + ' <span class="ct muted" style="font-weight:400">' + fmt(c.n) + '</span></div><div class="cd">' + esc(te ? linkShort(ty, te.cur) : '')
        + '</div><div class="cd">' + esc(t('mg.rule') + ': ' + (has('rule.' + c.rule) ? t('rule.' + c.rule) : c.rule)) + (c.detail ? ' · ' + esc(c.detail) : '') + '</div></div><div class="cr"><a href="#" data-open="' + esc(cf(c.to)) + '">' + esc(t('mg.open')) + '</a></div></div>';
    }).join('') + '</div>' + state + '</div>';
  }).join('');
  return sec(t('sec.merge'), body, esc(t('mg.hint')));
}
function decText(ty, d) {
  if (d.d === 'link') return t('dec.link.' + (d.via === 'confirm' ? 'confirm' : d.via === 'accept' ? 'accept' : d.via === 'revert' ? 'revert' : 'pick')) + ': ' + linkShort(ty, d.target) + (d.grade && (ty === 'taxon' || ty === 'habitat') ? ' · ' + d.grade : '');
  if (d.d === 'none') return t('dec.none.' + ty);
  return t('dec.' + d.d) + (d.via === 'revert' ? ' (' + t('dec.link.revert') + ')' : '');
}
function stateHtml(ty, e) {
  const d = entDec(ty, e);
  if (!d) {
    if (!entDone(ty, e)) return '';
    const lf = formDec(ty, e.l);
    return '<div class="state p" id="state"><b>' + esc(t('dec.you')) + ':</b><span class="sd">' + esc(lf && lf.d === 'same' && cf(lf.to) !== e.k ? t('dec.merged', lf.to) : t('dec.formsonly')) + '</span></div>';
  }
  const sugg = new Set(openSuggested(e).map(cf));
  const added = namesOf(e).filter(n => !(d.fs || []).map(cf).includes(cf(n)) && !sugg.has(cf(n)));
  const still = d.d === 'link' ? openSuggested(e).filter(n => !formDec(ty, n)) : [];
  return '<div class="state ' + decClass(ty, e) + '" id="state"><b>' + esc(t('dec.you')) + ':</b><span class="sd">' + esc(decText(ty, d)) + '</span><input type="text" id="note" placeholder="' + esc(t('dec.note')) + '" value="' + esc(d.note || '') + '">'
    + '<button class="lbtn" data-act="clear">' + esc(t('btn.clear')) + '</button>' + (d.chk ? '<div class="chk">' + esc(t('dec.import')) + '</div>' : '') + (added.length && d.d !== 'unsure' ? '<div class="chk">' + esc(t('dec.newforms', added.join(', '))) + '</div>' : '') + (still.length ? '<div class="chk">' + esc(t('dec.openforms', still.join(', '))) + '</div>' : '') + '</div>';
}
function renderCard() {
  const ty = cur.type; const wrap = $('#cardwrap');
  if (ty === 'home') return renderHome();
  const e = curEnt();
  if (!e) { wrap.innerHTML = '<div class="empty">' + esc(t('card.none')) + '</div>'; return; }
  const items = listItems(ty); const pos = items.indexOf(e);
  const yrs = e.yrs && e.yrs.length ? ' · ' + t('card.years', e.yrs[0][0], e.yrs[e.yrs.length - 1][0]) : '';
  const qb = '<span class="bd ' + ({ changed: 'mach', confirmed: 'ok', suggest: 'unk', pipeline: 'pipe', unlinked: '' })[e.q] + ' big">' + esc(t('q.' + e.q)) + '</span>';
  const mergeFirst = curQ(ty) === 'merge' && e.mg;
  wrap.innerHTML = '<div class="wrap"><div class="crumb"><span>' + esc(t('one.' + ty)) + '</span>' + qb + (pos >= 0 ? '<span>' + fmt(pos + 1) + ' / ' + fmt(items.length) + '</span>' : '')
    + '<span class="nav"><button class="nbtn" data-nav="prev" title="' + esc(t('card.prev')) + '">↑</button><button class="nbtn" data-nav="next" title="' + esc(t('card.next')) + '">↓</button><button class="nbtn primary" data-nav="open">' + esc(t('card.nextopen')) + '</button></span></div>'
    + '<h1 class="t">' + esc(e.l) + (e.gone ? ' <span class="bd no big">' + esc(t('gone.badge')) + '</span>' : '') + '</h1><p class="sub">' + esc(countText(e) + ' · ' + t('card.names', fmt(e.forms.length)) + yrs
    + (ty === 'place' && e.kind ? ' · ' + (has('place.kind.' + e.kind) ? t('place.kind.' + e.kind) : e.kind) : '')) + '</p>'
    + stateHtml(ty, e) + (mergeFirst ? secMerge(ty, e) : '') + secGraph(ty, e) + secChange(ty, e) + secSuggest(ty, e) + secDrift(ty, e) + secCands(ty, e) + secNames(ty, e) + (mergeFirst ? '' : secMerge(ty, e)) + secEv(ty, e) + secYears(ty, e) + '</div>';
  if (ty === 'place') initMap(e);
  if (panelForm) renderFormPanel(ty, e);
  enrichWD();
}

// ---------------------------------------------------------------- action bar
function curGrade(ty, e) { const d = entDec(ty, e); return gradePick || (d && d.grade) || defaultGrade(ty, e.cur, e); }
function renderActbar() {
  const ty = cur.type; const el = $('#actbar'); const e = curEnt();
  if (ty === 'home' || !e) { el.innerHTML = ''; return; }
  const d = entDec(ty, e); const on = k => (d && ((k === 'confirm' && d.d !== 'unsure' && d.via === 'confirm') || (k === 'other' && d.d === 'link' && d.via !== 'confirm') || (k === d.d && d.via !== 'confirm')) ? ' on' : '');
  if (curQ(ty) === 'merge' && e.mg) {
    const v = mergeNames(e).find(n => !formDec(ty, n)) || mergeNames(e)[0]; const first = e.mg.find(c => c.v === v);
    el.innerHTML = '<button class="btn a" data-act="mgsame">' + esc(t('btn.same', first.to)) + ' <kbd>J</kbd></button><button class="btn r" data-act="mgdiff">' + esc(t('btn.diff')) + ' <kbd>N</kbd></button><span class="sp"></span>'
      + '<button class="btn sm" data-act="tolink">' + esc(t('btn.tolink')) + '</button><button class="btn sm" data-act="undo">↶ <kbd>Z</kbd></button>';
    return;
  }
  const confirmLabel = e.gone ? 'btn.confirm.gone' : e.cur ? 'btn.confirm' : 'btn.confirm.nolink';
  const grades = ty === 'taxon' || ty === 'habitat' ? '<span class="gradesel" title="' + esc(t('grade')) + '">' + esc(t('grade')) + ' ' + ['exact', 'close', 'broad'].map(g => '<button class="gb' + (curGrade(ty, e) === g ? ' on' : '') + '" data-grade="' + g + '" title="' + esc(t('grade.' + g + '.tip')) + '">' + g + '</button>').join('') + '</span>' : '<span class="sp"></span>';
  el.innerHTML = '<button class="btn a' + on('confirm') + '" data-act="confirm">' + esc(t(confirmLabel)) + ' <kbd>J</kbd></button><button class="btn o' + on('other') + '" data-act="other">' + esc(t('btn.other')) + ' <kbd>A</kbd></button>'
    + (e.cur || e.gone ? '<button class="btn r' + on('nolink') + '" data-act="nolink">' + esc(t('btn.nolink')) + ' <kbd>N</kbd></button>' : '')
    + '<button class="btn r' + on('none') + '" data-act="none">' + esc(t('btn.none.' + ty)) + ' <kbd>X</kbd></button><button class="btn u' + on('unsure') + '" data-act="unsure">' + esc(t('btn.unsure')) + ' <kbd>U</kbd></button>'
    + grades;
}

// ---------------------------------------------------------------- overview
function corpusTableHtml() {   // the four corpora per type: entries with a mention in the corpus, mentions
  if (!D.corpus) return '';
  const c0 = corpus(); const pc = (a, b) => (b ? (100 * a / b).toLocaleString(loc(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' %' : '–');
  const rows = [0, 1, 2, 3].map(c => {
    const cells = TYPES.map(ty => { let en = 0, mn = 0; for (const e of ENTS[ty]) { const v = c === 0 ? e.n : (e.nc ? e.nc[c] : 0); if (v > 0) { en++; mn += v; } } return '<td class="n" data-cc="' + ty + '-e">' + fmt(en) + '</td><td class="n" data-cc="' + ty + '-m">' + fmt(mn) + '</td>'; }).join('');
    return '<tr class="ql' + (c === c0 ? ' on' : '') + '" data-corpus="' + c + '"><td class="q">' + (c ? '<span class="trc tr' + c + '">K' + c + '</span> ' : '') + esc(t('corp.' + c)) + '</td><td class="n">' + fmt(D.corpus.rec[c]) + '</td><td class="n muted">' + pc(D.corpus.rec[c], D.corpus.rec[0]) + '</td>' + cells + '</tr>';
  }).join('');
  return '<h2>' + esc(t('home.corp.h')) + '</h2><p>' + t('home.corp.lead') + '</p><div class="hc"><table class="covt"><tr><td class="muted" rowspan="2">' + esc(t('home.corp.c')) + '</td><td class="n muted" rowspan="2" colspan="2">' + esc(t('home.corp.rec')) + '</td>'
    + TYPES.map(ty => '<td class="n th" colspan="2">' + esc(t('type.' + ty)) + '</td>').join('') + '</tr><tr>' + TYPES.map(() => '<td class="n muted">' + esc(t('home.corp.ent')) + '</td><td class="n muted">' + esc(t('home.corp.men')) + '</td>').join('') + '</tr>' + rows + '</table></div>';
}
function renderHome() {
  const cards = TYPES.map(ty => {
    const p = typeProgress(ty); const [c] = queueCounts(ty);
    const mentions = {}; for (const q of QUEUES) mentions[q] = 0;
    for (const e of corpusItems(ty)) { const w = cn(e); mentions[e.q] += w; if (e.mg) mentions.merge += w; if (entDone(ty, e)) mentions.done += w; }
    const rows = QUEUES.map(q => '<tr class="ql" data-home="' + ty + '" data-hq="' + q + '" title="' + esc(t('q.' + q + '.tip')) + '"><td class="q">' + esc(t('q.' + q)) + '</td><td class="n">' + fmt(c[q].n) + '</td><td class="n">' + fmt(mentions[q]) + '</td><td class="n">'
      + (q === 'done' ? '' : fmt(c[q].n - c[q].open)) + '</td></tr>').join('');
    return '<div class="hc"><h3>' + esc(t('type.' + ty)) + ' <small>' + esc(t('auth.' + ty)) + '</small></h3><div class="cov">' + esc(t('home.entities', fmt(p.ents), fmt(p.n))) + '</div><div class="pbar"><i style="width:' + p.pct + '%"></i></div><div class="cov"><b>' + esc(t('home.cover', p.pct.toLocaleString(loc())))
      + '</b>' + (p.unsure ? ' · ' + esc(t('home.unsure', fmt(p.unsure))) : '') + '</div><table><tr><td class="muted">' + esc(t('home.col.q')) + '</td><td class="n muted">' + esc(t('home.col.n')) + '</td><td class="n muted">' + esc(t('home.col.m')) + '</td><td class="n muted">' + esc(t('home.col.d')) + '</td></tr>' + rows + '</table></div>';
  }).join('');
  let orphan = 0; for (const ty of TYPES) for (const k of Object.keys(S.ent[ty])) if (!BYK[ty].has(k)) orphan++;
  const rounds = (D.rounds || []).map(r => '<span class="bd">' + esc(r.label) + '</span> ' + esc([r.model, (r.built || '').slice(0, 10), r.dir].filter(Boolean).join(' · '))).join(' &nbsp; ');
  $('#cardwrap').innerHTML = '<div class="wrap wide home"><h1>' + esc(t('home.title')) + '</h1><p class="lead">' + esc(t('home.lead')) + '</p><div class="meta">' + esc(t('home.graph', D.export, D.base_export || '–', D.built)) + '</div>'
    + '<div class="grid4">' + cards + '</div>' + (orphan ? '<p class="small" style="color:var(--unk)">' + esc(t('home.unknown', fmt(orphan))) + '</p>' : '') + corpusTableHtml()
    + '<h2>' + esc(t('home.h.thresh')) + '</h2><p>' + esc(t('home.thresh', dec2(D.thresholds.conf), D.thresholds.agree)) + '</p><div class="meta">' + esc(t('home.rounds')) + ': ' + rounds + '</div>'
    + '<h2>' + esc(t('home.h.how')) + '</h2><ol>' + t('home.how') + '</ol><h2>' + esc(t('home.h.keys')) + '</h2><p class="kbdrow">' + t('home.keys') + '</p></div>';
}

// ---------------------------------------------------------------- scan pane
const scan = { pages: [], p: -1, hl: null, zoom: 0 };
let localOK = null;                       // null unknown, true: page JPEGs next to the page work, false: use Drive first
const driveThumb = id => 'https://drive.google.com/thumbnail?id=' + id + '&sz=w1600';
function pageSources(g) {
  const local = CFG.scans ? CFG.scans + g[0] + '.jpg' : ''; const drive = g[7] ? driveThumb(g[7]) : '';
  return (localOK === false ? [drive, local] : [local, drive]).filter(Boolean);
}
function pageLabel(p) { const g = PAGES[p]; return t('scan.title', g[1], g[2]) + (g[3] === 'L' ? t('scan.left') : g[3] === 'R' ? t('scan.right') : '') + (g[4] ? t('scan.page', String(g[4]).replace(/\.$/, '')) : ''); }
function showMention(i, quiet) {
  const e = curEnt(); if (!e || !e.ev || !e.ev[i]) return;
  curMen = i; const m = e.ev[i];
  scan.pages = (m.pp && m.pp.length ? m.pp : [m.p]).filter(p => p >= 0); scan.p = m.p != null ? m.p : (scan.pages[0] != null ? scan.pages[0] : -1); scan.hl = m.b ? { p: m.p, b: m.b } : null;
  $$('.men').forEach(el => el.classList.toggle('on', +el.dataset.men === i));
  if (!quiet && !S.ui.scan) { S.ui.scan = true; save(); $('#main').classList.remove('noscan'); }
  renderScan();
}
function renderScan() {
  const body = $('#scanbody'); const e = curEnt();
  if (!e || scan.p == null || scan.p < 0 || !PAGES[scan.p]) { $('#scantitle').textContent = ''; $('#scanpages').innerHTML = ''; body.innerHTML = '<div class="msg">' + esc(e && e.ev && e.ev.length ? t('scan.none') : t('scan.empty')) + '</div>'; return; }
  const g = PAGES[scan.p]; const m = e.ev[curMen];
  $('#scantitle').innerHTML = esc(pageLabel(scan.p)) + (m ? ' <span>· ' + esc(m.id) + '</span>' : '');
  $('#scanpages').innerHTML = scan.pages.length > 1 ? scan.pages.map((p, k) => '<button class="nbtn' + (p === scan.p ? ' on' : '') + '" data-page="' + p + '" title="' + esc(t('scan.pageOf', k + 1, scan.pages.length)) + '">' + (k + 1) + '</button>').join('') : '';
  $('#scanopen').href = g[7] ? 'https://drive.google.com/file/d/' + g[7] + '/view' : '#'; $('#scanopen').style.display = g[7] ? '' : 'none';
  const many = scan.pages.length > 6;                    // numbered page buttons up to six pages, ‹ › beyond
  $('#scanprev').style.display = $('#scannext').style.display = many ? '' : 'none'; $('#scanpages').style.display = many ? 'none' : '';
  const srcs = pageSources(g);
  body.innerHTML = '<div class="scanwrap' + (scan.zoom ? ' z' + scan.zoom : '') + '" id="scanwrap"><img id="scanimg" alt=""></div>';
  const img = $('#scanimg'); let k = 0;
  const fail = () => { body.innerHTML = '<div class="msg">' + esc(t('scan.fail')) + (g[7] ? ' <a href="https://drive.google.com/file/d/' + g[7] + '/view" target="_blank" rel="noopener">' + esc(t('scan.open')) + '</a>' : '') + '</div>'; };
  img.onerror = () => { if (srcs[k] && srcs[k].indexOf('drive.google') < 0 && localOK == null) localOK = false; k++; if (k < srcs.length) img.src = srcs[k]; else fail(); };
  img.onload = () => { if (srcs[k] && srcs[k].indexOf('drive.google') < 0) localOK = true; placeHl(); };
  if (srcs.length) img.src = srcs[0]; else fail();
}
function placeHl() {
  const img = $('#scanimg'); const wrap = $('#scanwrap'); if (!img || !wrap) return;
  $$('.hlbox,.hlseg,.hllab', wrap).forEach(x => x.remove());
  if (!scan.hl || scan.hl.p !== scan.p) return;
  const g = PAGES[scan.p]; const s = img.clientWidth / (g[5] || img.naturalWidth || 1); const [x0, y0, x1, y1, approx, f0, f1] = scan.hl.b;
  const box = document.createElement('div'); box.className = 'hlbox' + (approx ? ' approx' : '');
  box.style.left = (x0 * s - 4) + 'px'; box.style.top = (y0 * s - 4) + 'px'; box.style.width = ((x1 - x0) * s + 8) + 'px'; box.style.height = ((y1 - y0) * s + 8) + 'px'; wrap.appendChild(box);
  if (f0 != null && f1 != null && !approx) { const seg = document.createElement('div'); seg.className = 'hlseg'; seg.style.top = box.style.top; seg.style.height = box.style.height; seg.style.left = ((x0 + f0 * (x1 - x0)) * s - 2) + 'px'; seg.style.width = Math.max(10, (f1 - f0) * (x1 - x0) * s + 4) + 'px'; wrap.appendChild(seg); }
  if (approx) { const lab = document.createElement('div'); lab.className = 'hllab'; lab.textContent = t('scan.approx'); lab.style.left = (x0 * s) + 'px'; lab.style.top = Math.max(0, y0 * s - 22) + 'px'; wrap.appendChild(lab); }
  const sb = $('#scanbody'); sb.scrollTop = Math.max(0, y0 * s - sb.clientHeight * 0.35);
  if (scan.zoom) sb.scrollLeft = Math.max(0, (x0 + (f0 || 0) * (x1 - x0)) * s - sb.clientWidth * 0.3);
}

// ---------------------------------------------------------------- map (places)
let map = null, pickMarker = null;
// the chosen point: a ring (Leaflet's default marker needs image files, which a single-file page does not have)
const pinAt = ll => L.circleMarker(ll, { radius: 10, color: '#111', weight: 3, fillColor: '#ffd400', fillOpacity: .9 }).addTo(map).bindTooltip(t('map.pick'));
function initMap(e) {
  const el = $('#map'); if (!el || typeof L === 'undefined') return;
  if (map) { try { map.remove(); } catch (err) { /* gone with the old card */ } map = null; pickMarker = null; }
  const d = entDec('place', e); const pts = []; const legend = [];
  const has1 = x => x && x.lat != null;
  if (!has1(e.cur) && !has1(e.before) && !(e.m && has1(e.m.prop)) && !(e.cands || []).some(has1) && !(e.anc || []).length && !(d && has1(d.target))) { el.style.display = 'none'; $('#maplegend').textContent = t('map.none'); return; }
  map = L.map(el, { zoomControl: true, attributionControl: false, scrollWheelZoom: false });
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', { maxZoom: 17 }).addTo(map);
  const mk = (lat, lon, color, title, r) => { L.circleMarker([lat, lon], { radius: r || 8, color: '#fff', weight: 1.5, fillColor: color, fillOpacity: .95 }).addTo(map).bindTooltip(title); pts.push([lat, lon]); };
  const leg = (color, key) => { if (!legend.some(x => x[1] === key)) legend.push([color, key]); };
  for (const a of e.anc || []) if (a.lat != null) { mk(a.lat, a.lon, '#8a919b', t('map.anchor') + ': ' + a.place + ' (' + a.n + ')' + (a.km != null ? ' · ' + a.km + ' km' : ''), 6); leg('#8a919b', 'map.anchor'); }
  (searchRes || e.cands || []).forEach((c, k) => { if (c.lat != null && c.o !== 'b' && c.o !== 'm') { mk(c.lat, c.lon, '#2c5c98', (k + 1) + ' · ' + t('map.cand') + ': ' + (c.name || ''), 6); leg('#2c5c98', 'map.cand'); } });
  if (has1(e.before) && e.q === 'changed') { mk(e.before.lat, e.before.lon, '#6541a3', t('map.before') + ': ' + (+e.before.lat).toFixed(4) + ', ' + (+e.before.lon).toFixed(4), 7); leg('#6541a3', 'map.before'); }
  if (e.m && has1(e.m.prop) && (!e.m.ap || e.m.ineff) && !sameLink('place', e.m.prop, e.cur)) { mk(e.m.prop.lat, e.m.prop.lon, '#0c666c', t('map.prop') + ': ' + (e.m.prop.name || ''), 8); leg('#0c666c', 'map.prop'); }
  if (has1(e.cur)) { mk(e.cur.lat, e.cur.lon, '#c0392b', t('map.cur') + ': ' + e.l + ' (' + (+e.cur.lat).toFixed(4) + ', ' + (+e.cur.lon).toFixed(4) + ')', 9); leg('#c0392b', 'map.cur'); if (e.cur.unc) L.circle([e.cur.lat, e.cur.lon], { radius: +e.cur.unc, color: '#c0392b', weight: 1, fillOpacity: .06 }).addTo(map); }
  if (d && has1(d.target) && !sameLink('place', d.target, e.cur)) { pickMarker = pinAt([d.target.lat, d.target.lon]); pts.push([d.target.lat, d.target.lon]); leg('#111', 'map.pick'); }
  if (pts.length) map.fitBounds(L.latLngBounds(pts.map(p => L.latLng(p[0], p[1]))).pad(0.3), { maxZoom: 12 }); else map.setView([48.14, 11.58], 8);
  map.on('click', ev => { const la = $('#plat'), lo = $('#plon'); if (!la || !lo) return; la.value = ev.latlng.lat.toFixed(5); lo.value = ev.latlng.lng.toFixed(5); if (pickMarker) pickMarker.setLatLng(ev.latlng); else pickMarker = pinAt(ev.latlng); });
  $('#maplegend').innerHTML = legend.map(x => '<span><i style="background:' + x[0] + '"></i>' + esc(t(x[1])) + '</span>').join('');
}

// ---------------------------------------------------------------- refresh
function refresh(scroll) {
  const ty = cur.type;
  $('#main').className = 'main' + (ty === 'home' ? ' home' : S.ui.scan ? '' : ' noscan');
  renderHeader(); renderList(scroll); renderCard(); renderActbar();
  if (ty !== 'home') { if (curMen < 0) pickDefaultMention(); else renderScan(); }
}
function pickDefaultMention() {
  const e = curEnt(); if (!e || !e.ev || !e.ev.length) { curMen = -1; scan.p = -1; renderScan(); return; }
  const ok = m => !corpus() || menIn(m);                               // under a filter: a passage of the corpus first
  let i = e.ev.findIndex(m => ok(m) && m.b && !m.b[4]); if (i < 0) i = e.ev.findIndex(m => ok(m) && m.b); if (i < 0) i = e.ev.findIndex(m => m.b && !m.b[4]); if (i < 0) i = e.ev.findIndex(m => m.b); if (i < 0) i = 0;
  showMention(i, true);
}
function openEntity(ty, key, scroll) {
  cur.type = ty; S.ui.type = ty; cur.key = key; if (ty !== 'home') S.ui.sel[ty] = key;
  panelForm = null; searchRes = null; gradePick = null; curMen = -1;
  save(); refresh(scroll !== false);
  const cw = $('#cardwrap'); if (cw) cw.scrollTop = 0;
}
function openType(ty) {
  if (ty === 'home') return openEntity('home', null);
  const items = listItems(ty); let key = S.ui.sel[ty];
  if (!key || !items.some(e => e.k === key)) key = (items.find(e => isOpen(ty, e, curQ(ty))) || items[0] || {}).k || null;
  openEntity(ty, key);
}
