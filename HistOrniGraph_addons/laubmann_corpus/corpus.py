"""Primary text corpus builder.

Orchestrates load → annotate (scan once) → segment → render → write.  Output
artifacts and their column sets match the original build_corpus.py, with two
documented additions: page_uid/region_uid in corpus.json and the markdown
comments, and entry_uid/provenance columns appended to entries.csv.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loading import iter_volume_dirs, load_volume
from .render import render_volume_md, render_txt
from .stream import annotate_pages, segment_entries

_CSV_COLS = [
    "entry_id", "volume", "scan", "page_id", "image", "region_id",
    "region_type", "reading_order", "date_raw", "date_norm", "year",
    "location_raw", "variant", "n_chars", "n_words", "preview", "text_clean",
    # appended (see CHANGELOG): stable ids + normalization provenance
    "entry_uid", "page_uid", "region_uid",
    "month_source", "year_form", "loc_source",
]


def _page_json(vol_num: int, page: Dict[str, Any]) -> Dict[str, Any]:
    page_regions = []
    for reg in page["regions"]:
        page_regions.append({
            "region_uid": reg["region_uid"],
            "id": reg["id"], "type": reg["type"],
            "reading_order": reg["reading_order"],
            "page_side": reg["page_side"], "line_count": reg["line_count"],
            "crop": reg["crop"], "text": reg["text"],
            "entry_starts": [
                {"entry_uid": h.get("entry_uid"), "date": h["date"],
                 "location": h["location"],
                 "date_norm": h.get("date_norm"), "offset": h["offset"],
                 "variant": h["variant"], "month_source": h.get("month_source"),
                 "year_form": h.get("year_form"), "loc_source": h.get("loc_source")}
                for h in reg.get("starts", [])
            ],
        })
    return {
        "volume": vol_num, "page_uid": page["page_uid"],
        "page_id": page["page_id"], "image": page["image"],
        "scan": page["scan"], "page_number": page["page_number"],
        "regions": page_regions,
    }


def build_text_corpus(output_base: Path, corpus_dir: Path, per_volume: bool,
                      include_nontext: bool, loose: bool,
                      only_volumes: Optional[List[int]]) -> Dict[str, Any]:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    vol_dirs = iter_volume_dirs(output_base, only_volumes)
    print(f"Found {len(vol_dirs)} volume(s).")

    corpus_json: List[Dict[str, Any]] = []
    all_entries: List[Dict[str, Any]] = []
    md_parts: List[str] = []
    txt_lines: List[str] = []
    by_vol_dir = corpus_dir / "by_volume"
    if per_volume:
        by_vol_dir.mkdir(exist_ok=True)

    total_pages = total_regions = 0

    for vi, vol_dir in enumerate(vol_dirs, 1):
        vol_num, all_pages = load_volume(vol_dir, include_nontext)
        # Text corpus only sees pages with body regions — a page whose sole
        # content is multimodal (e.g. an isolated marginal note) does not appear
        # here, matching the original builder; the multimodal builder keeps it.
        pages = [p for p in all_pages if p["regions"]]
        if not pages:
            print(f"  [{vi:02d}/{len(vol_dirs)}] Vol.{vol_num:02d}  [!] no usable regions, skipping.")
            continue

        annotate_pages(pages, vol_num, loose=loose)
        entries = segment_entries(vol_num, pages)
        all_entries.extend(entries)

        for page in pages:
            corpus_json.append(_page_json(vol_num, page))

        md = render_volume_md(vol_num, pages)
        md_parts.append(md)
        txt_lines.extend(render_txt(vol_num, pages))
        if per_volume:
            (by_vol_dir / f"Laubmann_{vol_num:02d}.md").write_text(md, encoding="utf-8")

        n_regions = sum(len(p["regions"]) for p in pages)
        total_pages += len(pages)
        total_regions += n_regions
        print(f"  [{vi:02d}/{len(vol_dirs)}] Vol.{vol_num:02d}  "
              f"{len(pages)} pages, {n_regions} regions, {len(entries)} entries")

    (corpus_dir / "corpus.json").write_text(
        json.dumps(corpus_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (corpus_dir / "corpus.md").write_text("\n\n".join(md_parts), encoding="utf-8")
    (corpus_dir / "corpus.txt").write_text("\n".join(txt_lines), encoding="utf-8")

    with (corpus_dir / "entries.jsonl").open("w", encoding="utf-8") as fh:
        for e in all_entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    with (corpus_dir / "entries.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for e in all_entries:
            row = dict(e)
            row["preview"] = (e["text_clean"][:120] + "…") if len(e["text_clean"]) > 120 else e["text_clean"]
            w.writerow(row)

    print(f"\nCorpus: {total_pages} pages, {total_regions} regions, {len(all_entries)} entries")
    for name in ("corpus.md", "corpus.json", "corpus.txt", "entries.jsonl", "entries.csv"):
        print(f"  → {corpus_dir / name}")
    if per_volume:
        print(f"  → {by_vol_dir}/Laubmann_NN.md")

    return {"pages": total_pages, "regions": total_regions, "entries": len(all_entries)}
