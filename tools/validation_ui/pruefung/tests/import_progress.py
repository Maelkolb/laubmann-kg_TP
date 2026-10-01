"""Import of earlier progress: Laubmann_Pruefung.html (decisions keyed by its item numbers,
translated with the legacy map), Laubmann_Abgleich.html v4 (keyed by name / label /
passage key), a ZIP export, and decisions still in the browser's storage of those pages.
Imported decisions must show up on the right cases and in the export."""
import asyncio
import csv
import io
import json
import zipfile
from playwright.async_api import async_playwright
from common import SHOTS, check, done, open_page, reload

T = "2026-09-30T12:00:00.000Z"

LEGACY_JS = """() => {
  const L = __lp.D.LEGACY; if (!L) return null;
  const K = __lp.KEY2I; const I = __lp.ITEMS;
  const find = (pred) => { for (let oi = 0; oi < L.keys.length; oi++) { const k = L.keys[oi]; if (k && K.has(k) && pred(k, I[K.get(k)], oi)) return oi; } return -1; };
  const oT = find((k, it) => k.startsWith('taxon:') && it.forms && it.forms.length);
  const oP = find((k, it) => k.startsWith('person:'));
  const oE = find((k, it, oi) => k.startsWith('entry:') && Object.keys(L.obs[oi] || {}).length > 0);
  const fi = Object.keys(L.forms.taxon)[0]; const mi = Object.keys(L.mens.taxon)[0];
  const dec = {};
  if (oT >= 0) dec[oT] = { d: 'a', note: 'alt', by: 'OLD', t: '""" + T + """', names: { [fi]: { d: 'k', by: 'OLD', t: '""" + T + """' } }, mens: { [mi]: { d: 'n', by: 'OLD', t: '""" + T + """' } } };
  if (oP >= 0) dec[oP] = { d: 'u', note: '', by: 'OLD', t: '""" + T + """' };
  let obsKey = null;
  if (oE >= 0) { const ok = Object.keys(L.obs[oE])[0]; obsKey = L.obs[oE][ok]; dec[oE] = { d: 'a', by: 'OLD', t: '""" + T + """', obs: { [ok]: { d: 'n', by: 'OLD', t: '""" + T + """' } } }; }
  dec[999999] = { d: 'a', by: 'OLD', t: '""" + T + """' };
  return { json: { app: 'laubmann-pruefung', v: 1, export: L.export, built: L.built, state: { who: 'OLD', dec, log: [{ i: oT, d: 'a', t: '""" + T + """', by: 'OLD', lab: 'x' }], ui: {} } },
    expect: { tKey: L.keys[oT], pKey: L.keys[oP], eKey: L.keys[oE], name: L.forms.taxon[fi], mkey: L.mens.taxon[mi], obsKey } };
}"""

ABGLEICH_JS = """() => {
  const I = __lp.ITEMS, Q = __lp.QUEUES;
  const tx = I.find(x => x.t === 'taxon' && x.forms && x.forms.length);
  const tname = tx ? (__lp.D.FORMS.taxon[tx.forms[0]] || [''])[0].toLowerCase() : 'x';
  const tgt = __lp.D.TAXA[0];
  const pers = I.find(x => x.t === 'person' && x.q !== 'unchecked') || I.find(x => x.t === 'person');
  const plc = I.find(x => x.t === 'place' && x.q === 'unchecked') || I.find(x => x.t === 'place');
  const hab = I.find(x => x.t === 'habitat');
  const tx2 = I.find(x => x.t === 'taxon' && x !== tx && x.q !== 'sample');
  const men = Object.keys(__lp.D.MEN.taxon)[0];
  const m = __lp.D.MEN.taxon[men]; const mkey = __lp.D.E[m[1]][1] + '|' + __lp.D.FORMS.taxon[m[0]][0].toLowerCase() + '|' + (m.length > 6 ? m[6] : 0);
  const qa = Q.qa[0]; const e0 = __lp.D.E[Object.keys(__lp.D.E)[0]];
  const t = '""" + T + """', by = 'ALT';
  const j = { app: 'histornigraph-validation', version: 4, export: 'kg_exports_2026-08-19', who: 'ALT',
    id: { taxon: { [tname]: { d: 'r', target: { label: tgt[0], sci: tgt[1], key: tgt[2], rank: tgt[3] }, by, t } }, person: {}, place: {}, habitat: {} },
    men: { taxon: { [mkey]: { d: 'n', reason: 'misread', by, t } }, person: {}, place: {}, habitat: {} },
    ent: { taxon: tx2 ? { [tx2.label]: { d: 'n', by, t } } : {}, person: pers ? { [pers.label]: { d: 'y', qid: 'Q4115189', wd_label: 'Sandbox', by, t } } : {},
           place: plc ? { [plc.label]: { d: 'y', fix: { lat: '48.1', lon: '11.5', uncertainty_m: '1500' }, by, t } } : {}, habitat: hab ? { [hab.label]: { d: 'r', target: { code: 'C1', match: 'close' }, by, t } } : {} },
    grp: { place: plc ? { [plc.label]: { d: 'y', by, t } } : {}, taxon: {}, person: {}, habitat: {} },
    text: [{ id: 'v4x', entry_uid: e0[1], entry_id: e0[0], old: 'foo', new: 'bar', by, t }],
    qa: qa ? { [qa.id + '|' + qa.k + '|' + qa.label]: { d: 'n', by, t } } : {},
    ev: { [mkey]: { d: 'y', by, t } } };
  return { json: j, expect: { tname, tgtKey: tgt[2], mkey, persKey: pers && pers.key, plcKey: plc && plc.key, habKey: hab && hab.key, tx2Key: tx2 && tx2.key, qaKey: qa && qa.key, uid: e0[1] } };
}"""


