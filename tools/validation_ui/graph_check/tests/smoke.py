"""Smoke test: the page loads fast, every queue lists entries, an entry with findings renders its cards,
annotated graph, records table, scan overlay and all tabs; DE/EN without untranslated keys; the properties
layer and its presets, the table's columns, the gravity levels (pills, order, filter, rules) and the corpus
filter (counts, work list, entry, node view, overview) with its always visible bar; the explorer's other
views still work; no page errors. Works without any scan image. Then the EXPLORER BUILD of the same app
(--mode explorer): the same entry shows the same nodes, property rows, annotations, cards, table columns
and scan overlays as the review build, the corpus bar filters the views, and no decision control exists."""
import asyncio
import re
import time
from playwright.async_api import async_playwright
from common import EXPLORER_PAGE, SHOTS, check, done, find_entry, goto_entry, open_page, reload

# raw i18n keys that would show up if a string were missing
KEYPAT = re.compile(r"\b(?:q|qt|g|a|d|c|f|tip|lg|ov|ex|im|tck|tcv|nk|ak|as|src|hint|mk|bt|tl|txt|row|link|prec|ins|scan|sort|chk|agree|name|names|finish|err|crop|media|mkind"
                    r"|lv|lvf|lvk|lvt|sd|corp|tier|tw|cols|col|props|prop|pm|preset|out|pan|sec|hints|open|head|help|grp|filter|sev)_[a-z][a-z_-]*\b")
QUEUES = ["finding", "auto", "tc", "ins", "img", "qa", "sample", "all", "done"]
CASES = {   # card type -> predicate on (review entry, summary)
    "rec": "(rv, s) => s.find.length > 0 && Object.keys(rv.rec || {}).length < 25",
    "rec-both": "(rv) => Object.values(rv.rec || {}).some(r => r.g && r.s && r.g.v !== 'ok' && r.s.v !== 'ok')",
    "miss": "(rv, s) => s.miss.length > 0 && Object.keys(rv.rec || {}).length < 25",
    "name": "(rv, s) => s.auto.some(k => k.startsWith('name:')) && Object.keys(rv.rec || {}).length < 25",
    "tc": "(rv, s) => s.tc.length > 0 && (rv.tc || []).some(c => c[2] && c[3] >= 0 && c[5])",
    "ent": "(rv) => rv.ent && (rv.ent.g || rv.ent.s)",
    "qa": "(rv) => (rv.gone || []).some(g => g[0] === 'non_bird')",
    "media": "(rv, s) => s.unread > 0",
    "img": "(rv, s) => s.img >= 2 && (rv.media || []).filter(x => x.length >= 7).length >= 2 && (rv.reg || []).some(g => g[0] === rv.media.find(x => x.length >= 7)[2])",
}


async def img_checks(pg, lang):
    """The multimodal regions of an entry: cards with crops, large view, outlines on the scan, node tab."""
    n_media = await pg.evaluate("LKGC.EM.rv.media.length")
    check(await pg.locator("#pbody .rcard.t-media .mthumb").count() == n_media, f"[{lang}] every region of the entry has a card with its crop ({n_media})")
    first = await pg.evaluate("(() => { const items = LKGC.visibleItems(LKGC.EM); const i = items.findIndex(it => it.type === 'media' && it.x.length >= 7); LKGC.focusCard(i); return items[i].x; })()")
    await pg.wait_for_timeout(700)
    check(await pg.locator("#pbody .rcard.t-media.focus img.crop.thumb").count() == 1 and await pg.evaluate("(i => i.complete && i.naturalWidth > 0)(document.querySelector('#pbody .rcard.t-media.focus img.crop.thumb'))"),
          f"[{lang}] the crop loads from the local folder when Drive is not reachable")
    check(await pg.locator("#pbody .rcard.t-media.focus .rc-body").inner_text() != "", f"[{lang}] the card shows description or visible text of the region")
    check(await pg.locator("#scanov rect.mreg.on").count() == 1, f"[{lang}] selecting a media card highlights its box on the scan")
    check(await pg.evaluate(f"LKGC.SC.pages[LKGC.SC.pi].idx === {first[2]}"), f"[{lang}] ... on the region's page")
    n_out = await pg.locator("#scanov rect.mreg").count()
    await pg.click('#scanbar [data-sc="media"]')
    check(await pg.locator("#scanov rect.mreg").count() == 1 and n_out >= 1, f"[{lang}] the toggle hides the outlines (the selected one stays)")
    await pg.click('#scanbar [data-sc="media"]')
    check(await pg.locator("#scanov rect.mreg").count() == n_out, f"[{lang}] ... and shows them again")
    # a click on an outline selects the card
    await pg.evaluate("LKGC.focusCard(LKGC.visibleItems(LKGC.EM).findIndex(it => it.type === 'ent'))")      # another card; then back to the region's page, whole page
    await pg.click(f'#scanbar [data-sc="p{await pg.evaluate(f"LKGC.SC.pages.findIndex(p => p.idx === {first[2]})")}"]')
    await pg.click('#scanbar [data-sc="page"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator("#scanov rect.mreg.on").count() == 0 and await pg.locator("#scanov rect.mreg").count() >= 1, f"[{lang}] the outlines of the entry's regions are drawn on their page")
    pt = await pg.evaluate(f"(() => {{ const x = {first}; const r = document.querySelector('#scanview').getBoundingClientRect(); const S = LKGC.SC; return [r.left + S.x + (x[3] + x[5]) / 2 * S.W * S.k, r.top + S.y + (x[4] + x[6]) / 2 * S.H * S.k]; }})()")
    await pg.mouse.click(pt[0], pt[1])
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("(it => it && it.type === 'media')(LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card])") and await pg.locator("#pbody .rcard.t-media.focus").count() == 1, f"[{lang}] a click on an outline selects the region's card")
    # large view: opens, zooms, Esc closes
    await pg.click("#pbody .rcard.t-media.focus .mthumb")
    await pg.wait_for_timeout(500)
    check(await pg.locator("#lightbox").is_visible() and await pg.locator("#lightbox img.crop.big, #lightbox .cutout").count() == 1, f"[{lang}] a click on the crop opens the large view")
    before = await pg.evaluate("document.querySelector('#lightbox .lb-stage').style.transform")
    await pg.mouse.move(720, 480)
    await pg.mouse.wheel(0, -300)
    await pg.wait_for_timeout(150)
    check(await pg.evaluate("document.querySelector('#lightbox .lb-stage').style.transform") != before, f"[{lang}] the wheel zooms the large view")
    await pg.keyboard.press("j")
    check(await pg.locator("#pbody .rform").count() == 0, f"[{lang}] keys do not reach the cards while the large view is open")
    await pg.keyboard.press("Escape")
    check(not await pg.locator("#lightbox").is_visible(), f"[{lang}] Esc closes the large view")
    # node tab and node view of the region node
    node = await pg.evaluate(f"LKGC.G.nodes[LKGC.G.N.get('data:region_' + {first[0]!r})]")
    await pg.click('#ptabs [data-tab="node"]')
    await pg.wait_for_timeout(250)
    check(await pg.locator("#pbody .nodecrop").count() == 1, f"[{lang}] the node tab of a multimodal region shows its crop")
    await pg.evaluate(f"LKGC.go('/n/' + {node!r})")
    await pg.wait_for_timeout(500)
    check(await pg.locator("#v-node .nodecrop").count() == 1, f"[{lang}] the node view of a multimodal region shows its crop")

# ---------------------------------------------------------------------------------------------------------------
# final pass: properties layer and presets, table columns, gravity levels, corpus filter

# every outgoing triple of every drawn node is a row of its box or (node-valued, with `links`) an edge / "→" row
JS_COVER = """(links) => { const S = LKGC.SUB, G = LKGC.G; const E = new Set(); for (const ed of S.E) { E.add(ed.a.key + '|' + ed.b.key); E.add(ed.b.key + '|' + ed.a.key); }
  const NAME = new Set(['rdfs:label', 'skos:prefLabel', 'schema:name', 'dwc:scientificName']); const miss = []; let n = 0, nodes = 0;
  for (const v of S.V.values()) { if (v.n < 0 || v.kind === 'group' || v.kind === 'ghead') continue; nodes++; const props = v.props || [];
    const lit = new Set(props.filter(p => !p.link).map(p => p.p)), lk = new Set(props.filter(p => p.link).map(p => p.p));
    for (let i = G.sOff[v.n]; i < G.sOff[v.n + 1]; i++) { const p = G.preds[G.tP[i]], o = G.tO[i]; n++;
      if (o < 0) { if (!lit.has(p) && !NAME.has(p)) miss.push([v.key, p]); }
      else if (links && !lk.has(p) && !E.has(v.key + '|n' + o)) miss.push([v.key, p, o]); } }
  return { n, nodes, miss: miss.length, first: miss.slice(0, 6) }; }"""
JS_LEVEL_SORTED = """(l => l.every((r, i) => { if (!i) return true; const a = LKGC.openLevels(LKGC.RVS.get(l[i - 1].n)), b = LKGC.openLevels(LKGC.RVS.get(r.n));
  return a[3] > b[3] || (a[3] === b[3] && (a[2] > b[2] || (a[2] === b[2] && a[1] >= b[1]))); }))(LKGC.RVU.list.slice(0, 600))"""
JS_CORPUS_COUNT = """(c) => { let n = 0, e = 0; for (const r of LKGC.G.ent) { const rv = LKGC.R.entries[r.id] || {}; const flat = LKGC.R.obs[r.id] || []; let k = 0;
  for (let i = 0; i < flat.length; i += 3) { const rec = (rv.rec || {})[flat[i + 1]]; if (((rec && rec.t) || 0) >= c) k++; } n += k; if (k) e++; } return [n, e]; }"""
