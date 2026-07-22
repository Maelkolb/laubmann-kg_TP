"""CSV read/write helpers for the corpus interface and DwC-A output."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

# Raise the field-size limit: text_clean can exceed the 128 KB default.
csv.field_size_limit(10 * 1024 * 1024)


def read_dicts(path: Path) -> Iterator[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def read_entries(path: Path, volume: Optional[int] = None) -> list[dict[str, str]]:
    """Read the corpus ``entries.csv``, optionally filtered to one volume.

    Tolerant of the delivered column set: callers use ``.get()`` so a switch to
    the deduped corpus (which may add stream_start/stream_end/text_raw) needs no
    code change. See INTERFACES.md.
    """
    rows = [row for row in read_dicts(path)
            if volume is None or (row.get("volume") or "").strip() == str(volume)]
    logger.info("read %d entries from %s (volume=%s)", len(rows), path, volume)
    return rows


def write_rows(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore",
                                delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    logger.info("wrote %d rows to %s", count, path)
    return count
