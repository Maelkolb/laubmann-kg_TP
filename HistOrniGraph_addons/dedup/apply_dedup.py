#!/usr/bin/env python3
"""Apply confirmed dedup decisions to produce a clean corpus (non-destructive).

Reads the original corpus/ artifacts plus a dedup_decisions.json exported from
the review GUI. Writes a NEW corpus directory: the kept pages only, with
corpus.json, corpus.txt, entries.jsonl and entries.csv regenerated, plus a
dedup_manifest.json / .csv recording every dropped page, the cluster it
belonged to, the page kept in its place, and why. The input corpus is never
modified.

Only clusters with decision == "confirm" drop pages. "reject" clusters and any
cluster absent from the decisions file keep every page. Containment clusters
keep the superset page by default (the review GUI's keep choice wins).

Usage:
    python apply_dedup.py --corpus-dir corpus \
        --decisions dedup_reports/dedup_decisions.json \
        --out-dir corpus_dedup
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent, Path.cwd()):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    # New layout: functions live in the laubmann_corpus package.
    from laubmann_corpus.entries import find_entry_starts, strip_markup  # type: ignore
    _HAVE_BUILDER = True
except Exception:
    try:
        # Old layout: monolithic build_corpus.py defined them at top level.
        from build_corpus import find_entry_starts, strip_markup  # type: ignore
        _HAVE_BUILDER = True
    except Exception:
        _HAVE_BUILDER = False

try:
    # Full builder stack: reuse the exact segmentation + uid derivation of
    # build_corpus.py so the deduped entries.* are column-identical (incl.
    # entry_uid / page_uid / region_uid, which the KG stage joins on).
    from laubmann_corpus.ids import page_uid as _page_uid  # type: ignore
    from laubmann_corpus.loading import ENTRY_SCAN_TYPES  # type: ignore
    from laubmann_corpus.stream import annotate_pages, segment_entries  # type: ignore
    _HAVE_STREAM = True
except Exception:
    _HAVE_STREAM = False


def _uid(page: Dict[str, Any]) -> str:
    return f"L{int(page['volume']):02d}:{page['page_id']}"


def load_decisions(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    confirmed = {}
    for d in obj.get("decisions", []):
        if d.get("decision") == "confirm":
            confirmed[d["cluster_id"]] = d
    return confirmed


def resolve_drops(decisions: Dict[str, Any],
                  known_uids: Set[str]) -> Dict[str, Dict[str, Any]]:
    """Return {dropped_uid: {kept_uid, cluster_id, reason}}."""
    drops: Dict[str, Dict[str, Any]] = {}
    for cid, d in decisions.items():
        keep = d["keep"]
        if "drop" not in d:
            print(f"WARNING: confirmed cluster {cid} has no 'drop' list — "
                  f"nothing will be dropped for it. Export decisions from the "
                  f"review GUI (schema laubmann_dedup_decisions_v1), which "
                  f"fills 'drop' with the non-kept members.", file=sys.stderr)
        for uid in d.get("drop", []):
            if uid not in known_uids or keep not in known_uids:
                continue
            if uid == keep:
                continue
            drops[uid] = {"kept_uid": keep, "cluster_id": cid,
                          "relation": d.get("relation", ""),
                          "confidence": d.get("confidence"),
                          "note": d.get("note", "")}
    return drops


def regenerate_entries(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-segment entries per volume over the surviving reading-order stream."""
    if _HAVE_STREAM:
        return _regenerate_entries_stream(pages)
    if not _HAVE_BUILDER:
        return []
    entries: List[Dict[str, Any]] = []
    by_vol: Dict[int, List[Dict[str, Any]]] = {}
    for p in pages:
        by_vol.setdefault(int(p["volume"]), []).append(p)
    scan_types = {"ParagraphRegion", "ListRegion"}
    for vol, vpages in sorted(by_vol.items()):
        vpages = sorted(vpages, key=lambda p: (p["scan"], p["page_id"]))
        chunks, units, pos = [], [], 0
        for page in vpages:
            for reg in page["regions"]:
                if reg["type"] not in scan_types or not reg.get("text"):
                    continue
                text = reg.get("text", "")
                units.append({"page_id": page["page_id"],
                              "image": page.get("image", ""),
                              "scan": page.get("scan", 0),
                              "region_id": reg.get("id") or reg.get("region_id", ""),
                              "region_type": reg.get("type") or reg.get("region_type", ""),
                              "reading_order": reg.get("reading_order"),
                              "start": pos, "end": pos + len(text)})
                chunks.append(text)
                pos += len(text) + 2
        if not units:
            continue
        vol_text = "\n\n".join(chunks)
        starts = find_entry_starts(vol_text)
        for i, h in enumerate(starts):
            s0 = h["offset"]
            s1 = starts[i + 1]["offset"] if i + 1 < len(starts) else len(vol_text)
            raw = vol_text[s0:s1].strip()
            clean = strip_markup(raw)
            u = next((u for u in units if u["start"] <= s0 < u["end"] + 2),
                     units[-1])
            entries.append({
                "entry_id": f"L{vol:02d}-e{i + 1:04d}", "volume": vol,
                "scan": u["scan"], "page_id": u["page_id"],
                "image": u["image"], "region_id": u["region_id"],
                "region_type": u["region_type"],
                "reading_order": u["reading_order"],
                "date_raw": h["date"], "date_norm": h.get("date_norm"),
                "year": h.get("year"), "location_raw": h["location"],
                "variant": h["variant"], "n_chars": len(clean),
                "n_words": len(clean.split()),
                "text_raw": raw, "text_clean": clean})
    return entries


