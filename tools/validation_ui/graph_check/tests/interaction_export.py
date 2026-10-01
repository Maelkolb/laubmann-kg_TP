"""Interaction + export round trip: at least one decision of EVERY kind by keyboard and mouse, the ZIP
files, and each review/*.csv read by the pipeline loader it is meant for (repo interpreter,
loaders_check.py) — asserting that the rows arrive with the right values and that the value and
observation corrections, applied in the pipeline's order, change exactly the intended records."""
import asyncio
import csv
import io
import json
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from common import REPO_PY, SHOTS, check, done, goto_entry, open_page

TD_HEAD = ["entry_uid", "entry_id", "old_text", "new_text", "decision", "final_text", "note", "reviewed_by", "reviewed_at"]
QD_HEAD = ["entry_uid", "entry_id", "reason", "value", "decision", "note", "reviewed_by", "reviewed_at"]
ZIP_FILES = ["review/observation_corrections.csv", "review/value_corrections.csv", "review/transcript_decisions.csv", "review/text_corrections.csv",
             "review/qa_decisions.csv", "review/identities.csv", "entry_checks.csv", "graph_audit.csv", "graph_progress.json", "LIESMICH.txt"]

# JS: first (entry, item) where the entry's review data passes `pe` and one of its items passes `pi`;
# entries in `skip` are left out, so every case gets an entry of its own
FIND_ITEM = """([pe, pi, skip]) => { const fe = eval(pe), fi = eval(pi);
  for (const r of LKGC.G.ent) { const rv = LKGC.R.entries[r.id] || {}; const s = LKGC.RVS.get(r.n); if (skip.includes(r.id) || !fe(rv, s, r)) continue;
    const m = LKGC.buildModel(r.n); const it = m.items.find(x => fi(x, m)); if (it) return { id: r.id, uid: m.uid, key: it.key, written: it.o ? it.o.written : null, idx: it.o ? it.o.idx : null, occ: it.o ? it.o.occ : null }; }
  return null; }"""
MP = "LKGC.mergedProposal(it.o)"
SMALL = "Object.keys(rv.rec || {}).length <= 30"


def rows(files, name):
    text = dict(files)[name]
    return list(csv.DictReader(io.StringIO(text))), text.splitlines()[0].split(",")


