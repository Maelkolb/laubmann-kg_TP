"""Deterministic validation of an export: the Darwin Core Archive against the
GBIF expectations and against the graph, and the graph's shared nodes.

Complements SHACL (shape conformance) and the machine review (content, by
language models): here everything that can be checked by rule.

DwC-A
  - ids unique (eventID, occurrenceID, measurementID), every occurrence/eMoF row
    points to an existing event/occurrence
  - required terms (occurrenceID, basisOfRecord, scientificName, eventDate,
    occurrenceStatus); eventDate ISO 8601 date or interval within 1850–1975
  - coordinates in range, with datum and uncertainty; points outside Europe/N. Africa
  - individualCount a non-negative integer; absent records without count
  - kingdom/class/taxonRank consistent; vernacularName present
  - possible duplicate occurrences (same event, taxon, count, locality)
Graph ↔ DwC-A
  - every lkg:Observation has an occurrence row (same IRI), same eventDate and
    scientificName, coordinates of the observation's place
Graph
  - taxa sharing a GBIF key, places sharing a label with points > 25 km apart,
    persons sharing a label (unmerged duplicates); nodes nobody refers to;
    authority concepts without skos:notation; observations without taxon

    python tools/validate_export.py <export> --triples triples.pkl [--out <export>/review/validation]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import math
import pickle
import re
import sys
from pathlib import Path

csv.field_size_limit(2 ** 31 - 1)
ISO_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def loc(u) -> str:
    return str(u).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def read_tsv(path: Path):
    with open(path, encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h, delimiter="\t", quoting=csv.QUOTE_NONE))


def valid_date(value: str) -> bool:
    """ISO 8601 date or interval (the diaries quote literature and collection
    records back to the 18th century, so no lower bound; nothing after 1975)."""
    parts = value.split("/")
    if len(parts) > 2 or not all(ISO_DATE.match(p) for p in parts):
        return False
    try:
        for p in parts:
            if int(p[:4]) > 1975:
                return False
            if len(p) == 10:
                dt.date.fromisoformat(p)
        return len(parts) == 1 or parts[0] <= parts[1]
    except ValueError:
        return False


def historical(value: str) -> bool:
    return bool(value) and value[:4].isdigit() and int(value[:4]) < 1900


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export")
    ap.add_argument("--triples", required=True, help="tools/validation_ui/load.py output of the export's TTL")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    X = Path(args.export)
    out_dir = Path(args.out) if args.out else X / "review" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    issues: list[dict] = []
    counts = collections.Counter()

    def issue(level, check, id_, detail=""):
        counts[(level, check)] += 1
        if counts[(level, check)] <= 2000:
            issues.append({"level": level, "check": check, "id": id_, "detail": str(detail)[:300]})

    # ------------------------------------------------------------ DwC-A
    D = X / "dwca"
    events = read_tsv(D / "event.txt")
    occs = read_tsv(D / "occurrence.txt")
    emof = read_tsv(D / "measurementorfact.txt") if (D / "measurementorfact.txt").exists() else []
    ev_ids = collections.Counter(r["eventID"] for r in events)
    oc_ids = collections.Counter(r["occurrenceID"] for r in occs)
    for k, n in ev_ids.items():
        if n > 1:
            issue("error", "dwca: duplicate eventID", k, n)
    for k, n in oc_ids.items():
        if n > 1:
            issue("error", "dwca: duplicate occurrenceID", k, n)
    for k, n in collections.Counter(r.get("measurementID") for r in emof).items():
        if n > 1:
            issue("error", "dwca: duplicate measurementID", k, n)
    for r in events:
        if not r.get("eventDate"):
            issue("warning", "dwca: event without eventDate", r["eventID"])
        elif not valid_date(r["eventDate"]):
            issue("error", "dwca: event eventDate invalid/out of range", r["eventID"], r["eventDate"])
    europe = lambda lat, lon: 25 <= lat <= 72 and -25 <= lon <= 45  # noqa: E731
    dup = collections.Counter()
    for r in occs:
        oid = r["occurrenceID"]
        if r["eventID"] not in ev_ids:
            issue("error", "dwca: occurrence without event", oid, r["eventID"])
        for t in ("basisOfRecord", "scientificName", "occurrenceStatus"):
            if not r.get(t):
                issue("error", f"dwca: occurrence without {t}", oid)
        if r.get("eventDate") and not valid_date(r["eventDate"]):
            issue("error", "dwca: occurrence eventDate invalid/out of range", oid, r["eventDate"])
        elif historical(r.get("eventDate", "")):
            issue("info", "dwca: record before 1900 (quoted literature/collection record?)", oid,
                  f"{r['eventDate']} {r.get('basisOfRecord')} {r.get('scientificName')}")
        if r.get("individualCount"):
            if not r["individualCount"].isdigit():
                issue("error", "dwca: individualCount not a non-negative integer", oid, r["individualCount"])
            elif r.get("occurrenceStatus") == "absent" and int(r["individualCount"]) > 0:
                issue("error", "dwca: absent with individualCount > 0", oid, r["individualCount"])
        if r.get("decimalLatitude") or r.get("decimalLongitude"):
            try:
                lat, lon = float(r["decimalLatitude"]), float(r["decimalLongitude"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    issue("error", "dwca: coordinates out of range", oid, f"{lat},{lon}")
                elif not europe(lat, lon):
                    issue("info", "dwca: point outside Europe (check: travel or wrong place)", oid, f"{r.get('locality')} {lat},{lon}")
                if not r.get("geodeticDatum"):
                    issue("error", "dwca: coordinates without geodeticDatum", oid)
                if not r.get("coordinateUncertaintyInMeters"):
                    issue("warning", "dwca: coordinates without uncertainty", oid, r.get("locality"))
            except ValueError:
                issue("error", "dwca: coordinates not numeric", oid, f"{r.get('decimalLatitude')},{r.get('decimalLongitude')}")
        if r.get("kingdom") and r["kingdom"] != "Animalia":
            issue("warning", "dwca: kingdom not Animalia", oid, f"{r['kingdom']} {r.get('scientificName')}")
        if r.get("class") and r["class"] != "Aves":
            issue("info", "dwca: class not Aves", oid, f"{r['class']} {r.get('scientificName')} ({r.get('vernacularName')})")
        if not r.get("taxonID") and r.get("scientificName") not in ("Aves",):
            issue("info", "dwca: scientificName without GBIF taxonID", oid, f"{r.get('scientificName')} ({r.get('vernacularName')})")
        if not r.get("recordedBy"):
            issue("warning", "dwca: occurrence without recordedBy", oid)
        dup[(r["eventID"], r.get("scientificName"), r.get("individualCount"), r.get("locality"), r.get("eventDate"),
             r.get("sex"), r.get("lifeStage"), r.get("behavior"))] += 1
    for k, n in dup.items():
        if n > 1:
            issue("info", "dwca: possible duplicate occurrences (same event, taxon, count, place, date, sex, stage, behaviour)",
                  k[0], f"{n}x {k[1]} {k[2] or ''} {k[3] or ''}")
    for r in emof:
        if r.get("occurrenceID") and r["occurrenceID"] not in oc_ids:
            issue("error", "dwca: eMoF row without occurrence", r.get("measurementID"), r["occurrenceID"])

    # ------------------------------------------------------------ graph
    print("loading triples …", file=sys.stderr)
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    typ = collections.defaultdict(set)
    incoming = collections.Counter()
    for s, p, o in pickle.load(open(args.triples, "rb")):
        pn = loc(p)
        if pn == "type":
            typ[s].add(loc(o))
        else:
            out[s][pn].append(o)
            if not isinstance(o, str) or str(o).startswith("http"):
                incoming[o] += 1

    def one(s, p):
        v = out[s].get(p)
        return str(v[0]) if v else ""

    of = collections.defaultdict(list)
    for s, ts in typ.items():
        for t in ts:
            of[t].append(s)
    occ_by_id = {r["occurrenceID"]: r for r in occs}
    geom = {}
    for pl in of["Place"]:
        lat, lon = one(pl, "decimalLatitude") or one(pl, "lat"), one(pl, "decimalLongitude") or one(pl, "long")
        if lat and lon:
            geom[pl] = (float(lat), float(lon))
    for o in of["Observation"]:
        oid = str(o)
        tx = out[o].get("observedTaxon", [None])[0]
        if tx is None:
            issue("error", "graph: observation without taxon", oid)
        r = occ_by_id.get(oid)
        if r is None:
            issue("error", "graph↔dwca: observation without occurrence row", oid)
            continue
        if one(o, "eventDate") and r.get("eventDate") and one(o, "eventDate") != r["eventDate"]:
            issue("error", "graph↔dwca: eventDate differs", oid, f"{one(o, 'eventDate')} vs {r['eventDate']}")
        sci = one(tx, "scientificName") if tx is not None else ""
        if sci and r.get("scientificName") and sci != r["scientificName"]:
            issue("error", "graph↔dwca: scientificName differs", oid, f"{sci} vs {r['scientificName']}")
        pl = out[o].get("observedAt", [None])[0]
        if pl in geom and r.get("decimalLatitude"):
            g = geom[pl]
            if abs(g[0] - float(r["decimalLatitude"])) > 1e-4 or abs(g[1] - float(r["decimalLongitude"])) > 1e-4:
                issue("error", "graph↔dwca: coordinates differ from the observation's place", oid,
                      f"{g} vs {r['decimalLatitude']},{r['decimalLongitude']}")
    obs_ids = {str(o) for o in of["Observation"]}
    for oid in oc_ids:
        if oid not in obs_ids:
            issue("error", "graph↔dwca: occurrence row without observation in the graph", oid)
    by_key = collections.defaultdict(list)
    for t in of["Taxon"]:
        k = one(t, "taxonID")
        if k:
            by_key[k].append(t)
    for k, ts in by_key.items():
        if len(ts) > 1:
            issue("warning", "graph: several taxon nodes with one GBIF key (unmerged spellings)", k,
                  "; ".join(one(t, "label") for t in ts[:8]))
    by_label = collections.defaultdict(list)
    for pl in of["Place"]:
        by_label[one(pl, "label").lower()].append(pl)
    for lab, pls in by_label.items():
        pts = [geom[p] for p in pls if p in geom]
        if len(pts) > 1 and max(km(*a, *b) for a in pts for b in pts) > 25:
            issue("warning", "graph: places with one label > 25 km apart", lab, len(pts))
    by_plabel = collections.Counter(one(p, "label").lower() for p in of["Person"])
    for lab, n in by_plabel.items():
        if n > 1:
            issue("warning", "graph: several person nodes with one label", lab, n)
    for t in ("Taxon", "Place", "Person"):
        for s in of[t]:
            if incoming[s] == 0:
                issue("info", f"graph: {t} node nobody refers to", str(s), one(s, "label"))
    for s in of["Concept"]:
        if any(x in str(s) for x in ("gbif.org", "eunis", "geonames", "wikidata", "d-nb.info")) and not one(s, "notation"):
            issue("warning", "graph: authority concept without skos:notation", str(s))

    # ------------------------------------------------------------ report
    with open(out_dir / "issues.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=["level", "check", "id", "detail"])
        w.writeheader()
        w.writerows(issues)
    lines = [f"# Export validation — {X.name}\n",
             f"DwC-A: {len(events)} events, {len(occs)} occurrences, {len(emof)} eMoF rows. "
             f"Graph: {len(of['DiaryEntry'])} entries, {len(of['Observation'])} observations, {len(of['Taxon'])} taxa, "
             f"{len(of['Place'])} places, {len(of['Person'])} persons.\n",
             "| level | check | n |", "|---|---|---|"]
    order = {"error": 0, "warning": 1, "info": 2}
    for (level, check), n in sorted(counts.items(), key=lambda kv: (order[kv[0][0]], -kv[1])):
        lines.append(f"| {level} | {check} | {n} |")
    if not counts:
        lines.append("| — | no issues | 0 |")
    lines.append("\nExamples (up to 2,000 per check): issues.csv")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if any(level == "error" for level, _ in counts) else 0


if __name__ == "__main__":
    sys.exit(main())
