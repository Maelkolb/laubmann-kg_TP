"""Machine review of the persons: batches with Wikidata and GND candidates.

One record per person of the graph that is linked to Wikidata or has at least
``--min-mentions`` mentions: written names with counts, roles, mention years,
diary passages, the automatic Wikidata link, the Wikidata candidates of the
linking stage (enriched with life dates, occupation, GND number) and GND
candidates from lobid.org (name search, persons only, with dates, occupation,
places of activity and the GND's own Wikidata cross-reference). An agent
decides per person: the fitting Wikidata item and/or GND record, none, or
unclear, with a reason.

    python tools/validation_ui/machine_review/prepare_persons.py payload.b64 <export>/review/person_link_review.csv \
        --out <workdir> [--min-mentions 3] [--per-batch 15]
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import known_verdicts, Cache, context, get_json, instructions, load_payload, write_json  # noqa: E402

INSTRUCTIONS = """# Person check — instructions

You are checking the persons mentioned in the ornithological field diaries of Alfred Laubmann (1886–1965, ornithologist at the Zoologische Staatssammlung München; diaries 1917–1965, mostly Bavaria) against authority files: Wikidata items and GND (Gemeinsame Normdatei) records. Work carefully but do not over-deliberate; read the batch file, write the answer file, reply. No web lookups are needed: the candidate data is complete.

