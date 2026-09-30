"""Batches for model-assisted person matching (diary person -> Wikidata item).

For every person of the export that has Wikidata candidates (the automatic
link or the candidates of person_link_review.csv), one record with the name
forms, roles, the years of the mentions, a few passages, and the candidates
enriched with life dates, occupation and GND number (wbgetentities). A model
reads a batch and answers per person: the fitting candidate, "none", or
"unclear", with a reason. Answers are joined by person_matches_merge.py.

    python tools/validation_ui/person_batches.py payload.b64 <export>/review/person_link_review.csv \
        --out batches/ [--per-batch 15] [--cache wd_cache.json]
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

UA = {"User-Agent": "laubmann-kg validation UI (research use)"}


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def claim(en: dict, p: str):
    c = ((en.get("claims") or {}).get(p) or [None])[0]
    return c["mainsnak"]["datavalue"]["value"] if c and c.get("mainsnak", {}).get("datavalue") else None


def year(v) -> str:
    return v["time"][1:5] if isinstance(v, dict) and v.get("time") else ""


def enrich(qids: list[str], cache_path: Path) -> dict:
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = [q for q in qids if q not in cache]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        try:
            ents = get("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims|labels|descriptions&languages=de|en&ids=" + "|".join(chunk)).get("entities", {})
        except Exception as exc:  # noqa: BLE001
            print("wikidata failed", exc, "- retrying after 20 s")
            time.sleep(20)
            try:
                ents = get("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims|labels|descriptions&languages=de|en&ids=" + "|".join(chunk)).get("entities", {})
            except Exception as exc2:  # noqa: BLE001
                print("wikidata failed again", exc2)
                continue
        occ_ids = set()
        for q in chunk:
            en = ents.get(q, {})
            occs = [c["mainsnak"]["datavalue"]["value"]["id"] for c in (en.get("claims") or {}).get("P106", []) if c.get("mainsnak", {}).get("datavalue")]
            occ_ids.update(occs[:3])
            cache[q] = {"label": ((en.get("labels") or {}).get("de") or (en.get("labels") or {}).get("en") or {}).get("value", q),
                        "desc": ((en.get("descriptions") or {}).get("de") or (en.get("descriptions") or {}).get("en") or {}).get("value", ""),
                        "born": year(claim(en, "P569")), "died": year(claim(en, "P570")), "gnd": claim(en, "P227") or "",
                        "human": any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5" for c in (en.get("claims") or {}).get("P31", [])),
                        "occ": occs[:3]}
        time.sleep(1.5)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    # occupation labels
    occ_ids = sorted({o for q in qids for o in cache.get(q, {}).get("occ", []) if o not in cache})
    for i in range(0, len(occ_ids), 50):
        chunk = occ_ids[i:i + 50]
        try:
            ents = get("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=labels&languages=de|en&ids=" + "|".join(chunk)).get("entities", {})
            for o in chunk:
                cache[o] = {"label": ((ents.get(o, {}).get("labels") or {}).get("de") or (ents.get(o, {}).get("labels") or {}).get("en") or {}).get("value", o)}
        except Exception as exc:  # noqa: BLE001
            print("wikidata failed", exc)
        time.sleep(0.5)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("review_csv")
    ap.add_argument("--out", default="batches")
    ap.add_argument("--per-batch", type=int, default=15)
    ap.add_argument("--cache", default="wd_cache.json")
    ap.add_argument("--min-mentions", type=int, default=2)
    args = ap.parse_args()
    P = json.loads(gzip.decompress(base64.b64decode(Path(args.payload).read_text(encoding="utf-8"))))
    E, PS = P["E"], P["person"]
    cands: dict[str, list] = defaultdict(list)
    with open(args.review_csv, newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            if r.get("qid"):
                cands[r["person_name"].lower()].append(r["qid"])
    # entities: names, mentions
    ent_names = defaultdict(list)
    ent_men = defaultdict(list)
    for fi, f in enumerate(PS["forms"]):
        ent_names[f[2]].append(f)
    for m in PS["men"]:
        ent_men[PS["forms"][m[0]][2]].append(m)
    records = []
    for ei, ent in enumerate(PS["ent"]):
        names = ent_names.get(ei, [])
        men = ent_men.get(ei, [])
        if len(men) < args.min_mentions:
            continue
        qids = []
        if ent[1]:
            qids.append(ent[1])
        for f in names:
            for q in cands.get(f[0].lower(), []):
                if q not in qids:
                    qids.append(q)
        if not qids:
            continue
        years = sorted({E[m[1]][2][:4] for m in men if E[m[1]][2]})
        roles = defaultdict(int)
        for m in men:
            for r in (m[5] or "").split("/"):
                if r:
                    roles[r] += 1
        # up to 4 passages spread over time, the name highlighted
        ms = sorted(men, key=lambda m: E[m[1]][2] or "")
        picks = [ms[round(j * (len(ms) - 1) / 3)] for j in range(4)] if len(ms) > 4 else ms
        passages = []
        for m in picks:
            e = E[m[1]]
            t = e[7]
            a, b = (max(0, m[2] - 150), min(len(t), m[3] + 150)) if m[2] >= 0 else (0, 300)
            passages.append({"date": e[2], "entry": e[0], "text": ("…" if a else "") + t[a:b] + ("…" if b < len(t) else "")})
        records.append({"entity": ei, "label": ent[0], "auto_qid": ent[1] or "", "auto_gnd": ent[2] or "",
                        "names": [[f[0], f[1]] for f in sorted(names, key=lambda f: -f[1])], "n_mentions": len(men),
                        "years": (years[0] + "–" + years[-1]) if years else "", "roles": dict(roles), "passages": passages, "candidates": qids[:8]})
    print(len(records), "persons with candidates")
    cache = enrich(sorted({q for r in records for q in r["candidates"]}), Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(records), args.per_batch):
        batch = []
        for r in records[i:i + args.per_batch]:
            cs = []
            for q in r["candidates"]:
                c = cache.get(q, {})
                cs.append({"qid": q, "label": c.get("label", q), "description": c.get("desc", ""), "born": c.get("born", ""), "died": c.get("died", ""),
                           "occupation": ", ".join(cache.get(o, {}).get("label", o) for o in c.get("occ", [])), "gnd": c.get("gnd", ""), "human": c.get("human", False)})
            batch.append({**r, "candidates": cs})
        (out / f"batch_{i // args.per_batch + 1:03d}.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
    print("batches in", out)


if __name__ == "__main__":
    main()
