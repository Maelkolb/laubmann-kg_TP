"""Smoke test: the page loads, every tab renders, every item type renders a card and its
"other" panel, no page errors, no untranslated keys (DE and EN)."""
import asyncio
import re
from playwright.async_api import async_playwright
from common import SHOTS, check, done, open_page, open_item, reload

KEYPAT = re.compile(r"\b(?:tab|hint|q|f|row|d|cat|src|m|sec|box|card|v|nm|men|b|obs|miss|entry|o|log|scan|snip|home|task|bar|leg|prec|strat|ex|im|help|gs|for|chip|n|nav|st|rd|map|lbl|type|time|toast|hdr|saved|adv|crumb|close|empty|part|rnd|tck|tc|tcm|tcr|qa|qad|hab|now)\.[a-zA-Z][\w.-]*")
TABS = ["home", "change", "sample", "open", "tc", "extract", "unchecked", "habitat", "qa", "log"]
KINDS = [("taxon", "ok"), ("taxon", "newlink"), ("taxon", "unsure"), ("taxon", "name-unsure"), ("form", "moved"), ("person", "link-new"), ("person", "unsure"),
         ("place", "wrong"), ("place", "unsure"), ("place", "scan-located"), ("mention", "value-drop"), ("text", "text"), ("entry", "entry")]


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        check(await pg.evaluate("__lp.LANG") == "de", "German is the default language")
        tabs = await pg.eval_on_selector_all("#tabs .tab", "els => els.map(e => e.dataset.tab)")
        check(tabs == TABS, f"tabs in order {tabs}")
        check(await pg.locator(".tabsep").count() == 2, "tab bar separates part A and part B")
        q = await pg.evaluate("Object.fromEntries(Object.entries(__lp.QUEUES).map(([k, v]) => [k, v.length]))")
        print("queues", q)
        for k in ("change", "open", "sample", "tc", "unchecked", "habitat", "qa"):
            check(q.get(k, 0) > 0, f"queue {k} not empty")
        check(await pg.locator(".task").count() >= 8, "home lists the tasks")
        check(await pg.locator("h2.part").count() == 2, "home separates A and B")
        await pg.screenshot(path=str(SHOTS / "home.png"))
        await pg.click('.task[data-task="tc"][data-mode="sample"] button')
        await pg.wait_for_timeout(300)
        check(await pg.evaluate("__lp.S.ui.tab === 'tc' && __lp.S.ui.mode.tc === 'sample' && __lp.S.ui.filt.tc.state === 'open'"), "home task opens its tab, mode and filter")
        await pg.click('.brand')
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("__lp.S.ui.tab") == "home", "brand returns to the overview")
        for lang in ("de", "en"):
            await pg.evaluate(f"__lp.setLang('{lang}')")
            await reload(pg)
            bad = set()
            for tab in TABS:
                await pg.click(f'#tabs .tab[data-tab="{tab}"]')
                await pg.wait_for_timeout(250)
                bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                if lang == "de":
                    await pg.screenshot(path=str(SHOTS / f"tab_{tab}.png"))
            finds = [f"x => x.t === '{t}' && x.k === '{k}'" for t, k in KINDS] + [
                "x => x.t === 'tc' && x.applied === 'y'", "x => x.t === 'tc' && x.applied !== 'y'", "x => x.t === 'qa' && x.ei != null", "x => x.t === 'qa' && x.ei == null",
                "x => x.t === 'habitat' && x.cur", "x => x.t === 'habitat' && !x.cur", "x => x.q === 'unchecked' && x.t === 'person'",
                "x => x.q === 'unchecked' && x.t === 'place' && x.k === 'linked'", "x => x.q === 'unchecked' && x.t === 'place' && x.k === 'unlinked'", "x => x.q === 'unchecked' && x.t === 'taxon'"]
            seen = 0
            for js in finds:
                i = await open_item(pg, js)
                if i is None:
                    continue
                seen += 1
                ok = await pg.evaluate("!!document.querySelector('#work .card h1.t')")
                check(ok, f"[{lang}] card renders for {js}")
                bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                has_other = await pg.evaluate("[...document.querySelectorAll('.acts .btn')].some(b => b.dataset.act === 'o' || b.dataset.act === 'e')")
                if has_other:
                    await pg.keyboard.press("a")
                    await pg.wait_for_timeout(150)
                    check(await pg.evaluate("document.querySelector('#other').innerHTML.length > 0"), f"[{lang}] other/edit panel opens for {js}")
                    bad |= set(KEYPAT.findall(await pg.evaluate("document.body.innerText")))
                    await pg.keyboard.press("Escape")
                    await pg.keyboard.press("Escape")
                if lang == "de":
                    name = re.sub(r"[^a-z0-9]+", "_", js.split("=>")[1])[:60]
                    await pg.screenshot(path=str(SHOTS / f"card_{name}.png"))
            check(seen >= 12, f"[{lang}] {seen} item kinds rendered")
            await pg.click("#btnHelp")
            bad |= set(KEYPAT.findall(await pg.evaluate("document.querySelector('#modal').innerText")))
            await pg.keyboard.press("Escape")
            await pg.click("#btnExport")
            bad |= set(KEYPAT.findall(await pg.evaluate("document.querySelector('#modal').innerText")))
            await pg.keyboard.press("Escape")
            bad = {x for x in bad if not re.match(r"^(o\.k|d\.h|n\.b|m\.w|b\.w)", x)}
            check(not bad, f"[{lang}] no untranslated keys {sorted(bad)[:12]}")
        await b.close()
        done(errs)

asyncio.run(main())
