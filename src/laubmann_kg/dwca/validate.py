"""Structural validation of a produced Darwin Core Archive."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from xml.etree import ElementTree

from laubmann_kg.dwca.meta_xml import DWC, ROW_TYPES

logger = logging.getLogger(__name__)

REQUIRED = ["meta.xml", "event.txt", "occurrence.txt", "multimedia.txt",
            "measurementorfact.txt"]

_DWCA_NS = "{http://rs.tdwg.org/dwc/text/}"
_EMOF_ROW_TYPE = ROW_TYPES["measurement_or_fact"]

# columns whose values must come from a closed list when non-empty
_OCCURRENCE_STATUS = ("present", "absent")


def _read_tsv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        # meta.xml declares fieldsEnclosedBy="": parse verbatim (QUOTE_NONE),
        # exactly as a spec-conformant DwC-A reader sees the bytes.
        reader = csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        return list(reader.fieldnames or []), list(reader)


def _check_meta(archive_dir: Path, problems: list[str]) -> None:
    try:
        root = ElementTree.parse(archive_dir / "meta.xml").getroot()
    except ElementTree.ParseError as exc:
        problems.append(f"meta.xml not well-formed: {exc}")
        return
    core = root.find(_DWCA_NS + "core")
    if core is None:
        problems.append("meta.xml has no <core>")
        return
    if core.get("rowType") != DWC + "Event":
        problems.append(f"meta.xml core rowType is {core.get('rowType')!r}, expected dwc:Event")
    if core.find(_DWCA_NS + "id") is None:
        problems.append("meta.xml core lacks <id>")
    core_terms = {f.get("term") for f in core.findall(_DWCA_NS + "field")}
    if DWC + "eventID" not in core_terms:
        problems.append("meta.xml core does not declare dwc:eventID as a field")
    row_types = {ext.get("rowType") for ext in root.findall(_DWCA_NS + "extension")}
    if _EMOF_ROW_TYPE not in row_types:
        problems.append("meta.xml lacks the ExtendedMeasurementOrFact extension")
    for ext in root.findall(_DWCA_NS + "extension"):
        if ext.find(_DWCA_NS + "coreid") is None:
            problems.append(f"meta.xml extension {ext.get('rowType')} lacks <coreid>")


def validate_archive(archive_dir: Path) -> list[str]:
    """Return a list of structural problems; empty means the archive is valid."""
    archive_dir = Path(archive_dir)
    problems: list[str] = []

    for name in REQUIRED:
        if not (archive_dir / name).exists():
            problems.append(f"missing file: {name}")
    if problems:
        return problems

    _check_meta(archive_dir, problems)

    _, events = _read_tsv(archive_dir / "event.txt")
    event_ids = {row["eventID"] for row in events}
    if not event_ids:
        problems.append("event core is empty")
    if len(event_ids) != len(events):
        problems.append("event.txt has duplicate eventID values")

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
    occ_ids = {r.get("occurrenceID", "") for r in occ_rows}
    for column in ("occurrenceStatus", "basisOfRecord", "scientificName", "vernacularName"):
        if column not in occ_fields:
            problems.append(f"occurrence.txt missing {column} column")
    bad_status = {r.get("occurrenceStatus", "") for r in occ_rows} - {*_OCCURRENCE_STATUS, ""}
    if bad_status:
        problems.append(f"occurrence.txt: unexpected occurrenceStatus values {sorted(bad_status)}")
    zero_present = sum(1 for r in occ_rows
                       if r.get("individualCount") == "0"
                       and r.get("occurrenceStatus") != "absent")
    if zero_present:
        problems.append(f"occurrence.txt: {zero_present} row(s) with individualCount 0 but not absent")

    mof_fields, mof_rows = _read_tsv(archive_dir / "measurementorfact.txt")
    for column in ("occurrenceID", "measurementID", "measurementType", "measurementValue"):
        if column not in mof_fields:
            problems.append(f"measurementorfact.txt missing {column} column")
    if "measurementID" in mof_fields and (
            len({r["measurementID"] for r in mof_rows}) != len(mof_rows)):
        problems.append("measurementorfact.txt has duplicate measurementID values")
    if "occurrenceID" in mof_fields:
        orphan = {r["occurrenceID"] for r in mof_rows if r.get("occurrenceID")} - occ_ids
        if orphan:
            problems.append(f"measurementorfact.txt: {len(orphan)} occurrenceID(s) "
                            "not present in occurrence.txt")

    return problems
