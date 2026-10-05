"""Compare the blind second check (blind_check.py) with the graph, field by field.

For every record the check answered: does its own reading agree with what the graph holds? Fields: exists
(the record is in the entry at all), species, count, status, place, date, observer, record_type. Species agree
when the GBIF backbone gives the check's name and the graph's taxon the same accepted key (or the names are the
same); places when the graph's place of the record is one of the listed places the check accepted for it;
observers when the same persons (by surname, the diarist counted apart) are named.

    python tools/validation_ui/machine_review/blind_compare.py triples.pkl --work <workdir>/blind_check \\
        --dwca <export>/dwca

Writes ``<work>/blind_checks.csv`` (one row per record: ``<field>`` = agree | disagree | na and
``<field>_check`` = the check's value where it disagrees) and ``<work>/blind_entries.csv``.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rdflib import URIRef

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_json, write_json  # noqa: E402
from prepare_entries import GraphView  # noqa: E402

FIELDS = ["exists", "species", "count", "status", "place", "date", "observer", "record_type"]
DIARIST = "laubmann"
TITLES = {"dr", "herr", "hr", "frau", "frl", "prof", "freund", "praeparator", "oberlehrer"}


def fold(s) -> str:
    s = str(s or "").casefold()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h, delimiter="\t", quoting=csv.QUOTE_NONE))


class Gbif:
    """species/match lookups, seeded from the linking cache, new answers kept in the check's own cache."""

    def __init__(self, own: Path, seed: Path) -> None:
        self.path = own
        self.data = read_json(seed, {}) or {}
        self.data.update(read_json(own, {}) or {})

    def match(self, name: str) -> dict:
        key = "match:" + name.strip().lower()
        if key not in self.data:
            url = "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode({"name": name, "class": "Aves"})
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    self.data[key] = json.loads(r.read().decode("utf-8"))
            except Exception:  # noqa: BLE001 - an unreachable API leaves the name unresolved
                return {}
            time.sleep(0.05)
        return self.data[key] or {}

    def keys(self, name: str) -> set[int]:
        m = self.match(name)
        return {k for k in (m.get("usageKey"), m.get("acceptedUsageKey"), m.get("speciesKey") if m.get("rank") in ("SPECIES", "SUBSPECIES") else None) if k}

    def save(self) -> None:
        write_json(self.path, self.data, indent=None)


def canonical(sci: str) -> str:
    words = re.findall(r"[A-Za-z]+", sci or "")
    return " ".join(w.lower() for w in words[:2])


def parse_count(v) -> tuple:
    """'' | (n,) | (lo, hi) from the check's or the graph's count."""
    s = str(v or "").strip().lower()
    m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (int(s),) if s.isdigit() else ()


def count_agrees(check, n, lo, hi) -> bool:
    c, g = parse_count(check), parse_count(n)
    if not c:
        return not g or g == (0,)
    if not g:
        return False
    if len(c) == 2:
        return g[0] == c[0] or (lo, hi) == (str(c[0]), str(c[1]))
    return c[0] == g[0]


def span(d: str) -> tuple[str, str]:
    a, _, b = (d or "").partition("/")
    return a, b or a


def pad(d: str, end: bool) -> str:
    if len(d) == 4:
        return d + ("-12-31" if end else "-01-01")
    if len(d) == 7:
        return d + ("-31" if end else "-01")
    return d


def date_agrees(check: str, graph: str, entry_check: str, entry_graph: str) -> bool | None:
    check = (check or "").strip()
    if not check or not graph:
        return None
    g0, g1 = span(graph)
    if check == "entry":
        want = entry_check or entry_graph
        w0, w1 = span(want)
        return (w0 <= g0 and g1 <= w1) or (g0 <= w0 and w1 <= g1) or (g0 == w0)
    if check == "undated":
        return g0[:7] != g1[:7]
    if re.fullmatch(r"\d{4}(-\d{2})?", check):
        return g0 != g1 and pad(check, False) <= g0 and g1 <= pad(check, True)
    c0, c1 = span(check)
    c0, c1 = pad(c0, False), pad(c1, True)
    return (c0 <= g0 and g1 <= c1) or (g0 <= c0 and c1 <= g1 and g0 != g1)


