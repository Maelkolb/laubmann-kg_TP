"""Language switch: German by default (also in an English browser), EN/DE button switches
every view, the choice survives a reload, decisions and exports do not depend on it."""
import asyncio
import csv
import io
from playwright.async_api import async_playwright
from common import SHOTS, check, done, open_page, open_item, reload


async def tabs(pg):
    return await pg.evaluate("Array.from(document.querySelectorAll('#tabs .tab')).map(e => e.childNodes[0].textContent.trim())")


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p, locale="en-GB")
        check(await pg.evaluate("__lp.LANG") == "de", "German by default even in an English browser")
        de = await tabs(pg)
        check(de[:3] == ["Übersicht", "Änderungen", "Stichprobe"], f"German tabs {de}")
        await pg.click("#btnLang")
        await pg.wait_for_timeout(300)
        en = await tabs(pg)
        check(await pg.evaluate("__lp.LANG") == "en" and en[:3] == ["Overview", "Changes", "Sample"], f"EN button switches to English {en}")
        check(await pg.evaluate("document.documentElement.lang") == "en", "html lang follows")
        check(await pg.locator("#btnLang").text_content() == "DE", "button offers the way back")
        await pg.screenshot(path=str(SHOTS / "lang_home_en.png"))
        i = await open_item(pg, "x => x.t === 'tc'")
        if i is not None:
            txt = await pg.evaluate("document.querySelector('#work').innerText")
            check("Does the correction match the scan?" in txt, "transcript card in English")
            await pg.keyboard.press("j")
            await pg.wait_for_timeout(250)
            await pg.screenshot(path=str(SHOTS / "lang_tc_en.png"))
        i = await open_item(pg, "x => x.t === 'qa'")
        if i is not None:
            txt = await pg.evaluate("document.querySelector('#work').innerText")
            check("Is the flag justified?" in txt, "QA card in English")
        i = await open_item(pg, "x => x.t === 'habitat'")
        if i is not None:
            txt = await pg.evaluate("document.querySelector('#work').innerText")
            check("EUNIS class" in txt, "habitat card in English")
        files_en = await pg.evaluate("__lp.exportFiles()")
        await reload(pg)
        check(await pg.evaluate("__lp.LANG") == "en", "language choice survives a reload")
        await pg.click("#btnLang")
        await pg.wait_for_timeout(300)
        check(await pg.evaluate("__lp.LANG") == "de", "back to German")
        files_de = await pg.evaluate("__lp.exportFiles()")
        a = dict(files_en)["review/transcript_decisions.csv"]
        z = dict(files_de)["review/transcript_decisions.csv"]
        check(a == z and len(list(csv.DictReader(io.StringIO(a)))) == 1, "export contents do not depend on the language")
        check("Laubmann-Validierung — Export" in dict(files_de)["LIESMICH.txt"], "German README in the ZIP")
        await b.close()
        done(errs)

asyncio.run(main())
