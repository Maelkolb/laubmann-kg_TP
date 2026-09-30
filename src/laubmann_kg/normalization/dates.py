"""Normalize German diary dates to ISO 8601."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

GERMAN_MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

_GERMAN_DATE_RE = re.compile(
    r"(\d{1,2})\.?\s*([A-Za-zäöüÄÖÜ]+)\s+(\d{4})", re.UNICODE
)


def _valid_iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_german_date(text: str) -> Optional[str]:
    """Parse '7. April 1917' → '1917-04-07'. Returns None if not parseable."""
    if not text:
        return None
    match = _GERMAN_DATE_RE.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = GERMAN_MONTHS.get(month_name.lower())
    if month is None:
        return None
    return _valid_iso(int(year), month, int(day))


def normalize_date(date_raw: Optional[str], date_norm: Optional[str] = None) -> Optional[str]:
    """Return an ISO date. Prefer the corpus-provided ``date_norm`` (already
    normalized upstream); fall back to parsing ``date_raw``."""
    if date_norm:
        match = _ISO_RE.match(date_norm.strip())
        if match and _valid_iso(*(int(g) for g in match.groups())):
            return date_norm.strip()
    return parse_german_date(date_raw or "")


def event_date(entry) -> str:
    """Darwin Core eventDate of an entry: ISO date, or the ISO interval
    ``start/end`` for a multi-day entry (shared by the RDF and the DwC-A)."""
    start = entry.entry_date or ""
    end = getattr(entry, "entry_date_end", None)
    if start and end and end != start:
        return f"{start}/{end}"
    return start


def obs_event_date(obs, entry_date: str) -> str:
    """Darwin Core eventDate of a record: its own date (or date range) when the
    text gives one, else the entry's date or interval."""
    if obs.event_date:
        end = getattr(obs, "event_date_end", None)
        return f"{obs.event_date}/{end}" if end and end != obs.event_date else obs.event_date
    return entry_date