def people(names: list[str]) -> set[str]:
    out = set()
    for name in names:
        toks = [t for t in re.findall(r"[A-Za-zÄÖÜäöüß]+", name or "") if fold(t) not in TITLES]
        if toks:
            out.add(fold(toks[-1]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("triples")
    ap.add_argument("--work", required=True)
    ap.add_argument("--dwca", required=True)
    ap.add_argument("--gbif-seed", default=str(REPO / "data" / "cache" / "linking" / "gbif_cache.json"))
    args = ap.parse_args()
    work = Path(args.work)
    dwca = Path(args.dwca)

    occ = {r["occurrenceID"]: r for r in read_tsv(dwca / "occurrence.txt")}
    events = {r["eventID"]: r for r in read_tsv(dwca / "event.txt")}
    rtype = {r["occurrenceID"]: r["measurementValue"] for r in read_tsv(dwca / "measurementorfact.txt") if r["measurementType"] == "recordType"}
    print("loading triples …", flush=True)
    G = GraphView(args.triples)
    gbif = Gbif(work / "gbif_cache.json", Path(args.gbif_seed))

    rows, entries = [], []
    stats = collections.Counter()
    for path in sorted((work / "answers").glob("*.json")):
        a = read_json(path)
        ans = a.get("answer") if isinstance(a.get("answer"), dict) else None
        if not ans:
            stats["entries unparseable"] += 1
            continue
        places = [fold(p) for p in a["places"]]
        persons = a["persons"]
        ent = ans.get("entry") if isinstance(ans.get("entry"), dict) else {}
        by_i = {r.get("i"): r for r in ans.get("records") or [] if isinstance(r, dict)}
        entry_date_graph = ""
        first = None
        for rec in a["records"]:
            o = occ.get(rec["iri"])
            if o is None:
                stats["record not in DwC"] += 1
                continue
            first = first or o
            entry_date_graph = events.get(o["eventID"], {}).get("eventDate", "")
            c = by_i.get(rec["index"])
            row = {"occurrenceID": rec["iri"], "entry_id": a["entry_id"], "index": rec["index"], "written": rec["written"]}
            if c is None:
                row.update({f: "na" for f in FIELDS})
                stats["record unanswered"] += 1
                rows.append(row)
                continue
            row["confidence"] = c.get("c", "")
            res, val = {}, {}
            res["exists"] = "agree" if c.get("here", True) is not False else "disagree"
            node = URIRef(rec["iri"])
            tx = G.out[node].get("observedTaxon", [None])[0]
            gsci, grank = G.one(tx, "scientificName"), G.one(tx, "taxonRank")
            gkey = int(o["taxonID"].rsplit("/", 1)[-1]) if o.get("taxonID", "").rsplit("/", 1)[-1].isdigit() else None
            csci = (c.get("sci") or "").strip()
            if not csci:
                res["species"] = "na"
            elif canonical(csci) == canonical(gsci) or fold(c.get("de")) in (fold(o["vernacularName"]), fold(G.label(tx))):
                res["species"] = "agree"
            else:
                res["species"] = "agree" if gkey and gkey in gbif.keys(csci) else "disagree"
            val["species"] = f"{c.get('de') or ''} ({csci})"

            res["count"] = "agree" if count_agrees(c.get("n"), G.one(node, "individualCount"), G.one(node, "individualCountMin"),
                                                    G.one(node, "individualCountMax")) else "disagree"
            val["count"] = c.get("n") or ""
            absent = c.get("absent") is True
            res["status"] = "agree" if absent == (o["occurrenceStatus"] == "absent") else "disagree"
            val["status"] = "absent" if absent else "present"

            chosen = {places[k - 1] for k in c.get("places") or [] if isinstance(k, int) and 0 < k <= len(places)}
            place = G.out[node].get("observedAt", [None])[0]
            graph_places = {fold(G.one(node, "verbatimLocality")), fold(G.label(place) if place is not None else "")} - {""}
            if chosen:
                res["place"] = "agree" if graph_places & chosen else "disagree"
            elif c.get("site"):
                site = set(re.findall(r"[a-z]{4,}", fold(c["site"])))
                res["place"] = "agree" if any(site & set(re.findall(r"[a-z]{4,}", g)) for g in graph_places) else "disagree"
            else:
                res["place"] = "na"
            val["place"] = c.get("site") or "; ".join(a["places"][k - 1] for k in c.get("places") or [] if isinstance(k, int) and 0 < k <= len(places))

            ok = date_agrees(str(c.get("date") or ""), o["eventDate"], str(ent.get("date") or ""), entry_date_graph)
            res["date"] = "na" if ok is None else ("agree" if ok else "disagree")
            val["date"] = str(c.get("date") or "") + (f" (entry {ent.get('date')})" if c.get("date") == "entry" else "")

            names = [persons[k - 1] for k in c.get("obs") or [] if isinstance(k, int) and 0 < k <= len(persons)]
            text = c.get("obs_text") or ""
            unnamed = fold(text) in ("unnamed", "unbekannt", "unknown")
            if text and not unnamed:
                names += re.split(r"\s*[;,]\s*|\s+und\s+", text)
            graph_obs = [x for x in o["recordedBy"].split(" | ") if x]
            want, got = people(names), people(graph_obs)
            if unnamed and not names:
                res["observer"] = "agree" if not got or DIARIST not in got else "disagree"
            elif not want:
                res["observer"] = "na"
            else:
                same_diarist = (DIARIST in want) == (DIARIST in got)
                res["observer"] = "agree" if same_diarist and (want <= got or got <= want) and (want & got) else "disagree"
            val["observer"] = "; ".join(names) or text

            ct = (c.get("type") or "").strip()
            res["record_type"] = "na" if not ct else ("agree" if ct[:8] == rtype.get(rec["iri"], "field-observation")[:8] else "disagree")
            val["record_type"] = ct

            for f in FIELDS:
                row[f] = res.get(f, "na")
                stats[f"{f} {row[f]}"] += 1
                if row[f] == "disagree" and f != "exists":
                    row[f + "_check"] = val.get(f, "")
            rows.append(row)
        if first is not None:
            ev = events.get(first["eventID"], {})
            ep = {fold(a["places"][k - 1]) for k in ent.get("places") or [] if isinstance(k, int) and 0 < k <= len(places)}
            entries.append({"entry_id": a["entry_id"], "date_graph": ev.get("eventDate", ""), "date_check": ent.get("date", ""),
                            "date": "agree" if date_agrees(str(ent.get("date") or ""), ev.get("eventDate", ""), "", "") else "disagree",
                            "place_graph": ev.get("locality", ""), "place_check": "; ".join(a["places"][k - 1] for k in ent.get("places") or []
                                                                                          if isinstance(k, int) and 0 < k <= len(places)) or ent.get("site") or "",
                            "place": "agree" if fold(ev.get("locality")) in ep else ("na" if not ep else "disagree"),
                            "legible": ent.get("legible", "")})
        stats["entries"] += 1
    gbif.save()
    fields = ["occurrenceID", "entry_id", "index", "written", "confidence"] + [x for f in FIELDS for x in (f, f + "_check")]
    with open(work / "blind_checks.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(work / "blind_entries.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(entries[0]) if entries else ["entry_id"])
        w.writeheader()
        w.writerows(entries)
    print(json.dumps(dict(sorted(stats.items())), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
