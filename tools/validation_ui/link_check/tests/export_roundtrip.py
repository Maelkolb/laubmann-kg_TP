"""Interaction + export: decisions of every kind by keyboard and mouse, the ZIP, review/identities.csv read
by the pipeline's own loader (laubmann_kg.review.identities, run with the repo's Python), undo, change,
persistence, and the progress round trip (ZIP / JSON of this page, validation_progress.json of
Laubmann_Validierung.html).

    python tests/export_roundtrip.py [Laubmann_Verknuepfungen.html]
"""
import asyncio
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
from common import REPO, check, clear_state, done, open_page, open_first, reload

REPO_PY = os.environ.get("LC_REPO_PYTHON", str(REPO / ".venv" / "Scripts" / "python.exe"))
ID_HEAD = ["section", "name_form", "decision", "target", "authority", "scientific_name", "rank", "lat", "lon", "uncertainty_m", "eunis_match", "reason", "note", "reviewed_by", "reviewed_at"]
cf = lambda s: (s or "").strip().casefold()   # noqa: E731
FREE = "!__lc.S.ent[TY][e.k] && !e.forms.some(f => __lc.S.form[TY][__lc.cf(f.f)])"


async def ent(pg, ty, key):
    return await pg.evaluate(f"(e => e && ({{k: e.k, l: e.l, n: e.n, q: e.q, ck: e.ck || '', cur: e.cur, before: e.before || null, bsrc: e.bsrc || '', gone: !!e.gone, mg: e.mg || null, m: e.m || null,"
                             f" cands: e.cands || [], forms: e.forms.map(f => ({{f: f.f, n: f.n, was: f.was || null, m: f.m || null}}))}}))(__lc.BYK['{ty}'].get({json.dumps(key)}))")


async def pick(pg, ty, pred, queue=None):
    """Open the first entity matching the predicate that carries no decision yet; returns its record."""
    key = await open_first(pg, ty, f"e => ({pred}) && {FREE.replace('TY', repr(ty))}", queue)
    if key is None:
        print("skip (no entity):", ty, pred)
        return None
    await pg.evaluate("document.activeElement && document.activeElement.blur()")
    return await ent(pg, ty, key)


async def press(pg, *keys, wait=160):
    for k in keys:
        await pg.keyboard.press(k)
        await pg.wait_for_timeout(wait)


async def dec(pg, ty, key):
    return await pg.evaluate(f"__lc.S.ent['{ty}'][{json.dumps(key)}] || null")


async def fdec(pg, ty, name):
    return await pg.evaluate(f"__lc.S.form['{ty}'][__lc.cf({json.dumps(name)})] || null")


async def n_decisions(pg):
    return await pg.evaluate("['taxon','person','place','habitat'].map(t => Object.keys(__lc.S.ent[t]).length + Object.keys(__lc.S.form[t]).length).reduce((a, b) => a + b, 0)")


async def export_zip(pg, who=None):
    await pg.click("#btnExport")
    await pg.wait_for_selector("#exZip")
    if who is not None:
        await pg.fill("#who", who)
    async with pg.expect_download() as dl:
        await pg.click("#exZip")
    d = await dl.value
    path = await d.path()
    z = zipfile.ZipFile(path)
    files = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    await pg.click("[data-close]")
    return Path(path), files, d.suggested_filename


