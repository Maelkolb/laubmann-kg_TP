"""Build GBIF Multimedia extension rows from the corpus multimodal catalogue."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "identifier", "type", "format", "title", "description",
    "subjectPart",
]

_EXT_FORMAT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tif": "image/tiff"}


def _format(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_FORMAT.get(ext, "image/png")


def build_multimedia(result: "ExtractionResult") -> list[dict]:
    rows = []
    for region in result.multimodal:
        entry_uid = region.get("entry_uid") or ""
        crop = region.get("crop") or ""
        if not entry_uid or not crop:
            continue
        rows.append({
            "eventID": entry_uid,
            "identifier": crop,
            "type": "StillImage",
            "format": _format(crop),
            "title": region.get("region_type") or "",
            "description": region.get("description") or "",
            "subjectPart": region.get("visible_text") or "",
        })
    return rows


def media_by_entry(result: "ExtractionResult") -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for region in result.multimodal:
        entry_uid = region.get("entry_uid") or ""
        crop = region.get("crop") or ""
        if entry_uid and crop:
            mapping.setdefault(entry_uid, []).append(crop)
    return mapping
