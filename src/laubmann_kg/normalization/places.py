"""Normalize diary place names and resolve coordinates where confident."""

from __future__ import annotations

import logging
import re
from typing import Optional

from laubmann_kg.kg.model import Place

logger = logging.getLogger(__name__)

# Confident coordinate seeds only. Missing places get a Place node without
# coordinates rather than a fabricated location.
PLACE_GAZETTEER: dict[str, tuple[str, float, float]] = {
    "münchen": ("München", 48.1374, 11.5755),
    "kaufbeuren": ("Kaufbeuren", 47.8804, 10.6217),
    "oberstdorf": ("Oberstdorf", 47.4098, 10.2794),
    "augsburg": ("Augsburg", 48.3717, 10.8983),
    "ulm": ("Ulm", 48.3984, 9.9908),
    "nürnberg": ("Nürnberg", 49.4521, 11.0767),
    "regensburg": ("Regensburg", 49.0134, 12.1016),
    "passau": ("Passau", 48.5665, 13.4312),
    "mering": ("Mering", 48.2653, 10.9847),
    "mühlhausen": ("Mühlhausen", 48.2500, 11.0500),
}

_ALIASES = {
    "raufbeuren": "kaufbeuren",  # OCR variant seen in corpus
}


def _key(raw: str) -> str:
    key = raw.strip().lower().strip(".")
    return _ALIASES.get(key, key)


def normalize_place(location_raw: Optional[str]) -> Optional[Place]:
    """Return a Place for a raw locality string, with coordinates if seeded."""
    if not location_raw or not location_raw.strip():
        return None
    verbatim = location_raw.strip()
    # A locality may be a compound like "München - Gossenzugen"; key on the first.
    head = re.split(r"[-–—/]", verbatim)[0].strip()
    seed = PLACE_GAZETTEER.get(_key(head))
    if seed:
        canonical, lat, lon = seed
        return Place(verbatim=verbatim, canonical=canonical, lat=lat, long=lon)
    return Place(verbatim=verbatim, canonical=head or None)
