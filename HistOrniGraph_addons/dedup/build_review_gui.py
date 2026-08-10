#!/usr/bin/env python3
"""Build a self-contained duplicate-review GUI from duplicates_report.jsonl.

A student assistant opens one HTML file, works through each suspected cluster
side by side, and confirms or rejects it (choosing which page to keep). Edits
auto-save to localStorage and export to a decisions JSON that apply_dedup.py
consumes. Matches the HistOrniGraph validator look (Literata / IBM Plex Mono,
warm palette, localStorage session, portable JSON export).

Usage:
    python build_review_gui.py dedup_reports/duplicates_report.jsonl \
        --corpus corpus/corpus.json -o dedup_reports/review.html
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_MARKUP_RE = re.compile(r"</?(?:u|sup|sub|b|i|em|strong)\s*>", re.IGNORECASE)


def _page_text(page: Dict[str, Any]) -> str:
    return "\n\n".join(r.get("text", "") for r in page.get("regions", []))


def build_data(report_jsonl: Path,
               corpus_json: Optional[Path]) -> Dict[str, Any]:
    clusters = [json.loads(ln) for ln in
                report_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]

    text_by_uid: Dict[str, str] = {}
    if corpus_json and corpus_json.exists():
        for page in json.loads(corpus_json.read_text(encoding="utf-8")):
            uid = f"L{int(page['volume']):02d}:{page['page_id']}"
            text_by_uid[uid] = _page_text(page)

    for c in clusters:
        for m in c["members"]:
            m["text"] = text_by_uid.get(m["page_uid"], "")
    return {"clusters": clusters}


def generate_html(data: Dict[str, Any]) -> str:
    data_json = json.dumps(data, ensure_ascii=False)
    return _TEMPLATE.replace("/*__DATA__*/", data_json)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Laubmann — Duplicate Review</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Literata:ital,opsz,wght@0,7..72,300;0,7..72,400;0,7..72,600;1,7..72,400&display=swap');
  :root {
    --bg-primary:#faf8f5; --bg-secondary:#f0ece6; --bg-panel:#ffffff;
    --border:#d4cfc7; --border-active:#8b6914; --text-primary:#2c2418;
    --text-secondary:#6b6050; --text-muted:#968c7a; --accent:#8b6914;
    --accent-subtle:rgba(139,105,20,0.08); --success:#3a7d44;
    --success-subtle:rgba(58,125,68,0.10); --danger:#c04030;
    --danger-subtle:rgba(192,64,48,0.10); --warning:#c07d16;
    --keep:#3a7d44; --keep-subtle:rgba(58,125,68,0.14);
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg-primary); color:var(--text-primary);
    font-family:'Literata',Georgia,serif; font-size:15px; line-height:1.5; }
  header { position:sticky; top:0; z-index:20; background:var(--bg-panel);
    border-bottom:1px solid var(--border); padding:14px 22px;
    display:flex; align-items:center; gap:20px; flex-wrap:wrap; }
  h1 { font-size:17px; font-weight:600; margin:0; letter-spacing:0.01em; }
  .mono { font-family:'IBM Plex Mono',monospace; }
  .counts { display:flex; gap:16px; font-size:12.5px; color:var(--text-secondary);
    font-family:'IBM Plex Mono',monospace; }
  .counts b { color:var(--text-primary); font-weight:600; }
  .counts .done b { color:var(--success); }
  .counts .rej b { color:var(--danger); }
  .spacer { flex:1; }
  button { font-family:'IBM Plex Mono',monospace; font-size:12.5px;
    border:1px solid var(--border); background:var(--bg-panel);
    color:var(--text-primary); padding:7px 13px; border-radius:5px;
    cursor:pointer; transition:all .12s; }
  button:hover { border-color:var(--border-active); background:var(--accent-subtle); }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  button.primary:hover { background:#a37d1a; }
  #autosave { font-size:11.5px; color:var(--text-muted);
    font-family:'IBM Plex Mono',monospace; min-width:120px; }
  .wrap { max-width:1180px; margin:0 auto; padding:22px; }
  .filters { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
  .filters button.active { background:var(--accent); color:#fff; border-color:var(--accent); }
  .cluster { background:var(--bg-panel); border:1px solid var(--border);
    border-radius:8px; margin-bottom:20px; overflow:hidden; }
  .cluster.decided-confirm { border-left:4px solid var(--success); }
  .cluster.decided-reject { border-left:4px solid var(--danger); }
  .chead { display:flex; align-items:center; gap:14px; padding:12px 16px;
    background:var(--bg-secondary); border-bottom:1px solid var(--border);
    flex-wrap:wrap; }
  .cid { font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:13px; }
  .conf { font-family:'IBM Plex Mono',monospace; font-size:12px; padding:2px 8px;
    border-radius:10px; background:var(--accent-subtle); color:var(--accent); }
  .conf.hi { background:var(--success-subtle); color:var(--success); }
  .conf.lo { background:var(--danger-subtle); color:var(--danger); }
  .relation { font-family:'IBM Plex Mono',monospace; font-size:11.5px;
    color:var(--text-muted); }
  .signals { display:flex; gap:5px; flex-wrap:wrap; }
  .sig { font-family:'IBM Plex Mono',monospace; font-size:10.5px;
    padding:1px 6px; border-radius:8px; background:var(--bg-tertiary,#e8e3db);
    color:var(--text-secondary); border:1px solid var(--border); }
  .sig.struct { background:var(--accent-subtle); color:var(--accent); border-color:transparent; }
  .members { display:grid; gap:0; }
  .members.n2 { grid-template-columns:1fr 1fr; }
  .members.n3 { grid-template-columns:1fr 1fr 1fr; }
  .members.n4 { grid-template-columns:1fr 1fr; }
  .member { border-right:1px solid var(--border); border-bottom:1px solid var(--border);
    padding:0; display:flex; flex-direction:column; min-width:0; }
  .member.keep { background:var(--keep-subtle); }
  .mhead { padding:9px 13px; border-bottom:1px solid var(--border);
    display:flex; align-items:center; gap:9px; flex-wrap:wrap;
    background:var(--bg-primary); }
  .member.keep .mhead { background:var(--keep-subtle); }
  .uid { font-family:'IBM Plex Mono',monospace; font-size:11.5px;
    color:var(--text-secondary); word-break:break-all; flex:1; min-width:0; }
  .badge { font-family:'IBM Plex Mono',monospace; font-size:10px;
    padding:1px 6px; border-radius:8px; white-space:nowrap; }
  .badge.pn { background:var(--accent-subtle); color:var(--accent); }
  .badge.q  { background:var(--danger-subtle); color:var(--danger); }
  .keepbtn { font-size:11px; padding:4px 9px; }
  .keepbtn.on { background:var(--keep); color:#fff; border-color:var(--keep); }
  .mstats { padding:5px 13px; font-family:'IBM Plex Mono',monospace;
    font-size:10.5px; color:var(--text-muted); border-bottom:1px solid var(--border);
    display:flex; gap:12px; }
  .mtext { padding:11px 13px; font-size:13px; line-height:1.55; white-space:pre-wrap;
    overflow-y:auto; max-height:280px; color:var(--text-primary);
    font-family:'Literata',Georgia,serif; flex:1; }
  .mtext.diff ins { background:var(--success-subtle); text-decoration:none;
    color:var(--success); }
  .mtext.diff del { background:var(--danger-subtle); text-decoration:line-through;
    color:var(--danger); }
  .cfoot { display:flex; align-items:center; gap:10px; padding:12px 16px;
    border-top:1px solid var(--border); flex-wrap:wrap; }
  .cfoot .decbtn { padding:8px 16px; }
  .decbtn.confirm.on { background:var(--success); color:#fff; border-color:var(--success); }
  .decbtn.reject.on { background:var(--danger); color:#fff; border-color:var(--danger); }
  .note { flex:1; min-width:200px; font-family:'IBM Plex Mono',monospace;
    font-size:12px; padding:6px 10px; border:1px solid var(--border);
    border-radius:5px; background:var(--bg-primary); color:var(--text-primary); }
  .diff-toggle { font-size:11px; }
  .hidden { display:none !important; }
  footer { text-align:center; padding:30px; color:var(--text-muted); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>Laubmann · Duplicate Review</h1>
  <div class="counts">
    <span>total <b id="c-total">0</b></span>
    <span class="done">confirmed <b id="c-confirm">0</b></span>
    <span class="rej">rejected <b id="c-reject">0</b></span>
    <span>pending <b id="c-pending">0</b></span>
    <span>drops <b id="c-drops">0</b></span>
  </div>
  <div class="spacer"></div>
  <span id="autosave"></span>
  <button onclick="importSession()">Import</button>
  <button class="primary" onclick="exportDecisions()">Export decisions</button>
</header>
<div class="wrap">
  <div class="filters" id="filters">
    <button data-f="all" class="active">All</button>
    <button data-f="pending">Pending</button>
    <button data-f="confirm">Confirmed</button>
    <button data-f="reject">Rejected</button>
    <button data-f="high">Conf ≥ 0.80</button>
    <button data-f="review">Conf &lt; 0.80</button>
    <button data-f="containment">Containment</button>
    <button data-f="degenerate">Has degenerate</button>
  </div>
  <div id="clusters"></div>
</div>
<footer>Decisions auto-save to this browser. Export the JSON and hand it to apply_dedup.py.</footer>

<script>
const DATA = /*__DATA__*/;
const STORAGE_KEY = 'laubmann_dedup_review_v1';
const STRUCT_SIGS = new Set(['same_page_number','same_entry_dates','overlapping_entry_dates',
  'same_page_id_cross_volume','same_start','same_end','containment']);
let decisions = {};   // cluster_id -> {decision, keep, note}

function loadSession() {
  try { const r = localStorage.getItem(STORAGE_KEY);
        if (r) decisions = JSON.parse(r); } catch(e) {}
}
function autoSave() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
    const n = new Date(), p = x => String(x).padStart(2,'0');
    document.getElementById('autosave').textContent =
      'saved ' + p(n.getHours()) + ':' + p(n.getMinutes()) + ':' + p(n.getSeconds());
  } catch(e) { document.getElementById('autosave').textContent = 'save failed'; }
}
function defaultDecision(c) {
  return decisions[c.cluster_id] ||
    { decision:'', keep:c.suggested_keep, note:'' };
}

function tokenDiff(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  const dp = Array.from({length:n+1}, () => new Int32Array(m+1));
  for (let i=n-1;i>=0;i--) for (let j=m-1;j>=0;j--)
    dp[i][j] = A[i]===B[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j], dp[i][j+1]);
  let i=0,j=0,out='';
  const esc = s => s.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
  while (i<n && j<m) {
    if (A[i]===B[j]) { out+=esc(B[j]); i++; j++; }
    else if (dp[i+1][j] >= dp[i][j+1]) { out+='<del>'+esc(A[i])+'</del>'; i++; }
    else { out+='<ins>'+esc(B[j])+'</ins>'; j++; }
  }
  while (i<n) { out+='<del>'+esc(A[i++])+'</del>'; }
  while (j<m) { out+='<ins>'+esc(B[j++])+'</ins>'; }
  return out;
}

function render() {
  const root = document.getElementById('clusters');
  root.innerHTML = '';
  DATA.clusters.forEach(c => root.appendChild(renderCluster(c)));
  applyFilter(currentFilter);
  updateCounts();
}

function renderCluster(c) {
  const d = defaultDecision(c);
  const el = document.createElement('div');
  el.className = 'cluster' + (d.decision ? ' decided-'+d.decision : '');
  el.dataset.cid = c.cluster_id;
  el.dataset.conf = c.confidence;
  el.dataset.relation = c.relation;
  el.dataset.degenerate = c.members.some(m => (m.quality_flags||[]).length) ? '1':'0';

  const confClass = c.confidence>=0.80 ? 'hi' : (c.confidence<0.55?'lo':'');
  const sigs = c.signals.map(s =>
    `<span class="sig ${STRUCT_SIGS.has(s)?'struct':''}">${s}</span>`).join('');

  const n = c.members.length;
  const gridClass = n>=4 ? 'n4' : ('n'+n);
  const refText = (c.members.find(m=>m.page_uid===d.keep)||c.members[0]).text || '';

  const members = c.members.map(m => {
    const isKeep = m.page_uid === d.keep;
    const qflags = (m.quality_flags||[]);
    const qbadge = qflags.length ? `<span class="badge q" title="${qflags.join(', ')}">degenerate</span>` : '';
    const diffHtml = (m.text && refText && m.page_uid!==d.keep)
      ? tokenDiff(refText, m.text) : escapeHtml(m.text||'(no text on file)');
    return `
      <div class="member ${isKeep?'keep':''}" data-uid="${m.page_uid}">
        <div class="mhead">
          <span class="uid">${m.page_uid}</span>
          ${m.page_number?`<span class="badge pn">p.${escapeHtml(m.page_number)}</span>`:''}
          ${qbadge}
          <button class="keepbtn ${isKeep?'on':''}" onclick="setKeep('${c.cluster_id}','${m.page_uid}')">${isKeep?'★ keep':'keep'}</button>
        </div>
        <div class="mstats">
          <span>scan ${m.scan}${m.side?(' '+m.side):''}</span>
          <span>${m.n_regions} reg</span>
          <span>${m.n_entry_starts} entries</span>
          <span>${m.n_chars} ch</span>
        </div>
        <div class="mtext ${(m.page_uid!==d.keep && m.text)?'diff':''}">${diffHtml}</div>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="chead">
      <span class="cid">${c.cluster_id}</span>
      <span class="conf ${confClass}">${c.confidence.toFixed(3)}</span>
      <span class="relation">${c.relation}</span>
      <div class="signals">${sigs}</div>
    </div>
    <div class="members ${gridClass}">${members}</div>
    <div class="cfoot">
      <button class="decbtn confirm ${d.decision==='confirm'?'on':''}"
        onclick="setDecision('${c.cluster_id}','confirm')">✓ Confirm — drop others</button>
      <button class="decbtn reject ${d.decision==='reject'?'on':''}"
        onclick="setDecision('${c.cluster_id}','reject')">✗ Reject — keep all</button>
      <input class="note" placeholder="note (optional)" value="${escapeHtml(d.note||'')}"
        oninput="setNote('${c.cluster_id}', this.value)">
    </div>`;
  return el;
}

function escapeHtml(s){ return (s||'').replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function ensure(cid){ const c=DATA.clusters.find(x=>x.cluster_id===cid);
  if(!decisions[cid]) decisions[cid]={decision:'',keep:c.suggested_keep,note:''};
  return decisions[cid]; }
function setDecision(cid,val){ const d=ensure(cid);
  d.decision = d.decision===val ? '' : val; autoSave(); rerenderOne(cid); updateCounts(); }
function setKeep(cid,uid){ ensure(cid).keep=uid; autoSave(); rerenderOne(cid); }
function setNote(cid,val){ ensure(cid).note=val; autoSave(); }
function rerenderOne(cid){ const c=DATA.clusters.find(x=>x.cluster_id===cid);
  const old=document.querySelector(`.cluster[data-cid="${cid}"]`);
  const neu=renderCluster(c); old.replaceWith(neu);
  if(!matchFilter(neu,currentFilter)) neu.classList.add('hidden'); }

function updateCounts(){
  let conf=0,rej=0,drops=0;
  DATA.clusters.forEach(c=>{ const d=decisions[c.cluster_id];
    if(d&&d.decision==='confirm'){ conf++; drops += c.members.length-1; }
    else if(d&&d.decision==='reject') rej++; });
  document.getElementById('c-total').textContent=DATA.clusters.length;
  document.getElementById('c-confirm').textContent=conf;
  document.getElementById('c-reject').textContent=rej;
  document.getElementById('c-pending').textContent=DATA.clusters.length-conf-rej;
  document.getElementById('c-drops').textContent=drops;
}

let currentFilter='all';
function matchFilter(el,f){
  const cid=el.dataset.cid, d=decisions[cid]||{}, conf=parseFloat(el.dataset.conf);
  switch(f){
    case 'all': return true;
    case 'pending': return !d.decision;
    case 'confirm': return d.decision==='confirm';
    case 'reject': return d.decision==='reject';
    case 'high': return conf>=0.80;
    case 'review': return conf<0.80;
    case 'containment': return el.dataset.relation==='containment';
    case 'degenerate': return el.dataset.degenerate==='1';
  }
  return true;
}
function applyFilter(f){ currentFilter=f;
  document.querySelectorAll('#filters button').forEach(b=>
    b.classList.toggle('active', b.dataset.f===f));
  document.querySelectorAll('.cluster').forEach(el=>
    el.classList.toggle('hidden', !matchFilter(el,f))); }
document.getElementById('filters').addEventListener('click',e=>{
  if(e.target.dataset.f) applyFilter(e.target.dataset.f); });

function exportDecisions(){
  const out={ generated:new Date().toISOString(), schema:'laubmann_dedup_decisions_v1',
    decisions:[] };
  DATA.clusters.forEach(c=>{ const d=decisions[c.cluster_id];
    if(!d||!d.decision) return;
    out.decisions.push({ cluster_id:c.cluster_id, decision:d.decision,
      keep:d.keep, drop:d.decision==='confirm'
        ? c.members.map(m=>m.page_uid).filter(u=>u!==d.keep) : [],
      relation:c.relation, confidence:c.confidence, note:d.note||'' }); });
  const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='dedup_decisions.json'; a.click(); URL.revokeObjectURL(a.href);
}
function importSession(){
  const inp=document.createElement('input'); inp.type='file'; inp.accept='.json';
  inp.onchange=e=>{ const f=e.target.files[0]; if(!f) return;
    const r=new FileReader(); r.onload=()=>{ try{
      const obj=JSON.parse(r.result);
      (obj.decisions||[]).forEach(d=>{ decisions[d.cluster_id]=
        {decision:d.decision,keep:d.keep,note:d.note||''}; });
      autoSave(); render(); }catch(err){ alert('Bad file: '+err); } };
    r.readAsText(f); };
  inp.click();
}

loadSession(); render();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report_jsonl", type=Path)
    ap.add_argument("--corpus", type=Path, default=None,
                    help="corpus.json for full region text in the diff view")
    ap.add_argument("-o", "--out", type=Path, default=Path("review.html"))
    args = ap.parse_args()

    data = build_data(args.report_jsonl, args.corpus)
    args.out.write_text(generate_html(data), encoding="utf-8")
    n = len(data["clusters"])
    kb = args.out.stat().st_size / 1024
    print(f"→ {args.out} ({n} clusters, {kb:.0f} KB)")


if __name__ == "__main__":
    main()
