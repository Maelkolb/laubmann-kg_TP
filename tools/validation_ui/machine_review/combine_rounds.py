"""Combine the decision files of several machine review rounds for the pipeline.

``review.machine`` in the config reads ONE identities file and ONE value
corrections file. Later rounds check other or newer names (``--known`` skips
what earlier rounds judged); where two rounds judged the same written name,
the later round wins. Value corrections are keyed by entry uid + written name
+ occurrence; the later round wins as well.

    python tools/validation_ui/machine_review/combine_rounds.py --rounds <r1>/machine_review <r3>/machine_review \\
        --out data/review/machine
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read(path: Path):
    if not path.exists():
        return [], []
    with open(path, encoding="utf-8", newline="") as h:
        r = csv.DictReader(h)
        return list(r), list(r.fieldnames or [])


def write(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", nargs="+", required=True, help="machine_review folders, oldest first")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    for name, key in (("identities_machine.csv", lambda r: (r.get("section"), (r.get("name_form") or "").lower())),
                      ("value_corrections_machine.csv",
                       lambda r: (r.get("entry_uid"), (r.get("old_value") or "").lower(), str(r.get("occurrence")), r.get("kind")))):
        merged, fields, per_round = {}, [], []
        for i, d in enumerate(args.rounds, 1):
            rows, f = read(Path(d) / name)
            fields += [x for x in f if x not in fields]
            for r in rows:
                r["round"] = str(i)
                merged[key(r)] = r
            per_round.append(len(rows))
        if "round" not in fields:
            fields.append("round")
        write(out / name, fields, list(merged.values()))
        print(f"{name}: rows per round {per_round} -> {len(merged)} combined")


if __name__ == "__main__":
    main()
