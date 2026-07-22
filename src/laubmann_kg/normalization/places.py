"""Normalize diary place names and resolve coordinates where confident.

The corpus ``location_raw`` column is produced by upstream page segmentation and
is noisy: it carries elevation suffixes ("Oberstdorf 843 m"), descriptor tails
("Kochel. Herzogstandhaus 1555 m"), and — where a heading was mis-segmented —
bird names or fragments that are not localities at all. This module cleans the
plausible ones and rejects the implausible ones (returning ``None``) so they do
not become ``Place`` nodes; the QA pass reports the rejects via
``rejection_reason``.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from laubmann_kg.kg.model import Place
from laubmann_kg.normalization.taxa import looks_like_bird

logger = logging.getLogger(__name__)

# Confident coordinate seeds only. Missing places get a Place node without
# coordinates rather than a fabricated location. Keys are normalized (see _key).
PLACE_GAZETTEER: dict[str, tuple[str, float, float]] = {
    "münchen": ("München", 48.1374, 11.5755),
    "kaufbeuren": ("Kaufbeuren", 47.8804, 10.6217),
    "oberstdorf": ("Oberstdorf", 47.4098, 10.2794),
    "hindelang": ("Hindelang", 47.5089, 10.3733),
    "kochel": ("Kochel", 47.6497, 11.3450),
    "dießen am ammersee": ("Dießen am Ammersee", 47.9497, 11.1044),
    "füssen": ("Füssen", 47.5714, 10.7008),
    "augsburg": ("Augsburg", 48.3717, 10.8983),
    "ulm": ("Ulm", 48.3984, 9.9908),
    "nürnberg": ("Nürnberg", 49.4521, 11.0767),
    "regensburg": ("Regensburg", 49.0134, 12.1016),
    "passau": ("Passau", 48.5665, 13.4312),
    "mering": ("Mering", 48.2653, 10.9847),
    "mühlhausen": ("Mühlhausen", 48.2500, 11.0500),
}

# Normalized head → canonical gazetteer key, folding OCR and naming variants.
_ALIASES = {
    "raufbeuren": "kaufbeuren",          # OCR variant seen in corpus
    "dießen": "dießen am ammersee",
    "diessen": "dießen am ammersee",
    "kochel am kochelsee": "kochel",
}

# Fragments observed in the corpus that are not localities.
_GARBAGE = {"rauhfutter", "rauhhautm", "rauhhaut", "rauhsturm", "rauchturm"}

_ELEVATION = re.compile(r"\s*\d{2,4}\s*m\b.*$")
_VOWEL = re.compile(r"[aeiouyäöü]", re.I)


def _clean_head(verbatim: str) -> str:
    """First locality token, with elevation and descriptor tails removed."""
    head = re.split(r"[-–—/,;]", verbatim)[0]
    head = head.split(".")[0]              # "Kochel. Herzogstandhaus 1555 m" -> "Kochel"
    head = _ELEVATION.sub("", head)        # "Oberstdorf 843 m" -> "Oberstdorf"
    return head.strip(" .")


def _key(raw: str) -> str:
    key = raw.strip().lower().strip(".")
    return _ALIASES.get(key, key)


def rejection_reason(location_raw: Optional[str]) -> Optional[str]:
    """Why a raw locality is not a place: ``empty``, ``bird``, ``garbage`` — or
    ``None`` if it is an acceptable locality."""
    if not location_raw or not location_raw.strip():
        return "empty"
    head = _clean_head(location_raw)
    if len(head) < 3 or not _VOWEL.search(head):
        return "garbage"
    if _key(head) in _GARBAGE:
        return "garbage"
    if looks_like_bird(head):
        return "bird"
    return None


def normalize_place(location_raw: Optional[str]) -> Optional[Place]:
    """Return a cleaned Place for a locality string, or ``None`` if the string is
    not a plausible locality (empty, a bird name, or corpus garbage)."""
    if rejection_reason(location_raw):
        return None
    verbatim = location_raw.strip()
    head = _clean_head(verbatim)
    seed = PLACE_GAZETTEER.get(_key(head))
    if seed:
        canonical, lat, lon = seed
        return Place(verbatim=verbatim, canonical=canonical, lat=lat, long=lon)
    return Place(verbatim=verbatim, canonical=head or None)
