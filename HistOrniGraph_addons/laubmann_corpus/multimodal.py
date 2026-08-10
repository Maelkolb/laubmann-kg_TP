"""Multimodal corpus builder.

Catalogues every non-body-text region — ImageRegion, ObjectRegion,
GraphicRegion, MarginaliaRegion, and any InsertRegion (including
insert_state=="folded", recorded with an empty description and folded:true).

Each row is linked to the nearest preceding entry header in reading order, so an
image, specimen sketch, feather/paper slip or marginal note can be tied to the
diary observation it sits within or adjacent to.  Linking walks the combined
reading-order sequence of body + multimodal regions per volume: as body regions
carrying entry headers pass by, the "current entry" advances; each multimodal
region inherits whatever entry is current at its position.

Outputs (into <corpus_dir>/multimodal/): multimodal.jsonl, multimodal.csv, and a
browsable multimodal.md that inlines the crop image paths.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loading import iter_volume_dirs, load_volume
from .stream import annotate_pages

_CSV_COLS = [
    "region_uid", "page_uid", "volume", "scan", "page_number", "region_type",
    "insert_id", "insert_state", "folded", "crop", "page_side", "reading_order",
    "description", "visible_text",
    "entry_uid", "entry_date_raw", "entry_date_norm", "entry_location",
]


def _iter_multimodal_rows(vol_num: int, pages: List[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None  # nearest preceding entry header
    for page in pages:
        combined = [("body", r) for r in page["regions"]]
        combined += [("mm", r) for r in page["multimodal"]]
        combined.sort(key=lambda kr: (kr[1].get("reading_order") or 0))
        for kind, reg in combined:
            if kind == "body":
                for h in reg.get("starts", []):
                    cur = h
                continue
            rows.append({
                "region_uid": reg["region_uid"],
                "page_uid": page["page_uid"],
                "volume": vol_num,
                "scan": page["scan"],
                "page_number": page["page_number"],
                "region_type": reg["type"],
                "insert_id": reg.get("insert_id"),
                "insert_state": reg.get("insert_state"),
                "folded": bool(reg.get("folded")),
                "crop": reg["crop"],
                "page_side": reg.get("page_side", ""),
                "reading_order": reg["reading_order"],
                "description": reg.get("description", ""),
                "visible_text": reg.get("visible_text", ""),
                "entry_uid": (cur or {}).get("entry_uid", ""),
                "entry_date_raw": (cur or {}).get("date", ""),
                "entry_date_norm": (cur or {}).get("date_norm", ""),
                "entry_location": (cur or {}).get("location", ""),
            })
    return rows


def _render_md(rows: List[Dict[str, Any]]) -> str:
    out: List[str] = ["# Laubmann · Multimodal catalogue", ""]
    cur_vol = None
    for r in rows:
        if r["volume"] != cur_vol:
            cur_vol = r["volume"]
            out.append(f"\n## Vol. {cur_vol:02d}\n")
        ctx = []
        if r["entry_date_raw"]:
            ctx.append(r["entry_date_raw"])
        if r["entry_location"]:
            ctx.append(r["entry_location"])
        ctx_s = f" — entry: {' · '.join(ctx)}" if ctx else " — entry: (none)"
        flags = " [folded]" if r["folded"] else ""
        out.append(
            f"<!-- mm region_uid={r['region_uid']} page_uid={r['page_uid']} "
            f"type={r['region_type']} order={r['reading_order']} "
            f"insert_id={r['insert_id'] if r['insert_id'] is not None else ''} "
            f"insert_state={r['insert_state'] or ''} entry_uid={r['entry_uid']} -->"
        )
        out.append(f"### {r['region_type']} · scan {r['scan']:04d}{flags}{ctx_s}")
        out.append(f"![{r['region_type']}]({r['crop']})")
        if r["description"]:
            out.append(f"\n{r['description']}")
        if r["visible_text"]:
            out.append(f"\n*Visible text:* {r['visible_text']}")
        out.append("")
    return "\n".join(out)


def build_multimodal_corpus(output_base: Path, corpus_dir: Path,
                            loose: bool, only_volumes: Optional[List[int]]) -> Dict[str, Any]:
    mm_dir = corpus_dir / "multimodal"
    mm_dir.mkdir(parents=True, exist_ok=True)
    vol_dirs = iter_volume_dirs(output_base, only_volumes)
    print(f"Found {len(vol_dirs)} volume(s).")

    all_rows: List[Dict[str, Any]] = []
    for vi, vol_dir in enumerate(vol_dirs, 1):
        vol_num, pages = load_volume(vol_dir, include_nontext=False)
        if not pages:
            print(f"  [{vi:02d}/{len(vol_dirs)}] Vol.{vol_num:02d}  [!] no pages, skipping.")
            continue
        annotate_pages(pages, vol_num, loose=loose)
        rows = _iter_multimodal_rows(vol_num, pages)
        all_rows.extend(rows)
        n_folded = sum(1 for r in rows if r["folded"])
        print(f"  [{vi:02d}/{len(vol_dirs)}] Vol.{vol_num:02d}  "
              f"{len(rows)} multimodal regions ({n_folded} folded)")

    with (mm_dir / "multimodal.jsonl").open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    with (mm_dir / "multimodal.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    (mm_dir / "multimodal.md").write_text(_render_md(all_rows), encoding="utf-8")

    by_type: Dict[str, int] = {}
    for r in all_rows:
        by_type[r["region_type"]] = by_type.get(r["region_type"], 0) + 1
    print(f"\nMultimodal: {len(all_rows)} regions across {len(vol_dirs)} volume(s)")
    for t in sorted(by_type):
        print(f"    {t}: {by_type[t]}")
    for name in ("multimodal.jsonl", "multimodal.csv", "multimodal.md"):
        print(f"  → {mm_dir / name}")

    return {"regions": len(all_rows), "by_type": by_type}