FINAL_COUNTS = [85631, 74909, 69150, 44372]      # the final build (9,901 entries): full, core, strict core, strict core with coordinates


async def show_hints(pg):
    """Expand the collapsed level-0 cards of the check tab."""
    await pg.evaluate("(() => { if (!LKGC.RVU.hints) { const a = document.querySelector('#pbody [data-act=hints]'); if (a) a.click(); } })()")
    await pg.wait_for_timeout(120)


async def props_checks(pg):
    eid = await find_entry(pg, "(rv, s, r) => r.nobs >= 4 && r.nobs <= 10 && (rv.reg || []).length > 0 && Object.values(rv.rec || {}).some(x => x.g && x.g.v === 'wrong' && x.g.fix && x.g.fix.locality && x.g.fix.count)")
    await goto_entry(pg, eid)
    check(await pg.evaluate("LKGC.S.layers.props === true && LKGC.S.layers.links === false"), "the layer 'Eigenschaften' is on by default")
    check(await pg.locator("#gsvg text.pr").count() > 20, f"property rows are written into the node boxes ({eid})")
    cov = await pg.evaluate(JS_COVER, False)
    check(cov["miss"] == 0 and cov["n"] > 50, f"every literal statement of every drawn node is a row ({cov['n']} triples of {cov['nodes']} nodes; missing {cov['first']})")
    rows = await pg.evaluate("(() => { const v = [...LKGC.SUB.V.values()].find(v => v.kind === 'obs'); return v.props.map(r => [r.p, r.k]); })()")
    check(any(p == "lkg:verbatimNotes" for p, _ in rows) and all(k and k != p for p, k in rows), f"the rows carry the ontology labels ({len(rows)} rows of a record)")
    check(await pg.locator("#gsvg .nd.k-obs .tpill").count() == await pg.locator("#gsvg .nd.k-obs").count(), "every record node shows its corpus tier (K0–K3)")
    # compact: one line per node, all rows on the selected node, all rows in the tooltip
    await pg.select_option("#propsel", "compact")
    await pg.wait_for_timeout(250)
    st = await pg.evaluate("(() => { const vs = [...LKGC.SUB.V.values()].filter(v => v.kind === 'obs'); return { one: vs.filter(v => v.key !== LKGC.S.sel).every(v => v.rows.length === 1), sel: (vs.find(v => v.key === LKGC.S.sel) || { rows: [] }).rows.length, other: (vs.find(v => v.key !== LKGC.S.sel) || {}).key }; })()")
    check(st["one"] and st["sel"] > 2, f"compact: one summary line per record, the selected record keeps its rows ({st['sel']})")
    await pg.hover(f'#gsvg .nd[data-key="{st["other"]}"] rect.b')
    await pg.wait_for_timeout(150)
    check(await pg.locator("#gtip table.tipprops tr").count() > 2, "compact: the tooltip of a record lists all its rows")
    await pg.click(f'#gsvg .nd[data-key="{st["other"]}"] rect.b')
    await pg.wait_for_timeout(250)
    check(await pg.evaluate(f"LKGC.SUB.V.get({st['other']!r}).rows.length") > 2, "compact: selecting a record opens its rows")
    await pg.select_option("#propsel", "all")
    await pg.wait_for_timeout(200)
    n_rows = await pg.locator("#gsvg text.pr").count()
    more = pg.locator("#gsvg rect.pmore")
    if await more.count():
        await more.first.click(force=True)
        await pg.wait_for_timeout(250)
        check(await pg.locator("#gsvg text.pr").count() > n_rows, "a long value expands on click")
    await pg.select_option("#propsel", "auto")
    # the chip switches the layer off and on
    await pg.click('#gtools .chip[data-layer="props"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator("#gsvg text.pr").count() == 0 and await pg.locator("#propsel").count() == 0, "the chip 'Eigenschaften' switches the rows off")
    await pg.click('#gtools .chip[data-layer="props"]')
    await pg.wait_for_timeout(200)
    # presets
    await pg.click('#gtools [data-act="preset-all"]')
    await pg.wait_for_timeout(350)
    check(await pg.evaluate("Object.values(LKGC.S.layers).every(Boolean)"), "'Alles zeigen' switches every layer on")
    check(await pg.locator("#gsvg .nd.k-page").count() > 0 and await pg.locator("#gsvg .nd.k-region, #gsvg .nd.k-mmregion").count() > 0 and await pg.locator("#gsvg .nd.k-volume").count() > 0, "... archive with pages, regions and the volume is drawn")
    cov = await pg.evaluate(JS_COVER, True)
    check(cov["miss"] == 0 and cov["n"] > 100, f"'Alles zeigen': every triple of every drawn node is an edge or a row ({cov['n']} triples of {cov['nodes']} nodes; missing {cov['first']})")
    reach = await pg.evaluate("(() => { const G = LKGC.G, e = LKGC.S.e; let miss = 0, n = 0; for (let i = G.sOff[e]; i < G.sOff[e + 1]; i++) { const o = G.tO[i]; if (o < 0) continue; n++; if (!LKGC.SUB.V.has('n' + o) && !LKGC.SUB.V.get('n' + e).props.some(p => p.link && p.p === G.preds[G.tP[i]])) miss++; } return [n, miss]; })()")
    check(reach[1] == 0, f"... every node the entry points to is drawn or named in its box ({reach[0]} statements)")
    await pg.screenshot(path=str(SHOTS / "smoke_all_layers.png"))
    await pg.click('#gtools [data-act="preset-std"]')
    await pg.wait_for_timeout(300)
    check(await pg.evaluate("(l => l.records && l.taxa && l.places && l.persons && l.habitats && l.props && !l.archive && !l.authorities && !l.provenance && !l.links)(LKGC.S.layers)"), "'Standard' returns to the default layers")
    return eid


async def table_checks(pg, eid):
    await goto_entry(pg, eid)
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(300)
    cols = await pg.evaluate("LKGC.tableCols(LKGC.EM).map(c => ({ id: c.id, on: c.on, n: c.n, def: c.def, chip: !!c.chip }))")
    ths = await pg.evaluate("[...document.querySelectorAll('#rtable th[data-col]')].map(th => th.dataset.col)")
    check(ths == [c["id"] for c in cols if c["on"]] and len(ths) >= 12, f"the table shows {len(ths)} of {len(cols)} columns")
    check(all(c["on"] for c in cols if c["n"] > 0) and all(c["on"] == c["def"] for c in cols), "default: every column with a value in this entry")
    preds = await pg.evaluate("(() => { const G = LKGC.G; const s = new Set(); for (const o of LKGC.EM.obs) for (let i = G.sOff[o.n]; i < G.sOff[o.n + 1]; i++) s.add(G.preds[G.tP[i]] + (G.tO[i] < 0 ? '' : '>')); return [...s]; })()")
    covered = {"dwc:eventDate", "dwciri:recordedBy>", "lkg:recordType", "dwc:sex", "dwc:lifeStage", "lkg:breedingEvidence", "dwc:occurrenceStatus", "dwc:verbatimLocality"}
    ids = {c["id"] for c in cols}
    check(all(("p:" + p) in ids or p in covered for p in preds), f"every predicate of the entry's records has a column ({len(preds)} predicates)")
    check(await pg.evaluate("(td => getComputedStyle(td).position === 'sticky')(document.querySelector('#rtable td.c-species'))"), "the first column is sticky")
    check(await pg.evaluate("(b => b.scrollWidth > b.clientWidth + 100)(document.querySelector('#rtable'))"), "the table scrolls horizontally")
    check(await pg.locator("#rtable td.c-tier .trc").count() == await pg.locator("#rtable tr[data-o]").count(), "every row shows the corpus tier of its record")
    chips = await pg.evaluate("[...document.querySelectorAll('#rtable .pchip[data-acc]')].map(c => [c.dataset.acc.split('|')[0], c.closest('td').dataset.f])")
    check(len(chips) > 0 and all(f == td or (f == 'georef' and td == 'locality') or (f == 'drop' and td == 'species') for f, td in chips), f"finding chips stay in the cell of their field ({len(chips)})")
    # column chooser
    await pg.click('#gtools [data-act="cols"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator("#colpop label").count() == len(cols), "the column chooser lists every column")
    await pg.screenshot(path=str(SHOTS / "smoke_table.png"))
    await pg.uncheck('#colpop input[data-col="p:lkg:verbatimNotes"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator('#rtable th[data-col="p:lkg:verbatimNotes"]').count() == 0, "unchecking a column hides it")
    await pg.click('#colpop [data-cp="all"]')
    await pg.wait_for_timeout(250)
    check(await pg.locator("#rtable th[data-col]").count() == len(cols), "'alle' shows every column")
    await pg.click('#colpop [data-cp="def"]')
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("[...document.querySelectorAll('#rtable th[data-col]')].map(th => th.dataset.col)") == ths, "'Standard' returns to the default columns")
    await pg.click('#colpop [data-cp="close"]')
    check(await pg.locator("#colpop").count() == 0, "the chooser closes")
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(200)


async def severity_checks(pg):
    sev = await pg.evaluate("LKGC.SEV")
    f = sev["rec"]["field"]
    check(sev["rec"]["spurious"] == 3 and f["species"] == 3 and f["status"] == 3 and all(f[k] == 2 for k in ("count", "date", "locality", "observer", "record_type"))
          and all(f[k] == 1 for k in ("georef", "place", "sex", "life_stage", "breeding", "evidence", "call", "behav", "notes", "other")) and sev["rec"]["unsure"] == 1
          and sev["rec"]["both"] == 1 and sev["rec"]["lowConf"] == 0.8 and sev["rec"]["lowConfDelta"] == -1, "rules: record findings by their gravest field, +1 for both checks, −1 below 0.8")
    check(sev["miss"] == {"observation": 2, "other": 1} and sev["ent"] == {"date": 3, "place": 2, "kind": 1} and sev["auto"] == {"species": 2, "dropped": 2, "field": 1}
          and sev["name"]["taxa"]["relinked"] == 2 and sev["name"]["taxa"]["removed"] == 2 and sev["name"]["taxa"]["linked"] == 1 and sev["name"]["places"] == {"moved": 1, "removed": 1, "linked": 0}
          and sev["name"]["confirmed"] == 0 and sev["tc"] == {"birdOrNumber": 2, "place": 1, "other": 0} and sev["qa"]["transcript_illegible"] == 2 and sev["qa"]["non_bird"] == 1 and sev["qa"]["other"] == 0
          and sev["ins"] == {"unread": 2, "partly": 1, "other": 0}, "rules: missing, entry header, names, value corrections, reading corrections, QA, inserts")
    lv = await pg.evaluate("""(() => { const f = (g, s) => { const m = LKGC.buildModel(LKGC.G.ent[0].n); return LKGC.itemLevel(m, { type: 'rec', o: { rec: { g, s } } }); };
      return [f({ v: 'spurious', c: .9 }), f({ v: 'wrong', f: ['species'], c: .95 }), f({ v: 'wrong', f: ['count', 'sex'], c: .9 }), f({ v: 'wrong', f: ['georef'], c: .9 }), f({ v: 'wrong', f: ['count'], c: .7 }),
        f({ v: 'wrong', f: ['count'], c: .9 }, { v: 'wrong', f: ['sex'], c: .9 }), f({ v: 'wrong', f: ['sex'], c: .5 }), f({ v: 'unsure' }), f({ v: 'ok' }), f({ v: 'wrong', f: ['species'], c: .9 }, { v: 'spurious', c: .9 })]; })()""")
    check(lv == [3, 3, 2, 1, 1, 3, 1, 1, 0, 3], f"record levels: spurious 3, species 3, count 2, georef 1, count at 0.7 → 1, both checks +1, floor 1, unsure 1, ok 0, cap 3 ({lv})")
    # work list: pills, default order, level chips combined with a queue
    await pg.evaluate("LKGC.setQueue('all', false)")
    await pg.select_option("#qsort", "score")
    await pg.wait_for_timeout(250)
    check(await pg.evaluate(JS_LEVEL_SORTED), "default order: most open schwer, then mittel, then leicht")
    await pg.evaluate("document.querySelector('#elist-body').scrollTop = 0")
    await pg.wait_for_timeout(200)
    rows_bad = await pg.evaluate("""[...document.querySelectorAll('#elist-pad .erow')].slice(0, 12).map(row => { const c = LKGC.openLevels(LKGC.RVS.get(+row.dataset.e));
      return [3, 2, 1].every(lv => { const p = row.querySelector('.lvp.lv' + lv); return c[lv] ? !!p && parseInt(p.textContent.replace(/[^0-9]/g, '')) === c[lv] : !p; }) ? null : [row.dataset.e, c, row.querySelector('.b').innerText]; }).filter(Boolean)""")
    check(not rows_bad and await pg.locator("#elist-pad .erow .lvp.lv3").count() > 0, f"list rows show the open findings per level as pills (red, orange, amber) {rows_bad[:3]}")
    check(await pg.locator("#elist-pad .erow .b-err, #elist-pad .erow .b-auto, #elist-pad .erow .b-tc").count() == 0, "... instead of the three old badges")
    await pg.screenshot(path=str(SHOTS / "smoke_list_levels.png"))
    n_all = await pg.evaluate("LKGC.RVU.list.length")
    want = await pg.evaluate("[3, 2, 1].map(lv => [...LKGC.RVS.values()].filter(s => LKGC.openLevels(s)[lv] > 0).length)")
    shown = await pg.evaluate("[3, 2, 1].map(lv => document.querySelector('#lvchips [data-lv=\"' + lv + '\"] .num').textContent.replace(/\\D/g, '')).map(Number)")
    check(shown == want and all(want), f"level chips count the entries with open findings: schwer {want[0]}, mittel {want[1]}, leicht {want[2]}")
    await pg.click('#lvchips [data-lv="3"]')
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("LKGC.RVU.list.length") == want[0] and await pg.evaluate("LKGC.RVU.list.every(r => LKGC.openLevels(LKGC.RVS.get(r.n))[3] > 0)"), "chip 'schwer' lists only entries with open severe findings")
    await pg.click('#lvchips [data-lv="1"]')
    await pg.wait_for_timeout(250)
    n_u = await pg.evaluate("LKGC.RVU.list.length")
    check(want[0] < n_u < n_all and await pg.evaluate("LKGC.RVU.list.every(r => (c => c[3] > 0 || c[1] > 0)(LKGC.openLevels(LKGC.RVS.get(r.n))))"), f"chips combine (schwer or leicht: {n_u})")
    await pg.click('#lvchips [data-lv="1"]')
    await pg.evaluate("LKGC.setQueue('tc', false)")
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("LKGC.RVU.list.length > 0 && LKGC.RVU.list.every(r => (s => s.tc.length > 0 && LKGC.openLevels(s)[3] > 0)(LKGC.RVS.get(r.n)))"), "a level chip combines with the queue")
    await pg.click('#lvchips [data-lv="0"]')
    await pg.wait_for_timeout(200)
    check(await pg.evaluate("LKGC.RVU.lvf.size") == 0 and await pg.evaluate("LKGC.RVU.list.length") == await pg.evaluate("LKGC.RVU.counts.tc.n"), "× clears the level filter")
    await pg.evaluate("LKGC.setQueue('finding', false)")
    tot = await pg.evaluate("(() => { const t = LKGC.levelTotals(); const s = [0, 0, 0, 0]; for (const k in t) for (let i = 1; i < 4; i++) s[i] += t[k][i]; const e = [0, 0, 0, 0]; for (const x of LKGC.RVS.values()) { const c = LKGC.openLevels(x); for (let i = 1; i < 4; i++) e[i] += c[i]; } return [s, e, t]; })()")
    check(tot[0] == tot[1] and tot[0][3] > 0, f"open findings per level: schwer {tot[0][3]}, mittel {tot[0][2]}, leicht {tot[0][1]}")
    print("open findings per kind [_, leicht, mittel, schwer]:", tot[2])
    same = await pg.evaluate("(() => { let bad = 0, n = 0; for (const r of LKGC.G.ent) { if (n++ % 9) continue; const a = LKGC.openLevels(LKGC.RVS.get(r.n)), b = LKGC.openByLevel(LKGC.buildModel(r.n)); if (a[1] !== b[1] || a[2] !== b[2] || a[3] !== b[3]) bad++; } return bad; })()")
    check(same == 0, "the list's counts per level equal the cards of the entry (every 9th entry)")
    # one entry: head, order of the check tab, hints collapsed, node rings, a decision takes the item out of the counts
    eid = await find_entry(pg, "(rv, s, r) => { const c = LKGC.openLevels(s); return c[3] >= 1 && c[2] >= 1 && c[1] >= 1 && r.nobs <= 14 && s.find.length >= 2 && new Set(s.lv.map(x => x[2])).size >= 3 && (rv.tc || []).some(c => !c[5]); }")
    await goto_entry(pg, eid)
    c = await pg.evaluate("LKGC.openByLevel(LKGC.EM)")
    head = await pg.evaluate("[...document.querySelectorAll('#ehead .hstate .lvp')].map(p => [[...p.classList].find(x => /^lv\\d$/.test(x)), parseInt(p.textContent)])")
    check(head == [[f"lv{l}", c[l]] for l in (3, 2, 1) if c[l]], f"the entry head splits the open findings by level ({eid}: {head})")
    secs = await pg.evaluate("[...document.querySelectorAll('#pbody h3.lvh .lvd')].map(d => [...d.classList].find(x => /^lv\\d$/.test(x)))")
    check(secs == ["lv3", "lv2", "lv1", "lv0"], f"the check tab lists by level, gravest first, hints last ({secs})")
    order = await pg.evaluate("[...document.querySelectorAll('#pbody .rcard[data-ci]')].map(c => [...c.classList].find(x => /^lv[\\dx]$/.test(x)))")
    lvls = [int(x[2]) for x in order if x and x[2].isdigit() and int(x[2]) >= 1]
    check(lvls == sorted(lvls, reverse=True) and len(lvls) >= 3, f"cards stand in the order schwer, mittel, leicht ({lvls})")
    n0 = await pg.evaluate("LKGC.EM.items.filter(it => it.sec === 'hint').length")
    check(n0 > 0 and await pg.locator("#pbody .rcard.t-tc.lv0, #pbody .rcard.t-name.lv0, #pbody .rcard.t-qa.lv0").count() == 0 and await pg.locator("#pbody [data-act=hints]").count() == 1, f"hints (level 0) are collapsed: + {n0}")
    check((await pg.evaluate("document.querySelector('#ehead .hstate .hh').textContent")).strip().startswith("+"), "... and counted apart in the head")
    await show_hints(pg)
    check(await pg.locator("#pbody .rcard.lv0").count() >= n0, "the link shows them")
    rings = await pg.evaluate("(() => { let ok = 0, bad = 0; for (const it of LKGC.EM.items) { if (it.type !== 'rec' || !it.lv) continue; const el = document.querySelector('#gsvg .nd[data-key=\"n' + it.o.n + '\"]'); if (!el) continue; if (el.classList.contains('an-lv' + it.lv) && el.querySelector('.ring.lv' + it.lv) && el.querySelector('.abadge.lv' + it.lv)) ok++; else bad++; } return [ok, bad]; })()")
    check(rings[0] > 0 and rings[1] == 0, f"node ring and badge carry the level colour ({rings[0]} records)")
    marks = await pg.evaluate("[...new Set([...document.querySelectorAll('#pbody .rcard .mkp')].map(m => m.textContent))].sort().join('')")
    check("!" in marks and "M" in marks, f"the marker of a card says the kind of flag ({marks})")
    check(await pg.locator("#legend .lvd").count() == 4 and await pg.locator("#legend .mk").count() == 5, "the legend explains colour (four levels) and marker (five kinds)")
    await pg.evaluate("LKGC.focusCard(0)")
    await pg.keyboard.press("n")
    await pg.wait_for_timeout(400)
    c2 = await pg.evaluate("LKGC.openByLevel(LKGC.EM)")
    s2 = await pg.evaluate("LKGC.openLevels(LKGC.RVS.get(LKGC.S.e))")
    check(sum(c2[1:]) == sum(c[1:]) - 1 and s2[1:] == c2[1:], f"a decided item no longer counts ({c[1:]} → {c2[1:]})")
    check(await pg.locator("#pbody .rcard.done .mkp.dec").count() == 1, "... its card carries the green tick")
    pill = await pg.evaluate("(row => [3, 2, 1].map(lv => (p => p ? parseInt(p.textContent) : 0)(row.querySelector('.lvp.lv' + lv))))(document.querySelector('#elist-pad .erow.on'))")
    check(pill == [c2[3], c2[2], c2[1]], "... and the pills of the list row follow")
    await pg.keyboard.press("z")
    await pg.wait_for_timeout(300)
    check(await pg.evaluate("LKGC.openByLevel(LKGC.EM)") == c, "undo brings it back")
    # overview and help
    await pg.evaluate("LKGC.go('/')")
    await pg.wait_for_timeout(400)
    check(await pg.locator("#rv-ov table.lvt tr").count() == 11, "overview: open findings per level and per kind")
    check(await pg.locator("#rv-ov table.sevt tr").count() >= 30, "overview: the table of the rules")
    await pg.click("#btn-help")
    check(await pg.locator("#help table.sevt tr").count() >= 30, "help: the same table")
    await pg.click("#help h2")

