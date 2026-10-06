"""1440×900 screenshots of the page's main states (python tests/screenshots.py [page.html] [shots dir]).

The scans come from the local JPEGs (data/pages_jpg, the page's fallback): the network is blocked."""
import asyncio
from playwright.async_api import async_playwright
from common import EXPLORER_PAGE, SHOTS, check, done, find_entry, focus_item, goto_entry, open_page

SMALL = "Object.keys(rv.rec || {}).length >= 5 && Object.keys(rv.rec || {}).length <= 12"


async def card_shot(pg, name, pred_entry, pred_item, scan=False):
    eid = await find_entry(pg, pred_entry)
    if not check(eid is not None, f"{name}: an entry exists"):
        return
    await goto_entry(pg, eid, 700)
    if not scan and await pg.locator("#scanpane").is_visible():
        await pg.keyboard.press("s")
    await pg.evaluate("LKGC.RVU.hints = false")
    i = await focus_item(pg, pred_item)
    if i is None:      # a level-0 card: among the collapsed hints
        await pg.evaluate("(() => { const a = document.querySelector('#pbody [data-act=hints]'); if (a) a.click(); })()")
        await pg.wait_for_timeout(150)
        i = await focus_item(pg, pred_item)
    await pg.evaluate("(() => { const el = document.querySelector('#pbody .rcard.focus'); if (el) { const b = document.querySelector('#pbody'); b.scrollTop = Math.max(0, el.offsetTop - b.offsetTop - 34); } })()")
    await pg.wait_for_timeout(500)
    await pg.screenshot(path=str(SHOTS / name))
    print("shot", name, eid, "card", i)


SAME_ENTRY = "L17-e0132"


async def entry_shot(pg, name):
    """The entry both builds are compared on, in the same state: first record card with a line on the scan."""
    await goto_entry(pg, SAME_ENTRY, 900)
    if not await pg.locator("#scanpane").is_visible():
        await pg.keyboard.press("s")
    await focus_item(pg, "it => it.type === 'rec' && it.o.rec.loc && it.o.rec.g && it.o.rec.g.v === 'wrong'")
    await pg.wait_for_timeout(600)
    await pg.screenshot(path=str(SHOTS / name))


JS_ARCH = """(eid) => { const G = LKGC.G; const e = G.ent.find(r => r.id === eid).n; const out = (n, kind) => { for (let i = G.sOff[n]; i < G.sOff[n + 1]; i++) { const o = G.tO[i]; if (o >= 0 && G.kind[o] === kind) return o; } return -1; };
  const region = out(e, 13), page = out(region, 12), vol = out(page, 11);
  return { region: G.nodes[region], regionN: region, page: G.nodes[page], pageN: page, vol: G.nodes[vol] }; }"""


