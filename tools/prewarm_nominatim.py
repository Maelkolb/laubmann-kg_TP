"""Pre-warm the Nominatim cache used by linking/places.py.

    python tools/prewarm_nominatim.py <labels.json|graph.json|ttl> --cache <nominatim_cache.json> [--min-uses 1] [--limit N]

Reads the distinct place labels (from the explorer graph.json, a JSON list of
[label, uses] pairs, or the Turtle export), keeps the geocodable ones (see
linking.places.geocodable), most-used first, and queries Nominatim once per
label (1 request / 1.1 s, User-Agent with contact, viewbox biased to Bavaria
but not bounded — the diarist travelled). Results are cached as
{label: [hits]} and flushed every 25 labels, so the script can be stopped and
resumed at any time. The pipeline never calls Nominatim live unless
``linking.places.nominatim.live`` is set — it reads this cache.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laubmann_kg.linking.places import NominatimClient, geocodable  # noqa: E402


def labels_from(path: Path) -> list[tuple[str, int]]:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "places" in data:
            return [(p["name"], int(p.get("n") or 0)) for p in data["places"] if p.get("name")]
        return [(x[0], int(x[1])) for x in data]
    if path.suffix == ".ttl":
        from rdflib import Graph, Namespace, RDF, RDFS
        LKG = Namespace("https://w3id.org/laubmann-kg/ontology#")
        g = Graph(); g.parse(path, format="turtle")
        from collections import Counter
        use = Counter(o for o in g.objects(None, LKG.observedAt))
        return [(str(g.value(p, RDFS.label)), use.get(p, 0)) for p in g.subjects(RDF.type, LKG.Place)]
    raise SystemExit(f"unknown input {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--min-uses", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--email", default="totomail.tp@gmail.com")
    args = ap.parse_args()
    labels = [(l, n) for l, n in labels_from(Path(args.source)) if n >= args.min_uses and geocodable(l)]
    labels.sort(key=lambda x: -x[1])
    seen = set(); todo = []
    for l, n in labels:
        if l not in seen:
            seen.add(l); todo.append(l)
    if args.limit:
        todo = todo[:args.limit]
    client = NominatimClient(Path(args.cache), email=args.email, live=True)
    pending = [l for l in todo if l not in client.cache]
    print(f"{len(todo)} labels, {len(pending)} not cached yet (~{len(pending) * 1.1 / 60:.0f} min)", flush=True)
    t0 = time.time()
    for i, label in enumerate(pending, 1):
        client.search(label)
        if i % 25 == 0:
            client.flush()
            print(f"  {i}/{len(pending)} ({time.time() - t0:.0f}s)", flush=True)
    client.flush()
    print("done", len(client.cache), "cached labels")


if __name__ == "__main__":
    main()