def run_loader(csv_text):
    tmp = Path(tempfile.mkdtemp(prefix="lc_ids_"))
    (tmp / "identities.csv").write_text(csv_text, encoding="utf-8", newline="")
    out = subprocess.run([REPO_PY, str(Path(__file__).resolve().parent / "loaders_check.py"), str(tmp)], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(out.stderr[-2000:])
        return None
    return json.loads(out.stdout.strip().splitlines()[-1])


async def main():
    async with async_playwright() as p:
        b, pg, errs = await open_page(p)
        made = {}

        # ---------------- species
        e = await pick(pg, "taxon", "e.cur && e.q === 'confirmed' && e.forms.length >= 2 && e.forms.every(f => !(f.m && !f.m.ap && f.m.diff))")
        if e:
            await press(pg, "j")
            d = await dec(pg, "taxon", e["k"]) or {}
            check(d.get("d") == "link" and d.get("via") == "confirm" and str(d.get("target", {}).get("key")) == str(e["cur"]["key"]), "J confirms a species link")
            check(await pg.locator("#state").count() == 1 and "Entschieden von dir" in await pg.inner_text("#state"), "the card shows 'Entschieden von dir'")
            await pg.fill("#note", "Testnotiz, mit Komma")
            await pg.wait_for_timeout(100)
            made["taxon_confirm"] = e
        e = await pick(pg, "taxon", "e.cur && e.forms.length >= 1 && !e.gone")
        if e:
            other = await pg.evaluate(f"__lc.D.TAXA.find(x => x[2] !== {json.dumps(e['cur']['key'])})")
            await press(pg, "a")
            check(await pg.evaluate("document.activeElement && document.activeElement.id") == "sInput", "A focuses the search box")
            check(await pg.input_value("#sInput") == "", "the key A is not typed into the search box")
            await pg.keyboard.type(other[1], delay=5)
            await pg.wait_for_timeout(200)
            await press(pg, "Escape", "1")
            d = await dec(pg, "taxon", e["k"]) or {}
            check(d.get("d") == "link" and str(d.get("target", {}).get("key")) == str(other[2]), "A + search + digit links another GBIF record")
            made["taxon_other"] = dict(e, target=d.get("target"), fs=d.get("fs"))
        e = await pick(pg, "taxon", "e.cur && !e.gone && e.forms.length === 1")
        if e:
            await press(pg, "x")
            check((await dec(pg, "taxon", e["k"]) or {}).get("d") == "none", "X: not a taxon")
            made["taxon_none"] = e
        e = await pick(pg, "taxon", "e.cur && !e.gone && e.forms.length === 2")
        if e:
            await press(pg, "n")
            check((await dec(pg, "taxon", e["k"]) or {}).get("d") == "nolink", "N: no record fits")
            made["taxon_nolink"] = e
        e = await pick(pg, "taxon", "e.gone")
        if e:
            await press(pg, "j")
            check((await dec(pg, "taxon", e["k"]) or {}).get("d") == "none", "J on a removed name confirms the removal")
            made["taxon_gone"] = e
        e = await pick(pg, "taxon", "e.q === 'changed' && e.ck === 'forms'")
        if e:
            await press(pg, "r")
            was = [f for f in e["forms"] if f["was"] and f["was"].get("known")]
            got = [await fdec(pg, "taxon", f["f"]) for f in was]
            check(was and all(g and g.get("via") == "revert" for g in got), "R reverts the names the machine assigned")
            made["taxon_revert"] = dict(e, was=was)
        e = await pick(pg, "taxon", "e.q === 'suggest' && e.forms.some(f => f.m && !f.m.ap && f.m.diff && (f.m.none || f.m.key))")
        if e:
            await press(pg, "v")
            sug = [f for f in e["forms"] if f["m"] and not f["m"].get("ap") and f["m"].get("diff") and (f["m"].get("none") or f["m"].get("key"))]
            got = [await fdec(pg, "taxon", f["f"]) for f in sug]
            check(all(g and g.get("via") == "accept" for g in got), "V accepts the machine's suggestions for single names")
            made["taxon_accept"] = dict(e, sug=sug)

        # ---------------- persons
        e = await pick(pg, "person", "e.cur && e.cur.qid && e.q !== 'changed'")
        if e:
            await press(pg, "j")
            made["person_confirm"] = e
        e = await pick(pg, "person", "e.q === 'changed' && e.ck === 'newlink' && e.bsrc")
        if e:
            await press(pg, "r")
            check((await dec(pg, "person", e["k"]) or {}).get("d") == "nolink", "R on a newly linked person: back to no link")
            made["person_revert"] = e
        e = await pick(pg, "person", "e.q === 'suggest' && e.m && e.m.prop && e.m.prop.qid && !e.m.prop.weak")
        if e:
            await press(pg, "v")
            d = await dec(pg, "person", e["k"]) or {}
            check(d.get("d") == "link" and d.get("via") == "accept" and d["target"].get("qid") == e["m"]["prop"]["qid"], "V accepts a person link the machine proposed")
            made["person_accept"] = e
        e = await pick(pg, "person", "!e.cur && !e.gone && e.cands && e.cands.length && e.cands[0].qid")
        if e:
            await press(pg, "1")
            d = await dec(pg, "person", e["k"]) or {}
            check(d.get("d") == "link" and d["target"].get("qid") == e["cands"][0]["qid"], "digit 1 takes the first candidate")
            made["person_cand"] = e
        e = await pick(pg, "person", "!e.cur && !e.gone && e.q === 'unlinked'")
        if e:
            await press(pg, "j")
            check((await dec(pg, "person", e["k"]) or {}).get("d") == "nolink", "J on an unlinked person: stays unlinked")
            made["person_nolink"] = e
        e = await pick(pg, "person", "e.mg && e.mg.length >= 1", queue="merge")
        if e:
            await press(pg, "j")
            v = e["mg"][0]["v"]
            g = await fdec(pg, "person", v) or {}
            check(g.get("d") == "same" and g.get("to") == e["mg"][0]["to"] and g.get("via") == "merge", "merge queue: J = same entity as the first candidate")
            made["merge_same"] = dict(e, v=v, to=e["mg"][0]["to"])
        e = await pick(pg, "person", "e.mg && e.mg.length >= 1", queue="merge")
        if e:
            await press(pg, "n")
            v = e["mg"][0]["v"]
            check((await fdec(pg, "person", v) or {}).get("d") == "own", "merge queue: N = different")
            made["merge_diff"] = dict(e, v=v)

        # ---------------- places
        e = await pick(pg, "place", "e.cur && e.cur.lat != null && e.cur.gn && e.q === 'confirmed'")
        if e:
            await press(pg, "j")
            made["place_confirm"] = e
        e = await pick(pg, "place", "!e.cur && !e.gone && e.q === 'unlinked'")
        if e:
            await pg.fill("#plat", "48,12345")
            await pg.fill("#plon", "11.54321")
            await pg.fill("#punc", "750")
            await pg.press("#plon", "Enter")
            await pg.wait_for_timeout(200)
            d = await dec(pg, "place", e["k"]) or {}
            check(d.get("d") == "link" and abs(d["target"]["lat"] - 48.12345) < 1e-6 and d["target"].get("unc") == 750, "typed coordinates set a place link")
            made["place_coords"] = e
        e = await pick(pg, "place", "!e.gone && e.forms.length === 2 && e.forms.every(f => f.n > 0)")
        if e:
            await press(pg, "x")
            made["place_none"] = e
        e = await pick(pg, "place", "!e.gone && e.forms.filter(f => f.n > 0 && __lc.cf(f.f) !== e.k).length >= 2")
        if e:
            var = [f["f"] for f in e["forms"] if cf(f["f"]) != e["k"]]
            await pg.click(f'.tb.own[data-form={json.dumps(var[0])}]')
            await pg.wait_for_timeout(150)
            await pg.click(f'.tb.other[data-form={json.dumps(var[1])}]')
            await pg.wait_for_timeout(150)
            target = await pg.evaluate(f"__lc.ENTS.place.find(x => x.k !== {json.dumps(e['k'])} && !x.gone).l")
            await pg.fill("#fInput", target)
            await pg.wait_for_timeout(200)
            await pg.press("#fInput", "Enter")
            await pg.wait_for_timeout(200)
            g0, g1 = await fdec(pg, "place", var[0]) or {}, await fdec(pg, "place", var[1]) or {}
            check(g0.get("d") == "own", "name toggle: an entry of its own")
            check(g1.get("d") == "same" and g1.get("to") == target, "name toggle: belongs to another entry (search)")
            made["place_forms"] = dict(e, own=var[0], moved=var[1], to=target)
        e = await pick(pg, "place", "!e.gone && e.forms.filter(f => f.n > 0 && __lc.cf(f.f) !== e.k).length >= 1 && e.cur")
        if e:
            var = [f["f"] for f in e["forms"] if cf(f["f"]) != e["k"]]
            await pg.click(f'.tb.none[data-form={json.dumps(var[0])}]')
            await pg.wait_for_timeout(150)
            check((await fdec(pg, "place", var[0]) or {}).get("d") == "none", "name toggle: not a name")
            await pg.click(f'.tb.none[data-form={json.dumps(var[0])}]')
            await pg.wait_for_timeout(150)
            check(await fdec(pg, "place", var[0]) is None, "clicking the active toggle again withdraws it")
            await pg.click(f'.tb.none[data-form={json.dumps(var[0])}]')
            await pg.wait_for_timeout(150)
            made["place_form_none"] = dict(e, name=var[0])

        # ---------------- habitats
        e = await pick(pg, "habitat", "e.cur && !e.gone")
        if e:
            await pg.click('[data-grade="broad"]')
            await press(pg, "j")
            d = await dec(pg, "habitat", e["k"]) or {}
            check(d.get("d") == "link" and d.get("grade") == "broad", "grade selector: confirmed as broad")
            made["habitat_confirm"] = e
        e = await pick(pg, "habitat", "e.cur && !e.gone && e.cur.code !== 'C1.2'")
        if e:
            await press(pg, "a")
            await pg.keyboard.type("C1.2", delay=5)
            await pg.wait_for_timeout(200)
            await press(pg, "Escape", "1")
            d = await dec(pg, "habitat", e["k"]) or {}
            check(d.get("d") == "link" and d["target"].get("code") == "C1.2", "habitat: EUNIS search + digit")
            made["habitat_other"] = e
        e = await pick(pg, "habitat", "e.gone && e.bsrc")
        if e:
            await press(pg, "r")
            d = await dec(pg, "habitat", e["k"]) or {}
            check(d.get("via") == "revert" and d.get("keep") == 1, "R on a removed habitat name restores it")
            made["habitat_restore"] = dict(e, d=d)
        e = await pick(pg, "habitat", "!e.gone")
        if e:
            await press(pg, "u")
            check((await dec(pg, "habitat", e["k"]) or {}).get("d") == "unsure", "U: unsure")
            made["habitat_unsure"] = e

        # ---------------- undo, change, withdraw
        e = await pick(pg, "habitat", "e.cur && !e.gone")
        if e:
            await press(pg, "j")
            check(await dec(pg, "habitat", e["k"]) is not None, "decision made (before undo)")
            await press(pg, "z")
            check(await dec(pg, "habitat", e["k"]) is None, "Z undoes the last decision")
            await press(pg, "j", "x")
            check((await dec(pg, "habitat", e["k"]) or {}).get("d") == "none", "a decision can be changed (J then X)")
            await pg.click('#state [data-act="clear"]')
            await pg.wait_for_timeout(150)
            check(await dec(pg, "habitat", e["k"]) is None and await pg.locator("#state").count() == 0, "a decision can be withdrawn")
        await pg.evaluate("__lc.setQueue('taxon', 'changed')")
        k0 = await pg.evaluate("__lc.cur.key")
        await press(pg, "Enter")
        k1 = await pg.evaluate("__lc.cur.key")
        check(k1 != k0 and not await pg.evaluate(f"__lc.entDone('taxon', __lc.BYK.taxon.get({json.dumps(k1)}))"), "Enter jumps to the next undecided entry")

        # ---------------- export
        n_before = await n_decisions(pg)
        await pg.click("#btnExport")
        await pg.wait_for_selector("#exZip")
        await pg.click("#exZip")
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("document.activeElement && document.activeElement.id") == "who", "the export asks for the reviewer's name first")
        await pg.click("[data-close]")
        zpath, files, fname = await export_zip(pg, "TEST")
        check(set(files) == {"review/identities.csv", "link_audit.csv", "link_progress.json", "LIESMICH.txt"}, f"ZIP holds the four files {sorted(files)}")
        check(fname.endswith(".zip") and "TEST" in fname, f"ZIP name carries the reviewer ({fname})")
        text = files["review/identities.csv"]
        rows = list(csv.DictReader(io.StringIO(text)))
        check(text.splitlines()[0].split(",") == ID_HEAD, "identities.csv has exactly the columns of the contract")
        check(all(r["reviewed_by"] == "TEST" for r in rows) and all(r["reviewed_at"][:2] == "20" and "T" in r["reviewed_at"] for r in rows), "reviewed_by remembered, reviewed_at ISO")
        check(await pg.evaluate("__lc.S.who") == "TEST", "the reviewer name is remembered")
        audit = list(csv.DictReader(io.StringIO(files["link_audit.csv"])))
        check(len(audit) == n_before, f"link_audit.csv: one row per decision ({len(audit)} / {n_before})")
        check(all(a["human_decision"] for a in audit) and any(a["machine_applied"] == "y" for a in audit) and any(a["pipeline_link"] for a in audit), "audit rows carry the human decision and the machine / pipeline state")

        # the corpus filter is a view: the export is the same under every filter, hidden entries keep their decisions
        hidden = await pg.evaluate("(() => { const out = []; for (const t of ['taxon','person','place','habitat']) for (const k of Object.keys(__lc.S.ent[t])) { const e = __lc.BYK[t].get(k);"
                                   " if (e && e.nc && e.nc[3] === 0) out.push(t + ':' + k); } return out; })()")
        same = []
        for c in ("1", "2", "3"):
            await pg.click(f'#corpbar .cbtn[data-corpus="{c}"]')
            await pg.wait_for_timeout(200)
            same.append(await pg.evaluate("__lc.exportIdentities()") == text and await pg.evaluate("__lc.exportFiles().find(f => f[0] === 'link_audit.csv')[1]") == files["link_audit.csv"])
        check(all(same), f"identities.csv and link_audit.csv are identical under every corpus filter {same}")
        _, files3, _ = await export_zip(pg)
        st0, st3 = json.loads(files["link_progress.json"])["state"], json.loads(files3["link_progress.json"])["state"]
        check(files3["review/identities.csv"] == text and files3["link_audit.csv"] == files["link_audit.csv"] and st0 == st3, "the ZIP exported under 'strenger Kern mit Koordinaten' equals the unfiltered one")
        gone_ = [h for h in hidden if not await pg.evaluate(f"__lc.corpusItems({json.dumps(h.split(':', 1)[0])}).some(e => e.k === {json.dumps(h.split(':', 1)[1])})")]
        check(hidden and gone_ == hidden and await n_decisions(pg) == n_before, f"{len(hidden)} decided entries without a mention in the corpus are hidden but keep their decisions")
        await pg.click('#corpbar [data-act="corpus-off"]')
        await pg.wait_for_timeout(200)
        check(await pg.evaluate("__lc.S.ui.corpus") == 0, "'Filter aufheben' in the corpus bar clears the filter")

        L = run_loader(text)
        if not check(L is not None, "the pipeline's Identities.load() reads the exported file"):
            return done(errs)
        kept = sum(len(v) for v in L["forms"].values()) + sum(len(v) for v in L["links"].values())
        check(L["rows"] == len(rows) == kept, f"every exported row is kept by the loader ({len(rows)} rows, {kept} kept)")
        check(not L["warnings"], f"no loader warnings {L['warnings'][:3]}")
        F, K = L["forms"], L["links"]

        def form(sec, name):
            return F[sec].get(cf(name)) or {}

        def link(sec, name):
            return K[sec].get(cf(name)) or {}

        if "taxon_confirm" in made:
            e = made["taxon_confirm"]
            check(all(form("taxa", f["f"]).get("decision") == "same" and str(form("taxa", f["f"]).get("gbif_key")) == str(e["cur"]["key"]) for f in e["forms"]),
                  f"loader: confirmed species -> same + gbif:{e['cur']['key']} for all {len(e['forms'])} written names")
            r0 = form("taxa", e["forms"][0]["f"])
            check("Testnotiz, mit Komma" in r0.get("note", "") and "match=" in r0.get("note", "") and r0.get("scientific_name") == e["cur"]["sci"], "loader: note, grade and scientific name arrive")
        if "taxon_other" in made:
            e = made["taxon_other"]
            check(all(str(form("taxa", n).get("gbif_key")) == str(e["target"]["key"]) for n in e["fs"]), "loader: relinked species -> the chosen GBIF key")
        if "taxon_none" in made:
            check(form("taxa", made["taxon_none"]["forms"][0]["f"]).get("decision") == "none", "loader: not a taxon -> none")
        if "taxon_nolink" in made:
            check(all(form("taxa", f["f"]).get("decision") == "own" for f in made["taxon_nolink"]["forms"]), "loader: no record fits -> own (GBIF link dropped)")
        if "taxon_gone" in made:
            check(form("taxa", made["taxon_gone"]["l"]).get("decision") == "none", "loader: removal confirmed -> none")
        if "taxon_revert" in made:
            ok = all((form("taxa", f["f"]).get("decision") == "same" and str(form("taxa", f["f"]).get("gbif_key")) == str(f["was"]["key"])) if f["was"].get("key")
                     else form("taxa", f["f"]).get("decision") == "own" for f in made["taxon_revert"]["was"])
            check(ok, "loader: reverted names -> the pipeline's GBIF key (or own where it had none)")
        if "taxon_accept" in made:
            ok = all(form("taxa", f["f"]).get("decision") == ("none" if f["m"].get("none") else "same") and (f["m"].get("none") or str(form("taxa", f["f"]).get("gbif_key")) == str(f["m"]["key"]))
                     for f in made["taxon_accept"]["sug"])
            check(ok, "loader: accepted name suggestions -> the machine's GBIF key / none")
        if "person_confirm" in made:
            e = made["person_confirm"]
            r = link("persons", e["l"])
            check(r.get("decision") == "link" and r.get("authority", {}).get("wd") == e["cur"]["qid"] and (not e["cur"].get("gnd") or r["authority"].get("gnd") == e["cur"]["gnd"]), "loader: person link wd: / gnd:")
        if "person_revert" in made:
            check(link("persons", made["person_revert"]["l"]).get("decision") == "nolink", "loader: reverted person -> nolink")
        if "person_accept" in made:
            e = made["person_accept"]
            check(link("persons", e["l"]).get("authority", {}).get("wd") == e["m"]["prop"]["qid"], "loader: accepted person suggestion -> its Wikidata item")
        if "person_cand" in made:
            e = made["person_cand"]
            check(link("persons", e["l"]).get("authority", {}).get("wd") == e["cands"][0]["qid"], "loader: candidate chosen by digit -> its Wikidata item")
        if "person_nolink" in made:
            check(link("persons", made["person_nolink"]["l"]).get("decision") == "nolink", "loader: unlinked person confirmed -> nolink")
        if "merge_same" in made:
            e = made["merge_same"]
            r = form("persons", e["v"])
            check(r.get("decision") == "same" and r.get("target") == e["to"], "loader: merge candidate accepted -> same with target")
            check(L["mapped"]["persons"]["mapping"].get(e["v"]) == e["to"], "resolution (apply_mappings) moves the name to its target")
        if "merge_diff" in made:
            e = made["merge_diff"]
            check(form("persons", e["v"]).get("decision") == "own" and e["v"] not in L["mapped"]["persons"]["mapping"], "loader: merge candidate rejected -> own, kept out of every merge")
        if "place_confirm" in made:
            e = made["place_confirm"]
            r = link("places", e["l"])
            check(r.get("decision") == "link" and abs(r["lat"] - e["cur"]["lat"]) < 1e-5 and abs(r["lon"] - e["cur"]["lon"]) < 1e-5 and str(r.get("geonames_id")) == str(e["cur"]["gn"]),
                  "loader: place link with lat/lon and gn:")
        if "place_coords" in made:
            r = link("places", made["place_coords"]["l"])
            check(r.get("decision") == "link" and abs(r["lat"] - 48.12345) < 1e-6 and abs(r["lon"] - 11.54321) < 1e-6 and r.get("uncertainty_m") == 750, "loader: typed coordinates and uncertainty")
        if "place_none" in made:
            check(all(form("places", f["f"]).get("decision") == "none" for f in made["place_none"]["forms"]), "loader: not a place -> none for every written name")
        if "place_forms" in made:
            e = made["place_forms"]
            check(form("places", e["own"]).get("decision") == "own" and form("places", e["moved"]).get("decision") == "same" and form("places", e["moved"]).get("target") == e["to"],
                  "loader: name decisions own / same (other entry)")
        if "place_form_none" in made:
            check(form("places", made["place_form_none"]["name"]).get("decision") == "none", "loader: name decision none")
        if "habitat_confirm" in made:
            e = made["habitat_confirm"]
            r = link("habitats", e["l"])
            check(r.get("authority", {}).get("eunis") == e["cur"]["code"] and r.get("eunis_match") == "broad", "loader: habitat link eunis: with eunis_match")
        if "habitat_other" in made:
            check(link("habitats", made["habitat_other"]["l"]).get("authority", {}).get("eunis") == "C1.2", "loader: other EUNIS class")
        if "habitat_restore" in made:
            e = made["habitat_restore"]
            want = "link" if e["d"]["d"] == "link" else "nolink"
            check(form("habitats", e["l"]).get("decision") == "own" and link("habitats", e["l"]).get("decision") == want,
                  f"loader: restored name -> own (overrides the machine's none in the forms table) + {want}")
        if "habitat_unsure" in made:
            check(form("habitats", made["habitat_unsure"]["l"]).get("decision") == "unsure", "loader: unsure")
        print("kinds of decisions made:", len(made), sorted(made))
        check(len(made) >= 20, f"at least 20 kinds of decisions were exercised ({len(made)})")

        # ---------------- persistence and round trips
        await reload(pg)
        check(await n_decisions(pg) == n_before, "decisions survive a reload (localStorage)")
        tmp = Path(tempfile.mkdtemp(prefix="lc_rt_"))
        (tmp / "link_progress.json").write_text(files["link_progress.json"], encoding="utf-8")
        await clear_state(pg)
        check(await n_decisions(pg) == 0, "cleared state is empty")
        await pg.set_input_files("#fileImport", str(tmp / "link_progress.json"))
        await pg.wait_for_timeout(500)
        check(await n_decisions(pg) == n_before, "link_progress.json restores every decision")
        again = await pg.evaluate("__lc.exportIdentities()")
        check(again == text, "the re-imported state exports the identical identities.csv")
        await clear_state(pg)
        zcopy = tmp / "export.zip"
        zcopy.write_bytes(Path(zpath).read_bytes())
        await pg.set_input_files("#fileImport", str(zcopy))
        await pg.wait_for_timeout(500)
        check(await n_decisions(pg) == n_before, "the exported ZIP is re-loadable")

        # progress of Laubmann_Validierung.html: name-level decisions and entry decisions
        await clear_state(pg)
        tx = await pg.evaluate("(e => ({l: e.l, k: e.k, f: e.forms.map(f => f.f), key: e.cur.key}))(__lc.ENTS.taxon.find(e => e.cur && e.forms.length >= 3 && !e.gone))")
        tx2 = await pg.evaluate(f"__lc.D.TAXA.find(x => x[2] !== {json.dumps(tx['key'])})")
        pl = await pg.evaluate("(e => ({l: e.l, k: e.k}))(__lc.ENTS.place.find(e => e.cur && !e.gone))")
        ps = await pg.evaluate("(e => ({l: e.l, k: e.k}))(__lc.ENTS.person.find(e => !e.gone && e.q === 'changed' && e.bsrc && !e.before))")
        stamp = "2026-10-02T10:00:00.000Z"
        prog = {"app": "laubmann-validierung", "v": 2, "state": {"who": "HK", "mens": {}, "text": [], "ev": {}, "log": [],
                "names": {"taxon": {tx["f"][1].lower(): {"d": "k", "by": "HK", "t": stamp}, tx["f"][2].lower(): {"d": "o", "target": {"label": tx2[0], "sci": tx2[1], "key": tx2[2], "rank": tx2[3]}, "by": "HK", "t": stamp}},
                          "person": {"ein unbekannter name": {"d": "x", "by": "HK", "t": stamp, "written": "Ein Unbekannter Name"}}, "place": {}, "habitat": {}},
                "dec": {"place:" + pl["l"].lower(): {"d": "k", "by": "HK", "t": stamp}, "person:" + ps["l"].lower(): {"d": "r", "by": "HK", "t": stamp},
                        "taxon:" + tx["l"].lower(): {"d": "u", "by": "HK", "t": stamp}, "tc:e_x|a|b": {"d": "a", "by": "HK", "t": stamp}}}}
        (tmp / "validation_progress.json").write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")
        with zipfile.ZipFile(tmp / "validierung.zip", "w", zipfile.ZIP_STORED) as z:
            z.writestr("review/identities.csv", "section,name_form\n")
            z.writestr("validation_progress.json", json.dumps(prog, ensure_ascii=False))
        await pg.set_input_files("#fileImport", str(tmp / "validierung.zip"))
        await pg.wait_for_timeout(500)
        g1, g2, g3 = await fdec(pg, "taxon", tx["f"][1]) or {}, await fdec(pg, "taxon", tx["f"][2]) or {}, await fdec(pg, "person", "Ein Unbekannter Name") or {}
        check(g1.get("d") == "none" and g1.get("by") == "HK", "Validierung import: name decision 'kein Vogel' -> none")
        check(g2.get("d") == "same" and g2.get("to") == tx2[0] and str((g2.get("toLink") or {}).get("key")) == str(tx2[2]), "Validierung import: name -> other species with its GBIF key")
        check(g3.get("d") == "own", "Validierung import: a name that has no entry here is kept and exported")
        check((await dec(pg, "place", pl["k"]) or {}).get("d") == "none" and (await dec(pg, "person", ps["k"]) or {}).get("d") == "nolink" and (await dec(pg, "taxon", tx["k"]) or {}).get("d") == "unsure",
              "Validierung import: entry decisions (none, reject -> state before, unsure)")
        L2 = run_loader(await pg.evaluate("__lc.exportIdentities()"))
        check(L2 is not None and not L2["warnings"] and L2["forms"]["persons"].get("ein unbekannter name", {}).get("decision") == "own" and L2["forms"]["taxa"].get(cf(tx["f"][1]), {}).get("decision") == "none",
              "imported decisions pass the pipeline loader")
        await b.close()
        done(errs)


asyncio.run(main())
