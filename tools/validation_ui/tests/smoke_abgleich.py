"""Playwright smoke test of the Laubmann-Abgleich UI v4 (not part of the pytest suite).

    HOG_UI=Laubmann_Abgleich.html [HOG_BROWSER=<chromium/edge exe>] [HOG_PAGES=<HistOrniGraph_output>] \
        python tools/validation_ui/tests/smoke_abgleich.py

HOG_PAGES (optional): the Drive folder with Laubmann_XX_gemini/pages/*.png; Drive
thumbnail requests are then answered from these files, so line images and
scans render without a Google login. HOG_V1 (optional): a backup JSON of the
first UI version to import. The exported CSVs are fed through the pipeline's
loaders (round trip). Screenshots of every task go to HOG_SHOTS (default shots/).
"""
import asyncio
import csv
import json
import os
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
URL = Path(os.environ.get("HOG_UI", "Laubmann_Abgleich.html")).resolve().as_uri()
SHOTS = Path(os.environ.get("HOG_SHOTS", "shots"))
PAGES = os.environ.get("HOG_PAGES")
SHOTS.mkdir(parents=True, exist_ok=True)
drive = json.loads((HERE.parent / "drive_pages.json").read_text(encoding="utf-8"))
by_id = {v: k for k, v in drive.items()}
prefix = {}
if PAGES:
    for vol in Path(PAGES).glob("Laubmann_*_gemini"):
        first = next((vol / "pages").glob("*.png"), None) if (vol / "pages").is_dir() else None
        if first:
            prefix[first.name.split("_")[0]] = vol / "pages"


async def thumbnail(route):
    from urllib.parse import parse_qs, urlparse
    pid = by_id.get(parse_qs(urlparse(route.request.url).query).get("id", [""])[0])
    f = pid and prefix.get(pid.split("_")[0]) and prefix[pid.split("_")[0]] / f"{pid}.png"
    if f and f.exists():
        return await route.fulfill(status=200, content_type="image/png", body=f.read_bytes())
    return await route.fulfill(status=404, body="")


