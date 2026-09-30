"""Build GBIF Multimedia extension rows from the corpus multimodal catalogue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from laubmann_kg.kg.model import data_iri
from laubmann_kg.kg.rdf import image_url

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

FIELDS = [
    "eventID", "identifier", "type", "format", "title", "description",
]

_EXT_FORMAT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tif": "image/tiff"}


def _format(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_FORMAT.get(ext, "image/png")


def _get(region, key: str):
    """Attribute of a MultimodalRegion, or key of a legacy catalogue dict."""
    return region.get(key) if isinstance(region, dict) else getattr(region, key, None)


def _dated_entries(result: "ExtractionResult") -> set[str]:
    """Entries that become events (the event core skips undated entries)."""
    return {e.entry_uid for e in result.entries if e.entry_date}


def build_multimedia(result: "ExtractionResult") -> list[dict]:
    """One row per region crop of a dated entry, only once the crops are hosted
    (multimodal.image_base_url): GBIF needs a URL as identifier, a file path
    would be published as a broken link. Until then the graph references the
    crops by path (dcterms:identifier)."""
    rows = []
    base_url = getattr(result, "image_base_url", None)
    if not base_url:
        return rows
    events = _dated_entries(result)
    for region in result.multimodal:
        entry_uid = _get(region, "entry_uid") or ""
        crop = _get(region, "crop") or ""
        if not entry_uid or not crop or entry_uid not in events:
            continue
        rows.append({
            "eventID": data_iri("entry_" + entry_uid),
            "identifier": image_url(base_url, crop),
            "type": "StillImage",            # the crop is an image, whatever it shows
            "format": _format(crop),
            "title": _get(region, "kind") or _get(region, "region_type") or "",
            "description": _description(region),
        })
    return rows


def _description(region) -> str:
    """Region description; any transcribed visible text is folded in (Simple
    Multimedia has no dedicated term for it)."""
    description = " ".join((_get(region, "description") or "").split())
    visible = " ".join((_get(region, "visible_text") or "").split())
    if visible:
        return f"{description} — Text: {visible}" if description else f"Text: {visible}"
    return description

