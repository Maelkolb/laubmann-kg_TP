"""Structural validation of a produced Darwin Core Archive."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

REQUIRED = ["meta.xml", "event.txt", "occurrence.txt", "multimedia.txt",
            "measurementorfact.txt"]


def _read_tsv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def validate_archive(archive_dir: Path) -> list[str]:
    """Return a list of structural problems; empty means the archive is valid."""
    archive_dir = Path(archive_dir)
    problems: list[str] = []

    for name in REQUIRED:
        if not (archive_dir / name).exists():
            problems.append(f"missing file: {name}")
    if problems:
        return problems

    try:
        ElementTree.parse(archive_dir / "meta.xml")
    except ElementTree.ParseError as exc:
        problems.append(f"meta.xml not well-formed: {exc}")

    _, events = _read_tsv(archive_dir / "event.txt")
    event_ids = {row["eventID"] for row in events}
    if not event_ids:
        problems.append("event core is empty")

    for ext in ("occurrence.txt", "measurementorfact.txt", "multimedia.txt"):
        _, rows = _read_tsv(archive_dir / ext)
        dangling = {r.get("eventID", "") for r in rows} - event_ids
        if dangling:
            problems.append(f"{ext}: {len(dangling)} eventID(s) not present in event core")

    occ_fields, occ_rows = _read_tsv(archive_dir / "occurrence.txt")
    if "occurrenceID" not in occ_fields:
        problems.append("occurrence.txt missing occurrenceID column")
    elif len({r["occurrenceID"] for r in occ_rows}) != len(occ_rows):
        problems.append("occurrence.txt has duplicate occurrenceID values")

    return problems
