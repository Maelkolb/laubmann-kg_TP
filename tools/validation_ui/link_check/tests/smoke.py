"""Smoke test: the page loads fast, every type and every queue renders, cards step through, passages show
their line on the scan, DE/EN and light/dark toggle, no console error, no untranslated string.
Saves 1440x900 screenshots of each type's card to the shots folder.

    python tests/smoke.py [Laubmann_Verknuepfungen.html] [shots dir]
"""
import asyncio
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright
from common import PAGE, SHOTS, check, done, open_page, open_first, reload

HERE = Path(__file__).resolve().parent
TYPES = ["taxon", "person", "place", "habitat"]
QUEUES = ["changed", "confirmed", "suggest", "pipeline", "unlinked", "merge", "done"]
# one telling card per type for the screenshots (first match in mention order)
SHOT = {"taxon": ("e => e.q === 'changed' && e.ck === 'newlink'", None), "person": ("e => e.q === 'changed' && e.ck === 'newlink' && e.forms.length >= 3", None),
        "place": ("e => e.q === 'changed' && e.ck === 'moved'", None), "habitat": ("e => e.q === 'suggest' && e.sq === 'change' && e.m && e.m.votes && e.m.votes.length > 1", None)}


def static_keys():
    """Every literal t('key') of the app sources must exist in both languages."""
    src = "".join((HERE.parent / f).read_text(encoding="utf-8") for f in ("app_core.js", "app_view.js", "app_actions.js"))
    i18n = (HERE.parent / "app_i18n.js").read_text(encoding="utf-8")
    de, en = i18n.split("\n  en: {", 1)
    used = set(re.findall(r"\bt\('([a-zA-Z][\w.+-]*)'[,)]", src))
    miss = sorted(k for k in used if f"'{k}':" not in de or f"'{k}':" not in en)
    return used, miss


