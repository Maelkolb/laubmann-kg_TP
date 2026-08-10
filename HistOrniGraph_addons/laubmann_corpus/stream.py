"""Reading-order stream assembly and entry segmentation.

The original builder rebuilt the per-region entry-start scan in three places
(render_volume_md, render_txt, JSON export).  Here every scannable region is
scanned exactly once, in ``annotate_pages``, and the result is stored on the
region as ``reg["starts"]`` (region-local offsets).  The volume-level stream and
its entry segmentation reuse those same offsets, so a header is matched once and
shared by every consumer.
"""

from typing import Any, Dict, List, Optional, Tuple

from .entries import find_entry_starts, strip_markup
from .ids import entry_uid


def annotate_pages(pages: List[Dict[str, Any]], vol_num: int, loose: bool) -> None:
    """Attach ``reg['starts']`` (list of header hits, region-local offsets) to
    every scannable body region, then assign a stable ``entry_uid`` to each hit
    (derived from the volume-stream offset) so the entries table and the
    multimodal catalogue share the same key.  Idempotent within a run."""
    for page in pages:
        for reg in page["regions"]:
            reg["starts"] = (find_entry_starts(reg["text"], loose=loose)
                             if reg.get("scan_entries") else [])
    _assign_entry_uids(pages, vol_num)


def _assign_entry_uids(pages: List[Dict[str, Any]], vol_num: int) -> None:
    pos = 0
    for page in pages:
        for reg in page["regions"]:
            if not reg.get("scan_entries"):
                continue
            for h in reg.get("starts", []):
                h["entry_uid"] = entry_uid(vol_num, page["page_id"], reg["id"],
                                           pos + h["offset"])
            pos += len(reg["text"]) + 2


def build_stream(pages: List[Dict[str, Any]]
                 ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Concatenate scannable regions into one volume stream.

    Returns (stream_text, units, starts).  ``units`` map stream offsets back to
    the region that produced them.  ``starts`` are the region-level header hits
    re-expressed with volume-stream offsets (reusing ``reg['starts']``), so the
    header regex runs once per region, never again over the full stream.
    """
    chunks: List[str] = []
    units: List[Dict[str, Any]] = []
    starts: List[Dict[str, Any]] = []
    pos = 0
    for page in pages:
        for reg in page["regions"]:
            if not reg.get("scan_entries"):
                continue
            text = reg["text"]
            units.append({
                "page_uid": page["page_uid"], "page_id": page["page_id"],
                "image": page["image"], "scan": page["scan"],
                "region_uid": reg["region_uid"], "region_id": reg["id"],
                "region_type": reg["type"], "reading_order": reg["reading_order"],
                "start": pos, "end": pos + len(text),
            })
            for h in reg.get("starts", []):
                sh = dict(h)
                sh["offset"] = pos + h["offset"]
                sh["end"] = pos + h["end"]
                starts.append(sh)
            chunks.append(text)
            pos += len(text) + 2
    return "\n\n".join(chunks), units, starts


def _unit_for_offset(units: List[Dict[str, Any]], offset: int) -> Optional[Dict[str, Any]]:
    for u in units:
        if u["start"] <= offset < u["end"] + 2:
            return u
    return units[-1] if units else None


def segment_entries(vol_num: int, pages: List[Dict[str, Any]]
                    ) -> List[Dict[str, Any]]:
    """Segment the volume stream into entries using the pre-scanned starts.

    Requires ``annotate_pages`` to have run (reads ``reg['starts']``)."""
    vol_text, units, starts = build_stream(pages)
    if not units:
        return []
    entries: List[Dict[str, Any]] = []
    for i, h in enumerate(starts):
        seg_start = h["offset"]
        seg_end = starts[i + 1]["offset"] if i + 1 < len(starts) else len(vol_text)
        raw = vol_text[seg_start:seg_end].strip()
        clean = strip_markup(raw)
        u = _unit_for_offset(units, seg_start) or {}
        euid = h.get("entry_uid") or entry_uid(
            vol_num, u.get("page_id", ""), u.get("region_id", ""), seg_start)
        entries.append({
            "entry_uid": euid,
            "entry_id": f"L{vol_num:02d}-e{i + 1:04d}",
            "volume": vol_num,
            "page_uid": u.get("page_uid", ""),
            "scan": u.get("scan"),
            "page_id": u.get("page_id", ""),
            "image": u.get("image", ""),
            "region_uid": u.get("region_uid", ""),
            "region_id": u.get("region_id", ""),
            "region_type": u.get("region_type", ""),
            "reading_order": u.get("reading_order"),
            "date_raw": h["date"],
            "date_norm": h.get("date_norm"),
            "year": h.get("year"),
            "location_raw": h["location"],
            "variant": h["variant"],
            "month_source": h.get("month_source"),
            "year_form": h.get("year_form"),
            "loc_source": h.get("loc_source"),
            "stream_start": seg_start,
            "stream_end": seg_end,
            "n_chars": len(clean),
            "n_words": len(clean.split()),
            "text_raw": raw,
            "text_clean": clean,
        })
    return entries
