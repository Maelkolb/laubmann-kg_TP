"""Smoke test: the page loads fast, every type and every queue renders, cards step through, passages show
their line on the scan, DE/EN and light/dark toggle, no console error, no untranslated string.
Saves 1440x900 screenshots of each type's card to the shots folder.

    python tests/smoke.py [Laubmann_Verknuepfungen.html] [shots dir]
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright
from common import PAGE, REPO, SHOTS, check, done, open_page, open_first, reload

QSHOTS = Path(os.environ.get("LC_QSHOTS", REPO / "data" / "exports" / "link_check" / "shots_quality"))
QSHOTS.mkdir(parents=True, exist_ok=True)

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


def de(n):
    return f"{n:,}".replace(",", ".")


def layer_counts(layer):
    """Records per threshold [all, p < .5, p < .25, p < .1] straight from the review layer of the graph page."""
    entries = json.loads(layer.read_text(encoding="utf-8"))["entries"]
    ps = [r["q"]["p"] for e in entries.values() for r in (e.get("rec") or {}).values() if (r.get("q") or {}).get("p") is not None]
    n = sum(len(e.get("rec") or {}) for e in entries.values())
    return [n] + [sum(1 for p in ps if p < x) for x in (0.5, 0.25, 0.1)]


async def corpus_filter(pg):
    """The reliability filter of the graph validation page: selector, banner, counts, lists, passages, overview."""
    T = "['taxon','person','place','habitat']"
    await pg.click("#brand")
    await pg.wait_for_timeout(150)
    opts = await pg.eval_on_selector_all("#corpbar .cbtn", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
    rec = await pg.evaluate("__lc.D.corpus.rec")
    check(opts == [f"{n} {de(rec[c])}" for c, n in enumerate(["Alle", "< 50 %", "< 25 %", "< 10 %"])] and (await pg.inner_text("#corpbar .cbl")) == "Verlässlichkeit",
          f"reliability bar: label 'Verlässlichkeit' and four thresholds with their record counts {opts}")
    box = await pg.evaluate("(() => { const r = document.querySelector('#corpbar').getBoundingClientRect(), h = document.querySelector('header').getBoundingClientRect(); return [Math.round(r.top - h.bottom), Math.round(r.width), Math.round(r.height)]; })()")
    seen = [await pg.locator("#corpbar .cbtn:visible").count()]
    for ty in ["taxon", "person", "place", "habitat"]:
        await pg.click(f'#types [data-type="{ty}"]')
        await pg.wait_for_timeout(120)
        seen.append(await pg.locator("#corpbar .cbtn:visible").count())
    check(box[0] == 0 and box[1] >= 1400 and box[2] >= 30 and seen == [4] * 5, f"the reliability bar sits directly under the header in every view (overview and the four types) {box} {seen}")
    await pg.click('#corpbar [data-act="corpus-info"]')
    await pg.wait_for_timeout(150)
    info = await pg.inner_text("#modal")
    check(await pg.locator("#ovModal.show .cdef tr").count() == 4 and all(w in info for w in ["Alle", "< 10 %", "Wahrscheinlichkeit", "Scanprüfung", "Koordinaten", "nur eine Ansicht"]), "ⓘ explains the four thresholds in words")
    await pg.keyboard.press("Escape")
    tax = await pg.evaluate("[0,1,2,3].map(c => __lc.ENTS.taxon.filter(e => !e.gone).reduce((a, e) => a + e.nc[c], 0))")
    check(rec == tax, f"species mentions per threshold = records per threshold {tax}")
    layer = Path(os.environ.get("LC_REVIEW", REPO / "data" / "cache" / "graph_check" / "review_regions.json"))
    if layer.exists():
        want = layer_counts(layer)
        check(rec == want, f"records per threshold as in the review layer of the graph page {want}")
    ok = await pg.evaluate(f"{T}.every(t => __lc.ENTS[t].every(e => e.nc && e.nc[0] === e.n && e.nc[1] <= e.nc[0] && e.nc[2] <= e.nc[1] && e.nc[3] <= e.nc[2] && [0,1,2,3].every(c => e.forms.reduce((a, f) => a + f.nc[c], 0) === e.nc[c])))")
    check(ok, "every entry and written name carries nested counts for the four thresholds; names add up to the entry")
    check(await pg.locator('#corpbar .cbtn.on').count() == 1 and await pg.locator('#corpbar .cbtn.on[data-corpus="0"]').count() == 1 and await pg.locator('#corpbar [data-act="corpus-off"]').count() == 0
          and await pg.evaluate("__lc.corpus()") == 0 and not await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')"), "without a filter 'Alle' is the filled button, no 'Filter aufheben'")

    await pg.click('#corpbar .cbtn[data-corpus="2"]')
    await pg.wait_for_timeout(250)
    bar = await pg.inner_text("#corpbar .cbt")
    check(await pg.evaluate("__lc.S.ui.corpus") == 2 and "Filter aktiv: Fehlerrisiko unter 25 %" in bar and de(rec[2]) in bar and de(rec[0]) in bar and "Export bleiben vollständig" in bar
          and await pg.locator('#corpbar [data-act="corpus-off"]').count() == 1, f"a button sets the filter; the bar explains it and offers 'Filter aufheben' ({bar[:80]})")
    fill = await pg.evaluate("[...document.querySelectorAll('#corpbar .cbtn')].map(b => getComputedStyle(b).backgroundColor)")
    check(await pg.locator('#corpbar .cbtn.on').count() == 1 and await pg.locator('#corpbar .cbtn.on[data-corpus="2"]').count() == 1 and fill[2] != fill[0] and fill[0] == fill[1] == fill[3]
          and await pg.evaluate("document.querySelector('#corpbar').classList.contains('active')") and await pg.evaluate("document.activeElement.tagName") == "BODY",
          f"the active threshold is the one filled button {fill}")
    corp = await pg.evaluate("__lc.D.corpus")
    for ty in ["taxon", "person", "place", "habitat"]:
        await pg.click(f'#types [data-type="{ty}"]')
        await pg.wait_for_timeout(150)
        await pg.click('#qchips [data-q="suggest"]')
        await pg.wait_for_timeout(150)
        st = await pg.evaluate(f"(() => {{ const it = __lc.corpusItems('{ty}'); const p = __lc.typeProgress('{ty}'); const [c] = __lc.queueCounts('{ty}');"
                               f" return {{n: it.length, all: it.every(e => e.nc[2] > 0), sorted: it.every((e, i) => i === 0 || it[i - 1].nc[2] >= e.nc[2]), pn: p.n, pe: p.ents,"
                               f" q: ['changed','confirmed','suggest','pipeline','unlinked'].reduce((a, q) => a + c[q].n, 0), list: __lc.listItems('{ty}').length, sum: it.reduce((a, e) => a + e.nc[2], 0)}}; }})()")
        check(st["all"] and st["sorted"] and st["n"] == corp["ent"][ty][2] and st["sum"] == corp["men"][ty][2], f"[<25 %] {ty}: {st['n']} entries with a mention under the threshold, sorted by their {st['sum']} mentions there")
        check(st["pn"] == corp["men"][ty][2] and st["pe"] == st["n"] == st["q"] and st["n"] < corp["ent"][ty][0] and st["list"] <= st["n"],
              f"[<25 %] {ty}: progress and queue counts count the filter only ({st['pe']} of {corp['ent'][ty][0]} entries, {st['pn']} mentions)")
        nums = await pg.eval_on_selector_all(".qi .num", "els => els.map(e => e.textContent)")
        keys = await pg.eval_on_selector_all(".qi", "els => els.map(e => e.dataset.key)")
        exp = await pg.evaluate(f"{json.dumps(keys)}.map(k => {{ const e = __lc.BYK['{ty}'].get(k); return [e.nc[2], e.n]; }})")
        got = [[int(x.replace(".", "")) for x in s.split("/")] for s in nums]
        check(got == exp and all(a[0] > 0 for a in got) and [a[0] for a in got] == sorted((a[0] for a in got), reverse=True), f"[<25 %] {ty}: rows show 'n im Filter / n gesamt', most mentions in the filter first")
        check(de(st["pe"]) in await pg.inner_text(".pnote"), f"[<25 %] {ty}: the progress line counts the entries of the filter")
    # an entry without a mention under the threshold is hidden, not gone
    hid = await pg.evaluate("(__lc.ENTS.taxon.find(e => !e.gone && e.nc[2] === 0) || {}).k")
    check(hid is not None and not await pg.evaluate(f"__lc.corpusItems('taxon').some(e => e.k === {json.dumps(hid)})") and await pg.evaluate(f"__lc.BYK.taxon.has({json.dumps(hid)})"),
          f"an entry without a mention under the threshold is hidden by the filter ({hid})")
    # a species card under the filter: both counts, passages under the threshold first, error chips, reasons in words
    key = await pg.evaluate("(__lc.corpusItems('taxon').find(e => e.nc[2] < e.n && e.forms.length >= 3 && e.ev.some(m => m.k >= 2) && e.ev.some(m => m.k < 2)) || {}).k")
    await pg.evaluate(f"__lc.S.ui.q.taxon = __lc.BYK.taxon.get({json.dumps(key)}).q; __lc.openEntity('taxon', {json.dumps(key)})")
    await pg.wait_for_timeout(500)
    sub = await pg.inner_text("#cardwrap .sub")
    ev = await pg.eval_on_selector_all("#cardwrap .men", "els => els.map(e => { const m = __lc.curEnt().ev[+e.dataset.men]; return [e.classList.contains('out'), (e.querySelector('.trc') || {}).textContent || '', (e.querySelector('.trw') || {}).textContent || '', m.k, m.kp == null ? null : m.kp, (e.querySelector('.trc') || {}).title || '']; })")
    outs = [x[0] for x in ev]
    pct = lambda v: "–" if v is None else "< 1 %" if v < 1 else f"{v} %"
    check("im Filter" in sub and "/" in sub, f"[<25 %] card: mentions in the filter and in total ({sub[:60]})")
    check(all(" / " in x for x in await pg.eval_on_selector_all("#cardwrap .nm .ct", "els => els.map(e => e.textContent).filter(x => x !== '–')")), "[<25 %] written names show both counts")
    check(outs == sorted(outs) and True in outs and False in outs and all(x[1] == pct(x[4]) for x in ev) and all((x[3] >= 2) != x[0] for x in ev) and all(x[4] is None or (x[4] < 25) == (x[3] >= 2) for x in ev)
          and all("Fehlerwahrscheinlichkeit" in x[5] or "Datensatz" in x[5] for x in ev),
          f"[<25 %] passages under the threshold first, each with its estimated error {[x[1] for x in ev]}")
    check(all("nicht unter 25 %" in x[2] or "keinen Datensatz" in x[2] for x in ev if x[0]) and all(not x[2] for x in ev if not x[0]), f"[<25 %] passages above the threshold say why ({next((x[2] for x in ev if x[0]), '')[:70]})")
    check(await pg.locator("#cardwrap .men.on:not(.out)").count() == 1, "[<25 %] the scan shows a passage under the threshold first")
    await pg.evaluate("document.querySelector('#cardwrap').scrollTop = 0")
    await pg.screenshot(path=str(SHOTS / "card_taxon_k2.png"))
    await pg.evaluate("(() => { const el = [...document.querySelectorAll('#cardwrap .sec')].find(s => s.querySelector('.men')); if (el) el.scrollIntoView(); })()")
    await pg.wait_for_timeout(200)
    await pg.screenshot(path=str(SHOTS / "card_taxon_k2_passages.png"))
    await pg.keyboard.press("ArrowDown")
    await pg.wait_for_timeout(120)
    check(await pg.evaluate("__lc.corpusItems('taxon').some(e => e.k === __lc.cur.key)"), "[<25 %] the arrow keys stay inside the filter")
    # overview
    await pg.click("#brand")
    await pg.wait_for_timeout(200)
    card = await pg.inner_text(".grid4 .hc >> nth=0")
    check(de(corp["ent"]["taxon"][2]) in card and de(corp["men"]["taxon"][2]) in card, "[<25 %] overview: the type cards count the filter only")
    cells = await pg.evaluate("[0,1,2,3].map(c => ['taxon','person','place','habitat'].map(t => ['e','m'].map(x => +document.querySelector('.covt tr[data-corpus=\"' + c + '\"] td[data-cc=\"' + t + '-' + x + '\"]').textContent.replace(/\\D/g, ''))))")
    exp = [[[corp["ent"][t][c], corp["men"][t][c]] for t in ["taxon", "person", "place", "habitat"]] for c in range(4)]
    check(cells == exp and await pg.locator('.covt tr.on[data-corpus="2"]').count() == 1, "overview: table of the four thresholds per type (entries, mentions), the active one marked")
    check("Verlässlichkeit der Datensätze" in await pg.inner_text(".home") and "nur eine Ansicht" in await pg.inner_text(".home"), "overview explains the filter in one line")
    await pg.screenshot(path=str(SHOTS / "overview_k2.png"), full_page=False)
    await pg.evaluate("document.querySelector('#cardwrap').scrollTop = document.querySelector('.covt').offsetTop - 120")
    await pg.wait_for_timeout(150)
    await pg.screenshot(path=str(SHOTS / "overview_k2_corpora.png"))
    print("CORPUS", json.dumps(corp, ensure_ascii=False))
    # EN, remembered, row click, clear
    await pg.click("#btnLang")
    await pg.wait_for_timeout(200)
    bar = await pg.inner_text("#corpbar")
    opts = await pg.eval_on_selector_all("#corpbar .cbtn", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
    check("Filter active: error risk below 25 %" in bar and "clear the filter" in bar and bar.startswith("Reliability") and opts[2].startswith("< 25 % ") and opts[0].startswith("All ")
          and "Reliability of the records" in await pg.inner_text(".home"), "[en] reliability bar and overview in English")
    await pg.click('#types [data-type="taxon"]')
    await pg.wait_for_timeout(200)
    check("in the filter" in await pg.inner_text("#cardwrap .sub"), "[en] card counts in English")
    await pg.click("#btnLang")
    await reload(pg)
    check(await pg.evaluate("__lc.S.ui.corpus") == 2 and await pg.locator('#corpbar .cbtn.on[data-corpus="2"]').count() == 1 and await pg.locator('#corpbar [data-act="corpus-off"]').count() == 1, "the filter is remembered over a reload")
    await pg.click("#brand")
    await pg.wait_for_timeout(150)
    await pg.click('.covt tr[data-corpus="3"]')
    await pg.wait_for_timeout(200)
    check(await pg.evaluate("__lc.S.ui.corpus") == 3 and await pg.locator('#corpbar .cbtn.on[data-corpus="3"]').count() == 1 and "Fehlerrisiko unter 10 %" in await pg.inner_text("#corpbar .cbt"), "a row of the thresholds table sets the filter")
    await pg.click('#types [data-type="place"]')
    await pg.wait_for_timeout(150)
    await pg.click('#corpbar [data-act="corpus-off"]')
    await pg.wait_for_timeout(250)
    check(await pg.evaluate("__lc.S.ui.corpus") == 0 and await pg.locator('#corpbar .cbtn.on[data-corpus="0"]').count() == 1 and await pg.locator('#corpbar [data-act="corpus-off"]').count() == 0
          and await pg.evaluate("__lc.corpusItems('place').length") == await pg.evaluate("__lc.ENTS.place.length")
          and "/" not in (await pg.eval_on_selector_all(".qi .num", "els => els.map(e => e.textContent)"))[0], "'Filter aufheben' brings everything back")
    missing = await pg.evaluate("[...__lc.MISSING]")
    check(not missing, f"no untranslated string under the reliability filter {missing[:10]}")


async def link_basis(pg):
    """How a link is backed: classes per entry and name, badge, list filter, overview counts, export unchanged."""
    LB = ["two", "one", "name", "mno", "none"]
    await pg.evaluate("__lc.setCorpus(0)")
    await pg.click("#brand")
    await pg.wait_for_timeout(200)
    basis = await pg.evaluate("__lc.D.basis")
    got = await pg.evaluate("Object.fromEntries(['taxon','person','place','habitat'].map(t => [t, Object.fromEntries(['two','one','name','mno','none'].map(b => [b, __lc.ENTS[t].filter(e => e.lb === b).length]))]))")
    check(all(basis[t]["ent"] == got[t] for t in TYPES) and await pg.evaluate("['taxon','person','place','habitat'].every(t => __lc.ENTS[t].every(e => ['two','one','name','mno','none'].includes(e.lb)))")
          and await pg.evaluate("__lc.ENTS.taxon.every(e => e.forms.every(f => ['two','one','mno','none'].includes(f.lb)))"), f"every entry has one link class, every species name its own ({got['place']})")
    check(basis["place"]["ent"]["name"] > 0 and basis["taxon"]["ent"]["name"] == 0 and basis["taxon"]["men"]["two"] > basis["taxon"]["men"]["one"] > 0 and basis["habitat"]["men"]["one"] > 0,
          "classes as the data supports them: name match only for places, species split per written name")
    rows = await pg.evaluate("[...document.querySelectorAll('.grid4 .hc')].map(c => [...c.querySelectorAll('.lbt tr[data-lbv]')].map(r => [r.dataset.lbv, ...[...r.querySelectorAll('td.n')].map(x => x.textContent)]))")
    exp = [[[b, de(basis[t]["ent"][b]), de(basis[t]["men"][b])] for b in LB if basis[t]["ent"][b] or basis[t]["men"][b]] for t in TYPES]
    check([[r[:3] for r in c] for c in rows] == exp, f"overview: entries and mentions per link class in every type card {[[r[0] for r in c] for c in rows]}")
    shares = [sum(float(r[3].replace(" %", "").replace(",", ".")) for r in c) for c in rows]
    check(all(abs(s - 100) < 0.3 for s in shares), f"overview: the shares of the mentions add up to 100 % {shares}")
    home = await pg.inner_text(".grid4")
    below = await pg.evaluate("__lc.D.below")
    check("75 %" in home and "12 %" in home and "nicht gemessen" in home and de(below["habitat"]["rows"]) in home and "Konfidenz" in home,
          "overview: one line of the blind audit per class, below-threshold machine rows counted")
    await pg.evaluate("document.querySelector('#cardwrap').scrollTop = document.querySelector('.grid4').offsetTop - 60")
    await pg.wait_for_timeout(150)
    await pg.screenshot(path=str(QSHOTS / "overview_link_basis.png"))
    # a click on a row: the type, its first queue with such entries, the list filter set
    await pg.click('.lbt tr[data-hlb="place"][data-lbv="name"]')
    await pg.wait_for_timeout(300)
    st = await pg.evaluate("({ty: __lc.cur.type, lb: __lc.S.ui.lb.place, items: __lc.listItems('place').map(e => e.lb), on: [...document.querySelectorAll('.chip.lbc.on')].map(c => c.dataset.lb)})")
    check(st["ty"] == "place" and st["lb"] == "name" and st["items"] and set(st["items"]) == {"name"} and st["on"] == ["name"], f"a row of the overview opens the type filtered to its link class ({len(st['items'])} entries)")
    crumb = await pg.inner_text("#cardwrap .crumb")
    tip = await pg.get_attribute("#cardwrap .crumb .bd.lb", "title")
    check("nur Namensabgleich" in crumb and "75 %" in (tip or "") and "Namenstreffer" in (tip or ""), "card: the link class as a badge, its tooltip says what backs the link and what the audit measured")
    await pg.screenshot(path=str(QSHOTS / "card_place_name_match.png"))
    # the chip toggles the filter; the export does not depend on it
    ident, audit = await pg.evaluate("__lc.exportIdentities()"), await pg.evaluate("__lc.exportFiles().find(f => f[0] === 'link_audit.csv')[1]")
    await pg.click('.chip.lbc[data-lb="name"]')
    await pg.wait_for_timeout(200)
    n_all = await pg.evaluate("__lc.listItems('place').length")
    check(await pg.evaluate("__lc.S.ui.lb.place") == "" and await pg.locator(".chip.lbc.on").count() == 0 and n_all >= len(st["items"]), "a second click on the chip clears the link filter")
    check(await pg.evaluate("__lc.exportIdentities()") == ident and await pg.evaluate("__lc.exportFiles().find(f => f[0] === 'link_audit.csv')[1]") == audit
          and await pg.evaluate("__lc.exportFiles().find(f => f[0] === 'link_audit.csv')[1].split('\\n')[0].split(',').includes('link_basis')"), "the export is the same with and without the link filter; link_audit.csv has a link_basis column")
    # species: a name whose class differs from the entry's carries its own badge
    key = await pg.evaluate("(__lc.ENTS.taxon.find(e => e.forms.some(f => f.n && f.lb !== e.lb)) || {}).k")
    await pg.evaluate(f"__lc.S.ui.q.taxon = __lc.BYK.taxon.get({json.dumps(key)}).q; __lc.S.ui.lb.taxon = ''; __lc.openEntity('taxon', {json.dumps(key)})")
    await pg.wait_for_timeout(300)
    n_badges = await pg.locator("#cardwrap .nm .bd.lb").count()
    check(key and n_badges >= 1 and await pg.locator("#cardwrap .crumb .bd.lb").count() == 1, f"species: names linked otherwise than the entry show their own class ({key}, {n_badges})")
    await pg.evaluate("(() => { const el = [...document.querySelectorAll('#cardwrap .sec')].find(s => s.querySelector('.nm .bd.lb')); if (el) el.scrollIntoView(); })()")
    await pg.wait_for_timeout(150)
    await pg.screenshot(path=str(QSHOTS / "card_taxon_names_basis.png"))
    # English
    await pg.click("#btnLang")
    await pg.wait_for_timeout(200)
    await pg.click('#types [data-type="place"]')
    await pg.wait_for_timeout(200)
    chips = await pg.eval_on_selector_all(".chip.lbc", "els => els.map(e => e.textContent)")
    await pg.click("#brand")
    await pg.wait_for_timeout(200)
    home = await pg.inner_text(".grid4")
    check(any("name match only" in c or "two sources" in c or "unlinked" in c for c in chips) and "Link backed by" in home and "Blind audit 3 Oct" in home, f"[en] link classes in English {chips[:3]}")
    await pg.click("#btnLang")
    await pg.wait_for_timeout(150)
    missing = await pg.evaluate("[...__lc.MISSING]")
    check(not missing, f"no untranslated string around the link classes {missing[:10]}")


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
        check(await pg.locator(".grid4 .hc").count() == 4 and await pg.locator(".grid4 tr.ql[data-hq]").count() == 28, "overview: four types with their seven queues")
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
            check(await pg.locator(".grid4 .hc").count() == 4, f"[{lang}] the title returns to the overview")
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
        await corpus_filter(pg)
        await link_basis(pg)
        await b.close()
        done(errs)


asyncio.run(main())