Files (N = the batch number you were given, three digits):
- Batch: `{root}/persons/batches/batch_N.json` — an array of persons. Each has `entity` (id), `label` (canonical name in the graph), `names` (all written name forms with counts), `n_mentions`, `years` (first–last year of mention), `roles` (Beobachter = reported an observation, Quelle = source of information, Begleiter = companion on an excursion, Sammler = collector, zitiert = cited author, sonstige), `passages` (diary text with the name), `auto_qid` (the pipeline's automatic Wikidata link, unverified, may be wrong), `wikidata_candidates` (items with label, description, born, died, occupation, gnd, human) and `gnd_candidates` (GND persons found by name: gnd id, name, born, died, occupation, places, info, and `wikidata` when the GND record itself points to a Wikidata item).
- Answer: `{root}/persons/answers/batch_N.json`

For each person decide which Wikidata item and which GND record denote the person meant in the diary, or `none` (no candidate fits), or `unclear` (cannot tell). Rules: the person must have been alive at the mention years (a candidate who died before the first mention, or was born after the last, is excluded — except for role `zitiert`, where an older author can be cited); non-human items never fit; prefer ornithologists, zoologists, foresters, hunters, gamekeepers, naturalists, museum people, teachers and clergy of Bavarian places, Bavarian regional figures; a same-named politician, athlete, artist or scientist in another field is wrong unless a passage supports it; initials must be compatible with the candidate's given name; when the Wikidata item and a GND record are the same person (the GND candidate's `wikidata` equals the QID, or the Wikidata candidate's `gnd` equals the GND id) give both. Be conservative: when the evidence is only a surname or a title ("Prof. Müller") answer `unclear`, and when the passages show that the name forms of one entity mix different people, say so. Use the passages: they often say what the person did (shot a bird, sent a specimen, is a forester at X, a colleague at the museum).

Write the answers as JSON: an array with one object per person, in input order:
`{"entity": <id>, "label": "...", "wikidata": "<QID>|none|unclear", "gnd": "<GND id>|none|unclear", "auto_link_ok": true|false|null, "confidence": 0.0-1.0, "reason": "one or two short sentences in German, naming the decisive evidence"}`

`auto_link_ok` judges the pipeline's `auto_qid` (null when there is none). Then reply with only the answer file path and one line per person `label → wikidata / gnd (confidence)`.
"""

TITLE = ("Prof.", "Dr.", "Herr", "Herrn", "Frau", "Frl.", "Fräulein", "Lehrer", "Pfarrer", "Oberförster", "Förster", "Oberlehrer",
         "Präparator", "Apotheker", "Kustos", "Direktor", "Graf", "Freiherr", "Baron", "Hr.", "Hr", "Studienrat", "Ing.", "Major", "Hauptmann")


def bare(name: str) -> str:
    toks = [t for t in name.replace(",", " ").split() if t.rstrip(".") not in {t2.rstrip(".") for t2 in TITLE}]
    return " ".join(toks).strip()


def wd_enrich(qids: list[str], cache: Cache) -> None:
    todo = [q for q in qids if q and cache.get(q) is None]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        try:
            ents = get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims|labels|descriptions&languages=de|en&ids=" + "|".join(chunk)).get("entities", {})
        except RuntimeError as exc:
            print("wikidata failed", exc)
            continue
        occ_ids = set()
        rows = {}
        for q in chunk:
            en = ents.get(q, {})
            cl = en.get("claims") or {}

            def val(p):
                c = (cl.get(p) or [None])[0]
                return c["mainsnak"]["datavalue"]["value"] if c and c.get("mainsnak", {}).get("datavalue") else None

            def year(v):
                return v["time"][1:5] if isinstance(v, dict) and v.get("time") else ""
            occs = [c["mainsnak"]["datavalue"]["value"]["id"] for c in cl.get("P106", []) if c.get("mainsnak", {}).get("datavalue")]
            occ_ids |= set(occs)
            inst = val("P31")
            rows[q] = {"label": (en.get("labels", {}).get("de") or en.get("labels", {}).get("en") or {}).get("value", ""),
                       "desc": (en.get("descriptions", {}).get("de") or en.get("descriptions", {}).get("en") or {}).get("value", ""),
                       "born": year(val("P569")), "died": year(val("P570")), "gnd": (val("P227") or ""),
                       "human": bool(inst and inst.get("id") == "Q5"), "occ": occs}
        labels = {}
        occ_list = sorted(occ_ids)
        for j in range(0, len(occ_list), 50):
            try:
                got = get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=labels&languages=de|en&ids=" + "|".join(occ_list[j:j + 50])).get("entities", {})
            except RuntimeError:
                got = {}
            for k, en in got.items():
                labels[k] = (en.get("labels", {}).get("de") or en.get("labels", {}).get("en") or {}).get("value", k)
        for q, r in rows.items():
            r["occ"] = [labels.get(o, o) for o in r["occ"]]
            cache.put(q, r)
        cache.flush()
        time.sleep(0.5)


def gnd_search(name: str, cache: Cache, size: int = 6) -> list[dict]:
    key = "gnd:" + name.lower()
    hit = cache.get(key)
    if hit is None:
        q = urllib.parse.urlencode({"q": name, "filter": "type:Person", "format": "json", "size": size})
        try:
            d = get_json("https://lobid.org/gnd/search?" + q)
        except RuntimeError as exc:
            print("lobid failed", name, exc)
            return []
        hit = []
        for m in d.get("member", []):
            wd = next((s["id"].rsplit("/", 1)[-1] for s in m.get("sameAs", []) if "wikidata.org" in s.get("id", "")), "")
            hit.append({"gnd": m.get("gndIdentifier", ""), "name": m.get("preferredName", ""),
                        "born": (m.get("dateOfBirth") or [""])[0], "died": (m.get("dateOfDeath") or [""])[0],
                        "occupation": [o.get("label", "") for o in m.get("professionOrOccupation", [])][:4],
                        "places": [o.get("label", "") for o in m.get("placeOfActivity", []) + m.get("placeOfBirth", [])][:4],
                        "info": " ".join(m.get("biographicalOrHistoricalInformation", []))[:200],
                        "variants": [v for v in m.get("variantName", [])][:4], "wikidata": wd})
        cache.put(key, hit)
        time.sleep(0.25)
    return hit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("person_link_review")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-mentions", type=int, default=3)
    ap.add_argument("--known", nargs="*", default=None, help="machine_review.json / place_readings.json of earlier rounds")
    ap.add_argument("--per-batch", type=int, default=15)
    ap.add_argument("--wd-cache", default=None)
    ap.add_argument("--gnd-cache", default=None)
    ap.add_argument("--no-gnd", action="store_true")
    args = ap.parse_args()
    P = load_payload(args.payload)
    root = Path(args.out).resolve()
    PS, E = P["person"], P["E"]
    wd = Cache(args.wd_cache or root / "persons" / "wd_cache.json")
    gnd = Cache(args.gnd_cache or root / "persons" / "gnd_cache.json")

    plink = collections.defaultdict(list)
    with open(args.person_link_review, encoding="utf-8", newline="") as h:
        for r in csv.DictReader(h):
            if r.get("qid"):
                plink[r["person_name"].lower()].append(r)
    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(PS["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(PS["men"]):
        men_of[m[0]].append(mi)
    n_of = {ei: sum(PS["forms"][fi][1] for fi in fis) for ei, fis in forms_of.items()}

    selected = [ei for ei in forms_of if PS["ent"][ei][1] or n_of[ei] >= args.min_mentions]
    if args.known:
        known = known_verdicts(args.known)["person"]
        before = len(selected)
        selected = [ei for ei in selected
                    if PS["ent"][ei][0].lower() not in known
                    and not all(PS["forms"][fi][0].lower() in known for fi in forms_of[ei])]
        print(f"persons: {before - len(selected)} judged in earlier rounds, {len(selected)} to check")
    selected.sort(key=lambda ei: (-bool(PS["ent"][ei][1]), -n_of[ei]))
    print(f"persons selected: {len(selected)} (linked {sum(1 for ei in selected if PS['ent'][ei][1])})")

    qids = set()
    recs = []
    for ei in selected:
        ent = PS["ent"][ei]
        names = sorted(((PS["forms"][fi][0], PS["forms"][fi][1]) for fi in forms_of[ei]), key=lambda x: -x[1])
        cands = {}
        for fi in forms_of[ei]:
            for r in plink.get(PS["forms"][fi][0].lower(), []):
                cands.setdefault(r["qid"], {"qid": r["qid"], "label": r["wd_label"], "desc": r["wd_description"]})
        if ent[1] and ent[1] not in cands:
            cands[ent[1]] = {"qid": ent[1], "label": "", "desc": "im Graph verknüpft"}
        qids |= set(cands)
        years, roles, passages, seen = [], collections.Counter(), [], set()
        for fi in forms_of[ei]:
            for mi in men_of[fi]:
                m = PS["men"][mi]
                e = E[m[1]]
                if e[2]:
                    years.append(e[2][:4])
                for r in (m[5] or "sonstige").split("/"):
                    roles[r] += 1
                if e[0] not in seen and len(passages) < 6:
                    seen.add(e[0])
                    passages.append({"entry": e[0], "date": e[2], "text": context(e[7], m[2], m[3], 140)})
        recs.append({"entity": ei, "label": ent[0], "names": [{"name": n, "n": c} for n, c in names], "n_mentions": n_of[ei],
                     "years": f"{min(years)}–{max(years)}" if years else "", "roles": dict(roles.most_common()),
                     "passages": passages, "auto_qid": ent[1] or None, "auto_gnd": ent[2] or None,
                     "_cands": cands})
    print("wikidata enrichment of", len(qids), "items")
    wd_enrich(sorted(qids), wd)
    for rec in recs:
        out = []
        for q, c in rec.pop("_cands").items():
            x = wd.get(q) or {}
            out.append({"qid": q, "label": x.get("label") or c["label"], "description": x.get("desc") or c["desc"],
                        "born": x.get("born", ""), "died": x.get("died", ""), "occupation": x.get("occ", []),
                        "gnd": x.get("gnd", ""), "human": x.get("human", None)})
        rec["wikidata_candidates"] = out
        rec["gnd_candidates"] = []
        if not args.no_gnd:
            queries, seen = [], set()
            for nm in rec["names"][:3]:
                b = bare(nm["name"])
                if len(b) >= 4 and b.lower() not in seen and len(b.split()) >= 1:
                    seen.add(b.lower())
                    queries.append(b)
            found = {}
            for q in queries[:2]:
                for c in gnd_search(q, gnd):
                    if c["gnd"] and c["gnd"] not in found:
                        found[c["gnd"]] = dict(c, query=q)
            rec["gnd_candidates"] = list(found.values())[:8]
    gnd.flush()
    bdir = root / "persons" / "batches"
    bdir.mkdir(parents=True, exist_ok=True)
    (root / "persons" / "answers").mkdir(parents=True, exist_ok=True)
    for i in range(0, len(recs), args.per_batch):
        write_json(bdir / f"batch_{i // args.per_batch + 1:03d}.json", recs[i:i + args.per_batch])
    instructions(root / "persons" / "INSTRUCTIONS.md", INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"persons: {len(recs)} records in {(len(recs) + args.per_batch - 1) // args.per_batch} batches; "
          f"with GND candidates {sum(1 for r in recs if r['gnd_candidates'])}, with Wikidata candidates {sum(1 for r in recs if r['wikidata_candidates'])}")


if __name__ == "__main__":
    main()
