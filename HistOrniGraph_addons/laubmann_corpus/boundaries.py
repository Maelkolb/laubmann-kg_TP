"""Reviewed entry boundaries on top of the date-anchored segmentation.

The header detector (entries.py) only knows a line-initial ``day. month year``
and therefore misses entries — numeric dates of typed reports ("Ismaning, den
14.4.54."), day ranges, year-less dates, headers with markup inside the date
("27. <u>December 1938.</u>"), undated digest sections — and glues the text of
a volume's register onto its last entry. A boundary file fixes both without
touching the transcription:

``start``  a new entry begins at this line (``date_iso`` / ``location`` give its
           date and place; a null date is dated by position, i.e. the date of
           the entry before it, and flagged)
``stop``   the entry before ends at this line; the text up to the next start
           belongs to no entry (registers, indexes, end matter)

Each row names ``volume``, ``page_id``, ``region_id`` and the exact ``line`` as
transcribed. Boundaries only add offsets to the stream: the stream text and
the offsets of all detected headers stay the same, so every existing
``entry_uid`` is unchanged (entry text may get shorter where a start or stop
splits it). New entries get uids by the same derivation.

CSV columns: action, volume, page_id, region_id, line, date_iso, date_end_iso,
date_inferred, location, kind, confidence, source, note.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .entries import strip_markup

FIELDS = ["action", "volume", "page_id", "region_id", "line", "date_iso", "date_end_iso",
          "date_inferred", "location", "kind", "confidence", "source", "note"]
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_boundaries(path: Path) -> List[Dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = [dict(r) for r in csv.DictReader(handle)]
    for r in rows:
        r["action"] = (r.get("action") or "").strip().lower()
        if r["action"] not in ("start", "stop"):
            raise ValueError(f"boundary row with unknown action: {r}")
    return rows


def write_boundaries(path: Path, rows: List[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})


def locate_line(text: str, line: str) -> Optional[int]:
    """Offset of ``line`` as a full line of ``text`` (first occurrence), else
    None. Trailing blanks on either side are tolerated."""
    target = line.rstrip()
    pos = 0
    for raw in text.split("\n"):
        if raw.rstrip() == target:
            return pos
        pos += len(raw) + 1
    return None


def _header_hit(offset: int, row: Dict[str, str]) -> Dict[str, Any]:
    line = row["line"]
    date_iso = (row.get("date_iso") or "").strip()
    date_iso = date_iso if _ISO.match(date_iso) else ""
    inferred = (row.get("date_inferred") or "").strip().lower() in ("y", "yes", "true", "1")
    verbatim = strip_markup(line)[:120]
    return {
        "offset": offset,
        "end": offset + len(line),
        "date": verbatim,                         # date_raw: the header as written
        "location": (row.get("location") or "").strip(),
        "date_norm": date_iso or None,
        "date_end": (row.get("date_end_iso") or "").strip() or None,
        "year": int(date_iso[:4]) if date_iso else None,
        "month": int(date_iso[5:7]) if date_iso else None,
        "day": int(date_iso[8:10]) if date_iso else None,
        "variant": "boundary",
        "month_source": None,
        "year_form": "inferred" if inferred else ("reviewed" if date_iso else "positional"),
        "loc_source": "boundary",
        "header_line": line.strip(),
        "boundary_kind": (row.get("kind") or "").strip() or None,
        "boundary_source": (row.get("source") or "").strip() or None,
    }


def apply_boundaries(pages_by_vol: Dict[int, List[Dict[str, Any]]],
                     rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Attach the boundary rows to the annotated pages (``reg['starts']`` gets
    the new header hits, ``reg['stops']`` the stop offsets). Must run after
    ``annotate_pages`` and before ``segment_entries``; re-run
    ``stream._assign_entry_uids`` afterwards so new starts get uids.

    Returns one report row per boundary: status applied | detected (a start
    the detector already has) | not_found (page/region/line unknown)."""
    index: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for vol, pages in pages_by_vol.items():
        for page in pages:
            index[(vol, page["page_id"])] = page
    report: List[Dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        vol = int(row["volume"])
        page = index.get((vol, row["page_id"]))
        reg = next((r for r in (page or {}).get("regions", [])
                    if (r.get("id") or r.get("region_id")) == row["region_id"]), None)
        offset = locate_line(reg["text"], row["line"]) if reg is not None else None
        if offset is None or not reg.get("scan_entries"):
            out["status"] = "not_found"
            report.append(out)
            continue
        if row["action"] == "stop":
            stops = reg.setdefault("stops", [])
            if offset not in stops:
                stops.append(offset)
                stops.sort()
            out["status"] = "applied"
        else:
            starts = reg.setdefault("starts", [])
            if any(h["offset"] == offset for h in starts):
                out["status"] = "detected"
            else:
                starts.append(_header_hit(offset, row))
                starts.sort(key=lambda h: h["offset"])
                out["status"] = "applied"
        report.append(out)
    return report
