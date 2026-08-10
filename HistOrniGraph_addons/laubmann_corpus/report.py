"""Per-volume coverage report.

Summarizes, per volume: pages seen, regions by type, regions with empty/failed
transcription, entries detected, % of entries with a normalized date, % with a
location.  Reads raw JSON for the type/transcription census (so it reflects
on-disk truth, unfiltered) and the loaded stream for entry statistics.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loading import _read_page_files, load_volume  # noqa: WPS436 (intra-package)
from .stream import annotate_pages, segment_entries


def _raw_census(vol_dir: Path) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    empty_or_failed: Dict[str, int] = {}
    pages = 0
    for _, _, data in _read_page_files(vol_dir):
        pages += 1
        for r in data:
            rtype = r.get("type", "?")
            by_type[rtype] = by_type.get(rtype, 0) + 1
            tr = r.get("transcription") or {}
            failed = tr.get("status") != "success"
            skipped = bool(tr.get("skipped"))
            has_payload = bool(
                (tr.get("text") or "").strip()
                or (tr.get("description") or "").strip()
                or (tr.get("visible_text") or "").strip()
            )
            if failed or (not skipped and not has_payload):
                empty_or_failed[rtype] = empty_or_failed.get(rtype, 0) + 1
    return {"pages": pages, "by_type": by_type, "empty_or_failed": empty_or_failed}


def build_report(output_base: Path, loose: bool,
                 only_volumes: Optional[List[int]]) -> List[Dict[str, Any]]:
    from .loading import iter_volume_dirs
    rows: List[Dict[str, Any]] = []
    for vol_dir in iter_volume_dirs(output_base, only_volumes):
        vol_num = int(vol_dir.name.split("_")[1])
        census = _raw_census(vol_dir)
        _, pages = load_volume(vol_dir, include_nontext=False)
        annotate_pages(pages, vol_num, loose=loose)
        entries = segment_entries(vol_num, pages)
        n = len(entries)
        with_date = sum(1 for e in entries if e.get("date_norm"))
        with_loc = sum(1 for e in entries if e.get("location_raw"))
        rows.append({
            "volume": vol_num,
            "pages": census["pages"],
            "regions_by_type": census["by_type"],
            "regions_empty_or_failed": census["empty_or_failed"],
            "entries": n,
            "pct_entries_with_date": round(100 * with_date / n, 1) if n else 0.0,
            "pct_entries_with_location": round(100 * with_loc / n, 1) if n else 0.0,
        })
    return rows


def write_report(output_base: Path, corpus_dir: Path, loose: bool,
                 only_volumes: Optional[List[int]]) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    rows = build_report(output_base, loose, only_volumes)
    (corpus_dir / "report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Laubmann corpus — coverage report", ""]
    for r in rows:
        lines.append(f"## Vol. {r['volume']:02d}")
        lines.append(f"- pages: {r['pages']}")
        lines.append(f"- entries: {r['entries']} "
                     f"({r['pct_entries_with_date']}% dated, "
                     f"{r['pct_entries_with_location']}% located)")
        types = ", ".join(f"{t}={r['regions_by_type'][t]}"
                          for t in sorted(r["regions_by_type"]))
        lines.append(f"- regions by type: {types}")
        if r["regions_empty_or_failed"]:
            ef = ", ".join(f"{t}={r['regions_empty_or_failed'][t]}"
                           for t in sorted(r["regions_empty_or_failed"]))
            lines.append(f"- empty/failed transcription: {ef}")
        lines.append("")
    (corpus_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Report: {len(rows)} volume(s)")
    for name in ("report.json", "report.md"):
        print(f"  → {corpus_dir / name}")
