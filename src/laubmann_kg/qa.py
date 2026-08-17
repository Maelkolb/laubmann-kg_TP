"""Quality-assurance pass: flag outlier entries/observations and optionally
exclude them from the graph, always recording the decision to a review table.

QA is threshold-based on signals the MODEL provides (is_bird, taxon_rank,
confidence, date plausibility, place kind) — it contains no keyword rules that
decide content. Policy (defaults, all configurable under ``qa:``):

- ``non_bird``          – model says the organism is not a bird           -> exclude observation
- ``low_confidence_taxon`` – no scientific name, rank unknown/unstated, and a
  STATED model confidence < ``min_taxon_confidence`` (0.3)                 -> exclude observation
- ``implausible_date``  – model marks the header date contradicted/unrepairable -> exclude entry
- ``misdate``           – entry year outside the volume's median ± tolerance -> flag (exclude only
  with ``exclude_misdate: true``; retrospective/digest entries are never excluded by it)
- ``date_corrected``    – model corrected the header date                   -> flag
- ``record_type_conflict`` – model called an attributed/cited record field-observation -> flag
- ``nonplace``          – no usable entry place although a header exists     -> flag
- ``no_observations``   – no observation, but weather/travel explain it      -> flag
- ``empty``             – entry left with nothing at all                     -> flag

Exclusions are reversible: every flag (excluded or merely flagged) is written to
``qa_flags.csv`` with its reason, so a human can review and override.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class QAFlag:
    entry_id: str
    entry_uid: str
    reason: str          # see module docstring
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


_RETROSPECTIVE_KINDS = ("species-digest", "retrospective", "correspondence")


def run_qa(entries, config: Optional[dict] = None):
    """Return ``(kept_entries, flags)``. Mutates each entry's observation list to
    drop excluded observations when ``exclude`` is on."""
    config = config or {}
    exclude = config.get("exclude", True)
    exclude_non_bird = exclude and config.get("exclude_non_bird", True)
    exclude_low_conf = exclude and config.get("exclude_low_confidence_taxon", True)
    exclude_implausible = exclude and config.get("exclude_implausible_date", True)
    exclude_misdate = exclude and config.get("exclude_misdate", False)
    min_conf = float(config.get("min_taxon_confidence", 0.3))
    ranges = _year_ranges(entries, config)
    flags: list[QAFlag] = []
    kept = []

    def _act(excluded: bool) -> str:
        return "excluded" if excluded else "flagged"

    for e in entries:
        drop_entry = False

        # --- date -----------------------------------------------------------
        if e.date_plausible is False:
            flags.append(QAFlag(e.entry_id, e.entry_uid, "implausible_date",
                e.date_note or "Datum laut Modell widersprüchlich und nicht korrigierbar",
                _act(exclude_implausible), e.entry_date or ""))
            drop_entry = drop_entry or exclude_implausible
        elif e.header_date and e.entry_date and e.header_date != e.entry_date:
            flags.append(QAFlag(e.entry_id, e.entry_uid, "date_corrected",
                e.date_note or f"Kopfzeile {e.header_date} -> {e.entry_date}",
                "flagged", e.entry_date))

        yr = ranges.get(e.volume)
        if yr and e.entry_date:
            year = int(e.entry_date[:4])
            if not yr[0] <= year <= yr[1]:
                retrospective = (e.entry_kind in _RETROSPECTIVE_KINDS)
                excluded = exclude_misdate and not retrospective
                flags.append(QAFlag(e.entry_id, e.entry_uid, "misdate",
                    f"Jahr {year} ausserhalb {yr[0]}-{yr[1]} (Band {e.volume})"
                    + (f"; Eintragstyp {e.entry_kind}" if e.entry_kind else ""),
                    _act(excluded), e.entry_date))
                drop_entry = drop_entry or excluded

        # --- place ----------------------------------------------------------
        if e.place is None and e.location_raw and e.location_raw.strip():
            flags.append(QAFlag(e.entry_id, e.entry_uid, "nonplace",
                "kein verwertbarer Ort (Kopfzeile laut Modell unbrauchbar)",
                "flagged", e.location_raw.strip()))

        # --- observations ---------------------------------------------------
        kept_obs = []
        for obs in e.observations:
            taxon = obs.taxon
            if taxon.is_bird is False:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "non_bird",
                    "laut Modell kein Vogel" + (f" ({taxon.scientific_name})" if taxon.scientific_name else ""),
                    _act(exclude_non_bird), taxon.vernacular_de))
                if exclude_non_bird:
                    continue
            elif (taxon.scientific_name is None
                  and (taxon.rank in (None, "unknown"))
                  and taxon.confidence is not None and taxon.confidence < min_conf):
                # only a STATED low model confidence excludes; the offline backend
                # and legacy responses carry no confidence and are kept
                flags.append(QAFlag(e.entry_id, e.entry_uid, "low_confidence_taxon",
                    f"kein wissenschaftlicher Name, Rang unbekannt, Konfidenz {taxon.confidence}",
                    _act(exclude_low_conf), taxon.vernacular_de))
                if exclude_low_conf:
                    continue
            if "record_type_conflict" in obs.flags:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "record_type_conflict",
                    "field-observation trotz Beobachter/Zitat — Modellangabe beibehalten",
                    "flagged", taxon.vernacular_de))
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
