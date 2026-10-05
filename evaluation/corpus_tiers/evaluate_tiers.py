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

The verdicts are those of the audited export. With ``--dwca <export>/dwca --before-dwca <audited export>/dwca`` an
audited record whose observer or record type the evaluated export changed is judged again against what the auditor
gave as right (``correct`` of audit.csv; where the auditor accepted the attribution, the audited export's values):
a corrected attribution then counts as right, a new wrong one as an error. Nothing else is re-judged.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ["full", "core", "strict core", "strict core with coordinates"]
ATTR_FIELDS = {"observer", "record_type"}
TITLES = {"dr", "herr", "hr", "frau", "frl", "prof", "freund", "praeparator", "oberlehrer", "probably", "vermutlich", "wohl", "not", "nicht"}
UNNAMED = re.compile(r"author|unnamed|not named|unknown|unbekannt|verfasser", re.I)
DIARIST = "laubmann"


def fold(s: str) -> str:
    s = (s or "").casefold()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def people(value: str) -> list[tuple[str, str]]:
    """(first name, surname) of the persons in a recordedBy value or an auditor's observer text."""
    out = []
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", value or "")      # the auditor's remarks in brackets
    for part in re.split(r"\s*[|;,]\s*|\s+(?:and|und|with|mit)\s+", value):
        if not part.strip() or UNNAMED.search(part):
            continue
        toks = [t for t in re.findall(r"[A-Za-zÄÖÜäöüß]+", part) if fold(t) not in TITLES]
        if toks:
            out.append((fold(toks[0]) if len(toks) > 1 and len(toks[0]) > 2 else "", fold(toks[-1])))
    return out


def same_people(a: list, b: list) -> bool:
    """Same surnames, and no conflicting written-out first names ("Heinrich Wüst" is not "Walter Wüst")."""
    if {s for _, s in a} != {s for _, s in b}:
        return False
    firsts = {s: f for f, s in a if f}
    return all(not f or not firsts.get(s) or firsts[s].startswith(f) or f.startswith(firsts[s]) for f, s in b)


def attribution(dwca: str) -> dict:
    """occurrenceID -> (recordedBy, recordType) of an export."""
    rt = {}
    with open(Path(dwca) / "measurementorfact.txt", encoding="utf-8") as h:
        for r in csv.DictReader(h, delimiter="\t"):
            if r["measurementType"] == "recordType":
                rt[r["occurrenceID"]] = r["measurementValue"]
    with open(Path(dwca) / "occurrence.txt", encoding="utf-8") as h:
        return {r["occurrenceID"]: (r["recordedBy"] or "", rt.get(r["occurrenceID"], "field-observation"))
                for r in csv.DictReader(h, delimiter="\t")}


def rejudge(a: dict, before: tuple, after: tuple) -> int:
    """1 when the evaluated export's attribution (recordedBy, recordType) is wrong by the audit, else 0."""
    corr = json.loads(a["correct"] or "{}")
    if a["err_attr"] in ("1.0", "1"):
        want_type = str(corr.get("record_type") or "").split(" ")[0]
        want_obs = corr.get("observer")
    else:
        want_type, want_obs = before[1], before[0]
    got_by, got_type = after
    if want_type and not got_type.startswith(want_type[:10]):
        return 1
    if want_obs is None:
        return 0 if (want_type or a["err_attr"] not in ("1.0", "1")) else 1
    if UNNAMED.search(want_obs):
        # "author of the typed report (not named; probably W. Wüst), not Laubmann": the auditor only says who it is not
        return 0 if DIARIST not in fold(got_by) else 1
    want, got = people(want_obs), people(got_by)
    return 0 if same_people(want, got) else 1


def weighted(rows, key, cond=None):
    rows = [r for r in rows if cond is None or cond(r)]
    w = sum(r["weight"] for r in rows)
    return 100 * sum(r["weight"] * r[key] for r in rows) / w if w else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tiers", help="record_tiers.csv (build_review.py --tiers-csv)")
    ap.add_argument("--audit", default=str(HERE / "audit.csv"))
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--dwca", default=None, help="dwca/ of the evaluated export: re-judge changed attributions")
    ap.add_argument("--before-dwca", default=None, help="dwca/ of the export the audit judged (kg_exports_2026-10-04_text)")
    args = ap.parse_args()
    after = attribution(args.dwca) if args.dwca and args.before_dwca else {}
    before = attribution(args.before_dwca) if after else {}
    rejudged = collections.Counter()

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
            row = {"t": tier[r["occurrenceID"]], "stratum": r["stratum"], "weight": float(r["weight"]),
                   **{k: int(float(r[k])) for k in ("err_any", "err_occ", "err_place", "err_attr", "geo_known", "err_geo")}}
            o = r["occurrenceID"]
            if after and o in before and o in after and before[o] != after[o]:
                err = rejudge(r, before[o], after[o])
                rejudged[(row["err_attr"], err)] += 1
                others = {f for f in r["wrong_fields"].split(";") if f} - ATTR_FIELDS
                row["err_attr"] = err
                row["err_any"] = int(err or bool(others) or r["verdict"] == "spurious")
            rows.append(row)
    if after:
        print("attribution re-judged (before -> after: n):", {f"{a}->{b}": n for (a, b), n in sorted(rejudged.items())})
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
