"""Second search for persons a person batch left without a Wikidata item.

The candidates of prepare_persons.py come from a Wikidata search for the
written name; names written as initial + surname ("D. Lack", "E. Bezzel") or
with a title find nothing, so the agents answer "none" even for well-known
ornithologists. This script searches the SURNAME alone, keeps human items whose
description or occupation points to natural history (ornithologist, zoologist,
biologist, naturalist, taxidermist, forester, hunter, entomologist, botanist,
museum), enriches them (dates, occupation, GND) and writes new batches with
the same record shape for a second pass with the same INSTRUCTIONS.md.

    python tools/validation_ui/machine_review/research_persons.py --work <r3> --out <r3p> [--min-mentions 2]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Cache, get_json, instructions, read_json, write_json  # noqa: E402

API = "https://www.wikidata.org/w/api.php"
FIELD = re.compile(r"ornitholog|zoolog|biolog|naturalist|naturforscher|entomolog|botani|präparator|taxiderm|förster|forst|"
                   r"jäger|hunter|vogel|bird|museum|oolog|tierpark|zoo|professor|forscher|scientist|wissenschaftler", re.I)
TITLE = re.compile(r"^(dr|prof|frl|frau|fr|herr|hr|forstmeister|oberförster|förster|oberlehrer|lehrer|pfarrer|freiherr|frhr|"
                   r"graf|baron|cand|stud|dipl|ing|med|vet|rer|nat|geol|inspektor|direktor|jäger|revierjäger|präparator)\.?$", re.I)


def surname(names: list[str]) -> str | None:
    for n in sorted(names, key=len, reverse=True):
        toks = [t.strip(".,;()") for t in n.split()]
        toks = [t for t in toks if t and not TITLE.match(t) and not re.fullmatch(r"[A-ZÄÖÜ]\.?", t)
                and t.lower() not in ("v", "von", "van", "de", "der")]
        if toks and len(toks[-1]) >= 4 and toks[-1][0].isupper():
            return toks[-1]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True, help="workdir of the first person pass (persons/batches + answers)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-mentions", type=int, default=2)
    ap.add_argument("--per-batch", type=int, default=15)
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out).resolve()
    recs, ans = {}, {}
    for f in sorted((work / "persons" / "batches").glob("batch_*.json")):
        for r in read_json(f):
            recs[r["entity"]] = r
    for f in sorted((work / "persons" / "answers").glob("batch_*.json")):
        for a in read_json(f) or []:
            ans[a.get("entity")] = a
    todo = [e for e, a in ans.items() if e in recs and (a.get("wikidata") or "").strip() in ("none", "unclear", "")
            and recs[e]["n_mentions"] >= args.min_mentions]
    cache = Cache(out / "persons" / "wd_research_cache.json")
    new_recs = []
    for i, e in enumerate(todo, 1):
        r = recs[e]
        sn = surname([n["name"] for n in r["names"]] + [r["label"]])
        if not sn:
            continue
        key = f"search:{sn}"
        hits = cache.get(key)
        if hits is None:
            url = API + "?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": sn, "language": "de",
                                                      "uselang": "de", "type": "item", "format": "json", "limit": 30})
            hits = (get_json(url) or {}).get("search") or []
            cache.put(key, hits)
            time.sleep(0.3)
        cand_ids = [h["id"] for h in hits if FIELD.search(h.get("description") or "")]
        known = {c["qid"] for c in r.get("wikidata_candidates") or []}
        cand_ids = [q for q in cand_ids if q not in known][:6]
        if not cand_ids:
            continue
        ekey = "ent:" + "|".join(cand_ids)
        ents = cache.get(ekey)
        if ents is None:
            url = API + "?" + urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(cand_ids), "props": "labels|descriptions|claims",
                                                      "languages": "de|en", "format": "json"})
            ents = (get_json(url) or {}).get("entities") or {}
            cache.put(ekey, ents)
            time.sleep(0.3)
        cands = []
        for q in cand_ids:
            x = ents.get(q) or {}
            cl = x.get("claims") or {}

            def year(p):
                try:
                    return cl[p][0]["mainsnak"]["datavalue"]["value"]["time"][1:5]
                except (KeyError, IndexError, TypeError):
                    return ""

            def ids(p):
                out_ = []
                for s in cl.get(p, []):
                    v = ((s.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                    out_.append(v.get("id") if isinstance(v, dict) else v)
                return [v for v in out_ if v]

            human = "Q5" in ids("P31")
            if not human:
                continue
            lab = (x.get("labels") or {}).get("de", {}).get("value") or (x.get("labels") or {}).get("en", {}).get("value", "")
            desc = (x.get("descriptions") or {}).get("de", {}).get("value") or (x.get("descriptions") or {}).get("en", {}).get("value", "")
            gnd = ids("P227")
            cands.append({"qid": q, "label": lab, "description": desc, "born": year("P569"), "died": year("P570"),
                          "gnd": gnd[0] if gnd else "", "human": True, "found_by": f"surname search '{sn}'"})
        if cands:
            nr = dict(r)
            nr["wikidata_candidates"] = (r.get("wikidata_candidates") or []) + cands
            nr["first_pass"] = {"wikidata": ans[e].get("wikidata"), "gnd": ans[e].get("gnd"), "reason": ans[e].get("reason")}
            new_recs.append(nr)
        if i % 50 == 0:
            print(f"{i}/{len(todo)} searched, {len(new_recs)} with new candidates")
    cache.flush()
    bdir = out / "persons" / "batches"
    bdir.mkdir(parents=True, exist_ok=True)
    (out / "persons" / "answers").mkdir(parents=True, exist_ok=True)
    for i in range(0, len(new_recs), args.per_batch):
        write_json(bdir / f"batch_{i // args.per_batch + 1:03d}.json", new_recs[i:i + args.per_batch])
    text = (work / "persons" / "INSTRUCTIONS.md").read_text(encoding="utf-8").replace(
        str(work.resolve()).replace("\\", "/"), str(out).replace("\\", "/"))
    text += ("\n\nSecond pass: these persons were answered \"none\"/\"unclear\" before because no fitting candidate was offered "
             "(`first_pass`). New candidates were found by searching the surname alone (`found_by`). Link only when "
             "name, dates (alive at the mentions' years), field and context fit; otherwise keep none/unclear.\n")
    instructions(out / "persons" / "INSTRUCTIONS.md", text)
    # the merge reads wd_cache.json for the Wikidata<->GND cross-check
    wd = read_json(work / "persons" / "wd_cache.json", {}) or {}
    for r in new_recs:
        for c in r["wikidata_candidates"]:
            wd.setdefault(c["qid"], {"gnd": c.get("gnd"), "born": c.get("born"), "died": c.get("died")})
    write_json(out / "persons" / "wd_cache.json", wd, indent=0)
    print(f"{len(todo)} persons searched again; {len(new_recs)} with new candidates in "
          f"{(len(new_recs) + args.per_batch - 1) // args.per_batch} batches")


if __name__ == "__main__":
    main()