async def archive_shots(pg, tag):
    """Images of the archive nodes: page with outlines, text region, class grids, volume, subgraph thumbnails."""
    a = await pg.evaluate(JS_ARCH, SAME_ENTRY)
    await pg.evaluate(f"LKGC.go('/n/' + {a['page']!r})")
    await pg.wait_for_timeout(1500)
    await pg.screenshot(path=str(SHOTS / f"20a_{tag}_seite_scan_mit_regionen.png"))
    await pg.click("#v-node .arhint [data-page-open]")
    await pg.wait_for_timeout(900)
    await pg.screenshot(path=str(SHOTS / f"20b_{tag}_seite_grossansicht.png"))
    await pg.keyboard.press("Escape")
    await pg.evaluate(f"LKGC.go('/n/' + {a['region']!r})")
    await pg.wait_for_timeout(1500)
    await pg.screenshot(path=str(SHOTS / f"20c_{tag}_textregion.png"))
    for k, name in (("page", "20d_{}_klassen_seiten_bilder.png"), ("region", "20e_{}_klassen_quellregionen_bilder.png"), ("mmregion", "20f_{}_klassen_multimodale_regionen_bilder.png")):
        await pg.evaluate(f"LKGC.go('/c/{k}')")
        await pg.wait_for_timeout(400)
        await pg.click('#v-class [data-cmode="img"]')
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=str(SHOTS / name.format(tag)))
        await pg.click('#v-class [data-cmode="table"]')
    await pg.evaluate(f"LKGC.go('/n/' + {a['vol']!r})")
    await pg.wait_for_timeout(2200)
    await pg.screenshot(path=str(SHOTS / f"20g_{tag}_band_seiten.png"))
    await goto_entry(pg, SAME_ENTRY, 800)
    if not await pg.locator("#scanpane").is_visible():
        await pg.keyboard.press("s")
    await pg.click('#gtools [data-act="preset-all"]')
    await pg.wait_for_timeout(1500)
    await pg.screenshot(path=str(SHOTS / f"20h_{tag}_alles_zeigen_archivbilder.png"))
    await pg.click(f'#gsvg .nd[data-key="n{a["regionN"]}"] rect.b', position={"x": 40, "y": 10})
    await pg.wait_for_timeout(1000)
    await pg.screenshot(path=str(SHOTS / f"20i_{tag}_region_gewaehlt_scan_und_knoten.png"))
    await pg.click(f'#gsvg .nd[data-key="n{a["pageN"]}"] rect.b', position={"x": 40, "y": 10})
    await pg.wait_for_timeout(1000)
    await pg.screenshot(path=str(SHOTS / f"20j_{tag}_seite_gewaehlt_scan_und_knoten.png"))
    await pg.click('#gtools [data-act="preset-std"]')
    await pg.wait_for_timeout(300)
    print("shots 20", tag)


OUTREACH_ENTRY = "L17-e0132"     # machine changes of every kind, five records of all reliability levels, two pages
FIGURES_ENTRY = "L06-e0113"      # four photographs


