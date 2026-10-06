/* Graph-Prüfung — start: review layer, stored decisions, queues, event wiring of the review modules.
   This file closes the function scope opened in gc_explorer.js. */

async function rvBoot() {
  if (EXPLORER) $$('.rv-only').forEach(el => el.remove());   // reviewer name, progress, save / load: not part of the explorer build
  await loadReview();
  if (EXPLORER) xBoot();
  if ((R.meta || {}).mode && R.meta.mode !== GC_META.mode) console.warn('review layer built for mode', R.meta.mode);
  loadState();
  mediaIndex();
  buildSummaries();
  qfIndex();
  countQueues();
  if (!queueList().includes(RVU.queue) || !(RVU.counts[RVU.queue] || {}).n) RVU.queue = EXPLORER ? 'all' : QUEUES.find(q => RVU.counts[q].n) || 'all';
  renderVolSelect(); renderChips();
  RVU.list = listRows(); RVU.listPos = new Map(RVU.list.map((r, i) => [r.n, i])); $('#elist-body').dataset.lang = '';
}
function rvWire() {
  scanWire(); mediaWire(); archiveWire(); if (EXPLORER) xWire();
  $('#pbody').addEventListener('click', rvPanelClick);
  $('#pbody').addEventListener('mousedown', ev => { if (ev.target.closest('[data-act="txtedit"]')) ev.preventDefault(); });   // keep the text selection
  $('#rtable').addEventListener('click', tableClick);
  if (!EXPLORER) {
    $('#who').addEventListener('input', debounce(ev => { RV.who = ev.target.value.trim(); saveSoon(); }, 300));
    $('#btn-save').addEventListener('click', showExport);
    $('#btn-load').addEventListener('click', () => $('#fileImport').click());
    $('#fileImport').addEventListener('change', ev => { const f = ev.target.files[0]; ev.target.value = ''; if (f) importFile(f); });
  }
  $('#modalbg').addEventListener('click', modalClick);
  if (!EXPLORER) window.addEventListener('beforeunload', ev => { try { localStorage.setItem(LS_STATE, JSON.stringify(RV)); } catch (e) { /* stored at the last decision */ } if (RVU.lsFail && dirtyN) { ev.preventDefault(); ev.returnValue = ''; } });
  window.LKGC = window.LKGX;
  Object.assign(window.LKGC, { R, RV, RVU, RVS, SC, QUEUES, entryModel, buildModel, visibleItems, entCur, entProposal, makeZip, exportFiles, auditRows, importState, setQueue, decide, undo, cardAct, focusCard, countQueues, progressJSON,
    go, entryHash, proposal, mergedProposal, recVals, listRows, t, UI, MEDIA, cropErr, cutErr, cropSources, openCrop, closeCrop, selectMedia, scanMediaAt,
    SEV, QF, Q_MEASURES, LEVELS, openLevels, openByLevel, levelTotals, setQFilter, qfApply, qfName, qOf, qPass, setLevelFilter, setPreset, sevDoc, tableCols, nodeProps, stats, itemLevel, inCorpus, openFindings, itemDecided, usageRows, propMode, entryInCorpus, setNotes, queueList, META: GC_META, EXPLORER,
    pageErr, pageLoaded, openPage, pageRegions, pageIndex, regionBox, scanSources, pageEntries, regionEntries, thumbsSync, ARCH, pageNode, regionNode, pageTitle, kindOf, betterOf,
    xNames, xChanges, xChangeSteps, xDate, xRecordRows, label, Z });
  Object.defineProperty(window.LKGC, 'SUB', { get: () => SUB });
  Object.defineProperty(window.LKGC, 'EM', { get: () => EM });
  Object.defineProperty(window.LKGC, 'LANG', { get: () => LANG });
}
boot();
})();