JS_BAR = """[...document.querySelectorAll('#corpbar .cseg .cb')].map(b => ({ c: +b.dataset.corpus, name: b.querySelector('.cbn').textContent, n: b.querySelector('.cbc').textContent, on: b.classList.contains('on'),
  pressed: b.getAttribute('aria-pressed'), bg: getComputedStyle(b).backgroundColor, tip: b.title, vis: b.getBoundingClientRect().width > 20 }))"""
BAR_NAMES = ["Vollständig", "Kern", "Strenger Kern", "Strenger Kern mit Koordinaten"]


def de(n):
    return f"{n:,}".replace(",", ".")


async def corpus_bar_checks(pg, tag):
    """The corpus filter is an always visible segmented control directly under the header, in every view."""
    n = await pg.evaluate("LKGC.CORP.n")
    btns = await pg.evaluate(JS_BAR)
    check(len(btns) == 4 and [b["name"] for b in btns] == BAR_NAMES and [b["n"] for b in btns] == [de(x) for x in n] and all(b["vis"] for b in btns),
          f"[{tag}] the corpus bar has four labelled buttons with their record counts {[b['name'] + ' ' + b['n'] for b in btns]}")
    check((await pg.locator("#corpbar .cbl").inner_text()).strip().lower() == "korpus", f"[{tag}] ... with the leading label 'Korpus'")
    on = [b for b in btns if b["on"]]
    check(len(on) == 1 and on[0]["c"] == 0 and on[0]["pressed"] == "true" and all(b["bg"] != on[0]["bg"] for b in btns if not b["on"]), f"[{tag}] the active corpus is clearly filled ({on[0]['bg'] if on else '-'})")
    geo = await pg.evaluate("(() => { const h = document.querySelector('header#top').getBoundingClientRect(), b = document.querySelector('#corpbar').getBoundingClientRect(); return [Math.round(b.top - h.bottom), Math.round(b.height), Math.round(b.width), innerWidth]; })()")
    check(abs(geo[0]) <= 1 and 24 <= geo[1] <= 60 and geo[2] == geo[3], f"[{tag}] the bar is a row of its own directly under the header ({geo})")
    first = await pg.evaluate("LKGC.G.ent[0].id")
    tx = await pg.evaluate("LKGC.G.nodes[LKGC.stats().taxa[0].n]")
    for name, h in (("overview", "/"), ("entry", "/e/" + first), ("classes", "/c/taxon"), ("node view", "/n/" + tx)):
        await pg.evaluate(f"LKGC.go({h!r})")
        await pg.wait_for_timeout(350)
        ok = await pg.evaluate("(() => { const b = document.querySelector('#corpbar'); const r = b.getBoundingClientRect(); return r.height > 20 && r.top >= 0 && document.querySelectorAll('#corpbar .cb').length === 4 && document.elementFromPoint(r.left + 120, r.top + r.height / 2).closest('#corpbar') === b; })()")
        check(ok, f"[{tag}] the corpus bar is present in the {name}")
    await pg.keyboard.press("/")
    await pg.keyboard.type("Kaufbeuren")
    await pg.wait_for_timeout(450)
    check(await pg.locator("#qres .r").count() > 0 and await pg.locator("#corpbar .cb").first.is_visible(), f"[{tag}] ... and while searching")
    await pg.keyboard.press("Escape")
    await pg.evaluate("document.querySelector('#q').value = ''; document.querySelector('#q').blur()")
    # the definitions of the four corpora, in words
    check(all(len(b["tip"]) > 20 for b in btns), f"[{tag}] every button explains its corpus (title)")
    await pg.click('#corpbar [data-act="corpus-info"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator("#corpinfo").is_visible() and await pg.locator("#corpinfo dd").count() == 4 and len(await pg.locator("#corpinfo").inner_text()) > 300, f"[{tag}] ⓘ opens the definitions of the four corpora in words")
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(150)
    check(await pg.locator("#corpinfo").count() == 0, f"[{tag}] ... Esc closes them")
    # choosing a corpus: filled button, explanation and "Filter aufheben" in the bar
    await pg.click('#corpbar [data-corpus="2"]')
    await pg.wait_for_timeout(500)
    btns = await pg.evaluate(JS_BAR)
    note = await pg.locator("#corpbar .cnote").inner_text()
    check(await pg.evaluate("LKGC.RVU.corpus") == 2 and [b["c"] for b in btns if b["on"]] == [2] and await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')"), f"[{tag}] a click on 'Strenger Kern' sets the filter and fills that button")
    check(de(n[2]) in note and de(n[0]) in note and await pg.locator('#corpbar [data-act="corpus-off"]').is_visible(), f"[{tag}] the bar explains the active filter and offers 'Filter aufheben' ({note[:70]}…)")
    await pg.click('#corpbar [data-act="corpus-off"]')
    await pg.wait_for_timeout(400)
    check(await pg.evaluate("LKGC.RVU.corpus") == 0 and await pg.locator('#corpbar [data-act="corpus-off"]').count() == 0 and not await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')"), f"[{tag}] 'Filter aufheben' returns to the full corpus")


async def corpus_checks(pg, queues=QUEUES, tag="review"):
    opts = [b["name"] + " " + b["n"] for b in await pg.evaluate(JS_BAR)]
    n = await pg.evaluate("LKGC.CORP.n")
    brute = [await pg.evaluate(JS_CORPUS_COUNT, c) for c in range(4)]
    check(len(opts) == 4 and all(f"{n[c]:,}".replace(",", ".") in opts[c] for c in range(4)), f"[{tag}] the corpus bar carries the record counts {opts}")
    check(n == [b[0] for b in brute], f"corpus sizes: full {n[0]}, core {n[1]}, strict core {n[2]}, strict core with coordinates {n[3]}")
    if await pg.evaluate("LKGC.G.ent.length") == 9901:
        check(n == FINAL_COUNTS, f"... the numbers of the final build {FINAL_COUNTS}")
    tiers = await pg.evaluate("(() => { const c = [0, 0, 0, 0]; for (const r of LKGC.G.ent) { const flat = LKGC.R.obs[r.id] || []; for (let i = 0; i < flat.length; i += 3) c[LKGC.tierOf(flat[i])]++; } return c; })()")
    print("records per tier 0..3:", tiers, "· entries per corpus:", await pg.evaluate("LKGC.CORP.ent"), "· taxa per corpus:", await pg.evaluate("LKGC.CORP.taxa"))
    full = await pg.evaluate("LKGC.RVU.counts")
    check(await pg.locator("#corpbar").is_visible() and not await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')"), f"[{tag}] no filter: the bar is there, not marked active")
    for c in (1, 2, 3):
        await pg.click(f'#corpbar [data-corpus="{c}"]')
        await pg.wait_for_timeout(500)
        cnt = await pg.evaluate("LKGC.RVU.counts")
        check(await pg.locator("#corpbar").is_visible() and f"{n[c]:,}".replace(",", ".") in await pg.locator("#corpbar").inner_text() and await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')"),
              f"[{tag}] corpus {c}: the bar says that a filter is active")
        check(cnt["all"]["n"] == brute[c][1] and all(cnt[q]["n"] <= full[q]["n"] for q in queues), f"corpus {c}: queue counts follow the filter (all: {cnt['all']['n']} entries)")
        await pg.evaluate("LKGC.setQueue('all', false)")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate(f"LKGC.RVU.list.length === {brute[c][1]} && LKGC.RVU.list.every(r => LKGC.RVS.get(r.n).nc[{c}] > 0)"), f"corpus {c}: the work list holds only entries with a record in the corpus")
        st = await pg.evaluate("(s => [s.kc[2], s.kc[1], s.kc[6], s.obsCount])(LKGC.stats())")
        check(st[0] == n[c] and st[3] == n[c] and st[1] == brute[c][1] and st[2] == await pg.evaluate(f"LKGC.CORP.taxa[{c}]"), f"corpus {c}: the graph statistics count {st[0]} records, {st[1]} entries, {st[2]} taxa")
    # one entry under "strenger Kern": graph, table, cards, switch "n außerhalb zeigen"
    await pg.click('#corpbar [data-corpus="2"]')
    await pg.wait_for_timeout(400)
    check(await pg.locator("#elist-pad .erow .n b").count() > 0, "list rows say 'n im Korpus / n gesamt'")
    eid = await find_entry(pg, "(rv, s, r) => s.nc && s.nc[2] >= 2 && r.nobs - s.nc[2] >= 2 && r.nobs <= 12 && Object.values(rv.rec || {}).some(x => x.t < 2 && (x.g || {}).v === 'wrong')")
    await goto_entry(pg, eid, 500)
    inn, tot = await pg.evaluate("[LKGC.RVS.get(LKGC.S.e).nc[2], LKGC.EM.obs.length]")
    check(await pg.locator("#gsvg .nd.k-obs").count() == inn, f"the subgraph shows the {inn} of {tot} records of the corpus ({eid})")
    check(str(inn) in await pg.locator("#ehead .hcorp").inner_text() and str(tot) in await pg.evaluate("document.querySelector('#gsvg .nd.k-entry text.s').textContent"), "the head and the entry node say 'n von m'")
    check(await pg.locator("#pbody .corpnote").count() == 1 and await pg.evaluate("LKGC.visibleItems(LKGC.EM).every(it => it.type !== 'rec' || LKGC.inCorpus(it.o.n))"), "cards of records outside the corpus are hidden, with a note")
    await pg.screenshot(path=str(SHOTS / "smoke_corpus_entry.png"))
    await pg.click('#gtools [data-act="showout"]')
    await pg.wait_for_timeout(350)
    check(await pg.locator("#gsvg .nd.k-obs").count() == tot and await pg.locator("#gsvg .nd.k-obs.out").count() == tot - inn, f"'{tot - inn} außerhalb zeigen' brings the others back, dimmed")
    why = await pg.evaluate("(() => { const it = LKGC.visibleItems(LKGC.EM).find(it => it.type === 'rec' && !LKGC.inCorpus(it.o.n)); LKGC.focusCard(LKGC.visibleItems(LKGC.EM).indexOf(it)); return document.querySelector('#pbody .rcard.focus .trline').innerText; })()")
    check(len(why) > 25 and await pg.locator("#pbody .rcard.out").count() >= 1, f"... their card says the tier and the reason in words ({why.strip()[:90]!r})")
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(300)
    check(await pg.locator("#rtable tr[data-o]").count() == tot and await pg.locator("#rtable tr.out").count() == tot - inn and await pg.locator("#rtable tr.out td.c-tier .trwhy").count() == tot - inn, "the table marks the rows outside the corpus with the reason")
    await pg.click('#gtools [data-act="showout"]')
    await pg.wait_for_timeout(300)
    check(await pg.locator("#rtable tr[data-o]").count() == inn, "... and hides them again")
    await pg.keyboard.press("g")
    # node view, class view, overview under the filter
    tx = await pg.evaluate("(() => { const G = LKGC.G; const t = LKGC.stats().taxa[3]; let all = 0, inn = 0; for (let i = G.inOff[t.n]; i < G.inOff[t.n + 1]; i++) if (G.kind[G.inS[i]] === 2) { all++; if (LKGC.inCorpus(G.inS[i])) inn++; } return { iri: G.nodes[t.n], n: t.n, v: t.v, all, inn }; })()")
    await pg.evaluate(f"LKGC.go('/n/' + {tx['iri']!r})")
    await pg.wait_for_timeout(700)
    rows = await pg.evaluate(f"LKGC.usageRows({tx['n']}).length")
    check(rows == tx["inn"] == tx["v"] and tx["inn"] < tx["all"], f"node view of a taxon counts only the records of the corpus ({tx['inn']} of {tx['all']})")
    check(f"{tx['inn']:,}".replace(",", ".") in await pg.locator("#nv-usage h3").inner_text() and await pg.locator("#v-node .corpnote").count() == 1, "... its usage table says so, with the filter note")
    ysum = await pg.evaluate("[...document.querySelectorAll('#v-node .cols')].length")
    check(ysum >= 1, "... per-year / per-month charts are drawn from the same rows")
    await pg.screenshot(path=str(SHOTS / "smoke_corpus_node.png"))
    await pg.evaluate("LKGC.go('/c/taxon')")
    await pg.wait_for_timeout(400)
    check(f"{await pg.evaluate('LKGC.CORP.taxa[2]'):,}".replace(",", ".") in await pg.locator("#v-class").inner_text() and await pg.locator("#v-class .corptag").count() == 1, "class view lists only the taxa of the corpus")
    await pg.evaluate("LKGC.go('/')")
    await pg.wait_for_timeout(600)
    check(await pg.locator("#rv-ov table.covt tr[data-corpus]").count() == 4 and await pg.locator("#rv-ov tr[data-corpus].on").get_attribute("data-corpus") == "2", "overview: table of the four corpora, the chosen one marked")
    reasons = await pg.evaluate("LKGC.CORP.why")
    check(len(reasons) >= 8 and await pg.locator("#rv-ov table.covt").nth(2).locator("tr").count() == len(reasons) + 1, f"overview: distribution of the reasons {reasons}")
    check(f"{n[2]:,}".replace(",", ".") in await pg.locator("#x-ov .tiles").inner_text(), "overview: the explorer's tiles count the corpus")
    # remembered; a view only
    await reload(pg)
    check(await pg.evaluate("LKGC.RVU.corpus") == 2 and await pg.locator("#corpbar").is_visible(), "the chosen corpus is remembered")
    await pg.click('#corpbar [data-act="corpus-off"]')
    await pg.wait_for_timeout(500)
    check(await pg.evaluate("LKGC.RVU.corpus") == 0 and await pg.evaluate("LKGC.RVU.counts.all.n") == full["all"]["n"] and await pg.evaluate("LKGC.stats().kc[2]") == n[0], "'Filter aufheben' restores the full corpus")



# ---------------------------------------------------------------------------------------------------------------
# one app, two builds: the explorer build shows the same data and decides nothing

SAME_ENTRY = "L17-e0132"
JS_FACTS = """() => { const S = LKGC.SUB; const nodes = [...S.V.values()].map(v => [v.key, v.kind, (v.rows || []).map(r => (r.k || '') + '|' + r.v).join(' § ')]).sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const edges = S.E.map(e => e.a.key + '>' + e.b.key + '|' + e.p).sort();
  const box = r => ['x', 'y', 'width', 'height'].map(a => Math.round(+r.getAttribute(a))).join(',');
  const ov = { reg: [...document.querySelectorAll('#scanov rect.reg')].map(box), mreg: [...document.querySelectorAll('#scanov rect.mreg')].map(box), line: [...document.querySelectorAll('#scanov rect.line')].map(box), pages: LKGC.SC.pages.map(p => p.idx), page: LKGC.SC.pi };
  const rings = [...document.querySelectorAll('#gsvg .nd.an')].map(g => g.dataset.key + ':' + [...g.classList].filter(c => c.startsWith('an-')).join('.')).sort();
  const cards = [...document.querySelectorAll('#pbody .rcard[data-ci]:not(.t-done)')].map(c => [...c.classList].filter(x => /^(t-|lv)/.test(x)).join('.') + ' ' + c.querySelector('.rc-head').innerText.replace(/\\s+/g, ' ').trim());
  return { nodes, edges, ov, rings, cards, rows: document.querySelectorAll('#gsvg text.pr').length, layers: JSON.stringify(LKGC.S.layers), crops: document.querySelectorAll('#pbody .rcard.t-media .mthumb').length }; }"""
JS_TABLE = """() => ({ cols: [...document.querySelectorAll('#rtable th[data-col]')].map(th => th.dataset.col + '=' + th.textContent),
  cells: [...document.querySelectorAll('#rtable tbody tr')].map(tr => [...tr.querySelectorAll('td:not(.racts)')].map(td => td.innerText.replace(/\\s+/g, ' ').trim()).join(' | ')) })"""
JS_NUMBERS = """() => ({ corp: document.querySelector('#rv-ov tr[data-corpus]').closest('table').innerText, why: [...document.querySelectorAll('#rv-ov table.covt')][2].innerText,
  tiles: document.querySelector('#x-ov .tiles').innerText, lv: [...document.querySelectorAll('#rv-ov table.lvt td.num')].map(td => td.textContent).join(','), stats: [...LKGC.stats().kc].join(','), n: LKGC.CORP.n, ent: LKGC.CORP.ent, taxa: LKGC.CORP.taxa })"""
# every control that decides something; none of them may exist in the explorer build
DECIDE = ("#who, #btn-save, #btn-load, #fileImport, #rvprog, #savedlbl, .abtn, .rc-acts, .rform, .mine, [data-act=addrec], [data-act=txtedit], [data-act=txtdel], [data-act=reset], "
          "[data-ra], .racts, th.c-acts, [data-acc], .qchip[data-q=done], .qtile[data-queue=done], .rcard.t-done, .rcard.done, .nd.an-dec, .b-ok, #modal [data-m]")


async def entry_facts(pg, eid):
    """What one entry shows: subgraph, property rows, annotations, cards, scan overlays, table."""
    await goto_entry(pg, eid, 900)
    await pg.evaluate("(() => { const items = LKGC.visibleItems(LKGC.EM); const i = items.findIndex(it => it.type === 'rec' && it.o.rec.loc); if (i >= 0) LKGC.focusCard(i); })()")
    await pg.wait_for_timeout(500)
    f = await pg.evaluate(JS_FACTS)
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(350)
    f["table"] = await pg.evaluate(JS_TABLE)
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(250)
    await pg.click('#gtools [data-act="preset-all"]')
    await pg.wait_for_timeout(450)
    f["all"] = await pg.evaluate("(() => { const S = LKGC.SUB; return { nodes: [...S.V.values()].map(v => v.key + ':' + (v.rows || []).length).sort(), edges: S.E.length }; })()")
    await pg.click('#gtools [data-act="preset-std"]')
    await pg.wait_for_timeout(300)
    return f


async def review_reference(pg):
    """The facts of the review build that the explorer build must show identically."""
    ref = {"entry": await entry_facts(pg, SAME_ENTRY)}
    img = await find_entry(pg, CASES["img"])
    ref["img"] = img
    await goto_entry(pg, img, 700)
    ref["media"] = await pg.evaluate("({ cards: document.querySelectorAll('#pbody .rcard.t-media .mthumb').length, mreg: document.querySelectorAll('#scanov rect.mreg').length, n: LKGC.EM.rv.media.length })")
    await pg.evaluate("LKGC.go('/')")
    await pg.wait_for_timeout(500)
    ref["numbers"] = await pg.evaluate(JS_NUMBERS)
    tx = await pg.evaluate("LKGC.G.nodes[LKGC.stats().taxa[2].n]")
    ref["tx"] = tx
    await pg.evaluate(f"LKGC.go('/n/' + {tx!r})")
    await pg.wait_for_timeout(600)
    ref["node"] = await pg.evaluate("({ usage: document.querySelector('#nv-usage h3').innerText, card: document.querySelector('#v-node .card').innerText })")
    await pg.evaluate("LKGC.go('/c/taxon')")
    await pg.wait_for_timeout(400)
    ref["klass"] = await pg.evaluate("document.querySelectorAll('#v-class table.t tr').length + '|' + document.querySelector('#v-class table.t').innerText.slice(0, 400)")
    return ref


async def no_decision_controls(pg, where):
    n = await pg.locator(DECIDE).count()
    found = await pg.evaluate(f"[...document.querySelectorAll({DECIDE!r})].slice(0, 4).map(el => el.tagName + '#' + el.id + '.' + el.className)") if n else []
    check(n == 0, f"[explorer] no decision control in the {where} {found}")


async def explorer_checks(p, ref):
    if not check(EXPLORER_PAGE.exists(), f"the explorer build exists ({EXPLORER_PAGE.name}; build_graph_check.py --mode explorer)"):
        return []
    b, pg, errs = await open_page(p, url=EXPLORER_PAGE.as_uri())
    t0 = time.time()
    await reload(pg)
    load = time.time() - t0
    print(f"explorer build: load {load:.2f} s, timing {await pg.evaluate('LKGC.timing')}")
    check(load <= 5, f"[explorer] the page opens in <= 5 s ({load:.2f} s)")
    meta = await pg.evaluate("({ page: LKGC.META, graph: LKGC.G.meta.mode, layer: LKGC.R.meta.mode, flag: LKGC.EXPLORER, attr: document.documentElement.dataset.mode, title: document.title, h1: document.querySelector('#apptitle').textContent })")
    check(meta["page"]["mode"] == "explorer" and meta["graph"] == "explorer" and meta["layer"] == "explorer" and meta["flag"] is True and meta["attr"] == "explorer", f"[explorer] the mode flag stands in the embedded meta ({meta['page']})")
    check(meta["title"] == "Laubmann-KG · Graph-Explorer" == meta["h1"], f"[explorer] title {meta['title']!r}")
    await no_decision_controls(pg, "overview")
    check(await pg.locator("#rv-ov .qtile").count() == 8 and await pg.locator("#rv-ov table.prec").count() == 0, "[explorer] overview: eight filter tiles, no 'Geprüft', no precision of decisions")
    # the same numbers for the graph and the corpora
    num = await pg.evaluate(JS_NUMBERS)
    for k, what in (("n", "records per corpus"), ("ent", "entries per corpus"), ("taxa", "taxa per corpus"), ("corp", "table of the corpora"), ("why", "reasons"), ("tiles", "tiles of the graph"), ("stats", "node counts per kind"), ("lv", "notes per level and kind")):
        check(num[k] == ref["numbers"][k], f"[explorer] overview: same {what} as the review build")
    # the list: all entries in diary order by default, the queues as filters
    await pg.evaluate("LKGC.go('/e/' + LKGC.G.ent[0].id)")
    await pg.wait_for_timeout(500)
    check(await pg.evaluate("LKGC.RVU.queue === 'all' && LKGC.RVU.sort === 'diary' && LKGC.RVU.list.length === LKGC.G.ent.length"), "[explorer] the list holds all entries by default")
    check(await pg.evaluate("(l => l.every((r, i) => !i || LKGC.G.entPos.get(l[i - 1].n) < LKGC.G.entPos.get(r.n)))(LKGC.RVU.list)"), "[explorer] ... volume by volume in diary order")
    chips = await pg.evaluate("[...document.querySelectorAll('#qchips .qchip')].map(c => c.dataset.q)")
    check(chips == [q for q in QUEUES if q != "done"] and await pg.locator("#qchips .qt").count() == 0, f"[explorer] the queues remain as filters, without 'Geprüft' and without 'offen' {chips}")
    await pg.click('#qchips [data-q="img"]')
    await pg.wait_for_timeout(300)
    check(await pg.evaluate("LKGC.RVU.list.length > 0 && LKGC.RVU.list.every(r => LKGC.RVS.get(r.n).img > 0)"), "[explorer] a queue filters the list")
    await pg.evaluate("LKGC.setQueue('all', false)")
    # the same entry shows the same things
    f = await entry_facts(pg, SAME_ENTRY)
    r = ref["entry"]
    check(f["layers"] == r["layers"], f"[explorer] same default layers ({f['layers']})")
    check(f["nodes"] == r["nodes"] and len(f["nodes"]) > 8, f"[explorer] {SAME_ENTRY}: the same nodes with the same property rows ({len(f['nodes'])} nodes, {f['rows']} rows; review {len(r['nodes'])}, {r['rows']})")
    check(f["edges"] == r["edges"], f"[explorer] ... the same edges ({len(f['edges'])})")
    check(f["rings"] == r["rings"] and len(f["rings"]) > 0, f"[explorer] ... the same annotations: colours and markers ({len(f['rings'])} marked nodes)")
    check(f["cards"] == r["cards"] and len(f["cards"]) > 2, f"[explorer] ... the same cards in the same order ({len(f['cards'])})")
    check(f["ov"] == r["ov"] and len(f["ov"]["reg"]) > 0 and len(f["ov"]["line"]) == 1, f"[explorer] ... the same scan overlays: regions {len(f['ov']['reg'])}, media {len(f['ov']['mreg'])}, record line {f['ov']['line']}")
    check(f["table"]["cols"] == r["table"]["cols"] and len(f["table"]["cols"]) >= 12, f"[explorer] ... the same table columns ({len(f['table']['cols'])})")
    check(f["table"]["cells"] == r["table"]["cells"], f"[explorer] ... the same table rows with the same values and chips ({len(f['table']['cells'])})")
    check(f["all"] == r["all"], f"[explorer] ... the same graph with 'Alles zeigen' ({len(f['all']['nodes'])} nodes, {f['all']['edges']} edges)")
    await pg.screenshot(path=str(SHOTS / "smoke_explorer_entry.png"))
    # read-only annotations: from -> to and reasons, nothing to decide
    check(await pg.locator("#pbody .rcard.ro").count() == len(f["cards"]) and await pg.locator("#pbody .rcard.ro .diff").count() > 0 and await pg.locator("#pbody .rcard.ro .why").count() > 0, "[explorer] the cards are read-only annotations with from → to and reasons")
    await no_decision_controls(pg, "entry view (notes tab)")
    for tab in ("text", "node", "check"):
        await pg.click(f'#ptabs [data-tab="{tab}"]')
        await pg.wait_for_timeout(200)
        await no_decision_controls(pg, f"tab {tab}")
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(300)
    check(await pg.locator("#rtable tr[data-o]").count() > 0 and await pg.locator("#rtable .pchip").count() > 0, "[explorer] the table shows the findings as chips")
    await no_decision_controls(pg, "records table")
    await pg.click("#rtable tr[data-o] >> nth=1 >> td >> nth=3")
    await pg.click("#rtable tr[data-o] >> nth=1 >> td >> nth=3")
    await pg.wait_for_timeout(200)
    check(await pg.locator("#rtable input, #rtable select").count() == 0 and await pg.locator("#rtable tr.on").count() == 1, "[explorer] a click on a cell selects the row, nothing becomes editable")
    await pg.click('#gtools [data-act="cols"]')
    check(await pg.locator("#colpop label").count() >= 12, "[explorer] the column chooser works")
    await pg.click('#colpop [data-cp="close"]')
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(250)
    await pg.evaluate("LKGC.focusCard(0)")
    for key in ("j", "n", "e", "x", "u", "z", "Enter"):
        await pg.keyboard.press(key)
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == 0 and await pg.locator("#pbody .rform").count() == 0 and await pg.evaluate("localStorage.getItem('laubmann-graphpruefung')") is None, "[explorer] the decision keys do nothing, nothing is stored")
    await pg.keyboard.press("ArrowDown")
    await pg.wait_for_timeout(150)
    check(await pg.evaluate("LKGC.RVU.card") == 1, "[explorer] ↑ ↓ still step through the cards")
    # a decided state of the review build is not shown
    await pg.evaluate("localStorage.setItem('laubmann-graphpruefung', JSON.stringify({ v: 1, who: 'X', dec: { ['entry:' + LKGC.EM.uid]: { checked: { t: '2026-01-01T00:00:00Z' } } }, log: [] }))")
    await reload(pg)
    await goto_entry(pg, SAME_ENTRY, 600)
    check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == 0 and await pg.locator("#ehead .hstate.ok, .erow.chk").count() == 0, "[explorer] decisions stored by the review build are not loaded: no decided state")
    await pg.evaluate("localStorage.removeItem('laubmann-graphpruefung')")
    # images and inserts
    await goto_entry(pg, ref["img"], 700)
    med = await pg.evaluate("({ cards: document.querySelectorAll('#pbody .rcard.t-media .mthumb').length, mreg: document.querySelectorAll('#scanov rect.mreg').length, n: LKGC.EM.rv.media.length })")
    check(med == ref["media"] and med["cards"] > 0, f"[explorer] the same cards and outlines for images and inserts ({med})")
    await pg.evaluate("(() => { const items = LKGC.visibleItems(LKGC.EM); LKGC.focusCard(items.findIndex(it => it.type === 'media' && it.x.length >= 7)); })()")
    await pg.wait_for_timeout(800)
    check(await pg.evaluate("(i => !!i && i.complete && i.naturalWidth > 0)(document.querySelector('#pbody .rcard.t-media.focus img.crop.thumb'))"), "[explorer] the crop loads")
    await pg.click("#pbody .rcard.t-media.focus .mthumb")
    await pg.wait_for_timeout(500)
    check(await pg.locator("#lightbox").is_visible(), "[explorer] ... and opens in the large view")
    await pg.keyboard.press("Escape")
    await no_decision_controls(pg, "entry with images")
    # switch "Prüfhinweise zeigen"
    await goto_entry(pg, SAME_ENTRY, 600)
    sw = pg.locator("#corpbar #notesw")
    check(await sw.count() == 1 and await sw.is_checked() and await pg.locator("#gsvg .nd.an").count() > 0, "[explorer] 'Prüfhinweise zeigen' is on by default")
    n_obs = await pg.locator("#gsvg .nd.k-obs").count()
    await sw.uncheck()
    await pg.wait_for_timeout(500)
    off = await pg.evaluate("({ an: document.querySelectorAll('#gsvg .nd.an, #gsvg .ring, #gsvg .abadge').length, ghosts: document.querySelectorAll('#gsvg .nd.k-miss, #gsvg .nd.k-gone').length, cards: document.querySelectorAll('#pbody .rcard:not(.t-media)').length, pills: document.querySelectorAll('#elist-pad .lvp, #lvchips .lvchip, #ehead .hstate').length, chips: [...document.querySelectorAll('#qchips .qchip')].map(c => c.dataset.q), obs: document.querySelectorAll('#gsvg .nd.k-obs').length, rows: document.querySelectorAll('#gsvg text.pr').length, tier: document.querySelectorAll('#gsvg .tpill').length })")
    check(off["an"] == 0 and off["ghosts"] == 0 and off["cards"] == 0 and off["pills"] == 0, f"[explorer] switched off: no rings, markers, ghost nodes, note cards or level pills {off}")
    check(off["obs"] == n_obs and off["rows"] == f["rows"] and off["tier"] == n_obs and off["chips"] == ["ins", "img", "sample", "all"], "[explorer] ... the graph itself (records, property rows, corpus tiers) stays; the note queues are gone")
    await pg.keyboard.press("g")
    await pg.wait_for_timeout(300)
    check(await pg.locator("#rtable .pchip, #rtable .tbadge, #rtable tr.ghost").count() == 0 and await pg.locator("#rtable tr[data-o]").count() == n_obs, "[explorer] ... the table without chips and markers")
    await pg.keyboard.press("g")
    await pg.click('#ptabs [data-tab="text"]')
    await pg.wait_for_timeout(200)
    check(await pg.locator("#fnotes .tci, #fnotes del").count() == 0 and len(await pg.locator("#fnotes").inner_text()) > 20, "[explorer] ... the entry text without reading-correction marks")
    await pg.click('#ptabs [data-tab="check"]')
    await pg.screenshot(path=str(SHOTS / "smoke_explorer_notes_off.png"))
    await reload(pg)
    check(await pg.evaluate("LKGC.RVU.notes") is False, "[explorer] the switch is remembered")
    await pg.locator("#corpbar #notesw").check()
    await pg.wait_for_timeout(500)
    await goto_entry(pg, SAME_ENTRY, 600)
    check(await pg.locator("#gsvg .nd.an").count() == len(r["rings"]) and await pg.locator("#qchips .qchip").count() == 8, "[explorer] switched on again: the notes are back")
    # node view, class view, search
    await pg.evaluate(f"LKGC.go('/n/' + {ref['tx']!r})")
    await pg.wait_for_timeout(600)
    check(await pg.evaluate("({ usage: document.querySelector('#nv-usage h3').innerText, card: document.querySelector('#v-node .card').innerText })") == ref["node"], "[explorer] the same node view")
    await no_decision_controls(pg, "node view")
    await pg.evaluate("LKGC.go('/c/taxon')")
    await pg.wait_for_timeout(400)
    check(await pg.evaluate("document.querySelectorAll('#v-class table.t tr').length + '|' + document.querySelector('#v-class table.t').innerText.slice(0, 400)") == ref["klass"], "[explorer] the same class view")
    await no_decision_controls(pg, "class view")
    # corpus bar: present, four counts, filters the views
    await corpus_bar_checks(pg, "explorer")
    await corpus_checks(pg, [q for q in QUEUES if q != "done"], "explorer")
    # both languages without untranslated keys, the help without decisions
    for lang in ("de", "en"):
        if await pg.evaluate("LKGC.LANG") != lang:
            await pg.click("#btn-lang")
            await pg.wait_for_timeout(300)
        bad = set()
        await goto_entry(pg, SAME_ENTRY, 500)
        for tab in ("text", "node", "check"):
            await pg.click(f'#ptabs [data-tab="{tab}"]')
            await pg.wait_for_timeout(150)
            bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
        await pg.evaluate("LKGC.go('/')")
        await pg.wait_for_timeout(400)
        bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
        await pg.click("#btn-help")
        txt = await pg.locator("#help").inner_text()
        bad |= set(KEYPAT.findall(txt))
        check(not bad, f"[explorer {lang}] no untranslated keys {sorted(bad)[:12]}")
        check("J" not in [k.strip() for k in await pg.evaluate("[...document.querySelectorAll('#help kbd')].map(k => k.textContent)")] and await pg.locator("#help table.sevt").count() == 1, f"[explorer {lang}] the help lists no decision keys and explains the levels")
        await pg.click("#help h2")
    await pg.click("#btn-lang")
    await b.close()
    return errs


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        t0 = time.time()
        await reload(pg)
        load = time.time() - t0
        timing = await pg.evaluate("LKGC.timing")
        print(f"load {load:.2f} s, timing {timing}")
        check(load <= 5, f"the page opens in <= 5 s ({load:.2f} s)")
        check(await pg.evaluate("LKGC.LANG") == "de", "German is the default language")
        de_only = await pg.evaluate("Object.keys(LKGC.UI.de).filter(k => !(k in LKGC.UI.en))")
        en_only = await pg.evaluate("Object.keys(LKGC.UI.en).filter(k => !(k in LKGC.UI.de))")
        check(not de_only and not en_only, f"DE and EN have the same keys {de_only[:5]} {en_only[:5]}")

        # overview
        check(await pg.locator("#rv-ov .qtile").count() == 9, "overview shows the nine queue tiles")
        check(await pg.locator("#rv-ov table.covt tr").count() >= 8, "overview shows coverage and progress")
        check(await pg.locator("#x-ov .tile").count() >= 8, "the explorer's overview is still there")
        counts = await pg.evaluate("LKGC.RVU.counts")
        print("queue counts (entries, open):", {k: (v["n"], v["open"]) for k, v in counts.items()})

        # every queue
        for q in QUEUES:
            await pg.evaluate(f"LKGC.setQueue('{q}', true)")
            await pg.wait_for_timeout(250)
            n = await pg.evaluate("LKGC.RVU.list.length")
            check(n == counts[q]["n"], f"queue {q}: list has {n} entries (count {counts[q]['n']})")
            if q != "done":
                check(n > 0, f"queue {q} is not empty")
                check(await pg.locator("#elist-pad .erow").count() > 0, f"queue {q}: rows are drawn")
                check(await pg.evaluate("LKGC.S.view") == "entry" and await pg.locator("#pbody .rcard").count() > 0, f"queue {q}: its first entry opens with cards")
        check(await pg.locator("#qchips .qchip").count() == 9, "nine queue chips (with 'Bilder')")
        check(await pg.evaluate("LKGC.RVU.counts.img.n === [...LKGC.RVS.values()].filter(s => s.img > 0).length && LKGC.RVU.counts.img.n > 0"), "queue 'Bilder' = entries with a drawing, map, photograph, print or object")
        await pg.evaluate("LKGC.setQueue('finding', true)")
        await pg.select_option("#qsort", "diary")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("(l => l.every((r, i) => !i || LKGC.G.entPos.get(l[i - 1].n) < LKGC.G.entPos.get(r.n)))(LKGC.RVU.list)"), "'diary order' lists the entries in the order of the volumes")
        await pg.select_option("#qsort", "score")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate(JS_LEVEL_SORTED), "'schwer zuerst' sorts by the open findings per level")
        vol = await pg.evaluate("document.querySelector('#volsel').options[1].value")
        await pg.select_option("#volsel", vol)
        await pg.wait_for_timeout(200)
        check(await pg.evaluate(f"LKGC.RVU.list.length > 0 && LKGC.RVU.list.every(r => String(r.vol) === '{vol}')"), "volume filter restricts the list")
        await pg.select_option("#volsel", "all")

        for lang in ("de", "en"):
            if await pg.evaluate("LKGC.LANG") != lang:
                await pg.click("#btn-lang")
                await pg.wait_for_timeout(300)
            bad = set()
            for kind, pred in CASES.items():
                eid = await find_entry(pg, pred)
                if not check(eid is not None, f"[{lang}] an entry for card type {kind} exists"):
                    continue
                await goto_entry(pg, eid)
                typ = "media" if kind == "img" else kind.split("-")[0]
                if kind in ("name", "tc", "qa"):      # may be level-0 cards: collapsed until asked for
                    await show_hints(pg)
                check(await pg.locator(f"#pbody .rcard.t-{typ}").count() > 0, f"[{lang}] {kind}: card renders ({eid})")
                bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                if kind == "rec":
                    check(await pg.locator('#gsvg .nd.k-obs[class*="an-lv"] .ring, #gsvg .nd.k-group[class*="an-lv"] .ring').count() > 0, f"[{lang}] flagged record has a ring in its level colour")
                    check(await pg.locator("#legend .li").count() >= 5, f"[{lang}] the legend explains the annotation colours")
                    check(await pg.locator("#scanov rect.reg").count() > 0, f"[{lang}] the entry's region is outlined on the scan")
                    has_loc = await pg.evaluate("(() => { const m = LKGC.EM; const items = LKGC.visibleItems(m); const i = items.findIndex(it => it.type === 'rec' && it.o.rec.loc); if (i < 0) return false; LKGC.focusCard(i); return true; })()")
                    await pg.wait_for_timeout(150)
                    if has_loc:
                        check(await pg.locator("#scanov rect.line").count() == 1, f"[{lang}] focusing a record marks its line on the scan")
                    await pg.keyboard.press("g")
                    await pg.wait_for_timeout(250)
                    check(await pg.locator("#rtable tr[data-o]").count() > 0 and not await pg.locator("#gcanvas").is_visible(), f"[{lang}] G shows the records table")
                    bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                    await pg.keyboard.press("g")
                    await pg.wait_for_timeout(250)
                    check(await pg.locator("#gcanvas").is_visible() and not await pg.locator("#rtable").is_visible(), f"[{lang}] G returns to the graph")
                    for tab in ("text", "node", "check"):
                        await pg.click(f'#ptabs [data-tab="{tab}"]')
                        await pg.wait_for_timeout(200)
                        check(len(await pg.evaluate("document.querySelector('#pbody').innerText")) > 40, f"[{lang}] tab {tab} renders")
                        bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                    await pg.keyboard.press("s")
                    await pg.wait_for_timeout(150)
                    check(not await pg.locator("#scanpane").is_visible(), f"[{lang}] S hides the scan pane")
                    await pg.keyboard.press("s")
                    await pg.wait_for_timeout(250)
                    check(await pg.locator("#scanpane").is_visible(), f"[{lang}] S shows it again")
                if kind == "rec-both":
                    check(await pg.locator("#pbody .agree").count() > 0, f"[{lang}] a record judged by both checks says whether they agree")
                if kind == "miss":
                    check(await pg.locator("#gsvg .nd.k-miss").count() > 0, f"[{lang}] missing record is a ghost node")
                if kind == "name":
                    check(await pg.locator("#pbody .rcard.t-name .scope").count() > 0, f"[{lang}] name card says that it applies to all entries")
                if kind == "tc":
                    await pg.click('#ptabs [data-tab="text"]')
                    await pg.wait_for_timeout(200)
                    check(await pg.locator("#fnotes .tci").count() > 0 and await pg.locator("#fnotes del").count() > 0, f"[{lang}] reading corrections stand inline in the text")
                    await pg.click("#fnotes .tci >> nth=0")
                    await pg.wait_for_timeout(200)
                    check(await pg.evaluate("LKGC.S.tab") == "check" and await pg.locator("#pbody .rcard.t-tc.focus").count() == 1, f"[{lang}] clicking a correction in the text opens its card")
                if kind == "media":
                    n_cards = await pg.locator("#pbody .rcard.t-media").count()
                    n_regions = await pg.evaluate("new Set((LKGC.EM.rv.media || []).map(x => x[0]).concat((LKGC.EM.rv.ins || []).map(x => x[0]))).size")
                    check(n_cards == n_regions, f"[{lang}] one card per region: text inserts are merged into the media cards ({n_cards}/{n_regions})")
                    check(await pg.locator("#pbody .rcard.t-media .vd[class*=vd-ins-]").count() > 0 and await pg.locator("#pbody .rcard.t-media .hint.warn").count() > 0, f"[{lang}] the insert's card shows its read state and the hint for unread ones")
                if kind == "img":
                    await img_checks(pg, lang)
                if kind == "qa":
                    check(await pg.locator("#gsvg .nd.k-gone").count() > 0, f"[{lang}] removed record is a ghost node")
            # the overview and the explorer's other views in this language
            await pg.evaluate("LKGC.go('/')")
            await pg.wait_for_timeout(400)
            bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
            await pg.click("#btn-save")
            await pg.wait_for_timeout(200)
            check(await pg.locator("#modal table tr").count() >= 9, f"[{lang}] the export dialog lists the files")
            bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
            await pg.keyboard.press("Escape")
            await pg.click("#btn-help")
            bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
            await pg.click("#help")
            check(not bad, f"[{lang}] no untranslated keys {sorted(bad)[:12]}")
        await pg.click("#btn-lang")
        await pg.wait_for_timeout(200)

        # final pass: properties, table columns, gravity, corpus filter
        eid_p = await props_checks(pg)
        await table_checks(pg, eid_p)
        await severity_checks(pg)
        await corpus_bar_checks(pg, "review")
        await corpus_checks(pg)
        ref = await review_reference(pg)      # what the explorer build must show identically

        # the explorer's other views
        await pg.evaluate("LKGC.go('/c/taxon')")
        await pg.wait_for_timeout(300)
        check(await pg.locator("#v-class table.t tr").count() > 10, "class view still works")
        node = await pg.evaluate("(() => { for (let n = 0; n < LKGC.G.nodes.length; n++) if (LKGC.G.kind[n] === 6) return LKGC.G.nodes[n]; })()")
        await pg.evaluate(f"LKGC.go('/n/' + {node!r})")
        await pg.wait_for_timeout(500)
        check(await pg.locator("#v-node .card").count() >= 2, "node view still works")
        await pg.keyboard.press("/")
        await pg.keyboard.type("Kaufbeuren")
        await pg.wait_for_timeout(500)
        check(await pg.locator("#qres .r").count() > 0, "search (/) still works")
        await pg.keyboard.press("Escape")

        # the largest entry stays responsive
        big = await pg.evaluate("LKGC.G.ent.slice().sort((a, b) => b.nobs - a.nobs)[0]")
        t0 = time.time()
        await pg.evaluate(f"LKGC.go('/e/' + {big['id']!r})")
        await pg.wait_for_function(f"LKGC.EM && LKGC.EM.id === {big['id']!r} && document.querySelector('#pbody .rcard')")
        t_open = time.time() - t0
        t0 = time.time()
        await pg.keyboard.press("g")
        await pg.wait_for_function("document.querySelectorAll('#rtable tr[data-o]').length > 0")
        t_table = time.time() - t0
        t0 = time.time()
        await pg.evaluate("(() => { const m = LKGC.EM; const it = LKGC.visibleItems(m).find(i => i.type === 'rec'); LKGC.decide(it.key, { d: 'u', ref: { uid: m.uid, id: m.id, w: it.o.written, idx: it.o.idx, occ: it.o.occ } }, 'test'); })()")
        t_dec = time.time() - t0
        await pg.keyboard.press("z")
        await pg.keyboard.press("g")
        print(f"largest entry {big['id']} ({big['nobs']} records): open {t_open:.2f} s, table {t_table:.2f} s, decision + redraw {t_dec:.2f} s")
        check(t_open < 1.5 and t_table < 1.5 and t_dec < 1.5, "the largest entry stays responsive (< 1.5 s per step)")
        await b.close()

        # without any scan image
        b, pg, errs2 = await open_page(p, local_scans=False)
        eid = await find_entry(pg, CASES["rec"])
        await goto_entry(pg, eid, 900)
        check(await pg.locator("#scanmsg").is_visible() and await pg.locator("#scanov rect.reg").count() > 0, "without images: message, region overlay still drawn")
        check(await pg.locator("#pbody .rcard").count() > 0, "without images: cards render")
        eid = await find_entry(pg, CASES["img"])
        await goto_entry(pg, eid, 600)
        await pg.evaluate("(() => { const items = LKGC.visibleItems(LKGC.EM); LKGC.focusCard(items.findIndex(it => it.type === 'media')); })()")
        await pg.wait_for_timeout(1500)
        check(await pg.locator("#pbody .rcard.t-media .cropfail").count() > 0 and await pg.locator("#pbody .rcard.t-media").count() >= 2, "without images: media cards render with the note 'Bild nicht ladbar'")
        await pg.click("#pbody .rcard.t-media.focus .mthumb")
        await pg.wait_for_timeout(800)
        check(await pg.locator("#lightbox").is_visible() and await pg.locator("#lightbox .cropfail").count() == 1, "without images: the large view opens and says so")
        await pg.keyboard.press("Escape")
        await b.close()

        # the explorer build of the same app
        errs3 = await explorer_checks(p, ref)
        done(errs + errs2 + errs3)

asyncio.run(main())
