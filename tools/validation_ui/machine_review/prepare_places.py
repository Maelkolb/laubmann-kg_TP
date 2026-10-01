"""Machine review of the places: batches for the GeoNames links and for the
frequent places without a location.

Every place of the graph with at least ``--min-mentions`` mentions gets a
record: written names, mention roles, the location and GeoNames/Wikidata
record the graph carries (with the linking stage's source and note), the
ANCHORS of its entries (the entry-header places of the entries that mention
it, with coordinates and the distance to the graph's point), diary passages,
and candidate locations: the Nominatim results of the label alone (from the
linking cache) and of the label qualified by its most frequent anchor
("Süddamm, Ismaning" - the contextual geocoding docs/validation.md asks for),
queried live and cached. An agent judges whether the location is right, or
which candidate fits, or that the name is no place / not locatable.

    python tools/validation_ui/machine_review/prepare_places.py payload.b64 <export>/review/place_link_review.csv \
        --out <workdir> --nominatim-cache "<linking_cache>/nominatim_cache.json" [--min-mentions 3] [--per-batch 25]
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import known_verdicts, Cache, context, get_json, instructions, load_payload, read_json, write_json  # noqa: E402

INSTRUCTIONS = """# Place check — instructions

You are checking the places of a knowledge graph built from the ornithological field diaries of Alfred Laubmann (Bavaria, 1917–1965; he lived in München and Kaufbeuren, worked at the Zoologische Staatssammlung München, and made excursions mostly in Upper Bavaria and Swabia — Ismaninger Teichgebiet, Starnberger See, Ammersee, Chiemsee, Isar, Lech, Allgäu, Alps — with some travel to Austria, Italy, Switzerland, northern Germany and further). The transcription is machine-made and misreads place names. Work carefully but do not over-deliberate; read the batch file, write the answer file, reply. No web lookups are needed.