async def explorer_shots(p):
    """The explorer build, the outreach file: overview, the entry with its Text tab (light, dark), hover cards on a machine
    change and on a bird name, the records, the Notes tab, the reliability filter, 1280 × 800, images, the original
    transcription. Written to shots_outreach next to the shots folder; the archive images to the shots folder."""
    if not check(EXPLORER_PAGE.exists(), f"the explorer build exists ({EXPLORER_PAGE.name})"):
        return []
    out = SHOTS.parent / "shots_outreach"
    out.mkdir(parents=True, exist_ok=True)
    b, pg, errs = await open_page(p, viewport=(1440, 900), url=EXPLORER_PAGE.as_uri())
    await pg.wait_for_timeout(500)
    await pg.screenshot(path=str(out / "01_overview.png"))
    await goto_entry(pg, OUTREACH_ENTRY, 1200)
    await pg.screenshot(path=str(out / "02_entry_text.png"))
    await pg.hover("#fnotes .xc >> nth=0")
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(out / "04_hover_machine_change.png"))
    await pg.hover("#fnotes .xb >> nth=0")
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(out / "05_hover_bird_name.png"))
    await pg.click("#fnotes .xb >> nth=0")
    await pg.mouse.move(700, 880)
    await pg.wait_for_timeout(600)
    await pg.evaluate("(() => { const b = document.querySelector('#pbody'); b.scrollTop = document.querySelector('#pbody .xrecs').offsetTop - 120; })()")
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(out / "06_records.png"))
    await pg.click('#ptabs [data-tab="check"]')
    await pg.wait_for_timeout(400)
    await pg.screenshot(path=str(out / "07_notes_tab.png"))
    await pg.click('#ptabs [data-tab="text"]')
    await pg.click('#qbar [data-qt="2"]')
    await pg.wait_for_timeout(800)
    await pg.screenshot(path=str(out / "08_reliability_below_25.png"))
    await pg.click('#qbar [data-qt="0"]')
    await pg.wait_for_timeout(500)
    await pg.click('#pbody [data-act="tlayer"][data-layer="orig"]')
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(out / "11_original_transcription.png"))
    await pg.click('#pbody [data-act="tlayer"][data-layer="final"]')
    await goto_entry(pg, FIGURES_ENTRY, 1200)
    await pg.evaluate("(() => { const b = document.querySelector('#pbody'); b.scrollTop = document.querySelector('#pbody .xmedia').offsetTop - 60; })()")
    await pg.wait_for_timeout(1200)
    await pg.screenshot(path=str(out / "10_images_and_inserts.png"))
    await pg.click("#btn-theme")
    await goto_entry(pg, OUTREACH_ENTRY, 1000)
    await pg.screenshot(path=str(out / "03_entry_text_dark.png"))
    await pg.evaluate("LKGC.go('/')")
    await pg.wait_for_timeout(600)
    await pg.screenshot(path=str(out / "12_overview_dark.png"))
    await pg.click("#btn-theme")
    await pg.set_viewport_size({"width": 1280, "height": 800})
    await goto_entry(pg, OUTREACH_ENTRY, 1000)
    await pg.screenshot(path=str(out / "09_entry_1280x800.png"))
    await pg.set_viewport_size({"width": 1440, "height": 900})
    print("outreach shots in", out)
    await archive_shots(pg, "explorer")
    await b.close()
    return errs


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p, viewport=(1440, 900))
        await pg.fill("#who", "T. Prüferin")
        await pg.keyboard.press("Escape")

        # 1 work list + graph with annotations; 4 scan with region and line; 2 table with chips
        eid = await find_entry(pg, f"(rv, s) => s.find.length >= 2 && s.miss.length >= 1 && s.auto.some(k => k.startsWith('name:')) && (rv.gone || []).length && {SMALL} && Object.values(rv.rec).some(r => r.loc && r.g && r.g.v === 'wrong' && r.g.fix && (r.g.fix.count || r.g.fix.locality))") \
            or await find_entry(pg, f"(rv, s) => s.find.length >= 1 && s.miss.length >= 1 && {SMALL} && Object.values(rv.rec).some(r => r.loc && r.g && r.g.v === 'wrong' && r.g.fix && (r.g.fix.count || r.g.fix.locality))")
        await goto_entry(pg, eid, 900)
        await focus_item(pg, "it => it.type === 'rec' && it.o.rec.loc && it.o.rec.g && it.o.rec.g.v === 'wrong'")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "01_arbeitsliste_graph_annotationen.png"))
        await pg.keyboard.press("g")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "02_tabelle_befund_chips.png"))
        await pg.keyboard.press("g")
        print("shots 01, 02", eid)
        eid = await find_entry(pg, "(rv, s) => (rv.reg || []).some(g => g[5]) && Object.values(rv.rec || {}).some(r => r.loc && r.loc[7] > r.loc[6] && r.g && r.g.v === 'wrong') && Object.keys(rv.rec).length <= 10")
        await goto_entry(pg, eid, 900)
        await focus_item(pg, "it => it.type === 'rec' && it.o.rec.loc && it.o.rec.loc[7] > it.o.rec.loc[6] && it.o.rec.g && it.o.rec.g.v === 'wrong'")
        await pg.wait_for_timeout(600)
        await pg.screenshot(path=str(SHOTS / "04_scan_region_zeile.png"))
        print("shot 04", eid)

        # 3 the check tab with each card type (scan hidden: more room for the cards)
        await card_shot(pg, "03a_pruefen_datensatz_beide_pruefungen.png", f"(rv) => Object.values(rv.rec || {{}}).some(r => r.g && r.s && r.g.v === 'wrong' && r.s.v === 'wrong') && {SMALL}", "it => it.type === 'rec' && it.o.rec.g && it.o.rec.s && it.o.rec.g.v === 'wrong' && it.o.rec.s.v === 'wrong'")
        await card_shot(pg, "03b_pruefen_fehlender_datensatz.png", f"(rv, s) => s.miss.length >= 1 && {SMALL} && (rv.miss || []).some(x => x.count && x.loc)", "it => it.type === 'miss'")
        await card_shot(pg, "03c_pruefen_automatische_namensaenderung.png", f"(rv, s) => s.auto.filter(k => k.startsWith('name:')).length >= 2 && {SMALL}", "it => it.type === 'name' && it.x.kind === 'changed'")
        await card_shot(pg, "03d_pruefen_lesekorrektur_eintragskopf.png", "(rv, s) => (rv.tc || []).some(c => c[2] && /[bn]/.test(c[5] || '') && (c[6] === 'wrong' || c[7] === 'wrong') && c[8]) && rv.ent && rv.ent.g && rv.ent.g.date_ok === false && s.tc.length <= 6", "it => it.type === 'tc' && it.lv >= 1")
        await card_shot(pg, "03e_pruefen_entfernt_hinweise.png", "(rv, s) => (rv.gone || []).some(g => g[0] === 'non_bird') && (rv.qa || []).length >= 2 && (rv.tc || []).length <= 4 && s.find.length <= 1", "it => it.type === 'qa'")
        await card_shot(pg, "03f_pruefen_texteinlage_abschluss.png", "(rv, s) => s.unread > 0 && s.find.length + s.miss.length <= 2 && (rv.tc || []).length <= 3", "it => it.type === 'media' && it.ins")
        # the multimodal regions of an entry (maps and photographs of volume 3), crops from the local folder
        eid = await find_entry(pg, "(rv, s, r) => r.id.startsWith('L03') && (rv.media || []).filter(x => x[1] === 'map' && x.length >= 7).length >= 2 && s.img >= 3 && (rv.reg || []).some(g => g[0] === rv.media[0][2])") or await find_entry(pg, "(rv, s) => s.img >= 3")
        await goto_entry(pg, eid, 700)
        if not await pg.locator("#scanpane").is_visible():
            await pg.keyboard.press("s")
        await focus_item(pg, "it => it.type === 'media' && it.x.length >= 7")
        await pg.evaluate("(() => { const el = document.querySelector('#pbody .rcard.focus'); const b = document.querySelector('#pbody'); b.scrollTop = Math.max(0, el.offsetTop - b.offsetTop - 34); })()")
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=str(SHOTS / "07_bilder_und_einlagen.png"))
        await pg.click("#pbody .rcard.t-media.focus .mthumb")
        await pg.wait_for_timeout(1200)
        await pg.screenshot(path=str(SHOTS / "08_bild_grossansicht.png"))
        await pg.keyboard.press("Escape")
        print("shots 07, 08", eid)

        # ---- final pass: properties, table columns, gravity levels, reliability filter
        # 09 an entry with "Alles zeigen": default zoom (legible, pan hint), and the whole graph with the work list hidden
        eid = await find_entry(pg, "(rv, s, r) => r.nobs >= 3 && r.nobs <= 5 && s.find.length >= 1 && (rv.media || []).length >= 1 && (rv.reg || []).length >= 1 && s.auto.some(k => k.startsWith('name:'))") \
            or await find_entry(pg, "(rv, s, r) => r.nobs >= 3 && r.nobs <= 5 && s.find.length >= 1 && (rv.reg || []).length >= 1")
        await goto_entry(pg, eid, 700)
        await pg.click('#gtools [data-act="preset-all"]')
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "09a_alles_zeigen.png"))
        await pg.click('#ehead [data-act="list"]')
        await pg.keyboard.press("s")
        await pg.wait_for_timeout(300)
        await pg.click('#gtools [data-act="fit"]')
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "09b_alles_zeigen_ganzer_graph.png"))
        await pg.click('#gtools [data-act="preset-std"]')
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "09c_standard_eigenschaften.png"))
        print("shots 09", eid)
        # 10 the records table with all columns (work list hidden: more columns in view)
        eid = await find_entry(pg, f"(rv, s) => s.find.length >= 2 && {SMALL} && Object.values(rv.rec).some(r => r.g && r.g.v === 'wrong' && r.g.fix && r.g.fix.count) && Object.values(rv.rec).some(r => r.g && (r.g.f || []).some(f => ['evidence', 'call', 'behav', 'notes'].includes(f)))") \
            or await find_entry(pg, f"(rv, s) => s.find.length >= 2 && {SMALL}")
        await goto_entry(pg, eid, 600)
        await pg.keyboard.press("g")
        await pg.wait_for_timeout(300)
        await pg.click('#gtools [data-act="cols"]')
        await pg.click('#colpop [data-cp="all"]')
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "10a_tabelle_spaltenwahl.png"))
        await pg.click('#colpop [data-cp="close"]')
        await pg.evaluate("document.querySelector('#rtable').scrollLeft = 0")
        await pg.wait_for_timeout(200)
        await pg.screenshot(path=str(SHOTS / "10b_tabelle_alle_spalten.png"))
        await pg.evaluate("document.querySelector('#rtable').scrollLeft = 900")
        await pg.wait_for_timeout(200)
        await pg.screenshot(path=str(SHOTS / "10c_tabelle_alle_spalten_rechts.png"))
        await pg.click('#gtools [data-act="cols"]')
        await pg.click('#colpop [data-cp="def"]')
        await pg.click('#colpop [data-cp="close"]')
        await pg.keyboard.press("g")
        await pg.click('#ehead [data-act="list"]')
        await pg.keyboard.press("s")
        print("shots 10", eid)
        # 11 the work list sorted by gravity with the level pills; 12 the check tab with items of different levels
        await pg.evaluate("LKGC.setQueue('all', false)")
        eid = await find_entry(pg, "(rv, s, r) => { const c = LKGC.openLevels(s); return c[3] >= 2 && c[2] >= 2 && c[1] >= 1 && r.nobs <= 14 && s.find.length >= 2 && new Set(s.lv.map(x => x[2])).size >= 4; }")
        await goto_entry(pg, eid, 600)
        await pg.evaluate("document.querySelector('#elist-body').scrollTop = 0")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "11_arbeitsliste_nach_schwere.png"))
        await pg.keyboard.press("s")
        await pg.evaluate("LKGC.focusCard(0)")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "12a_pruefen_nach_schwere.png"))
        await pg.evaluate("(() => { const h = [...document.querySelectorAll('#pbody h3.lvh')][1]; const b = document.querySelector('#pbody'); if (h) b.scrollTop = h.offsetTop - b.offsetTop - 180; })()")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "12b_pruefen_mittel_leicht.png"))
        await pg.evaluate("(() => { const a = document.querySelector('#pbody [data-act=hints]'); if (a) a.click(); })()")
        await pg.wait_for_timeout(200)
        await pg.evaluate("(() => { const h = [...document.querySelectorAll('#pbody h3.lvh')].pop(); const b = document.querySelector('#pbody'); if (h) b.scrollTop = h.offsetTop - b.offsetTop - 260; })()")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "12c_pruefen_leicht_hinweise.png"))
        await pg.keyboard.press("s")
        await pg.evaluate("LKGC.setQueue('finding', false)")
        print("shots 11, 12", eid)
        # 13 "Datensatz < 25 %" active: an entry (hidden records, then shown dimmed), 14 a taxon node view, 15 the overview
        await pg.click('#qbar [data-qt="2"]')
        await pg.wait_for_timeout(600)
        eid = await find_entry(pg, "(rv, s, r) => s.qn >= 3 && r.nobs - s.qn >= 2 && r.nobs <= 9 && Object.values(rv.rec || {}).some(x => x.q && x.q.lv > 2 && (x.g || {}).v === 'wrong')")
        await goto_entry(pg, eid, 700)
        await pg.screenshot(path=str(SHOTS / "13a_unter_25_eintrag.png"))
        await pg.click('#gtools [data-act="showout"]')
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "13b_unter_25_ausserhalb_gezeigt.png"))
        await pg.keyboard.press("g")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "13c_unter_25_tabelle.png"))
        await pg.keyboard.press("g")
        tx = await pg.evaluate("LKGC.G.nodes[LKGC.stats().taxa[4].n]")
        await pg.evaluate(f"LKGC.go('/n/' + {tx!r})")
        await pg.wait_for_timeout(900)
        await pg.screenshot(path=str(SHOTS / "14_unter_25_taxon.png"))
        await pg.evaluate("LKGC.go('/c/taxon')")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "14b_unter_25_klasse_taxa.png"))
        await pg.evaluate("LKGC.go('/')")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=str(SHOTS / "15a_uebersicht_unter_25.png"))
        await pg.evaluate("LKGC.setQFilter('p', 0)")
        await pg.wait_for_timeout(600)
        print("shots 13, 14, 15a", eid)

        # ---- 17 the reliability bar (always under the header) in the review build; 18a the entry both builds are compared on
        await pg.evaluate("LKGC.go('/')")
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(SHOTS / "17a_verlaesslichkeit_pruefung_uebersicht.png"))
        await pg.select_option("#qmsel", "pl")
        await pg.click('#qbar [data-qt="2"]')
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(SHOTS / "17c_verlaesslichkeit_ort_unter_25.png"))
        await pg.select_option("#qmsel", "p")
        await pg.click('#qbar [data-qt="0"]')
        await pg.wait_for_timeout(500)
        await entry_shot(pg, "18a_pruefung_eintrag_L17-e0132.png")
        await pg.click('#qbar [data-qt="2"]')
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(SHOTS / "17b_verlaesslichkeit_pruefung_eintrag_unter_25.png"))
        await pg.click('#qbar [data-qt="0"]')
        await pg.wait_for_timeout(500)
        print("shots 17, 18a")
        await archive_shots(pg, "pruefung")
        # a decided entry: 'von dir entschieden' on cards, nodes and in the list
        eid = await find_entry(pg, f"(rv, s) => s.find.length >= 2 && {SMALL} && Object.values(rv.rec).filter(r => r.g && r.g.v === 'wrong' && r.g.fix && (r.g.fix.count || r.g.fix.locality)).length >= 2")
        await goto_entry(pg, eid, 600)
        if not await pg.locator("#scanpane").is_visible():
            await pg.keyboard.press("s")
        await pg.evaluate("LKGC.focusCard(0)")
        for key in ("j", "n", "x"):
            await pg.keyboard.press(key)
            await pg.wait_for_timeout(250)
            if await pg.locator("#pbody .rform").count():
                await pg.keyboard.press("Escape")
                await pg.keyboard.press("n")
                await pg.wait_for_timeout(250)
        await pg.evaluate("LKGC.focusCard(0)")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / "06_von_dir_entschieden.png"))
        print("shot 06", eid)

        # 5 overview (with the decisions just made)
        await pg.evaluate("LKGC.go('/')")
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(SHOTS / "05_uebersicht.png"))
        await pg.evaluate("(() => { const d = document.querySelector('#rv-ov details.sevcard'); d.open = true; d.scrollIntoView({ block: 'start' }); })()")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "15b_uebersicht_regeln_der_schwere.png"))
        await pg.evaluate("document.querySelector('#v-overview').scrollTop = 0")
        await pg.click("#btn-theme")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "16a_dunkel_uebersicht.png"))
        await pg.evaluate("LKGC.go('/e/' + LKGC.RVU.list[0].id)")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=str(SHOTS / "16b_dunkel_eintrag.png"))
        await pg.click("#btn-lang")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(SHOTS / "16c_dark_entry_english.png"))
        await pg.click("#btn-help")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "16d_help_english.png"))
        await b.close()
        done(errs + await explorer_shots(p))

asyncio.run(main())
