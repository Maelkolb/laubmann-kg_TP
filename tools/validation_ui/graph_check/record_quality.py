"""Estimated quality of every record, from two scan checks and the blind audit.

Two machine checks read every record against the page scans: the record check (record_check.py, Gemini 3.8 Flash,
shown the graph's values) and the blind check (blind_check.py, Gemini 3.7 Flash, not shown them). For every field
of a record their verdicts give a status:

    ok     both checks accept the graph's value
    c1     only the record check doubts it
    c2     only the blind check reads something else
    both   both doubt it
    one    only one check judged the field, and it accepts it

The audit of 3 October (evaluation/corpus_tiers/audit.csv: 734 records, checked blind by Opus subagents against
the scans, weighted to the strata they were drawn from) says how often a field in each status is wrong. The rate
of a status is measured per field and per risk group (the record's old corpus tier: 0 outside the core, 1 core,
2 strict core and above), each shrunk toward the coarser rate when few audited records fall into it. A record's
estimated error is 1 - prod(1 - p_field) over its fields; coordinates are estimated apart (reviewed place link,
gazetteer match only, flagged by the record check).

    python tools/validation_ui/graph_check/record_quality.py --dwca <export>/dwca --blind <work>/blind_checks.csv \\
        --record-check <record_check>/record_checks.csv --tiers record_tiers.csv \\
        --audited-dwca data/exports/kg_exports_2026-10-01_checked/dwca \\
        --before-dwca data/exports/kg_exports_2026-10-04_text/dwca --out data/cache/graph_check/quality

Writes ``record_quality.csv`` (one row per occurrence) and ``quality_summary.json`` (rates per status, levels,
cross-validated calibration against the audit, expected number of wrong records).
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "evaluation" / "corpus_tiers"))
from evaluate_tiers import attribution, rejudge  # noqa: E402

FIELDS = ["exists", "species", "count", "date", "place", "observer", "record_type"]
OCCURRENCE = ["exists", "species", "count", "date"]
AUDIT_FIELD = {"species": "species", "count": "count", "date": "date", "place": "locality", "observer": "observer",
               "record_type": "record_type"}
CHECK1_FIELD = {"species": {"species"}, "count": {"count"}, "date": {"date"}, "place": {"locality"},
                "observer": {"observer"}, "record_type": {"record_type"}, "status": {"status"}}
DWC_FIELD = {"species": "scientificName", "count": "individualCount", "date": "eventDate", "place": "locality",
             "observer": "recordedBy", "record_type": "recordType"}
LEVELS = [(0.10, 1), (0.25, 2), (0.50, 3), (1.01, 4)]     # estimated error below the bound -> level
PRIOR = 4.0                                                # audited records' worth of shrinkage toward the coarser rate


def read_csv(path, delimiter=","):
    with open(path, encoding="utf-8", newline="") as h:
        if delimiter == "\t":
            return list(csv.DictReader(h, delimiter="\t", quoting=csv.QUOTE_NONE))
        return list(csv.DictReader(h))


def dwca_records(dwca: Path) -> dict:
    occ = {r["occurrenceID"]: r for r in read_csv(dwca / "occurrence.txt", "\t")}
    for r in read_csv(dwca / "measurementorfact.txt", "\t"):
        if r["measurementType"] == "recordType" and r["occurrenceID"] in occ:
            occ[r["occurrenceID"]]["recordType"] = r["measurementValue"]
    for r in occ.values():
        r.setdefault("recordType", "field-observation")
    return occ


def obs_index(iri: str, entry_uid: str, written: str) -> int:
    want = iri.rsplit("_", 1)[-1]
    for i in range(1000):
        if hashlib.sha1(f"{entry_uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == want:
            return i
    return -1


def level(p: float) -> int:
    p = round(p, 3)                                        # the precision the pages see
    return next(lv for bound, lv in LEVELS if p < bound)


def risk_group(tier: int) -> str:
    return "t0" if tier <= 0 else "t1" if tier == 1 else "t2"


def coords_status(o: dict, c1_fields: set) -> str:
    src = o.get("georeferenceSources") or ""
    if not o.get("decimalLatitude"):
        return "none"
    base = "gaz" if "name match" in src else "rev"
    return base + ("-c1" if "georef" in c1_fields else "")


class Rates:
    """Weighted error rate per (field, status) and per (field, status, risk group), shrunk toward the coarser rate."""

    def __init__(self, rows: list[dict]) -> None:
        self.n = collections.defaultdict(float)
        self.k = collections.defaultdict(float)
        self.cnt = collections.Counter()
        for r in rows:
            for f, (status, wrong) in r["label"].items():
                for key in ((f,), (f, status), (f, status, r["risk"])):
                    self.n[key] += r["w"]
                    self.k[key] += r["w"] * wrong
                    self.cnt[key] += 1

    def rate(self, key: tuple, prior: float) -> float:
        n, c = self.n.get(key, 0.0), self.cnt.get(key, 0)
        if not c:
            return prior
        mean_w = n / c
        return (self.k[key] + PRIOR * mean_w * prior) / (n + PRIOR * mean_w)

    def p(self, f: str, status: str, risk: str) -> float:
        base = self.rate((f,), 0.05)
        cell = self.rate((f, status), base)
        return self.rate((f, status, risk), cell)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dwca", required=True)
    ap.add_argument("--blind", required=True, help="blind_checks.csv (blind_compare.py)")
    ap.add_argument("--record-check", required=True, help="record_checks.csv of the record check on this export")
    ap.add_argument("--tiers", required=True, help="record_tiers.csv of this export (risk group)")
    ap.add_argument("--audit", default=str(REPO / "evaluation" / "corpus_tiers" / "audit.csv"))
    ap.add_argument("--audited-dwca", required=True, help="dwca/ of the export the audit judged")
    ap.add_argument("--before-dwca", required=True, help="dwca/ before the attribution fix (re-judges changed attributions)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    occ = dwca_records(Path(args.dwca))
    tiers = {r["occurrenceID"]: r for r in read_csv(args.tiers)}
    blind = {r["occurrenceID"]: r for r in read_csv(args.blind)}
    c1 = {(r["entry_id"], int(r["obs_index"])): r for r in read_csv(args.record_check)}

    records = {}
    for oid, o in occ.items():
        t = tiers.get(oid, {})
        uid = o["eventID"].rsplit("entry_", 1)[-1]
        b = blind.get(oid)
        idx = int(b["index"]) if b else obs_index(oid, uid, t.get("written_name", ""))
        chk = c1.get((t.get("entry_id", ""), idx), {})
        v1 = chk.get("verdict", "unchecked")
        f1 = set((chk.get("fields") or "").split(";")) - {""} if v1 == "wrong" else set()
        status = {}
        for f in FIELDS:
            d1 = (v1 == "spurious") if f == "exists" else bool(CHECK1_FIELD[f] & f1)
            r2 = b.get(f, "na") if b else "na"
            if f == "species" or f == "count":
                d1 = d1 or (v1 == "spurious")
            if r2 == "na":
                status[f] = "c1" if d1 else ("one" if v1 in ("ok", "wrong") else "na")
            else:
                d2 = r2 == "disagree"
                status[f] = "both" if d1 and d2 else "c1" if d1 else "c2" if d2 else "ok"
        records[oid] = {"o": o, "entry_id": t.get("entry_id", ""), "index": idx, "tier": int(t.get("tier", 0) or 0),
                        "status": status, "coords": coords_status(o, f1), "blind": b or {}}

    # ------------------------------------------------------------ audit labels
    audited = dwca_records(Path(args.audited_dwca))
    after, before = attribution(args.dwca), attribution(args.before_dwca)
    rows = []
    for a in read_csv(args.audit):
        oid = a["occurrenceID"]
        if a["verdict"] not in ("ok", "wrong", "spurious") or oid not in records or oid not in audited:
            continue
        rec = records[oid]
        wrong = set(a["wrong_fields"].split(";")) - {""}
        if oid in before and oid in after and before[oid] != after[oid] and not rejudge(a, before[oid], after[oid]):
            wrong -= {"observer", "record_type"}
        label = {}
        for f in FIELDS:
            if f == "exists":
                label[f] = (rec["status"][f], 1 if a["verdict"] == "spurious" else 0)
                continue
            if f not in ("observer", "record_type") and audited[oid].get(DWC_FIELD[f]) != rec["o"].get(DWC_FIELD[f]):
                continue
            label[f] = (rec["status"][f], 1 if AUDIT_FIELD[f] in wrong else 0)
        if a["georef"] in ("right", "wrong") and audited[oid].get("decimalLatitude") == rec["o"].get("decimalLatitude"):
            label["coords"] = (rec["coords"], 1 if a["georef"] == "wrong" else 0)
        any_wrong = 1 if (wrong - {"other"}) or a["verdict"] == "spurious" else 0
        rows.append({"oid": oid, "entry": a["entry_id"], "w": float(a["weight"]), "risk": risk_group(rec["tier"]),
                     "label": label, "any": any_wrong, "occ": 1 if (wrong & {"species", "count", "date", "status"}) or a["verdict"] == "spurious" else 0})

    def predict(rates: Rates, rec: dict) -> dict:
        risk = risk_group(rec["tier"])
        p = {f: rates.p(f, rec["status"][f], risk) for f in FIELDS}
        p["coords"] = None if rec["coords"] == "none" else rates.p("coords", rec["coords"], risk)
        prod = lambda fs: 1 - math.prod(1 - p[f] for f in fs)   # noqa: E731
        p["occ"], p["any"] = prod(OCCURRENCE), prod(FIELDS)
        return p

    # ------------------------------------------------------------ cross-validated calibration on the audit
    entries = sorted({r["entry"] for r in rows})
    random.Random(20261006).shuffle(entries)
    fold_of = {e: i % args.folds for i, e in enumerate(entries)}
    cv = []
    for k in range(args.folds):
        rates = Rates([r for r in rows if fold_of[r["entry"]] != k])
        for r in rows:
            if fold_of[r["entry"]] == k:
                p = predict(rates, records[r["oid"]])
                cv.append((r, p))

    def wmean(pairs, fn):
        w = sum(r["w"] for r, _ in pairs)
        return sum(r["w"] * fn(r, p) for r, p in pairs) / w if w else float("nan")

    calib = {"records": len(cv),
             "any: predicted": round(100 * wmean(cv, lambda r, p: p["any"]), 1), "any: observed": round(100 * wmean(cv, lambda r, p: r["any"]), 1),
             "occurrence: predicted": round(100 * wmean(cv, lambda r, p: p["occ"]), 1), "occurrence: observed": round(100 * wmean(cv, lambda r, p: r["occ"]), 1),
             "by level": {}}
    for lv in (1, 2, 3, 4):
        part = [(r, p) for r, p in cv if level(p["any"]) == lv]
        if part:
            calib["by level"][lv] = {"audited": len(part), "predicted any %": round(100 * wmean(part, lambda r, p: p["any"]), 1),
                                     "observed any %": round(100 * wmean(part, lambda r, p: r["any"]), 1),
                                     "observed occurrence %": round(100 * wmean(part, lambda r, p: r["occ"]), 1)}
    pairs = sorted(cv, key=lambda x: x[1]["any"])
    concordant = total = 0.0
    bad = [(r, p) for r, p in pairs if r["any"]]
    good = [(r, p) for r, p in pairs if not r["any"]]
    for rb, pb in bad:
        for rg, pg in good:
            ww = rb["w"] * rg["w"]
            total += ww
            concordant += ww * (1.0 if pb["any"] > pg["any"] else 0.5 if pb["any"] == pg["any"] else 0.0)
    calib["AUC any (weighted)"] = round(concordant / total, 3) if total else None

    # ------------------------------------------------------------ all records
    rates = Rates(rows)
    table = {}
    for f in FIELDS + ["coords"]:
        statuses = sorted({k[1] for k in rates.cnt if k[0] == f and len(k) == 2})
        table[f] = {s: {"audited": rates.cnt[(f, s)], "error %": round(100 * rates.rate((f, s), rates.rate((f,), 0.05)), 1)}
                    for s in statuses}
    out_rows = []
    totals = collections.Counter()
    status_counts = {f: collections.Counter() for f in FIELDS + ["coords"]}
    for oid, rec in records.items():
        p = predict(rates, rec)
        lv = level(p["any"])
        totals["records"] += 1
        totals[f"level {lv}"] += 1
        totals["expected wrong (any)"] += p["any"]
        totals["expected wrong (occurrence)"] += p["occ"]
        if p["coords"] is not None:
            totals["with coordinates"] += 1
            totals["expected wrong coordinates"] += p["coords"]
        for f in FIELDS:
            status_counts[f][rec["status"][f]] += 1
        status_counts["coords"][rec["coords"]] += 1
        row = {"occurrenceID": oid, "entry_id": rec["entry_id"], "obs_index": rec["index"], "level": lv,
               "p_any": f"{p['any']:.3f}", "p_occurrence": f"{p['occ']:.3f}", "p_coords": "" if p["coords"] is None else f"{p['coords']:.3f}"}
        for f in FIELDS:
            row[f"p_{f}"] = f"{p[f]:.3f}"
            row[f"s_{f}"] = rec["status"][f]
            if rec["status"][f] in ("c2", "both"):
                row[f"check_{f}"] = rec["blind"].get(f + "_check", "")
        row["s_coords"] = rec["coords"]
        out_rows.append(row)
    cols = ["occurrenceID", "entry_id", "obs_index", "level", "p_any", "p_occurrence", "p_coords"] + \
           [f"p_{f}" for f in FIELDS] + [f"s_{f}" for f in FIELDS] + ["s_coords"] + [f"check_{f}" for f in FIELDS if f != "exists"]
    with open(out / "record_quality.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    n = totals["records"]
    summary = {"records": n,
               "levels": {lv: {"records": totals[f"level {lv}"], "share %": round(100 * totals[f"level {lv}"] / n, 1)} for lv in (1, 2, 3, 4)},
               "level bounds (estimated error of any field)": {1: "< 10 %", 2: "10-25 %", 3: "25-50 %", 4: ">= 50 %"},
               "expected wrong records (any field)": round(totals["expected wrong (any)"]),
               "expected share wrong (any field) %": round(100 * totals["expected wrong (any)"] / n, 1),
               "expected wrong records (occurrence)": round(totals["expected wrong (occurrence)"]),
               "expected share wrong (occurrence) %": round(100 * totals["expected wrong (occurrence)"] / n, 1),
               "expected share wrong coordinates %": round(100 * totals["expected wrong coordinates"] / max(1, totals["with coordinates"]), 1),
               "status counts": {f: dict(c) for f, c in status_counts.items()},
               "audited error % per status": table,
               "cross-validated calibration": calib,
               "audit records used": len(rows)}
    (out / "quality_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
