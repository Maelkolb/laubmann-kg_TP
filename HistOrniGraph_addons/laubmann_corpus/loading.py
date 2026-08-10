"""Volume / region loading and the schema census.

``load_volume`` reconstructs each page's regions in reading order.  It keeps two
partitions on every page:

    regions       — body-text regions used by the primary text corpus
                    (identical selection to the original build_corpus.py)
    multimodal    — non-body-text regions for the multimodal catalogue
                    (Image/Object/Graphic/Marginalia + any insert, incl. folded)

Both partitions carry ``page_uid`` / ``region_uid`` so the two corpora join
without re-parsing markdown.  Field access is defensive: nothing here assumes a
field exists beyond ``id`` / ``type`` / ``transcription``, which are present on
every real region.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .ids import page_uid, region_uid

BODY_TEXT_TYPES = {"ParagraphRegion", "ListRegion", "FootnoteRegion", "TableRegion"}
ENTRY_SCAN_TYPES = {"ParagraphRegion", "ListRegion"}
NONTEXT_TYPES = {"ImageRegion", "ObjectRegion", "MarginaliaRegion"}
MULTIMODAL_TYPES = {
    "ImageRegion", "ObjectRegion", "GraphicRegion",
    "MarginaliaRegion", "InsertRegion",
}
PAGE_META_TYPES = {"PageNumberRegion"}


# ── page-id parsing / sorting ────────────────────────────────────────────────

def _parse_pid(stem: str) -> Tuple[int, str]:
    side = ""
    base = stem
    if len(stem) > 2 and stem[-2] == "_" and stem[-1] in "LRlr":
        side = stem[-1].upper()
        base = stem[:-2]
    nums = re.findall(r"\d+", base)
    scan = int(nums[-1]) if nums else 0
    return scan, side


def _page_sort_key(page_id: str) -> Tuple[int, int]:
    scan, side = _parse_pid(page_id)
    return (scan, {"": 0, "L": 0, "R": 1}.get(side, 0))


def region_crop_path(page_id: str, region_id: str, rtype: str) -> str:
    return f"regions/{page_id}/{region_id}_{rtype}.png"


# ── transcription extraction ─────────────────────────────────────────────────

def _body_text(r: Dict[str, Any]) -> str:
    tr = r.get("transcription") or {}
    if tr.get("status") != "success" or tr.get("skipped"):
        return ""
    rtype = r.get("type")
    if rtype in ("ImageRegion", "ObjectRegion"):
        desc = tr.get("description") or tr.get("text") or ""
        vis = tr.get("visible_text", "")
        if vis and vis.lower() != "none":
            desc = f"{desc}\nText: {vis}".strip()
        return desc.strip()
    return (tr.get("text") or "").strip()


def _mm_fields(r: Dict[str, Any]) -> Dict[str, Any]:
    tr = r.get("transcription") or {}
    folded = r.get("insert_state") == "folded"
    if folded:
        return {"description": "", "visible_text": "", "folded": True,
                "status": tr.get("status", ""), "skipped": bool(tr.get("skipped"))}
    ok = tr.get("status") == "success" and not tr.get("skipped")
    desc = tr.get("description")
    vis = tr.get("visible_text")
    if desc is None and ok:
        desc = tr.get("text") or ""
    if vis and str(vis).lower() == "none":
        vis = ""
    return {
        "description": (desc or "").strip(),
        "visible_text": (vis or "").strip(),
        "folded": False,
        "status": tr.get("status", ""),
        "skipped": bool(tr.get("skipped")),
    }


def _page_number(regions: List[Dict[str, Any]]) -> str:
    for r in regions:
        if r.get("type") == "PageNumberRegion":
            pn = r.get("page_number") or (r.get("transcription") or {}).get("text", "")
            if pn:
                return str(pn).strip()
    return ""


# ── volume discovery ─────────────────────────────────────────────────────────

def iter_volume_dirs(output_base: Path,
                     only_volumes: Optional[List[int]] = None) -> List[Path]:
    dirs = sorted(
        (d for d in output_base.iterdir()
         if d.is_dir() and d.name.startswith("Laubmann_") and d.name.endswith("_gemini")),
        key=lambda p: int(p.name.split("_")[1]),
    )
    if only_volumes:
        keep = set(only_volumes)
        dirs = [d for d in dirs if int(d.name.split("_")[1]) in keep]
    return dirs


def _read_page_files(vol_dir: Path) -> Iterator[Tuple[str, int, List[Dict[str, Any]]]]:
    regions_dir = vol_dir / "regions"
    if not regions_dir.exists():
        return
    files = sorted(regions_dir.glob("*.json"), key=lambda p: _page_sort_key(p.stem))
    for jf in files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [!] Cannot read {jf.name}: {exc}")
            continue
        if not isinstance(data, list):
            continue
        scan, _ = _parse_pid(jf.stem)
        yield jf.stem, scan, data


def load_volume(vol_dir: Path, include_nontext: bool
                ) -> Tuple[int, List[Dict[str, Any]]]:
    vol_num = int(vol_dir.name.split("_")[1])
    pages: List[Dict[str, Any]] = []

    for page_id, scan, data in _read_page_files(vol_dir):
        page_num = _page_number(data)
        puid = page_uid(vol_num, page_id)

        body: List[Dict[str, Any]] = []
        multimodal: List[Dict[str, Any]] = []

        for r in sorted(data, key=lambda r: r.get("reading_order", 99)):
            rtype = r.get("type", "")
            if rtype in PAGE_META_TYPES:
                continue

            reading_order = r.get("reading_order", len(body) + len(multimodal) + 1)
            rid = r.get("id", "")
            ruid = region_uid(vol_num, page_id, rid, reading_order)
            is_insert = r.get("page_side") == "insert" or "insert_id" in r
            is_folded = r.get("insert_state") == "folded"
            is_mm_type = rtype in MULTIMODAL_TYPES

            if is_mm_type or is_insert:
                mm = _mm_fields(r)
                multimodal.append({
                    "region_uid": ruid, "id": rid, "type": rtype,
                    "reading_order": reading_order,
                    "page_side": r.get("page_side", ""),
                    "insert_id": r.get("insert_id"),
                    "insert_state": r.get("insert_state"),
                    "crop": region_crop_path(page_id, rid, rtype),
                    **mm,
                })

            if is_folded:
                continue
            is_body = rtype in BODY_TEXT_TYPES
            if not is_body and not (include_nontext and rtype in NONTEXT_TYPES):
                continue
            text = _body_text(r)
            if not text:
                continue
            body.append({
                "region_uid": ruid,
                "id": rid,
                "type": rtype,
                "reading_order": reading_order,
                "page_side": r.get("page_side", ""),
                "line_count": r.get("line_count"),
                "crop": region_crop_path(page_id, rid, rtype),
                "text": text,
                "is_body": is_body,
                "scan_entries": rtype in ENTRY_SCAN_TYPES,
            })

        if body or multimodal:
            pages.append({
                "page_uid": puid,
                "page_id": page_id,
                "image": f"{page_id}.png",
                "scan": scan,
                "page_number": page_num,
                "regions": body,
                "multimodal": multimodal,
            })
    return vol_num, pages


# ── schema census ────────────────────────────────────────────────────────────

def schema_census(output_base: Path, only_volumes: Optional[List[int]],
                  sample_volumes: int = 6) -> Dict[str, set]:
    """Return {region_type: set(keys seen)} across a sample of volumes.

    Reads raw JSON (not the loaded/filtered view) so it reflects the true
    on-disk shape, and unions ``transcription.*`` keys as ``transcription.<k>``.
    """
    census: Dict[str, set] = {}
    vol_dirs = iter_volume_dirs(output_base, only_volumes)
    if sample_volumes and len(vol_dirs) > sample_volumes:
        step = max(1, len(vol_dirs) // sample_volumes)
        vol_dirs = vol_dirs[::step][:sample_volumes]
    for vol_dir in vol_dirs:
        for _, _, data in _read_page_files(vol_dir):
            for r in data:
                rtype = r.get("type", "?")
                keys = census.setdefault(rtype, set())
                for k, v in r.items():
                    if k == "transcription" and isinstance(v, dict):
                        for tk in v:
                            keys.add(f"transcription.{tk}")
                    else:
                        keys.add(k)
    return census


def print_schema_census(output_base: Path, only_volumes: Optional[List[int]]) -> None:
    census = schema_census(output_base, only_volumes)
    print("Schema census (keys per region type, sampled):")
    for rtype in sorted(census):
        keys = ", ".join(sorted(census[rtype]))
        print(f"  {rtype}: {keys}")
