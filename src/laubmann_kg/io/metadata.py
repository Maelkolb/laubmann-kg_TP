"""Read multimodal (non-text region) metadata from the corpus.

The delivered corpus ships ``multimodal.md`` (a Markdown catalogue whose HTML
comments carry the structured fields). The frozen contract also allows a
``multimodal.csv``; since ontology 0.6.0 the preferred input is
``multimodal_regions.jsonl`` (HistOrniGraph_addons/build_multimodal_regions.py:
catalogue v2 images/objects + selected text inserts, duplicate scans removed,
relinked to the entries of the corpus it was built against). All three yield
the same record shape; ``to_region`` turns a record into the model object.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from laubmann_kg.io.csv import read_dicts
from laubmann_kg.kg.model import MultimodalRegion
from laubmann_kg.normalization import vocabularies as vocab

logger = logging.getLogger(__name__)

_MM_COMMENT = re.compile(r"<!--\s*mm\s+(.*?)-->", re.S)
_KV = re.compile(r"(\w+)=([^\s]*)")
_VOL_HEADER = re.compile(r"^##\s+Vol\.\s+(\d+)", re.M)
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_SCAN = re.compile(r"scan\s+(\d+)")
_VISIBLE = re.compile(r"\*Visible text:\*\s*(.*)")

_FIELDS = ("region_uid", "page_uid", "region_type", "reading_order", "insert_id",
           "insert_state", "entry_uid", "volume", "scan", "crop", "description",
           "visible_text")


def _blocks(text: str) -> list[tuple[int, str]]:
    matches = list(_MM_COMMENT.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.start(), text[m.start():end]))
    return out


def _volume_at(text: str, pos: int) -> str:
    vol = ""
    for m in _VOL_HEADER.finditer(text):
        if m.start() > pos:
            break
        vol = str(int(m.group(1)))
    return vol


# layout region type -> lkg:regionKind when the catalogue gives no finer kind
_KIND_BY_TYPE = {"ImageRegion": "drawing", "GraphicRegion": "drawing", "ObjectRegion": "object",
                 "ParagraphRegion": "text-insert", "ListRegion": "list", "TableRegion": "list",
                 "InsertRegion": "text-insert"}


def to_region(record: dict, volume: Optional[int] = None) -> Optional[MultimodalRegion]:
    """A catalogue record as a ``MultimodalRegion`` (None without a region uid).
    Marginal notes are not multimodal regions of the graph (0.6.0)."""
    uid = (record.get("region_uid") or "").strip()
    rtype = record.get("region_type") or record.get("type_original") or ""
    if not uid or rtype == "MarginaliaRegion" and not record.get("kind"):
        return None
    kind = record.get("kind") if record.get("kind") in vocab.REGION_KINDS else _KIND_BY_TYPE.get(rtype, "drawing")
    vol = record.get("volume")
    return MultimodalRegion(
        region_uid=uid,
        page_uid=record.get("page_uid") or "",
        page_id=record.get("page_id") or "",
        volume=int(vol) if str(vol or "").strip().isdigit() else int(volume or 0),
        scan=str(record.get("scan")) if record.get("scan") not in (None, "") else None,
        entry_uid=record.get("entry_uid") or None,
        kind=kind,
        description=(record.get("description") or "").strip() or None,
        visible_text=(record.get("visible_text") or "").strip() or None,
        crop=record.get("crop") or None,
        region_type=rtype or None,
    )


def read_multimodal(path: Path) -> list[dict[str, str]]:
    """Return one record per non-text region, keyed for join on ``entry_uid``."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return [dict(row) for row in read_dicts(path)]
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        logger.info("read %d multimodal regions from %s", len(records), path)
        return records

    text = path.read_text(encoding="utf-8")
    records: list[dict[str, str]] = []
    for pos, block in _blocks(text):
        comment = _MM_COMMENT.search(block)
        kv = dict(_KV.findall(comment.group(1))) if comment else {}
        image = _IMAGE.search(block)
        scan = _SCAN.search(block)
        visible = _VISIBLE.search(block)
        body = _strip_meta(block)
        records.append({
            "region_uid": kv.get("region_uid", ""),
            "page_uid": kv.get("page_uid", ""),
            "region_type": kv.get("type", ""),
            "reading_order": kv.get("order", ""),
            "insert_id": kv.get("insert_id", ""),
            "insert_state": kv.get("insert_state", ""),
            "entry_uid": kv.get("entry_uid", ""),
            "volume": _volume_at(text, pos),
            "scan": scan.group(1) if scan else "",
            "crop": image.group(1) if image else "",
            "description": body,
            "visible_text": visible.group(1).strip() if visible else "",
        })
    logger.info("read %d multimodal regions from %s", len(records), path)
    return records


def _strip_meta(block: str) -> str:
    lines = []
    for line in block.splitlines():
        stripped = line.strip()
        if (not stripped or stripped.startswith("<!--") or stripped.startswith("#")
                or stripped.startswith("![") or stripped.startswith("*Visible text:*")):
            continue
        lines.append(stripped)
    return " ".join(lines).strip()