async def main():
    async with async_playwright() as p:
        exe = os.environ.get("HOG_BROWSER")
        b = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 1680, "height": 1000})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errs.append(m.text))
        if prefix:
            await pg.route("**/drive.google.com/thumbnail**", thumbnail)
        for host in ("api.gbif.org", "www.wikidata.org", "lobid.org", "nominatim.openstreetmap.org", "server.arcgisonline.com"):
            await pg.route(f"**://{host}/**", lambda r: r.abort())
        await pg.goto(URL)
        await pg.wait_for_selector("#loading", state="detached", timeout=120000)
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await pg.wait_for_selector("#loading", state="detached", timeout=120000)
        await pg.wait_for_timeout(900)
        await pg.fill("#hwho", "Test")
        await pg.keyboard.press("Escape")
        H = pg.evaluate

        async def shot(name):
            await pg.wait_for_timeout(700)
            await pg.screenshot(path=str(SHOTS / f"{name}.png"))

        async def open_ent(tab, t, label):
            ok = await H("""([tab, t, label]) => { const h = window.__hog; const e = h.X[t].ents.find(x => x.label === label); if (!e) return false;
                h.cur.type = t; h.S.ui.type[tab] = t; h.S.ui.show[tab] = 'all'; h.openTab(tab, t + ':' + e.i); return h.cur.sel === e; }""", [tab, t, label])
            assert ok, (tab, t, label)
            await pg.wait_for_timeout(400)

        # --- Prüfen: a linked taxon; Y confirms; unchecking a name asks where it belongs
        await open_ent("check", "taxon", "Gimpel")
        await shot("check_taxon")
        await pg.keyboard.press("y")
        assert (await H("window.__hog.S.ent.taxon['Gimpel']"))["d"] == "y"
        nm = await H("""() => { const h = window.__hog; const e = h.cur.sel; const n = e.names.find(x => !h.nameState('taxon', x)) || e.names[e.names.length - 1]; return [n.fi, n.key]; }""")
        await pg.click(f'.nm[data-fi="{nm[0]}"] .cb')
        d = await H(f"window.__hog.S.id.taxon[{json.dumps(nm[1])}]")
        assert d and d["d"] == "o", d
        await pg.click(f'.nm[data-fi="{nm[0]}"] [data-nreassign]')
        await pg.keyboard.type("Hausrot")
        await pg.wait_for_timeout(300)
        await pg.keyboard.press("Enter")
        d = await H(f"window.__hog.S.id.taxon[{json.dumps(nm[1])}]")
        assert d["d"] == "r" and d["target"]["sci"] == "Phoenicurus ochruros", d
        await shot("check_taxon_name")
        await pg.keyboard.press("z")
        assert (await H(f"window.__hog.S.id.taxon[{json.dumps(nm[1])}]"))["d"] == "o"
        # reading editor opened with ✎ on a mention card: the typed key must not land in the text
        await pg.click(f'.nm[data-fi="{nm[0]}"] [data-toggle]')
        await pg.wait_for_timeout(300)
        await pg.click(f'.nm[data-fi="{nm[0]}"] .men [data-ma="e"]')
        await pg.wait_for_timeout(500)
        assert await pg.query_selector("#edtext")
        await pg.keyboard.press("Escape")

        # --- Verknüpfen: an unlinked taxon with a merge suggestion; ⇧A merges it
        got = await H("""() => { const h = window.__hog; h.cur.type = 'taxon'; h.S.ui.type.link = 'taxon'; h.openTab('link');
            for (let p = 0; p < h.cur.list.length; p++) { const e = h.cur.list[p]; if ((h.CAND.taxon.nc[e.names[0].fi] || []).length) { h.selectItem(e); return e.label; } } return null; }""")
        await pg.wait_for_timeout(400)
        await shot("link_taxon")
        if got:
            assert await pg.query_selector(".cand[data-merge]"), "merge suggestions expected"
            await pg.keyboard.press("Shift+A")
            d = await H(f"window.__hog.S.ent.taxon[{json.dumps(got)}]")
            assert d and d["d"] == "r" and d["target"]["label"], d
        # GBIF panel via A on an unlinked taxon (network is blocked: the panel must still open)
        await pg.keyboard.press("a")
        await pg.wait_for_timeout(200)
        assert await pg.query_selector('.rpanel[data-scope="e"] .rq')
        await pg.keyboard.press("Escape")

        # --- Namen: an entity with incoming candidates; checking one moves the name here; Y confirms the group
        got = await H("""() => { const h = window.__hog; h.cur.type = 'taxon'; h.S.ui.type.names = 'taxon'; h.openTab('names');
            for (let p = 0; p < h.cur.list.length; p++) { const e = h.cur.list[p]; if ((h.CAND.taxon.ec[e.i] || []).length) { h.selectItem(e); return e.label; } } return null; }""")
        await pg.wait_for_timeout(400)
        await shot("names_taxon")
        if got:
            inc = await H("() => { const r = document.querySelector('.nm[data-inc=\"1\"]'); return r ? [+r.dataset.fi, window.__hog.X.taxon.names[+r.dataset.fi].key] : null; }")
            assert inc, "incoming name row expected"
            await pg.click(f'.nm[data-fi="{inc[0]}"][data-inc="1"] .cb')
            d = await H(f"window.__hog.S.id.taxon[{json.dumps(inc[1])}]")
            assert d and d["d"] == "r" and d["target"]["label"] == got, d
            await pg.keyboard.press("y")
            assert (await H(f"window.__hog.S.grp.taxon[{json.dumps(got)}]"))["d"] == "y"
            # search box adds any name of the graph
            await pg.fill('.rpanel[data-scope="add"] .rq', "Dompfaff")
            await pg.wait_for_timeout(300)
            await shot("names_taxon_add")

        # --- Lesefehler: first item; 1 accepts the first differing model reading; E lets the reviewer type the word
        await pg.click('.tab[data-tab="read"]')
        await pg.wait_for_timeout(600)
        await shot("read")
        key = await H("window.__hog.cur.sel && window.__hog.cur.sel.key")
        assert key
        n_text = await H("window.__hog.S.text.length")
        await pg.keyboard.press("1")
        d = await H(f"window.__hog.S.men.taxon[{json.dumps(key)}]")
        assert d and d["d"] in ("y", "r", "n"), d
        await shot("read_accepted")
        await pg.click('[data-ra=""]')
        assert not await H(f"window.__hog.S.men.taxon[{json.dumps(key)}]")
        assert await H("window.__hog.S.text.length") == n_text
        await pg.keyboard.press("e")
        await pg.wait_for_timeout(200)
        await pg.fill("#wordfix", "Gimpel")
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(300)
        d = await H(f"window.__hog.S.men.taxon[{json.dumps(key)}]")
        assert d and d["d"] in ("y", "r"), d
        assert await H("window.__hog.S.text.length") == n_text + 1
        await pg.keyboard.press("y")   # Y after a correction: transcription right again -> hunk removed
        await pg.wait_for_timeout(200)

        # --- scan: second page of a multi-page entry
        await H("() => { const h = window.__hog; h.showScan(h.P.E.findIndex(e => e[8].length > 2)); }")
        await pg.wait_for_timeout(600)
        await pg.click("#scanpages button:nth-child(2)")
        await pg.wait_for_timeout(600)
        assert "Seite 2/" in await pg.text_content("#scantitle")

        # --- persons: candidate click, model suggestion box; places: coordinates; habitats
        await open_ent("check", "person", "Walter Wüst")
        await shot("check_person")
        if await pg.query_selector('.cand[data-qid="Q2546836"]'):
            await pg.click('.cand[data-qid="Q2546836"]')
            assert (await H("window.__hog.S.ent.person['Walter Wüst']"))["qid"] == "Q2546836"
        got = await H("""() => { const h = window.__hog; h.cur.type = 'person'; h.S.ui.type.link = 'person'; h.openTab('link');
            for (let p = 0; p < h.cur.list.length; p++) { const e = h.cur.list[p]; if (h.PM[e.i] && /^Q/.test(h.PM[e.i][0])) { h.selectItem(e); return e.label; } } return null; }""")
        await pg.wait_for_timeout(400)
        await shot("link_person")
        if got:
            assert await pg.query_selector(".modelbox")
            await pg.keyboard.press("y")   # confirms the model's candidate
            d = await H(f"window.__hog.S.ent.person[{json.dumps(got)}]")
            assert d and d["d"] == "y" and d["qid"], d
        await open_ent("link", "place", "Englischer Garten")   # 446 mentions without coordinates
        await pg.fill("#ll", "48.1642, 11.6056")
        await pg.click("#llbtn")
        assert (await H("window.__hog.S.ent.place['Englischer Garten']"))["fix"]["lat"] == "48.16420"
        await shot("check_place")
        await H("() => { const h = window.__hog; h.cur.type = 'habitat'; h.S.ui.type.check = 'habitat'; h.openTab('check'); }")
        await pg.wait_for_timeout(400)
        await shot("check_habitat")
        await pg.keyboard.press("y")
        for tab in ("eval", "qa", "log"):
            await pg.click(f'.tab[data-tab="{tab}"]')
            await pg.wait_for_timeout(500)
            if tab == "eval":
                await pg.keyboard.press("y")
            await shot(tab)
        if os.environ.get("HOG_V1"):
            await pg.set_input_files("#fileImport", os.environ["HOG_V1"])
            await pg.wait_for_timeout(1200)
        ex = await H("({ id: window.__hog.exportIdentities(), men: window.__hog.exportMentions(), text: window.__hog.exportText(), rd: window.__hog.exportReadings() })")
        await b.close()

    # round trip through the pipeline loaders
    from laubmann_kg.normalization.corrections import load_corrections
    from laubmann_kg.review.identities import Identities
    from laubmann_kg.review.readings import load_readings
    tmp = Path(tempfile.mkdtemp())
    for name, key in (("identities.csv", "id"), ("value_corrections.csv", "men"), ("text_corrections.csv", "text")):
        (tmp / name).write_text(ex[key], encoding="utf-8")
    count = lambda name: sum(1 for _ in csv.DictReader((tmp / name).open(encoding="utf-8")))   # noqa: E731 (notes may hold line breaks)
    ids = Identities.load(tmp / "identities.csv")
    n_loaded = sum(len(v) for v in ids.forms.values()) + sum(len(v) for v in ids.links.values())
    assert n_loaded == count("identities.csv"), (n_loaded, count("identities.csv"))
    assert len(load_corrections(tmp / "value_corrections.csv")) == count("value_corrections.csv")
    assert len(load_readings(tmp / "text_corrections.csv")) == count("text_corrections.csv")
    assert ex["rd"].count("\n") > 1
    assert not errs, errs
    print(f"ok: {n_loaded} identities, round trip clean; screenshots in {SHOTS}")


asyncio.run(main())