async def main():
    used, miss = static_keys()
    check(not miss, f"all {len(used)} literal string keys exist in German and English {miss[:8]}")
    size = PAGE.stat().st_size / 1e6
    check(size <= 15, f"page size {size:.1f} MB <= 15 MB")
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        t0 = time.time()
        await pg.reload()
        await pg.wait_for_selector("#loading", state="detached")
        await pg.wait_for_selector(".home .hc")
        dt = time.time() - t0
        check(dt < 3.0, f"the page opens in {dt:.2f} s (< 3 s)")
        check(await pg.evaluate("__lc.LANG") == "de" and await pg.evaluate("document.documentElement.dataset.theme") == "light", "German and the light theme are the defaults")
        check(await pg.locator(".home .hc").count() == 4 and await pg.locator(".home tr.ql").count() == 28, "overview: four types with their seven queues")
        check("Konfidenz" in await pg.inner_text(".home") and await pg.locator(".home kbd").count() >= 10, "overview explains the thresholds and the keys")
        await pg.screenshot(path=str(SHOTS / "overview.png"))
        counts = await pg.evaluate("Object.fromEntries(['taxon','person','place','habitat'].map(t => [t, Object.fromEntries(Object.entries(__lc.queueCounts(t)[0]).map(([q, c]) => [q, c.n]))]))")
        cover = await pg.evaluate("Object.fromEntries(['taxon','person','place','habitat'].map(t => { const p = __lc.typeProgress(t); return [t, [p.ents, p.n]]; }))")
        print("QUEUE COUNTS", counts)
        print("ENTRIES, MENTIONS", cover)
        # translations of every value the data carries (verdict words, sources, rules, roles, origins)
        gaps = await pg.evaluate("""(() => { const need = new Set(); const S = __lc.STR;
          for (const t of ['taxon','person','place','habitat']) for (const e of __lc.ENTS[t]) {
            const m = e.m; if (m) { if (m.word) need.add('m.word.' + m.word); for (const s of m.s || []) need.add('src.' + s); for (const v of m.votes || []) { need.add('src.' + v.s); if (v.v) need.add('m.word.' + v.v); } }
            if (e.ck) need.add(e.ck === 'none' ? 'ck.none.' + t : 'ck.' + e.ck); if (e.sq) need.add('sq.' + e.sq);
            const w = e.who || {}; if (w.rule && t !== 'habitat') need.add('rule.' + w.rule); if (!w.rule && w.status && t !== 'person') need.add('rule.status.' + w.status);
            for (const f of e.forms) { if (f.how && f.how.rule) need.add('rule.' + f.how.rule); if (f.m) { need.add('m.word.' + f.m.d); for (const s of f.m.s || []) need.add('src.' + s); } }
            for (const c of e.mg || []) need.add('rule.' + c.rule); for (const c of e.cands || []) if (c.o) need.add('cand.o.' + c.o);
            for (const x of e.ev || []) for (const r of (x.ro || '').split('/')) if (r) need.add('role.' + r);
            if (t === 'place' && e.kind) need.add('place.kind.' + e.kind);
          }
          return [...need].filter(k => S.de[k] == null || S.en[k] == null).sort(); })()""")
        check(not gaps, f"every verdict word, source, rule, role and origin in the data has a German and an English label {gaps[:12]}")

        for lang in ("de", "en"):
            if lang == "en":
                await pg.click("#btnLang")
                await pg.wait_for_timeout(200)
                check(await pg.evaluate("__lc.LANG") == "en" and "Species" in await pg.inner_text("#types"), "the EN button switches the language")
            for ty in TYPES:
                await pg.click(f'#types [data-type="{ty}"]')
                await pg.wait_for_timeout(150)
                check(await pg.evaluate("__lc.cur.type") == ty and await pg.locator(".pbar").count() >= 1 and "%" in await pg.inner_text(".pnote"), f"[{lang}] {ty}: list with the mention-weighted progress bar")
                for q in QUEUES:
                    n = counts[ty].get(q, 0)
                    if not n and q != "done":
                        continue
                    await pg.click(f'#qchips [data-q="{q}"]')
                    await pg.wait_for_timeout(120)
                    rows = await pg.locator(".qi").count()
                    if q == "done":
                        check(rows == 0 and await pg.locator(".qempty").count() == 1, f"[{lang}] {ty}/{q}: empty before any decision")
                        continue
                    ok = rows == min(n, 150) and await pg.locator("#cardwrap h1.t").count() == 1 and await pg.locator("#actbar .btn").count() >= 2
                    nums = await pg.eval_on_selector_all(".qi .num", "els => els.map(e => +e.textContent.replace(/[^0-9]/g, ''))")
                    check(ok and nums == sorted(nums, reverse=True), f"[{lang}] {ty}/{q}: {n} entries, card and actions render, sorted by mentions")
                    if lang == "de":
                        seen = [await pg.evaluate("__lc.cur.key")]
                        for _ in range(3):                      # step through cards
                            await pg.keyboard.press("ArrowDown")
                            await pg.wait_for_timeout(90)
                            seen.append(await pg.evaluate("__lc.cur.key"))
                        check(len(set(seen)) == min(4, n) and await pg.locator("#cardwrap h1.t").count() == 1, f"[de] {ty}/{q}: arrow keys step through the cards")
                    if q == "suggest":
                        await pg.click('.chip[data-sub="change"]')
                        await pg.wait_for_timeout(100)
                        check(await pg.evaluate(f"__lc.listItems('{ty}').every(e => e.sq === 'change')"), f"[{lang}] {ty}/suggest: sub-filter 'would change'")
                # the card sections of a telling entity
                key = await open_first(pg, ty, SHOT[ty][0]) or await open_first(pg, ty, "e => e.q === 'changed'")
                await pg.wait_for_timeout(500)
                heads = await pg.eval_on_selector_all("#cardwrap .sec > h3", "els => els.map(e => e.firstChild.textContent.trim())")
                want = ["Im Graph", "Vorher → Nachher", "Andere Datensätze", "Geschriebene Namen", "Belege"] if lang == "de" else ["In the graph", "Before → after", "Other records", "Written names", "Passages"]
                if ty == "habitat":
                    want[1] = "Vorschlag der Maschine" if lang == "de" else "Machine suggestion"
                check(all(w in heads for w in want) and [h for h in heads if h in want] == want, f"[{lang}] {ty}: sections in order {heads}")
                check(await pg.locator("#cardwrap .mbox .votes tr").count() >= 1, f"[{lang}] {ty}: machine box with the votes of its sources")
                if ty == "person":
                    check(await pg.locator("svg.hist rect").count() >= 2, f"[{lang}] person: years histogram")
                if ty == "place":
                    check(await pg.locator("#map.leaflet-container").count() == 1 and await pg.locator("#map path.leaflet-interactive").count() >= 2, f"[{lang}] place: map with the point and other markers")
                if lang == "de":
                    # a passage with a line box: click -> scan pane shows the page with the box
                    i = await pg.evaluate("__lc.BYK[__lc.cur.type].get(__lc.cur.key).ev.findIndex(m => m.b)")
                    if i >= 0:
                        await pg.click(f'.men[data-men="{i}"]')
                        await pg.wait_for_function("(() => { const im = document.querySelector('#scanimg'); return im && im.complete && im.naturalWidth > 0; })()", timeout=15000)
                        await pg.wait_for_timeout(250)
                        w = await pg.evaluate("document.querySelector('#scanimg').naturalWidth")
                        check(await pg.locator(f'.men.on[data-men="{i}"]').count() == 1 and await pg.locator("#scanwrap .hlbox").count() == 1, f"[de] {ty}: clicking a passage marks its line on the scan (image {w}px wide)")
                    j = await pg.evaluate("(() => { for (const e of __lc.ENTS[__lc.cur.type]) { const k = (e.ev || []).findIndex(m => m.b && m.b[4]); if (k >= 0) return [e.k, k]; } return null; })()")
                    if j:
                        await pg.evaluate(f"__lc.openEntity('{ty}', {j[0]!r})")
                        await pg.click(f'.men[data-men="{j[1]}"]')
                        await pg.wait_for_function("(() => { const im = document.querySelector('#scanimg'); return im && im.complete && im.naturalWidth > 0; })()", timeout=15000)
                        await pg.wait_for_timeout(250)
                        check(await pg.locator("#scanwrap .hlbox.approx").count() == 1 and await pg.locator("#scanwrap .hllab").count() == 1, f"[de] {ty}: an approximate line gets a dashed box and the label 'ungefähre Zeile'")
                        await open_first(pg, ty, SHOT[ty][0])
                        await pg.wait_for_timeout(500)
                    await pg.evaluate("document.querySelector('#cardwrap').scrollTop = 0")
                    await pg.wait_for_timeout(200)
                    await pg.screenshot(path=str(SHOTS / f"card_{ty}.png"))
                    await pg.evaluate("(() => { const el = [...document.querySelectorAll('#cardwrap .sec')].find(s => s.querySelector('.names')); if (el) el.scrollIntoView(); })()")
                    await pg.wait_for_timeout(200)
                    await pg.screenshot(path=str(SHOTS / f"card_{ty}_names.png"))
                else:
                    await pg.screenshot(path=str(SHOTS / f"card_{ty}_en.png"))
            # gone entity, merge card
            await open_first(pg, "taxon", "e => e.gone")
            check(await pg.locator("#cardwrap h1.t .bd.no").count() == 1, f"[{lang}] a name the machine removed is shown as removed")
            await open_first(pg, "person", "e => e.mg && e.mg.length > 1", "merge")
            check(await pg.locator("#cardwrap .cand[data-mg]").count() >= 2 and await pg.locator('#actbar [data-act="mgsame"]').count() == 1, f"[{lang}] merge card: candidates and J/N actions")
            if lang == "de":
                await pg.screenshot(path=str(SHOTS / "card_merge.png"))
            await pg.click("#btnHelp")
            check(await pg.locator("#ovModal.show .modal h2").count() == 1, f"[{lang}] help opens")
            await pg.keyboard.press("Escape")
            await pg.click("#btnExport")
            check(await pg.locator("#ovModal.show #exZip").count() == 1 and await pg.locator("#exPre").count() == 1, f"[{lang}] export dialog opens")
            await pg.keyboard.press("Escape")
            check(await pg.locator("#ovModal.show").count() == 0, f"[{lang}] Esc closes the dialog")
            await pg.click("#brand")
            await pg.wait_for_timeout(100)
            check(await pg.locator(".home .hc").count() == 4, f"[{lang}] the title returns to the overview")
        missing = await pg.evaluate("[...__lc.MISSING]")
        check(not missing, f"no untranslated string was rendered {missing[:10]}")

        # keys: list filter, scan toggle; theme
        await pg.click("#btnLang")
        await pg.click('#types [data-type="place"]')
        await pg.click('#qchips [data-q="confirmed"]')
        await pg.keyboard.press("/")
        check(await pg.evaluate("document.activeElement.id") == "qsearch", "/ focuses the list filter")
        await pg.keyboard.type("starnberg", delay=10)
        await pg.wait_for_timeout(450)
        txt = await pg.eval_on_selector_all(".qi .l1", "els => els.map(e => e.textContent)")
        check(txt and len(txt) < 150 and any("Starnberg" in x for x in txt) and await pg.evaluate("__lc.listItems('place').length") == len(txt), f"the filter narrows the list ({len(txt)} rows)")
        await pg.keyboard.press("Escape")
        await pg.keyboard.press("s")
        check(await pg.evaluate("document.querySelector('#main').classList.contains('noscan')"), "S hides the scan pane")
        await pg.keyboard.press("s")
        check(not await pg.evaluate("document.querySelector('#main').classList.contains('noscan')"), "S shows it again")
        await pg.fill("#qsearch", "")
        await pg.wait_for_timeout(350)
        await pg.click("#btnTheme")
        check(await pg.evaluate("document.documentElement.dataset.theme") == "dark", "theme button switches to dark")
        for ty in TYPES:
            await open_first(pg, ty, SHOT[ty][0])
            await pg.wait_for_timeout(400)
            bg = await pg.evaluate("getComputedStyle(document.querySelector('#cardwrap .box')).backgroundColor")
            fg = await pg.evaluate("getComputedStyle(document.querySelector('#cardwrap h1.t')).color")
            check(bg != "rgb(255, 255, 255)" and fg != "rgb(22, 28, 37)", f"dark theme: {ty} card uses the dark tokens ({bg} / {fg})")
            if ty in ("taxon", "place"):
                await pg.screenshot(path=str(SHOTS / f"card_{ty}_dark.png"))
        await reload(pg)
        check(await pg.evaluate("document.documentElement.dataset.theme") == "dark" and await pg.evaluate("__lc.cur.type") == "habitat", "theme and the open card are remembered")
        await pg.click("#btnTheme")
        await b.close()
        done(errs)


asyncio.run(main())
