"""Playwright smoke test of the Laubmann-Abgleich UI (not part of the pytest suite).

    HOG_UI=Laubmann_Abgleich.html [HOG_BROWSER=<chromium/edge exe>] [HOG_PAGES=<HistOrniGraph_output>] \
        python tools/validation_ui/tests/smoke_abgleich.py

HOG_PAGES (optional): the Drive folder with Laubmann_XX_gemini/pages/*.png; Drive
thumbnail requests are then answered from these files, so line images and
scans render without a Google login. HOG_V1 (optional): a backup JSON of the
first UI version to import. The exported CSVs are fed through the pipeline's
loaders (round trip).
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

        async def open_ent(t, label):
            await H("""([t, label]) => { const h = window.__hog; const e = h.X[t].ents.find(x => x.label === label);
                if (h.cur.tab !== t) h.openTab(t); h.selectItem(e); }""", [t, label])
            await pg.wait_for_timeout(400)

        # entity ✓, then the focus moves to the first open name; N + 1 rejects it; Z undoes
        await open_ent("taxon", "Gimpel")
        await pg.keyboard.press("y")
        assert await H("window.__hog.cur.focus.startsWith('n:')")
        await pg.keyboard.press("n")
        await pg.keyboard.press("1")
        assert len(await H("Object.keys(window.__hog.S.id.taxon)")) == 1
        await pg.keyboard.press("z")
        assert len(await H("Object.keys(window.__hog.S.id.taxon)")) == 0
        # a name reassigned by keyboard: A, type, Enter
        await H("""() => { const h = window.__hog; const nm = h.X.taxon.names.find(n => n.name === 'Kameradeneingang'); h.setFocus('n:' + nm.fi); }""")
        await pg.keyboard.press("a")
        await pg.keyboard.type("Hausrot")
        await pg.wait_for_timeout(300)
        await pg.keyboard.press("Enter")
        d = await H("window.__hog.S.id.taxon['kameradeneingang']")
        assert d["d"] == "r" and d["target"]["sci"] == "Phoenicurus ochruros", d
        # reading editor opened with E: the key must not be typed into the text
        await H("""() => { const h = window.__hog; const nm = h.X.taxon.names.find(n => n.name === 'Kameradeneingang'); h.setFocus('m:' + nm.men[0]); }""")
        await pg.keyboard.press("e")
        await pg.wait_for_timeout(500)
        sel = await H("() => { const ta = document.querySelector('#edtext'); return ta.value.slice(ta.selectionStart, ta.selectionEnd); }")
        assert sel == "Kameradeneingänge", sel
        await pg.keyboard.type("Hausrotschwänzchen")
        await pg.keyboard.press("Control+Enter")
        rd = await H("window.__hog.S.text.map(c => [c.old, c.new])")
        assert rd == [["Kameradeneingänge", "Hausrotschwänzchen"]], rd
        await pg.screenshot(path=str(SHOTS / "gimpel.png"))
        # second reading accepted with G (a mention whose suggestion names another species of the graph)
        acc = await H("""() => { const h = window.__hog; for (const e of h.X.taxon.ents) for (const nm of e.names) for (const mi of nm.men) { const s = h.SUG[mi];
            if (s && s[2] === 'bird' && s[7] >= 0 && s[7] !== nm.ent) { h.selectItem(e); h.setFocus('m:' + mi); return mi; } } return -1; }""")
        if acc >= 0:
            await pg.keyboard.press("g")
            assert await H(f"(() => {{ const h = window.__hog; return !!h.S.men.taxon[h.X.taxon.mkey[{acc}]]; }})()")
        # scan: second page of a multi-page entry
        await H("() => { const h = window.__hog; h.showScan(h.P.E.findIndex(e => e[8].length > 2)); }")
        await pg.wait_for_timeout(600)
        await pg.click("#scanpages button:nth-child(2)")
        await pg.wait_for_timeout(600)
        assert "Seite 2/" in await pg.text_content("#scantitle")
        # person link, place coordinate, habitat, sample, hints, log
        await open_ent("person", "Walter Wüst")
        if await pg.query_selector('.cand[data-qid="Q2546836"]'):
            await pg.click('.cand[data-qid="Q2546836"]')
            assert (await H("window.__hog.S.ent.person['Walter Wüst']"))["qid"] == "Q2546836"
        await open_ent("place", "Englischer Garten")
        await pg.fill("#ll", "48.1642, 11.6056")
        await pg.click("#llbtn")
        assert (await H("window.__hog.S.ent.place['Englischer Garten']"))["fix"]["lat"] == "48.16420"
        for tab in ("habitat", "eval", "qa", "log"):
            await pg.click(f'.tab[data-tab="{tab}"]')
            await pg.wait_for_timeout(500)
            await pg.screenshot(path=str(SHOTS / f"{tab}.png"))
        if os.environ.get("HOG_V1"):
            await pg.set_input_files("#fileImport", os.environ["HOG_V1"])
            await pg.wait_for_timeout(800)
        ex = await H("({ id: window.__hog.exportIdentities(), men: window.__hog.exportMentions(), text: window.__hog.exportText() })")
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
    assert not errs, errs
    print(f"ok: {n_loaded} identities, round trip clean; screenshots in {SHOTS}")


asyncio.run(main())
