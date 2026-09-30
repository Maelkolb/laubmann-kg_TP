"""Reviewer corrections of the transcription (validation UI export ``review/text_corrections.csv``).

A misreading of the handwriting is fixed where it happened: in the text of
that one entry ("Kameradeneingänge" -> "Hausrotschwänzchen", "5 Eis- Gimpel"
-> "Stare, Gimpel", "8. Mai" -> "9. Mai"). The correction is applied before
extraction, so the model reads the corrected entry and everything it derives
(species, counts, places, dates) follows from the right text; the changed
prompt misses the LLM cache, so only corrected entries are extracted anew. The
corpus is not modified; the graph records every correction as a skos:note of
the entry and in the QA table (``reading_corrected`` / ``reading_unmatched``).

CSV contract (one row per correction; extra columns are ignored)::

    entry_uid    required (entry_id alone is accepted as a fallback)
    entry_id     informative
    old_text     the exact text as transcribed (must occur in the entry text)
    new_text     what the scan shows
    note, reviewed_by, reviewed_at   audit only
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.normalization.dates import parse_german_date
from laubmann_kg.qa import QAFlag

logger = logging.getLogger(__name__)

READING_FIELDS = ["entry_uid", "entry_id", "old_text", "new_text", "note", "reviewed_by", "reviewed_at"]


@dataclass(frozen=True)
class Reading:
    old: str
    new: str
    entry_uid: str = ""
    entry_id: str = ""
    note: str = ""


def load_readings(path) -> list[Reading]:
    if not path:
        return []
    path = Path(path)
    if not path.exists():
        logger.info("no reading corrections at %s", path)
        return []
    out: list[Reading] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for i, row in enumerate(csv.DictReader(handle), 2):
            old, new = row.get("old_text") or "", (row.get("new_text") or "").strip()
            uid, eid = (row.get("entry_uid") or "").strip(), (row.get("entry_id") or "").strip()
            if not old.strip() or not new or not (uid or eid) or old == new:
                logger.warning("%s:%d skipped (entry_uid/old_text/new_text invalid)", path.name, i)
                continue
            out.append(Reading(old, new, uid, eid, (row.get("note") or "").strip()))
    return out


def apply_readings(entries: list[DiaryEntry], readings: list[Reading]) -> list[QAFlag]:
    """Apply ``readings`` to the entry texts in place (before extraction).
    Returns the audit flags."""
    if not readings:
        return []
    by_uid: dict[str, list[Reading]] = defaultdict(list)
    by_id: dict[str, list[Reading]] = defaultdict(list)
    for r in readings:
        (by_uid[r.entry_uid] if r.entry_uid else by_id[r.entry_id]).append(r)
    flags: list[QAFlag] = []
    matched: set[int] = set()
    for e in entries:
        for r in by_uid.get(e.entry_uid, []) + by_id.get(e.entry_id, []):
            matched.add(id(r))
            if r.old not in (e.text_clean or ""):
                flags.append(QAFlag(e.entry_id, e.entry_uid, "reading_unmatched",
                                    f"Lesung „{r.old}“ steht nicht (mehr) im Eintragstext", "flagged", f"{r.old} -> {r.new}"))
                logger.warning("reading correction matched nothing: %r -> %r (%s)", r.old, r.new, e.entry_id)
                continue
            e.text_clean = e.text_clean.replace(r.old, r.new, 1)
            # the header strings go to the prompt separately: keep them consistent
            if e.verbatim_event_date and r.old in e.verbatim_event_date:
                e.verbatim_event_date = e.verbatim_event_date.replace(r.old, r.new, 1)
                e.entry_date = parse_german_date(e.verbatim_event_date) or e.entry_date
            if e.location_raw and r.old in e.location_raw:
                e.location_raw = e.location_raw.replace(r.old, r.new, 1)
            e.reading_notes.append(f"Lesung bei der Durchsicht korrigiert: „{r.old}“ → „{r.new}“"
                                   + (f" ({r.note})" if r.note else ""))
            flags.append(QAFlag(e.entry_id, e.entry_uid, "reading_corrected",
                                f"Lesung korrigiert: „{r.old}“ → „{r.new}“" + (f"; {r.note}" if r.note else ""),
                                "flagged", f"{r.old} -> {r.new}"))
    for r in readings:
        if id(r) not in matched:
            flags.append(QAFlag(r.entry_id, r.entry_uid, "reading_unmatched",
                                "Eintrag nicht in diesem Lauf", "flagged", f"{r.old} -> {r.new}"))
    logger.info("reading corrections: %d applied, %d unmatched", sum(f.reason == "reading_corrected" for f in flags),
                sum(f.reason == "reading_unmatched" for f in flags))
    return flags
