"""Review-CSV I/O for the linking stage (apply_enrichment decision contract)."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# apply_enrichment.py decision contract: these values mark a row as accepted.
_ACCEPT_DECISIONS = {"y", "yes", "merge", "1"}


def write_review_csv(rows: list[dict], fieldnames: list[str], path: Path) -> Path:
    """Write review rows, merging with any existing file at ``path``: non-blank
    decisions carry over onto new rows matching on the first (key) column, and
    an empty row list leaves an existing file untouched — human adjudication
    must survive reruns and failed sections."""
    path = Path(path)
    if not rows and path.exists():
        return path
    decisions: dict[str, str] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for old in csv.DictReader(handle):
                decision = (old.get("decision") or "").strip()
                if decision:
                    decisions.setdefault(old.get(fieldnames[0]) or "", decision)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            key = str(row.get(fieldnames[0]) or "")
            writer.writerow({**row, "decision": decisions.get(key, "")})
    logger.info("wrote %d review rows to %s", len(rows), path)
    return path


def load_reviewed(path) -> list[dict]:
    """Rows a human adjudicator accepted (decision y/yes/merge/1)."""
    path = Path(path)
    if not path.exists():
        logger.warning("reviewed CSV not found: %s", path)
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle)
                if (row.get("decision") or "").strip().lower() in _ACCEPT_DECISIONS]