def _regenerate_entries_stream(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-segment via laubmann_corpus.stream so the output matches the original
    builder exactly, including entry_uid / page_uid / region_uid.

    Works on a deep copy: annotate_pages mutates regions (adds ``starts`` /
    ``scan_entries``), and those working keys must not leak into the deduped
    corpus.json."""
    import copy
    entries: List[Dict[str, Any]] = []
    by_vol: Dict[int, List[Dict[str, Any]]] = {}
    for p in copy.deepcopy(pages):
        by_vol.setdefault(int(p["volume"]), []).append(p)
    for vol, vpages in sorted(by_vol.items()):
        vpages.sort(key=lambda p: (int(p.get("scan", 0)), p["page_id"]))
        for page in vpages:
            page.setdefault("page_uid", _page_uid(vol, page["page_id"]))
            page.setdefault("image", f"{page['page_id']}.png")
            for reg in page.get("regions", []):
                reg.setdefault("id", reg.get("region_id", ""))
                reg.setdefault("type", reg.get("region_type", ""))
                reg.setdefault("reading_order", None)
                reg.setdefault("region_uid", "")
                reg.setdefault("text", "")
                reg.setdefault("scan_entries",
                               reg["type"] in ENTRY_SCAN_TYPES and bool(reg["text"]))
        annotate_pages(vpages, vol, loose=False)
        entries.extend(segment_entries(vol, vpages))
    return entries


def write_corpus(pages: List[Dict[str, Any]], entries: List[Dict[str, Any]],
                 out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")

    txt: List[str] = []
    for p in sorted(pages, key=lambda p: (p["volume"], p["scan"], p["page_id"])):
        txt.append(f"\n=== Vol.{p['volume']:02d}  scan {p['scan']:04d}  "
                   f"{p['page_id']} ===")
        for reg in p["regions"]:
            txt.append(reg.get("text", ""))
            txt.append("")
    (out_dir / "corpus.txt").write_text("\n".join(txt), encoding="utf-8")

    if entries:
        with (out_dir / "entries.jsonl").open("w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        cols = ["entry_id", "volume", "scan", "page_id", "image", "region_id",
                "region_type", "reading_order", "date_raw", "date_norm", "year",
                "location_raw", "variant", "n_chars", "n_words", "preview",
                "text_clean"]
        if _HAVE_STREAM:
            # match the full builder contract (INTERFACES.md): stable ids +
            # normalization provenance, appended after text_clean
            cols += ["entry_uid", "page_uid", "region_uid",
                     "month_source", "year_form", "loc_source"]
        with (out_dir / "entries.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for e in entries:
                row = dict(e)
                tc = e["text_clean"]
                row["preview"] = (tc[:120] + "…") if len(tc) > 120 else tc
                w.writerow(row)


def write_manifest(drops: Dict[str, Dict[str, Any]],
                   pages_by_uid: Dict[str, Dict[str, Any]],
                   out_dir: Path, stats: Dict[str, Any]) -> None:
    records = []
    for uid, info in sorted(drops.items()):
        p = pages_by_uid[uid]
        records.append({
            "dropped_page_uid": uid, "volume": p["volume"],
            "page_id": p["page_id"], "scan": p["scan"],
            "page_number": p.get("page_number", ""),
            "image": p.get("image", ""), "n_regions": len(p["regions"]),
            "kept_page_uid": info["kept_uid"], "cluster_id": info["cluster_id"],
            "relation": info["relation"], "confidence": info["confidence"],
            "note": info["note"]})
    (out_dir / "dedup_manifest.json").write_text(
        json.dumps({"stats": stats, "dropped": records},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "dedup_manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dropped_page_uid", "volume", "scan", "page_number",
                    "n_regions", "kept_page_uid", "cluster_id", "relation",
                    "confidence", "note"])
        for r in records:
            w.writerow([r["dropped_page_uid"], r["volume"], r["scan"],
                        r["page_number"], r["n_regions"], r["kept_page_uid"],
                        r["cluster_id"], r["relation"], r["confidence"],
                        r["note"]])


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--decisions", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    corpus_json = args.corpus_dir / "corpus.json"
    pages = json.loads(corpus_json.read_text(encoding="utf-8"))
    pages_by_uid = {_uid(p): p for p in pages}
    known = set(pages_by_uid)

    decisions = load_decisions(args.decisions)
    drops = resolve_drops(decisions, known)

    kept = [p for p in pages if _uid(p) not in drops]
    entries = regenerate_entries(kept)

    stats = {
        "input_pages": len(pages), "output_pages": len(kept),
        "dropped_pages": len(drops),
        "confirmed_clusters": len(decisions),
        "output_entries": len(entries),
        "entries_regenerated": _HAVE_BUILDER,
    }
    write_corpus(kept, entries, args.out_dir)
    write_manifest(drops, pages_by_uid, args.out_dir, stats)

    print(f"input:   {len(pages)} pages")
    print(f"dropped: {len(drops)} pages across {len(decisions)} confirmed clusters")
    print(f"output:  {len(kept)} pages"
          + (f", {len(entries)} entries" if entries else
             " (entries not regenerated — build_corpus.py not importable)"))
    print(f"→ {args.out_dir}/corpus.json")
    print(f"→ {args.out_dir}/dedup_manifest.json")
    print(f"→ {args.out_dir}/dedup_manifest.csv")


if __name__ == "__main__":
    main()
