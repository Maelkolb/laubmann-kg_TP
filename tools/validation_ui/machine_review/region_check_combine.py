"""Combine the two region checks (region_check.py) into decisions the pipeline applies: where both models agree.

    python tools/validation_ui/machine_review/region_check_combine.py --work data/cache/region_check \\
        --models gemini-3.8-flash gemini-3.7-flash --out data/review/machine/region_quality_machine.csv

A region is dropped when both checks say it shows the same physical object as another region and that region shows
it better, with the same kind of content in both (`duplicate`: a repeat scan, a cut-off strip, the mirror image of a
photograph or typed sheet seen through the paper), or that it is blank paper (`blank`), or a fragment that is no part of a
larger object (`fragment`). Completeness is set where both agree (`complete`, `cut off`); a region both call cut
off by its box gets a new box (the mean of the two boxes, when they overlap by at least half) and is cut anew from
its page scan (`recrop.py`). A duplicate is dropped only when a last check of the pair (region_duplicate_check.py) finds that it shows nothing the
kept region lacks. Everything else stays as it is.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

FIELDS = ["region_uid", "entry_uid", "page_id", "scan", "kind", "decision", "reason", "duplicate_of", "completeness",
          "cut", "cause", "box", "agreement", "confidence", "why_a", "why_b", "reviewed_by"]


def answers(work: Path, model: str, regions: dict) -> dict:
    """region_uid -> the model's answer from the window where the region sits most centrally."""
    best: dict = {}
    for path in sorted((work / model / "answers").glob("*.json")):
        a = json.loads(path.read_text(encoding="utf-8"))
        rows = {r.get("id"): r for r in ((a.get("answer") or {}).get("regions") or []) if isinstance(r, dict)}
        labels = a["regions"]
        uid_of = {lab: uid for lab, uid in labels.items()}
        n = len(labels)
        for i, (lab, uid) in enumerate(labels.items()):
            r = rows.get(lab)
            if r is None:
                continue
            centrality = min(i, n - 1 - i)
            if uid not in best or centrality > best[uid][0]:
                same = {uid_of[x] for x in r.get("same_as") or [] if x in uid_of}
                parts = {uid_of[x] for x in r.get("parts_of") or [] if x in uid_of}
                best[uid] = (centrality, dict(r, same=same, parts=parts, model=model))
    return {uid: v[1] for uid, v in best.items()}


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def valid_box(b) -> bool:
    return isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b) and b[2] > b[0] and b[3] > b[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--models", nargs=2, required=True)
    ap.add_argument("--regions", default="data/corpus_patched/multimodal_regions.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--duplicate-check", default=None, help="region_duplicate_check.py output: a duplicate that adds anything stays")
    args = ap.parse_args()
    adds = json.loads(Path(args.duplicate_check).read_text(encoding="utf-8")) if args.duplicate_check else None
    regions = {}
    for line in open(args.regions, encoding="utf-8"):
        r = json.loads(line)
        if r.get("entry_uid"):
            regions[r["region_uid"]] = r
    A = answers(Path(args.work), args.models[0], regions)
    B = answers(Path(args.work), args.models[1], regions)

    def representative(uid: str, ans: dict) -> str | None:
        """The region the model marks best among those it calls the same object as uid."""
        cands = [u for u in ans[uid]["same"] if ans.get(u, {}).get("best")]
        return cands[0] if cands else None

    rows, stats = [], collections.Counter()
    drops = {}
    for uid, r in regions.items():
        a, b = A.get(uid), B.get(uid)
        if not a or not b:
            stats["not judged by both"] += 1
            continue
        ca, cb = a.get("content"), b.get("content")
        if ca == "blank" and cb == "blank":
            drops[uid] = ("blank", "")
        elif {ca, cb} <= {"blank", "fragment"} and not a["parts"] and not b["parts"]:
            drops[uid] = ("fragment", "")
        elif a["same"] and b["same"] and a.get("best") is False and b.get("best") is False:
            ra, rb = representative(uid, A), representative(uid, B)
            rep = ra if ra and (ra == rb or rb is None) else rb if ra is None else ra
            # the same kind of content in both regions by both checks: the written back of a postcard is
            # not a repeat of its picture side
            same_kind = rep and all(ans.get(rep, {}).get("content") == ans[uid].get("content") for ans in (A, B))
            if rep and same_kind:
                drops[uid] = ("duplicate", rep)
                if regions.get(rep, {}).get("entry_uid") != r["entry_uid"]:
                    stats["duplicate of a region placed with another entry"] += 1
            elif rep:
                stats["same object, other content (e.g. the back of a postcard): kept"] += 1
    for uid, (reason, rep) in list(drops.items()):     # a duplicate that shows anything its twin lacks stays
        if reason == "duplicate" and adds is not None and adds.get(uid, {}).get("adds") is not False:
            del drops[uid]
            stats["duplicate that adds something (note, caption, other part): kept"] += 1
    for uid, (reason, rep) in list(drops.items()):     # never drop the region a duplicate points to
        if reason == "duplicate" and rep in drops:
            del drops[uid]
            stats["duplicate whose representative is dropped too: kept"] += 1

    for uid, r in regions.items():
        a, b = A.get(uid), B.get(uid)
        if not a or not b:
            continue
        row = {"region_uid": uid, "entry_uid": r["entry_uid"], "page_id": r["page_id"], "scan": r.get("scan"), "kind": r.get("kind"),
               "decision": "keep", "why_a": (a.get("why") or "")[:200], "why_b": (b.get("why") or "")[:200],
               "reviewed_by": f"machine:{args.models[0]}+{args.models[1]} (region check)"}
        try:
            row["confidence"] = f"{1 - (1 - float(a.get('c') or 0)) * (1 - float(b.get('c') or 0)):.2f}"
        except (TypeError, ValueError):
            row["confidence"] = ""
        if uid in drops:
            row.update(decision="drop", reason=drops[uid][0], duplicate_of=drops[uid][1], agreement=2)
            stats[f"drop {drops[uid][0]}"] += 1
        elif a.get("complete") is False and b.get("complete") is False:
            causes = {a.get("cause"), b.get("cause")}
            row.update(completeness="cut off", cut=";".join(sorted(set(a.get("cut") or []) | set(b.get("cut") or []))),
                       cause=causes.pop() if len(causes) == 1 else "unclear", agreement=2)
            ba, bb = a.get("box"), b.get("box")
            if row["cause"] == "box" and valid_box(ba) and valid_box(bb) and iou(ba, bb) >= 0.5:
                row["box"] = json.dumps([round((x + y) / 2000, 4) for x, y in zip(ba, bb)])
                stats["cut off by its box: new box"] += 1
            stats[f"cut off ({row['cause']})"] += 1
        elif a.get("complete") is True and b.get("complete") is True:
            row.update(completeness="complete", agreement=2)
            stats["complete"] += 1
        else:
            row["agreement"] = 1
            stats["completeness disputed"] += 1
        rows.append(row)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    stats["regions"] = len(regions)
    stats["rows"] = len(rows)
    print(json.dumps(dict(sorted(stats.items())), indent=1))


if __name__ == "__main__":
    main()
