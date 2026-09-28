"""Playwright smoke test of the Abgleich UI (not part of the pytest suite).

    HOG_UI=HistOrniGraph_Abgleich.html [HOG_BROWSER=<chromium/edge exe>] [HOG_PAGES=<HistOrniGraph_output>] \
        python tools/validation_ui/tests/smoke_abgleich.py

HOG_PAGES (optional): the Drive folder with Laubmann_XX_gemini/pages/*.png; Drive
thumbnail requests are then answered from these files, so line images and
scans render without a Google login. HOG_V1 (optional): a backup JSON of the
first UI version to import. The exported CSVs are fed through the pipeline's
loaders (round trip).
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
URL = Path(os.environ.get("HOG_UI", "HistOrniGraph_Abgleich.html")).resolve().as_uri()
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
        pg = await (await b.new_context(viewport={"width": 1600, "height": 1000})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errs.append(m.text))
        if prefix:
            await pg.route("**/drive.google.com/thumbnail**", thumbnail)
        await pg.goto(URL)
        await pg.wait_for_selector("#loading", state="detached", timeout=120000)
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await pg.wait_for_selector("#loading", state="detached", timeout=120000)
        await pg.wait_for_timeout(800)
        await pg.keyboard.press("Escape")
        await pg.fill("#who", "Test")

        async def open_form(task, name):
            await pg.click(f'.task[data-t="{task}"]')
            await pg.evaluate("t => { window.__hog.S.ui.chips[t] = ['A','B','C','L','V','K','W','E','R','N','G']; }", task)
            await pg.click(f'.task[data-t="{task}"]')
            await pg.select_option("#qshow", "all")
            await pg.fill("#qsearch", name)
            await pg.wait_for_timeout(500)
            labels = await pg.eval_on_selector_all("#qlist .qi .l1", "els => els.map(e => e.textContent)")
            await pg.click(f'#qlist .qi[data-p="{labels.index(name)}"]')

        # name form reassigned to another species
        await open_form("taxon", "Kameradeneingang")
        await pg.keyboard.press("a")
        await pg.fill("#detail .rpanel .rq", "Hausrot")
        await pg.wait_for_timeout(300)
        await pg.click('#detail .rpanel .rres .r[data-k="0"]')
        d = await pg.evaluate("window.__hog.S.id.taxon['kameradeneingang']")
        assert d["d"] == "r" and d["target"]["sci"] == "Phoenicurus ochruros", d
        # mentions decided one by one, one reading corrected
        await open_form("taxon", "Tirol")
        await pg.keyboard.press("e")
        await pg.click('#detail .psg >> nth=0 >> [data-md="r"]')
        await pg.fill("#detail .psg >> nth=0 >> .rq", "Pirol")
        await pg.wait_for_timeout(300)
        await pg.click('#detail .psg >> nth=0 >> .rres .r[data-k="0"]')
        await pg.click('#detail .psg >> nth=1 >> [data-md="n"]')
        await pg.click('#detail .psg >> nth=1 >> [data-reason="misread"]')
        await pg.click('#detail .psg >> nth=0 >> [data-md="text"]')
        await pg.fill("#detail .psg >> nth=0 >> .c-new", "Pirol")
        await pg.click("#detail .psg >> nth=0 >> .c-save")
        await pg.screenshot(path=str(SHOTS / "tirol.png"))
        assert len(await pg.evaluate("Object.keys(window.__hog.S.men.taxon)")) == 2
        # scan viewer: the second page of a multi-page entry
        mi = await pg.evaluate("""() => { const h = window.__hog; for (const it of h.M.taxon.items) for (const mi of it.men) {
            const m = h.P.taxon.men[mi]; if (h.P.E[m[1]][8].length > 1) { h.openScan(m[1], h.P.E[m[1]][8][0], null); return mi; } } return -1; }""")
        assert mi >= 0
        await pg.click("#scanpages button:nth-child(2)")
        await pg.wait_for_timeout(800)
        assert "Seite 2 von" in await pg.text_content("#scantitle")
        await pg.screenshot(path=str(SHOTS / "scan_page2.png"))
        await pg.keyboard.press("Escape")
        # other queues render
        for task in ("person", "place", "habitat", "eval", "qa"):
            await pg.click(f'.task[data-t="{task}"]')
            await pg.wait_for_timeout(600)
            await pg.screenshot(path=str(SHOTS / f"{task}.png"))
        # v1 import
        if os.environ.get("HOG_V1"):
            await pg.set_input_files("#fileImport", os.environ["HOG_V1"])
            await pg.wait_for_timeout(800)
        ex = await pg.evaluate("({ id: window.__hog.exportIdentities(), men: window.__hog.exportMentions(), text: window.__hog.exportText() })")
        await b.close()

    # round trip through the pipeline loaders
    from laubmann_kg.normalization.corrections import load_corrections
    from laubmann_kg.review.identities import Identities
    from laubmann_kg.review.readings import load_readings
    tmp = Path(tempfile.mkdtemp())
    for name, key in (("identities.csv", "id"), ("value_corrections.csv", "men"), ("text_corrections.csv", "text")):
        (tmp / name).write_text(ex[key], encoding="utf-8")
    import csv as _csv
    count = lambda name: sum(1 for _ in _csv.DictReader((tmp / name).open(encoding="utf-8")))   # noqa: E731 (notes may hold line breaks)
    ids = Identities.load(tmp / "identities.csv")
    n_rows = count("identities.csv")
    n_loaded = sum(len(v) for v in ids.forms.values()) + sum(len(v) for v in ids.links.values())
    assert n_loaded == n_rows, (n_loaded, n_rows)
    assert len(load_corrections(tmp / "value_corrections.csv")) == count("value_corrections.csv")
    assert len(load_readings(tmp / "text_corrections.csv")) == count("text_corrections.csv")
    assert not errs, errs
    print(f"ok: {n_rows} identities, round trip clean; screenshots in {SHOTS}")


asyncio.run(main())
