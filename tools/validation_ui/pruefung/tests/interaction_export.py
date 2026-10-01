"""Interaction + export: decisions of every kind by keyboard and mouse, the ZIP files in the
pipeline contracts (checked with the pipeline's loaders), undo, persistence and the
progress round trip (export -> clear -> import)."""
import asyncio
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from common import SHOTS, check, done, open_page, open_item, reload

REPO_PY = os.environ.get("LV_REPO_PYTHON", str(Path(__file__).resolve().parents[4] / ".venv" / "Scripts" / "python.exe"))
TD_HEAD = ["entry_uid", "entry_id", "old_text", "new_text", "decision", "final_text", "note", "reviewed_by", "reviewed_at"]
QD_HEAD = ["entry_uid", "entry_id", "reason", "value", "decision", "note", "reviewed_by", "reviewed_at"]
ID_HEAD = ["section", "name_form", "decision", "target", "authority", "scientific_name", "rank", "lat", "lon", "uncertainty_m", "eunis_match", "reason", "note", "reviewed_by", "reviewed_at"]


def rows(files, name):
    text = dict(files)[name]
    return list(csv.DictReader(io.StringIO(text))), text.splitlines()[0].split(",")


async def decide(pg, js, keys, wait=220):
    i = await open_item(pg, js.replace("x => ", "x => !__lp.S.dec[x.key] && ", 1))
    if i is None:
        print("skip (no item)", js)
        return None
    it = await pg.evaluate(f"(({{key, t, q, k, label, new: nw, cur, prop, forms, ei}}) => ({{key, t, q, k, label, new: nw, cur, prop, forms, ei}}))(__lp.ITEMS[{i}])")
    it["i"] = i
    for k in keys:
        await pg.keyboard.press(k)
        await pg.wait_for_timeout(wait)
    return it


