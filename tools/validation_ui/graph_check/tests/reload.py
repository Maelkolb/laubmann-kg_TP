"""Persistence: decisions survive a reload (localStorage), Z undoes them one by one, the progress JSON
and the export ZIP load into a fresh browser profile and re-export the same files; newer decisions win
when progress is merged."""
import asyncio
import base64
import json
from playwright.async_api import async_playwright
from common import SHOTS, check, done, find_entry, goto_entry, open_page, reload

CSVS = ["review/observation_corrections.csv", "review/value_corrections.csv", "review/transcript_decisions.csv", "review/qa_decisions.csv", "review/identities.csv", "entry_checks.csv", "graph_audit.csv"]


async def decide_some(pg):
    """A few decisions by keyboard in one entry with findings; returns the entry id."""
    eid = await find_entry(pg, "(rv, s) => s.find.length >= 2 && s.lv.some(x => x[2] === 'tc') && Object.keys(rv.rec || {}).length <= 25")
    await goto_entry(pg, eid)
    await pg.evaluate("LKGC.focusCard(0)")
    for key in ("j", "n"):                                 # the first two cards are records with findings
        await pg.keyboard.press(key)
        await pg.wait_for_timeout(220)
        if await pg.locator("#pbody .rform").count():      # J opened the form (a proposal in a format the pipeline cannot read)
            await pg.keyboard.press("Escape")
            await pg.keyboard.press("n")
            await pg.wait_for_timeout(220)
    i = await pg.evaluate("(() => { const items = LKGC.visibleItems(LKGC.EM); const i = items.findIndex(it => it.type === 'tc' && !LKGC.RV.dec[it.key]); if (i >= 0) LKGC.focusCard(i); return i; })()")
    if i >= 0:
        await pg.keyboard.press("j")
        await pg.wait_for_timeout(220)
    return eid


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        await pg.fill("#who", "TEST")
        await pg.keyboard.press("Escape")
        eid = await decide_some(pg)
        n = await pg.evaluate("Object.keys(LKGC.RV.dec).length")
        check(n >= 3, f"{n} decisions made by keyboard in {eid}")
        before = await pg.evaluate("JSON.stringify(LKGC.RV.dec)")

        # undo, one by one
        await pg.keyboard.press("z")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == n - 1, "Z undoes the last decision")
        await pg.keyboard.press("z")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == n - 2, "Z again undoes the one before")
        for _ in range(n + 2):
            await pg.keyboard.press("z")
            await pg.wait_for_timeout(120)
        check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == 0, "undo back to the start; further Z does nothing")
        check(await pg.locator("#pbody .rcard.done").count() == 0 and await pg.locator("#gsvg .nd.an-dec").count() == 0, "cards and nodes are open again")
        await decide_some(pg)
        check(await pg.evaluate("JSON.stringify(Object.keys(LKGC.RV.dec).sort())") == json.dumps(sorted(json.loads(before)), separators=(",", ":"), ensure_ascii=False), "the same decisions again")

        # mark the entry as checked, reload
        n_items = await pg.evaluate("LKGC.visibleItems(LKGC.EM).length")
        await pg.evaluate(f"LKGC.focusCard({n_items - 1})")
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(200)
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(300)
        uid = await pg.evaluate("LKGC.EM.uid")
        check(await pg.evaluate(f"!!(LKGC.RV.dec['entry:{uid}'] || {{}}).checked"), "entry marked as checked")
        await pg.wait_for_timeout(600)          # debounced save
        ndec = await pg.evaluate("Object.keys(LKGC.RV.dec).length")
        files = dict(await pg.evaluate("LKGC.exportFiles()"))
        zip_b64 = await pg.evaluate("(async () => { const buf = new Uint8Array(await LKGC.makeZip(LKGC.exportFiles()).arrayBuffer()); let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000)); return btoa(s); })()")
        await reload(pg)
        check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == ndec, "decisions survive a reload")
        check(await pg.evaluate("LKGC.RV.who") == "TEST" and await pg.input_value("#who") == "TEST", "the reviewer name survives a reload")
        check(await pg.evaluate("LKGC.RVU.counts.done.n") == 1, "the checked entry is counted after the reload")
        await goto_entry(pg, eid)
        check(await pg.locator("#pbody .rcard.done").count() >= 3 and await pg.locator("#ehead .hstate.ok").count() == 1, "the entry shows the decisions and the checked state after the reload")
        await pg.screenshot(path=str(SHOTS / "r_decided_entry.png"))
        await b.close()

        # progress JSON into a fresh profile
        pj = SHOTS / "progress_roundtrip.json"
        pj.write_text(files["graph_progress.json"], encoding="utf-8")
        pz = SHOTS / "progress_roundtrip.zip"
        pz.write_bytes(base64.b64decode(zip_b64))
        for path, what in ((pj, "JSON"), (pz, "ZIP")):
            b, pg, errs2 = await open_page(p)
            errs += errs2
            check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == 0, f"[{what}] a fresh profile starts empty")
            await pg.set_input_files("#fileImport", str(path))
            await pg.wait_for_timeout(700)
            check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") == ndec, f"[{what}] 'Fortschritt laden' restores every decision")
            check(await pg.evaluate("LKGC.RV.who") == "TEST", f"[{what}] ... and the reviewer name")
            files2 = dict(await pg.evaluate("LKGC.exportFiles()"))
            same = [n for n in CSVS if files2[n] == files[n]]
            check(same == CSVS, f"[{what}] re-export after loading gives identical files ({len(same)}/{len(CSVS)})")
            check(await pg.evaluate("LKGC.RVU.counts.done.n") == 1 or await pg.evaluate("LKGC.countQueues().done.n") == 1, f"[{what}] the checked entry is counted")
            if what == "JSON":
                # merging: a newer decision in the page wins over the file, an older one loses
                key = next(k for k in json.loads(files["graph_progress.json"])["state"]["dec"] if k.startswith("rec:"))
                await pg.evaluate(f"(() => {{ const d = Object.assign({{}}, LKGC.RV.dec[{json.dumps(key)}], {{ d: 'u' }}); LKGC.decide({json.dumps(key)}, d, 'test'); }})()")
                await pg.set_input_files("#fileImport", str(path))
                await pg.wait_for_timeout(500)
                check(await pg.evaluate(f"LKGC.RV.dec[{json.dumps(key)}].d") == "u", "loading older progress does not overwrite a newer decision")
                await pg.keyboard.press("z")
            await b.close()
        done(errs)

asyncio.run(main())