class Run:
    def __init__(self, pg):
        self.pg, self.used, self.made = pg, [], {}

    async def find(self, name, pe, pi):
        hit = await self.pg.evaluate(FIND_ITEM, [pe, pi, self.used])
        if check(hit is not None, f"case {name}: an entry exists"):
            self.used.append(hit["id"])
            self.made[name] = hit
        return hit

    async def open(self, hit, wait=350):
        await goto_entry(self.pg, hit["id"], wait)
        return await self.focus(hit["key"])

    async def focus(self, key):
        i = await self.pg.evaluate(f"(() => {{ const m = LKGC.EM; let items = LKGC.visibleItems(m); let i = items.findIndex(x => x.key === {json.dumps(key)}); if (i < 0) {{ LKGC.RVU.hints = true; LKGC.RVU.showOut = true; items = LKGC.visibleItems(m); i = items.findIndex(x => x.key === {json.dumps(key)}); }} document.querySelector('#ptabs [data-tab=check]').click(); if (i >= 0) LKGC.focusCard(i); return i; }})()")
        await self.pg.wait_for_timeout(120)
        return i

    async def press(self, *keys, wait=200):
        for k in keys:
            await self.pg.keyboard.press(k)
            await self.pg.wait_for_timeout(wait)

    async def dec(self, key):
        return await self.pg.evaluate(f"LKGC.RV.dec[{json.dumps(key)}] || null")


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        R = Run(pg)
        await pg.fill("#who", "TEST")
        await pg.keyboard.press("Escape")          # leaves the name field (keys typed there are text)
        await pg.wait_for_timeout(400)
        check(await pg.evaluate("document.activeElement.id") != "who" and await pg.evaluate("LKGC.RV.who") == "TEST", "the reviewer name is stored; Esc leaves the field")

        # ---------------------------------------------------------------- 1 records with findings: J N E X U
        h = await R.find("apply", f"(rv, s) => s.find.length && {SMALL}", f"(it) => {{ if (it.type !== 'rec') return false; const mp = {MP}; return mp && !mp.drop && !mp.geo && !Object.keys(mp.bad).length && !mp.vals.species && ('count' in mp.vals || 'locality' in mp.vals); }}")
        if h:
            await R.open(h)
            h["vals"] = await pg.evaluate("(() => LKGC.mergedProposal(LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].o).vals)()")
            await pg.screenshot(path=str(SHOTS / "i_record_card.png"))
            await R.press("j")
            d = await R.dec(h["key"]) or {}
            check(d.get("d") == "a" and d.get("vals") == h["vals"] and d.get("by") == "TEST", f"J applies the proposed values {h['vals']}")
            check(await pg.locator("#pbody .rcard.done .mine").count() >= 1, "the card shows 'von dir entschieden'")
            check(await pg.locator("#gsvg .nd.an-dec").count() >= 1, "the node carries the green tick")
        h = await R.find("spurious", f"(rv, s) => s.find.length && {SMALL}", f"(it) => it.type === 'rec' && ({MP} || {{}}).drop")
        if h:
            await R.open(h)
            await R.press("j")
            check((await R.dec(h["key"]) or {}).get("d") == "x", "J on a spurious record strikes it")
        h = await R.find("ok", f"(rv, s) => s.find.length && {SMALL}", "(it) => it.type === 'rec' && LKGC.mergedProposal(it.o)")
        if h:
            await R.open(h)
            await R.press("n")
            check((await R.dec(h["key"]) or {}).get("d") == "ok", "N: the record is right (finding rejected)")
        h = await R.find("unsure", f"(rv, s) => s.find.length && {SMALL}", "(it) => it.type === 'rec'")
        if h:
            await R.open(h)
            await R.press("u")
            check((await R.dec(h["key"]) or {}).get("d") == "u", "U: unsure")
        h = await R.find("geo", f"(rv, s) => s.find.length && {SMALL}", f"(it) => {{ if (it.type !== 'rec') return false; const mp = {MP}; return mp && mp.geo && Object.keys(mp.vals).length === 1 && !Object.keys(mp.bad).length; }}")
        if h:
            await R.open(h)
            check(await pg.locator("#pbody .rcard.focus .geonote").count() == 1, "georeference finding: the card says that the place must be checked on the link page")
            h["place"] = await pg.evaluate("LKGC.mergedProposal(LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].o).vals.locality")
            await R.press("j")
            d = await R.dec(h["key"]) or {}
            check(d.get("d") == "a" and d.get("vals") == {"locality": h["place"]}, "georeference: J sets the locality of this record only")
        h = await R.find("species", f"(rv, s) => s.find.length && {SMALL}", f"(it) => {{ if (it.type !== 'rec') return false; const mp = {MP}; return mp && !mp.drop && mp.vals.species && !Object.keys(mp.bad).length; }}")
        if h:
            await R.open(h)
            h["vals"] = await pg.evaluate("LKGC.mergedProposal(LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].o).vals")
            await R.press("j")
            check(((await R.dec(h["key"]) or {}).get("vals") or {}).get("species", {}).get("de") == h["vals"]["species"]["de"], "J applies another species")
        h = await R.find("badformat", "(rv, s) => s.find.length", f"(it) => it.type === 'rec' && Object.keys(({MP} || {{bad: {{}}}}).bad).length && !({MP}).drop")
        if h:
            await R.open(h)
            await R.press("j")
            check(await pg.locator("#pbody .rform").count() == 1 and await R.dec(h["key"]) is None, "J with a value the pipeline cannot read opens the form instead of exporting it")
            await R.press("Escape")
            check(await pg.locator("#pbody .rform").count() == 0, "Esc closes the form")

        # E: edit values — a record of a name that occurs three times; its neighbours are struck (order of the drop rows)
        h = await R.find("multi", "(rv, s, r) => r.nobs >= 3 && r.nobs <= 20", "(it, m) => it.type === 'rec' && it.o.occ === 1 && m.obs.filter(o => o.written.toLowerCase() === it.o.written.toLowerCase()).length >= 3 && !it.o.rec.auto")
        if h:
            await R.open(h)
            same = await pg.evaluate(f"LKGC.EM.obs.filter(o => o.written.toLowerCase() === {json.dumps(h['written'].lower())}).map(o => ({{ key: o.key, idx: o.idx, occ: o.occ }}))")
            h["same"] = same
            await pg.keyboard.press("e")
            await pg.wait_for_timeout(250)
            check(await pg.evaluate("document.activeElement && document.activeElement.name") == "species_de", "E opens the edit form with the species field focused")
            check(await pg.evaluate("document.activeElement.value") == h["written"], "the key E is not typed into the field")
            await pg.screenshot(path=str(SHOTS / "i_edit_form.png"))
            await pg.fill('.rform input[name="species_de"]', "Zilpzalp")
            await pg.wait_for_timeout(250)
            n_res = await pg.locator(".rform .tres .r").count()
            if n_res:
                await pg.click(".rform .tres .r >> nth=0")
            h["species"] = await pg.evaluate("({ de: document.querySelector('.rform input[name=species_de]').value, sci: document.querySelector('.rform input[name=species_sci]').value, key: document.querySelector('.rform input[name=species_key]').value })")
            check(n_res > 0 and h["species"]["sci"] != "", f"the species search offers species of the graph ({h['species']})")
            await pg.fill('.rform input[name="count"]', "5 Paare und 3")
            await pg.keyboard.press("Enter")
            await pg.wait_for_timeout(200)
            check(await R.dec(h["key"]) is None and await pg.locator(".rform input.bad").count() == 1, "an unreadable count is refused")
            await pg.fill('.rform input[name="count"]', "3-5")
            await pg.fill('.rform input[name="locality"]', "Testweiher")
            await pg.fill('.rform input[name="date"]', "1930-05-06")
            await pg.fill('.rform input[name="observer"]', "W. Wüst")
            await pg.fill('.rform input[name="co_observers"]', "E. Bezzel; H. Remold")
            await pg.select_option('.rform select[name="record_type"]', "third-party-report")
            h["sex"] = "female" if await pg.evaluate("document.querySelector('.rform select[name=sex]').value") == "male" else "male"
            await pg.select_option('.rform select[name="sex"]', h["sex"])
            await pg.keyboard.press("Enter")
            await pg.wait_for_timeout(300)
            d = await R.dec(h["key"]) or {}
            check(d.get("d") == "e" and d.get("vals", {}).get("count") == "3-5" and d["vals"].get("species", {}).get("de") == h["species"]["de"], f"E + Enter stores the edited values {list(d.get('vals', {}))}")
            # strike occurrence 0 and 2 of the same name with X (cards exist only for flagged records: use the table)
            await R.press("g")
            for o in (same[0], same[2]):
                await pg.click(f"#rtable tr[data-o] >> nth={await pg.evaluate(f'LKGC.EM.obs.findIndex(x => x.key === {json.dumps(o['key'])})')} >> td.racts [data-ra=drop]")
                await pg.wait_for_timeout(200)
            check(all([(await R.dec(same[0]["key"]) or {}).get("d") == "x", (await R.dec(same[2]["key"]) or {}).get("d") == "x"]), "✕ in the table strikes records")
            check(await pg.locator("#rtable tr.dropped").count() == 2, "struck rows are shown struck through")
            await R.press("g")

        # X by keyboard, then undo and redo
        h = await R.find("drop", f"(rv, s) => s.find.length && {SMALL}", "(it) => it.type === 'rec'")
        if h:
            await R.open(h)
            await R.press("x")
            check((await R.dec(h["key"]) or {}).get("d") == "x", "X strikes the record")
            await R.press("z")
            check(await R.dec(h["key"]) is None, "Z undoes the last decision")
            await R.focus(h["key"])
            await R.press("x")

        # ---------------------------------------------------------------- table: chip and cell
        h = await R.find("table", f"(rv, s) => s.find.length && {SMALL}", f"(it, m) => {{ if (it.type !== 'rec') return false; const pp = LKGC.proposal(it.o, 'g'); return pp && !pp.drop && Object.keys(pp.vals).some(k => ['count', 'date', 'locality'].includes(k)) && m.obs.some(x => !x.rec.auto && !['g', 's'].some(c => x.rec[c] && x.rec[c].v !== 'ok')); }}")
        if h:
            await R.open(h)
            await R.press("g")
            check(await pg.locator("#rtable .pchip[data-acc]").count() >= 1, "the table shows the finding as an 'ist → soll' chip")
            await pg.screenshot(path=str(SHOTS / "i_table.png"))
            row = await pg.evaluate(f"LKGC.EM.obs.findIndex(x => x.key === {json.dumps(h['key'])})")
            chip = pg.locator(f"#rtable tr[data-o] >> nth={row} >> .pchip[data-acc]").first
            acc = await chip.get_attribute("data-acc")
            await chip.click()
            await pg.wait_for_timeout(250)
            d = await R.dec(h["key"]) or {}
            check(d.get("d") in ("a", "e") and acc.split("|")[0] in d.get("vals", {}), f"clicking the chip takes over that value ({acc})")
            h["chip"] = [acc.split("|")[0], d.get("vals", {}).get(acc.split("|")[0])]
            # a cell of a record without findings
            other = await pg.evaluate("(() => { const m = LKGC.EM; const o = m.obs.find(x => !LKGC.RV.dec[x.key] && !x.rec.auto && !['g', 's'].some(c => x.rec[c] && x.rec[c].v !== 'ok')); return o ? { key: o.key, i: m.obs.indexOf(o), idx: o.idx, written: o.written } : null; })()")
            if check(other is not None, "the entry has a record without findings"):
                cell = pg.locator(f"#rtable tr[data-o] >> nth={other['i']} >> td[data-f=count]")
                await cell.click()
                await pg.wait_for_timeout(200)
                if not await pg.locator("#rtable td input").count():
                    await cell.click()
                    await pg.wait_for_timeout(200)
                check(await pg.locator("#rtable td input").count() == 1, "clicking a cell opens the editor")
                await pg.keyboard.type("5 Paare und 3")
                await pg.keyboard.press("Enter")
                await pg.wait_for_timeout(200)
                check(await R.dec(other["key"]) is None and await pg.locator("#rtable td input.bad").count() == 1, "the cell editor refuses an unreadable count")
                await pg.fill("#rtable td input", "ca. 20")
                await pg.keyboard.press("Enter")
                await pg.wait_for_timeout(250)
                d = await R.dec(other["key"]) or {}
                check(d.get("d") == "e" and d.get("vals") == {"count": "ca. 20"}, "the cell editor stores the corrected count")
                h["cell"] = other
            await R.press("g")

        # ---------------------------------------------------------------- 2 missing records
        h = await R.find("miss", f"(rv, s) => s.miss.length && {SMALL}", "(it) => it.type === 'miss' && it.x.kind === 'observation' && it.x.de && it.x.text")
        if h:
            await R.open(h)
            await pg.keyboard.press("j")
            await pg.wait_for_timeout(250)
            check(await pg.evaluate("document.activeElement && document.activeElement.name") == "species_de", "J on a missing record opens the form")
            h["de"] = await pg.evaluate("document.activeElement.value")
            check(not h["de"].endswith("j") and h["de"] != "", "the form is prefilled from the suggestion and the key J is not typed")
            await pg.screenshot(path=str(SHOTS / "i_add_form.png"))
            await pg.fill('.rform input[name="count"]', "2")
            await pg.fill('.rform input[name="date"]', "")
            await pg.fill('.rform input[name="locality"]', "Testmoos")
            await pg.fill('.rform input[name="observer"]', "Adolf Müller")
            await pg.click(".rform button[type=submit]")
            await pg.wait_for_timeout(300)
            d = await R.dec(h["key"]) or {}
            check(d.get("d") == "add" and d.get("rec", {}).get("species_de") == h["de"] and d["rec"]["count"] == "2", "the missing record is added with the form values")
            h["text"] = d.get("rec", {}).get("text")
            check(await pg.locator("#gsvg .nd.k-miss.an-dec").count() >= 1, "the ghost node shows the reviewer's decision")
        h = await R.find("miss_no", f"(rv, s) => s.miss.length && {SMALL}", "(it) => it.type === 'miss' && it.x.kind === 'observation'")
        if h:
            await R.open(h)
            await R.press("n")
            check((await R.dec(h["key"]) or {}).get("d") == "no", "N: the missing record is not added")
        # a record added by hand
        if "ok" in R.made:
            await goto_entry(pg, R.made["ok"]["id"])
            await pg.click('#pbody [data-act="addrec"]')
            await pg.wait_for_timeout(250)
            await pg.fill('.rform input[name="species_de"]', "Kiebitz")
            await pg.fill('.rform textarea[name="text"]', "ein Kiebitz am Weiher")
            await pg.keyboard.press("Enter")
            await pg.wait_for_timeout(300)
            key = f"miss:{R.made['ok']['uid']}|ein Kiebitz am Weiher"
            check((await R.dec(key) or {}).get("d") == "add", "a record can be added by hand")
            R.made["manual"] = {"uid": R.made["ok"]["uid"], "key": key}

        # ---------------------------------------------------------------- 3 automatic changes of names
        h = await R.find("name_confirm", "(rv, s) => s.auto.some(k => k.startsWith('name:'))", "(it) => it.type === 'name' && it.x.kind === 'changed' && it.x.section === 'taxa'")
        if h:
            await R.open(h)
            check("ALLEN" in await pg.locator("#pbody .rcard.focus .scope").inner_text(), "the name card says that the decision applies to ALL entries")
            check(await pg.evaluate("/\\d/.test(document.querySelector('#pbody .rcard.focus .scope').innerText)"), "... and how many mentions the name has")
            await pg.screenshot(path=str(SHOTS / "i_name_card.png"))
            h["row"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.info.rows.find(r => r.auto)")
            h["form"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.form")
            await R.press("j")
            check((await R.dec(h["key"]) or {}).get("d") == "confirm", "J confirms the machine's name decision")
        for sec in ("places", "taxa"):
            h = await R.find("name_revert_" + sec, "(rv, s) => s.auto.some(k => k.startsWith('name:'))", f"(it) => it.type === 'name' && it.x.kind === 'changed' && it.x.section === '{sec}' && !LKGC.RV.dec[it.key]")
            if h:
                await R.open(h)
                h["before"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.info.before")
                h["form"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.form")
                await R.press("n")
                check((await R.dec(h["key"]) or {}).get("d") == "revert", f"N takes back the machine's {sec} decision")
        h = await R.find("name_removed", "(rv) => (rv.gone || []).some(g => g[0].startsWith('review_not_'))", "(it) => it.type === 'name' && it.x.kind === 'removed' && !LKGC.RV.dec[it.key]")
        if h:
            await R.open(h)
            h["form"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.form")
            await R.press("n")
            check((await R.dec(h["key"]) or {}).get("d") == "revert", "N takes back a name the machine removed")
        h = await R.find("name_suggest", "(rv, s, r) => r.nobs > 0", "(it) => it.type === 'name' && it.x.kind === 'suggest' && !LKGC.RV.dec[it.key]")
        if h:
            await R.open(h)
            h["row"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.info.rows[0]")
            h["form"] = await pg.evaluate("LKGC.visibleItems(LKGC.EM)[LKGC.RVU.card].x.form")
            await R.press("j")
            check((await R.dec(h["key"]) or {}).get("d") == "apply", "J applies a machine suggestion below the thresholds")

        # ---------------------------------------------------------------- 4 reading corrections: J N E
        h = await R.find("tc", "(rv, s) => s.lv.filter(x => x[2] === 'tc').length >= 3", "(it) => it.type === 'tc' && it.lv >= 1")
        if h:
            await goto_entry(pg, h["id"])
            keys = await pg.evaluate("[...new Set(LKGC.EM.items.filter(it => it.type === 'tc' && it.lv >= 1).map(it => it.key))].slice(0, 3)")
            h["keys"] = keys
            for key, k in zip(keys, ["j", "n", "e"]):
                await R.focus(key)
                await pg.keyboard.press(k)
                await pg.wait_for_timeout(250)
                if k == "e":
                    check(await pg.evaluate("document.activeElement && document.activeElement.name") == "final", "E opens the reading field with focus")
                    pre = await pg.evaluate(f"(it => it.c[8] || it.c[1])(LKGC.EM.items.find(x => x.key === {json.dumps(key)}))")
                    check(await pg.evaluate("document.activeElement.value") == pre, "the key E is not typed into the reading")
                    await pg.screenshot(path=str(SHOTS / "i_tc_cards.png"))
                    await pg.fill(".rform textarea[name=final]", "Testlesung der Prüferin")
                    await pg.keyboard.press("Enter")
                    await pg.wait_for_timeout(250)
            got = [((await R.dec(k)) or {}).get("d") for k in keys]
            check(got == ["accept", "reject", "edit"], f"reading corrections J N E stored {got}")
            await pg.click('#ptabs [data-tab="text"]')
            await pg.wait_for_timeout(200)
            check(await pg.locator("#fnotes .tci.v-acc, #fnotes .tci.v-rej, #fnotes .tci.v-edt").count() >= 1, "the text shows the reviewer's verdicts on the corrections")

        # ---------------------------------------------------------------- text: own correction of a passage
        h = await R.find("txt", "(rv, s, r) => r.nobs > 0 && (rv.tc || []).filter(c => c[2]).length <= 2", "(it, m) => it.type === 'ent'")
        if h:
            await goto_entry(pg, h["id"])
            await pg.click('#ptabs [data-tab="text"]')
            await pg.wait_for_timeout(250)
            sel = await pg.evaluate("""(() => { const spans = [...document.querySelectorAll('#fnotes span[data-s]')].filter(s => !s.classList.contains('tci') && s.firstChild && s.firstChild.nodeType === 3 && /\\p{L}{5,}/u.test(s.textContent));
              const sp = spans[spans.length - 1]; if (!sp) return null; const m = /\\p{L}{5,}/u.exec(sp.textContent); const r = document.createRange(); r.setStart(sp.firstChild, m.index); r.setEnd(sp.firstChild, m.index + m[0].length);
              const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); return m[0]; })()""")
            if check(sel is not None, "the entry text has a word to select"):
                await pg.click('#pbody [data-act="txtedit"]')
                await pg.wait_for_timeout(250)
                check(await pg.locator("#pbody .rform[data-kind=txt]").count() == 1 and await pg.locator(".rform .oldtext").inner_text() == sel, f"'Auswahl korrigieren' opens the form for the selected passage ({sel})")
                await pg.fill(".rform textarea[name=new]", sel + "X")
                await pg.keyboard.press("Enter")
                await pg.wait_for_timeout(250)
                key = f"txt:{h['uid']}|{sel}"
                check((await R.dec(key) or {}).get("new") == sel + "X", "the own text correction is stored")
                h["old"], h["new"] = sel, sel + "X"
                await pg.screenshot(path=str(SHOTS / "i_text_tab.png"))

        # ---------------------------------------------------------------- 5 entry header
        h = await R.find("ent", "(rv) => rv.ent && ['g', 's'].some(c => rv.ent[c] && rv.ent[c].date_ok === false && /^\\d{4}-\\d{2}-\\d{2}$/.test(rv.ent[c].date || ''))", "(it, m) => it.type === 'ent' && LKGC.entProposal(m).vals.date")
        if h:
            await R.open(h)
            h["date"] = await pg.evaluate("LKGC.entProposal(LKGC.EM).vals.date")
            await pg.screenshot(path=str(SHOTS / "i_header_card.png"))
            await R.press("j")
            d = await R.dec(h["key"]) or {}
            check((d.get("date") or {}).get("v") == h["date"], f"J applies the proposed entry date {h['date']}")
        h = await R.find("ent_edit", "(rv, s, r) => r.place >= 0 && r.nobs > 0", "(it) => it.type === 'ent'")
        if h:
            await R.open(h)
            cur = await pg.evaluate("LKGC.entCur(LKGC.EM)")
            h["cur"] = cur
            await pg.keyboard.press("e")
            await pg.wait_for_timeout(250)
            kind = "retrospective" if cur["kind"] != "retrospective" else "other"
            await pg.fill('.rform input[name="date"]', "1931-02-03")
            await pg.select_option('.rform select[name="kind"]', kind)
            await pg.fill('.rform input[name="place"]', "Testhausen")
            await pg.click(".rform button[type=submit]")
            await pg.wait_for_timeout(250)
            d = await R.dec(h["key"]) or {}
            check((d.get("date") or {}).get("v") == "1931-02-03" and (d.get("kind") or {}).get("v") == kind and (d.get("place") or {}).get("v") == "Testhausen", "E edits date, kind and place of the entry")
            h["kind"] = kind

        # ---------------------------------------------------------------- 6 removed / QA flags
        h = await R.find("qa_false", "(rv) => (rv.gone || []).some(g => g[0] === 'non_bird')", "(it) => it.type === 'qa' && it.q[0] === 'non_bird'")
        if h:
            await R.open(h)
            await pg.screenshot(path=str(SHOTS / "i_qa_card.png"))
            await R.press("n")
            check((await R.dec(h["key"]) or {}).get("d") == "false_alarm", "N: false alarm on an exclusion")
        h = await R.find("qa_confirm", "(rv) => (rv.qa || []).some(q => q[1] === 'flagged')", "(it) => it.type === 'qa' && it.q[1] === 'flagged'")
        if h:
            await R.open(h)
            await R.press("j")
            check((await R.dec(h["key"]) or {}).get("d") == "confirm", "J confirms a QA flag")

        # ---------------------------------------------------------------- 7 text inserts
        h = await R.find("ins", "(rv, s) => s.unread > 0", "(it) => it.type === 'media' && it.ins && (it.ins[3] === 'unread' || it.ins[3] === 'partly')")
        if h:
            await R.open(h)
            check(await pg.locator("#pbody .rcard.t-media .hint.warn").count() >= 1, "an unread insert says that its records are missing")
            await pg.screenshot(path=str(SHOTS / "i_ins_card.png"))
            await pg.keyboard.press("j")
            await pg.wait_for_timeout(250)
            check(await pg.locator("#pbody .rform[data-kind=add]").count() == 1, "J on an insert opens the form for a missing record")
            await R.press("Escape")

        # ---------------------------------------------------------------- Eintrag geprüft
        if "apply" in R.made:
            h = R.made["apply"]
            await goto_entry(pg, h["id"])
            n_items = await pg.evaluate("LKGC.visibleItems(LKGC.EM).length")
            await pg.evaluate(f"LKGC.focusCard({n_items - 1})")
            open_n = await pg.evaluate("LKGC.openFindings(LKGC.EM)")   # open items of level schwer or mittel
            await R.press("Enter")
            if open_n:
                check(not (await R.dec("entry:" + h["uid"]) or {}).get("checked"), "Enter with open findings asks again first")
                await R.press("Enter")
            d = await R.dec("entry:" + h["uid"]) or {}
            check(bool(d.get("checked")) and d["checked"].get("queue") and isinstance(d["checked"].get("impl"), list), "Enter on the last card marks the entry as checked")
            h["n"] = d.get("checked", {}).get("n")
            h["impl"] = len(d.get("checked", {}).get("impl", []))
            check(await pg.locator("#elist-pad .erow.on .b-ok").count() == 1, "the work list shows the tick")
            check(await pg.evaluate("LKGC.countQueues().done.n") == 1, "the queue 'Geprüft' counts the entry")
        await pg.evaluate("LKGC.go('/')")
        await pg.wait_for_timeout(500)
        check(await pg.locator("#rv-ov table.prec tr").count() >= 4, "the overview shows the precision table of the decisions")
        await pg.screenshot(path=str(SHOTS / "i_overview.png"), full_page=False)

        # ---------------------------------------------------------------- export and contracts
        files = await pg.evaluate("LKGC.exportFiles()")
        names = [f[0] for f in files]
        check(names == ZIP_FILES, f"the ZIP holds the ten files {names}")
        # the corpus filter is a view: the export is the same under the strictest corpus
        await pg.evaluate("LKGC.setCorpus(3)")
        await pg.wait_for_timeout(400)
        csv3 = {n: text for n, text in await pg.evaluate("LKGC.exportFiles()") if n.endswith(".csv")}
        check(csv3 == {n: text for n, text in files if n.endswith(".csv")} and len(csv3) >= 8, "the corpus filter does not change the export (same CSV files under 'strenger Kern mit Koordinaten')")
        check(await pg.evaluate("Object.keys(LKGC.RV.dec).length") > 20, "... nor the decisions")
        await pg.evaluate("LKGC.setCorpus(0)")
        await pg.wait_for_timeout(400)
        out = SHOTS / "export"
        (out / "review").mkdir(parents=True, exist_ok=True)
        for n, text in files:
            (out / n).write_text(text, encoding="utf-8", newline="")
        async with pg.expect_download() as dl:
            await pg.click("#btn-save")
            await pg.click('#modal [data-m="zip"]')
        zpath = SHOTS / "export.zip"
        await (await dl.value).save_as(str(zpath))
        import zipfile
        with zipfile.ZipFile(zpath) as z:
            check(sorted(z.namelist()) == sorted(ZIP_FILES) and z.testzip() is None, "the downloaded ZIP is valid and complete")
            check(z.read("review/observation_corrections.csv").decode("utf-8") == dict(files)["review/observation_corrections.csv"], "ZIP content = exported files")
        await pg.keyboard.press("Escape")

        # entries of the decisions, for applying the corrections to model objects
        uids = sorted({k.split(":", 1)[1].split("|")[0] for k in await pg.evaluate("Object.keys(LKGC.RV.dec)") if k.split(":")[0] in ("rec", "miss", "entry")})
        spec = await pg.evaluate("""(uids) => LKGC.G.ent.filter(r => uids.includes(LKGC.RVS.get(r.n).uid)).map(r => { const m = LKGC.buildModel(r.n); const d = LKGC.RV.dec['entry:' + m.uid] || {}; const c = LKGC.entCur(m);
            return { uid: m.uid, id: m.id, date: c.date.split('/')[0], place: (d.place && d.place.old) || c.place || c.header, observations: m.obs.map(o => [(o.rec.auto || []).some(a => a[0] === 'value') ? o.rec.auto.find(a => a[0] === 'value')[1] : o.written, o.idx]) }; })""", uids)
        (out / "entries.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        res = subprocess.run([REPO_PY, str(Path(__file__).with_name("loaders_check.py")), str(out / "review"), str(out / "entries.json")], capture_output=True, text=True, encoding="utf-8")
        if not check(res.returncode == 0, "the pipeline loaders read the export " + res.stderr[-600:]):
            await b.close()
            done(errs)
        L = json.loads(res.stdout.strip().splitlines()[-1])
        check(not L["warnings"], f"no loader warnings {L['warnings'][:4]}")
        M = R.made

        # --- observation_corrections.csv
        oc_rows, head = rows(files, "review/observation_corrections.csv")
        check(head == L["contract"]["observation_corrections"], "observation_corrections.csv has exactly the contract columns (FIELDS)")
        oc = L["observation_corrections"]
        check(len(oc) == len(oc_rows), f"the loader keeps every row of observation_corrections.csv ({len(oc)}/{len(oc_rows)})")
        check(all(r["reviewed_by"] == "TEST" and r["reviewed_at"] and r["entry_uid"] and r["entry_id"] for r in oc_rows), "rows carry reviewer, time, entry uid and id")

        def oc_set(uid, idx, field):
            return [c for c in oc if c["entry_uid"] == uid and c["action"] == "set" and c["obs_index"] == idx and c["field"] == field]
        if "apply" in M:
            for f, v in M["apply"]["vals"].items():
                got = oc_set(M["apply"]["uid"], M["apply"]["idx"], f)
                check(len(got) == 1 and got[0]["new"] == v and got[0]["written"] == M["apply"]["written"] and got[0]["occurrence"] == M["apply"]["occ"], f"applied finding arrives: {f} = {v!r} (written, obs_index, occurrence)")
        if "geo" in M:
            got = oc_set(M["geo"]["uid"], M["geo"]["idx"], "locality")
            check(len(got) == 1 and got[0]["new"] == M["geo"]["place"], "georeference 'nur dieser Datensatz' arrives as locality of that record")
        if "multi" in M:
            m = M["multi"]
            for f, v in (("count", "3-5"), ("locality", "Testweiher"), ("date", "1930-05-06"), ("observer", "W. Wüst"), ("co_observers", "E. Bezzel; H. Remold"), ("record_type", "third-party-report"), ("sex", m["sex"])):
                got = oc_set(m["uid"], m["idx"], f)
                check(len(got) == 1 and got[0]["new"] == v and got[0]["written"] == m["species"]["de"] and got[0]["occurrence"] is None, f"edited record: {f} = {v!r}, addressed by the NEW species name and obs_index")
        if "table" in M and "cell" in M["table"]:
            got = oc_set(M["table"]["uid"], M["table"]["cell"]["idx"], "count")
            check(len(got) == 1 and got[0]["new"] == "ca. 20", "count from the table cell arrives")
            got = oc_set(M["table"]["uid"], M["table"]["idx"], M["table"]["chip"][0])
            check(M["table"]["chip"][0] == "species" or (len(got) == 1 and got[0]["new"] == M["table"]["chip"][1]), "value taken from the chip arrives")
        adds = [c for c in oc if c["action"] == "add"]
        if "miss" in M:
            got = [c for c in adds if c["entry_uid"] == M["miss"]["uid"]]
            check(len(got) == 1 and got[0]["add"].get("species_de") == M["miss"]["de"] and got[0]["add"].get("count") == "2" and got[0]["add"].get("locality") == "Testmoos"
                  and got[0]["add"].get("observer") == "Adolf Müller" and got[0]["add"].get("text") == M["miss"]["text"] and "date" not in got[0]["add"], f"added record arrives with species, count, locality, observer, passage {got[:1]}")
        if "manual" in M:
            check(any(c["entry_uid"] == M["manual"]["uid"] and c["add"].get("species_de") == "Kiebitz" and c["add"].get("text") == "ein Kiebitz am Weiher" for c in adds), "record added by hand arrives")
        if "miss_no" in M:
            check(not any(c["entry_uid"] == M["miss_no"]["uid"] for c in adds), "a rejected missing record is not exported")
        ent_rows = [c for c in oc if c["written"] == ""]
        if "ent" in M:
            check(any(c["entry_uid"] == M["ent"]["uid"] and c["field"] == "entry_date" and c["new"] == M["ent"]["date"] for c in ent_rows), "entry date (J) arrives as entry_date with empty written")
        if "ent_edit" in M:
            e = M["ent_edit"]
            check(any(c["entry_uid"] == e["uid"] and c["field"] == "entry_date" and c["new"] == "1931-02-03" for c in ent_rows) and any(c["entry_uid"] == e["uid"] and c["field"] == "entry_kind" and c["new"] == e["kind"] for c in ent_rows), "edited entry date and kind arrive")

        # --- value_corrections.csv
        vc_rows, head = rows(files, "review/value_corrections.csv")
        check(head == L["contract"]["value_corrections"], "value_corrections.csv has exactly the contract columns (FIELDS)")
        vc = L["value_corrections"]
        check(len(vc) == len(vc_rows), f"the loader keeps every row of value_corrections.csv ({len(vc)}/{len(vc_rows)})")
        if "spurious" in M:
            check(any(c["kind"] == "taxon" and c["action"] == "drop" and c["entry_uid"] == M["spurious"]["uid"] and c["old"] == M["spurious"]["written"] and c["occurrence"] == M["spurious"]["occ"] for c in vc), "struck record (spurious) arrives as drop with name and occurrence")
        if "species" in M:
            sp = M["species"]["vals"]["species"]
            check(any(c["kind"] == "taxon" and c["action"] == "replace" and c["entry_uid"] == M["species"]["uid"] and c["old"] == M["species"]["written"] and c["new"] == sp["de"] and c["scientific_name"] == sp["sci"]
                      and c["occurrence"] == M["species"]["occ"] and (c["gbif_key"] or "") == (int(sp["key"]) if sp["key"] else "") for c in vc), "another species arrives as taxon replace with scientific name and GBIF key")
        if "multi" in M:
            m = M["multi"]
            mine = [c for c in vc if c["entry_uid"] == m["uid"] and c["old"].lower() == m["written"].lower()]
            check([c["occurrence"] for c in mine] == [2, 1, 0] and [c["action"] for c in mine] == ["drop", "replace", "drop"], f"rows of one name are ordered from the highest occurrence down {[(c['occurrence'], c['action']) for c in mine]}")
            check(mine[1]["new"] == m["species"]["de"] and (mine[1]["gbif_key"] or "") == (int(m["species"]["key"]) if m["species"]["key"] else ""), "the replaced species carries the GBIF key of the search")
        if "ent_edit" in M:
            e = M["ent_edit"]
            check(any(c["kind"] == "place" and c["action"] == "replace" and c["entry_uid"] == e["uid"] and c["new"] == "Testhausen" and c["old"] == (e["cur"]["place"] or e["cur"]["header"]) for c in vc), "replaced entry place arrives as kind=place")

        # --- applied to model entries in the pipeline's order
        A = L["applied"]
        unmatched = [f for f in A["flags"] if f[1] == "correction_unmatched"]
        check(not unmatched, f"every correction row finds its record when applied {unmatched[:3]}")
        E = A["entries"]

        def obs(uid, idx):
            return next((o for o in E[uid]["observations"] if o["index"] == idx), None)
        if "spurious" in M:
            check(obs(M["spurious"]["uid"], M["spurious"]["idx"]) is None, "applied: the spurious record is gone")
        if "species" in M:
            check((obs(M["species"]["uid"], M["species"]["idx"]) or {}).get("name") == M["species"]["vals"]["species"]["de"], "applied: the record carries the other species")
        if "geo" in M:
            check((obs(M["geo"]["uid"], M["geo"]["idx"]) or {}).get("locality") == M["geo"]["place"], "applied: the locality of that one record is set")
        if "multi" in M:
            m = M["multi"]
            gone = [s["idx"] for s in (m["same"][0], m["same"][2])]
            check(all(obs(m["uid"], i) is None for i in gone), f"applied: exactly the struck records {gone} are gone")
            o = obs(m["uid"], m["idx"]) or {}
            check(o.get("name") == m["species"]["de"] and (o.get("min"), o.get("max")) == (3, 5) and o.get("locality") == "Testweiher" and o.get("date") == "1930-05-06" and o.get("observer") == "W. Wüst"
                  and o.get("co") == ["E. Bezzel", "H. Remold"] and o.get("record_type") == "third-party-report" and o.get("sex") == m["sex"], f"applied: the edited record has species, count 3-5, locality, date, observers, type, sex {o}")
            others = [s for s in m["same"][3:]]
            check(all((obs(m["uid"], s["idx"]) or {}).get("name", "").lower() == m["written"].lower() for s in others), "applied: further records of that name are untouched")
        if "table" in M and "cell" in M["table"]:
            o = obs(M["table"]["uid"], M["table"]["cell"]["idx"]) or {}
            check(o.get("count") == 20 and o.get("qualifier") == "approximate", "applied: 'ca. 20' is an approximate count of 20")
        if "miss" in M:
            check(any(o["name"] == M["miss"]["de"] and o["text"] == M["miss"]["text"] and o["count"] == 2 and o["locality"] == "Testmoos" and o["observer"] == "Adolf Müller" for o in E[M["miss"]["uid"]]["observations"]), "applied: the missing record is added")
        if "ent_edit" in M:
            e = E[M["ent_edit"]["uid"]]
            check(e["date"] == "1931-02-03" and e["kind"] == M["ent_edit"]["kind"] and e["place"] == "Testhausen", f"applied: entry date, kind and place are corrected {e['date'], e['kind'], e['place']}")
        if "ent" in M:
            check(E[M["ent"]["uid"]]["date"] == M["ent"]["date"], "applied: the proposed entry date is set")

        # --- transcript_decisions.csv
        td_rows, head = rows(files, "review/transcript_decisions.csv")
        check(head == TD_HEAD, "transcript_decisions.csv has the contract columns")
        td = {(r["entry_uid"], r["old_text"], r["new_text"]): r for r in L["transcript_decisions"]}
        if "tc" in M:
            want = dict(zip(M["tc"]["keys"], ["accept", "reject", "edit"]))
            for key, dec in want.items():
                uid, old, new = key[3:].split("|", 2)
                got = td.get((uid, old, new))
                fin = {"accept": new, "reject": old, "edit": "Testlesung der Prüferin"}[dec]
                check(got is not None and got["decision"] == dec and got["final_text"] == fin, f"reading decision {dec} arrives keyed by (entry_uid, old_text, new_text) with final_text")
        # --- text_corrections.csv
        tc_rows, head = rows(files, "review/text_corrections.csv")
        check(head == L["contract"]["text_corrections"], "text_corrections.csv has exactly the contract columns (READING_FIELDS)")
        if "txt" in M and "old" in M["txt"]:
            check(any(r["entry_uid"] == M["txt"]["uid"] and r["old"] == M["txt"]["old"] and r["new"] == M["txt"]["new"] for r in L["text_corrections"]), "own text correction arrives (old_text, new_text)")
        # --- qa_decisions.csv
        qd_rows, head = rows(files, "review/qa_decisions.csv")
        check(head == QD_HEAD, "qa_decisions.csv has the contract columns")
        qd = {(r["entry_uid"], r["reason"], r["value"]): r["decision"] for r in L["qa_decisions"]}
        for name, dec in (("qa_false", "false_alarm"), ("qa_confirm", "confirm")):
            if name in M:
                uid, reason, value = M[name]["key"][3:].split("|", 2)
                check(qd.get((uid, reason, value)) == dec, f"QA decision {dec} arrives keyed by (entry_uid, reason, value)")
        # --- identities.csv
        id_rows, head = rows(files, "review/identities.csv")
        check(head == L["contract"]["identities"], "identities.csv has exactly the contract columns (IDENTITY_FIELDS)")
        ids = L["identities"]
        check(len(ids) == len(id_rows), f"the loader keeps every identities row ({len(ids)}/{len(id_rows)})")
        check(all(r["reviewed_by"] == "TEST" for r in id_rows), "identities rows carry the human reviewer")

        def ident(section, form):
            return [i for i in ids if i["section"] == section and i["name"].casefold() == form.casefold()]
        if "name_confirm" in M:
            h, r = M["name_confirm"], M["name_confirm"]["row"]
            got = ident("taxa", h["form"])
            auth = [list(a) for a in (tuple(tok.split(":", 1)) for tok in (r.get("auth") or "").split() if ":" in tok)]
            check(len(got) == 1 and got[0]["decision"] == r["d"] and got[0]["target"] == (r.get("t") or "") and got[0]["authority"] == auth and got[0]["scientific_name"] == (r.get("sci") or ""), f"confirmed machine row arrives as the same decision, now a human row {got[:1]}")
        if "name_revert_taxa" in M:
            h = M["name_revert_taxa"]
            got = ident("taxa", h["form"])
            bef = h["before"]
            ok = len(got) == 1 and ((got[0]["decision"] == "same" and got[0]["authority"] == [["gbif", str(bef[2])]] and got[0]["target"] == bef[0]) if bef and bef[2] else got[0]["decision"] == "unsure")
            check(ok, f"reverted species decision restores the earlier GBIF link (or blocks the machine row) {got[:1]} before {bef}")
        if "name_revert_places" in M:
            h = M["name_revert_places"]
            got = ident("places", h["form"])
            bef = h["before"]
            if bef and bef[1] not in (None, ""):
                ok = len(got) == 1 and got[0]["decision"] == "link" and got[0]["table"] == "links" and abs(got[0]["lat"] - float(bef[1])) < 1e-6 and abs(got[0]["lon"] - float(bef[2])) < 1e-6
            else:
                ok = len(got) == 1 and got[0]["decision"] == "nolink"
            check(ok, f"reverted place decision restores the earlier link {got[:1]} before {bef}")
        if "name_removed" in M:
            got = [i for i in ids if i["name"].casefold() == M["name_removed"]["form"].casefold()]
            check(len(got) == 1 and got[0]["decision"] == "unsure" and got[0]["table"] == "forms", "reverted removal arrives as a human form row that blocks the machine's 'none'")
        if "name_suggest" in M:
            h, r = M["name_suggest"], M["name_suggest"]["row"]
            got = [i for i in ids if i["name"].casefold() == h["form"].casefold() and i["decision"] == r["d"]]
            check(len(got) == 1, "applied suggestion arrives as the machine row, reviewed by the human")

        # --- statistics files
        ec, head = rows(files, "entry_checks.csv")
        check(head == ["entry_uid", "entry_id", "queue", "n_records", "confirmed", "corrected", "added", "dropped", "reviewed_by", "reviewed_at"], "entry_checks.csv columns")
        if "apply" in M and M["apply"].get("n") is not None:
            r = next((x for x in ec if x["entry_uid"] == M["apply"]["uid"]), None)
            check(r is not None and int(r["n_records"]) == M["apply"]["n"] and int(r["corrected"]) >= 1 and int(r["confirmed"]) >= M["apply"]["impl"] and r["queue"] and r["reviewed_by"] == "TEST", f"entry_checks.csv has the checked entry {r}")
        au, head = rows(files, "graph_audit.csv")
        kinds = {r["kind"] for r in au}
        want = {"record_wrong", "record_spurious", "missing_record", "missing_manual", "name_changed", "name_suggest", "reading_relevant", "entry_date", "qa_excluded", "qa_flagged", "text"}
        check(want <= kinds, f"graph_audit.csv has a row for every kind of decision (missing: {sorted(want - kinds)})")
        check(all(r["agreed"] in ("yes", "partly", "no", "") for r in au) and any(r["agreed"] == "yes" for r in au) and any(r["agreed"] == "no" for r in au), "graph_audit.csv says whether the human agreed with the machine")
        if "apply" in M:
            r = [x for x in au if x["key"] == M["apply"]["key"]]
            check(bool(r) and all(x["machine_verdict"] and x["human_decision"] == "a" for x in r) and any(x["agreed"] == "yes" for x in r), "an applied finding is audited as agreed, with the checker's proposal")
        if "ok" in M:
            r = [x for x in au if x["key"] == M["ok"]["key"] and x["machine_verdict"] in ("wrong", "spurious")]
            check(bool(r) and all(x["agreed"] == "no" for x in r), "a rejected finding is audited as disagreed")
        check(any(r["human_decision"] == "implicit_ok" for r in au), "records confirmed by 'Eintrag geprüft' are audited as implicit confirmations")
        prog = json.loads(dict(files)["graph_progress.json"])
        check(prog.get("app") == "laubmann-graphpruefung" and len(prog["state"]["dec"]) == await pg.evaluate("Object.keys(LKGC.RV.dec).length"), "graph_progress.json holds every decision")
        check("review/identities.csv" in dict(files)["LIESMICH.txt"] and "Pipeline" in dict(files)["LIESMICH.txt"], "LIESMICH.txt explains the files")
        keys = await pg.evaluate("Object.keys(LKGC.RV.dec)")
        import re
        pat = re.compile(r"^(rec:e_[0-9a-f]+\|[^|]*\|\d+|tc:e_[0-9a-f]+\|.*|qa:e_[0-9a-f]+\|[a-z_]+\|.*|miss:e_[0-9a-f]+\|.*|entry:e_[0-9a-f]+|name:(taxa|places|persons|habitats)\|.+|txt:e_[0-9a-f]+\|.+)$", re.S)
        check(all(pat.match(k) for k in keys) and all(k == k.lower() or not k.startswith(("rec:", "name:")) for k in keys), f"state keys follow the stable scheme ({len(keys)} keys)")
        print("decisions made:", sorted(M))
        await b.close()
        done(errs)

asyncio.run(main())
