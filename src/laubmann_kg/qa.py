"""Quality-assurance pass: flag outlier entries/observations and optionally
exclude them from the graph, always recording the decision to a review table.

Policy (defaults):
- ``misdate``  – entry year outside the volume's plausible span  -> exclude entry
- ``garbage_taxon`` – unresolved taxon that is not a plausible bird name -> exclude observation
- ``nonplace`` – ``location_raw`` rejected by the place normalizer -> flag only
- ``no_observations`` – no observation, but weather/travel explain it -> flag only
- ``empty``    – entry left with nothing at all -> flag only

Exclusions are reversible: every flag (excluded or merely flagged) is written to
``qa_flags.csv`` with its reason, so a human can review and override.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from laubmann_kg.normalization.places import rejection_reason
from laubmann_kg.normalization.taxa import _norm

logger = logging.getLogger(__name__)

# German bird head-morphemes, written in taxa._norm's normalized form
# (ä->a, ö->o, ü->u, ß->ss, AND v->w — so "Vogel" normalizes to "wogel"). A
# vernacular containing any of these — or a bare bird word — is treated as a
# plausible (if unmapped) species rather than OCR garbage.
_BIRD_MORPHEMES = (
    "wogel", "meise", "fink", "drossel", "schwalbe", "ammer", "specht", "taube",
    "ente", "mowe", "laufer", "schnapper", "sanger", "pieper", "reiher", "falke",
    "adler", "eule", "kauz", "huhn", "schwanz", "kehlchen", "konig", "zeisig",
    "hanfling", "girlitz", "lerche", "grasmucke", "wurger", "sperling", "taucher",
    "segler", "ralle", "schnepfe", "kiebitz", "storch", "gans", "schwan", "krahe",
    "rabe", "elster", "haher", "kuckuck", "nachtigall", "braunelle", "kleiber",
    "bussard", "weihe", "milan", "sperber", "habicht", "dohle", "amsel", "wachtel",
    "erpel", "schwirl", "goldhahnchen", "baumlaufer", "mowen", "spatz", "star",
)
_BIRD_WORDS = {
    "amsel", "drossel", "meise", "mowe", "ente", "falke", "krahe", "specht",
    "star", "spatz", "lerche", "schwalbe", "taube", "reiher", "gans", "schwan",
    "rabe", "elster", "dohle", "kuckuck", "storch", "kiebitz", "kranich",
    "wachtel", "wogel", "finkenwogel", "meischen",
}
_DIMINUTIVE = re.compile(r"(chen|lein)$")


def plausible_bird(vernacular: str) -> bool:
    """True if the (unresolved) vernacular still looks like a German bird name.

    Lenient by design: exclusions are reversible via the review table, so we keep
    anything with a recognisable bird morpheme and only reject clear noise
    ("Tolarla", "Beidbeiss", "Wied"-style fragments)."""
    raw = _norm(vernacular or "")
    for form in (raw, _DIMINUTIVE.sub("", raw)):
        if form in _BIRD_WORDS or any(m in form for m in _BIRD_MORPHEMES):
            return True
    return False


@dataclass
class QAFlag:
    entry_id: str
    entry_uid: str
    reason: str          # misdate | garbage_taxon | nonplace | empty | no_observations
    detail: str
    action: str          # excluded | flagged
    value: str = ""


def _year_ranges(entries, config: dict) -> dict[int, tuple[int, int]]:
    """Plausible year span PER VOLUME: {volume: (lo, hi)}.

    Each diary volume covers a narrow stretch of Laubmann's life, so the
    misdate test must be scoped to the volume's own median — a single global
    median across a multi-volume run would exclude almost every entry outside
    a few years mid-corpus. Explicit ``year_min``/``year_max`` in the config
    override the medians and apply to every volume."""
    lo, hi = config.get("year_min"), config.get("year_max")
    tol = int(config.get("year_tolerance", 2))
    by_vol: dict[int, list[int]] = {}
    for e in entries:
        if e.entry_date:
            by_vol.setdefault(e.volume, []).append(int(e.entry_date[:4]))
    ranges: dict[int, tuple[int, int]] = {}
    for vol, years in by_vol.items():
        if lo and hi:
            ranges[vol] = (int(lo), int(hi))
            continue
        years.sort()
        median = years[len(years) // 2]
        ranges[vol] = (median - tol, median + tol)
    return ranges


def run_qa(entries, config: Optional[dict] = None):
    """Return ``(kept_entries, flags)``. Mutates each entry's observation list to
    drop excluded observations when ``exclude`` is on."""
    config = config or {}
    exclude = config.get("exclude", True)
    ranges = _year_ranges(entries, config)
    flags: list[QAFlag] = []
    kept = []

    for e in entries:
        drop_entry = False

        yr = ranges.get(e.volume)
        if yr and e.entry_date:
            year = int(e.entry_date[:4])
            if not yr[0] <= year <= yr[1]:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "misdate",
                    f"Jahr {year} ausserhalb {yr[0]}-{yr[1]} (Band {e.volume})",
                    "excluded" if exclude else "flagged", e.entry_date))
                drop_entry = exclude

        if e.location_raw and e.location_raw.strip():
            reason = rejection_reason(e.location_raw)
            if reason in ("bird", "garbage"):
                flags.append(QAFlag(e.entry_id, e.entry_uid, "nonplace",
                    f"Ort verworfen ({reason})", "flagged", e.location_raw.strip()))

        kept_obs = []
        for obs in e.observations:
            garbage = obs.taxon.scientific_name is None and not plausible_bird(obs.taxon.vernacular_de)
            if garbage:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "garbage_taxon",
                    "unauflösbar und nicht vogelartig",
                    "excluded" if exclude else "flagged", obs.taxon.vernacular_de))
                if exclude:
                    continue
            kept_obs.append(obs)
        e.observations = kept_obs

        if not e.observations:
            if e.weather is not None or e.travel_events:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "no_observations",
                    "kein Vogelnachweis, aber Wetter/Reise vorhanden", "flagged", ""))
            else:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "empty",
                    "keine Beobachtung (mögl. Segmentierungsfehler)", "flagged", ""))

        if not drop_entry:
            kept.append(e)

    return kept, flags


_FIELDS = ("entry_id", "entry_uid", "reason", "action", "value", "detail")


def write_review_table(flags: list[QAFlag], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS)
        writer.writeheader()
        for f in flags:
            writer.writerow({"entry_id": f.entry_id, "entry_uid": f.entry_uid,
                             "reason": f.reason, "action": f.action,
                             "value": f.value, "detail": f.detail})
    logger.info("wrote %d QA flags to %s", len(flags), path)
    return path