Files (N = the batch number you were given, three digits):
- Batch: `{root}/places/batches/batch_N.json` — an array of places. Each has `entity` (id), `label`, `names` (written forms with counts), `n_mentions`, `roles` (Kopfzeile = the entry's own place in its heading, Beobachtung = locality of an observation, Reise = leg of a journey), `kind` (the model's place kind), `graph` (the location the graph carries: lat, lon, uncertainty_m, geonames id and name/feature/country/admin1, wikidata, source and note of the linking stage; `null` when the place has no location), `anchors` (the header places of the entries mentioning this place, with their coordinates, how many of the entries they head, and the distance in km from the graph's point), `passages` (diary text with the name), and `candidates` (Nominatim/OpenStreetMap results: for the label alone and for the label qualified by the main anchor; each with display name, type, coordinates, distance to the main anchor, wikidata).
- Answer: `{root}/places/answers/batch_N.json`

For each place decide:
- `verdict`: `ok` (the graph's location and GeoNames record fit the diary's place), `wrong` (they point somewhere else — a same-named place in another region, a street instead of a village, a bridge in another city; then choose a candidate in `candidate` by its `id`, or describe the right location in `location_hint`), `unlocated_ok` (the graph has no location and one of the candidates fits — give it in `candidate`), `unlocatable` (a real place or micro-toponym that no candidate matches; give the best `location_hint`: "part of Ismaninger Teichgebiet, near Ismaning", "a bridge over the Isar in München"), `not_a_place` (the name is no place: a bird name, a person, a habitat word like "Wiese", a fragment of prose), `unsure`.
- Judge with the anchors and passages: a village 300 km from every entry that mentions it is almost certainly a homonym; a place the diary reaches by train from München in a morning is near München; a "See", "Weiher", "Moos", "Filz" belongs to the landscape of its anchors; typical misreadings turn Ismaning into "Ismanning", Pöcking into "Pöking", Maisinger See into "Mainiger See" — a candidate whose name differs by a letter and lies at the anchors is usually right.
- `uncertainty_m`: your estimate of the radius in metres that covers the place (village 1000–2000, town 5000, lake 2000–5000, region 10000+, street/bridge 200–500).

Write the answers as JSON, an array with one object per place in input order:
`{"entity": <id>, "label": "...", "verdict": "ok|wrong|unlocated_ok|unlocatable|not_a_place|unsure", "candidate": "<candidate id>|null", "location_hint": "text or null", "uncertainty_m": <int or null>, "confidence": 0.0-1.0, "reason": "one short sentence, German"}`

Then reply with only the answer file path and one line per place `label → verdict (candidate)`.
"""

GENERIC = {"see", "weiher", "wald", "wiese", "moos", "moor", "bach", "fluss", "teich", "garten", "park", "damm", "forst", "insel",
           "berg", "tal", "au", "feld", "acker", "straße", "strasse", "ufer", "brücke", "bahnhof", "friedhof", "allee", "kanal",
           "schloss", "kirche", "dorf", "stadt", "hof", "wirtschaft", "haus", "sammlung", "museum", "akademie", "wohnung", "zimmer"}


def dist_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def nominatim(q: str, cache: Cache, live: bool, limit: int = 4) -> list[dict]:
    hit = cache.get(q)
    if hit is None:
        if not live:
            return []
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": q, "format": "jsonv2", "limit": limit, "extratags": 1, "accept-language": "de", "namedetails": 1})
        try:
            res = get_json(url, retries=2, timeout=40)
        except RuntimeError as exc:
            print("nominatim failed", q, exc)
            return []
        hit = [{"osm_type": r.get("osm_type"), "osm_id": r.get("osm_id"), "lat": r.get("lat"), "lon": r.get("lon"),
                "category": r.get("category"), "type": r.get("type"), "place_rank": r.get("place_rank"), "importance": r.get("importance"),
                "name": r.get("name"), "display_name": r.get("display_name"), "addresstype": r.get("addresstype"),
                "wikidata": (r.get("extratags") or {}).get("wikidata", ""), "name_de": (r.get("namedetails") or {}).get("name:de", "")}
               for r in res]
        cache.put(q, hit)
        time.sleep(1.1)
    return hit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("place_link_review")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nominatim-cache", required=True, help="the linking stage's nominatim_cache.json (label -> results)")
    ap.add_argument("--min-mentions", type=int, default=3)
    ap.add_argument("--max-mentions", type=int, default=0, help="only places with at most this many mentions (0 = no limit)")
    ap.add_argument("--known", nargs="*", default=None, help="machine_review.json / place_readings.json of earlier rounds")
    ap.add_argument("--per-batch", type=int, default=25)
    ap.add_argument("--no-live", action="store_true", help="never query Nominatim (contextual candidates only from the cache)")
    ap.add_argument("--max-live", type=int, default=1500)
    args = ap.parse_args()
    P = load_payload(args.payload)
    root = Path(args.out).resolve()
    PL, E = P["place"], P["E"]
    base = read_json(args.nominatim_cache, {}) or {}
    ctx_cache = Cache(root / "places" / "nominatim_context_cache.json")
    glink = {}
    with open(args.place_link_review, encoding="utf-8", newline="") as h:
        for r in csv.DictReader(h):
            glink[r["place_name"].lower()] = r

    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(PL["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(PL["men"]):
        men_of[m[0]].append(mi)
    n_of = {ei: sum(PL["forms"][fi][1] for fi in fis) for ei, fis in forms_of.items()}
    # entry header place per entry (payload E[6] = label; find the entity by label among the entry's Kopfzeile mentions)
    header = {}
    for mi, m in enumerate(PL["men"]):
        if m[5] == "Kopfzeile":
            header.setdefault(m[1], PL["forms"][m[0]][2])
    selected = [ei for ei in forms_of if n_of[ei] >= args.min_mentions
                and (not args.max_mentions or n_of[ei] <= args.max_mentions)]
    if args.known:
        known = known_verdicts(args.known)["place"]
        before = len(selected)
        selected = [ei for ei in selected
                    if PL["ent"][ei][0].lower() not in known
                    and not all(PL["forms"][fi][0].lower() in known for fi in forms_of[ei])]
        print(f"places: {before - len(selected)} judged in earlier rounds, {len(selected)} to check")
    selected.sort(key=lambda ei: (PL["ent"][ei][1] is None, -n_of[ei]))
    print(f"places selected: {len(selected)} (located {sum(1 for ei in selected if PL['ent'][ei][1] is not None)})")

    recs, live_used = [], 0
    for ei in selected:
        ent = PL["ent"][ei]
        names = sorted(((PL["forms"][fi][0], PL["forms"][fi][1]) for fi in forms_of[ei]), key=lambda x: -x[1])
        lr = glink.get(ent[0].lower(), {})
        pt = (ent[1], ent[2]) if ent[1] is not None else None
        roles, anchors, passages, seen = collections.Counter(), collections.Counter(), [], set()
        for fi in forms_of[ei]:
            for mi in men_of[fi]:
                m = PL["men"][mi]
                roles[m[5] or "?"] += 1
                h = header.get(m[1])
                if h is not None and h != ei:
                    anchors[h] += 1
                e = E[m[1]]
                if e[0] not in seen and len(passages) < 4:
                    seen.add(e[0])
                    passages.append({"entry": e[0], "date": e[2], "role": m[5], "text": context(e[7], m[2], m[3], 120)})
        anc = []
        for h, n in anchors.most_common(4):
            a = PL["ent"][h]
            anc.append({"place": a[0], "entries": n, "lat": a[1], "lon": a[2],
                        "km_from_graph_point": round(dist_km((a[1], a[2]), pt), 1) if pt and a[1] is not None else None})
        main_anchor = next((a for a in anc if a["lat"] is not None), None)
        apt = (main_anchor["lat"], main_anchor["lon"]) if main_anchor else None
        cands, cid = [], 0
        seen_osm = set()

        def add(res, query):
            nonlocal cid
            for r in res[:4]:
                k = (r.get("osm_type"), r.get("osm_id"))
                if k in seen_osm or not r.get("lat"):
                    continue
                seen_osm.add(k)
                cid += 1
                la, lo = float(r["lat"]), float(r["lon"])
                cands.append({"id": f"c{cid}", "query": query, "name": r.get("name_de") or r.get("name"), "display_name": r.get("display_name"),
                              "type": f"{r.get('category', '')}/{r.get('type', '')}", "lat": round(la, 5), "lon": round(lo, 5),
                              "km_from_main_anchor": round(dist_km((la, lo), apt), 1) if apt else None, "wikidata": r.get("wikidata", ""),
                              "osm": f"{r.get('osm_type', '')}/{r.get('osm_id', '')}"})
        add(base.get(ent[0], []) or [], ent[0])
        for nm, _ in names[1:3]:
            if nm in base and nm != ent[0]:
                add(base.get(nm) or [], nm)
        if main_anchor and ent[0].lower() not in GENERIC:
            q = f"{ent[0]}, {main_anchor['place']}"
            live = not args.no_live and live_used < args.max_live
            before = ctx_cache.get(q) is not None
            res = nominatim(q, ctx_cache, live)
            if not before and res is not None and live:
                live_used += 1
            add(res or [], q)
        recs.append({"entity": ei, "label": ent[0], "names": [{"name": n, "n": c} for n, c in names], "n_mentions": n_of[ei],
                     "roles": dict(roles.most_common()), "kind": ent[6] or None,
                     "graph": {"lat": ent[1], "lon": ent[2], "uncertainty_m": ent[3] or None, "geonames_id": ent[4] or None,
                               "geonames_name": lr.get("geonames_name") or None, "feature": lr.get("feature") or None,
                               "country": lr.get("country") or None, "admin1": lr.get("admin1") or None, "wikidata": ent[5] or None,
                               "source": lr.get("source") or ent[7] or None, "linking_note": lr.get("note") or None,
                               "linking_status": lr.get("status") or None} if pt else None,
                     "review_suggestion": ({"lat": lr.get("lat"), "lon": lr.get("lon"), "geonames_id": lr.get("geonames_id"),
                                            "geonames_name": lr.get("geonames_name"), "country": lr.get("country"), "note": lr.get("note")}
                                           if not pt and lr.get("lat") else None),
                     "anchors": anc, "passages": passages, "candidates": cands})
        if len(recs) % 100 == 0:
            print(len(recs), "records; live queries", live_used)
            ctx_cache.flush()
    ctx_cache.flush()
    bdir = root / "places" / "batches"
    bdir.mkdir(parents=True, exist_ok=True)
    (root / "places" / "answers").mkdir(parents=True, exist_ok=True)
    for i in range(0, len(recs), args.per_batch):
        write_json(bdir / f"batch_{i // args.per_batch + 1:03d}.json", recs[i:i + args.per_batch])
    instructions(root / "places" / "INSTRUCTIONS.md", INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"places: {len(recs)} records in {(len(recs) + args.per_batch - 1) // args.per_batch} batches; live Nominatim queries {live_used}")


if __name__ == "__main__":
    main()
