"""Extract and normalize person names mentioned in diary entries."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Titled / abbreviated-forename mentions: "Prof. Dümmer", "K. Lanker",
# "Herr Schuster". Conservative: only fires on an explicit title or initial.
_PERSON_RE = re.compile(
    r"\b(?:(?:Prof|Dr|Herr|Frau|Hr|Fr|Graf|Baron|P|St)\.?\s+"
    r"|[A-ZÄÖÜ]\.\s+)"
    r"([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)"
)


@dataclass(frozen=True)
class PersonMention:
    surface: str
    name: str


def extract_persons(text: str) -> list[PersonMention]:
    """Return distinct titled person mentions, ordered by appearance."""
    seen: dict[str, PersonMention] = {}
    for match in _PERSON_RE.finditer(text or ""):
        name = match.group(1).strip()
        surface = match.group(0).strip()
        if name not in seen:
            seen[name] = PersonMention(surface=surface, name=name)
    return list(seen.values())
