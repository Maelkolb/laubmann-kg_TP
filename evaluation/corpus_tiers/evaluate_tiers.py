"""Estimated error rates of the four corpora, from the blind scan audit.

    python evaluation/corpus_tiers/evaluate_tiers.py <record_tiers.csv> [--reps 1000]

audit.csv holds 734 records drawn from 29 strata (strata.csv: records per stratum in the export), each
checked against the page scans by a Claude Opus subagent (auditor_instructions.md, answers/). A record's
weight is records in its stratum / records sampled from it. For every corpus (records with tier >= t) the
script prints the weighted share of audited records with an error:

    any        any field wrong, or the record does not exist (spurious)
    occ        species, count, date or status wrong, or spurious
    place      the locality wrong
    attr       observer or record type wrong
    georef     coordinates wrong, among records whose coordinates the auditor could judge

and a 90 % bootstrap interval of `any` (resampling within strata). Records judged `unclear` are left out.
"""
from __future__ import annotations

import argparse
import collections
import csv
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ["full", "core", "strict core", "strict core with coordinates"]


def weighted(rows, key, cond=None):
    rows = [r for r in rows if cond is None or cond(r)]
    w = sum(r["weight"] for r in rows)
    return 100 * sum(r["weight"] * r[key] for r in rows) / w if w else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tiers", help="record_tiers.csv (build_review.py --tiers-csv)")
    ap.add_argument("--audit", default=str(HERE / "audit.csv"))
    ap.add_argument("--reps", type=int, default=1000)
    args = ap.parse_args()

    tier = {}
    size = collections.Counter()
    with open(args.tiers, encoding="utf-8") as h:
        for r in csv.DictReader(h):
            tier[r["occurrenceID"]] = int(r["tier"])
            for t in range(int(r["tier"]) + 1):
                size[t] += 1
    rows = []
    with open(args.audit, encoding="utf-8") as h:
        for r in csv.DictReader(h):
            if r["verdict"] not in ("ok", "wrong", "spurious") or r["occurrenceID"] not in tier:
                continue
            rows.append({"t": tier[r["occurrenceID"]], "stratum": r["stratum"], "weight": float(r["weight"]),
                         **{k: int(float(r[k])) for k in ("err_any", "err_occ", "err_place", "err_attr", "geo_known", "err_geo")}})
    by_stratum = collections.defaultdict(list)
    for r in rows:
        by_stratum[r["stratum"]].append(r)
    rng = random.Random(1)
    boot = collections.defaultdict(list)
    for _ in range(args.reps):
        sample = [rng.choice(rs) for rs in by_stratum.values() for _ in rs]
        for t in range(4):
            boot[t].append(weighted([r for r in sample if r["t"] >= t], "err_any"))
    print(f"{'corpus':30s} {'records':>8s} {'audited':>8s} {'any':>6s} {'occ':>6s} {'place':>6s} {'attr':>6s} {'georef':>7s}   90 % interval of any")
    for t in range(4):
        c = [r for r in rows if r["t"] >= t]
        b = sorted(x for x in boot[t] if x == x)
        lo, hi = b[int(0.05 * len(b))], b[int(0.95 * len(b)) - 1]
        print(f"{NAMES[t]:30s} {size[t]:8,d} {len(c):8d} {weighted(c, 'err_any'):5.1f}% {weighted(c, 'err_occ'):5.1f}% {weighted(c, 'err_place'):5.1f}% "
              f"{weighted(c, 'err_attr'):5.1f}% {weighted(c, 'err_geo', lambda r: r['geo_known']):6.1f}%   {lo:4.1f}–{hi:4.1f} %")


if __name__ == "__main__":
    main()