async def dec(pg, key):
    return await pg.evaluate(f"__lp.S.dec[{json.dumps(key)}] || null")


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        await pg.fill("#who", "TEST")
        await pg.evaluate("__lp.S.ui.adv = false")
        made = {}

        # --- A: machine-checked
        it = await decide(pg, "x => x.q === 'change' && x.auto", ["j"])
        if it:
            made["auto"] = it
            check((await dec(pg, it["key"]) or {}).get("d") == "a", "J accepts an automatic change")
        it = await decide(pg, "x => x.q === 'change' && x.t === 'taxon' && x.cur && x.cur.key && x.prop && x.prop.key", ["n"])
        if it:
            made["reject"] = it
            check((await dec(pg, it["key"]) or {}).get("d") == "r", "N rejects a taxon change")
        it = await decide(pg, "x => (x.q === 'change' || x.q === 'open' || x.q === 'unchecked') && x.t === 'taxon' && x.k !== 'name-unsure'", ["a"])
        if it:
            label = await pg.evaluate("__lp.D.TAXA[0][0]")
            await pg.fill("#tsearch", label)
            await pg.wait_for_timeout(200)
            await pg.keyboard.press("1")
            await pg.wait_for_timeout(250)
            d = await dec(pg, it["key"]) or {}
            check(d.get("d") == "o" and (d.get("target") or {}).get("key"), "A + search + digit sets another species")
            made["taxon_other"] = dict(it, target=d.get("target"))
        it = await decide(pg, "x => x.q === 'change' && x.t === 'person' && x.prop && x.prop.qid", ["j"])
        if it:
            made["person_acc"] = it
        it = await decide(pg, "x => x.q === 'change' && x.t === 'place' && x.prop && x.prop.lat != null", ["j"])
        if it:
            made["place_acc"] = it
        it = await decide(pg, "x => x.q === 'sample' && x.t === 'taxon'", ["j"])
        if it:
            made["sample_yes"] = it
        it = await decide(pg, "x => x.q === 'sample' && x.t === 'person'", ["n"])
        if it:
            made["sample_person_no"] = it
        it = await decide(pg, "x => x.q === 'sample' && x.t === 'place'", ["a"])
        if it:
            await pg.wait_for_timeout(300)
            box = await pg.evaluate("(r => ({x: r.x, y: r.y, w: r.width, h: r.height}))(document.querySelector('#map').getBoundingClientRect())")
            await pg.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            await pg.wait_for_timeout(200)
            await pg.click("#lok")
            await pg.wait_for_timeout(250)
            d = await dec(pg, it["key"]) or {}
            check(d.get("d") == "o" and (d.get("target") or {}).get("lat") is not None, "sample place: A + map click sets a location")
            made["sample_place"] = it
        it = await decide(pg, "x => (x.q === 'open' || x.q === 'unchecked') && x.t === 'person'", ["a"])
        if it:
            await pg.fill("#pqid", "Q42")
            await pg.click("#pok")
            await pg.wait_for_timeout(250)
            d = await dec(pg, it["key"]) or {}
            check(d.get("d") == "o" and (d.get("target") or {}).get("qid") == "Q42", "person: QID entered by hand")
            made["person_q42"] = it

        # --- transcript corrections: J, N, E (typed text), U
        tcs = await pg.evaluate("__lp.QUEUES.tcSample.slice(0, 4).map(x => x.i)")
        check(len(tcs) >= 4, "at least 4 transcript corrections in the sample")
        tc_keys = []
        for i, k in zip(tcs, ["j", "n", "e", "u"]):
            await pg.evaluate(f"__lp.goto({i})")
            await pg.wait_for_timeout(200)
            key = await pg.evaluate(f"__lp.ITEMS[{i}].key")
            tc_keys.append(key)
            await pg.keyboard.press(k)
            await pg.wait_for_timeout(250)
            if k == "e":
                foc = await pg.evaluate("document.activeElement && document.activeElement.id")
                check(foc == "tval", "E opens the edit field with focus")
                val = await pg.evaluate("document.querySelector('#tval').value")
                pre = await pg.evaluate(f"(x => (x.m && x.m.better) || x.new)(__lp.ITEMS[{i}])")
                check(val == pre, "the key E is not typed into the edit field")
                await pg.fill("#tval", "Testtext der Prüferin")
                await pg.keyboard.press("Enter")
                await pg.wait_for_timeout(250)
        got = [((await dec(pg, k)) or {}).get("d") for k in tc_keys]
        check(got == ["a", "r", "e", "u"], f"transcript decisions J N E U stored {got}")
        await pg.screenshot(path=str(SHOTS / "i_tc.png"))

        # --- QA flags: J, N, A (fix with note)
        qas = await pg.evaluate("__lp.QUEUES.qa.slice(0, 3).map(x => x.i)")
        qa_keys = []
        for i, k in zip(qas, ["j", "n", "a"]):
            await pg.evaluate(f"__lp.goto({i})")
            await pg.wait_for_timeout(200)
            qa_keys.append(await pg.evaluate(f"__lp.ITEMS[{i}].key"))
            await pg.keyboard.press(k)
            await pg.wait_for_timeout(250)
            if k == "a":
                check(await pg.evaluate("document.activeElement && document.activeElement.id") == "qfix", "A opens the fix note with focus")
                check(await pg.evaluate("document.querySelector('#qfix').value") == "", "the key A is not typed into the note")
                await pg.keyboard.type("Datum falsch gelesen")
                await pg.keyboard.press("Enter")
                await pg.wait_for_timeout(250)
        got = [((await dec(pg, k)) or {}).get("d") for k in qa_keys]
        check(got == ["a", "r", "o"], f"QA decisions J N A stored {got}")

        # --- habitats: J (class right), A (other class via search), N (no class)
        hab = {}
        it = await decide(pg, "x => x.t === 'habitat' && x.q === 'habitat' && x.cur", ["j"])
        if it:
            hab["y"] = it
        it = await decide(pg, "x => x.t === 'habitat' && x.q === 'habitat'", ["a"])
        if it:
            await pg.fill("#hsearch", "C1.1")
            await pg.wait_for_timeout(200)
            await pg.keyboard.press("1")
            await pg.wait_for_timeout(250)
            d = await dec(pg, it["key"]) or {}
            check(d.get("d") == "o" and (d.get("target") or {}).get("code", "").startswith("C1.1"), "habitat: A + EUNIS search + digit")
            hab["o"] = dict(it, code=(d.get("target") or {}).get("code"))
        it = await decide(pg, "x => x.t === 'habitat' && x.q === 'habitat'", ["n"])
        if it:
            hab["k"] = it
        check(len(hab) == 3, "three habitat decisions made")
        it = await decide(pg, "x => x.t === 'habitat' && x.q === 'change' && x.prop && x.prop.code", ["j"])
        if it:
            hab["machine"] = it

        # --- part B: unchecked place -> not a place; name and passage sub-decisions
        it = await decide(pg, "x => x.q === 'unchecked' && x.t === 'place'", ["n"])
        if it:
            made["place_none"] = it
        it = await open_item(pg, "x => x.t === 'taxon' && x.forms.length >= 2 && x.q !== 'unchecked'")
        sub_name = None
        if it is not None:
            sub_name = await pg.evaluate("document.querySelectorAll('.nm .nn')[1].textContent")
            await pg.click(".nm:nth-child(2) .mb[data-v='k']")
            await pg.wait_for_timeout(250)
            check(await pg.evaluate(f"!!__lp.S.names.taxon[{json.dumps(sub_name.lower())}]"), "name ✗ stored under the written name")
        it = await open_item(pg, "x => x.t === 'taxon' && x.ev && x.ev.length >= 1")
        men_key = None
        if it is not None:
            await pg.click(".men .mb[data-v='n']")
            await pg.wait_for_timeout(250)
            men_key = await pg.evaluate("Object.keys(__lp.S.mens.taxon)[0]")
            check(bool(men_key) and men_key.count("|") >= 2, f"passage ✗ stored under entry_uid|name|occurrence ({men_key})")
        it = await decide(pg, "x => x.t === 'entry'", ["j"])
        if it:
            await pg.evaluate(f"__lp.goto({it['i']})")
            await pg.wait_for_timeout(200)
            if await pg.locator("tr.wrong .mb[data-v='n']").count():
                await pg.click("tr.wrong .mb[data-v='n'] >> nth=0")
                await pg.wait_for_timeout(200)
                d = await dec(pg, it["key"]) or {}
                check(d.get("d") == "a" and len(d.get("obs") or {}) == 1, "entry: finding accepted + one row overridden")

        # --- undo
        n0 = await pg.evaluate("Object.keys(__lp.S.dec).length")
        it = await decide(pg, "x => x.q === 'qa' && !__lp.S.dec[x.key]", ["j"])
        n1 = await pg.evaluate("Object.keys(__lp.S.dec).length")
        await pg.keyboard.press("z")
        await pg.wait_for_timeout(250)
        n2 = await pg.evaluate("Object.keys(__lp.S.dec).length")
        check(n1 == n0 + 1 and n2 == n0, f"Z undoes the last decision ({n0} -> {n1} -> {n2})")
        await pg.click('#tabs .tab[data-tab="log"]')
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOTS / "i_log.png"))
        check(await pg.locator("#work table.tbl tr").count() > 10, "log lists the decisions")

        # --- export and contracts
        files = await pg.evaluate("__lp.exportFiles()")
        names = [f[0] for f in files]
        for n in ["review/identities.csv", "review/value_corrections.csv", "review/text_corrections.csv", "review/transcript_decisions.csv", "review/qa_decisions.csv",
                  "observation_corrections.csv", "machine_audit.csv", "validation_log.csv", "validation_progress.json", "LIESMICH.txt"]:
            check(n in names, f"ZIP contains {n}")
        out = SHOTS / "export"
        (out / "review").mkdir(parents=True, exist_ok=True)
        for n, text in files:
            (out / n).write_text(text, encoding="utf-8")
        td, head = rows(files, "review/transcript_decisions.csv")
        check(head == TD_HEAD, "transcript_decisions.csv has exactly the contract columns")
        by = {r["decision"]: r for r in td}
        check(sorted(by) == ["accept", "edit", "reject", "unsure"], f"transcript decisions exported {sorted(by)}")
        if "accept" in by:
            check(by["accept"]["final_text"] == by["accept"]["new_text"], "accept: final_text = new_text")
            check(by["reject"]["final_text"] == by["reject"]["old_text"], "reject: final_text = old_text")
            check(by["edit"]["final_text"] == "Testtext der Prüferin", "edit: final_text = typed text")
            check(by["unsure"]["final_text"] == "", "unsure: no final_text")
            check(all(r["reviewed_by"] == "TEST" and r["entry_uid"] for r in td), "transcript rows carry reviewer and entry_uid")
        qd, head = rows(files, "review/qa_decisions.csv")
        check(head == QD_HEAD, "qa_decisions.csv has exactly the contract columns")
        check(sorted(r["decision"] for r in qd) == ["confirm", "false_alarm", "fix"], f"QA decisions exported {[r['decision'] for r in qd]}")
        check(any(r["decision"] == "fix" and "Datum falsch gelesen" in r["note"] for r in qd), "fix carries the typed note")
        ids, head = rows(files, "review/identities.csv")
        check(head == ID_HEAD, "identities.csv has the contract columns")
        hab_rows = [r for r in ids if r["section"] == "habitats"]
        check(any(r["decision"] == "link" and r["authority"].startswith("eunis:") and r["eunis_match"] for r in hab_rows), "habitat class exported as link eunis:<code> with eunis_match")
        if "o" in hab:
            check(any(r["authority"] == "eunis:" + hab["o"]["code"] for r in hab_rows), "habitat other class exported")
        check(any(r["decision"] == "nolink" for r in hab_rows), "habitat 'no class' exported as nolink")
        if "machine" in hab:
            check(any(r["authority"] == "eunis:" + hab["machine"]["prop"]["code"] and r["reviewed_by"] == "TEST" for r in hab_rows), "accepted machine habitat class exported with the reviewer")
        if sub_name:
            check(any(r["section"] == "taxa" and r["name_form"] == sub_name and r["decision"] == "none" for r in ids), "name ✗ exported as decision none")
        if "reject" in made:
            m = made["reject"]
            check(any(r["section"] == "taxa" and r["authority"] == "gbif:" + m["cur"]["key"] for r in ids), "rejected change pins the earlier GBIF key")
        if "taxon_other" in made and made["taxon_other"].get("target"):
            check(any(r["authority"] == "gbif:" + str(made["taxon_other"]["target"]["key"]) for r in ids), "other species exported with its GBIF key")
        if "person_q42" in made:
            check(any(r["section"] == "persons" and r["decision"] == "link" and "wd:Q42" in r["authority"] for r in ids), "person link wd:Q42 exported")
        if "sample_person_no" in made:
            check(any(r["section"] == "persons" and r["decision"] == "nolink" and r["name_form"] == made["sample_person_no"]["label"] for r in ids), "sample person N exported as nolink")
        if "place_none" in made:
            check(any(r["section"] == "places" and r["decision"] == "none" for r in ids), "unchecked place N exported as none")
        if "auto" in made:
            check(any(r["reviewed_by"] == "TEST" and "machine verdict accepted" in r["note"] for r in ids), "accepted machine rows exported with the reviewer")
        vc, _ = rows(files, "review/value_corrections.csv")
        if men_key:
            uid, name, occ = men_key.split("|")[0], "|".join(men_key.split("|")[1:-1]), men_key.split("|")[-1]
            check(any(r["entry_uid"] == uid and r["old_value"].lower() == name and r["action"] == "drop" and r["occurrence"] == occ for r in vc), "passage ✗ exported as drop with entry_uid/occurrence")
        res = subprocess.run([REPO_PY, str(Path(__file__).with_name("loaders_check.py")), str(out / "review")], capture_output=True, text=True, encoding="utf-8")
        check(res.returncode == 0, "pipeline loaders read the export " + res.stderr[-400:])
        if res.returncode == 0:
            L = json.loads(res.stdout.strip().splitlines()[-1])
            print("loaders:", {k: v for k, v in L.items() if k not in ("transcript", "qa")})
            check(not L["warnings"], f"no loader warnings {L['warnings'][:3]}")
            check(len(L["transcript"]) == 3, "transcript loader takes accept/reject/edit (not unsure)")
            check(sorted(L["qa"].values()) == ["confirm", "false_alarm", "fix"], "QA loader reads the three decisions")
            check(L["links"]["habitats"] >= 2, "identities loader: habitat links")

        # --- persistence and progress round trip
        ndec = await pg.evaluate("Object.keys(__lp.S.dec).length")
        nnames = await pg.evaluate("Object.keys(__lp.S.names.taxon).length")
        await reload(pg)
        check(await pg.evaluate("Object.keys(__lp.S.dec).length") == ndec, "decisions survive a reload")
        check(await pg.evaluate("__lp.S.who") == "TEST", "reviewer name survives a reload")
        prog = dict(files)["validation_progress.json"]
        pj = SHOTS / "progress_roundtrip.json"
        pj.write_text(prog, encoding="utf-8")
        await b.close()
        b, pg, errs2 = await open_page(p)          # a fresh browser profile: empty storage
        errs += errs2
        check(await pg.evaluate("Object.keys(__lp.S.dec).length") == 0, "fresh profile starts empty")
        await pg.set_input_files("#fileImport", str(pj))
        await pg.wait_for_timeout(600)
        check(await pg.evaluate("Object.keys(__lp.S.dec).length") == ndec, "progress JSON import restores every decision")
        check(await pg.evaluate("Object.keys(__lp.S.names.taxon).length") == nnames, "... and the name decisions")
        files2 = await pg.evaluate("__lp.exportFiles()")
        td2, _ = rows(files2, "review/transcript_decisions.csv")
        check(len(td2) == len(td), "re-export after import gives the same transcript decisions")
        await b.close()
        done(errs)

asyncio.run(main())