def csv_rows(files, name):
    return list(csv.DictReader(io.StringIO(dict(files)[name])))


async def main():
    async with async_playwright() as p:
        # ---- 1. progress file of Laubmann_Pruefung.html (item numbers -> stable keys)
        b, pg, errs = await open_page(p)
        r = await pg.evaluate(LEGACY_JS)
        check(r is not None, "page carries the legacy map of Laubmann_Pruefung")
        if r:
            f = SHOTS / "legacy_pruefung_progress.json"
            f.write_text(json.dumps(r["json"]), encoding="utf-8")
            await pg.set_input_files("#fileImport", str(f))
            await pg.wait_for_timeout(500)
            ex = r["expect"]
            S = await pg.evaluate("__lp.S")
            if ex.get("tKey"):
                check((S["dec"].get(ex["tKey"]) or {}).get("d") == "a", f"legacy item decision mapped to {ex['tKey']}")
            if ex.get("pKey"):
                check((S["dec"].get(ex["pKey"]) or {}).get("d") == "u", f"legacy person decision mapped to {ex['pKey']}")
            check((S["names"]["taxon"].get(ex["name"]) or {}).get("d") == "k", f"legacy name decision mapped to the written name {ex['name']!r}")
            check((S["mens"]["taxon"].get(ex["mkey"]) or {}).get("d") == "n", f"legacy passage decision mapped to {ex['mkey']!r}")
            if ex.get("eKey"):
                check(ex["obsKey"] in ((S["dec"].get(ex["eKey"]) or {}).get("obs") or {}), "legacy observation row decision mapped to written|occurrence")
            check(any(l.get("k") == ex.get("tKey") for l in S["log"]), "legacy log entries carried over")
            check(S["who"] == "OLD", "reviewer name taken over")
            files = await pg.evaluate("__lp.exportFiles()")
            vc = csv_rows(files, "review/value_corrections.csv")
            check(any(f"{x['entry_uid']}|{x['old_value'].lower()}|{x['occurrence']}" == ex["mkey"] and x["action"] == "drop" for x in vc), "legacy passage decision exported")
        await b.close()

        # ---- 2. Laubmann_Abgleich.html v4 backup (names, labels, passage keys)
        b, pg, errs2 = await open_page(p)
        errs += errs2
        await pg.fill("#who", "NEU")
        r = await pg.evaluate(ABGLEICH_JS)
        f = SHOTS / "abgleich_v4_progress.json"
        f.write_text(json.dumps(r["json"]), encoding="utf-8")
        await pg.set_input_files("#fileImport", str(f))
        await pg.wait_for_timeout(500)
        ex = r["expect"]
        S = await pg.evaluate("__lp.S")
        nm = S["names"]["taxon"].get(ex["tname"]) or {}
        check(nm.get("d") == "o" and str((nm.get("target") or {}).get("key")) == str(ex["tgtKey"]), "Abgleich name reassignment -> name decision with target")
        check((S["mens"]["taxon"].get(ex["mkey"]) or {}).get("d") == "n", "Abgleich passage decision -> passage store")
        if ex.get("persKey"):
            d = S["dec"].get(ex["persKey"]) or {}
            check(d.get("d") in ("o", "a") and (d.get("d") == "a" or (d.get("target") or {}).get("qid") == "Q4115189"), f"Abgleich person link -> {d.get('d')}")
        if ex.get("plcKey"):
            d = S["dec"].get(ex["plcKey"]) or {}
            check(d.get("d") in ("o", "a") and (d.get("d") == "a" or abs((d.get("target") or {}).get("lat", 0) - 48.1) < 1e-6), "Abgleich place fix -> location decision")
        if ex.get("habKey"):
            d = S["dec"].get(ex["habKey"]) or {}
            check(d.get("d") == "o" and (d.get("target") or {}).get("code") == "C1", "Abgleich EUNIS class -> habitat decision")
        if ex.get("tx2Key"):
            d = S["dec"].get(ex["tx2Key"]) or {}
            check(d.get("d") in ("o", "a", "r") and (d.get("d") != "o" or (d.get("target") or {}).get("own")), "Abgleich taxon 'keine' -> drop the GBIF link (own)")
        if ex.get("qaKey"):
            check((S["dec"].get(ex["qaKey"]) or {}).get("d") == "r", "Abgleich QA 'falsch erkannt' -> false alarm")
        check(any(t.get("old") == "foo" for t in S["text"]), "Abgleich reading corrections kept")
        check(ex["mkey"] in S["ev"], "Abgleich evaluation sample kept")
        check(S["who"] == "NEU", "own reviewer name is not overwritten by an import")
        files = await pg.evaluate("__lp.exportFiles()")
        names = [x[0] for x in files]
        ids = csv_rows(files, "review/identities.csv")
        check(any(x["name_form"].lower() == ex["tname"] and x["authority"] == "gbif:" + str(ex["tgtKey"]) for x in ids), "imported name decision exported to identities.csv")
        if ex.get("habKey"):
            check(any(x["section"] == "habitats" and x["authority"] == "eunis:C1" for x in ids), "imported EUNIS class exported")
        if ex.get("plcKey"):
            check(any(x["section"] == "places" and x["lat"] and abs(float(x["lat"]) - 48.1) < 1e-6 for x in ids), "imported place location exported")
        tcx = csv_rows(files, "review/text_corrections.csv")
        check(any(x["old_text"] == "foo" and x["new_text"] == "bar" for x in tcx), "imported reading correction exported to text_corrections.csv")
        if ex.get("qaKey"):
            check(any(x["decision"] == "false_alarm" for x in csv_rows(files, "review/qa_decisions.csv")), "imported QA decision exported")
        check("evaluation_imported.csv" in names, "imported evaluation judgements exported")
        n_before = len(S["dec"])
        # ---- 3. ZIP of this page's own export (re-import is idempotent)
        zpath = SHOTS / "own_export.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for n, text in files:
                z.writestr(n, text)
        await pg.set_input_files("#fileImport", str(zpath))
        await pg.wait_for_timeout(500)
        check(await pg.evaluate("Object.keys(__lp.S.dec).length") == n_before, "ZIP re-import changes nothing (idempotent)")
        await b.close()

        # ---- 4. decisions still in this browser from the earlier pages
        b, pg, errs3 = await open_page(p)
        errs += errs3
        r1 = await pg.evaluate(LEGACY_JS)
        r2 = await pg.evaluate(ABGLEICH_JS)
        await pg.evaluate("([a, b]) => { localStorage.setItem('laubmann-pruefung-v1', JSON.stringify(a)); localStorage.setItem('hog-validation-v2', JSON.stringify(b)); }",
                          [r1["json"]["state"] if r1 else {"dec": {}}, {k: v for k, v in r2["json"].items() if k not in ("app", "version", "export")}])
        await reload(pg)
        await pg.click('#tabs .tab[data-tab="home"]')
        await pg.wait_for_timeout(200)
        n_btn = await pg.locator("[data-legacy]").count()
        check(n_btn == (2 if r1 else 1), f"home offers the browser's earlier decisions ({n_btn} buttons)")
        await pg.screenshot(path=str(SHOTS / "import_banner.png"))
        for _ in range(n_btn):
            await pg.click("[data-legacy] >> nth=0")
            await pg.wait_for_timeout(400)
        check(await pg.locator("[data-legacy]").count() == 0, "banner disappears after the take-over")
        check(await pg.evaluate("Object.keys(__lp.S.dec).length") > 0, "decisions taken over from the browser storage")
        await b.close()
        done(errs)

asyncio.run(main())
